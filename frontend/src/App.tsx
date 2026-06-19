import { useEffect, useRef, useState } from "react";

import { apiFetch, clearToken, getToken } from "./api";
import Header from "./components/Header";
import EnrichmentModal from "./components/EnrichmentModal";
import InboxDrawer from "./components/InboxDrawer";
import LeadModal from "./components/LeadModal";
import LeadDetailsModal from "./components/LeadDetailsModal";
import LoginPage from "./components/LoginPage";
import ActivityView from "./views/ActivityView";
import LeadsView from "./views/LeadsView";
import MeetingsView from "./views/MeetingsView";
import OverviewView from "./views/OverviewView";
import SettingsView from "./views/SettingsView";
import type { Activity, Enrichment, EventSettings, EventSummary, Lead, Meeting, Message, Metrics, ViewName } from "./types";

const EMPTY_METRICS: Metrics = {
  total_leads: 0,
  confirmed: 0,
  attended: 0,
  no_show: 0,
  attendance_rate: 0,
  meetings_booked: 0,
  messages_sent: 0,
  messages_blocked: 0,
};

export default function App() {
  const [authenticated, setAuthenticated] = useState(Boolean(getToken()));
  const [activeView, setActiveView] = useState<ViewName>("overview");
  const [leads, setLeads] = useState<Lead[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [enrichments, setEnrichments] = useState<Enrichment[]>([]);
  const [metrics, setMetrics] = useState<Metrics>(EMPTY_METRICS);
  const [eventSettings, setEventSettings] = useState<EventSettings | null>(null);
  const [leadModalOpen, setLeadModalOpen] = useState(false);
  const [inboxOpen, setInboxOpen] = useState(false);
  const [enrichmentLead, setEnrichmentLead] = useState<Lead | null>(null);
  const [detailsLead, setDetailsLead] = useState<Lead | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actionLoading, setActionLoading] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const refreshLock = useRef(false);

  async function loadDashboard(silent = false) {
    if (refreshLock.current) return;
    refreshLock.current = true;
    if (!silent) setRefreshing(true);
    try {
      const responses = await Promise.all([
        apiFetch("/api/leads"),
        apiFetch("/api/activities"),
        apiFetch("/api/messages"),
        apiFetch("/api/enrichments"),
        apiFetch("/api/metrics"),
        apiFetch("/api/events"),
        apiFetch("/api/meetings"),
      ]);
      if (responses.some((response) => response.status === 401)) {
        clearToken();
        setAuthenticated(false);
        return;
      }
      if (responses.some((response) => !response.ok)) throw new Error("Não foi possível atualizar os dados do painel.");
      const [leadData, activityData, messageData, enrichmentData, metricData, eventData, meetingData] = await Promise.all(responses.map((response) => response.json()));
      setLeads(leadData);
      setActivities(activityData);
      setMessages(messageData);
      setEnrichments(enrichmentData);
      setMetrics(metricData);
      setMeetings(meetingData);
      const activeEvent = (eventData as EventSummary[]).find((item) => item.active) ?? eventData[0];
      if (activeEvent) {
        const settingsResponse = await apiFetch(`/api/events/${activeEvent.id}/settings`);
        if (!settingsResponse.ok) throw new Error("Não foi possível carregar as configurações do evento.");
        setEventSettings(await settingsResponse.json());
      } else {
        setEventSettings(null);
      }
      setLastUpdated(new Date());
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao atualizar o painel.");
    } finally {
      refreshLock.current = false;
      setRefreshing(false);
      setInitialLoading(false);
    }
  }

  useEffect(() => {
    if (!authenticated) return;
    loadDashboard();
    const interval = window.setInterval(() => loadDashboard(true), 5_000);
    return () => window.clearInterval(interval);
  }, [authenticated]);

  async function createLead(payload: Record<string, FormDataEntryValue | boolean>) {
    setActionLoading("create-lead");
    try {
      const response = await apiFetch("/api/leads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...payload, event_id: eventSettings?.id }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(response.status === 409 ? "Este e-mail já foi cadastrado." : data?.detail ?? "Falha ao cadastrar participante.");
      }
      setLeadModalOpen(false);
      setActiveView("leads");
      setNotice("Participante cadastrado. A automação cuidará das próximas etapas.");
      await loadDashboard();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao cadastrar participante.");
    } finally {
      setActionLoading("");
    }
  }

  async function recordAttendance(leadId: number, status: "attended" | "no_show") {
    setActionLoading(`attendance-${leadId}`);
    try {
      const response = await apiFetch(`/api/leads/${leadId}/attendance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, interest_topic: status === "attended" ? "gestão de vulnerabilidades" : null }),
      });
      if (!response.ok) throw new Error("Não foi possível registrar a presença.");
      setNotice(status === "attended" ? "Presença registrada." : "Ausência registrada.");
      await loadDashboard();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao registrar presença.");
    } finally {
      setActionLoading("");
    }
  }

  async function saveEventSettings(payload: object) {
    if (!eventSettings) return;
    setActionLoading("save-settings");
    try {
      const response = await apiFetch(`/api/events/${eventSettings.id}/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail ?? "Não foi possível salvar as configurações.");
      }
      setEventSettings(await response.json());
      setLastUpdated(new Date());
      setNotice("Configurações do evento salvas.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar configurações.");
    } finally {
      setActionLoading("");
    }
  }

  async function deleteLead(leadId: number) {
    if (!window.confirm("Excluir este participante e todo o seu histórico?")) return;
    setActionLoading(`delete-${leadId}`);
    try {
      const response = await apiFetch(`/api/leads/${leadId}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Não foi possível excluir o participante.");
      setNotice("Participante excluído.");
      await loadDashboard();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao excluir participante.");
    } finally {
      setActionLoading("");
    }
  }

  async function refreshEnrichment(leadId: number, payload: object) {
    setActionLoading(`enrichment-${leadId}`);
    try {
      const response = await apiFetch(`/api/leads/${leadId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error("Não foi possível consultar o site informado.");
      setEnrichmentLead(null);
      setNotice("Dados do participante e enriquecimento atualizados.");
      await loadDashboard();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao atualizar enriquecimento.");
    } finally {
      setActionLoading("");
    }
  }

  async function retryMessage(messageId: number) {
    setActionLoading(`retry-${messageId}`);
    try {
      const response = await apiFetch(`/api/messages/${messageId}/retry`, { method: "POST" });
      if (!response.ok) throw new Error("O envio ainda foi recusado. Confira as configurações do Resend.");
      setNotice("E-mail enviado com sucesso.");
      await loadDashboard();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao reenviar e-mail.");
      await loadDashboard();
    } finally {
      setActionLoading("");
    }
  }

  async function deleteEvent() {
    if (!eventSettings || !window.confirm("Excluir o evento e todo o histórico relacionado? Esta ação não pode ser desfeita.")) return;
    setActionLoading("delete-event");
    try {
      const response = await apiFetch(`/api/events/${eventSettings.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Não foi possível excluir o evento.");
      setNotice("Evento excluído. Um novo evento vazio foi preparado.");
      await loadDashboard();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao excluir evento.");
    } finally {
      setActionLoading("");
    }
  }

  async function deleteMeeting(meetingId: number) {
    if (!window.confirm("Excluir esta reunião e devolver o horário à disponibilidade?")) return;
    setActionLoading(`delete-meeting-${meetingId}`);
    try {
      const response = await apiFetch(`/api/meetings/${meetingId}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Não foi possível excluir a reunião.");
      setNotice("Reunião excluída e horário disponibilizado novamente.");
      await loadDashboard();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao excluir reunião.");
    } finally { setActionLoading(""); }
  }

  async function saveMeeting(meetingId: number, payload: object) {
    setActionLoading(`save-meeting-${meetingId}`);
    try {
      const response = await apiFetch(`/api/meetings/${meetingId}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!response.ok) throw new Error("Não foi possível salvar os detalhes da reunião.");
      setNotice("Detalhes da reunião salvos.");
      await loadDashboard();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao salvar reunião."); }
    finally { setActionLoading(""); }
  }

  async function notifyMeeting(meetingId: number) {
    setActionLoading(`notify-meeting-${meetingId}`);
    try {
      const response = await apiFetch(`/api/meetings/${meetingId}/notify`, { method: "POST" });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(data?.detail ?? "Não foi possível avisar o participante.");
      setNotice("Participante avisado sobre a reunião.");
      await loadDashboard();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao avisar participante."); }
    finally { setActionLoading(""); }
  }

  function logout() {
    clearToken();
    setAuthenticated(false);
  }

  if (!authenticated) return <LoginPage onLogin={() => setAuthenticated(true)} />;

  if (initialLoading) return <div className="app-loading"><span className="loader" /><strong>Preparando o painel...</strong><small>Carregando evento, participantes e automações.</small></div>;

  return (
    <div className="app-shell">
      <Header activeView={activeView} notificationCount={messages.length} lastUpdated={lastUpdated} onNavigate={setActiveView} onAddLead={() => setLeadModalOpen(true)} onOpenInbox={() => setInboxOpen(true)} onLogout={logout} />
      {refreshing && <div className="refresh-bar" />}
      {error && <div className="error-banner"><span>{error}</span><button onClick={() => setError("")}>×</button></div>}
      {notice && <div className="success-banner"><span>{notice}</span><button onClick={() => setNotice("")}>×</button></div>}
      <main className="dashboard-main">
        {activeView === "overview" && <OverviewView metrics={metrics} activities={activities} event={eventSettings} />}
        {activeView === "leads" && <LeadsView leads={leads} enrichments={enrichments} actionLoading={actionLoading} onAttendance={recordAttendance} onDelete={deleteLead} onEnrich={setEnrichmentLead} onDetails={setDetailsLead} />}
        {activeView === "meetings" && <MeetingsView meetings={meetings} leads={leads} actionLoading={actionLoading} onDelete={deleteMeeting} onSave={saveMeeting} onNotify={notifyMeeting} />}
        {activeView === "activity" && <ActivityView activities={activities} />}
        {activeView === "settings" && <SettingsView event={eventSettings} loading={actionLoading === "save-settings"} deleting={actionLoading === "delete-event"} onSave={saveEventSettings} onDelete={deleteEvent} />}
      </main>
      {leadModalOpen && <LeadModal loading={actionLoading === "create-lead"} shareUrl={eventSettings ? `${window.location.origin}/register?event=${eventSettings.id}` : undefined} onClose={() => setLeadModalOpen(false)} onSubmit={createLead} />}
      {inboxOpen && <InboxDrawer messages={messages} retrying={actionLoading} onClose={() => setInboxOpen(false)} onRetry={retryMessage} />}
      {enrichmentLead && <EnrichmentModal lead={enrichmentLead} loading={actionLoading === `enrichment-${enrichmentLead.id}`} onClose={() => setEnrichmentLead(null)} onSubmit={refreshEnrichment} />}
      {detailsLead && <LeadDetailsModal lead={detailsLead} enrichment={enrichments.find((item) => item.lead_id === detailsLead.id)} onClose={() => setDetailsLead(null)} />}
    </div>
  );
}
