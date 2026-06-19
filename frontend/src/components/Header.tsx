import type { ViewName } from "../types";

type Props = {
  activeView: ViewName;
  notificationCount: number;
  lastUpdated: Date | null;
  onNavigate: (view: ViewName) => void;
  onAddLead: () => void;
  onOpenInbox: () => void;
  onLogout: () => void;
};

const NAV_ITEMS: Array<{ id: ViewName; label: string }> = [
  { id: "overview", label: "Visão geral" },
  { id: "leads", label: "Participantes" },
  { id: "meetings", label: "Reuniões" },
  { id: "activity", label: "Histórico" },
  { id: "settings", label: "Evento" },
];

export default function Header({ activeView, notificationCount, lastUpdated, onNavigate, onAddLead, onOpenInbox, onLogout }: Props) {
  return (
    <header className="app-header">
      <div className="brand">
        <span className="brand-mark">V</span>
        <div><strong>Vigil Summit</strong><small>Gestão inteligente de eventos</small></div>
      </div>
      <nav aria-label="Navegação principal">
        {NAV_ITEMS.map((item) => (
          <button className={activeView === item.id ? "nav-item active" : "nav-item"} key={item.id} onClick={() => onNavigate(item.id)}>
            {item.label}
          </button>
        ))}
      </nav>
      <div className="header-actions">
        <small className="sync-label">{lastUpdated ? `Atualizado ${lastUpdated.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}` : "Sincronizando"}</small>
        <button className="icon-button" aria-label="Abrir caixa de entrada" onClick={onOpenInbox}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg>
          {notificationCount > 0 && <span className="notification-badge">{notificationCount}</span>}
        </button>
        <button className="primary-button" onClick={onAddLead}>+ Participante</button>
        <button className="icon-button logout-button" aria-label="Sair do sistema" title="Sair" onClick={onLogout}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 17l5-5-5-5M15 12H3M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" /></svg></button>
      </div>
    </header>
  );
}
