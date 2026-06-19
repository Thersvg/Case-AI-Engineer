# Documento técnico — Vigil Summit Agent

Este é o documento principal da entrega do desafio AI Engineer 2026. Ele descreve o que foi construído, como testar, as decisões tomadas e os limites conscientes do MVP.

## 1. Objetivo e aderência

O sistema gerencia o funil do Vigil Summit da inscrição ao agendamento comercial:

1. Captação por formulário público compartilhável ou cadastro administrativo.
2. Enriquecimento com website público, fonte, confiança e evidências.
3. Régua pré-evento para confirmação, lembrete e instruções finais.
4. Registro de presença/no-show e follow-up pós-evento.
5. Escolha de horário, reserva exclusiva e confirmação da reunião.

O agente é testável localmente, usa banco relacional, LLM, comunicação por e-mail, memória persistente e dashboard protegido. O fluxo completo também pode ser demonstrado sem credenciais externas por providers fake.

## 2. Arquitetura

```text
Formulário público ───────┐
Dashboard administrativo ├── React/Vite ── HTTP/JSON ── FastAPI
Página do participante ──┘                         │
                                                   ├── SQLite / SQLModel
                                                   ├── Worker autônomo
                                                   ├── Enriquecimento web + Gemini
                                                   └── Resend / caixa fake
```

Camadas:

- Entrada: formulário público, modal administrativo e página individual por token.
- API: autenticação, validação, regras do funil e endpoints públicos/administrativos.
- Agente: ciclo autônomo que observa o estado, seleciona a próxima ação elegível e executa ferramentas.
- LLM: Gemini Flash para classificação factual e mensagens; templates determinísticos funcionam como fallback.
- Dados: SQLite guarda leads, consentimentos, eventos, enriquecimentos, mensagens, respostas, presenças, reuniões e auditoria.
- Canal: Resend envia e-mail real; provider fake mantém as mensagens demonstráveis na caixa do dashboard.

## 3. Stack e justificativas

| Escolha | Justificativa |
|---|---|
| Python + FastAPI | API pequena, tipada, fácil de testar e adequada ao worker do MVP. |
| SQLModel + SQLite | Modelo relacional auditável e execução sem provisionar infraestrutura. PostgreSQL é a evolução natural de produção. |
| React + Vite + TypeScript | Dashboard rápido, tipado e simples de executar localmente. |
| Gemini Flash | Custo e latência adequados ao MVP. O desafio prefere Claude, mas não o torna obrigatório; o provider é isolado e substituível. |
| API nativa + máquina de estados | Um agente e poucas ferramentas não justificam LangChain/CrewAI/Agno. A solução fica menor e as decisões permanecem auditáveis. |
| Resend/e-mail | Executivos B2B já utilizam e-mail corporativo; é assíncrono, auditável e comporta links de confirmação e agenda. |
| Monorepo | Backend, frontend e documentação versionados juntos, mas com responsabilidades separadas. |

Não há deploy nem CI/CD nesta entrega. O repositório é executado localmente pelo avaliador; Docker e workflow adicionariam manutenção sem atender uma necessidade do desafio. Em produção, a proposta seria frontend estático, API em container, PostgreSQL gerenciado, fila durável e secrets manager.

## 4. Como o agente funciona

O worker acorda no intervalo de `AUTOMATION_INTERVAL_SECONDS`, consulta a memória do banco e executa um ciclo:

1. Enriquece leads ainda não processados.
2. Calcula a etapa de cada participante.
3. Verifica consentimento, data do evento, mensagem anterior e intervalo mínimo.
4. Gera a próxima mensagem elegível com Gemini ou fallback.
5. Envia pelo provider configurado e registra resultado, prompt, modelo e atividade.
6. Executa follow-up após a equipe registrar presença ou no-show.
7. Remove dados expirados conforme a política de retenção.

As decisões críticas são determinísticas. O LLM redige e classifica; ele não pode ignorar consentimento, alterar status arbitrariamente, reservar horário inexistente ou enviar mensagens fora da cadência.

Ferramentas do agente: enriquecimento público, geração de mensagem, envio de e-mail, leitura/gravação da memória e aplicação das réguas.

## 5. Dados, enriquecimento e personalização

O participante informa nome, e-mail, empresa, cargo, website e LinkedIn opcional. O website informado sempre prevalece; o domínio do e-mail só é usado quando nenhum site foi fornecido e o domínio não é pessoal.

O enriquecimento coleta a página inicial e tenta `/sobre` e `/about`. URLs são validadas contra SSRF. O Gemini pode complementar a pesquisa, mas cada setor, porte, cargo ou sinal precisa de evidência específica. Setores são normalizados por uma taxonomia controlada. Sem suporte factual, o campo permanece “Não identificado”.

O LinkedIn é uma referência útil, mas o sistema não acessa nem raspa diretamente o perfil. A URL pode orientar uma pesquisa fundamentada; sem fonte pública suficiente, o cargo continua declarado e não validado. Uma integração oficial de dados profissionais exigiria outro fornecedor ou autorização específica.

O e-mail pessoal não influencia a classificação quando existe website. Por exemplo, “Aeroespacial e defesa” é um setor coerente para uma empresa que publica evidências sobre foguetes, espaçonaves, satélites ou lançamentos; o rótulo só é aceito quando essa evidência existe.

A personalização recebe dados declarados, enriquecimento, abertura anterior, resposta, presença e tema de interesse. Cada mensagem tem um objetivo de etapa explícito e não deve inventar fatos.

## 6. Réguas de comunicação

### Pré-evento

| Momento/condição | Ação |
|---|---|
| Cadastro | Confirma recebimento e apresenta o próximo passo. |
| Até D-14, sem resposta | Solicita confirmação objetiva de presença. |
| Até D-3, confirmado | Reforça relevância e antecipação do conteúdo. |
| Até D-1, confirmado | Envia data, local e instruções de credenciamento. |
| Mensagem anterior não aberta | O contexto informa isso ao gerador para mudar o enfoque. |
| Qualquer etapa | Respeita consentimento, unicidade e intervalo mínimo do evento. |

Exemplo: “Marina, seu cadastro foi recebido. Como CISO de uma empresa do setor financeiro, as discussões sobre priorização de riscos e conformidade serão especialmente relevantes. Confirme sua presença pelo link individual.”

### Pós-evento

| Condição | Ação |
|---|---|
| Presente | Agradece e conecta o interesse registrado ao próximo passo. |
| No-show | Reconhece a ausência sem constranger e oferece conversa contextualizada. |
| Follow-up enviado | Oferece os horários comerciais disponíveis. |
| Horário escolhido | Reserva atomicamente e remove o slot da lista pública. |
| Link da chamada preenchido | Administração envia confirmação com data, horário e acesso. |

Exemplo: “Marina, obrigado por participar. Você demonstrou interesse em conformidade LGPD. Podemos aprofundar como a Vigil.AI prioriza esse tipo de risco em uma conversa de 30 minutos?”

O check-in é manual porque representa um fato presencial. A resposta e a reserva são realizadas diretamente pelo participante em sua página individual.

## 7. Google Meet

O MVP já conclui o requisito de reunião agendada e permite salvar qualquer URL HTTPS da chamada. A geração automática de Google Meet é viável por meio da Google Calendar API: após OAuth do administrador, o backend criaria um evento com conferência, salvaria o link e notificaria o participante.

Ela não foi implementada porque exige projeto no Google Cloud, tela de consentimento, escopos de calendário, callback OAuth, armazenamento seguro e renovação de tokens. Isso aumentaria bastante a configuração do avaliador e não é solicitado pelo desafio. O ponto de extensão já existe no serviço de reuniões; a integração pode substituir o preenchimento manual sem mudar o funil.

## 8. LGPD e segurança

- Consentimento explícito antes de comunicações.
- Opt-out imediato e exclusão administrativa dos dados relacionados.
- Retenção configurável.
- Minimização: apenas dados necessários ao evento e à qualificação B2B.
- Fontes e atividades auditáveis.
- Segredos fora do Git em `.env`.
- Login administrativo, tokens assinados, limitação de tentativas, CORS e cabeçalhos de segurança.
- Proteção SSRF em URLs de enriquecimento e validação HTTPS para reuniões.

A base legal e o prazo definitivo de retenção exigiriam validação jurídica antes de produção. Detalhes técnicos e riscos residuais estão em `docs/SECURITY.md`.

## 9. Três decisões estratégicas e alternativas

1. E-mail em vez de WhatsApp: menor atrito para executivos, melhor auditoria e nenhuma aprovação de template. WhatsApp seria um segundo canal opcional para D-1, mediante consentimento.
2. Máquina de estados em vez de framework multiagente: reduz dependências e torna cada decisão explicável. LangChain, CrewAI e Agno foram considerados, mas não agregam valor suficiente neste fluxo único.
3. Execução local com SQLite em vez de cloud/Docker: maximiza a reprodutibilidade do desafio. PostgreSQL, Redis/fila e containers são adequados quando houver concorrência e operação contínua.

As escolhas seguem padrões consolidados de sistemas de workflow: regras críticas determinísticas, LLM limitado a tarefas probabilísticas, idempotência de mensagens, memória estruturada e fallback para dependências externas.

## 10. Plano dos primeiros cinco dias

1. Definir estados, métricas, consentimento e modelo relacional.
2. Entregar captação e enriquecimento com rastreabilidade.
3. Implementar a régua pré-evento e respostas do participante.
4. Implementar presença, follow-up e agenda comercial.
5. Testar ponta a ponta, tratar falhas externas e finalizar documentação.

A captação e o modelo de dados vêm primeiro porque todas as fases dependem de identidade, consentimento e memória consistentes.

## 11. Escala para dez eventos

O modelo já associa inscrições, agendas, mensagens e reuniões a `event_id`. Para dez eventos simultâneos:

- PostgreSQL substituiria SQLite.
- Uma fila durável distribuiria tarefas particionadas por evento.
- Cadência, público, taxonomia e prompts seriam configurações versionadas por evento.
- Workers seriam horizontalmente escaláveis e idempotentes.
- Métricas e limites seriam segmentados por evento e canal.
- O mesmo núcleo de ferramentas e máquina de estados seria reutilizado.

## 12. Execução e demonstração

Pré-requisitos: Python 3.12 ou superior, Node.js 20 ou superior e npm.

```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Em outro terminal:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Acesse `http://localhost:5173`. Para a primeira demonstração, mantenha `LLM_PROVIDER=fake` e `EMAIL_PROVIDER=fake`. O fluxo completo sintético também pode ser executado com:

```powershell
cd backend
.venv\Scripts\python.exe scripts\demo_flow.py
```

Para integrações reais, configure Gemini e Resend conforme `backend/.env.example`, usando chaves novas e um domínio autorizado no Resend.

Validação:

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm.cmd run build
```

## 13. Limitações conscientes

- LinkedIn não oferece enriquecimento público confiável sem autenticação ou fornecedor autorizado.
- Sites dinâmicos e proteções antirrobô podem reduzir a cobertura.
- Gemini e Resend dependem de disponibilidade e credenciais externas; há fallback demonstrável.
- Google Meet é preenchido manualmente no MVP.
- SQLite e o rate limit em memória são adequados à avaliação local, não a múltiplas instâncias de produção.
