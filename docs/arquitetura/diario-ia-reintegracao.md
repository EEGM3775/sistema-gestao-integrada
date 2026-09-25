# Reintegração do Diário de Obra + IA (plano)

> Plano de reintegração do canal **WhatsApp → IA → Diário** no v02, com o novo modelo de
> **diário do dia compartilhado**. Ver o módulo em [../modulos/modulodiario.md](../modulos/modulodiario.md).

## Decisões (fixadas com o cliente)

- **1 diário por obra por dia**, compartilhado; cada contribuição registra **quem** a fez.
- **Web** cria texto **e** foto, seguindo a regra do dia e disparando a IA.
- **Contribuir** = funcionário na equipe ∪ responsáveis técnicos. **Moderar** (editar/excluir) = responsável técnico.
- **Linguagem**: Python (Django + Celery). Coerente com o [CLAUDE.md](../../CLAUDE.md) e a Fase 11
  (eliminar Node do backend). A LLM de visão é um serviço Python à parte.
- **Provedor de IA**: LLM **local** (em desenvolvimento pelo cliente). O contrato JSON abaixo é o alvo;
  pode ser ajustado quando a LLM ficar pronta.

## Contrato do `resultado_analise` (alvo)

```json
{
  "tipo_analise": "completa",
  "resumo": "string",
  "progresso": { "percentual": 0, "observacao": "" },
  "seguranca": { "epi_ok": true, "riscos": [{ "descricao": "", "severidade": "baixa|media|alta" }] },
  "qualidade": { "itens": [{ "descricao": "", "status": "ok|atencao|reprovado" }] },
  "itens_detectados": ["..."],
  "alertas": ["string"],
  "confianca": 0.0
}
```

O `AnaliseModal` do frontend renderiza esse JSON; hoje de forma genérica, e um card estruturado quando o
contrato estabilizar.

## Fases

### Fase A — Modelo do dia + web ✅ (06/06/2026)

- Modelos: `DiarioObra` (container do dia), `EntradaDiario` (contribuição com autor), `DocumentoDiario`
  (+`autor`, +`origem`). Migration `0003`.
- Permissões `pode_contribuir` / `pode_moderar`; 403 verdadeiro quando falta `funcionario_profile`.
- Endpoint **`contribuir`** (get-or-create do dia) e `today` por (obra, data).
- Web: form de contribuição (texto + foto + clima + ocorrência), timeline do dia com autoria, moderação
  para responsável técnico. IA fica "pendente" até a Fase B.

### Fase B — Pipeline de IA ✅ (14/07/2026, backend)

- **Worker Celery** no `docker-compose.yml` já provido (A1/Fase 10.9).
- `funcoesia` **reescrito em Python**: task `funcoesia.tasks.analisar_documento_ia` (base `DLQTask`) lê a
  imagem do `DocumentoDiario` **in-process** (FileField local, sem download HTTP), chama a LLM local via
  `funcoesia.llm_client` e grava `AnaliseImagemIA` no tenant correto (`rls_bypass` p/ achar o tenant →
  `tenant_context` p/ gravar). Indisponibilidade → retry+DLQ; resposta malformada → `erro`. Os proxies FBV
  (`iniciar`/`reprocessar`/`tipos`/`recomendacoes`) e o `modulodiario` deixaram de chamar o Node (fecha a
  parte de IA do **D1**). Suíte `testes/backend/funcoesia/tests.py` 6/6 sobre Postgres.
- **Pendente:** serviço da **LLM local** (Python/FastAPI) no compose — contrato HTTP `LLM_VISION_URL`
  (entra imagem+tipo, sai o JSON acima); sem a URL a análise fica `erro` sem travar o diário.

### Fase C — Canal WhatsApp em Python 📋

- `funcoeswhatsapp` reescrito como webhook Django + Celery (estado da conversa em Redis).
- Identificação por **telefone** (filtro `/funcionarios/?telefone=` já existe e normaliza número).
- **Auth**: a borda usa a **assinatura HMAC da Meta**; a escrita roda **in-process** (padrão da Fase B,
  sem auto-HTTP), com autoria via telefone→funcionário. O **JWT de serviço da Fase 10.8** fica como plano
  B caso o canal seja mantido como processo separado — ver o refinamento no plano detalhado.

> **Plano detalhado (desenho + fases C.0–C.5 + decisões):**
> [../modulos/funcoeswhatsapp.md](../modulos/funcoeswhatsapp.md) — o canal WhatsApp é a **comunicação do
> SaaS** (o diário é um dos seus fluxos). Esta seção é só o lugar dele na sequência A→B→C.

## Sequência

```
Fase A (feito) ─► Fase B (worker + LLM) ─► Fase C (WhatsApp Python + auth de serviço)
```

Cada fase fecha com um E2E no padrão dos `phaseN_*` em [../../infra/gateway/](../../infra/gateway/).
