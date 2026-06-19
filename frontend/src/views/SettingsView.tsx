import { FormEvent, useEffect, useState } from "react";

import type { EventSettings } from "../types";

type Props = { event: EventSettings | null; loading: boolean; deleting: boolean; onSave: (payload: object) => Promise<void>; onDelete: () => Promise<void> };

function toLocalInput(value: string) {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export default function SettingsView({ event, loading, deleting, onSave, onDelete }: Props) {
  const [slots, setSlots] = useState<string[]>([]);
  const slotSignature = event?.meeting_slots.map((slot) => slot.starts_at).join("|") ?? "";
  useEffect(() => setSlots(event?.meeting_slots.map((slot) => toLocalInput(slot.starts_at)) ?? []), [event?.id, slotSignature]);
  if (!event) return <div className="loading-state">Carregando configurações...</div>;

  async function submit(formEvent: FormEvent<HTMLFormElement>) {
    formEvent.preventDefault();
    const form = new FormData(formEvent.currentTarget);
    await onSave({
      name: form.get("name"),
      starts_at: new Date(String(form.get("starts_at"))).toISOString(),
      location: form.get("location"),
      message_interval_hours: Number(form.get("message_interval_hours")),
      meeting_slots: slots.filter(Boolean).map((slot) => new Date(slot).toISOString()),
    });
  }

  return (
    <>
      <section className="page-heading"><div><span className="section-kicker">Administração</span><h1>Configurações do evento</h1><p>Controle data, local, intervalo de comunicação e agenda comercial.</p></div></section>
      <form className="settings-grid" onSubmit={submit}>
        <section className="panel settings-card"><div className="panel-header"><div><span className="section-kicker">Informações</span><h2>Evento</h2></div></div><label>Nome do evento<input name="name" defaultValue={event.name} required /></label><label>Data e horário<input name="starts_at" type="datetime-local" defaultValue={toLocalInput(event.starts_at)} required /></label><label>Local<input name="location" defaultValue={event.location} required /></label></section>
        <section className="panel settings-card"><div className="panel-header"><div><span className="section-kicker">Comunicação</span><h2>Cadência</h2></div></div><label>Intervalo mínimo entre e-mails<input name="message_interval_hours" type="number" min="0" max="720" step="0.5" defaultValue={event.message_interval_hours} required /></label><p className="field-help">Use 24 horas para dar um dia ao participante. O sistema verifica automaticamente quando é o momento do próximo contato.</p></section>
        <section className="panel settings-card slots-card"><div className="panel-header"><div><span className="section-kicker">Comercial</span><h2>Horários para reunião</h2></div><button type="button" className="secondary-button" onClick={() => setSlots([...slots, ""])}>+ Horário</button></div><div className="slot-list">{slots.map((slot, index) => <div className="slot-row" key={index}><input aria-label={`Horário ${index + 1}`} type="datetime-local" value={slot} onChange={(changeEvent) => setSlots(slots.map((item, itemIndex) => itemIndex === index ? changeEvent.target.value : item))} /><button type="button" className="remove-button" onClick={() => setSlots(slots.filter((_, itemIndex) => itemIndex !== index))}>Remover</button></div>)}</div>{slots.length === 0 && <div className="empty-state">Adicione pelo menos um horário para habilitar o agendamento.</div>}</section>
        <div className="settings-actions"><button type="button" className="danger-button" disabled={deleting} onClick={onDelete}>{deleting ? "Excluindo..." : "Excluir evento"}</button><button className="primary-button" disabled={loading}>{loading ? "Salvando..." : "Salvar configurações"}</button></div>
      </form>
    </>
  );
}
