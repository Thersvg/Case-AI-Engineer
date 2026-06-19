import type { Activity, EventSettings, Metrics } from "../types";

type Props = { metrics: Metrics; activities: Activity[]; event: EventSettings | null };

function ActivityChart({ activities }: { activities: Activity[] }) {
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setDate(date.getDate() - (6 - index));
    return date;
  });
  const values = days.map((day) => activities.filter((activity) => new Date(activity.created_at).toDateString() === day.toDateString()).length);
  const maximum = Math.max(...values, 1);
  const points = values.map((value, index) => `${index * (600 / 6)},${150 - (value / maximum) * 120}`).join(" ");

  return (
    <div className="chart-wrap">
      <svg viewBox="0 0 600 170" role="img" aria-label="Atividades dos últimos sete dias">
        <defs><linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#62e6b6" stopOpacity=".35" /><stop offset="1" stopColor="#62e6b6" stopOpacity="0" /></linearGradient></defs>
        <polyline className="chart-area" points={`0,150 ${points} 600,150`} />
        <polyline className="chart-line" points={points} />
        {values.map((value, index) => <circle key={index} cx={index * (600 / 6)} cy={150 - (value / maximum) * 120} r="4" />)}
      </svg>
      <div className="chart-labels">{days.map((day) => <span key={day.toISOString()}>{day.toLocaleDateString("pt-BR", { weekday: "short" })}</span>)}</div>
    </div>
  );
}

export default function OverviewView({ metrics, activities, event }: Props) {
  const cards = [
    ["Participantes", metrics.total_leads],
    ["Confirmados", metrics.confirmed],
    ["Presentes", metrics.attended],
    ["Comparecimento", `${Math.round(metrics.attendance_rate * 100)}%`],
    ["Reuniões", metrics.meetings_booked],
    ["E-mails enviados", metrics.messages_sent],
  ];
  return (
    <>
      <section className="page-heading">
        <div><span className="section-kicker">Operação em tempo real</span><h1>Visão geral</h1><p>Acompanhe o funil, a comunicação e a conversão do evento.</p></div>
        <div className="agent-chip"><span className="status-dot" /> Agente ativo</div>
      </section>
      <section className="metric-grid">
        {cards.map(([label, value]) => <article className="metric-card" key={label}><span>{label}</span><strong>{value}</strong><small>Atualizado automaticamente</small></article>)}
      </section>
      <section className="overview-grid">
        <article className="panel chart-panel">
          <div className="panel-header"><div><span className="section-kicker">Últimos 7 dias</span><h2>Atividade do funil</h2></div><span className="panel-badge">{activities.length} eventos</span></div>
          <ActivityChart activities={activities} />
        </article>
        <article className="panel event-summary">
          <span className="section-kicker">Próximo evento</span>
          <h2>{event?.name ?? "Carregando evento"}</h2>
          {event && <><div className="event-detail"><span>Data</span><strong>{new Date(event.starts_at).toLocaleString("pt-BR")}</strong></div><div className="event-detail"><span>Local</span><strong>{event.location}</strong></div><div className="event-detail"><span>Cadência</span><strong>{event.message_interval_hours}h entre e-mails</strong></div><div className="event-detail"><span>Horários comerciais</span><strong>{event.meeting_slots.length} disponíveis</strong></div></>}
        </article>
      </section>
    </>
  );
}

