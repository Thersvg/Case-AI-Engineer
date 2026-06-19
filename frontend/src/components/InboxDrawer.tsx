import type { Message } from "../types";

type Props = { messages: Message[]; retrying: string; onClose: () => void; onRetry: (messageId: number) => Promise<void> };

export default function InboxDrawer({ messages, retrying, onClose, onRetry }: Props) {
  const labels: Record<string, string> = { pending: "Pendente", sent: "Enviado", delivered: "Entregue", failed: "Falhou", cancelled: "Cancelado" };
  const friendlyFailure = (reason?: string) => reason?.includes("403 Forbidden")
    ? "O Resend recusou o envio. Verifique se o remetente usa um domínio validado e se a chave possui permissão de envio."
    : reason;
  return (
    <div className="drawer-backdrop" onMouseDown={onClose}>
      <aside className="inbox-drawer" aria-label="Caixa de entrada" onMouseDown={(event) => event.stopPropagation()}>
        <div className="drawer-header">
          <div><span className="section-kicker">Comunicações</span><h2>Caixa de saída</h2></div>
          <button className="close-button" aria-label="Fechar" onClick={onClose}>×</button>
        </div>
        <div className="inbox-list">
          {messages.length === 0 && <div className="empty-state">Nenhum e-mail gerado até agora.</div>}
          {messages.map((message) => {
            const participantUrl = message.body.match(/https?:\/\/\S+\/participant\?token=\S+/)?.[0];
            return (
              <article className="inbox-item" key={message.id}>
                <div className="inbox-meta"><span className={`status-pill ${message.status}`}>{labels[message.status] ?? message.status}</span><time>{new Date(message.created_at).toLocaleString("pt-BR")}</time></div>
                <strong>{message.subject}</strong>
                <p>{message.body}</p>
                {participantUrl && <a href={participantUrl}>Abrir jornada do participante →</a>}
                {message.failure_reason && <small className="error-text">{friendlyFailure(message.failure_reason)}</small>}
                {message.status === "failed" && <button className="secondary-button retry-button" disabled={retrying === `retry-${message.id}`} onClick={() => onRetry(message.id)}>{retrying === `retry-${message.id}` ? "Tentando novamente..." : "Tentar envio novamente"}</button>}
              </article>
            );
          })}
        </div>
      </aside>
    </div>
  );
}
