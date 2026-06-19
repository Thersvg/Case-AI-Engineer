import { useMemo, useState } from "react";

import type { Enrichment, Lead } from "../types";

type Props = {
  leads: Lead[];
  enrichments: Enrichment[];
  actionLoading: string;
  onAttendance: (leadId: number, status: "attended" | "no_show") => Promise<void>;
  onDelete: (leadId: number) => Promise<void>;
  onEnrich: (lead: Lead) => void;
  onDetails: (lead: Lead) => void;
};

const STATUS_LABELS: Record<string, string> = { registered: "Cadastrado", enriched: "Enriquecido", enrichment_unavailable: "Dados não encontrados", confirmed: "Confirmado", declined: "Recusado", attended: "Presente", no_show: "Ausente", meeting_booked: "Reunião agendada" };

export default function LeadsView({ leads, enrichments, actionLoading, onAttendance, onDelete, onEnrich, onDetails }: Props) {
  const [search, setSearch] = useState("");
  const enrichmentMap = useMemo(() => new Map(enrichments.map((item) => [item.lead_id, item])), [enrichments]);
  const filtered = leads.filter((lead) => `${lead.name} ${lead.email} ${lead.company ?? ""}`.toLowerCase().includes(search.toLowerCase()));
  return <><section className="page-heading"><div><span className="section-kicker">Base do evento</span><h1>Participantes</h1><p>Dados cadastrais, evidências públicas, qualificação e estágio do funil.</p></div><input className="search-input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar participante..." /></section><section className="panel table-panel"><div className="table-wrap"><table><thead><tr><th>Participante</th><th>Empresa</th><th>Enriquecimento</th><th>Qualificação</th><th>Status</th><th>Cadastro</th><th>Ação</th></tr></thead><tbody>{filtered.map((lead) => {
    const enrichment = enrichmentMap.get(lead.id);
    const loading = actionLoading === `attendance-${lead.id}`;
    return <tr key={lead.id}><td><strong>{lead.name}</strong><small>{lead.email}</small></td><td>{lead.company || "Não informada"}<small>{lead.role || "Cargo não informado"}</small>{enrichment && <small title={enrichment.role_validation}>{enrichment.role_validation}</small>}</td><td>{enrichment ? <><span>{enrichment.sector}</span><small>{enrichment.company_size} · {Math.round(enrichment.confidence * 100)}%</small><small>{enrichment.source.startsWith("http") ? "Fonte pública verificada" : enrichment.source.startsWith("demo:") ? "Dados de demonstração" : "Fonte pública não localizada"}</small><small>{enrichment.professional_presence !== "Não localizada" ? "Presença profissional informada" : "Presença profissional não localizada"}</small></> : <span className="muted">Aguardando enriquecimento</span>}</td><td>{enrichment ? <><strong>{enrichment.qualification_score}/100</strong><small>{enrichment.qualification_score >= 60 ? "Perfil prioritário" : "Revisão recomendada"}</small></> : "-"}</td><td><span className={`status-pill ${lead.status}`}>{STATUS_LABELS[lead.status] ?? lead.status}</span></td><td>{new Date(lead.created_at).toLocaleDateString("pt-BR")}<small>{new Date(lead.created_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</small></td><td><div className="row-actions"><button className="secondary-button" onClick={() => onDetails(lead)}>Ver detalhes</button><button onClick={() => onEnrich(lead)}>Editar dados</button>{lead.status === "confirmed" && <><button disabled={loading} onClick={() => onAttendance(lead.id, "attended")}>Registrar presença</button><button className="ghost-danger" disabled={loading} onClick={() => onAttendance(lead.id, "no_show")}>Registrar ausência</button></>}<button className="ghost-danger" disabled={actionLoading === `delete-${lead.id}`} onClick={() => onDelete(lead.id)}>{actionLoading === `delete-${lead.id}` ? "Excluindo..." : "Excluir"}</button></div></td></tr>;
  })}</tbody></table></div>{filtered.length === 0 && <div className="empty-state">Nenhum participante encontrado.</div>}</section></>;
}
