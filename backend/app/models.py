from datetime import UTC, datetime
from enum import StrEnum

from pydantic import EmailStr, HttpUrl, field_validator
from sqlmodel import Field, SQLModel, UniqueConstraint


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class LeadStatus(StrEnum):
    REGISTERED = "registered"
    ENRICHED = "enriched"
    ENRICHMENT_UNAVAILABLE = "enrichment_unavailable"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    ATTENDED = "attended"
    NO_SHOW = "no_show"
    MEETING_BOOKED = "meeting_booked"


class ConsentChannel(StrEnum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"


class ActivityType(StrEnum):
    LEAD_CREATED = "lead_created"
    LEAD_ENRICHED = "lead_enriched"
    RESPONSE_RECEIVED = "response_received"
    CHECK_IN_RECORDED = "check_in_recorded"
    MESSAGE_SENT = "message_sent"
    MESSAGE_BLOCKED = "message_blocked"
    MEETING_BOOKED = "meeting_booked"
    MEETING_CANCELLED = "meeting_cancelled"


class MessageStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageKind(StrEnum):
    REGISTRATION_CONFIRMATION = "registration_confirmation"
    ATTENDANCE_REQUEST = "attendance_request"
    EVENT_REMINDER = "event_reminder"
    FINAL_INSTRUCTIONS = "final_instructions"
    POST_EVENT_THANK_YOU = "post_event_thank_you"
    MISSED_EVENT_FOLLOWUP = "missed_event_followup"
    MEETING_INVITE = "meeting_invite"
    MEETING_CONFIRMATION = "meeting_confirmation"


class ResponseKind(StrEnum):
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    INTERESTED = "interested"


class AttendanceStatus(StrEnum):
    ATTENDED = "attended"
    NO_SHOW = "no_show"


class MeetingStatus(StrEnum):
    BOOKED = "booked"
    CANCELLED = "cancelled"


class DeliveryEventType(StrEnum):
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    FAILED = "failed"


class LeadBase(SQLModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    company: str | None = Field(default=None, max_length=160)
    role: str | None = Field(default=None, max_length=120)
    company_website: str | None = Field(default=None, max_length=300)
    linkedin_url: str | None = Field(default=None, max_length=300)


class Lead(LeadBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    status: LeadStatus = Field(default=LeadStatus.REGISTERED, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LeadCreate(LeadBase):
    consent_email: bool = False
    event_id: int | None = None


class LeadRead(LeadBase):
    id: int
    status: LeadStatus
    created_at: datetime


class LeadUpdate(LeadBase):
    consent_email: bool | None = None


class EnrichmentSourceUpdate(SQLModel):
    company_website: str | None = Field(default=None, max_length=300)
    linkedin_url: str | None = Field(default=None, max_length=300)


class Event(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, max_length=160)
    starts_at: datetime
    location: str = Field(max_length=200)
    active: bool = True


class EventRead(SQLModel):
    id: int
    name: str
    starts_at: datetime
    location: str
    active: bool

    _utc_starts_at = field_validator("starts_at", mode="before")(as_utc)


class EventCreate(SQLModel):
    name: str = Field(min_length=3, max_length=160)
    starts_at: datetime
    location: str = Field(max_length=200)


class EventSettingsUpdate(SQLModel):
    name: str = Field(min_length=3, max_length=160)
    starts_at: datetime
    location: str = Field(max_length=200)
    message_interval_hours: float = Field(ge=0, le=720)
    meeting_slots: list[datetime]


class MeetingSlot(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("event_id", "starts_at"),)

    id: int | None = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="event.id", index=True)
    starts_at: datetime
    active: bool = True


class MeetingSlotRead(SQLModel):
    id: int
    starts_at: datetime
    active: bool

    _utc_starts_at = field_validator("starts_at", mode="before")(as_utc)


class EventSchedule(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("event_id"),)

    id: int | None = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="event.id", index=True)
    message_interval_hours: float = Field(default=24, ge=0, le=720)


class EventSettingsRead(SQLModel):
    id: int
    name: str
    starts_at: datetime
    location: str
    active: bool
    message_interval_hours: float
    meeting_slots: list[MeetingSlotRead]

    _utc_starts_at = field_validator("starts_at", mode="before")(as_utc)


class EventRegistration(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("event_id", "lead_id"),)

    id: int | None = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="event.id", index=True)
    lead_id: int = Field(foreign_key="lead.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Consent(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("lead_id", "channel"),)

    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id", index=True)
    channel: ConsentChannel
    granted: bool
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConsentRead(SQLModel):
    lead_id: int
    channel: ConsentChannel
    granted: bool
    updated_at: datetime


class Activity(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id", index=True)
    event_id: int | None = Field(default=None, foreign_key="event.id", index=True)
    type: ActivityType
    description: str = Field(max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ActivityRead(SQLModel):
    id: int
    lead_id: int
    event_id: int | None
    type: ActivityType
    description: str
    created_at: datetime


class Message(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("lead_id", "event_id", "kind"),)

    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id", index=True)
    event_id: int = Field(foreign_key="event.id", index=True)
    channel: ConsentChannel = ConsentChannel.EMAIL
    kind: MessageKind
    subject: str = Field(max_length=200)
    body: str = Field(max_length=2000)
    status: MessageStatus = Field(default=MessageStatus.PENDING, index=True)
    failure_reason: str | None = Field(default=None, max_length=300)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sent_at: datetime | None = None


class MessageRead(SQLModel):
    id: int
    lead_id: int
    event_id: int
    channel: ConsentChannel
    kind: MessageKind
    subject: str
    body: str
    status: MessageStatus
    failure_reason: str | None
    created_at: datetime
    sent_at: datetime | None


class MessageDeliveryEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    message_id: int = Field(foreign_key="message.id", index=True)
    type: DeliveryEventType
    provider: str = Field(max_length=80)
    external_id: str | None = Field(default=None, max_length=200)
    detail: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MessageDeliveryCreate(SQLModel):
    type: DeliveryEventType
    detail: str | None = Field(default=None, max_length=500)


class MessageDeliveryRead(MessageDeliveryCreate):
    id: int
    message_id: int
    provider: str
    external_id: str | None
    created_at: datetime


class GenerationTrace(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id", index=True)
    event_id: int = Field(foreign_key="event.id", index=True)
    message_kind: MessageKind
    provider: str = Field(max_length=80)
    model: str = Field(max_length=120)
    prompt_version: str = Field(max_length=40)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GenerationTraceRead(SQLModel):
    id: int
    lead_id: int
    event_id: int
    message_kind: MessageKind
    provider: str
    model: str
    prompt_version: str
    created_at: datetime


class LeadEnrichment(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("lead_id"),)

    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id", index=True)
    sector: str = Field(max_length=120)
    company_size: str = Field(max_length=80)
    interest_signal: str = Field(max_length=300)
    source: str = Field(max_length=200)
    confidence: float = Field(ge=0, le=1)
    role_validation: str = Field(default="Não validado publicamente", max_length=200)
    professional_presence: str = Field(default="Não localizada", max_length=300)
    qualification_score: int = Field(default=0, ge=0, le=100)
    research_sources: str | None = Field(default=None, max_length=1000)
    enriched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LeadEnrichmentRead(SQLModel):
    id: int
    lead_id: int
    sector: str
    company_size: str
    interest_signal: str
    source: str
    confidence: float
    role_validation: str
    professional_presence: str
    qualification_score: int
    research_sources: str | None
    enriched_at: datetime


class ParticipantResponse(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id", index=True)
    event_id: int = Field(foreign_key="event.id", index=True)
    kind: ResponseKind
    note: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ParticipantResponseCreate(SQLModel):
    kind: ResponseKind
    note: str | None = Field(default=None, max_length=500)


class ParticipantResponseRead(ParticipantResponseCreate):
    id: int
    lead_id: int
    event_id: int
    created_at: datetime


class ParticipantToken(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("token"), UniqueConstraint("lead_id", "event_id"))

    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id", index=True)
    event_id: int = Field(foreign_key="event.id", index=True)
    token: str = Field(index=True, max_length=120)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ParticipantContext(SQLModel):
    lead_name: str
    event_name: str
    event_location: str
    event_starts_at: datetime
    registration_url: str
    status: LeadStatus
    meeting_slots: list[datetime]
    can_schedule: bool
    meeting_starts_at: datetime | None = None
    meeting_url: str | None = None
    meeting_note: str | None = None


class Attendance(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("lead_id", "event_id"),)

    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id", index=True)
    event_id: int = Field(foreign_key="event.id", index=True)
    status: AttendanceStatus
    interest_topic: str | None = Field(default=None, max_length=200)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AttendanceCreate(SQLModel):
    status: AttendanceStatus
    interest_topic: str | None = Field(default=None, max_length=200)


class AttendanceRead(AttendanceCreate):
    id: int
    lead_id: int
    event_id: int
    recorded_at: datetime


class Meeting(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("lead_id", "event_id"),)

    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="lead.id", index=True)
    event_id: int = Field(foreign_key="event.id", index=True)
    starts_at: datetime
    status: MeetingStatus = MeetingStatus.BOOKED
    meeting_url: str | None = Field(default=None, max_length=500)
    admin_note: str | None = Field(default=None, max_length=500)
    notified_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MeetingCreate(SQLModel):
    starts_at: datetime


class MeetingUpdate(SQLModel):
    meeting_url: HttpUrl | None = None
    admin_note: str | None = Field(default=None, max_length=500)

    @field_validator("meeting_url")
    @classmethod
    def validate_meeting_url(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value and value.scheme != "https" and value.host not in {"localhost", "127.0.0.1"}:
            raise ValueError("O link da reunião deve usar HTTPS")
        return value


class MeetingRead(SQLModel):
    id: int
    lead_id: int
    event_id: int
    starts_at: datetime
    status: MeetingStatus
    meeting_url: str | None
    admin_note: str | None
    notified_at: datetime | None
    created_at: datetime

    _utc_datetimes = field_validator("starts_at", "notified_at", "created_at", mode="before")(lambda value: as_utc(value) if value else value)


class DashboardMetrics(SQLModel):
    total_leads: int
    confirmed: int
    attended: int
    no_show: int
    attendance_rate: float
    meetings_booked: int
    messages_sent: int
    messages_blocked: int


class LoginRequest(SQLModel):
    email: str
    password: str


class LoginResponse(SQLModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 28800
