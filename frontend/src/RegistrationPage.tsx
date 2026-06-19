import { FormEvent, useEffect, useState } from "react";

import { API_URL } from "./api";
import type { EventSummary } from "./types";

export default function RegistrationPage() {
  const eventId = new URLSearchParams(window.location.search).get("event");
  const [event, setEvent] = useState<EventSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [completed, setCompleted] = useState(false);

  useEffect(() => {
    if (!eventId) { setError("Link de inscrição inválido."); return; }
    fetch(`${API_URL}/api/public/events/${eventId}`).then(async (response) => {
      if (!response.ok) throw new Error("Evento não encontrado.");
      setEvent(await response.json());
    }).catch((reason) => setError(reason.message));
  }, [eventId]);

  async function submit(formEvent: FormEvent<HTMLFormElement>) {
    formEvent.preventDefault();
    setLoading(true);
    setError("");
    const form = new FormData(formEvent.currentTarget);
    try {
      const response = await fetch(`${API_URL}/api/public/events/${eventId}/register`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: form.get("name"), email: form.get("email"), company: form.get("company"), role: form.get("role"), company_website: form.get("company_website") || null, linkedin_url: form.get("linkedin_url") || null, consent_email: form.get("consent_email") === "on" }) });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(response.status === 409 ? "Este e-mail já está inscrito." : data?.detail ?? "Não foi possível concluir a inscrição.");
      setCompleted(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha na inscrição.");
    } finally { setLoading(false); }
  }

  if (completed) return <main className="public-form-page"><section className="public-form-card success-card"><span className="brand-mark">✓</span><h1>Inscrição concluída</h1><p>Enviaremos as próximas informações pelo e-mail cadastrado.</p></section></main>;
  return <main className="public-form-page"><section className="public-form-card"><div className="brand"><span className="brand-mark">V</span><div><strong>Vigil Summit</strong><small>Inscrição no evento</small></div></div>{event ? <><span className="section-kicker">Inscrição</span><h1>{event.name}</h1><p>{new Date(event.starts_at).toLocaleString("pt-BR")} · {event.location}</p><form className="modal-form" onSubmit={submit}><label>Nome completo<input name="name" required minLength={2} /></label><label>E-mail corporativo<input name="email" type="email" required /></label><div className="form-row"><label>Empresa<input name="company" required /></label><label>Cargo<input name="role" required /></label></div><label>Site da empresa<input name="company_website" type="url" placeholder="https://empresa.com.br" required /></label><label>LinkedIn (opcional)<input name="linkedin_url" type="url" /></label><label className="checkbox-label"><input name="consent_email" type="checkbox" required /> Autorizo comunicações sobre este evento por e-mail.</label>{error && <span className="error-text">{error}</span>}<button className="primary-button" disabled={loading}>{loading ? "Enviando..." : "Confirmar inscrição"}</button></form></> : error ? <div className="error-text">{error}</div> : <div className="loading-state">Carregando evento...</div>}</section></main>;
}
