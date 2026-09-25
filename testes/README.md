# testes/ — tudo o que prova ou popula o sistema

| Pasta | O que é | Como roda |
|---|---|---|
| [`backend/`](backend/) | Suíte do Django do backend, um pacote por app (`testes.backend.<app>`) | `cd backend && python manage.py test` |
| [`iam/`](iam/) | Suíte do Django da IAM: `identity` + o pacote compartilhado `funcoesemail` | `cd iam && python manage.py test` |
| [`e2e/`](e2e/README.md) | Roteiros contra o sistema **vivo**, pelo gateway (API e navegador) | `python3 testes/e2e/<roteiro>.py` |
| [`seeds/`](seeds/) | Dados de demonstração: `seed_demo.py` (IAM), `seed_demo_data.py` (backend), `seed_staging.sh` (os dois no staging) | `docker compose exec -T iam python manage.py shell < testes/seeds/seed_demo.py` |

## Por que fora dos apps

Os testes não vão para a imagem de produção (`.dockerignore`), e ficam num lugar só. O preço é que o
Django não os acha sozinho: quem resolve é o `TEST_RUNNER` de cada serviço
([backend](../backend/nucleo/test_runner.py), [IAM](../iam/iam_project/runner_testes.py)).

- **Sem rótulo**, descobre `testes/<serviço>/` inteiro.
- **Rótulo de app** continua valendo: `manage.py test moduloorcamento` ou
  `manage.py test nucleo.test_quotas` viram `testes.backend.<...>`.
- `testes/` é procurada ao lado do `BASE_DIR` (clone) ou dentro dele (cópia em contêiner). Se não
  achar, o runner **falha** — nunca roda 0 testes e diz OK.

Rodar dentro de um contêiner exige copiar a pasta antes, já que a imagem não a carrega:

```bash
docker exec sgi-erp mkdir -p /app/testes && docker cp testes/. sgi-erp:/app/testes/
docker exec sgi-erp python manage.py test --noinput
```

## Regras de um teste novo

- Mora em `testes/<serviço>/<app>/test_<assunto>.py`; o diretório do app precisa de `__init__.py`.
- Importa o código pelo caminho absoluto (`from moduloorcamento.models import …`) — `from .models`
  apontaria para o pacote de teste. Import relativo só entre módulos de teste (`from .tests import …`).
- Caminho da árvore do código vem de `settings.BASE_DIR`, nunca de `__file__`.
