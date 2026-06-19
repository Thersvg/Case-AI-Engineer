# Segurança

## Controles implementados

- Autenticação administrativa por token HMAC com expiração de oito horas.
- Inicialização bloqueada quando senha ou segredo de autenticação são fracos.
- Token administrativo armazenado apenas na sessão do navegador.
- Comparação de credenciais em tempo constante.
- CORS limitado ao frontend configurado, métodos e headers necessários.
- Hosts permitidos configuráveis por `ALLOWED_HOSTS`.
- Rate limit em login, inscrição pública e ações públicas do participante.
- Headers `nosniff`, `DENY`, `no-referrer`, `Permissions-Policy` e `no-store` para APIs.
- CSP no frontend e ausência de renderização de HTML fornecido por usuário.
- ORM e parâmetros tipados, sem SQL construído com entrada externa.
- URLs de reuniões limitadas a HTTPS.
- Proteção SSRF: bloqueio de IPs privados/reservados, portas não web, credenciais em URL, respostas grandes e redirecionamentos excessivos.
- Tokens públicos aleatórios de alta entropia e consentimento verificado antes de envio.
- `.env`, bancos e artefatos locais ignorados pelo Git.

## Configuração obrigatória

Com `AUTH_ENABLED=true`:

- `ADMIN_PASSWORD` deve possuir pelo menos 10 caracteres.
- `AUTH_SECRET` deve possuir pelo menos 32 caracteres aleatórios.
- `ALLOWED_HOSTS` deve listar somente os hosts usados pela aplicação.

Para gerar um segredo:

```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Riscos residuais do MVP

- Desenvolvimento local usa HTTP. Produção exige HTTPS no proxy ou plataforma de hospedagem.
- Rate limit é local ao processo; múltiplas instâncias exigem Redis ou gateway.
- Não há MFA, RBAC ou revogação central de sessões.
- SQLite não possui criptografia em repouso configurada.
- Links individuais usam token na URL e podem aparecer em logs de acesso.
- CSP contém origens de desenvolvimento e deve ser ajustada para o domínio de produção.
- Swagger fica disponível somente em `DEMO_MODE=true`.
- Serviços Gemini, Resend e pesquisa pública permanecem dependências externas.

As chaves que já tenham sido compartilhadas fora do `.env` devem ser revogadas e recriadas antes da entrega.
