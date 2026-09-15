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
| `pdca1_cronograma_test.py` | PDCA ponta a ponta — WBS, rede, CPM sobre o calendário da obra, arrastar, publicar, replanejar e a linha de base |
| `pdca3_medicao_test.py` | PDCA.3 — contrato, medição nascendo do avanço, trava do contratado, escada de atesto (quem apura não ateste) e o **título gerado no ERP**; retenção retida e liberada em título próprio |
| `pdca4_aditivo_test.py` | PDCA.4 — o `contexto/` da medição (a rede do **D138**: acumulado nunca negativo, saldo nunca acima do contratado), deduções tipadas entre a retenção e o líquido, material estocado pagando a **diferença**, aditivo com escada própria abrindo saldo, e as travas de supressão abaixo do já medido e de período sobreposto |
| `pdca3_grade_browser_test.py` | PDCA.3 no **navegador** — o caminho de dedo até a carteira, as colunas da grade e a **trava acendendo na digitação** (a única parte do instrumento que não dá para provar por API). Pede `LD_LIBRARY_PATH=~/.local/chromium-libs` |
| `pdca3_formulario_browser_test.py` | Os seis achados do "+ novo contrato" (D132): valor em real, zero à esquerda, select de fornecedores, rodapé em **janela baixa (620 px)**, a planilha contratual e a seleção ao focar. Pede `LD_LIBRARY_PATH` |
| `aprovacoes_admin_browser_test.py` | Administração → Aprovações (D130) — a escada na tela, e o **autoatesto ligado pela tela e conferido na API**. Pede `LD_LIBRARY_PATH` |
| `map6_maps_test.py`, `orc6_orcamento_test.py`, `orc8_carga_base_test.py`, `ie_impexp_test.py`, `d70_*`, `d23_*`, `phaseC_*` | Um módulo ou um achado específico, no stack vivo |
| `amostras_pra8.py` | **Apoio**: os bytes de amostra (DWG, DXF, PDF, RVT) que o `pra8` usa — importado como módulo irmão |
| `d11_mailpit_helper.py` | **Apoio**: lê o Mailpit para conferir e-mail de verdade |
| `carregar_acervo_dwg.py` | **Apoio**: sobe um acervo de DWG pelo caminho de produção |

Apoio não é teste: não tem asserção e não deve ser executado sozinho esperando um veredito.
