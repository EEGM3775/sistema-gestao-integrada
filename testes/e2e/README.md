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

## Teste de API não substitui teste de navegador

Lição de 15/09/2026, e ela custou uma tarde ao dono. A PDCA.4 foi entregue com a suíte do Django
verde (1.865), dois E2E de API verdes (69/69 e 55/55) e `tsc`/`vite build` limpos — e o dono clicou
numa medição da lista, a tela **sumiu**, e a aba travou. Três defeitos que **nenhum teste de API
pegaria**, porque nenhum deles está na API:

- o serializer devolvia a lista de deduções como a string `"[]"` (um `str()` num nível só). O JSON
  era **200**; quem quebrava era o `.map` do boletim, e a árvore do React caía inteira;
- o redirecionamento do endereço antigo dependia de um objeto que o React Router recria a cada
  render — `navigate` a cada render, render a cada `navigate`. Em 5 s: 31 requisições;
- a grade de um documento começava na proposta em vez do que estava gravado, então zerar uma linha
  a fazia **voltar sozinha** e ser regravada — num documento que vira título a pagar.

**A régua que fica:** tela nova ou tela reescrita entrega com teste de navegador junto, e ele mede
três coisas que só existem ali — *o conteúdo aparece* (não basta responder 200), *o que se digita
sobrevive ao F5* (é a prova do autosave, e a do "zerei e continua zero"), e **com a tela parada não
pode haver requisição** (é assim que se prova ausência de laço de renderização, sem depender de
alguém notar a aba travando).

O `pdca3_grade_browser_test.py` é o modelo: ele monta o cenário por API — o que se prova é a
**tela** — e anda o caminho de dedo inteiro, do cockpit ao boletim impresso.

## Teste de serviço não substitui teste de porta

A irmã backend da régua acima, e ela custou o mesmo tipo de surpresa no dia seguinte. A PDCA.5 saiu
com 309 testes verdes no módulo e **a primeira requisição real devolveu 500**: os dois viewsets novos
sobrescreviam o `perform_create` do `TenantScopedViewSetMixin` sem repetir o `tenant_id`, a linha
nascia sem tenant e a RLS recusava o INSERT (**D149**). A fatia era inutilizável em produção.

Nenhum dos 309 pegou porque todos montavam os objetos **pelo ORM**, com o tenant na mão, e testavam
o serviço. Nenhum atravessava o viewset. O mesmo cego deixou passar o **D150** (dois cartões da mesma
atividade sem local, porque no Postgres `NULL ≠ NULL`) — que só aparece quando alguém puxa o mesmo
cartão duas vezes, coisa que um teste que monta um objeto por atividade nunca faz.

**A régua que fica:** porta nova se exerce **pela porta**. A classe `ApiDaPdca5Tests` é o modelo —
`APITestCase`, um POST por endpoint de escrita, conferindo o que **ficou gravado**. É barata, roda em
milissegundos e teria pego os dois antes de o E2E existir.

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
| `pdca5_programacao_test.py` | PDCA.5 — o Last Planner com **quatro tokens reais**, porque a fatia move *quem responde pelo quê*: `campo` registra a trava e **não** a remove, `gerente` lê o PPC e **não** assume nem julga, `demo` faz o ciclo. Cobre a regra que define o método (atividade travada não entra no quadro), o seam do SCM (restrição de material → `Demanda`, idempotente), o PPC `null` até encerrar e o ranking de causas |
| `pdca3_grade_browser_test.py` | PDCA.3 no **navegador** — o caminho de dedo até a carteira, as colunas da grade e a **trava acendendo na digitação** (a única parte do instrumento que não dá para provar por API). Pede `LD_LIBRARY_PATH=~/.local/chromium-libs` |
| `pdca6_linha_de_balanco_test.py` | PDCA.6 — a LOB **derivada**: eixo na ordem em que a obra sobe (P10 depois de P9, não antes), ritmo em número, gargalo, choque de equipe como **fato** (dois ofícios no mesmo local ao mesmo tempo) e o que ficou **fora** do gráfico dito em voz alta. Mais o traço: `SS` + atraso, simulação sem gravar e a recusa do plano vigente |
| `pdca5_quadro_browser_test.py` | PDCA.5 no **navegador** — o **cartão travado que não é clicável** (recusar só no envio faria o time descobrir a trava depois da reunião), a tela sendo outra em cada estado da semana, o select de causa aparecendo só quando é exigido, e o PPC sobrevivendo ao F5. Pede `LD_LIBRARY_PATH` |
| `pdca6_ritmo_browser_test.py` | PDCA.6 no **navegador** — a quinta lente do plano, o SVG saindo com uma polilinha por serviço (a inclinação é a informação), simular mostrando o número **sem** desenhar, o traço feito pela tela nascendo no gráfico e reaparecendo no Gantt ao lado (a mesma atividade é barra e reta — planta §5.4). Pede `LD_LIBRARY_PATH` |
| `pdca7_verificacao_test.py` | PDCA.7 — a máquina de verificação e **o laço**. Metade das checagens existe para provar que os atalhos estão fechados: a ficha não conclui com obrigatória em branco, o desvio não passa sem explicação (nem o *não aplicável*), a NC **não encerra** com o plano concluído mas sem eficácia verificada, e quem trata não assina a própria eficácia. Prova o congelamento nos dois sentidos — apertar o critério do modelo muda o **modelo** e não a ficha já aplicada — e o seam vivo: NC crítica vira restrição e a atividade **sai do quadro da semana** |
| `pdca7_ficha_browser_test.py` | PDCA.7 no **navegador** — o **5º instrumento**: uma pergunta por vez com o critério ao lado dela, o desvio abrindo o campo de texto e a tela recusando **antes** de gastar requisição, a resposta sobrevivendo ao F5 (a prova de que grava a cada resposta, não no fim) e a ficha concluída virando leitura. Mais a fila de decisão do cockpit dizendo *o que falta*, e não o estado do banco. Pede `LD_LIBRARY_PATH` |
| `pdca_cockpit_test.py` | O **cockpit** — as três leituras que atravessam (`carteira/`, `hoje/`, `busca/`). Metade das checagens existe porque a leitura foi feita **para** cruzar: o recorte por permissão devolve a fila que a pessoa pode ver e nomeia o que faltou, em vez de 403 na página; a carteira discrimina as pendências e nunca as soma; o que não foi apurado volta nulo **com frase** e nunca como 0%; e entrada torta (`?dias=ontem`, obra inexistente) responde 400, não 500 |
| `pdca_cockpit_browser_test.py` | O cockpit no **navegador** — a régua de pronto item a item: a carteira ordenada pelo que dói, `HOJE` abrindo pela fila com o **verbo** que decide, cada leitura do pulso levando ao posto que a explica, a ausência das taxas dita em português de obra (e sem número de fatia), e a `⌘K` achando sem acento com o piso de duas letras **visível mesmo havendo resultados**. Mais: uma chamada só para os três blocos, e a tela parada. Pede `LD_LIBRARY_PATH` |
| `pdca_frente_test.py` | A **frente do canteiro** (`minhas-frentes/`) e o ato que a alimenta. O que ele protege é o casamento por **nome**: `responsavel`, `quem` e `inspetor` são rótulo durável no módulo, então "meu" se resolve sem acento e sem caixa, `?como=` troca o alvo, e a resposta diz contra qual nome procurou. Mais: bloco vazio vem **com razão escrita** (no celular, lista em branco é indistinguível de lista que não carregou), a leitura atravessa obras de propósito, o apontado nulo não vira zero, e o ato de campo grava, aparece e **estorna** sem deixar resíduo |
| `pdca_semana_campo_browser_test.py` | O posto **SEMANA** e o **campo** no navegador, nas duas físicas (1500px e 390px). O loop inteiro numa semana de rascunho que o roteiro cria e apaga: puxar sem arrastar (o par acessível do canvas), assumir, julgar **no cartão**, ser segurado pelo diálogo que **nomeia** o compromisso sem causa, e encerrar recebendo o índice com a base do peso. No celular: a falta de rede declarada, o alvo ≥ 48 px, o teclado numérico, e o estorno a um toque deixando a linha errada legível. Pede `LD_LIBRARY_PATH` |
| `pdca3_formulario_browser_test.py` | Os seis achados do "+ novo contrato" (D132): valor em real, zero à esquerda, select de fornecedores, rodapé em **janela baixa (620 px)**, a planilha contratual e a seleção ao focar. Pede `LD_LIBRARY_PATH` |
| `aprovacoes_admin_browser_test.py` | Administração → Aprovações (D130) — a escada na tela, e o **autoatesto ligado pela tela e conferido na API**. Pede `LD_LIBRARY_PATH` |
| `map6_maps_test.py`, `orc6_orcamento_test.py`, `orc8_carga_base_test.py`, `ie_impexp_test.py`, `d70_*`, `d23_*`, `phaseC_*` | Um módulo ou um achado específico, no stack vivo |
| `amostras_pra8.py` | **Apoio**: os bytes de amostra (DWG, DXF, PDF, RVT) que o `pra8` usa — importado como módulo irmão |
| `d11_mailpit_helper.py` | **Apoio**: lê o Mailpit para conferir e-mail de verdade |
| `carregar_acervo_dwg.py` | **Apoio**: sobe um acervo de DWG pelo caminho de produção |

Apoio não é teste: não tem asserção e não deve ser executado sozinho esperando um veredito.
