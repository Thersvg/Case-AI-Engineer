import { FormEvent, useState } from "react";

type Props = {
  loading: boolean;
  onClose: () => void;
  onSubmit: (payload: Record<string, FormDataEntryValue | boolean>) => Promise<void>;
  shareUrl?: string;
};

export default function LeadModal({ loading, onClose, onSubmit, shareUrl }: Props) {
  const [copied, setCopied] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSubmit({
      name: form.get("name") ?? "",
      email: form.get("email") ?? "",
      company: form.get("company") ?? "",
      role: form.get("role") ?? "",
      company_website: form.get("company_website") ?? "",
      linkedin_url: form.get("linkedin_url") ?? "",
      consent_email: form.get("consent_email") === "on",
    });
  }

  async function copyLink() {
    if (!shareUrl) return;
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="lead-modal-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div><span className="section-kicker">Novo contato</span><h2 id="lead-modal-title">Cadastrar participante</h2></div>
          <div className="modal-header-actions">{shareUrl && <button className="share-link-button" type="button" onClick={copyLink}>{copied ? "Link copiado" : "Compartilhar formulário"}</button>}<button className="close-button" aria-label="Fechar" onClick={onClose}>×</button></div>
        </div>
        <form className="modal-form" onSubmit={submit}>
          <label>Nome completo<input name="name" placeholder="Ex.: Ana Souza" required minLength={2} /></label>
          <label>E-mail corporativo<input name="email" placeholder="ana@empresa.com" type="email" required /></label>
          <div className="form-row">
            <label>Empresa<input name="company" placeholder="Empresa" required /></label>
            <label>Cargo<input name="role" placeholder="CISO, CTO..." required /></label>
          </div>
          <label>Site da empresa<input name="company_website" type="url" placeholder="https://empresa.com.br" required /></label>
          <label>LinkedIn da empresa ou participante (opcional)<input name="linkedin_url" type="url" placeholder="https://www.linkedin.com/company/empresa" /></label>
          <label className="checkbox-label"><input name="consent_email" type="checkbox" required /> Autorizou comunicações sobre o evento por e-mail.</label>
          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={onClose}>Cancelar</button>
            <button className="primary-button" type="submit" disabled={loading}>{loading ? "Cadastrando..." : "Cadastrar participante"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}
