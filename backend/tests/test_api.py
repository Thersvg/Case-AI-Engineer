import os
from datetime import UTC, datetime
from uuid import uuid4

os.environ["LLM_PROVIDER"] = "fake"
os.environ["EMAIL_PROVIDER"] = "fake"
os.environ["ENRICHMENT_PROVIDER"] = "fake"
os.environ["AUTOMATION_ENABLED"] = "false"
os.environ["DEFAULT_MESSAGE_INTERVAL_HOURS"] = "0"
os.environ["AUTH_ENABLED"] = "false"
os.environ["ADMIN_EMAIL"] = "admin@vigilsummit.com"
os.environ["ADMIN_PASSWORD"] = "admin123"
os.environ["AUTH_SECRET"] = "test-secret"
os.environ["ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver"

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.automation import run_automation_cycle
from app.database import get_session
from app.enrichment import PublicWebsiteEnrichmentProvider, validate_public_url
from app.llm import FakeMessageProvider, GeminiMessageProvider
from app.main import app
from app.models import Event, Lead, MessageKind
from app.services import sanitize_email_text

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SQLModel.metadata.create_all(test_engine)


def get_test_session():
    with Session(test_engine) as session:
        yield session


def run_cycle() -> dict[str, int]:
    with Session(test_engine) as session:
        return run_automation_cycle(session)


def participant_token(client: TestClient, lead_id: int) -> str:
    messages = client.get("/api/messages").json()
    message = next(item for item in messages if item["lead_id"] == lead_id)
    return message["body"].split("token=")[-1].splitlines()[0]


app.dependency_overrides[get_session] = get_test_session


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_admin_login() -> None:
    with TestClient(app) as client:
        invalid = client.post("/api/auth/login", json={"email": "admin@vigilsummit.com", "password": "errada"})
        valid = client.post("/api/auth/login", json={"email": "admin@vigilsummit.com", "password": "admin123"})
    assert invalid.status_code == 401
    assert valid.status_code == 200
    assert valid.json()["access_token"]


def test_email_text_is_plain_and_has_real_signature() -> None:
    cleaned = sanitize_email_text("Olá **Marina** — confirme.\n\nAtenciosamente,\n[Seu Nome/Nome da Equipe]", include_signature=True)
    assert "**" not in cleaned and "—" not in cleaned
    assert "[Seu Nome" not in cleaned
    assert "Equipe Vigil Summit" in cleaned


def test_each_message_stage_has_a_distinct_objective() -> None:
    provider = FakeMessageProvider()
    lead = Lead(name="Marina", email="marina@example.com", company="Banco Exemplo", role="CISO")
    event = Event(name="Vigil Summit", starts_at=datetime.now(UTC), location="São Paulo")
    expected = {
        MessageKind.REGISTRATION_CONFIRMATION: "cadastro",
        MessageKind.ATTENDANCE_REQUEST: "confirmação",
        MessageKind.EVENT_REMINDER: "confirmada",
        MessageKind.FINAL_INSTRUCTIONS: "credenciamento",
        MessageKind.POST_EVENT_THANK_YOU: "próximo passo",
        MessageKind.MISSED_EVENT_FOLLOWUP: "não conseguiu participar",
        MessageKind.MEETING_INVITE: "agendar",
    }
    for kind, marker in expected.items():
        content = provider.generate(kind, lead, event, None, None, "")
        assert marker in f"{content.subject} {content.body}".lower()


def test_founder_is_treated_as_a_decision_maker() -> None:
    lead = Lead(name="Rodrigo", email="contato@empresa.com", company="Empresa", role="Founder", company_website="https://empresa.com")
    score = PublicWebsiteEnrichmentProvider._qualification_score(lead, "Tecnologia Financeira", "Não identificado publicamente")
    assert score >= 60


def test_sector_requires_controlled_value_and_matching_evidence() -> None:
    classify = PublicWebsiteEnrichmentProvider._sector_from_evidence
    assert classify("Aerospace and Defense", "Spacecraft, rockets and launch services") == "Aeroespacial e defesa"
    assert classify("Aerospace and Defense", "Plataforma de pagamentos para varejistas") == "Não identificado"
    assert classify("setor inventado", "Descrição sem evidência setorial") == "Não identificado"
    assert PublicWebsiteEnrichmentProvider._sector_from_text("Rockets, spacecraft and satellite launch services") == "Aeroespacial e defesa"


def test_enrichment_rejects_private_network_targets() -> None:
    for target in ("http://127.0.0.1/admin", "http://localhost:8000", "http://169.254.169.254/latest/meta-data"):
        with pytest.raises(ValueError):
            validate_public_url(target)


def test_automation_enriches_lead_and_records_activity() -> None:
    with TestClient(app) as client:
        lead = client.post(
            "/api/leads",
            json={
                "name": "Maria Silva",
                "email": f"maria-{uuid4()}@example.com",
                "company": "Empresa Teste",
                "role": "CISO",
                "consent_email": True,
            },
        ).json()
        cycle = run_cycle()
        assert cycle["enriched"] >= 1
        updated = next(item for item in client.get("/api/leads").json() if item["id"] == lead["id"])
        assert updated["status"] == "enriched"
        activities = client.get("/api/activities").json()
        descriptions = [item["description"] for item in activities if item["lead_id"] == lead["id"]]
        assert "Lead cadastrado no evento." in descriptions
        assert any("Perfil enriquecido" in description for description in descriptions)


def test_cadence_respects_consent_and_avoids_duplicates() -> None:
    with TestClient(app) as client:
        allowed = client.post(
            "/api/leads",
            json={"name": "Lead Permitido", "email": f"allowed-{uuid4()}@example.com", "consent_email": True},
        ).json()
        blocked = client.post(
            "/api/leads",
            json={"name": "Lead Bloqueado", "email": f"blocked-{uuid4()}@example.com", "consent_email": False},
        ).json()
        run_cycle()
        messages = client.get("/api/messages").json()
        assert next(item for item in messages if item["lead_id"] == allowed["id"])["status"] == "sent"
        assert next(item for item in messages if item["lead_id"] == blocked["id"])["status"] == "cancelled"

        run_cycle()
        run_cycle()
        messages = client.get("/api/messages").json()
        allowed_messages = [item for item in messages if item["lead_id"] == allowed["id"]]
        assert len(allowed_messages) == 2


def test_complete_participant_journey() -> None:
    with TestClient(app) as client:
        lead = client.post(
            "/api/leads",
            json={
                "name": "Carlos Demo",
                "email": f"carlos-{uuid4()}@banco-demo.com",
                "company": "Banco Demo",
                "role": "CISO",
                "consent_email": True,
            },
        ).json()
        run_cycle()
        token = participant_token(client, lead["id"])

        context = client.get(f"/api/public/participant/{token}")
        assert context.status_code == 200
        opened = client.post(f"/api/public/participant/{token}/opened")
        assert opened.status_code == 204

        response = client.post(
            f"/api/public/participant/{token}/response",
            json={"kind": "interested", "note": "Interesse em vulnerabilidades"},
        )
        assert response.status_code == 200

        attendance = client.post(
            f"/api/leads/{lead['id']}/attendance",
            json={"status": "attended", "interest_topic": "gestão de vulnerabilidades"},
        )
        assert attendance.status_code == 200
        run_cycle()
        followups = [item for item in client.get("/api/messages").json() if item["lead_id"] == lead["id"] and item["kind"] == "post_event_thank_you"]
        assert followups and "Interesse em vulnerabilidades" in followups[0]["body"]

        context = client.get(f"/api/public/participant/{token}").json()
        assert context["can_schedule"] is True
        meeting = client.post(
            f"/api/public/participant/{token}/meeting",
            json={"starts_at": context["meeting_slots"][0]},
        )
        assert meeting.status_code == 200
        assert meeting.json()["status"] == "booked"
        event_settings = client.get(f"/api/events/{meeting.json()['event_id']}/settings").json()
        assert context["meeting_slots"][0] not in [slot["starts_at"] for slot in event_settings["meeting_slots"]]
        assert any(item["lead_id"] == lead["id"] for item in client.get("/api/meetings").json())
        journey_metrics = client.get("/api/metrics").json()
        assert journey_metrics["meetings_booked"] >= 1
        assert journey_metrics["attended"] >= 1
        details = client.put(f"/api/meetings/{meeting.json()['id']}", json={"meeting_url": "https://meet.google.com/demo-vigil", "admin_note": "Reunião de 30 minutos"})
        assert details.status_code == 200
        notified = client.post(f"/api/meetings/{meeting.json()['id']}/notify")
        assert notified.status_code == 200
        meeting_context = client.get(f"/api/public/participant/{token}").json()
        assert meeting_context["meeting_url"] == "https://meet.google.com/demo-vigil"
        run_cycle()
        journey_messages = [item for item in client.get("/api/messages").json() if item["lead_id"] == lead["id"]]
        assert any(item["kind"] == "meeting_confirmation" for item in journey_messages)
        assert not any(item["kind"] == "meeting_invite" for item in journey_messages)
        assert client.delete(f"/api/meetings/{meeting.json()['id']}").status_code == 204
        restored = client.get(f"/api/events/{meeting.json()['event_id']}/settings").json()
        restored_times = [datetime.fromisoformat(slot["starts_at"].replace("Z", "+00:00")) for slot in restored["meeting_slots"]]
        selected_time = datetime.fromisoformat(context["meeting_slots"][0].replace("Z", "+00:00"))
        assert any(item.replace(tzinfo=UTC) == selected_time for item in restored_times)


def test_public_event_registration_form() -> None:
    with TestClient(app) as client:
        event = client.get("/api/events").json()[0]
        assert client.get(f"/api/public/events/{event['id']}").status_code == 200
        response = client.post(
            f"/api/public/events/{event['id']}/register",
            json={"name": "Inscrição Pública", "email": f"public-{uuid4()}@example.com", "company": "Empresa", "role": "CISO", "consent_email": True},
        )
        assert response.status_code == 201


def test_admin_can_edit_all_participant_profile_fields() -> None:
    with TestClient(app) as client:
        lead = client.post("/api/leads", json={"name": "Perfil Antigo", "email": f"old-{uuid4()}@example.com", "company": "Empresa A", "role": "Analista", "consent_email": True}).json()
        updated = client.put(f"/api/leads/{lead['id']}", json={"name": "Perfil Atualizado", "email": f"new-{uuid4()}@example.com", "company": "Empresa B", "role": "CISO", "company_website": "https://example.com", "linkedin_url": "https://linkedin.com/in/exemplo"})
        assert updated.status_code == 200
        assert updated.json()["name"] == "Perfil Atualizado"
        assert updated.json()["role"] == "CISO"


def test_public_opt_out_and_admin_delete() -> None:
    with TestClient(app) as client:
        lead = client.post(
            "/api/leads",
            json={"name": "Titular LGPD", "email": f"privacy-{uuid4()}@example.com", "consent_email": True},
        ).json()
        run_cycle()
        token = participant_token(client, lead["id"])
        opted_out = client.post(f"/api/public/participant/{token}/opt-out")
        assert opted_out.status_code == 200
        assert opted_out.json()["granted"] is False

        assert client.delete(f"/api/leads/{lead['id']}").status_code == 204
        assert all(item["id"] != lead["id"] for item in client.get("/api/leads").json())


def test_gemini_provider_parses_structured_response(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"subject":"Convite","body":"Mensagem personalizada"}'}]}}]}

    monkeypatch.setattr("app.llm.httpx.post", lambda *args, **kwargs: FakeResponse())
    content = GeminiMessageProvider("test-key", "gemini-3.5-flash").generate(
        MessageKind.REGISTRATION_CONFIRMATION,
        Lead(name="Ana", email="ana@example.com", company="Empresa", role="CISO"),
        Event(name="Vigil Summit", starts_at=datetime.now(UTC), location="São Paulo"),
        None,
        None,
        "",
    )
    assert content.provider == "gemini"
    assert content.subject == "Convite"
    assert content.body == "Mensagem personalizada"


def test_gemini_provider_falls_back_after_service_unavailable(monkeypatch) -> None:
    attempts = 0

    def unavailable(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, request=httpx.Request("POST", "https://example.com"))

    monkeypatch.setattr("app.llm.httpx.post", unavailable)
    monkeypatch.setattr("app.llm.time.sleep", lambda _: None)
    content = GeminiMessageProvider("test-key", "gemini-2.5-flash").generate(
        MessageKind.REGISTRATION_CONFIRMATION,
        Lead(name="Ana", email="ana@example.com", company="Empresa", role="CISO"),
        Event(name="Vigil Summit", starts_at=datetime.now(UTC), location="São Paulo"),
        None,
        None,
        "",
    )
    assert attempts == 3
    assert content.provider == "fake-fallback"
    assert content.body


def test_event_settings_control_message_interval_and_meeting_slots() -> None:
    with TestClient(app) as client:
        event = client.get("/api/events").json()[0]
        original = client.get(f"/api/events/{event['id']}/settings").json()
        custom_slots = [
            datetime(2027, 1, 10, 14, 0, tzinfo=UTC).isoformat(),
            datetime(2027, 1, 11, 15, 30, tzinfo=UTC).isoformat(),
        ]
        updated = client.put(
            f"/api/events/{event['id']}/settings",
            json={
                "name": original["name"],
                "starts_at": original["starts_at"],
                "location": original["location"],
                "message_interval_hours": 24,
                "meeting_slots": custom_slots,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["message_interval_hours"] == 24
        assert len(updated.json()["meeting_slots"]) == 2

        lead = client.post(
            "/api/leads",
            json={"name": "Cadência Teste", "email": f"cadence-{uuid4()}@example.com", "consent_email": True},
        ).json()
        run_cycle()
        run_cycle()
        messages = [item for item in client.get("/api/messages").json() if item["lead_id"] == lead["id"]]
        assert len(messages) == 1

        client.put(
            f"/api/events/{event['id']}/settings",
            json={
                "name": original["name"],
                "starts_at": original["starts_at"],
                "location": original["location"],
                "message_interval_hours": 0,
                "meeting_slots": [slot["starts_at"] for slot in original["meeting_slots"]],
            },
        )


def test_admin_can_delete_event_and_its_participants() -> None:
    with TestClient(app) as client:
        event = client.post(
            "/api/events",
            json={"name": "Evento descartável", "starts_at": datetime(2027, 2, 1, tzinfo=UTC).isoformat(), "location": "São Paulo"},
        ).json()
        lead = client.post(
            "/api/leads",
            json={"name": "Participante descartável", "email": f"delete-{uuid4()}@example.com", "event_id": event["id"], "consent_email": True},
        ).json()
        assert client.delete(f"/api/events/{event['id']}").status_code == 204
        assert all(item["id"] != event["id"] for item in client.get("/api/events").json())
        assert all(item["id"] != lead["id"] for item in client.get("/api/leads").json())
