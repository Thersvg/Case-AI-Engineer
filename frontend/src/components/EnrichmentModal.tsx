import { FormEvent } from "react";

import type { Lead } from "../types";

type Props = { lead: Lead; loading: boolean; onClose: () => void; onSubmit: (leadId: number, payload: object) => Promise<void> };

export default function EnrichmentModal({ lead, loading, onClose, onSubmit }: Props) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSubmit(lead.id, {
      name: form.get("name"), email: form.get("email"), company: form.get("company"), role: form.get("role"),
      company_website: form.get("company_website") || null, linkedin_url: form.get("linkedin_url") || null,
    });
  }

  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="edit-lead-title" onMouseDown={(event) => event.stopPropagation()}><div className="modal-header"><div><span className="section-kicker">Participante</span><h2 id="edit-lead-title">Editar dados</h2><p>Ao salvar, o enriquecimento será processado novamente.</p></div><button className="close-button" aria-label="Fechar" onClick={onClose}>×</button></div><form className="modal-form" onSubmit={submit}><label>Nome completo<input name="name" defaultValue={lead.name} required /></label><label>E-mail corporativo<input name="email" type="email" defaultValue={lead.email} required /></label><div className="form-row"><label>Empresa<input name="company" defaultValue={lead.company} required /></label><label>Cargo<input name="role" defaultValue={lead.role} required /></label></div><label>Site da empresa<input name="company_website" type="url" defaultValue={lead.company_website} required /></label><label>LinkedIn (opcional)<input name="linkedin_url" type="url" defaultValue={lead.linkedin_url} /></label><p className="field-help">O consentimento do participante não é alterado por esta edição.</p><div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Cancelar</button><button className="primary-button" disabled={loading}>{loading ? "Salvando..." : "Salvar e atualizar"}</button></div></form></section></div>;
}
