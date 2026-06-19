from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import get_settings


@dataclass
class EmailResult:
    success: bool
    provider: str
    external_id: str | None = None
    detail: str | None = None


class EmailProvider(Protocol):
    def send(self, recipient: str, subject: str, body: str) -> EmailResult: ...


class FakeEmailProvider:
    def send(self, recipient: str, subject: str, body: str) -> EmailResult:
        return EmailResult(success=True, provider="fake", external_id=f"fake:{recipient}:{abs(hash(subject))}")


class ResendEmailProvider:
    def __init__(self, api_key: str, sender: str):
        self.api_key = api_key
        self.sender = sender

    def send(self, recipient: str, subject: str, body: str) -> EmailResult:
        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"from": self.sender, "to": [recipient], "subject": subject, "text": body},
                timeout=30,
            )
            response.raise_for_status()
            return EmailResult(success=True, provider="resend", external_id=response.json().get("id"))
        except httpx.HTTPError as exc:
            detail = "Falha ao enviar o e-mail pelo Resend."
            if isinstance(exc, httpx.HTTPStatusError):
                try:
                    provider_detail = exc.response.json().get("message", "")
                except (ValueError, AttributeError):
                    provider_detail = ""
                if exc.response.status_code == 403:
                    detail = "Resend recusou o envio. Verifique se EMAIL_FROM usa um domínio validado no Resend e se a chave possui permissão de envio."
                elif exc.response.status_code == 401:
                    detail = "A chave RESEND_API_KEY é inválida ou expirou."
                if provider_detail:
                    detail = f"{detail} Detalhe: {provider_detail}"
            return EmailResult(success=False, provider="resend", detail=detail[:500])


def get_email_provider() -> EmailProvider:
    settings = get_settings()
    if settings.email_provider == "resend" and settings.resend_api_key:
        return ResendEmailProvider(settings.resend_api_key, settings.email_from)
    return FakeEmailProvider()
