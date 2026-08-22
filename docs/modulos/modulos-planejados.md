# Módulos planejados (placeholders)

> Diretórios de app que **existem mas estão vazios** (sem `models.py`/`views.py`). São intenções de
> produto, ainda não implementadas. Quando forem construídos, devem seguir o **contrato de módulo
> novo** ([../acesso-e-permissoes.md](../acesso-e-permissoes.md) §7).

## Lista

| App | Nome e escopo |
|---|---|
| `modulodms` | DMS — gestão de documentos; é dele a **capacidade de PDF** da plataforma (nota abaixo) |
| `modulopdca` | PDCA — **planejamento de obra** (cronograma físico, Gantt, linha de balanço, avanço × previsto), **contrato de empreiteiro: medição, retenção e aditivo** (ver nota abaixo) **e** ciclo de melhoria contínua (FVS, não-conformidades, planos de ação) |
| `nucleo.frota` | **Gerência de frota de trabalho pesado** — admissão, fila por plano e preempção das conversões (nota abaixo) |

> 📐 **`modulopdca` — o que o Orçamento está esperando dele.** Decidido ao fechar o ORC.7
> (17/08/2026), quando a comparação com Sienge e Arquimedes mostrou o que faltava e o dono
> definiu que **não existiria um `modulomedicao`**: medir é apurar avanço, e avanço é
> planejamento. Então o PDCA nasce devendo três coisas ao laço
> `orçado → comprometido → aplicado → realizado`:
>
> 1. **Contrato de empreiteiro, medição, retenção e aditivo** — o avanço apurado por
>    serviço/etapa contra a régua do orçamento aprovado, a retenção contratual aplicada sobre ele
>    e a liberação da parcela. A régua já existe e é estável: `Orcamento` aprovado é congelado, e
>    `planilha.orcado_por_etapa` entrega o previsto na mesma dimensão (`obras.EtapaObra`) que o
>    SIL usa para o aplicado. **Tudo isso é do PDCA**, porque é contrato de *obra* — o
>    [moduloerp](moduloerp.md) é de recursos empresariais e não tem por que conhecer percentual de
>    avanço de etapa para pagar. O seam é o mesmo que o SCM já usa: o PDCA decide **quanto é
>    devido e por quê**, entrega um **título líquido** ao ERP (molde do
>    `PedidoCompra.conta_pagar_ref`), e o ERP decide **quando sai do caixa**.
> 2. **Gantt, precedências e caminho crítico** — a dimensão tempo *causal*. O Orçamento já tem a
>    dimensão tempo **financeira** (`ParcelaEtapa` → curva S → desembolso, inclusive por insumo
>    desde o ORC.7), e ela é a semente: a distribuição por competência que o planejador digita
>    hoje é o que o cronograma físico vai passar a derivar, em vez de as duas conviverem.
> 3. **Avanço físico medido** substituindo o `EtapaObra.percentual_conclusao` digitado à mão —
>    que é o número que hoje pondera a curva S real.
>
> Enquanto o PDCA não existe, o Orçamento **declara a ausência** em vez de improvisar: a §7 e a
> §13 da [planta dele](moduloorcamento.md) dizem o que ele não faz e onde cada coisa mora.

> ⚙️ **Gerência de frota — ✅ existe desde 16/08/2026, em [`nucleo/frota.py`](../../backend/nucleo/frota.py).**
> O que este endereço reservava foi construído: tabela de fila no Postgres (`TarefaNaFila`) +
> despachante, fila única com prioridade e cadeira marcada em fração, recolocação com envelhecimento,
> `liberar_orfas` no beat e a rota `/api/frota/tarefas/`. Os números da política moram em
> [`payment/planos.py`](../../payment/planos.py) §5.4c e estão **declarados como provisórios até o
> estudo** que o dono pediu. A Prancheta é a primeira cliente; importação de acervo, exportação
> grande e ortofoto do Maps entram pelo campo `frota` sem fila paralela. Relato inteiro no
> [histórico](../historico-correcoes.md) (D98 e PRA.11).
>
> O parágrafo abaixo é o registro de **por que** o endereço foi reservado, e fica porque explica o
> desenho que existe hoje. Hoje o trabalho pesado
> tinha **freio, mas não tinha porteiro**: o `worker-conversao` é uma frota separada com
> `--concurrency 1`, `mem_limit` e o `orcamento_de_conversao` ([base.yml](../../deploy/compose/base.yml),
> D57), e isso protege a máquina — mas quem chega primeiro ocupa, e quem chega depois espera sem
> ordem e sem previsão. O que falta é a camada que o drone já tem: o **ClusterODM**, que enfileira,
> distribui entre nós e diz a posição a quem espera, na frente dos `NodeODM` que fazem o trabalho
> ([`ImgDrone/ClusterODM-master`](../../ImgDrone/)). É esse papel — o *cluster manager* — que o SGI
> precisa ter para a conversão, e é ele que este endereço reserva.
>
> Três decisões do dono já tomadas (16/08/2026), para não se perderem até a planta existir:
>
> - **Fila com prioridade e cadeira marcada, nunca fila separada por plano.** O premium fura a fila,
>   mas **não a fila inteira**: parte dos lugares é reservada a ele e o free não senta lá, e o
>   inverso também vale — uma parcela fica garantida ao free, para que ele não espere uma
>   eternidade. As duas reservas são **fração da frota, não número fixo**: *"você não pode deixar 40
>   cadeiras premium e quando o programa lançar haver 100.000.000 de pessoas na fila"*. Fração
>   escala sozinha com a frota e com a demanda; número absoluto vira gargalo no dia do lançamento.
> - **Preempção por relógio — ✅ feita, e o checkpoint que a destravou é a FOLHA.** Este item dizia
>   ser impossível, e o motivo era correto: sem ponto de retomada, "voltar para a fila" jogaria fora
>   o trabalho e gastaria mais CPU total do que deixar terminar. A saída não foi a prevista aqui
>   (gravar o DXF intermediário em disco) e sim uma mais barata: o `MotorDxf` **já emite folha a
>   folha**, então bastou conferir o relógio entre folhas e devolver um marcador `Retomada`. O que
>   toda passada repete é a gravação da geometria; o que ela pula é reemitir as folhas prontas — que
>   num arquivo de dezenas de desenhos é a maior parte do relógio. Para quem converte numa unidade
>   indivisível (PDF, imagem, IFC), `retomavel = False` mantém o contrato antigo: estoura o teto,
>   **para tudo e explica** (`recurso_excedido`), o degrau que o
>   [`limites.py`](../../backend/moduloprancheta/limites.py) já implementava.
> - **Os tetos continuam sendo do dono.** Fração reservada por plano, profundidade da fila e relógio
>   de preempção são limite comercial e nascem em [`payment/planos.py`](../../payment/planos.py),
>   como todo teto do sistema — nunca em código de engenharia nem no compose.
>
> **O que a gerência vale além da conversão:** ela é o lugar natural de qualquer trabalho cujo custo
> venha do arquivo do cliente — importação de acervo, exportação grande, ortofoto do
> [`modulomaps`](modulomaps.md). Por isso o endereço é `nucleo`, e não `moduloprancheta`: a
> Prancheta é a **primeira** cliente, não a dona.

> 📄 **Capacidade de PDF — endereço reservado, planta ainda não escrita.** As operações de PDF do
> sistema (remover **marca d'água**, carimbar, juntar/dividir, extrair página, girar) pertencem ao
> `modulodms`. Esta nota existe para a função ter **endereço antes de ter desenho** — para ninguém a
> implementar avulsa dentro do módulo que precisar dela primeiro, que é como uma capacidade
> transversal vira quatro cópias divergentes. **Não** é a planta do DMS; quando ela for escrita, é lá
> que o desenho entra. Três decisões já tomadas, para não se perderem até lá:
>
> - **O produto de cada operação é uma revisão nova, publicada** — não uma derivada e nunca um passo
>   automático no upload. O arquivo continua guardado **como o cliente entregou**; a versão limpa (ou
>   carimbada) nasce como revisão nova, com autor, data e o ato de `publicar` separado do de `editar`.
>   Preserva o *write-once* que a [Prancheta](moduloprancheta.md) §9 já pratica e deixa rastro de quem
>   removeu o quê — que é o ponto de um DMS.
> - **A biblioteca é o `pikepdf`** (MPL-2.0, sobre o QPDF/Apache-2.0), **não o PyMuPDF**: aquele é
>   AGPL-3.0 e o backend é SaaS proprietário servido pela rede — o gatilho literal do §13 da licença.
>   Mesma política permissiva que a Prancheta já escolheu ao preferir `pypdfium2`
>   ([THIRD-PARTY-LICENSES.md](../../THIRD-PARTY-LICENSES.md)).
> - **O motor já existe, validado à mão**, em [`ferramentas/marca_dagua/`](../../ferramentas/README.md):
>   as cinco estratégias de remoção (bloco de texto `BT…ET`, XObject, camada OCG, anotação, imagem) e
>   o diagnóstico que escolhe entre elas. O porte para `pikepdf` é trabalho conhecido, não pesquisa; o
>   que não se reaproveita é a interface Tkinter.

> `moduloprancheta` (**Prancheta** — visualizador central dos arquivos de projeto: DWG/DXF, RVT, IFC,
> KMZ, QGIS, nuvem de pontos, PDF, para consulta em campo) **saiu da lista de placeholders**: PRA.0
> (fundação do backend) ✅ 31/07/2026. Planta em [moduloprancheta.md](moduloprancheta.md); status no
> [../roadmap.md](../roadmap.md) (Fase 7).

> ⚠️ **`moduloaps` foi renomeado para `moduloprancheta` (28/07/2026) — e o nome antigo enganou o
> projeto inteiro.** A sigla APS era **Autodesk Platform Services** (o ex-Forge): a v01 tinha
> `APSModel` + proxy OAuth do Autodesk Viewer, ou seja, um **visualizador de projeto**. Este
> documento leu a sigla como "acompanhamento/planejamento de serviços" e essa leitura se espalhou
> por sete documentos, criando um módulo de **planejamento** que nunca existiu — e do qual o
> Orçamento e o hub passaram a depender. O planejamento é necessidade real e foi para o
> `modulopdca`; o visualizador ficou com o nome próprio. A linha abaixo já avisava do risco.

> `moduloscm` (SCM — suprimentos) **saiu da lista de placeholders**: porte iniciado (fatia 1 ✅
> 20/07/2026 — catálogo + centro de custo). Desenho e faseamento em
> [../expansão/modulos/moduloscm.md](../expansão/modulos/moduloscm.md); status no
> [../roadmap.md](../roadmap.md) (Fase 7).

> `modulomaps` (Maps — dimensão espacial) **saiu da lista de placeholders**: implementado em
> MAP.0–MAP.6 (**duas metades** — `Local` como fundação sem entitlement, à la
> `catalogo`/`funcoesimpexp`, e as camadas de ortofoto/voo/rota/cerca atrás do entitlement `maps`;
> **PostGIS/GeoDjango** como camada espacial). Falta só o MAP.7 (`CamadaExterna` + banco de terrenos),
> que é fronteira com a expansão. Planta em [modulomaps.md](modulomaps.md); status no
> [../roadmap.md](../roadmap.md) (Fase 7).

> `modulosil` (SIL — estoque & logística interna) **saiu da lista de placeholders**: desenho
> aprovado (Estoque + logística interna ampla, sobre um **catálogo-mestre de plataforma** novo —
> app-fundação `catalogo`). Plantas em [modulosil.md](modulosil.md) + [catalogo.md](catalogo.md);
> expansão em [../expansão/modulos/modulosil.md](../expansão/modulos/modulosil.md); status no
> [../roadmap.md](../roadmap.md) (Fase 7).

> **Confirmar a intenção com o produto antes de implementar** — e conferir o que a v01 realmente
> tinha em [../arquitetura/migracao-v01.md §5](../arquitetura/migracao-v01.md). Nome inferido por
> sigla é chute, e chute escrito em planta vira requisito: foi assim que o `moduloaps` passou um mês
> sendo documentado como o oposto do que é.

## Contrato a seguir (resumo)

Qualquer módulo novo — app Django **ou** serviço separado (estilo drone) — não reimplementa
identidade:

1. Registrar um `Modulo` (código) no catálogo da IAM.
2. Tornar-se vendável por `AssinaturaTenant` (empresa) + liberável por `AcessoUsuarioModulo` (usuário).
3. Validar o JWT da IAM e **exigir o código do módulo** — via `RequireModule` (Django,
   [nucleo/permissions.py](../../backend/nucleo/permissions.py)) ou filtro de authority (estilo drone).
4. Aplicar RBAC por papel quando necessário e **filtrar tudo por tenant** (herdar de
   `TenantScopedModel`).

Ver detalhe e exemplos em [../acesso-e-permissoes.md](../acesso-e-permissoes.md) e um doc de módulo
real como referência ([modulocrm.md](modulocrm.md)).
