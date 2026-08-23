# testes/e2e/ — a suíte que roda contra o sistema vivo, pelo gateway

Estes testes **não** são a suíte do Django. A de `backend/` prova o código contra um banco de teste
que ela mesma cria e destrói; esta prova o **produto montado**: containers de pé, nginx roteando,
JWT assinado de verdade, RLS ligada, entitlement de plano valendo. É a diferença entre "a view
devolve 403" e "o tenant que não assina `maps` leva 403 atravessando o gateway com um token real" —
e foi essa segunda pergunta que achou o [D31](../../docs/historico-correcoes.md) (nenhum tenant
assinava `maps` no stack vivo, e o módulo estava inalcançável sem ninguém notar).

## Por que não vivem mais em `infra/`

Moraram em `infra/gateway/` até 16/08/2026, ao lado dos `nginx.conf`, por terem nascido junto com o
gateway. Ficou errado quando cresceram: `infra/` é **como o sistema sobe** — compose, nginx, init do
Postgres, chaves, proxies. Teste não sobe nada; ele interroga o que já subiu. A pasta virou gaveta e
foi a primeira coisa que se procurou quando se quis saber o que ali era infraestrutura de verdade.

Em `infra/gateway/` ficou só o que é infraestrutura: os três `nginx*.conf` e o
`docker-compose.gateway.yml`.

## Como rodar

O stack precisa estar de pé (ver [desenvolvimento.md](../../docs/desenvolvimento.md)). Os testes
falam com o gateway em `:8090` e, alguns, direto com os serviços:

```sh
.venv/bin/python testes/e2e/phase8_tenancy_test.py
.venv/bin/python testes/e2e/pra8_prancheta_test.py
bash testes/e2e/d11_recuperacao_senha_test.sh
```

Os que abrem navegador (`*_browser_test.py`, `browser_smoke_test.py`) exigem o Playwright do `.venv`
da raiz e o frontend servido — em geral `:5173` no modo de desenvolvimento.

## O que é teste e o que é apoio

| Arquivo | Papel |
|---|---|
| `phase*_test.py`, `phase4_e2e.py` | As fases da plataforma: RS256, RBAC, tenancy, auditoria, WebSocket de serviço |
| `pra*_test.py` | Prancheta ponta a ponta — escala, hachura, upload de acervo, o módulo pelo gateway |
| `map6_maps_test.py`, `orc6_orcamento_test.py`, `orc8_carga_base_test.py`, `ie_impexp_test.py`, `d70_*`, `d23_*`, `phaseC_*` | Um módulo ou um achado específico, no stack vivo |
| `amostras_pra8.py` | **Apoio**: os bytes de amostra (DWG, DXF, PDF, RVT) que o `pra8` usa — importado como módulo irmão |
| `d11_mailpit_helper.py` | **Apoio**: lê o Mailpit para conferir e-mail de verdade |
| `carregar_acervo_dwg.py` | **Apoio**: sobe um acervo de DWG pelo caminho de produção |

Apoio não é teste: não tem asserção e não deve ser executado sozinho esperando um veredito.
