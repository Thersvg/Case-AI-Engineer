import html as html_lib
import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from app.config import get_settings
from app.models import Lead

MAX_PUBLIC_RESPONSE_BYTES = 2_000_000

SECTOR_TAXONOMY = {
    "Financeiro": ("financeiro", "financial services", "banking", "bank", "banco", "fintech", "crédito", "payments", "pagamentos"),
    "Saúde": ("saúde", "healthcare", "health care", "hospital", "clinic", "clínica", "medical"),
    "Tecnologia": ("tecnologia", "technology", "software", "cloud computing", "cybersecurity", "cibersegurança", "saas"),
    "Varejo": ("varejo", "retail", "e-commerce", "ecommerce"),
    "Aeroespacial e defesa": ("aeroespacial", "aerospace", "defense", "defence", "spacecraft", "foguete", "rocket", "launch services", "satellite"),
    "Manufatura": ("manufatura", "manufacturing", "industrial"),
    "Governo": ("governo", "government", "public sector", "setor público"),
}


def validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid public URL")
    if parsed.port and parsed.port not in {80, 443}:
        raise ValueError("Public URL uses a forbidden port")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Public hostname could not be resolved") from exc
    if not addresses:
        raise ValueError("Public hostname has no address")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Private or reserved network targets are forbidden")


def safe_public_get(url: str, timeout: int, headers: dict[str, str]) -> httpx.Response:
    current = url
    for _ in range(4):
        validate_public_url(current)
        response = httpx.get(current, follow_redirects=False, timeout=timeout, headers=headers)
        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                raise ValueError("Redirect without destination")
            current = urljoin(current, location)
            continue
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > MAX_PUBLIC_RESPONSE_BYTES:
            raise ValueError("Public response is too large")
        if len(response.content) > MAX_PUBLIC_RESPONSE_BYTES:
            raise ValueError("Public response is too large")
        return response
    raise ValueError("Too many redirects")


@dataclass
class EnrichmentData:
    sector: str
    company_size: str
    interest_signal: str
    source: str
    confidence: float
    role_validation: str
    professional_presence: str
    qualification_score: int
    research_sources: str | None = None


class FakeEnrichmentProvider:
    def enrich(self, lead: Lead) -> EnrichmentData:
        company_text = (lead.company or "").lower()
        sector = "Financeiro" if any(word in company_text for word in ("bank", "banco", "fin")) else "Tecnologia"
        domain = str(lead.email).split("@")[-1]
        return EnrichmentData(
            sector=sector,
            company_size="200–1000 funcionários",
            interest_signal=f"Cargo {lead.role or 'não informado'} relacionado à decisão de tecnologia e segurança.",
            source=f"demo://public-company-profile/{domain}",
            confidence=0.65,
            role_validation=f"Cargo informado: {lead.role or 'não informado'} (dado de demonstração)",
            professional_presence=lead.linkedin_url or "Não localizada",
            qualification_score=85,
            research_sources=None,
        )


class UnavailableEnrichmentProvider:
    def enrich(self, lead: Lead) -> EnrichmentData:
        return EnrichmentData(
            sector="Não identificado",
            company_size="Não identificado",
            interest_signal="Não foi possível localizar uma fonte pública confiável para este participante.",
            source="public_web:unavailable",
            confidence=0,
            role_validation=f"Cargo informado pelo participante: {lead.role or 'não informado'}; não validado publicamente",
            professional_presence=lead.linkedin_url or "Não localizada",
            qualification_score=PublicWebsiteEnrichmentProvider._qualification_score(lead, "Não identificado", "Não identificado"),
            research_sources=None,
        )


class PublicWebsiteEnrichmentProvider:
    @staticmethod
    def _sector_from_text(text: str) -> str:
        lowered = text.lower()
        scores = {
            sector: sum(1 for term in terms if term in lowered)
            for sector, terms in SECTOR_TAXONOMY.items()
        }
        best_sector, best_score = max(scores.items(), key=lambda item: item[1])
        return best_sector if best_score else "Não identificado"

    @staticmethod
    def _sector_from_evidence(value: object, evidence: str) -> str:
        candidate = str(value or "").strip().lower()
        evidence_lower = evidence.lower()
        if not candidate or not evidence_lower:
            return "Não identificado"
        for canonical, terms in SECTOR_TAXONOMY.items():
            candidate_matches = candidate == canonical.lower() or any(term in candidate for term in terms)
            evidence_matches = any(term in evidence_lower for term in terms)
            if candidate_matches and evidence_matches:
                return canonical
        return "Não identificado"

    @staticmethod
    def _qualification_score(lead: Lead, sector: str, company_size: str) -> int:
        role = (lead.role or "").lower()
        decision_terms = ("founder", "co-founder", "fundador", "ceo", "owner", "sócio", "ciso", "cto", "cio", "diretor", "director", "head", "gestor", "manager", "risk", "risco", "segurança", "security", "ti")
        score = 40 if any(term in role for term in decision_terms) else 10
        size_numbers = [int(value.replace(".", "")) for value in re.findall(r"\d[\d.]*", company_size)]
        if size_numbers and max(size_numbers) >= 200:
            score += 35
        elif not company_size.startswith("Não identificado"):
            score += 15
        if sector != "Não identificado":
            score += 15
        if lead.company_website:
            score += 10
        return min(score, 100)

    @staticmethod
    def _source_url(lead: Lead) -> str:
        candidate = (lead.company_website or "").strip()
        if candidate and not candidate.startswith(("http://", "https://")):
            candidate = f"https://{candidate}"
        if not candidate:
            domain = str(lead.email).split("@")[-1].lower()
            if domain in {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com"} or "." not in domain:
                raise ValueError("Corporate website required for public enrichment")
            candidate = f"https://{domain}"
        validate_public_url(candidate)
        return candidate

    @staticmethod
    def _visible_text(page: str) -> str:
        cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        return re.sub(r"\s+", " ", html_lib.unescape(cleaned)).strip()

    @staticmethod
    def _company_size(text: str) -> str:
        patterns = (
            r"(?:mais de|over|more than)\s+(\d[\d.]*)\s+(?:funcionários|employees|colaboradores)",
            r"(\d[\d.]*)\+?\s+(?:funcionários|employees|colaboradores)",
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return f"Aproximadamente {match.group(1)}+ funcionários"
        return "Não identificado publicamente"

    @staticmethod
    def _gemini_research(lead: Lead, text: str) -> dict | None:
        settings = get_settings()
        if not settings.enrichment_search_enabled or settings.llm_provider != "gemini" or not settings.gemini_api_key:
            return None
        prompt = {
            "task": "Pesquise a empresa e o profissional usando somente fontes públicas. Retorne apenas JSON. Cada dado precisa de uma evidência textual específica; sem evidência, use Não identificado. Não use o domínio do e-mail como evidência e não confunda homônimos.",
            "lead": {"name": lead.name, "company": lead.company, "declared_role": lead.role, "website": lead.company_website, "linkedin_reference": lead.linkedin_url},
            "public_evidence_excerpt": text[:10000],
            "allowed_sectors": list(SECTOR_TAXONOMY),
            "schema": {"company_match": "boolean", "sector": "um allowed_sectors ou Não identificado", "sector_evidence": "trecho factual curto", "company_size": "string ou Não identificado publicamente", "company_size_evidence": "trecho factual curto", "role_validation": "cargo validado ou declarado, não validado", "role_evidence": "trecho que associa pessoa, cargo e empresa", "professional_presence": "URL encontrada ou Não localizada", "interest_signal": "sinal factual de segurança ou Não identificado", "interest_evidence": "trecho factual curto", "confidence": "0 a 1"},
        }
        try:
            response = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{settings.llm_model}:generateContent",
                headers={"x-goog-api-key": settings.gemini_api_key, "content-type": "application/json"},
                json={"contents": [{"parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}], "tools": [{"google_search": {}}], "generationConfig": {"temperature": 0.1}},
                timeout=40,
            )
            response.raise_for_status()
            candidate = response.json()["candidates"][0]
            raw = candidate["content"]["parts"][0]["text"].strip()
            raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.IGNORECASE).strip()
            if not raw.startswith("{"):
                match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
                raw = match.group(0) if match else raw
            result = json.loads(raw)
            chunks = candidate.get("groundingMetadata", {}).get("groundingChunks", [])
            sources = []
            for chunk in chunks:
                web = chunk.get("web", {})
                if web.get("uri"):
                    sources.append(f"{web.get('title', 'Fonte')}: {web['uri']}")
            if not sources or not isinstance(result, dict):
                return None
            result["_sources"] = sources[:5]
            return result
        except (httpx.HTTPError, KeyError, json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _gemini_analysis(lead: Lead, text: str) -> dict | None:
        settings = get_settings()
        if settings.llm_provider != "gemini" or not settings.gemini_api_key:
            return None
        prompt = {
            "task": "Classifique a empresa somente com base no conteúdo público fornecido. Não invente dados. Retorne JSON.",
            "company": lead.company,
            "website_content": text[:12_000],
            "allowed_sectors": list(SECTOR_TAXONOMY),
            "schema": {
                "sector": "um allowed_sectors ou Não identificado",
                "sector_evidence": "trecho do website que sustenta o setor",
                "company_size": "porte/faixa somente se houver evidência, senão Não identificado publicamente",
                "company_size_evidence": "trecho do website que sustenta o porte",
                "interest_signal": "resumo factual de até 180 caracteres",
                "interest_evidence": "trecho do website que sustenta o sinal",
                "confidence": "número entre 0 e 1 proporcional à evidência",
            },
        }
        try:
            response = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{settings.llm_model}:generateContent",
                headers={"x-goog-api-key": settings.gemini_api_key, "content-type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
                },
                timeout=30,
            )
            response.raise_for_status()
            result = json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"])
            return result if isinstance(result, dict) else None
        except (httpx.HTTPError, KeyError, json.JSONDecodeError, TypeError):
            return None

    def enrich(self, lead: Lead) -> EnrichmentData:
        url = self._source_url(lead)
        response = safe_public_get(url, timeout=10, headers={"User-Agent": "VigilSummitBot/1.0"})
        response.raise_for_status()
        html = response.text[:200_000]
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        descriptions = re.findall(r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\'](.*?)["\']', html, flags=re.IGNORECASE | re.DOTALL)
        visible_text = self._visible_text(html)[:12_000]
        public_text = " ".join(
            filter(None, [title_match.group(1).strip() if title_match else "", *descriptions, visible_text])
        )
        for path in ("/sobre", "/about"):
            try:
                about = safe_public_get(urljoin(str(response.url), path), timeout=6, headers={"User-Agent": "VigilSummitBot/1.0"})
                if about.is_success:
                    public_text += " " + self._visible_text(about.text[:150_000])[:8_000]
                    break
            except (httpx.HTTPError, ValueError):
                continue
        lowered = public_text.lower()
        sector = self._sector_from_text(lowered)
        company_size = self._company_size(public_text)
        confidence = 0.2
        if len(public_text) >= 200:
            confidence += 0.15
        if sector != "Não identificado":
            confidence += 0.25
        if company_size != "Não identificado publicamente":
            confidence += 0.2
        if lead.company_website:
            confidence += 0.1
        analysis = self._gemini_research(lead, public_text) or self._gemini_analysis(lead, public_text)
        interest_signal = f"Conteúdo público identificado: {public_text[:180] or response.url}."
        role_validation = f"Cargo informado pelo participante: {lead.role or 'não informado'}; não validado publicamente"
        professional_presence = lead.linkedin_url or "Não localizada"
        research_sources = None
        if analysis:
            grounded = bool(analysis.get("_sources"))
            company_match = analysis.get("company_match") is not False
            sector_evidence = str(analysis.get("sector_evidence") or "")[:500]
            analyzed_sector = self._sector_from_evidence(analysis.get("sector"), sector_evidence)
            size_evidence = str(analysis.get("company_size_evidence") or "")[:500]
            analyzed_size = str(analysis.get("company_size") or "Não identificado publicamente")[:80] if size_evidence else "Não identificado publicamente"
            signal_evidence = str(analysis.get("interest_evidence") or "")[:500]
            analyzed_signal = str(analysis.get("interest_signal") or interest_signal)[:300] if signal_evidence else interest_signal
            try:
                analyzed_confidence = max(0, min(float(analysis.get("confidence", confidence)), 0.9))
            except (TypeError, ValueError):
                analyzed_confidence = confidence
            if company_match:
                sector = analyzed_sector if analyzed_sector != "Não identificado" else sector
                company_size = analyzed_size if not analyzed_size.startswith("Não identificado") else company_size
                interest_signal = analyzed_signal
                confidence = analyzed_confidence
            if grounded and company_match:
                role_evidence = str(analysis.get("role_evidence") or "").strip()
                if role_evidence:
                    role_validation = str(analysis.get("role_validation") or role_validation)[:200]
                found_presence = str(analysis.get("professional_presence") or "").strip()
                if found_presence.startswith(("http://", "https://")):
                    professional_presence = found_presence[:300]
                grounded_sources = " | ".join(analysis["_sources"])
                research_sources = f"{research_sources} | {grounded_sources}"[:1000] if research_sources else grounded_sources[:1000]
            if not company_match:
                confidence = min(confidence, 0.35)
        if sector == "Não identificado" and company_size.startswith("Não identificado"):
            confidence = min(confidence, 0.35)
        elif "não validado" in role_validation.lower() and company_size.startswith("Não identificado"):
            confidence = min(confidence, 0.75)
        return EnrichmentData(
            sector=sector,
            company_size=company_size,
            interest_signal=interest_signal,
            source=str(response.url),
            confidence=min(confidence, 0.9),
            role_validation=role_validation,
            professional_presence=professional_presence,
            qualification_score=self._qualification_score(lead, sector, company_size),
            research_sources=research_sources,
        )


def enrich_with_configured_provider(lead: Lead) -> EnrichmentData:
    settings = get_settings()
    if settings.enrichment_provider == "public_web":
        try:
            return PublicWebsiteEnrichmentProvider().enrich(lead)
        except (httpx.HTTPError, ValueError):
            return UnavailableEnrichmentProvider().enrich(lead)
    return FakeEnrichmentProvider().enrich(lead)
