import asyncio
import hmac
from contextlib import suppress
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlmodel import Session, select

from app.config import get_settings
from app.auth import create_access_token, valid_access_token
from app.automation import automation_loop
from app.database import create_db_and_tables, engine, get_session
from app.security import rate_limiter
from app.models import (
    Activity,
    ActivityRead,
    Attendance,
    AttendanceCreate,
    AttendanceRead,
    ConsentRead,
    DashboardMetrics,
    Event,
    EventCreate,
    EventRead,
    EventSettingsRead,
    EventSettingsUpdate,
    EnrichmentSourceUpdate,
    GenerationTrace,
    GenerationTraceRead,
    Lead,
    LeadCreate,
    LeadEnrichment,
    LeadEnrichmentRead,
    LeadRead,
    LeadUpdate,
    LoginRequest,
    LoginResponse,
    Meeting,
    MeetingCreate,
    MeetingRead,
    MeetingUpdate,
    Message,
    MessageDeliveryEvent,
    MessageDeliveryRead,
    MessageRead,
    ParticipantResponse,
    ParticipantContext,
    ParticipantResponseCreate,
    ParticipantResponseRead,
)
from app.services import (
    book_meeting_by_token,
    create_lead,
    update_lead,
    get_metrics,
    get_or_create_default_event,
    get_event_settings,
    get_participant_context,
    opt_out_by_token,
    record_attendance,
    record_participant_open,
    record_response_by_token,
    retry_failed_message,
    refresh_lead_enrichment,
    delete_lead_data,
    delete_event_data,
    delete_meeting,
    update_meeting,
    notify_meeting_participant,
    purge_expired_leads,
    update_event_settings,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auth_enabled and (len(settings.admin_password) < 10 or len(settings.auth_secret) < 32):
        raise RuntimeError("AUTH_ENABLED exige ADMIN_PASSWORD com 10+ caracteres e AUTH_SECRET com 32+ caracteres.")
    create_db_and_tables()
    with Session(engine) as session:
        get_or_create_default_event(session)
    automation_task = None
    if settings.automation_enabled:
        automation_task = asyncio.create_task(automation_loop(settings.automation_interval_seconds))
    yield
    if automation_task:
        automation_task.cancel()
        with suppress(asyncio.CancelledError):
            await automation_task


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.demo_mode else None,
    openapi_url="/openapi.json" if settings.demo_mode else None,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[host.strip() for host in settings.allowed_hosts.split(",") if host.strip()])
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_controls(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path
    if request.method == "POST" and path == "/api/auth/login":
        allowed = rate_limiter.allow(f"login:{client_ip}", 5, 60)
    elif request.method == "POST" and path.startswith("/api/public/events/") and path.endswith("/register"):
        allowed = rate_limiter.allow(f"register:{client_ip}", 20, 3600)
    elif request.method == "POST" and path.startswith("/api/public/participant/"):
        allowed = rate_limiter.allow(f"participant:{client_ip}", 60, 60)
    else:
        allowed = True
    if not allowed:
        return JSONResponse(status_code=429, content={"detail": "Muitas tentativas. Aguarde e tente novamente."}, headers={"Retry-After": "60"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store" if path.startswith("/api/") else "no-cache"
    return response


@app.middleware("http")
async def admin_authentication(request: Request, call_next):
    path = request.url.path
    exact_public_paths = {"/health", "/docs", "/openapi.json", "/api/auth/login"}
    public = path in exact_public_paths or path.startswith("/docs/") or path.startswith("/api/public/")
    if (
        not settings.auth_enabled
        or request.method == "OPTIONS"
        or public
    ):
        return await call_next(request)
    authorization = request.headers.get("Authorization", "")
    token = authorization.removeprefix("Bearer ").strip()
    if not token or not valid_access_token(token):
        return JSONResponse(
            status_code=401,
            content={"detail": "Sessão inválida ou expirada"},
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
            },
        )
    return await call_next(request)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/login", response_model=LoginResponse)
def login_route(payload: LoginRequest) -> LoginResponse:
    email_matches = hmac.compare_digest(payload.email.lower(), settings.admin_email.lower())
    password_matches = hmac.compare_digest(payload.password, settings.admin_password)
    if not email_matches or not password_matches:
        return JSONResponse(status_code=401, content={"detail": "E-mail ou senha inválidos"})
    return LoginResponse(access_token=create_access_token(settings.admin_email))


@app.get("/api/leads", response_model=list[LeadRead])
def list_leads(session: Session = Depends(get_session)) -> list[Lead]:
    return list(session.exec(select(Lead).order_by(Lead.created_at.desc())).all())


@app.post("/api/leads", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
def create_lead_route(payload: LeadCreate, session: Session = Depends(get_session)) -> Lead:
    return create_lead(session, payload)


@app.put("/api/leads/{lead_id}", response_model=LeadRead)
def update_lead_route(lead_id: int, payload: LeadUpdate, session: Session = Depends(get_session)) -> Lead:
    return update_lead(session, lead_id, payload)


@app.get("/api/public/events/{event_id}", response_model=EventRead)
def public_event_route(event_id: int, session: Session = Depends(get_session)) -> Event:
    event = session.get(Event, event_id)
    if not event or not event.active:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return event


@app.post("/api/public/events/{event_id}/register", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
def public_register_route(event_id: int, payload: LeadCreate, session: Session = Depends(get_session)) -> Lead:
    event = session.get(Event, event_id)
    if not event or not event.active:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return create_lead(session, payload.model_copy(update={"event_id": event_id}))


@app.get("/api/events", response_model=list[EventRead])
def list_events(session: Session = Depends(get_session)) -> list[Event]:
    return list(session.exec(select(Event).order_by(Event.starts_at)).all())


@app.post("/api/events", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def create_event_route(payload: EventCreate, session: Session = Depends(get_session)) -> Event:
    event = Event.model_validate(payload)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@app.delete("/api/events/{event_id}", status_code=204)
def delete_event_route(event_id: int, session: Session = Depends(get_session)) -> None:
    delete_event_data(session, event_id)
    get_or_create_default_event(session)


@app.get("/api/events/{event_id}/settings", response_model=EventSettingsRead)
def event_settings_route(event_id: int, session: Session = Depends(get_session)) -> EventSettingsRead:
    return get_event_settings(session, event_id)


@app.put("/api/events/{event_id}/settings", response_model=EventSettingsRead)
def update_event_settings_route(
    event_id: int,
    payload: EventSettingsUpdate,
    session: Session = Depends(get_session),
) -> EventSettingsRead:
    return update_event_settings(session, event_id, payload)


@app.get("/api/activities", response_model=list[ActivityRead])
def list_activities(session: Session = Depends(get_session)) -> list[Activity]:
    statement = select(Activity).order_by(Activity.created_at.desc()).limit(30)
    return list(session.exec(statement).all())


@app.get("/api/messages", response_model=list[MessageRead])
def list_messages(session: Session = Depends(get_session)) -> list[Message]:
    statement = select(Message).order_by(Message.created_at.desc()).limit(50)
    return list(session.exec(statement).all())


@app.post("/api/messages/{message_id}/retry", response_model=MessageRead)
def retry_message_route(message_id: int, session: Session = Depends(get_session)) -> Message:
    return retry_failed_message(session, message_id)


@app.get("/api/enrichments", response_model=list[LeadEnrichmentRead])
def list_enrichments(session: Session = Depends(get_session)) -> list[LeadEnrichment]:
    return list(session.exec(select(LeadEnrichment).order_by(LeadEnrichment.enriched_at.desc())).all())


@app.post("/api/leads/{lead_id}/enrichment", response_model=LeadEnrichmentRead)
def refresh_enrichment_route(
    lead_id: int,
    payload: EnrichmentSourceUpdate,
    session: Session = Depends(get_session),
) -> LeadEnrichment:
    return refresh_lead_enrichment(session, lead_id, payload)


@app.get("/api/responses", response_model=list[ParticipantResponseRead])
def list_responses(session: Session = Depends(get_session)) -> list[ParticipantResponse]:
    return list(session.exec(select(ParticipantResponse).order_by(ParticipantResponse.created_at.desc())).all())


@app.get("/api/attendance", response_model=list[AttendanceRead])
def list_attendance(session: Session = Depends(get_session)) -> list[Attendance]:
    return list(session.exec(select(Attendance).order_by(Attendance.recorded_at.desc())).all())


@app.post("/api/leads/{lead_id}/attendance", response_model=AttendanceRead)
def record_attendance_route(
    lead_id: int,
    payload: AttendanceCreate,
    session: Session = Depends(get_session),
) -> Attendance:
    return record_attendance(session, lead_id, payload)


@app.get("/api/meetings", response_model=list[MeetingRead])
def list_meetings(session: Session = Depends(get_session)) -> list[Meeting]:
    return list(session.exec(select(Meeting).order_by(Meeting.starts_at)).all())


@app.delete("/api/meetings/{meeting_id}", status_code=204)
def delete_meeting_route(meeting_id: int, session: Session = Depends(get_session)) -> None:
    delete_meeting(session, meeting_id)


@app.put("/api/meetings/{meeting_id}", response_model=MeetingRead)
def update_meeting_route(meeting_id: int, payload: MeetingUpdate, session: Session = Depends(get_session)) -> Meeting:
    return update_meeting(session, meeting_id, payload)


@app.post("/api/meetings/{meeting_id}/notify", response_model=MeetingRead)
def notify_meeting_route(meeting_id: int, session: Session = Depends(get_session)) -> Meeting:
    return notify_meeting_participant(session, meeting_id)


@app.get("/api/metrics", response_model=DashboardMetrics)
def metrics_route(session: Session = Depends(get_session)) -> DashboardMetrics:
    return get_metrics(session)


@app.get("/api/message-events", response_model=list[MessageDeliveryRead])
def list_message_events(session: Session = Depends(get_session)) -> list[MessageDeliveryEvent]:
    return list(
        session.exec(select(MessageDeliveryEvent).order_by(MessageDeliveryEvent.created_at.desc()).limit(100)).all()
    )


@app.get("/api/generation-traces", response_model=list[GenerationTraceRead])
def list_generation_traces(session: Session = Depends(get_session)) -> list[GenerationTrace]:
    return list(session.exec(select(GenerationTrace).order_by(GenerationTrace.created_at.desc()).limit(100)).all())


@app.delete("/api/leads/{lead_id}", status_code=204)
def delete_lead_route(lead_id: int, session: Session = Depends(get_session)) -> None:
    delete_lead_data(session, lead_id)


@app.post("/api/privacy/purge")
def purge_route(session: Session = Depends(get_session)) -> dict[str, int]:
    return {"purged_leads": purge_expired_leads(session, settings.data_retention_days)}


@app.get("/api/public/participant/{token}", response_model=ParticipantContext)
def participant_context_route(token: str, session: Session = Depends(get_session)) -> ParticipantContext:
    return get_participant_context(session, token)


@app.post("/api/public/participant/{token}/opened", status_code=204)
def participant_opened_route(token: str, session: Session = Depends(get_session)) -> None:
    record_participant_open(session, token)


@app.post("/api/public/participant/{token}/response", response_model=ParticipantResponseRead)
def participant_response_route(
    token: str,
    payload: ParticipantResponseCreate,
    session: Session = Depends(get_session),
) -> ParticipantResponse:
    return record_response_by_token(session, token, payload)


@app.post("/api/public/participant/{token}/meeting", response_model=MeetingRead)
def participant_meeting_route(
    token: str,
    payload: MeetingCreate,
    session: Session = Depends(get_session),
) -> Meeting:
    return book_meeting_by_token(session, token, payload)


@app.post("/api/public/participant/{token}/opt-out", response_model=ConsentRead)
def participant_opt_out_route(token: str, session: Session = Depends(get_session)):
    return opt_out_by_token(session, token)
