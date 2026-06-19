import secrets
import re
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func
from sqlmodel import Session, delete, select

from app.config import get_settings
from app.email import get_email_provider
from app.enrichment import enrich_with_configured_provider
from app.llm import get_message_provider
from app.models import (
    Activity,
    ActivityType,
    Attendance,
    AttendanceCreate,
    AttendanceStatus,
    Consent,
    ConsentChannel,
    DashboardMetrics,
    DeliveryEventType,
    Event,
    EventRegistration,
    EventSchedule,
    EventSettingsRead,
    EventSettingsUpdate,
    EnrichmentSourceUpdate,
    GenerationTrace,
    Lead,
    LeadCreate,
    LeadEnrichment,
    LeadStatus,
    LeadUpdate,
    Meeting,
    MeetingCreate,
    MeetingSlot,
    MeetingSlotRead,
    MeetingUpdate,
    Message,
    MessageDeliveryEvent,
    MessageKind,
    MessageStatus,
    ParticipantResponse,
    ParticipantResponseCreate,
    ParticipantContext,
    ParticipantToken,
    ResponseKind,
)

CADENCE_BY_STATUS = {
    LeadStatus.REGISTERED: [MessageKind.REGISTRATION_CONFIRMATION, MessageKind.ATTENDANCE_REQUEST],
    LeadStatus.ENRICHED: [MessageKind.REGISTRATION_CONFIRMATION, MessageKind.ATTENDANCE_REQUEST],
    LeadStatus.ENRICHMENT_UNAVAILABLE: [MessageKind.REGISTRATION_CONFIRMATION, MessageKind.ATTENDANCE_REQUEST],
    LeadStatus.CONFIRMED: [MessageKind.EVENT_REMINDER, MessageKind.FINAL_INSTRUCTIONS],
}


def cadence_sequence(lead: Lead, event: Event) -> list[MessageKind]:
    settings = get_settings()
    base_sequence = CADENCE_BY_STATUS.get(lead.status, [])
    if settings.demo_mode:
        return base_sequence
    days_until_event = (event.starts_at - datetime.now(UTC)).total_seconds() / 86400
    if lead.status in (LeadStatus.REGISTERED, LeadStatus.ENRICHED, LeadStatus.ENRICHMENT_UNAVAILABLE):
        sequence = [MessageKind.REGISTRATION_CONFIRMATION]
        if days_until_event <= 14:
            sequence.append(MessageKind.ATTENDANCE_REQUEST)
        return sequence
    if lead.status == LeadStatus.CONFIRMED:
        sequence = []
        if days_until_event <= 3:
            sequence.append(MessageKind.EVENT_REMINDER)
        if days_until_event <= 1:
            sequence.append(MessageKind.FINAL_INSTRUCTIONS)
        return sequence
    return []


def get_or_create_default_event(session: Session) -> Event:
    event = session.exec(select(Event).where(Event.active == True)).first()  # noqa: E712
    if event:
        ensure_event_configuration(session, event)
        return event
    event = Event(
        name="Vigil Summit — Segurança para a Era da IA",
        starts_at=datetime.now(UTC) + timedelta(days=30),
        location="São Paulo, SP",
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    ensure_event_configuration(session, event)
    return event


def ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def ensure_event_configuration(session: Session, event: Event) -> EventSchedule:
    schedule = session.exec(select(EventSchedule).where(EventSchedule.event_id == event.id)).first()
    if not schedule:
        schedule = EventSchedule(
            event_id=event.id,
            message_interval_hours=get_settings().default_message_interval_hours,
        )
        session.add(schedule)
    slots = session.exec(select(MeetingSlot).where(MeetingSlot.event_id == event.id)).all()
    if not slots:
        sao_paulo = ZoneInfo("America/Sao_Paulo")
        event_date = ensure_aware(event.starts_at).astimezone(sao_paulo)
        for day in (1, 2, 3):
            slot_date = (event_date + timedelta(days=day)).date()
            session.add(
                MeetingSlot(
                    event_id=event.id,
                    starts_at=datetime.combine(slot_date, time(14, 0), tzinfo=sao_paulo).astimezone(UTC),
                )
            )
    session.commit()
    session.refresh(schedule)
    return schedule


def get_event_settings(session: Session, event_id: int) -> EventSettingsRead:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    schedule = ensure_event_configuration(session, event)
    slots = session.exec(
        select(MeetingSlot).where(
            MeetingSlot.event_id == event.id,
            MeetingSlot.active == True,  # noqa: E712
        ).order_by(MeetingSlot.starts_at)
    ).all()
    return EventSettingsRead(
        id=event.id,
        name=event.name,
        starts_at=event.starts_at,
        location=event.location,
        active=event.active,
        message_interval_hours=schedule.message_interval_hours,
        meeting_slots=[MeetingSlotRead.model_validate(slot) for slot in slots],
    )


def update_event_settings(
    session: Session,
    event_id: int,
    payload: EventSettingsUpdate,
) -> EventSettingsRead:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.name = payload.name
    event.starts_at = ensure_aware(payload.starts_at)
    event.location = payload.location
    schedule = ensure_event_configuration(session, event)
    schedule.message_interval_hours = payload.message_interval_hours
    session.add(event)
    session.add(schedule)
    session.exec(delete(MeetingSlot).where(MeetingSlot.event_id == event.id))
    seen_slots: set[datetime] = set()
    for starts_at in payload.meeting_slots:
        normalized = ensure_aware(starts_at)
        if normalized in seen_slots:
            continue
        seen_slots.add(normalized)
        session.add(MeetingSlot(event_id=event.id, starts_at=normalized))
    session.commit()
    return get_event_settings(session, event.id)


def get_event_for_lead(session: Session, lead: Lead) -> Event:
    registration = session.exec(
        select(EventRegistration).where(EventRegistration.lead_id == lead.id)
    ).first()
    if registration:
        event = session.get(Event, registration.event_id)
        if event:
            return event
    event = get_or_create_default_event(session)
    session.add(EventRegistration(event_id=event.id, lead_id=lead.id))
    session.flush()
    return event


def get_or_create_participant_token(session: Session, lead: Lead, event: Event) -> ParticipantToken:
    participant_token = session.exec(
        select(ParticipantToken).where(
            ParticipantToken.lead_id == lead.id,
            ParticipantToken.event_id == event.id,
        )
    ).first()
    if participant_token:
        return participant_token
    participant_token = ParticipantToken(
        lead_id=lead.id,
        event_id=event.id,
        token=secrets.token_urlsafe(24),
    )
    session.add(participant_token)
    session.flush()
    return participant_token


def create_lead(session: Session, payload: LeadCreate) -> Lead:
    if session.exec(select(Lead).where(Lead.email == payload.email)).first():
        raise HTTPException(status_code=409, detail="Lead already registered")
    event = session.get(Event, payload.event_id) if payload.event_id else get_or_create_default_event(session)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    lead = Lead.model_validate(payload.model_dump(exclude={"consent_email", "event_id"}))
    session.add(lead)
    session.flush()
    session.add(EventRegistration(event_id=event.id, lead_id=lead.id))
    session.add(ParticipantToken(lead_id=lead.id, event_id=event.id, token=secrets.token_urlsafe(24)))
    session.add(Consent(lead_id=lead.id, channel=ConsentChannel.EMAIL, granted=payload.consent_email))
    session.add(
        Activity(
            lead_id=lead.id,
            event_id=event.id,
            type=ActivityType.LEAD_CREATED,
            description="Lead cadastrado no evento.",
        )
    )
    session.commit()
    session.refresh(lead)
    return lead


def update_lead(session: Session, lead_id: int, payload: LeadUpdate) -> Lead:
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    duplicate = session.exec(select(Lead).where(Lead.email == payload.email, Lead.id != lead_id)).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="E-mail already registered")
    for field, value in payload.model_dump(exclude={"consent_email"}).items():
        setattr(lead, field, value or None)
    consent = session.exec(select(Consent).where(Consent.lead_id == lead.id, Consent.channel == ConsentChannel.EMAIL)).first()
    if payload.consent_email is not None:
        if consent:
            consent.granted = payload.consent_email
            consent.updated_at = datetime.now(UTC)
        else:
            consent = Consent(lead_id=lead.id, channel=ConsentChannel.EMAIL, granted=payload.consent_email)
    session.add(lead)
    if consent:
        session.add(consent)
    session.commit()
    session.refresh(lead)
    enrich_lead(session, lead.id, force=True)
    return lead


def enrich_lead(session: Session, lead_id: int, force: bool = False) -> LeadEnrichment:
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    existing = session.exec(select(LeadEnrichment).where(LeadEnrichment.lead_id == lead.id)).first()
    if existing:
        if not force and (get_settings().enrichment_provider != "public_web" or not existing.source.startswith("demo:")):
            return existing
        session.delete(existing)
        session.flush()
    data = enrich_with_configured_provider(lead)
    enrichment = LeadEnrichment(
        lead_id=lead.id,
        sector=data.sector,
        company_size=data.company_size,
        interest_signal=data.interest_signal,
        source=data.source,
        confidence=data.confidence,
        role_validation=data.role_validation,
        professional_presence=data.professional_presence,
        qualification_score=data.qualification_score,
        research_sources=data.research_sources,
    )
    no_useful_data = data.sector == "Não identificado" and data.company_size.startswith("Não identificado")
    if lead.status in {LeadStatus.REGISTERED, LeadStatus.ENRICHED, LeadStatus.ENRICHMENT_UNAVAILABLE}:
        lead.status = LeadStatus.ENRICHMENT_UNAVAILABLE if no_useful_data else LeadStatus.ENRICHED
    session.add(enrichment)
    session.add(lead)
    session.flush()
    session.add(
        Activity(
            lead_id=lead.id,
            type=ActivityType.LEAD_ENRICHED,
            description=(
                f"Perfil enriquecido por fonte pública com confiança {enrichment.confidence:.0%}."
                if enrichment.source.startswith("http")
                else f"Perfil enriquecido pela fonte {enrichment.source}."
            ),
        )
    )
    session.commit()
    session.refresh(enrichment)
    return enrichment


def refresh_lead_enrichment(session: Session, lead_id: int, payload: EnrichmentSourceUpdate) -> LeadEnrichment:
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.company_website = payload.company_website or None
    lead.linkedin_url = payload.linkedin_url or None
    session.add(lead)
    session.commit()
    return enrich_lead(session, lead_id, force=True)


def sanitize_email_text(value: str, include_signature: bool = False) -> str:
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1: \2", value)
    text = text.replace("**", "").replace("*", "").replace("—", "-")
    text = re.sub(r"\[(?:Seu Nome|Nome da Equipe|Seu Nome/Nome da Equipe)\]", "Equipe Vigil Summit", text, flags=re.IGNORECASE)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = re.sub(r"\.{2,}", ".", text)
    if include_signature and "Equipe Vigil Summit" not in text:
        text = f"{text}\n\nAtenciosamente,\nEquipe Vigil Summit"
    return text


def create_outbox_message(session: Session, lead: Lead, event: Event, kind: MessageKind) -> Message | None:
    existing = session.exec(
        select(Message).where(Message.lead_id == lead.id, Message.event_id == event.id, Message.kind == kind)
    ).first()
    if existing:
        return None
    consent = session.exec(
        select(Consent).where(Consent.lead_id == lead.id, Consent.channel == ConsentChannel.EMAIL)
    ).first()
    enrichment = session.exec(select(LeadEnrichment).where(LeadEnrichment.lead_id == lead.id)).first()
    attendance = session.exec(
        select(Attendance).where(Attendance.lead_id == lead.id, Attendance.event_id == event.id)
    ).first()
    behavior_context = ""
    if kind == MessageKind.ATTENDANCE_REQUEST:
        previous = session.exec(
            select(Message).where(
                Message.lead_id == lead.id,
                Message.event_id == event.id,
                Message.kind == MessageKind.REGISTRATION_CONFIRMATION,
            )
        ).first()
        opened = previous and session.exec(
            select(MessageDeliveryEvent).where(
                MessageDeliveryEvent.message_id == previous.id,
                MessageDeliveryEvent.type == DeliveryEventType.OPENED,
            )
        ).first()
        behavior_context = (
            "Obrigado por acompanhar nossas comunicações."
            if opened
            else "Como a mensagem anterior não foi aberta, estamos reforçando a confirmação por um assunto diferente."
        )
    if kind in {
        MessageKind.POST_EVENT_THANK_YOU,
        MessageKind.MISSED_EVENT_FOLLOWUP,
        MessageKind.MEETING_INVITE,
    }:
        interest_response = session.exec(
            select(ParticipantResponse)
            .where(
                ParticipantResponse.lead_id == lead.id,
                ParticipantResponse.event_id == event.id,
                ParticipantResponse.kind == ResponseKind.INTERESTED,
            )
            .order_by(ParticipantResponse.created_at.desc())
        ).first()
        contexts = []
        if interest_response and interest_response.note:
            contexts.append(f"Interesse declarado pelo participante: {interest_response.note}")
        if attendance and attendance.interest_topic:
            contexts.append(f"Tema registrado pela equipe: {attendance.interest_topic}")
        if enrichment and enrichment.interest_signal:
            contexts.append(f"Sinal público: {enrichment.interest_signal}")
        behavior_context = " | ".join(contexts)
    content = get_message_provider().generate(kind, lead, event, enrichment, attendance, behavior_context)
    content.subject = sanitize_email_text(content.subject).splitlines()[0][:200]
    content.body = sanitize_email_text(content.body)
    participant_token = get_or_create_participant_token(session, lead, event)
    participant_url = f"{get_settings().frontend_url.rstrip('/')}/participant?token={participant_token.token}"
    action_label = (
        "Consulte os horários disponíveis e agende uma reunião"
        if kind in {MessageKind.POST_EVENT_THANK_YOU, MessageKind.MISSED_EVENT_FOLLOWUP, MessageKind.MEETING_INVITE}
        else "Confirme ou gerencie sua participação"
    )
    content.body = sanitize_email_text(f"{content.body}\n\n{action_label}: {participant_url}", include_signature=True)
    allowed = bool(consent and consent.granted)
    message = Message(
        lead_id=lead.id,
        event_id=event.id,
        kind=kind,
        subject=content.subject,
        body=content.body,
        status=MessageStatus.PENDING if allowed else MessageStatus.CANCELLED,
        failure_reason=None if allowed else "Sem consentimento para comunicação por e-mail.",
    )
    session.add(message)
    session.flush()
    session.add(
        GenerationTrace(
            lead_id=lead.id,
            event_id=event.id,
            message_kind=kind,
            provider=content.provider,
            model=content.model,
            prompt_version=content.prompt_version,
        )
    )
    delivery_success = False
    if allowed:
        result = get_email_provider().send(str(lead.email), content.subject, content.body)
        delivery_success = result.success
        message.status = MessageStatus.SENT if result.success else MessageStatus.FAILED
        message.sent_at = datetime.now(UTC) if result.success else None
        message.failure_reason = result.detail
        session.add(message)
        session.add(
            MessageDeliveryEvent(
                message_id=message.id,
                type=(DeliveryEventType.DELIVERED if result.success and result.provider == "fake" else DeliveryEventType.SENT)
                if result.success
                else DeliveryEventType.FAILED,
                provider=result.provider,
                external_id=result.external_id,
                detail=result.detail,
            )
        )
    session.add(
        Activity(
            lead_id=lead.id,
            event_id=event.id,
            type=ActivityType.MESSAGE_SENT if delivery_success else ActivityType.MESSAGE_BLOCKED,
            description=(
                f"Mensagem '{kind.value}' enviada na simulação."
                if delivery_success
                else f"Mensagem '{kind.value}' não enviada: {message.failure_reason or 'falha no provider'}."
            ),
        )
    )
    return message


def retry_failed_message(session: Session, message_id: int) -> Message:
    message = session.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.status != MessageStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed messages can be retried")
    lead = session.get(Lead, message.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    result = get_email_provider().send(str(lead.email), message.subject, message.body)
    message.status = MessageStatus.SENT if result.success else MessageStatus.FAILED
    message.sent_at = datetime.now(UTC) if result.success else None
    message.failure_reason = None if result.success else result.detail
    session.add(message)
    session.add(MessageDeliveryEvent(message_id=message.id, type=DeliveryEventType.SENT if result.success else DeliveryEventType.FAILED, provider=result.provider, external_id=result.external_id, detail=result.detail))
    session.commit()
    session.refresh(message)
    return message


def message_interval_elapsed(session: Session, lead: Lead, event: Event) -> bool:
    schedule = ensure_event_configuration(session, event)
    last_message = session.exec(
        select(Message)
        .where(Message.lead_id == lead.id, Message.event_id == event.id)
        .order_by(Message.created_at.desc())
    ).first()
    if not last_message:
        return True
    next_allowed_at = ensure_aware(last_message.created_at) + timedelta(hours=schedule.message_interval_hours)
    return datetime.now(UTC) >= next_allowed_at


def run_pre_event_cadence(session: Session) -> list[Message]:
    created: list[Message] = []
    for lead in session.exec(select(Lead).order_by(Lead.created_at)).all():
        event = get_event_for_lead(session, lead)
        sequence = cadence_sequence(lead, event)
        if not sequence or not message_interval_elapsed(session, lead, event):
            continue
        existing_kinds = set(
            session.exec(select(Message.kind).where(Message.lead_id == lead.id, Message.event_id == event.id)).all()
        )
        next_kind = next((kind for kind in sequence if kind not in existing_kinds), None)
        if next_kind:
            message = create_outbox_message(session, lead, event, next_kind)
            if message:
                created.append(message)
    session.commit()
    for message in created:
        session.refresh(message)
    return created


def record_response(session: Session, lead_id: int, payload: ParticipantResponseCreate) -> ParticipantResponse:
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    event = get_event_for_lead(session, lead)
    response = ParticipantResponse(lead_id=lead.id, event_id=event.id, **payload.model_dump())
    if payload.kind in (ResponseKind.CONFIRMED, ResponseKind.INTERESTED):
        lead.status = LeadStatus.CONFIRMED
    elif payload.kind == ResponseKind.DECLINED:
        lead.status = LeadStatus.DECLINED
    session.add(response)
    session.add(lead)
    session.flush()
    session.add(
        Activity(
            lead_id=lead.id,
            event_id=event.id,
            type=ActivityType.RESPONSE_RECEIVED,
            description=f"Resposta registrada: {payload.kind.value}.",
        )
    )
    session.commit()
    session.refresh(response)
    return response


def record_attendance(session: Session, lead_id: int, payload: AttendanceCreate) -> Attendance:
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    event = get_event_for_lead(session, lead)
    attendance = session.exec(
        select(Attendance).where(Attendance.lead_id == lead.id, Attendance.event_id == event.id)
    ).first()
    if attendance:
        attendance.status = payload.status
        attendance.interest_topic = payload.interest_topic
        attendance.recorded_at = datetime.now(UTC)
    else:
        attendance = Attendance(lead_id=lead.id, event_id=event.id, **payload.model_dump())
    lead.status = LeadStatus.ATTENDED if payload.status == AttendanceStatus.ATTENDED else LeadStatus.NO_SHOW
    session.add(attendance)
    session.add(lead)
    session.flush()
    session.add(
        Activity(
            lead_id=lead.id,
            event_id=event.id,
            type=ActivityType.CHECK_IN_RECORDED,
            description=f"Presença registrada: {payload.status.value}.",
        )
    )
    session.commit()
    session.refresh(attendance)
    return attendance


def run_post_event_followup(session: Session) -> list[Message]:
    created: list[Message] = []
    attendances = session.exec(select(Attendance).order_by(Attendance.recorded_at)).all()
    for attendance in attendances:
        lead = session.get(Lead, attendance.lead_id)
        event = session.get(Event, attendance.event_id)
        if not lead or not event:
            continue
        if session.exec(
            select(Meeting).where(Meeting.lead_id == lead.id, Meeting.event_id == event.id)
        ).first():
            continue
        sequence = (
            [MessageKind.POST_EVENT_THANK_YOU, MessageKind.MEETING_INVITE]
            if attendance.status == AttendanceStatus.ATTENDED
            else [MessageKind.MISSED_EVENT_FOLLOWUP, MessageKind.MEETING_INVITE]
        )
        if not message_interval_elapsed(session, lead, event):
            continue
        existing_kinds = set(
            session.exec(select(Message.kind).where(Message.lead_id == lead.id, Message.event_id == event.id)).all()
        )
        next_kind = next((kind for kind in sequence if kind not in existing_kinds), None)
        if next_kind:
            message = create_outbox_message(session, lead, event, next_kind)
            if message:
                created.append(message)
    session.commit()
    for message in created:
        session.refresh(message)
    return created


def available_meeting_slots(session: Session, event_id: int) -> list[datetime]:
    booked = set(session.exec(select(Meeting.starts_at).where(Meeting.event_id == event_id)).all())
    slots = session.exec(
        select(MeetingSlot).where(MeetingSlot.event_id == event_id, MeetingSlot.active == True).order_by(MeetingSlot.starts_at)  # noqa: E712
    ).all()
    now = datetime.now(UTC)
    return [ensure_aware(slot.starts_at) for slot in slots if ensure_aware(slot.starts_at) > now and slot.starts_at not in booked]


def book_meeting(session: Session, lead_id: int, payload: MeetingCreate) -> Meeting:
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    event = get_event_for_lead(session, lead)
    existing = session.exec(
        select(Meeting).where(Meeting.lead_id == lead.id, Meeting.event_id == event.id)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Meeting already booked")
    starts_at = payload.starts_at
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)
    if starts_at <= datetime.now(UTC):
        raise HTTPException(status_code=422, detail="Meeting must be in the future")
    if starts_at not in available_meeting_slots(session, event.id):
        raise HTTPException(status_code=409, detail="Meeting slot is not available")
    selected_slot = session.exec(
        select(MeetingSlot).where(MeetingSlot.event_id == event.id, MeetingSlot.starts_at == starts_at)
    ).first()
    if selected_slot:
        selected_slot.active = False
        session.add(selected_slot)
    meeting = Meeting(lead_id=lead.id, event_id=event.id, starts_at=starts_at)
    lead.status = LeadStatus.MEETING_BOOKED
    session.add(meeting)
    session.add(lead)
    session.flush()
    session.add(
        Activity(
            lead_id=lead.id,
            event_id=event.id,
            type=ActivityType.MEETING_BOOKED,
            description=f"Reunião agendada para {starts_at.isoformat()}.",
        )
    )
    session.commit()
    session.refresh(meeting)
    return meeting


def update_meeting(session: Session, meeting_id: int, payload: MeetingUpdate) -> Meeting:
    meeting = session.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    meeting.meeting_url = str(payload.meeting_url) if payload.meeting_url else None
    meeting.admin_note = payload.admin_note or None
    session.add(meeting)
    session.commit()
    session.refresh(meeting)
    return meeting


def notify_meeting_participant(session: Session, meeting_id: int) -> Meeting:
    meeting = session.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if not meeting.meeting_url:
        raise HTTPException(status_code=422, detail="Meeting URL is required")
    lead = session.get(Lead, meeting.lead_id)
    event = session.get(Event, meeting.event_id)
    if not lead or not event:
        raise HTTPException(status_code=404, detail="Meeting context not found")
    consent = session.exec(
        select(Consent).where(Consent.lead_id == lead.id, Consent.channel == ConsentChannel.EMAIL)
    ).first()
    if not consent or not consent.granted:
        raise HTTPException(status_code=409, detail="Participant has no email consent")
    local_time = ensure_aware(meeting.starts_at).astimezone(ZoneInfo("America/Sao_Paulo"))
    body = (
        f"Olá, {lead.name}.\n\n"
        f"Sua reunião com a equipe Vigil.AI está confirmada.\n\n"
        f"Data: {local_time.strftime('%d/%m/%Y')}\n"
        f"Horário: {local_time.strftime('%H:%M')} (horário de Brasília)\n"
        f"Acesso à chamada: {meeting.meeting_url}"
    )
    if meeting.admin_note:
        body += f"\nObservações: {meeting.admin_note}"
    body = sanitize_email_text(body, include_signature=True)
    message = session.exec(
        select(Message).where(
            Message.lead_id == lead.id,
            Message.event_id == event.id,
            Message.kind == MessageKind.MEETING_CONFIRMATION,
        )
    ).first()
    if not message:
        message = Message(
            lead_id=lead.id,
            event_id=event.id,
            kind=MessageKind.MEETING_CONFIRMATION,
            subject="Reunião confirmada com a Vigil.AI",
            body=body,
        )
    else:
        message.subject = "Reunião confirmada com a Vigil.AI"
        message.body = body
    session.add(message)
    session.flush()
    result = get_email_provider().send(str(lead.email), message.subject, message.body)
    message.status = MessageStatus.SENT if result.success else MessageStatus.FAILED
    message.sent_at = datetime.now(UTC) if result.success else None
    message.failure_reason = None if result.success else result.detail
    session.add(message)
    session.add(
        MessageDeliveryEvent(
            message_id=message.id,
            type=DeliveryEventType.SENT if result.success else DeliveryEventType.FAILED,
            provider=result.provider,
            external_id=result.external_id,
            detail=result.detail,
        )
    )
    if not result.success:
        session.commit()
        raise HTTPException(status_code=502, detail=result.detail or "Email delivery failed")
    meeting.notified_at = datetime.now(UTC)
    session.add(meeting)
    session.add(
        Activity(
            lead_id=lead.id,
            event_id=event.id,
            type=ActivityType.MESSAGE_SENT,
            description="Participante avisado sobre os detalhes da reunião.",
        )
    )
    session.commit()
    session.refresh(meeting)
    return meeting


def delete_meeting(session: Session, meeting_id: int) -> None:
    meeting = session.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    lead = session.get(Lead, meeting.lead_id)
    slot = session.exec(
        select(MeetingSlot).where(
            MeetingSlot.event_id == meeting.event_id,
            MeetingSlot.starts_at == meeting.starts_at,
        )
    ).first()
    if slot:
        slot.active = True
        session.add(slot)
    else:
        session.add(MeetingSlot(event_id=meeting.event_id, starts_at=meeting.starts_at, active=True))
    if lead:
        attendance = session.exec(
            select(Attendance).where(Attendance.lead_id == lead.id, Attendance.event_id == meeting.event_id)
        ).first()
        if attendance:
            lead.status = LeadStatus.ATTENDED if attendance.status == AttendanceStatus.ATTENDED else LeadStatus.NO_SHOW
            session.add(lead)
        session.add(Activity(lead_id=lead.id, event_id=meeting.event_id, type=ActivityType.MEETING_CANCELLED, description=f"Reunião de {meeting.starts_at.isoformat()} excluída pela administração."))
    session.delete(meeting)
    session.commit()


def register_delivery_event(
    session: Session,
    message_id: int,
    event_type: DeliveryEventType,
    detail: str | None = None,
) -> MessageDeliveryEvent:
    message = session.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    existing = session.exec(
        select(MessageDeliveryEvent).where(
            MessageDeliveryEvent.message_id == message.id,
            MessageDeliveryEvent.type == event_type,
        )
    ).first()
    if existing:
        return existing
    delivery_event = MessageDeliveryEvent(
        message_id=message.id,
        type=event_type,
        provider="manual",
        detail=detail,
    )
    if event_type == DeliveryEventType.FAILED:
        message.status = MessageStatus.FAILED
        message.failure_reason = detail or "Falha informada pelo canal."
        session.add(message)
    session.add(delivery_event)
    session.commit()
    session.refresh(delivery_event)
    return delivery_event


def get_participant_token(session: Session, token: str) -> ParticipantToken:
    participant_token = session.exec(select(ParticipantToken).where(ParticipantToken.token == token)).first()
    if not participant_token:
        raise HTTPException(status_code=404, detail="Participant link not found")
    return participant_token


def get_participant_context(session: Session, token: str) -> ParticipantContext:
    participant_token = get_participant_token(session, token)
    lead = session.get(Lead, participant_token.lead_id)
    event = session.get(Event, participant_token.event_id)
    if not lead or not event:
        raise HTTPException(status_code=404, detail="Participant data not found")
    meeting = session.exec(
        select(Meeting).where(Meeting.lead_id == lead.id, Meeting.event_id == event.id)
    ).first()
    can_schedule = lead.status in (LeadStatus.ATTENDED, LeadStatus.NO_SHOW) and meeting is None
    return ParticipantContext(
        lead_name=lead.name,
        event_name=event.name,
        event_location=event.location,
        event_starts_at=ensure_aware(event.starts_at),
        registration_url=f"{get_settings().frontend_url.rstrip('/')}/register?event={event.id}",
        status=lead.status,
        meeting_slots=available_meeting_slots(session, event.id) if can_schedule else [],
        can_schedule=can_schedule,
        meeting_starts_at=ensure_aware(meeting.starts_at) if meeting else None,
        meeting_url=meeting.meeting_url if meeting else None,
        meeting_note=meeting.admin_note if meeting else None,
    )


def record_participant_open(session: Session, token: str) -> MessageDeliveryEvent | None:
    participant_token = get_participant_token(session, token)
    message = session.exec(
        select(Message)
        .where(
            Message.lead_id == participant_token.lead_id,
            Message.event_id == participant_token.event_id,
            Message.status == MessageStatus.SENT,
        )
        .order_by(Message.created_at.desc())
    ).first()
    if not message:
        return None
    return register_delivery_event(session, message.id, DeliveryEventType.OPENED, "Link do participante acessado.")


def record_response_by_token(
    session: Session,
    token: str,
    payload: ParticipantResponseCreate,
) -> ParticipantResponse:
    participant_token = get_participant_token(session, token)
    return record_response(session, participant_token.lead_id, payload)


def book_meeting_by_token(session: Session, token: str, payload: MeetingCreate) -> Meeting:
    participant_token = get_participant_token(session, token)
    return book_meeting(session, participant_token.lead_id, payload)


def opt_out_by_token(session: Session, token: str) -> Consent:
    participant_token = get_participant_token(session, token)
    return opt_out_lead(session, participant_token.lead_id)


def opt_out_lead(session: Session, lead_id: int) -> Consent:
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    consent = session.exec(
        select(Consent).where(Consent.lead_id == lead.id, Consent.channel == ConsentChannel.EMAIL)
    ).first()
    if consent:
        consent.granted = False
        consent.updated_at = datetime.now(UTC)
    else:
        consent = Consent(lead_id=lead.id, channel=ConsentChannel.EMAIL, granted=False)
    session.add(consent)
    session.flush()
    session.add(
        Activity(
            lead_id=lead.id,
            type=ActivityType.RESPONSE_RECEIVED,
            description="Opt-out de e-mail registrado.",
        )
    )
    session.commit()
    session.refresh(consent)
    return consent


def delete_lead_data(session: Session, lead_id: int) -> None:
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    message_ids = session.exec(select(Message.id).where(Message.lead_id == lead_id)).all()
    if message_ids:
        session.exec(delete(MessageDeliveryEvent).where(MessageDeliveryEvent.message_id.in_(message_ids)))
    for model in (
        GenerationTrace,
        ParticipantResponse,
        Attendance,
        Meeting,
        Message,
        Activity,
        Consent,
        LeadEnrichment,
        EventRegistration,
        ParticipantToken,
    ):
        session.exec(delete(model).where(model.lead_id == lead_id))
    session.delete(lead)
    session.commit()


def delete_event_data(session: Session, event_id: int) -> None:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    lead_ids = session.exec(select(EventRegistration.lead_id).where(EventRegistration.event_id == event_id)).all()
    for lead_id in lead_ids:
        delete_lead_data(session, lead_id)
    message_ids = session.exec(select(Message.id).where(Message.event_id == event_id)).all()
    if message_ids:
        session.exec(delete(MessageDeliveryEvent).where(MessageDeliveryEvent.message_id.in_(message_ids)))
    for model in (
        GenerationTrace,
        ParticipantResponse,
        Attendance,
        Meeting,
        Message,
        Activity,
        ParticipantToken,
        EventRegistration,
        MeetingSlot,
        EventSchedule,
    ):
        session.exec(delete(model).where(model.event_id == event_id))
    session.delete(event)
    session.commit()


def purge_expired_leads(session: Session, retention_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    leads = session.exec(
        select(Lead).where(
            Lead.created_at < cutoff,
            Lead.status.in_([LeadStatus.DECLINED, LeadStatus.NO_SHOW]),
        )
    ).all()
    for lead in leads:
        delete_lead_data(session, lead.id)
    return len(leads)


def get_metrics(session: Session) -> DashboardMetrics:
    def lead_count(status: LeadStatus) -> int:
        return session.exec(select(func.count(Lead.id)).where(Lead.status == status)).one()

    attended = session.exec(select(func.count(Attendance.id)).where(Attendance.status == AttendanceStatus.ATTENDED)).one()
    no_show = session.exec(select(func.count(Attendance.id)).where(Attendance.status == AttendanceStatus.NO_SHOW)).one()
    check_ins = attended + no_show
    return DashboardMetrics(
        total_leads=session.exec(select(func.count(Lead.id))).one(),
        confirmed=lead_count(LeadStatus.CONFIRMED),
        attended=attended,
        no_show=no_show,
        attendance_rate=attended / check_ins if check_ins else 0,
        meetings_booked=session.exec(select(func.count(Meeting.id))).one(),
        messages_sent=session.exec(
            select(func.count(Message.id)).where(Message.status == MessageStatus.SENT)
        ).one(),
        messages_blocked=session.exec(
            select(func.count(Message.id)).where(Message.status == MessageStatus.CANCELLED)
        ).one(),
    )
