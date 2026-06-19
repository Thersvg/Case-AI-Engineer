"""Executa uma jornada sintética completa sem consumir APIs externas."""

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
demo_db = Path(__file__).resolve().parents[1] / "vigil_demo.db"
if demo_db.exists():
    demo_db.unlink()

os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{demo_db.as_posix()}",
        "LLM_PROVIDER": "fake",
        "EMAIL_PROVIDER": "fake",
        "ENRICHMENT_PROVIDER": "fake",
        "AUTOMATION_ENABLED": "false",
        "DEMO_MODE": "true",
        "DEFAULT_MESSAGE_INTERVAL_HOURS": "0",
        "AUTH_ENABLED": "false",
    }
)

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.automation import run_automation_cycle
from app.database import engine
from app.main import app


def cycle() -> dict[str, int]:
    with Session(engine) as session:
        return run_automation_cycle(session)


with TestClient(app) as client:
    email = f"demo-{uuid4().hex[:8]}@banco-exemplo.com"
    lead = client.post(
        "/api/leads",
        json={
            "name": "Marina Costa",
            "email": email,
            "company": "Banco Exemplo",
            "role": "CISO",
            "company_website": "https://example.com",
            "linkedin_url": "https://www.linkedin.com/in/marina-exemplo",
            "consent_email": True,
        },
    ).json()
    cycle()
    first_message = next(item for item in client.get("/api/messages").json() if item["lead_id"] == lead["id"])
    token = first_message["body"].split("token=")[-1].splitlines()[0]
    client.post(
        f"/api/public/participant/{token}/response",
        json={"kind": "interested", "note": "Priorização de vulnerabilidades e conformidade LGPD"},
    )
    client.post(
        f"/api/leads/{lead['id']}/attendance",
        json={"status": "attended", "interest_topic": "priorização de vulnerabilidades"},
    )
    cycle()
    context = client.get(f"/api/public/participant/{token}").json()
    meeting = client.post(
        f"/api/public/participant/{token}/meeting",
        json={"starts_at": context["meeting_slots"][0]},
    ).json()
    client.put(
        f"/api/meetings/{meeting['id']}",
        json={"meeting_url": "https://meet.google.com/vigil-demo", "admin_note": "Conversa de 30 minutos com o especialista."},
    )
    meeting = client.post(f"/api/meetings/{meeting['id']}/notify").json()
    messages = [item for item in client.get("/api/messages").json() if item["lead_id"] == lead["id"]]
    result = {
        "lead": {"id": lead["id"], "name": lead["name"], "email": lead["email"]},
        "messages": [{"kind": item["kind"], "status": item["status"], "body": item["body"]} for item in messages],
        "meeting": meeting,
        "metrics": client.get("/api/metrics").json(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
