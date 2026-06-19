import { FormEvent, useState } from "react";

import { API_URL, saveToken } from "../api";

type Props = { onLogin: () => void };

export default function LoginPage({ onLogin }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch(`${API_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? "Não foi possível entrar.");
      saveToken(data.access_token);
      onLogin();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao entrar.");
    } finally {
      setLoading(false);
    }
  }

  return <main className="login-page"><section className="login-card"><div className="brand login-brand"><span className="brand-mark">V</span><div><strong>Vigil Summit</strong><small>Gestão inteligente de eventos</small></div></div><span className="section-kicker">Acesso administrativo</span><h1>Bem-vindo</h1><p>Entre para acompanhar participantes, comunicações e reuniões.</p><form className="modal-form" onSubmit={submit}><label>E-mail<input name="email" type="email" autoComplete="username" required /></label><label>Senha<input name="password" type="password" autoComplete="current-password" required /></label>{error && <span className="error-text">{error}</span>}<button className="primary-button" disabled={loading}>{loading ? "Entrando..." : "Entrar"}</button></form></section></main>;
}
