# Observabilidade (Fase 10.1) — runbook

Instrumentação transversal da plataforma: **logs estruturados** correlacionados,
**métricas** de latência/erro e **sondas de saúde**. Objetivo: diagnosticar um
incidente multi-serviço (11 serviços, 3 stacks) a partir de um único
`request_id`.

> **Nomenclatura:** "**backend**" é o serviço Django em [`backend/`](../../backend/)
> (resource server da IAM). O identificador literal do container/scrape/label é
> `erp` (código, não renomeado aqui). "ERP" sozinho designa o **módulo** de
> negócio [`moduloerp/`](../../backend/moduloerp/) (financeiro).

## O que existe

| Eixo | Onde | Detalhe |
| --- | --- | --- |
| `request_id` na borda | `infra/gateway/nginx.unified.conf` | Gera (ou honra) `X-Request-ID`, propaga aos upstreams e devolve ao cliente; loga em JSON no stdout. |
| Logs JSON + correlação | `backend/nucleo/observability.py`, `iam/identity/observability.py` | Uma linha JSON por evento com `request_id`/`tenant_id`; `LOG_FORMAT=text` volta ao formato humano de dev. |
| Log de acesso | `*/middleware.py` (`ObservabilityMiddleware`) | Método, rota, status, `duration_ms` por requisição; 5xx sai em nível ERROR. |
| Métricas Prometheus | `GET /metrics` (backend `erp:8000`, IAM `:8001`) | `sgi_http_requests_total{service,method,view,status}` e `sgi_http_request_duration_seconds`. |
| Liveness | `GET /healthz` | Sempre 200 se o processo atende; **sem I/O** (um banco fora não reinicia o container). |
| Readiness | `GET /readyz` | Sonda banco + cache + broker (backend) / banco + Redis (IAM); **503** se algo cair → sai do balanceamento. |

`/healthz`, `/readyz` e `/metrics` **não são roteados pelo gateway** — só
alcançáveis dentro da rede `sgi` (Docker healthcheck e Prometheus).

## Subir o Prometheus

```bash
docker compose --profile full --profile observability up -d
# UI: http://localhost:9090  (Status → Targets deve mostrar erp e iam "UP")
```

Config de scrape: [`prometheus.yml`](prometheus.yml). Retenção 15 dias (dev).

## Correlacionar um incidente

1. O cliente/suporte informa o `X-Request-ID` da resposta (header).
2. Filtre os logs por ele: `docker compose logs gateway erp iam | grep <request_id>`
   (ou, com coletor, `request_id="<id>"`). A linha da borda tem status/latência
   totais; as do backend/IAM têm a rota e o `tenant_id`.

## Consultas úteis (PromQL)

```promql
# Taxa de erro 5xx por serviço (5 min)
sum by (service) (rate(sgi_http_requests_total{status=~"5.."}[5m]))
  / sum by (service) (rate(sgi_http_requests_total[5m]))

# Latência p95 por rota (5 min)
histogram_quantile(0.95,
  sum by (le, view) (rate(sgi_http_request_duration_seconds_bucket[5m])))
```

## Notas de operação

- **Gunicorn multi-worker:** com mais de 1 worker, as métricas por processo
  divergem. Setar `PROMETHEUS_MULTIPROC_DIR` (dir gravável, um por container) e o
  `render_latest_metrics()` já agrega via `MultiProcessCollector`. O compose atual
  roda 1 worker (default), então não é necessário.
- **`prometheus-client` ausente:** o app sobe mesmo assim (import tolerante);
  `/metrics` responde um comentário e as métricas ficam desligadas até
  `pip install`.
- **Logs:** JSON por padrão fora de DEBUG (`LOG_FORMAT`), nível via `LOG_LEVEL`.

## Próximos passos (10.1 → DoD da Fase 10)

- **Grafana** com dashboard mínimo (taxa de erro + latência p95 por serviço/rota).
- **Alertas** (regras Prometheus + Alertmanager): 5xx sustentado e p95 alto.
- **Paridade das outras stacks:** `/metrics` + `/healthz` no Java do drone e nos
  serviços Node (estes últimos são absorvidos na Fase 11 — instrumentar ao portar).
- **Tracing pelo gateway** (opcional, item 10.1).
