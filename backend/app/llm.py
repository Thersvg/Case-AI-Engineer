import json
import logging
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import get_settings
from app.models import Attendance, Event, Lead, LeadEnrichment, MessageKind

logger = logging.getLogger(__name__)

STAGE_INSTRUCTIONS = {
    MessageKind.REGISTRATION_CONFIRMATION: "Confirme que o cadastro foi recebido. Explique que o próximo passo será confirmar presença. Não diga que a presença já está confirmada.",
    MessageKind.ATTENDANCE_REQUEST: "Peça uma decisão objetiva de presença e destaque data/local do evento. O CTA é confirmar ou recusar presença.",
    MessageKind.EVENT_REMINDER: "A presença já está confirmada. Reforce proximidade, relevância do conteúdo e preparação para o evento.",
    MessageKind.FINAL_INSTRUCTIONS: "Envie instruções finais práticas: data, local e credenciamento. Não peça nova confirmação.",
    MessageKind.POST_EVENT_THANK_YOU: "Agradeça a participação e conecte explicitamente o interesse registrado ao próximo passo comercial.",
    MessageKind.MISSED_EVENT_FOLLOWUP: "Reconheça a ausência sem constranger, ofereça os aprendizados e proponha conversa comercial contextualizada.",
    MessageKind.MEETING_INVITE: "Convide o participante a escolher um horário disponível. Deixe claro que ainda não existe reunião agendada.",
    MessageKind.MEETING_CONFIRMATION: "Confirme data, horário e acesso da reunião já agendada.",
}


@dataclass
class MessageContent:
    subject: str
    body: str
    provider: str
    model: str
    prompt_version: str = "v1"


class MessageProvider(Protocol):
    def generate(
        self,
        kind: MessageKind,
        lead: Lead,
        event: Event,
        enrichment: LeadEnrichment | None,
        attendance: Attendance | None,
        behavior_context: str,
    ) -> MessageContent: ...


class FakeMessageProvider:
    def generate(
        self,
        kind: MessageKind,
        lead: Lead,
        event: Event,
        enrichment: LeadEnrichment | None,
        attendance: Attendance | None,
        behavior_context: str,
    ) -> MessageContent:
        context = f" do setor {enrichment.sector}" if enrichment else ""
        topic = f" sobre {attendance.interest_topic}" if attendance and attendance.interest_topic else ""
        personalized_context = f" Contexto considerado: {behavior_context}." if behavior_context else ""
        templates = {
            MessageKind.REGISTRATION_CONFIRMATION: MessageContent(
                "Cadastro recebido no Vigil Summit",
                f"Olá, {lead.name}. Seu cadastro para o {event.name} foi recebido com sucesso. O conteúdo foi selecionado para decisores{context}. Próximo passo: confirme sua presença pelo link abaixo.",
                "fake",
                "deterministic-template",
            ),
            MessageKind.ATTENDANCE_REQUEST: MessageContent(
                "Confirme sua presença no Vigil Summit",
                f"Olá, {lead.name}. Sua inscrição está registrada, mas ainda precisamos da sua confirmação de presença no {event.name}, em {event.location}. {behavior_context}".strip(),
                "fake",
                "deterministic-template",
            ),
            MessageKind.EVENT_REMINDER: MessageContent(
                "Sua presença está confirmada no Vigil Summit",
                f"Olá, {lead.name}. Sua presença no {event.name} está confirmada. O encontro será em {event.location}. Estamos preparando conteúdos sobre segurança e IA relevantes para o seu contexto.",
                "fake",
                "deterministic-template",
            ),
            MessageKind.FINAL_INSTRUCTIONS: MessageContent(
                "Informações para o dia do Vigil Summit",
                f"Olá, {lead.name}. Está tudo pronto para receber você no {event.name}. Local: {event.location}. Leve um documento para o credenciamento e chegue com antecedência.",
                "fake",
                "deterministic-template",
            ),
            MessageKind.POST_EVENT_THANK_YOU: MessageContent(
                "Obrigado pela participação: próximo passo",
                f"Olá, {lead.name}. Obrigado por participar do Vigil Summit{topic}. O próximo passo é escolher um horário para aprofundarmos esse tema com o time da Vigil.AI.{personalized_context}",
                "fake",
                "deterministic-template",
            ),
            MessageKind.MISSED_EVENT_FOLLOWUP: MessageContent(
                "Principais aprendizados do Vigil Summit",
                f"Olá, {lead.name}. Notamos que você não conseguiu participar do Vigil Summit. Podemos compartilhar os principais aprendizados e apresentar uma demonstração relacionada ao seu contexto.{personalized_context}",
                "fake",
                "deterministic-template",
            ),
            MessageKind.MEETING_INVITE: MessageContent(
                "Escolha um horário com o time Vigil.AI",
                f"Olá, {lead.name}. A etapa seguinte é agendar uma conversa com nosso time. Há horários disponíveis para avaliarmos como a Vigil.AI pode apoiar {lead.company or 'sua empresa'}.{personalized_context}",
                "fake",
                "deterministic-template",
            ),
        }
        return templates[kind]


class GeminiMessageProvider:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def generate(
        self,
        kind: MessageKind,
        lead: Lead,
        event: Event,
        enrichment: LeadEnrichment | None,
        attendance: Attendance | None,
        behavior_context: str,
    ) -> MessageContent:
        prompt = {
            "task": "Escreva um e-mail B2B curto em português. Use somente os contextos fornecidos, destaque interesse declarado quando existir e não invente fatos. Use texto simples, sem Markdown, asteriscos, travessão ou placeholders. Não crie assinatura; o sistema adicionará Equipe Vigil Summit. Retorne apenas JSON com subject e body.",
            "message_kind": kind.value,
            "stage_objective": STAGE_INSTRUCTIONS[kind],
            "lead": {"name": lead.name, "company": lead.company, "role": lead.role},
            "event": {"name": event.name, "location": event.location},
            "enrichment": enrichment.model_dump() if enrichment else None,
            "attendance": attendance.model_dump() if attendance else None,
            "behavior_context": behavior_context,
        }
        for attempt in range(3):
            try:
                response = httpx.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                    headers={"x-goog-api-key": self.api_key, "content-type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": json.dumps(prompt, default=str)}]}],
                        "generationConfig": {"responseMimeType": "application/json"},
                    },
                    timeout=30,
                )
                response.raise_for_status()
                text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                data = json.loads(text)
                return MessageContent(
                    subject=data["subject"][:200],
                    body=data["body"][:2000],
                    provider="gemini",
                    model=self.model,
                )
            except (httpx.HTTPError, KeyError, json.JSONDecodeError) as exc:
                retryable = not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code in {429, 500, 502, 503, 504}
                if retryable and attempt < 2:
                    time.sleep(attempt + 1)
                    continue
                logger.warning("Gemini unavailable; using deterministic fallback: %s", exc)
                fallback = FakeMessageProvider().generate(
                    kind,
                    lead,
                    event,
                    enrichment,
                    attendance,
                    behavior_context,
                )
                fallback.provider = "fake-fallback"
                fallback.model = self.model
                return fallback


def get_message_provider() -> MessageProvider:
    settings = get_settings()
    if settings.llm_provider == "gemini" and settings.gemini_api_key:
        return GeminiMessageProvider(settings.gemini_api_key, settings.llm_model)
    return FakeMessageProvider()
