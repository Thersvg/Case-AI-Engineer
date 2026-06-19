export type Lead = {
  id: number;
  name: string;
  email: string;
  company?: string;
  role?: string;
  company_website?: string;
  linkedin_url?: string;
  status: string;
  created_at: string;
};

export type Activity = {
  id: number;
  lead_id: number;
  type: string;
  description: string;
  created_at: string;
};

export type Message = {
  id: number;
  lead_id: number;
  kind: string;
  subject: string;
  body: string;
  status: string;
  failure_reason?: string;
  created_at: string;
  sent_at?: string;
};

export type Enrichment = {
  lead_id: number;
  sector: string;
  company_size: string;
  interest_signal: string;
  source: string;
  confidence: number;
  role_validation: string;
  professional_presence: string;
  qualification_score: number;
  research_sources?: string;
  enriched_at: string;
};

export type Metrics = {
  total_leads: number;
  confirmed: number;
  attended: number;
  no_show: number;
  attendance_rate: number;
  meetings_booked: number;
  messages_sent: number;
  messages_blocked: number;
};

export type EventSummary = {
  id: number;
  name: string;
  starts_at: string;
  location: string;
  active: boolean;
};

export type MeetingSlot = {
  id: number;
  starts_at: string;
  active: boolean;
};

export type EventSettings = EventSummary & {
  message_interval_hours: number;
  meeting_slots: MeetingSlot[];
};

export type Meeting = {
  id: number;
  lead_id: number;
  event_id: number;
  starts_at: string;
  status: string;
  meeting_url?: string;
  admin_note?: string;
  notified_at?: string;
  created_at: string;
};

export type ViewName = "overview" | "leads" | "meetings" | "activity" | "settings";
