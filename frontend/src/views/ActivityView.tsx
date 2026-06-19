import type { Activity } from "../types";

export default function ActivityView({ activities }: { activities: Activity[] }) {
  const labels: Record<string, string> = { lead_created: "Participante cadastrado", lead_enriched: "Participante enriquecido", message_sent: "Mensagem enviada", response_received: "Resposta recebida", attendance_recorded: "Presença registrada", meeting_booked: "Reunião agendada", meeting_cancelled: "Reunião excluída" };
  return (
    <>
      <section className="page-heading"><div><span className="section-kicker">Auditoria</span><h1>Histórico</h1><p>Todas as ações relevantes executadas pelo sistema e pelos participantes.</p></div></section>
      <section className="panel activity-panel">
        {activities.length === 0 && <div className="empty-state">Nenhuma atividade registrada.</div>}
        <div className="timeline">{activities.map((activity) => <article key={activity.id}><span className="timeline-dot" /><div><strong>{activity.description}</strong><p>Participante #{activity.lead_id} · {labels[activity.type] ?? activity.type}</p></div><time>{new Date(activity.created_at).toLocaleString("pt-BR")}</time></article>)}</div>
      </section>
    </>
  );
}
