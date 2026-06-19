# Vigil Summit Agent

MVP do desafio técnico para gerenciar o funil do Vigil Summit, da captação do lead ao agendamento de uma reunião comercial.

## Estrutura

```text
backend/                  API FastAPI, automação e banco SQLite
frontend/                 Dashboard e página do participante em React/Vite
docs/TECHNICAL_DOCUMENTATION.md Documento técnico completo exigido pelo desafio
docs/SECURITY.md          Controles e riscos residuais de segurança
```

Backend e frontend ficam separados no mesmo repositório. Não há Docker, workflow de CI/CD ou infraestrutura de produção porque a entrega será feita diretamente pelo GitHub para avaliação.

## Funcionalidades

- Cadastro e inscrição de leads no evento.
- Consentimento, opt-out e exclusão LGPD.
- Enriquecimento real pelo website do domínio corporativo, sem inventar dados quando a fonte não é encontrada.
- Site e LinkedIn opcionais no cadastro, com atualização manual da fonte pela lista de participantes.
- Formulário público compartilhável para inscrições em escala.
- Agenda administrativa com exclusão de reunião e devolução automática do horário.
- Edição completa do participante, comprovante imprimível e convite compartilhável.
- Reunião confirmada pela administração com link da chamada e aviso por e-mail.
- Personalização com Gemini ou templates fake.
- Envio por Resend ou caixa de saída fake.
- Worker verifica o funil a cada 30 segundos, respeitando o intervalo configurado entre e-mails.
- Regras temporais D-14, D-3 e D-1 fora do modo de demonstração.
- Link individual para o participante confirmar, recusar ou demonstrar interesse.
- Abertura registrada automaticamente quando o link é acessado.
- Check-in/no-show registrado pela equipe no dashboard.
- Escolha de horário pelo participante.
- Histórico, métricas e prevenção de mensagens duplicadas.
- Dashboard atualizado automaticamente a cada 5 segundos.
- Navegação para visão geral, participantes, histórico e configurações.
- Modal de cadastro, inbox de mensagens, estados de loading e gráfico de atividade.
- Configuração administrativa da data, local, cadência e horários comerciais.
- Diagnóstico dos providers, modo de execução e estado da automação.

## Executar localmente

### Backend

```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

API: `http://localhost:8000`  
Swagger: `http://localhost:8000/docs`

### Frontend

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Dashboard: `http://localhost:5173`

## Configuração

Copie `backend/.env.example` para `backend/.env` e preencha as credenciais:

```env
DATABASE_URL=sqlite:///./vigil.db
FRONTEND_URL=http://localhost:5173
ALLOWED_HOSTS=localhost,127.0.0.1

LLM_PROVIDER=gemini
GEMINI_API_KEY=sua_chave
LLM_MODEL=gemini-2.5-flash

EMAIL_PROVIDER=resend
RESEND_API_KEY=sua_chave
EMAIL_FROM="Vigil Summit <no-reply@seudominio.com>"

ENRICHMENT_PROVIDER=public_web
ENRICHMENT_SEARCH_ENABLED=true

AUTOMATION_ENABLED=true
AUTOMATION_INTERVAL_SECONDS=30
DEMO_MODE=true
DEFAULT_MESSAGE_INTERVAL_HOURS=24
DATA_RETENTION_DAYS=365

AUTH_ENABLED=true
ADMIN_EMAIL=ramon@pareto.io
ADMIN_PASSWORD=ramon@2026
AUTH_SECRET=troque-por-uma-chave-longa-e-aleatoria
```

`ADMIN_PASSWORD` deve ter pelo menos 10 caracteres e `AUTH_SECRET`, pelo menos 32. Gere um segredo antes da demonstração:

```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Para testar sem APIs externas, use `fake` nos três providers.

O painel administrativo exige login. As credenciais são definidas por `ADMIN_EMAIL` e `ADMIN_PASSWORD`; o token da sessão é válido por oito horas. Troque também `AUTH_SECRET` antes de publicar o repositório.

Com `ENRICHMENT_PROVIDER=public_web`, o sistema consulta o site associado ao domínio do e-mail corporativo. E-mails pessoais ou sites indisponíveis são marcados como “fonte pública não localizada”, sem substituição silenciosa por dados simulados. O provider `fake` é exclusivo para testes e demonstrações.

Quando informado, o campo “Site da empresa” tem prioridade total sobre o domínio do e-mail; portanto, um e-mail pessoal não interfere nessa pesquisa. O sistema analisa a página inicial e tenta também `/sobre` ou `/about`. Setor, porte e sinais só são aceitos com evidência específica, e o setor precisa pertencer à taxonomia controlada. O LinkedIn é uma referência opcional: bloqueios da plataforma não interrompem o restante do enriquecimento.

Com Gemini configurado, o conteúdo público é classificado pelo modelo com instrução explícita para não inventar informações. Se setor e porte continuarem desconhecidos, a confiança é limitada a 35%.

Para envio real pelo Resend, `EMAIL_FROM` precisa usar um remetente autorizado na conta e `RESEND_API_KEY` deve possuir permissão de envio. Para uma demonstração sem entrega externa, use `EMAIL_PROVIDER=fake`.

## Roteiro de demonstração

Para executar uma jornada sintética completa automaticamente:

```powershell
cd backend
.venv\Scripts\python.exe scripts\demo_flow.py
```

1. Cadastre um lead com consentimento.
2. Configure a cadência do evento; use `0.01` hora para uma demonstração rápida ou `24` horas para uso real.
3. Aguarde até 30 segundos para enriquecimento e primeira mensagem.
4. Abra o link individual exibido na inbox ou recebido por e-mail.
5. Confirme presença na página do participante.
6. No dashboard, marque presente ou no-show.
7. Aguarde o follow-up automático.
8. Abra novamente a página do participante e escolha um horário configurado.
9. Confira métricas, gráfico e histórico no dashboard.

Consulte a [documentação técnica da entrega](docs/TECHNICAL_DOCUMENTATION.md) e os [controles de segurança](docs/SECURITY.md).
