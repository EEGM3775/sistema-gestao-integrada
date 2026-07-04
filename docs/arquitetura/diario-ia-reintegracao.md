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

### Fase B — Pipeline de IA 📋

- **Worker Celery** no `docker-compose.yml` (mesma imagem do ERP, `command: celery -A ... worker`).
- `funcoesia` reescrito em **Python** (task Celery) chamando a **LLM local** (HTTP) e gravando `AnaliseImagemIA`.
- Serviço da **LLM local** (Python/FastAPI) no compose quando pronto; contrato HTTP: entra imagem+tipo,
  sai o JSON acima.

### Fase C — Canal WhatsApp em Python 📋

- `funcoeswhatsapp` reescrito como webhook Django + Celery (estado da conversa em Redis).
- Identificação por **telefone** (filtro `/funcionarios/?telefone=` já existe e normaliza número).
- **Auth serviço→serviço**: IAM emite **JWT de serviço de vida curta** (Fase 10.8). O webhook chama o
  ERP com esse JWT; a **autoria** vem do telefone→funcionário. Substitui a `TokenAuth` legada da v01.

## Sequência

```
Fase A (feito) ─► Fase B (worker + LLM) ─► Fase C (WhatsApp Python + auth de serviço)
```

Cada fase fecha com um E2E no padrão dos `phaseN_*` em [../../infra/gateway/](../../infra/gateway/).
