# Prancheta — o projeto da obra, aberto em campo

> **Planta do módulo `moduloprancheta`** (entitlement `prancheta`, rota `/api/prancheta/`).
> Descreve o desenho, não o status — o andamento vive no [roadmap.md](../roadmap.md).

## 1. O nome (e por que o antigo enganava)

O app se chamava **`moduloaps`**. A sigla vinha de **Autodesk Platform Services** (o ex-Forge) — o
nome do **fornecedor** que a v01 usava para renderizar DWG/RVT, não o nome do domínio. Lida fora de
contexto, "APS" virou *"acompanhamento/planejamento de serviços"*, e essa leitura entrou em sete
documentos: nasceu um módulo de **planejamento** que nunca existiu, do qual o Orçamento e o hub da
home passaram a depender.

Duas correções, e elas são independentes:

- **O visualizador** ganhou nome de domínio: **Prancheta** — a mesa onde o projeto fica aberto. Não
  é "Plantas" porque este repositório já chama de *planta* os seus documentos de arquitetura, e não
  é "CAD/BIM" porque o mestre de obras não fala assim.
- **O planejamento** (cronograma físico, Gantt, linha de balanço, avanço × previsto) é necessidade
  real e foi para o **`modulopdca`**, que na v01 já tinha `Tarefa`/`Marco`/`Risco`.

Lição registrada em [modulos-planejados.md](modulos-planejados.md): nome inferido por sigla é chute,
e chute escrito em planta vira requisito.

## 2. A tese — uma porta só para abrir arquivo

O sistema já sabe abrir coisas, mas cada uma no seu canto: ortofoto e nuvem de pontos no **drone**
(Potree), camada geo no **Maps** (MapLibre/PostGIS), PDF e imagem espalhados pelo diário e pelos
anexos. Quem está no canteiro não quer saber de qual módulo o arquivo veio — quer **abrir o projeto
no celular** e conferir a medida antes de mandar executar. Hoje isso termina em PDF exportado e
WhatsApp.

A Prancheta é o **visualizador central**: uma porta única para abrir qualquer arquivo de projeto da
obra. Ela **não duplica** o dado dos outros módulos — **consome** o que eles já servem. O dono do
dado continua sendo quem sempre foi; o que centraliza é a **visualização**.

**Gate único, sem metade de fundação.** Diferente do [Maps](modulomaps.md) — onde `Local` é cadastro
que o SIL e o SCM consomem, e por isso fica fora do entitlement —, aqui **tudo** está atrás de
`RequireModule("prancheta")`. O custo (storage de CAD/BIM + motor de conversão) é todo do módulo, e
uma "metade de fundação" aqui daria de graça exatamente o que é o produto.

### 2.1 Não é um módulo, é uma capacidade da plataforma

*(decisão do dono, 08/08/2026 — e ela corrige a frase que estava aqui: "nenhum outro módulo depende
do acervo de projeto para funcionar".)*

**Quem compra a Prancheta não está comprando um módulo — está comprando poder ver os próprios
arquivos e projetos dentro do software.** A consequência é que a visualização não pertence a uma tela:
quando o [Orçamento](moduloorcamento.md), o [SIL](modulosil.md) ou o diário precisarem mostrar um DWG,
eles **puxam esta visualização**, no lugar onde a pessoa já está. Quem não a contratou vê o **aviso
com cadeado ali mesmo**, na tela do Orçamento — nunca é mandado para um silo separado, e nunca a
função some sem explicação. É a regra do farol
([frontend.md §3.2](../frontend.md)) valendo para **função**, e não só para menu.

Isso muda três coisas concretas, e as três já estão no código:

1. **O que se vende é o formato, uma vez.** `formatos_prancheta` em
   [payment/planos.py](../../payment/planos.py) deixou de significar "formatos que a Prancheta abre" e
   passa a significar **"formatos que esta empresa abre no sistema"**. Quem aplica a parede não é mais
   o módulo, na porta dele: é o motor, na porta única, pelo gancho `Recurso.formatos_contratados`
   ([funcoesimpexp §2, R17](funcoesimpexp.md)). Um 402 só, para todos os módulos.
2. **O motor de conversão continua sendo degrau à parte.** Abrir DWG é a capacidade; abrir DWG *com
   alta fidelidade* é o `motores_prancheta`, e é o que a PRA.4 vende. Formato e acabamento são duas
   vendas porque são dois custos — a segunda é COGS por tradução.
3. **A régua de integração se aplica a esta capacidade primeiro.** É o exemplo mais literal do "o que
   conversa no backend conversa na tela" da [frontend.md §1.6](../frontend.md): um sistema de gestão
   integrada, não silos.

**Por isso ela é uma lente, não um lugar do ciclo** ([frontend.md §3.2](../frontend.md)): mora como
ícone na **topbar**, ao lado de Mapas e Calendário, e não na sidebar. A régua do projeto pergunta
"onde eu estou no ciclo?" para a sidebar e "o que está acontecendo, visto de outro eixo?" para a
topbar — e o projeto se abre *por cima* da tela em que a pessoa já está (a obra, a etapa, a
não-conformidade), não como um destino ao qual se viaja. Ela tem página própria (acervo + cockpit),
como o Maps tem a dele.

## 3. Formatos e quem é dono de cada um

| Família | Formatos | Motor | Dono do dado |
|---|---|---|---|
| CAD 2D | DWG, DXF, DWF | ODA/`ezdxf` → SVG/tiles · ou APS | **Prancheta** |
| BIM 3D | **IFC** (2x3/4/4.3), RVT, NWD/NWC, DGN, SKP | IfcOpenShell + That Open (IFC) · APS (RVT/NWD) | **Prancheta** |
| Geo | KML/KMZ, SHP, GeoJSON, GPKG, QGZ/QGS, GeoTIFF | GDAL/OGR → camada | [Maps](modulomaps.md) — a Prancheta abre, o Maps guarda |
| Nuvem de pontos | LAS/LAZ, COPC, E57 | Potree/PDAL (já no stack) | [drone](../arquitetura/migracao-v01.md) |
| Documento | PDF, imagem | render nativo do browser | o DMS — [funcoesimpexp](funcoesimpexp.md) §13 (ciclo de vida) |
| Colaboração | **BCF** | — (não converte: vira marcação, §13) | **Prancheta** |

**BCF é o que fecha o laço** e merece destaque: é o padrão aberto para marcar um problema no modelo
(ponto de vista + comentário + status) e devolvê-lo ao projetista. Sem ele o módulo é só leitura;
com ele o campo responde ao escritório no formato que o escritório abre.

**Ele é a única linha desta tabela que não é arquivo de acervo.** Um `.bcfzip` não tem geometria — ele
carrega marcações *sobre* uma prancha que já está aqui. Por isso não tem motor (`interop=True` no
registry), não entra por upload de revisão e viaja por endpoint próprio. A tabela o listava com motor
`IfcOpenShell` até o PRA.3, o que teria feito o upload passar e a conversão morrer em
`arquivo_corrompido` depois de ocupar storage pago.

## 4. Motores — o que a pesquisa mostrou

- **DWG e RVT são o nó.** RVT é fechado; ler DWG sem licença da Autodesk é juridicamente cinzento.
  Na prática só a **APS/Model Derivative** traduz RVT/DWG/NWD/IFC com confiabilidade, e cobra **por
  tradução** (0,5 token por job complexo — RVT/IFC/NWD; 0,1 por simples — DWG), em Prepay/Flex ou
  pay-as-you-go. É **COGS por arquivo**: o knob mora em [payment/](../../payment/README.md), como
  IA, NF, boleto e storage.
- **IFC é livre e maduro:** **IfcOpenShell** (LGPL, **Python** — cai na stack do backend) para
  processar, e **That Open / Fragments** (MIT, `web-ifc` em WASM) no browser: 2 GB de IFC viram
  ~80 MB de derivada.
- **Armadilha de licença registrada:** o **xeokit**, o viewer BIM open-source mais citado, é
  **AGPLv3** — incompatível com SaaS proprietário sem licença comercial. Não entrar por engano.
- DXF resolve com **`ezdxf`** (Python, MIT), que também rasteriza/gera SVG.

### 4.1 O nó do DWG — não há caminho grátis *e* limpo

O DWG é o formato dominante da construtora brasileira, e é onde a licença dói. **Três caminhos, e
nenhum é "de graça e pronto":**

| Caminho | Custo | O que trava |
|---|---|---|
| **ODA File Converter** | — | ❌ **Descartado.** É gratuito **só para uso não-comercial** de quem não é membro da ODA. Um SaaS pago é uso comercial |
| **ODA membership** | fixo, anual (**Sustaining**, milhares de USD/ano) | Web/SaaS exige o nível *Sustaining* — o *Commercial* cobre só desktop/mobile com <100 cópias/ano. Melhor qualidade, custo fixo antes do primeiro cliente |
| **LibreDWG** (`dwg2dxf`) | zero marginal | **GPLv3**: chamado como binário separado (subprocesso) o nosso código continua proprietário, mas a imagem passa a distribuir GPL — exige ship da licença e oferta de fonte daquele componente. **E não é empacotado pelo Debian** (ver §4.2) |
| **APS** (job simples) | 0,1 token por arquivo | Sem custo fixo; o custo chega junto com o uso. Torna DWG um formato **pago** para todo cliente |

**Decidido: os dois, e o motor é o degrau do plano.** LibreDWG nos planos básicos, APS nos premium.
A escolha resolve o dilema em vez de arbitrá-lo — o cliente de entrada abre DWG sem que a plataforma
pague nada por arquivo, e quem precisa de fidelidade de referência (ou de RVT) paga por ela.

Isso funciona porque a `DerivadaProjeto` é única por `(revisão, tipo, **motor**)`: as duas derivadas
do mesmo arquivo coexistem, então **subir de plano reconverte com o motor melhor** sem invalidar
nada, e descer de plano não apaga o que já foi convertido. Duas consequências a honrar na
implementação:

- **Falha do motor livre é upsell honesto, não erro genérico.** DWG que o LibreDWG não abre precisa
  dizer *"este arquivo exige o motor de alta fidelidade"* — e não "falha na conversão". A régua de
  dados honestos vale nos dois sentidos: nem esconder o limite, nem fingir defeito.
- **A cobertura do motor livre é medida, não suposta.** O LibreDWG declara ler r1.2–**r2018** com
  ~99% (a fraqueza dele é *escrita*, que não usamos). Mas há indício de um formato **DWG 2024
  (AC1037)** nas versões recentes do AutoCAD, e as fontes se contradizem. A taxa de sucesso real
  sobre os DWGs do cliente é o que define onde fica a fronteira entre os planos — se o motor livre
  cobrir pouco, o degrau desce; se cobrir quase tudo, o premium fica só com RVT/NWD.
  O instrumento da medição é o comando
  [`medir_cobertura_dwg`](../../backend/moduloprancheta/management/commands/medir_cobertura_dwg.py):
  aponta-se para uma pasta de DWGs reais e ele classifica em quatro baldes — **convertido**,
  **falhou_no_alcance** (dentro do que o LibreDWG promete e ainda assim não abriu: é este que mede a
  distância entre promessa e entrega), **acima_do_alcance** (`AC1037`, recusado pela leitura do
  cabeçalho antes de gastar subprocesso) e **inválido** —, agrega por versão de DWG e imprime as
  duas taxas. Não grava nada: rodar no acervo de um cliente não pode deixar rastro nele.

#### A medição — 73 DWGs reais de construtora, 01/08/2026

| Balde | Arquivos |
|---|---|
| convertido | 40 |
| falhou_no_alcance | 33 |
| **acima_do_alcance** | **0** |
| inválido | 0 |
| **Taxa** | **54,8%** |

Por versão: `AC1032` (R2018) domina o acervo — 55 dos 73 —, seguida de `AC1024` (10), `AC1021` (3),
`AC1027` (4) e `AC1015` (1). **Nenhum `AC1037`.**

**As duas conclusões contrariam a suposição que a fatia carregava:**

1. **O premium não se justifica por versão nova.** Zero arquivos acima do alcance declarado — o DWG
   2024 que motivou metade desta seção não apareceu no acervo real. O que separa os planos não é *a
   versão que o cliente salva*, é **o que o caminho livre entrega no arquivo que ele já tem**.
2. **A maior parte da falha não é do LibreDWG.** Das 33, só **5** vêm do `dwg2dxf` (CRC/checksum no
   próprio DWG). Outras **26 acontecem depois**: o DWG virou DXF e o `ezdxf` não conseguiu
   desenhá-lo — 13 recusados como "não é um DXF válido", 10 por *"Required block definition for `*U`
   does not exist"* (bloco anônimo referenciado e não definido no DXF gerado) e 3 por divisão por
   zero / *bounding box* vazia. A fronteira comercial que esta medição deveria posicionar está, na
   verdade, **em cima de um defeito nosso** — registrado como [D42](../historico-correcoes.md).

O número honesto do plano de entrada não são os ~99% que a documentação do LibreDWG sugere — mas
tampouco os 55% desta primeira leitura, como a remedição mostrou. A amostra tem viés declarado: são
os 73 arquivos do acervo que estavam **locais** (os outros 2.585 são placeholders do OneDrive, e
lê-los baixaria ~10 GB).

#### A remedição — 150 DWGs, amostra espalhada, 02/08/2026

Feita ao fechar o [D42](../historico-correcoes.md), sobre uma amostra **1 a cada 7** de um acervo local de
1.107 DWGs (o dobro largo da primeira, e espalhada pelo acervo inteiro em vez de concentrada nas
primeiras pastas). O mesmo corpus foi medido **antes e depois** do conserto, para a comparação não
depender de qual arquivo estava na máquina naquele dia:

| | antes | depois |
|---|---|---|
| convertido | 106 | **110** |
| falhou | 44 | 40 |
| **Taxa** | 70,7% | **73,3%** |
| mensagens que acusavam o arquivo do cliente | 20 | **0** |

**O ganho de taxa é o menor dos dois resultados.** O que muda de figura é a classificação das 40
falhas restantes, que separa pela primeira vez o que é nosso do que é limite real:

| Causa | Arquivos | De quem é |
|---|---|---|
| DXF intermediário ilegível | 20 (13,3%) | **nosso** — o `dwg2dxf` gera um DXF que o `ezdxf` não lê ([D43](../pendencias.md)) |
| prancha montada só no *paperspace* | 8 (5,3%) | **nosso** — desenhamos só o modelspace ([D44](../historico-correcoes.md)) |
| desenho genuinamente vazio | 5 (3,3%) | **de ninguém** — o arquivo não tem entidade nenhuma ([D45](../historico-correcoes.md)) |
| XREF não enviado | 2 (1,3%) | **do cliente** — a geometria está em arquivo externo que não subiu ([D45](../historico-correcoes.md)) |
| CRC/checksum no `dwg2dxf` | 5 (3,3%) | **do motor livre** — é este, e só este, o caso do premium |

**Por contagem de arquivo, o limite real do caminho livre é 3,3%** — não os 45% que a taxa crua
sugeria: de cada 100 arquivos que não abrem, ~70 são defeito nosso e ~12 não têm desenho para abrir.
Dimensionar o plano pelo número cru teria vendido como fronteira tecnológica o que era, em quase
tudo, lista de correção nossa.

#### A remedição completa — 160 DWGs, 07/08/2026 (PRA.1d, item 5)

Fecha a passada que 06/08 interrompeu no meio (62 de 160, quando o consumo sem teto chegou a 62 GB —
[D57](../historico-correcoes.md)). Rodou em **16 lotes, um container por lote**, com teto duro de 3 GB/2 CPUs
por lote além dos tetos de produção por arquivo; o corpus está versionado em
[ferramentas/medicao/corpus-160.txt](../../ferramentas/medicao/corpus-160.txt) e o disparo em
[remedir_dwg.sh](../../ferramentas/medicao/remedir_dwg.sh).

| | 02/08 (D42) | 07/08 |
|---|---|---|
| válidos medidos | 150 | **160** |
| convertido | 110 | **116** |
| **Taxa** | 73,3% | **72,5%** |

**A taxa das duas colunas NÃO é comparável, e dizer o contrário seria inventar um resultado.** São
duas amostras 1-em-7 diferentes do mesmo acervo: a lista de 02/08 se perdeu (é a origem do
`--salvar-lista`), e este corpus é o montado em 06/08. A partir daqui a comparação passa a ser
possível — a lista está versionada.

**O que a composição diz, e ela é comparável por causa:**

| Causa | 02/08 | 07/08 | Leitura |
|---|---|---|---|
| DXF intermediário ilegível | 20 | **21** | [D43](../pendencias.md) intacto — é o maior bolso, e é nosso |
| prancha só no *paperspace* | 8 | **0** | [D44](../historico-correcoes.md) confirmado no acervo real: 8 arquivos passaram a converter **pelo paperspace** |
| XREF não enviado | 2 | **0** | [D45](../historico-correcoes.md); 1 arquivo desenhou mesmo com XREF faltando |
| desenho vazio | 5 | **5** | de ninguém, como esperado |
| CRC no `dwg2dxf` (`motor_insuficiente`) | 5 | **5** | **a fronteira do premium não se moveu: 3,1%** |
| `recurso_excedido` | — | **11** | **novo** — a categoria não existia antes de haver teto |

**O achado que importa é o `recurso_excedido`.** Os 11 arquivos (6,9%) não são falha nova: são os que
antes convertiam **pagando com memória sem limite** — a conta que produziu o incidente de 62 GB.
Trocamos 11 conversões silenciosamente caríssimas por 11 recusas declaradas, e é por isso que a taxa
não subiu apesar de [D44](../historico-correcoes.md) e [D45](../historico-correcoes.md) terem devolvido 10 arquivos.

**Este parágrafo estava errado sobre a causa, e a remedição seguinte mostrou por quê** — não porque a
escada fosse fraca, mas porque o orçamento que estes 11 encontraram não era o que o plano declarava
([D76](../historico-correcoes.md)). Fica como está por ser o registro do que se leu naquele dia; a
correção é a seção abaixo.

**Dois números que a passada fechou de lado:**

- **[D49](../historico-correcoes.md), caminho feliz provado:** **52 dos 160** trazem miniatura embutida do CAD
  (2 ilegíveis). Até aqui só havia a prova da *ausência*, com binário falso.
- **[D43](../pendencias.md) dimensionado:** o `dwg2SVG` desenha **37 das 44 falhas** (4 abrem sem
  traço, 3 não abrem). O resgate não é hipótese — é a maior alavanca de cobertura que resta, e é
  nossa.

#### A remedição sob o teto corrigido — o MESMO corpus de 160, 08/08/2026

A passada de 07/08 mediu com o orçamento de memória valendo outra coisa: o `RLIMIT_AS` contava o
**processo inteiro**, então o teto de 1.536 MB entregava ~384 MB reais à conversão
([D76](../historico-correcoes.md)). Corrigida a unidade, os mesmos 160 arquivos foram medidos de
novo — mesmo corpus provado pela impressão digital (`corpus_hash f8f5b542c6497a47`), mesmo motor,
mesmos lotes. Relatório inteiro em
[ferramentas/medicao/resultado-2026-08-08.log](../../ferramentas/medicao/resultado-2026-08-08.log).

| | 07/08 (teto ~384 MB real) | 08/08 (teto declarado) |
|---|---|---|
| convertido | 116 | **126** |
| **Taxa** | 72,5% | **78,8%** |
| `recurso_excedido` | 11 (6,9%) | **0** |
| DXF intermediário ilegível | 21 | **22** |
| `motor_insuficiente` (premium) | 5 (3,1%) | **5 (3,1%)** |
| desenho vazio | 5 | **5** |
| **falhas que são NOSSAS** | 21,2% | **15,0%** |

**Os 11 do [D61](../historico-correcoes.md) estão contados um a um:** 10 convertem, e 1 apenas
avançou — passou a ler o DWG inteiro e morreu depois, no DXF intermediário, entrando no bolso do
[D43](../pendencias.md) (21 → 22). Não sobrou nenhum arquivo recusado por orçamento, e o D61 fecha
**por medição**, não por decisão de produto: a pergunta "a unidade de cobrança devia ser o cômputo?"
era consequência de um teto que não existia como anunciado.

**A fronteira comercial não se mexeu, e é o número mais importante da tabela.** Os 5 arquivos de
`motor_insuficiente` (3,1%) são os mesmos — a PRA.4 continua dimensionada por RVT/NWD e pelo peso do
arquivo (a seção seguinte), não por cobertura de DWG. O que encolheu foi a **nossa** fila.

**A escada da PRA.1d aparece agora fazendo o trabalho dela:** exatamente **2 arquivos** estouraram o
orçamento na 1ª passada, desceram para `SHOW_OUTLINE` e converteram — declarando a hachura
simplificada, como manda o contrato do degrau. Sob o teto velho eles não chegavam a esse ponto.

**O instrumento também mudou, e isso vale além desta passada.** A medição de 07/08 guardou os baldes
e jogou fora o veredito por arquivo: "11 estouraram o orçamento" e "21 geraram DXF ilegível" eram
números sem nome, e a investigação seguinte teria de remedir o acervo só para reencontrá-los. O
parcial subiu para **v2** e passou a gravar a linha de cada arquivo; a consolidação imprime a lista
**por causa, com o dono junto** — o D43 virou uma lista de 22 caminhos para abrir um a um. A subida
de versão também **recusa somar** os parciais de 07/08 com os de hoje, que é o certo: são dois
orçamentos diferentes.

**Custo da passada:** 16 lotes, **7min15s** de relógio, um container por lote com 3 GB/2 CPUs e
`nice -19` — nenhum lote caiu, e o pior caso continua sendo o lote, nunca a estação.

#### O bolso do D43 aberto — os mesmos 160, 09/08/2026

Quatro defeitos do escritor de DXF do LibreDWG e **um nosso**, cada um achado abrindo os arquivos que
não abriam, um a um. Relatório em
[ferramentas/medicao/resultado-2026-08-09.log](../../ferramentas/medicao/resultado-2026-08-09.log).

| | 07/08 | 08/08 | 09/08 | 09/08 · LibreDWG 0.14 |
|---|---|---|---|---|
| convertido | 116 | 126 | 135 | **159** |
| **Taxa** | 72,5% | 78,8% | 84,4% | **99,4%** |
| `motor_insuficiente` (premium) | 5 (3,1%) | 5 (3,1%) | 5 (3,1%) | **0 (0%)** |
| falhas **nossas** | — | 21,2% | 12,5% | **0,6%** (1 arquivo) |

**A fronteira comercial não se moveu em nenhuma das três primeiras passadas.** Os mesmos 5 arquivos,
3,1% — tudo o que se ganhou em cobertura saiu da **nossa** fila, não da do cliente. É o argumento do
§6.1 ficando mais forte a cada medição: o degrau do plano não é a cobertura de DWG.

**Na quarta ela sumiu.** Trocado o motor livre pelo commit `a8ce2489` do LibreDWG (`dwg2dxf
0.14.8566`, [Dockerfile](../../backend/Dockerfile)), os 5 arquivos que sustentavam o
`motor_insuficiente` passaram a converter: a fronteira do premium em DWG é **0%**, medida sobre o
mesmo corpus. Relatório em
[ferramentas/medicao/resultado-2026-08-09-libredwg-0.14.log](../../ferramentas/medicao/resultado-2026-08-09-libredwg-0.14.log);
o caminho até a decisão está no [D43](../historico-correcoes.md).

O argumento do §6.1 deixa de ser tendência e vira fato: **a PRA.4 não tem mais o DWG como
justificativa**, e fica dimensionada só por RVT/NWD e pelo acabamento — que é o que esta planta
sempre mandou fazer. Vender premium por cobertura de DWG agora teria número contra.

**Sobra um arquivo, e ele não é erro de código.** O `J2 - S_PROJETO EXECUTIVO FINAL COM LAZER.dwg`
estoura o orçamento de 1.536 MB e sai como `recurso_excedido` — teto de recurso, que mora em
[payment/planos.py](../../payment/planos.py) e é knob do dono. **Gatilho de reabertura:** se um
segundo arquivo do acervo real bater no mesmo teto, a pergunta deixa de ser "sobe o número?" e passa
a ser "o que aloca proporcional ao desenho?", que é engenharia e volta para a fila de conserto.

**Uma consequência para a camada de reparo:** `convertido_apos_reparo: continuacao_orfa` **sumiu do
relatório** — o corte de texto em 255 bytes está consertado a montante. As três funções de
`reparar_intermediario` ficam como **rede**, não como muleta: são auto-limitadas (só disparam contra
construção que não existe em DXF são), então não custam nada enquanto não forem necessárias.

**O reparo do intermediário virou camada** ([`reparar_intermediario`](../../backend/moduloprancheta/motores/dwg.py)),
com três funções pequenas que disparam contra construções que **não existem em DXF são**:

| Reparo | O defeito | Arquivos do corpus |
|---|---|---|
| `continuacao_orfa` | Texto acima de 255 bytes escrito sem o código de grupo `3` de continuação | **9** |
| `seta_de_cota_orfa` | `DIMSTYLE 342 → #7`, e o `#7` é um `VERTEX` — handle que existe e aponta para coisa **sem nome** | **1** |
| `registro_vazio` | Registro de tabela aberto e nunca preenchido, sem handle nem nome | 0 (achado no `FILE.DWG`, que não abriu por outro motivo) |

A camada tem uma disciplina própria, e ela é de recurso: **divide as linhas uma vez, junta uma vez, e
não junta se ninguém mexeu**. A 1ª versão encadeava três passadas completas e, num DXF de 84 MB,
empurrou para fora do orçamento um arquivo que convertia — reparo que custa conversão não é reparo.

**A 5ª causa era nossa:** o `_ler` caía no `recover` só em `DXFStructureError`, e qualquer outro erro
virava "ilegível" com a segunda tentativa ali sem ser chamada. Um arquivo de 25.727 entidades morria
assim. Agora toda falha de conteúdo tenta o reparo; ficam de fora o `OSError` (é o arquivo, não o
conteúdo) e o teto de memória.

**E `desenho_vazio` foi a zero, o que NÃO é ganho.** Os 5 que a passada anterior dava como "de
ninguém" têm DXF sem a tag `EOF`: o modelspace vazio não era prova de desenho vazio, era o
intermediário cortado no meio. A conta ficou honesta, e eles voltaram para a nossa fila.

#### O tamanho do arquivo é a fronteira real — 102 DWGs acima de 5 MB, 02/08/2026

A amostra acima é dominada por arquivo pequeno (121 dos 150 abaixo de 1 MB), e isso esconde o eixo
que de fato separa os planos. Varrendo **toda** a população pesada do acervo local pelo degrau do
`dwg2dxf`:

| Tamanho do DWG | Abriu | Falhou | Taxa |
|---|---|---|---|
| 5–10 MB | 41 | 3 | 93,2% |
| 10–20 MB | 32 | 2 | 94,1% |
| 20–40 MB | 9 | 5 | 64,3% |
| **acima de 40 MB** | **0** | **10** | **0,0%** |

**A fronteira comercial não é a versão do DWG nem a cobertura média: é o peso do arquivo.** Acima de
40 MB o caminho livre não entrega **nada** — e é exatamente ali que mora o projeto executivo completo
(o `JS_PROJETO EXECUTIVO FINAL COM LAZER`, de 138 MB, é o retrato). Todos os 10 falham com a mesma
assinatura: `checksum CRC mismatch` seguido de `Invalid section_array_size`, que é o LibreDWG
esbarrando no próprio limite ao percorrer o mapa de seções de um DWG grande.

Isso **restabelecia a PRA.4 como degrau de plano em DWG**, e com um critério defensável e visível
antes de converter: o **tamanho**. Um plano de entrada que abre desenho de disciplina e um plano
superior que abre o executivo inteiro é uma fronteira que o cliente entende — e que a plataforma
consegue declarar no upload, sem gastar conversão para descobrir.

**O motor de 09/08/2026 tirou o chão de metade desse argumento.** Cruzando a remedição dos 160 com o
tamanho de cada arquivo em disco:

| Tamanho do DWG | Arquivos | Converteu | Taxa (0.14.8566) | Antes (0.13.3) |
|---|---|---|---|---|
| até 5 MB | 141 | 141 | **100%** | — |
| 5–10 MB | 9 | 9 | **100%** | 93,2% |
| 10–20 MB | 7 | 7 | **100%** | 94,1% |
| 20–40 MB | 2 | 2 | **100%** | 64,3% |
| acima de 40 MB | 1 | 0 | **0%** | 0,0% |

**A faixa de 20–40 MB deixou de ser degrau.** Acima de 40 MB o corpus tem **um** arquivo — amostra
que não sustenta nem derruba o teto —, e mesmo ele mudou de causa: falha por `recurso_excedido`, o
**nosso** orçamento de memória, e não mais pelo `checksum CRC mismatch` do decodificador. A pergunta
que decide o knob virou outra: não "o LibreDWG aguenta?", mas "quanto de memória o desenho grande
exige?".

#### Os 10 acima de 40 MB, remedidos — 09/08/2026

Feita sobre [corpus-grandes-10.txt](../../ferramentas/medicao/corpus-grandes-10.txt): os **10 DWGs acima de
40 MB que estão locais** no acervo (os outros 18 daquela faixa são placeholders do OneDrive, e
lê-los baixaria ~1,5 GB — a mesma restrição da medição de 01/08). Motor 0.14.8566, tetos de produção
(1.536 MB de orçamento, 300 s de relógio), lotes de 2. Relatório inteiro em
[resultado-2026-08-09-grandes.log](../../ferramentas/medicao/resultado-2026-08-09-grandes.log).

| Peso | Versão | Veredito | De quem é |
|---|---|---|---|
| 43,2 MB | AC1032 | **convertido** | — |
| 43,9 MB | AC1032 | **convertido** | — |
| 62,7 MB | AC1024 | `recurso_excedido` | **nosso** — orçamento de memória |
| 62,7 MB | AC1024 | `recurso_excedido` | **nosso** — orçamento de memória |
| 64,4 MB | AC1032 | `recurso_excedido` | **nosso** — orçamento de memória |
| 64,9 MB | AC1024 | `recurso_excedido` | **nosso** — orçamento de memória |
| 87,2 MB | AC1032 | **convertido** | — |
| 95,8 MB | AC1027 | `motor_insuficiente` | o cliente (premium) |
| 138,4 MB | AC1024 | `motor_insuficiente` | o cliente (premium) |
| 155,5 MB | AC1027 | `motor_insuficiente` | o cliente (premium) |

**Taxa: 30% (3 de 10).** O "0% acima de 40 MB" caiu, mas não virou 100%: o caminho livre passou a
entregar um terço da faixa que antes não entregava nada.

**O que este corpus derruba é o formato do knob, não só o seu valor.** `DWG_MB_MOTOR_LIVRE` é um
degrau por **tamanho**, e o tamanho não separa os baldes: um arquivo de **87,2 MB converteu** enquanto
**quatro de 62–65 MB** estouraram o orçamento. Não existe corte em MB que ponha os três convertidos de
um lado e os sete que falharam do outro — qualquer valor erra em pelo menos um. É a mesma lição do
[D57](../historico-correcoes.md) vista pelo outro lado: **tamanho não é proxy de custo**.

**O que separa, neste corpus, é a versão do DWG:** AC1032 (AutoCAD 2018+) converteu 3 de 4; AC1024 e
AC1027 (2010/2013) converteram **0 de 6**. Com 10 arquivos isso é indício, não regra — mas é o eixo
que a próxima medição deve testar, porque a versão também é legível **antes** de converter, que era a
virtude do degrau por tamanho.

**As duas metades da falha têm donos diferentes, e só uma é de venda:**

- **4 de 10 são `recurso_excedido`** — o nosso orçamento de 1.536 MB, não o motor. Vender premium por
  causa deles seria cobrar pelo nosso teto. A pergunta que a passada anterior já tinha aberto continua
  aberta e agora tem massa: *quanto de memória o desenho grande exige?* Ela mora em
  [`payment/planos.py`](../../payment/planos.py), no `PRANCHETA_CONVERSAO_MEMORIA_MB`, e não aqui.
- **3 de 10 eram `motor_insuficiente` — e os três foram investigados no mesmo dia, e o rótulo é
  falso** ([D78](../pendencias.md)). Rodado cru, o `dwg2dxf` converte os três com código 0 e `EOF`
  válido, produzindo intermediários de **705 MB, 1,05 GB e 952 MB**. O que os derruba dentro do
  pipeline é o **nosso** `RLIMIT_AS`, herdado pelo subprocesso: o LibreDWG não confere o `malloc`,
  morre com `SIGSEGV`, e "código ≠ 0" vira *"exige o motor de alta fidelidade"*. **Os 10 arquivos
  desta faixa não têm um único caso de limite real do motor livre.**

  A desconfiança que abriu a investigação foi a instrumentação: a `nota` guardava 120 caracteres
  **da cabeça**, e nos três sobrou o mesmo `Warning: Unstable Class object 501 MATERIAL`. Aceitar
  aquela classificação sem a prova teria dimensionado a PRA.4 sobre um artefato do nosso orçamento —
  que é a forma exata do [D43](../historico-correcoes.md), quando "o arquivo é ruim" virou, ao ser
  investigado, cinco bugs nossos e do escritor de DXF.

**Em aberto — o dono decide, não a engenharia:** o `DWG_MB_MOTOR_LIVRE` fica em 40 (avisa e deixa
passar, então não bloqueia ninguém) até que se escolha entre (a) mudar o valor, (b) trocar o eixo do
degrau — versão do DWG em vez de peso — ou (c) tirar o degrau e tratar a faixa como orçamento de
memória. Para (c) haver número, o parcial precisa **gravar pico e tempo por conversão**, que a PRA.1d
instrumentou no pipeline mas não persiste no relatório.

**Consequência para a PRA.4 — e a investigação dos três já aconteceu.** A leitura de 09/08 sobre o
corpus de 160 dizia que o DWG saíra da conta do premium; a passada dos >40 MB pareceu reabrir isso com
3 casos, e a investigação **fechou de novo, agora com prova**: os três convertem no motor livre, e o
que os derruba é o nosso teto ([D78](../pendencias.md)). Somando as duas passadas, o limite real do
caminho livre em DWG é **0% de 170 arquivos medidos**. A PRA.4 fica dimensionada por **RVT/NWD e
acabamento**, como a planta já mandava — e desta vez o número foi conferido nos dois extremos do
acervo, não só na média.

**O que sobra em DWG não é venda, é engenharia:** um intermediário de 1 GB para um DWG de 138 MB é
custo real de processamento, e a pergunta que ele abre é de orçamento — quanto a plataforma se dispõe
a gastar por conversão —, não de plano.

#### O custo medido, com o D78 fechado — 09/08/2026

Terceira passada sobre os mesmos 10, agora com a instrumentação v3 e **um container por arquivo**
(`LOTE=1`, que é o que torna o `ru_maxrss` do filho atribuível). Relatório em
[resultado-2026-08-09-custo-grandes.log](../../ferramentas/medicao/resultado-2026-08-09-custo-grandes.log).
As duas metades são medidas separadas porque estouram em lugares diferentes; aqui as duas em **RSS**,
para a comparação ser da mesma grandeza.

| Entrada | `dwg2dxf` | `ezdxf` | Tempo | Veredito |
|---|---|---|---|---|
| 43,2 MB | 220 MB | 739 MB | 14,1 s | convertido |
| 43,9 MB | 225 MB | 738 MB | 14,1 s | convertido |
| 62,7 MB | **≥2.036 MB** | — | 9,0 s | `recurso_excedido` |
| 62,7 MB | **≥2.035 MB** | — | 8,8 s | `recurso_excedido` |
| 64,4 MB | **≥2.036 MB** | — | 8,8 s | `recurso_excedido` |
| 64,9 MB | **≥2.036 MB** | — | 8,3 s | `recurso_excedido` |
| 87,2 MB | 416 MB | 1.158 MB | 17,4 s | convertido |
| 95,8 MB | **≥2.036 MB** | — | 8,7 s | `recurso_excedido` |
| 138,4 MB | **≥2.036 MB** | — | 9,1 s | `recurso_excedido` |
| 155,5 MB | **≥2.035 MB** | — | 10,5 s | `recurso_excedido` |

**O par que sozinho refuta qualquer linha em MB:** o arquivo de **62,7 MB exige mais de 2.036 MB** no
decodificador; o de **87,2 MB exige 416 MB** — no mesmo estágio e no mesmo motor. O menor custa **mais
de cinco vezes** o maior. Nenhum corte por peso põe os dois do lado certo, porque o mais pesado é o
mais barato.

**Dentro de uma mesma família de projeto, o peso prevê bem** — os três convertidos são projetos de
rede de água do mesmo escritório, e a razão custo/peso deles fica entre 12,6 e 17,1. É isso que fazia
o degrau parecer defensável: medido num acervo homogêneo, ele funciona. O acervo real não é homogêneo,
e é entre famílias que a previsão morre.

**A metade cara é o `ezdxf`, não o decodificador** — 3,3× · 3,3× · 2,8× o custo do filho nos três
medidos. Os dois orçamentos hoje estão dimensionados ao contrário disso: o subprocesso tem 2.048 MB e
o trabalho em processo, 1.536 MB. O arquivo de 87,2 MB usou **1.158 MB de RSS (1.094 de VA)** contra
esse teto — 71% dele. Um desenho um pouco mais denso passa a falhar na segunda metade, e a próxima
pergunta de orçamento é essa, não a do subprocesso.

**Sete dos dez pararam NO teto, e isso é piso e não exigência.** O que sabemos deles: precisam de mais
de 2 GB só para decodificar, e convertem quando soltos num container de 3 GB — a exigência real está
nessa faixa. Fechá-la custa medir com teto maior, o que é decisão de quem paga a máquina.

**Apertar não custou cobertura:** a taxa seguiu **30% (3 de 10)**, a mesma de antes do D78, embora o
filho tenha saído de ~2,6 GB herdados para 2.048 MB declarados. Nenhum arquivo que convertia deixou de
converter.

#### Dois caminhos de eficiência medidos e REPROVADOS — 10/08/2026

Registrados com número para não serem retentados: os dois parecem ganhos enormes no papel.

**`dwg2dxf -b` (DXF binário) — reprovado por quebrar o desenho.** O intermediário cai à metade e a
decodificação também:

| Entrada | Texto | `-b` |
|---|---|---|
| 43,2 MB | 125,8 MB · 2 s | 61,7 MB · 1 s |
| 62,7 MB | 498,8 MB · 11 s | 232,0 MB · 5 s |
| 95,8 MB | 705,4 MB · 29 s | 338,4 MB · 13 s |

E no pipeline o efeito era grande: memória em processo de 1.094 → 425 MB e tempo de 17,4 → 7,7 s no
arquivo de 87,2 MB. **Mas a taxa foi de 30% para 0%.** O escritor binário do LibreDWG **trunca o nome
das entradas de tabela no primeiro caractere**: o `ezdxf` morre em `DXFTableEntryError: S` procurando
o estilo de texto (`Standard`), e em outro arquivo `: C`. Três de três arquivos que convertem em texto
falharam em binário, com dois modos distintos. É a metade fraca do LibreDWG — a mesma que o
[D43](../historico-correcoes.md) mapeou, e que o [Dockerfile](../../backend/Dockerfile) já
descrevia como *"o escritor, a metade que a própria documentação do LibreDWG chama de fraca"*.
**Reabrir só faz sentido se o escritor binário for consertado a montante.**

**`dwg2dxf -m` (minimal) — reprovado por destruir a envolvente.** Encolhe muito mais que o `-b`
(705 MB → 5,5 MB no `Arq.dwg`) e **preserva a contagem de entidades** (16.392 de 16.394). Mas nos dois
arquivos em que a envolvente era calculável, ela virou `null`: as entidades sobrevivem como objetos e
perdem o que as posiciona (as definições de bloco vivem fora das `ENTITIES`). Sem envolvente não há
separação de folha, escala nem calibração por UTM — é o `--as rNNNN` do D43 outra vez, legibilidade
sem geometria.

**`ezdxf.options.load_proxy_graphics = False` — sem ganho mensurável.** A hipótese era que o *proxy
graphic* (desenho em cache de aplicativo ausente, que nunca usamos porque redesenhamos da geometria)
fosse parte da carga morta. No pipeline: 668 → 720 MB, 670 → 667 MB, 1.094 → 1.105 MB, tempos iguais
— ruído, com dois piorando. Não ficou no código.

**O que estes três deixam de pé:** o `-b` mantém tudo e é o formato que quebra; o `-m` corta demais; o
proxy não é o peso.

> ⚠️ **A tese desta seção foi MEDIDA e não se sustenta — leia o bloco "Corrigido" logo abaixo dela.**
> O texto fica como está porque é o raciocínio que levou à medição, e apagá-lo faria a mesma hipótese
> voltar como ideia nova.

#### A causa do custo: nós expandimos a repetição que o desenho descreve por referência

Medido em 10/08/2026, e é o que fecha a investigação. **Não é carga morta** — a hipótese de entulho
foi testada e refutada: das 289 e 508 definições de bloco dos dois arquivos mais pesados, **zero estão
ociosas**; todas são referenciadas. Os 92% de `BLOCKS` são geometria de verdade.

O peso está em **como** essa geometria chega ao SVG:

| Seção do intermediário | 04- Projeto de Agua | JS_PROJETO ESTRUTURAL |
|---|---|---|
| `BLOCKS` | **196,8 MB (92,3%)** | **462,2 MB (92,7%)** |
| `ENTITIES` | 12,6 MB | 34,8 MB |
| `OBJECTS` | 2,4 MB (1,1%) | 1,0 MB (0,2%) |

Um DWG guarda o bloco **uma vez** e o insere N vezes. O nosso caminho (`ezdxf` → SVG) **desdobra cada
inserção em geometria completa**: um arquivo com 858 inserções de 250 blocos vira 47.610 traços no
SVG e obriga o `ezdxf` a materializar tudo na memória — daí os 700 MB a 1,1 GB para um DWG de 43 MB.
O `dwg2SVG` do próprio LibreDWG emite `<g id="symbol-…">` uma vez e `<use>` para cada inserção,
preservando a repetição.

**A consequência é a resposta à pergunta que abriu tudo isto** (por que um arquivo pequeno custa mais
que um grande): custa mais o desenho que **repete mais**, não o que pesa mais. Repetição é barata no
DWG e cara no nosso SVG.

#### ❌ Corrigido em 10/08/2026: a repetição NÃO é a causa principal — medido no `ezdxf`

A tese acima foi construída comparando o **nosso** SVG com o do `dwg2SVG` (47.610 traços × 13.060) e
inferindo que a diferença era a expansão de bloco. A inferência estava errada, e o jeito de saber era
medir **dentro** do `ezdxf`, sem o `dwg2SVG` no meio — desenhar o modelspace de duas maneiras e contar
os registros do `Recorder`:

| | Registros | O que faz |
|---|---|---|
| **Hoje** — `draw_layout(msp)` | **47.610** | expande cada inserção em geometria própria |
| **Bloco uma vez** — `draw_entities(não-INSERT)` + cada bloco 1× | **30.603** | a economia proposta, no seu melhor caso teórico |

**1,6×, e não uma ordem de grandeza.** E o número que explica: o modelspace tem **53 blocos
distintos**, não os 250 que a leitura do `<defs>` do `dwg2SVG` sugeria — aquele número inclui o
paperspace e símbolos que o modelspace não usa. Com 53 definições, não há repetição suficiente para
que eliminá-la mude a ordem de grandeza: **a maior parte dos 47.610 registros é geometria direta do
modelspace**, que não tem o que deduplicar.

**Consequência para o roadmap:** as duas rotas investigadas em 10/08 estão medidas e as duas são
becos —

1. **trocar para o `dwg2SVG`** → ele erra o lugar de 44% das inserções (bloco anterior);
2. **desenhar cada bloco uma vez no nosso renderizador** → 1,6×, insuficiente.

#### ✅ ONDE O CUSTO ESTÁ — medido etapa a etapa em 10/08/2026

A pergunta certa ("quanto precisa existir de uma vez na memória") foi medida no mesmo dia, cronometrando
o RSS a cada etapa do caminho. O resultado encerra a investigação:

| Etapa | RSS acumulado | Custo próprio |
|---|---|---|
| `ezdxf.readfile()` — o DXF vira grafo de objetos Python | **396 MB** | **396 MB · 81%** |
| `+ Recorder` — a geometria gravada (2ª cópia) | 435 MB | 39 MB · 8% |
| `+ SVGBackend` — o SVG montado (3ª cópia) | 469 MB | 34 MB · 7% |
| **pico total** | **488 MB** | |

Soltar o documento do `ezdxf` devolve **386 MB** de uma vez — é o grafo, e só ele.

**A tese das "três cópias vivas" também cai:** a 2ª e a 3ª somam **73 MB**. Quem custa é a **leitura**,
não o desenho nem a emissão.

**E é isto que explica os dois becos anteriores.** Trocar o renderizador mexe na etapa 3 (7%);
deduplicar bloco mexe na etapa 2 (8%). Nenhum dos dois podia dar ordem de grandeza — os dois atacavam
15% do custo. O `dwg2SVG` parecia barato pelo motivo certo e pela razão errada: ele **não faz a etapa
1**, porque lê o DWG direto, sem intermediário e sem grafo de objetos.

**O alvo, então, é o par escrever→ler**, e ele tem duas frentes independentes:

1. **não materializar o DXF inteiro** — o `ezdxf` traz `addons.iterdxf`, leitor em fluxo feito
   exatamente para DXF grande demais para caber. Limite conhecido a verificar antes de prometer: ele
   entrega entidades do modelspace e **não** resolve `INSERT` (precisa das tabelas e do `BLOCKS`), o
   que exige uma passada própria para os blocos — que agora se sabe serem só 53;
2. **não escrever o intermediário** — hoje o `dwg2dxf` grava centenas de MB em disco para o `ezdxf`
   reler. Ligar os dois por *pipe* corta a ida ao disco, embora não corte o grafo.

**Nenhuma das duas está medida.** Ficam registradas como frentes, não como solução.

#### `dwg2SVG` — medido, e é outra ordem de grandeza

Mesmo binário que já distribuímos, mesma fronteira de licença (processo separado), **já instalado na
imagem** — hoje usado só como resgate.

| Arquivo | Caminho atual | `dwg2SVG` |
|---|---|---|
| 02 - Projeto de agua (43,9 MB) | ~945 MB · 13,9 s | **225 MB · 0,8 s** |
| 04- Projeto de Agua (87,2 MB) | ~1.520 MB · 17,2 s | **416 MB · 1,7 s** |
| JS_PROJETO ESTRUTURAL (62,7 MB) | **`recurso_excedido`** | 2.410 MB · 5,0 s |
| Arq.dwg (95,8 MB) | **`recurso_excedido`** | 3.069 MB · 27,1 s |
| JS 26062023 (155,5 MB) | **`recurso_excedido`** | 3.067 MB · 97,1 s |

**Fidelidade:** no `04- Projeto de Agua` a contagem de elementos bate em **99,7%** (32.013 × 32.097).
No `02 - Projeto de agua` a contagem **não** bate (47.610 × 13.739), e a diferença tem duas causas
somadas, ambas verificadas em 10/08: os blocos referenciados em vez de expandidos, e o nosso caminho
virando cada texto em **contorno** — o `dwg2SVG` emite `<text>`, e são 1.988 deles nesse arquivo.

#### A medição foi refeita: os números acima eram do *paper space*

**Achado ao conferir o formato de saída, 10/08/2026.** O `dwg2SVG` **sem flag desenha o paper
space** — uma *vista* do modelo —, e é assim que a primeira passada mediu. O `--mspace` (*"only
model-space, no paper-space"*) desenha o modelo, e no `02 - Projeto de agua` dobra o conteúdo: 5,1 →
**10,3 MB**, 13.060 → **27.729** `<path>`, 1.988 → **5.104** `<text>`.

**O custo não muda, e é isso que salva a comparação:** os bytes a mais vão para o stdout, não para a
RAM.

| | Caminho atual | `dwg2SVG` padrão | `dwg2SVG --mspace` |
|---|---|---|---|
| memória | ~945 MB | 220 MB | **220 MB** |
| tempo | 13,9 s | 0,8 s | **0,9 s** |
| saída | 11,7 MB | 5,1 MB | **10,3 MB** |

Então o ganho de **4,3× em memória e 15× em tempo** vale desenhando o modelo inteiro — mas `--mspace`
é **obrigatório** na adoção. Sem a flag, a troca entregaria meia prancha barata.

#### Duas correções que a adoção exige, achadas na mesma conferência

1. **O `viewBox` dele é inútil.** Ele declara `487789 8579416 2548 2106` (UTM) e **0,3%** da geometria
   cai dentro (65 de 18.774 pontos amostrados; o x vai de 12,5 a 490.334). Não é impeditivo — a
   separação de folha calcula a envolvente real de qualquer maneira —, mas significa que a saída do
   `dwg2SVG` **não é uma prancha pronta**: é matéria-prima. Aberta como está, o navegador mostraria
   quase nada, que é a tarja da §4.5 de volta;
2. **o texto sai com dois defeitos**, e são no que mais importa — carimbo, cota e legenda:
   os **`%%`-códigos não são decodificados** (`N.%%D` literal na tela, onde `%%D`=°, `%%P`=±,
   `%%C`=⌀) e o **`font-family="Courier"` está cravado** em todo `<text>`. Courier é monoespaçada, o
   pior caso de largura de glifo — exatamente a causa que a §4.3 já registra para carimbo desalinhado
   e cota vazando da caixa. Os dois se corrigem em pós-processamento, porque o SVG sai por nós.

**Ressalva do próprio autor**, que fica registrada: o `--help` do `dwg2SVG` diz *"Converts **some** 2D
elements of the DWG to a SVG"*. "Some" é palavra deles, e é o motivo de a fidelidade precisar ser
medida arquivo a arquivo antes da troca, não deduzida de dois casos.

#### ❌ REPROVADO como caminho principal: ele não coloca 44% dos blocos no lugar

**Medido em 10/08/2026, e é o que fecha a investigação do `dwg2SVG`.** Ao escrever o leitor de
geometria da PRA.1e — que resolve `<use>` aplicando a matriz de transformação, como o formato manda —
os números não fecharam, e o censo do arquivo de referência diz por quê:

| Elemento | Na página | Fora, mas explicável | **Em lugar nenhum** |
|---|---|---|---|
| `path` · `circle` · `ellipse` · `text` | 18.110 | — | 0 |
| `polygon` | 600 | — | **65** |
| **`use`** | **403** | 3 | **315** |

São **315 de 721 inserções de bloco (44%)** que não caem em lugar nenhum sob interpretação alguma. E
os `transform` deles mostram que não é convenção a descobrir, é número errado: `translate(478573,24
−2294249,61)` e `translate(−2300773,28 −446914,34)` **numa página de 2.548 × 2.106 unidades**.

**Duas hipóteses foram testadas e descartadas no caminho**, e ficam registradas para não voltarem:

1. *"o `<defs>` tem um deslocamento fixo, derivável do cabeçalho"* — **parcialmente verdadeiro e
   insuficiente**. Ele existe e é exatamente `(x0, −(y0+altura))`: descontado, `symbol-4B9` vira um
   bico de seta de 0,18 × 0,06 e `symbol-4C4` uma barra de 2 unidades, que é o que devem ser. Mas
   corrige **3** inserções e quebraria **403** que já estavam certas — o `dwg2SVG` mistura as duas
   convenções dentro do mesmo `<defs>`;
2. *"então decide-se símbolo a símbolo, pela distância à origem"* — implementado, e **também não
   fecha**: sobra o terço de `<use>` cujo próprio `transform` é impossível.

**A consequência para o custo, e é a parte que importa:** os **220 MB contra 945 MB** continuam
verdadeiros como número, e continuam **inúteis como promessa** — parte da economia é não desenhar os
blocos onde eles vão. Comparar o custo de um renderizador que erra 44% das inserções com o de um que
acerta 100% não é comparação.

**Para onde a PRA.1e vai, então.** A causa do custo segue valendo inteira — nós expandimos a
repetição que o desenho descreve por referência —, e ela não depende do `dwg2SVG` para ser atacada: o
caminho é **parar de expandir no nosso renderizador**. Cada definição de bloco é desenhada **uma vez**
pelo `ezdxf` (que já sabe desenhar e cuja saída é confiável), vira um `<g id="symbol-…">`, e cada
`INSERT` do DXF vira um `<use>` com a transformação lida **do próprio DXF** — que é a fonte em que se
pode confiar, ao contrário da que o `dwg2SVG` calcula. Isso preserva tudo o que já está provado
(folha, escala, âncora, texto em contorno, política de hachura) e ataca exatamente os 92% de `BLOCKS`
da tabela acima.

O que sobrevive do trabalho no `dwg2SVG`: ele **continua sendo o último degrau** (prancha com
convenção estranha é melhor que erro, e lá a alternativa é não entregar nada), agora com o
[D79](../historico-correcoes.md) guardando a saída; e o leitor de geometria escrito para ele
([svg_do_motor.py](../../backend/moduloprancheta/motores/svg_do_motor.py)) é reaproveitável, porque
separar folha lendo bbox de SVG é o mesmo problema nos dois caminhos.

**O que a adoção exige, e é o que a torna fatia e não ajuste** — a saída dele tem outra convenção:

1. **viewBox em coordenada de mundo** (`487789 8579416 2548 2106`, UTM) contra a nossa normalizada
   (`0 0 1000000 828005`). A escala por folha (§13.2) e a âncora de marcação, que é normalizada pela
   largura da folha, leem a nossa convenção;
2. **renderiza o *paper space*** por padrão (o SVG abre com `<!-- *Paper_Space -->`), enquanto o nosso
   caminho é modelspace com recuo para layout (D44);
3. **`<use>` em vez de geometria expandida** — ótimo para peso, mas a separação de folhas por lacuna
   (PRA.1c) mede envolvente de geometria, não de referência.

**Nenhum dos três é impeditivo; os três são trabalho.** O ganho que justifica: **10× no tempo, 3,7× na
memória, e três dos sete arquivos que hoje não abrem passam a abrir.**

#### O que foi implementado em 10/08/2026 — e o que ficou faltando

**Implementado: o `dwg2SVG` como ÚLTIMO degrau da escada** (`ECONOMIA_SVG_DIRETO` em
[base.py](../../backend/moduloprancheta/motores/base.py), `_svg_direto` em
[dwg.py](../../backend/moduloprancheta/motores/dwg.py)). Ele não economiza no desenho como os degraus
anteriores — ele **troca de renderizador**, saindo do caminho que expande a repetição.

Três propriedades que o tornam seguro nesta posição:

1. **só é alcançado depois de o orçamento estourar.** Arquivo que converte hoje nunca chega nele, e a
   alternativa nesse ponto não é uma prancha melhor, é `recurso_excedido` — nenhuma prancha. Prancha
   com a convenção do LibreDWG é melhor que erro;
2. **a saída se declara.** `detalhe` carrega `renderizador="dwg2SVG"` e `convencao="mundo"`, para a
   tela não aplicar por cima a normalização de folha que só vale para o nosso traço;
3. **a folha prova que desenhou** (`folha_destruida()`, [D79](../historico-correcoes.md)). O degrau
   pergunta duas coisas, nesta ordem: *saiu byte de traço?* (o arquivo vazio) e *o traço caiu em algum
   lugar?* (o arquivo **destruído**). A segunda existe porque o `dwg2SVG` publica o sentinela de
   extensão não apurada do LibreDWG — `viewBox` de ±1e20, todo traço colapsado no mesmo ponto — com
   `rc=0` e `<path>` de sobra. A ordem é contrato: invertê-la faria toda folha vazia mudar de coluna na
   fila do cockpit (§11), saindo do *"ninguém resolve"* para a conta que mede o **nosso** trabalho. E
   `viewBox` ausente ou ilegível **não** reprova — quem julga é a evidência de destruição, não a falta
   dela, senão um build novo do motor viraria acervo que para de abrir.

**Implementado junto: a escada aprendeu a saltar** ([pipeline.py](../../backend/moduloprancheta/pipeline.py)).
Quem levanta `RecursoExcedido` pode declarar `pular_para="…"`, e o `_para_dxf` declara o degrau do
`dwg2SVG`. Sem isso, um estouro no `dwg2dxf` percorreria os degraus que economizam no `ezdxf` — um
estágio que o arquivo nem alcançou — repetindo a decodificação inteira para falhar igual. Substitui o
`degradavel=False` que o D78 tinha posto ali, que era a resposta certa quando não existia degrau capaz
de ajudar.

**Não resolvido, e o motivo é aritmético:** o degrau roda sob os mesmos 2.048 MB de
`PRANCHETA_SUBPROCESSO_MEMORIA_MB`, e os 7 arquivos pesados pedem **2.410 a 3.069 MB** no `dwg2SVG`.
Faltam de 400 MB a 1 GB. O degrau é alcançado (o tempo por arquivo dobrou de ~9 s para ~18 s, que são
as duas tentativas) e estoura também. **A taxa dos 10 segue 30%.**

#### O custo do caso COMUM, medido arquivo a arquivo — 159 do corpus, 12/08/2026

As passadas de custo até aqui mediram os **10 pesados**, que é onde se esperava o problema. Esta mede
o corpus inteiro com `LOTE=1` (um container por arquivo, único jeito de o pico do filho ser
atribuível) e responde a pergunta pelo outro lado: *quanto custa o arquivo pequeno?* Relatório em
[resultado-2026-08-12-custo-160.log](../../ferramentas/medicao/resultado-2026-08-12-custo-160.log).

**Cobertura inalterada, e é o que autoriza ler o resto:** 158 convertidos de 159 (**99,4%**),
`motor_insuficiente` **0%**, e a única falha é o mesmo `J2 - S_PROJETO EXECUTIVO FINAL COM LAZER.dwg`
de 64,9 MB, por `recurso_excedido`. Nada regrediu desde 09/08.

**O corpus é de 159, não de 160** — a pasta `…/VCA/Terrenos/Benfica/` saiu do acervo entre 07/08 e
hoje, e com ela um arquivo. O `corpus_hash` mudou (`ab377b6a307f8d1d`) e o comando avisou, como
manda o D41. As taxas seguem comparáveis (159 de 160 é o mesmo conjunto menos um convertido).

**O arquivo pequeno é o caro, e a margem não é sutil:**

| Entrada | RSS em processo | Filho (`dwg2dxf`) | Tempo | MB de pico por MB |
|---|---|---|---|---|
| **1,0 MB** | 1.702 MB | 1.751 MB | 14,2 s | **≈1.700×** |
| **1,5 MB** | 1.764 MB | 1.756 MB | 15,4 s | ≈1.170× |
| **2,1 MB** | 1.778 MB | 1.755 MB | 18,5 s | ≈820× |
| 4,6 MB | 1.667 MB | 338 MB | 18,0 s | ≈350× |
| 9,6 MB | **2.249 MB** | 1.760 MB | 84,3 s | ≈230× |
| 21,9 MB | 36 MB | — | 3,7 s | 1,6× |
| 24,6 MB | 81 MB | — | 2,7 s | 3,3× |

**Por faixa, a mediana anda para trás:** 2–5 MB tem mediana de pico de **893 MB**; acima de 20 MB, de
**81 MB**. A faixa pequena custa **11× a grande na mediana** — e as duas pontas do acervo agora
dizem a mesma coisa, porque a passada dos >40 MB já mostrara 87,2 MB custando menos que 62,7 MB.
**Não existe corte em MB, em nenhuma direção, que ordene o custo.** O `DWG_MB_MOTOR_LIVRE` está
medido contra o eixo errado, e isto fecha a pergunta que o §12 item 00 deixou aberta: o eixo não é o
peso.

**14 dos 159 (8,8%) passam de 1 GB de pico, e 6 deles têm menos de 5 MB.** Não é a cauda de arquivo
executivo gigante: é prancha de disciplina, do tamanho que chega por WhatsApp.

**Quem já paga por isso é o cliente, hoje.** Sete arquivos só converteram **descendo a escada** para
hachura simplificada — e cinco deles têm ≤ 9,6 MB, três têm ≤ 2,1 MB. Um desenho de 1 MB já está
entregando prancha degradada, com a declaração honesta do §4.6, por um custo que o plano não previa.

**Um número que aperta a infra:** `--max-memory-per-child` (2.048 MB) foi ultrapassado por 2 arquivos
— 2.249 e 2.229 MB de RSS em processo. O filho do Celery é reciclado depois de cada um; a rede
funcionou, mas ela é rede.

**E um "platô do decodificador" que NÃO existe** — a passada relatou seis arquives parando o
`dwg2dxf` entre 1.751 e 1.760 MB, marca quase idêntica para entradas de 1,0 a 9,6 MB. Investigado no
mesmo dia, o número é **artefato do instrumento** ([D82](../pendencias.md)), e a seção abaixo mede o
que de fato acontece.

#### A causa do custo do arquivo pequeno: HACHURA — 12/08/2026

Os 6 do "platô" foram abertos um a um, com o `dwg2dxf` rodado **cru** e o desenho medido com a
hachura fiel contra a hachura em contorno. Duas coisas caem.

**1. O decodificador não é o custo — em 5 dos 6.** Rodado sozinho, o `dwg2dxf` pede:

| Entrada | Pico real do `dwg2dxf` | DXF gerado | Expansão | HATCH no arquivo |
|---|---|---|---|---|
| 1,0 MB | **23 MB** | 3,5 MB | 3,4× | 83 |
| 1,5 MB | **57 MB** | 10,2 MB | 6,8× | 44 |
| 2,1 MB | **55 MB** | 12,8 MB | 6,0× | 10 |
| 9,1 MB | **222 MB** | 44,5 MB | 4,9× | **1.395** |
| 9,6 MB | **230 MB** | 44,9 MB | 4,7× | **1.403** |
| 9,4 MB | **1.577 MB** | 9,0 MB | **1,0×** | 407 |

A última linha é a exceção e é real: o `Sensor de Incendio.dwg` faz o `dwg2dxf` gastar **1,5 GB para
produzir 9 MB de DXF** — patologia do decodificador, num arquivo só, e é o único caso de custo de
motor livre em todo o corpus.

**2. O custo é a hachura, e a prova é o contêiner morrendo.** Com a política fiel (`HatchPolicy.NORMAL`),
os 5 arquivos estouram **3 GB** e são mortos pelo kernel; com `SHOW_OUTLINE`, o mesmo desenho passa.
E o `ezdxf.readfile()` — o suposto dono de 81% do custo — custa aqui **78 · 129 · 134 · 123 · 317 MB**,
ou seja **5% a 15%** do total, não 81%.

**Isto não contradiz a medição de 10/08, delimita-a.** Lá o perfil foi levantado sobre um projeto de
rede de água, onde não havia hachura relevante e a leitura de fato dominava. **O caminho tem dois
regimes**, e o que decide qual vale é o *conteúdo* do desenho:

| Regime | Quem paga | Qual desenho |
|---|---|---|
| **leitura** (`readfile`, 81%) | o grafo de objetos | desenho de traço — rede, topografia, loteamento |
| **hachura** (o desenho, >90%) | a expansão do padrão | prancha de disciplina — hidráulica, PCI, estrutural |

**Por que o tamanho do arquivo não podia prever nada disso.** O DWG guarda a hachura como
**declaração** — *"preencha este contorno com o padrão X na escala Y"* —, algumas centenas de bytes.
Quem desenha precisa **expandi-la** em segmentos, e a contagem é proporcional à *área dividida pelo
espaçamento do padrão*: duas grandezas que o tamanho do arquivo não limita. Um arquivo de 1 MB pode
declarar trabalho ilimitado. **O custo acompanha o trabalho declarado, não os bytes** — e é a mesma
mecânica do incidente de 62 GB do [D57](../historico-correcoes.md), agora medida no caso comum.

O `ezdxf` tem defesa própria e ela aparece no log: *"hatching timeout of 30.0s reached for HATCH —
aborting"*, por hachura. Num dos arquivos ela disparou 6 vezes antes de o processo morrer — 3 minutos
gastos em 6 hachuras, e o relógio de 300 s do `PRANCHETA_CONVERSAO_SEGUNDOS` cobre ~10 delas.

**A escada já é o remédio, e ela funcionou** — os 7 arquivos que converteram com hachura simplificada
são estes. O que a medição muda é o **diagnóstico**: eles não são arquivos difíceis nem grandes, são
pranchas de disciplina normais, e o degrau que hoje é exceção é o caminho comum delas.

#### ✅ A hachura passou a ser desenhada COMO HACHURA — 12/08/2026

O conserto é de desenho, não de orçamento: em vez de expandir o padrão, emitimos **o contorno mais o
padrão**, que é o que o arquivo trazia. Mora em [motores/hachura.py](../../backend/moduloprancheta/motores/hachura.py),
com o enganche no `Frontend` e no `SVGBackend` do [motores/dxf.py](../../backend/moduloprancheta/motores/dxf.py).
Relatório em [resultado-2026-08-12-hachura-nativa.log](../../ferramentas/medicao/resultado-2026-08-12-hachura-nativa.log).

**Por que o SVG expressa isto sem aproximar.** Uma família de linhas de padrão DXF é um **reticulado**
— linhas paralelas repetidas a cada vetor de deslocamento, com tracejado periódico ao longo da linha —,
ou seja, uma malha gerada por dois vetores. O `<pattern>` do SVG ladrilha um retângulo sob um
`patternTransform` **afim arbitrário**, e essa matriz é exatamente a que leva o quadrado unitário no
paralelogramo do reticulado. Não há amostragem no meio: emite-se a mesma declaração que estava no
arquivo, e quem expande é o rasterizador do navegador — com o custo limitado pela **tela**, que é o
modelo do AutoCAD.

**O deslocamento não é perpendicular, e é por isso que a matriz importa.** Num padrão `_USER` ele é
(o desenho só declara espaçamento), mas os padrões de arquitetura escalonam as linhas: o `AR-SAND` do
acervo tem componente ao longo da própria linha, e quatro famílias. Largura e altura separadas
errariam justo esses; *stagger* é só um vetor não-ortogonal, e a matriz o carrega de graça. Padrão com
N famílias sai como N preenchimentos empilhados sobre o mesmo contorno — barato porque o que se repete
é o bordo (dezenas de comandos), não a área.

| Entrada | Antes (política fiel) | Depois | Hachuras |
|---|---|---|---|
| 1,0 MB | **morto a 3 GB** | **194 MB · 2,1 s** | 212 nativas |
| 1,5 MB | **morto a 3 GB** | **250 MB · 3,5 s** | 30 |
| 2,1 MB | **morto a 3 GB** | **310 MB · 5,9 s** | 7 |
| 9,1 MB | **morto a 3 GB** | **891 MB · 29,5 s** | 499 |
| 9,4 MB | **morto a 3 GB** | **457 MB · 15,0 s** | 178 de 184 |
| 9,6 MB | **morto a 3 GB** | **902 MB · 43,3 s** | 478 |
| 21,9 MB *(controle)* | 222 MB · 2,6 s | **222 MB · 2,5 s** | 0 |
| 24,6 MB *(controle)* | 209 MB · 0,9 s | **209 MB · 0,9 s** | 0 |

**Os dois controles são o número mais importante da tabela.** Desenho sem hachura sai **idêntico** dos
dois lados: nenhum caminho novo, nenhum custo novo, nenhuma folha diferente. A troca não tem como
regredir a prancha de traço, que é a maioria do acervo — a mesma garantia que o recorte da PRA.1c teve
de dar.

**E a folha melhorou junto com o custo.** Os seis não convertiam; quando convertiam em produção, era
**descendo a escada**, e o cliente recebia `hachura: contorno`. Agora saem `completa`. O degrau
continua no lugar como rede — para padrão que não ladrilha (reticulado degenerado, definição que o
`ezdxf` não resolve) o caminho antigo segue disponível, e o censo declara quantas hachuras saíram por
cada um (`hachuras_nativas`).

**Três armadilhas que a implementação teve de tratar, e as três são silenciosas:**

1. **A identidade viaja pelo `handle`, e o `handle` é da entidade de topo.** Dentro de um bloco ele é
   o do `INSERT`: marcar sem restaurar faria todo preenchimento seguinte do mesmo `INSERT` herdar o
   padrão — pintando de hachura um sólido que não é hachura. A marca é sintética e única por hachura
   desenhada, e o valor anterior é reposto. Guardado por teste próprio.
2. **Regra de CSS vence atributo de apresentação.** O `SVGRenderBackend` põe a cor de preenchimento
   numa classe; um `fill="url(#…)"` ao lado seria ignorado e a área sairia **sólida** — pior que o
   defeito original, porque parece certa. A classe não é aplicada nesse caminho.
3. **O conteúdo do ladrilho é recortado pelo ladrilho.** Linha na borda perde metade da espessura e o
   padrão sai mais claro do que é; ela é desenhada no meio, com meio deslocamento devolvido na
   translação para a fase não mudar.

**O que isto NÃO resolve**, e continua de pé: o regime de **leitura** (`ezdxf.readfile`, o desenho de
traço), que é a frente do `iterdxf`; e o `Sensor de Incendio.dwg`, cuja metade cara é o decodificador.

**Isto não muda a fronteira comercial, e reforça de onde ela não vem.** `motor_insuficiente` segue em
0%: nada aqui é limite do motor livre. O que a passada dimensiona é o **COGS por conversão** — e ele
confirma a candidata que o §4.6 já registrara, o **crédito de processamento**, porque o único proxy
que a plataforma sabe ler antes de converter (o tamanho) está agora refutado nas duas pontas.

**Custo da passada:** 159 containers, **14,8 min** de conversão somada.

### 4.2 Como o LibreDWG entra na imagem — e por que isso vira desenho

**O LibreDWG não é empacotado pelo Debian**: não há pacote `libredwg` em bookworm, trixie nem sid.
Como a imagem do backend é `python:3.12-slim` (Debian), não existe `apt-get install` que resolva, e
o binário entra **compilado de fonte** num *build stage* separado do
[`backend/Dockerfile`](../../backend/Dockerfile).

**A fonte era a tarball estável do `ftp.gnu.org`; desde 09/08/2026 é um commit fixado**
(`LIBREDWG_COMMIT`, hoje `a8ce2489` = `dwg2dxf 0.14.8566`). A razão de ter sido tarball continua
verdadeira — ponto fixo e publicamente arquivado torna a oferta de código-fonte da GPLv3 cumprível
sem esforço —, e é justamente por isso que a troca veio acompanhada de uma contrapartida: a imagem
passou a **carregar o fonte correspondente** (`git archive` do próprio commit, em
`/usr/share/licenses/libredwg/`), porque commit não é ponto arquivado. O que forçou a mudança foi
medida, não gosto: o 0.13.3 é o último release publicado, é de 2023, e 12 arquivos do corpus paravam
no decodificador dele ([D43](../historico-correcoes.md)).

**Subir o commit é mexer no motor que produz a taxa de cobertura** — exige remedir o mesmo corpus
(§4.1), nunca só conferir se builda.

Compilar código de 2023 com o compilador de hoje tem um preço fixo: o `configure` roda com
**`--disable-werror`**. O GCC 14 do `python:3.12-slim` estreou o `-Walloc-size`, que acusa dezenas de
`malloc()` menores que o struct em `src/encode.c` — e o `-Werror` do projeto os promove a erro, o que
derruba o build inteiro. Desligar é a decisão certa por dois motivos: o padrão acusado é intencional
lá em cima (o struct tem cauda de tamanho variável) e **`encode` é o escritor de DWG**, a metade que
o próprio LibreDWG chama de fraca e que este caminho não toca — o `dwg2dxf` decodifica. Manter o
`-Werror` deixaria o build do backend refém do aviso novo do GCC seguinte, em código de terceiro que
não vamos consertar. A instalação usa `install-strip`: o binário estático com símbolos de debug tem
66 MB, e sem eles 17 MB.

Isso tem uma consequência de produto, e ela é a razão de o fato estar aqui e não só no Dockerfile:
**a ausência do motor é um estado que o cliente pode ver**, e ele não pode ser confundido com o
limite de plano. Daí os dois motivos de erro distintos (§9):

- `motor_insuficiente` — *o seu arquivo exige o motor de alta fidelidade*. Limite de **plano**, a
  saída é comprar. É a frase que o DWG acima do alcance recebe.
- `motor_indisponivel` — *o motor não está neste servidor*. Problema **nosso**, a saída é deploy.
  Mandar o cliente comprar um plano melhor por causa de um binário que esquecemos de instalar
  venderia uma solução que não resolve o problema dele.

**A PRA.1b acrescentou um terceiro dono, e ele é o arquivo.** A remedição do
[D42](../historico-correcoes.md) mostrou um grupo que não cabia em nenhum dos dois acima: o arquivo não tem
desenho dentro (`desenho_vazio`), a geometria mora em XREF que nunca subiu (`referencia_ausente`) ou
o DWG não carrega a miniatura que o CAD grava (`sem_preview`). Chamá-los de "falha interna do motor"
confessa um defeito inexistente **e** enche a fila do que *nós* consertamos com linha que nenhum
conserto resolve — e uma fila cujo número nunca desce por mais que se trabalhe é uma fila que se
aprende a ignorar. Deles só o `referencia_ausente` é acionável, e por **quem enviou**; por isso a
fila do cockpit passou a contar por **quem age** (§11).

Remover o build stage **não quebra o sistema**: o adaptador não supõe que o binário exista e o
`GET /api/prancheta/status/` declara o motor como indisponível. O que se perde é DWG.

### 4.3 A fidelidade não é só do parser — o render sai de fábrica

Ler o DWG e **desenhá-lo** são dois problemas, e o segundo tinha knobs que o módulo nunca tocou até a
PRA.1b: o `ezdxf` era instanciado como `Frontend(RenderContext(documento), backend)`, **sem
`config=`**, então tudo era default. Medido dentro da imagem que roda (`ezdxf 1.4.4`):

| Opção | Valor de fábrica | Consequência |
|---|---|---|
| `lineweight_policy` | `ABSOLUTE` | **traço grosso**, e só em parte do acervo |
| `min_lineweight` · `lineweight_scaling` | `None` · `1.0` | nunca calibrados |
| `load_proxy_graphics` | `True` | — já ligado, **não** é causa de perda |
| `hatch_policy` | `NORMAL` | — hachura não é ignorada, **não** é causa |

**Por que o traço engrossa em umas pranchas e não em outras.** A política `ABSOLUTE` trata 0,25 mm
como 0,25 mm *de papel*. Só que a folha é auto-dimensionada (`Page(0, 0)`) com `scale=1.0`, então o
tamanho físico dela depende de **como o escritório modelou**. Medido com a mesma geometria em duas
unidades, num desenho de 841 unidades de largura:

| Modelagem | Folha gerada | Traço de 0,13 mm sai com | Razão |
|---|---|---|---|
| em **milímetros** | 861 mm | 1/6.623 da folha | traço fino normal |
| em **metros** | 20,8 mm | 1/160 da folha | **41× mais grosso** — empastado |

**A grandeza certa é a folha, porque espessura de linha é propriedade do papel.** É por isso que o
CAD plota: você escolhe um tamanho de papel e a pena vale milímetros *ali*. A saída é a política
`RELATIVE` do `ezdxf`, que amarra o traço ao lado maior da página, com o teto calibrado numa **folha
de referência A1** — `ESPESSURA_RELATIVA = 2,11 mm / 841 mm`, onde 2,11 mm é a espessura máxima que o
próprio DXF define. Medido depois: as duas modelagens acima saem com **frações idênticas**
(`0,000218 · 0,000356 · 0,000646 · 0,001224 · 0,002508`), e as cinco penas continuam distintas e em
ordem — a hierarquia que separa corte de hachura é o que uma espessura fixa (`RELATIVE_FIXED`)
destruiria.

**Foi a PRA.1c que tornou `RELATIVE` utilizável**, e é por isso que o D46 chegou a registrá-la como
inviável: enquanto a folha era o arquivo inteiro (469 m × 8,5 km no caso medido), 0,1% dela — o
padrão do ezdxf — dava traço de metros. Com um desenho por folha, a fração voltou a significar o que
diz.

#### O texto SHX — o que a medição corrigiu

A versão anterior desta seção afirmava que sem a fonte o desenho sai com *tofu* no lugar de cada
caractere, e que **nenhum caminho livre resolve**. As duas metades estavam erradas, e medir foi o que
mostrou:

- **não sai tofu.** O `ezdxf` cai no *fallback* — `LiberationSans-Regular.ttf`, que a imagem já traz
  por `fonts-liberation` — e desenha as letras. Verificado glifo a glifo (`IIIII` rende 309 bytes de
  path, `WWWWW` rende 1.924: são formas diferentes, não caixas). O que se perde não é o conteúdo, é a
  **forma**: uma sans-serif proporcional no lugar de uma monoline de traço, com larguras diferentes —
  o que desalinha carimbo e faz cota vazar da caixa;
- **existe caminho livre, e o `ezdxf` já o lê.** O pacote traz `fonts/lff.py` (LibreCAD Font Format) e
  o mapa `LFF_FONTS`, com resolução `resolve_shx_font_name(nome, "lts")` — LFF, depois TTF, depois o
  SHX de verdade. Falta só o **arquivo da fonte**: `font_manager.has_font("txt.lff")` responde
  `False`, e `ezdxf.options.support_dirs` está vazio.

O que sobra é uma decisão de licença, não de engenharia: as LFF do LibreCAD são GPL, e embarcá-las
faz a imagem redistribuir GPL **como dado lido em processo** — forma diferente da do `dwg2dxf`, que
é subprocesso (§4.2). A decisão está aberta e é do dono (§12, item 10). Enquanto não decidir, o texto
continua legível e com a forma trocada, e o carimbo desenhado *como o projetista o escreveu* segue
sendo diferencial do motor premium (§6).

### 4.4 O preview embutido — a única imagem que não é redesenho nosso

Todo DWG pode carregar um **thumbnail** que o próprio CAD gravou ao salvar, e o LibreDWG extrai esse
raster com o `dwgbmp` — ferramenta separada do `dwg2dxf`, do mesmo fonte já compilado no build
stage, e que a PRA.1b passou a instalar junto (era o [D49](../historico-correcoes.md)).

**O motor novo extrai menos preview, e isso foi medido e aceito** *(09/08/2026)*. Rodando os dois
`dwgbmp` sobre os mesmos 160 arquivos: **0.13.3 extrai 49, o 0.14.8566 extrai 40** — 11 arquivos
perdem a miniatura e 2 ganham. É regressão de verdade, e vem de graça junto do commit que levou a
conversão de 84,4% a 99,4%.

**Aceita porque o alcance dela é zero onde ela importa:** os **11 convertem**. Quem perdeu a miniatura
do CAD passou a mostrar o cartão com o **nosso** redesenho, que é melhor — vetorial, com zoom e
medição. O valor do preview embutido está escrito duas linhas acima: *"inclusive quando a conversão
falhou, que é justamente quando o cliente fica sem nada para ver"*. Nenhum dos 11 está nesse caso.

**Gatilho de reabertura:** um arquivo que **falhe na conversão** e também não dê preview no 0.14. Aí
o cartão fica vazio de verdade, e o conserto já está desenhado — `dwgbmp` e `dwg2dxf` são binários
independentes, então basta um segundo *build stage* com o 0.13.3 fornecendo só o `dwgbmp`. Custa um
compile a mais no build da imagem, e é por isso que não se paga antes de precisar.

Isso não é conversão: é a figura que o AutoCAD fez. Vale como **cartão do acervo** e como resposta a
*"é esta prancha mesmo?"* — inclusive quando a conversão falhou, que é justamente quando o cliente
fica sem nada para ver. O limite é o que ele é: raster de baixa resolução, sem zoom útil e sem
medição. Por isso é fonte de miniatura, nunca de prancha, e a procedência (`preview_embutido`)
aparece na tela.

**Duas linhas no banco, não uma.** O `MotorDwg` declara `tipos = ("vetor_2d", "miniatura")`, então o
mesmo arquivo rende duas `DerivadaProjeto` independentes — e é isso que faz **uma sobreviver à falha
da outra**, que é o ponto inteiro. Três consequências a honrar:

- o gate de versão (`ALCANCE_LIVRE`) **não** se aplica à miniatura: o R2024 é justamente onde a
  prancha não sai, e onde a figura do AutoCAD é a única coisa que o cliente teria para ver;
- **a ausência de preview não é avaria.** Depende de o escritório salvar com `RASTERPREVIEW` ligado, e
  arquivo gerado por script sai sem. Motivo próprio (`sem_preview`, §9), fora da fila do que se
  conserta;
- **o código de saída não denuncia a ausência.** Medido no binário 0.13.3: sem thumbnail o `dwgbmp`
  imprime *"No thumbnail image"*, **sai com 0** e não escreve arquivo nenhum. Quem responde é o
  destino existir e ter tamanho — a mesma armadilha que o `-y` do [D34](../historico-correcoes.md) cobrou caro.

O `dwgbmp` entrega **o que estava lá dentro** (BMP, PNG ou WMF; não converte entre eles). Pillow lê os
dois primeiros; WMF é vetorial do Windows e não abre sem renderizador externo, então esse caso vira
ausência declarada com a assinatura na memória de conversão — para a estatística existir antes de
alguém decidir se vale um renderizador de WMF.

### 4.5 Um desenho, uma folha — separar sem apagar

**Uma revisão não é uma prancha**, e essa premissa estava errada desde a PRA.0. O `ezdxf` dimensiona
a página pela extensão do que foi desenhado, e o DWG de construtora não traz *um* desenho: traz a
mesma área na origem e em coordenada UTM (o `confrontantes.dwg`, com duas poligonais de 1.089 × 861
unidades, 169 traços cada, a 8,5 milhões de unidades uma da outra), ou o *sheet set* inteiro montado
no modelspace — dezenas de plantas em grade. Numa folha só isso vira uma página de **469 m × 8,5 km**,
com aspecto 1:18, onde cada desenho ocupa 0,2% da largura.

E o limite não é estético: um `<img>` com essa página tem tamanho intrínseco de **1,77 milhão ×
32,4 milhões de pixels CSS**. Nenhum navegador rasteriza isso — a folha existe, o desenho está lá, e
a tela mostra uma tarja.

**Apagar o que está longe continua recusado**, pelas duas razões de sempre: a plataforma não sabe o
que é lixo (um traço solto pode ser o marco topográfico que alguém foi a campo levantar), e o caso
real não tem lixo nenhum — qualquer recorte agressivo o bastante para isolar uma poligonal apagaria a
outra. **A saída não é escolher uma folha, é dar uma folha a cada desenho.** Nada é descartado; o que
muda é que cada aglomerado ganha a página que lhe cabe, e com ela a própria régua.

O motor **grava antes de desenhar** (o `Frontend` escreve num `Recorder`, não direto no `SVGBackend`),
separa os aglomerados e reproduz cada um com `crop_rect`:

- **o corte é onde a lacuna é maior que o próprio desenho** — a referência é o **maior** dos dois
  vizinhos. Com o menor, um ponto solto a 5 cm de uma planta separaria por qualquer vazio e a folha
  normal se estilhaçaria; com o maior, planta e corte lado a lado continuam juntos (100 mm de vazio
  contra 800 mm de desenho) e 50 plantas em grade viram 50 folhas (1.000 contra 800);
- **desenho sozinho não passa pelo recorte** — a folha sai idêntica à de antes desta mudança, então a
  prancha comum, que é a esmagadora maioria do acervo, não tem como regredir. É também o que faz
  marcação e medição já existentes continuarem sobre exatamente a mesma geometria de página;
- **o traço solto vira a própria folha**, de um registro, com a contagem no rótulo. Não é escondido
  nem apagado: fica navegável, e quem julga é o dono do arquivo;
- **aglomerado que não desenha nada não vira folha, e isso não vai à tela.** A régua é "o que tem
  desenho é para ser mostrado, o que não tem pode ser ignorado". O `MaxPlast.dwg` traz **513 registros
  de extensão zero exatamente na origem** — que são **51 arcos de raio zero do bloco `onibus`,
  repetidos nas 10 inserções dele**: as 39 linhas de cada ônibus estão desenhadas, no lugar certo,
  dentro do Desenho 1. Não há geometria perdida, e esses arcos degenerados é que esticavam a página de
  UTM até (0,0) — são a causa da extensão absurda do [D46](../historico-correcoes.md). O censo fica na
  `memoria` da derivada (`desenhos_sem_traco`, `registros_sem_traco`), que é onde se audita conversão;
  contá-lo no aviso alarmava sem informar e mandava o leitor procurar um desenho que não existe.

A envolvente de cada folha viaja em **unidade de desenho**, não normalizada, e é essa a identidade que
atravessa revisões: a folha muda quando o projetista mexe no desenho, o lugar no terreno não (§9).

#### A aba de layout já É uma folha (PRA.1b, [D44](../historico-correcoes.md))

Quando o modelspace não desenha nada, o motor cai nas **abas de layout** — e ali a unidade que a
§4.5 inventou já existia no arquivo: um layout é uma folha física, com moldura, carimbo e legendas.
Três decisões, e as três vêm do que o paperspace **é**:

- **sem separação por lacuna.** No modelspace a lacuna distingue desenhos que só por acaso moram no
  mesmo arquivo; num layout, partir moldura de carimbo por causa do vazio entre eles inventaria duas
  pranchas onde o projetista vê uma;
- **ordem de aba, e o nome da aba vira o nome da folha.** É a única vez em que este módulo recebe um
  nome escrito por gente sem pedir a ninguém — "PLANTA BAIXA - PAV TIPO" é melhor que "Desenho 1".
  Vale só para folha nova: renomear na tela é soberano, como a calibração;
- **nenhuma régua sai daqui, e essa é a armadilha da fatia.** No paperspace a unidade é a da **folha**
  (milímetro de papel), não a do modelo. Publicar aquela largura como `escala_largura_m` faria a tela
  responder "0,84 m" para uma fachada de 30 m — e o valor cairia *dentro* da janela de plausibilidade
  sem disparar nada, que é o pior desfecho possível neste módulo (§13.2). Quem cai no paperspace mede
  em fração da largura e a memória de conversão diz por quê (`escala_indisponivel: paperspace`).

**Limite declarado:** o caminho só existe quando o modelspace produz **nada**. Um arquivo cuja folha
está no layout mas que tem três entidades soltas no modelspace continua sendo desenhado por elas —
comparar os dois espaços para escolher "o melhor" é heurística que erraria calada, e a fatia preferiu
consertar exatamente o caso que hoje dá erro duro.

**Efeito colateral que vale registrar:** com a folha certa, a grade de saída volta ao padrão do
`ezdxf` — o alargamento que existia para impedir o desenho de ser *destruído na emissão* (segmentos
arredondados para `l -0 -0`) deixa de ser necessário, e o SVG emagrece. O mecanismo fica no código
como rede de segurança, não como remédio de uso diário.

#### O que isso custa, medido

| | `confrontantes.dwg` | `MaxPlast.dwg` | `UFRB…-IE` (folha normal) |
|---|---|---|---|
| folhas | 2 | 2 | 1 |
| página | 1.109 × 881 mm cada | 5.415 × 2.998 mm · 1.221 × 867 mm | 177 × 65 mm |
| SVG | 182 KB cada | **13,6 MB** + 453 KB | 3,4 MB |
| conversão | 0,2 s | **26 s** | 6,4 s |

Os dois números em negrito são o limite honesto do caminho atual: agora que a geometria não é mais
destruída na emissão, ela pesa o que pesa. A conversão é assíncrona e não faz ninguém esperar, mas
13,6 MB no 4G do canteiro é muito — é exatamente o que o render vetorial do §12.6 resolve, porque um
buffer de coordenadas é uma fração de um SVG que descreve as mesmas linhas em XML.

### 4.6 O orçamento de uma conversão — e por que ele é de produto, não de operação

A medição do §4.1 cobrou um preço que a planta não previa: uma prancha do acervo real expandiu
hachura até **62 GB de RAM**, e a conversão **não tinha teto de recurso nenhum** ([D57](../historico-correcoes.md)).
Os `TIMEOUT_SEGUNDOS` que existiam cobrem os *subprocessos* (`dwg2dxf`, `dwgbmp`); a metade cara — o
`ezdxf` desenhando — roda em processo, e ninguém a limitava.

**A leitura certa não é "a medição pesou".** O mesmo caminho roda em worker compartilhado, sobre
arquivo que qualquer cliente sobe, e em produção sobre máquina paga. Sem teto, o custo por upload é
ilimitado e imprevisível — o oposto exato da regra de que o plano básico não pode custar nada ao
dono (§6.1). E nenhuma das três camadas de limite da plataforma pega isto: a
[D23](../historico-correcoes.md) limita entrada, a [D22](../historico-correcoes.md) limita saída, a
[D24](../historico-correcoes.md) conta objetos e seats. **Ninguém limitava cômputo**, que é onde mora o COGS
real deste módulo.

**O desenho segue o que plataforma de mídia faz com upload pesado**, em quatro movimentos:

| Movimento | Como fica aqui |
|---|---|
| **frota separada** | fila `conversao` + serviço `worker-conversao` no compose, com `mem_limit`/`cpus` próprios. Transcodificação nunca divide processo com cobrança, e-mail e NF — quando o kernel escolhe uma vítima por memória, ele não sabe qual task estava emitindo um boleto |
| **teto por job** | `orcamento_de_conversao` em [limites.py](../../backend/moduloprancheta/limites.py): `RLIMIT_AS` faz a explosão virar `MemoryError` (exceção Python, capturável) e `SIGALRM` corta o relógio. **Os dois números vivem em [payment/planos.py §5.4](../../payment/planos.py)** desde 08/08/2026 — eram default de `settings.py`, que é arquivo de deploy, enquanto os gêmeos do import/export já eram do dono. A variável de ambiente continua sobrescrevendo: uma VM pequena tem outro orçamento, e isso é operação |
| **degradação em camadas** | miniatura embutida (instantânea, já existe) → render simplificado → folha completa. **Cada camada diz o que é** — nada de armengar uma prancha pior fingindo ser a boa. A folha publica `hachura` em três estados (`completa` · `parcial` · `contorno`) e o aviso da prancha traduz cada um; `completa` não gera frase, porque avisar que está tudo certo treina o canteiro a fechar o aviso sem ler |
| **medir para precificar depois** | tempo e pico de **cada** conversão vão para a memória de conversão, em `memoria["custo"]` — é o número que o paywall vai precisar, e ele existe desde o [D82](../historico-correcoes.md). O §4.7 diz por que medi-lo é mais difícil do que parece |

**A escada tem um degrau, e ele é `SHOW_OUTLINE`.** Lendo o dispatch do `ezdxf 1.4.4`, essa política
faz o `draw_hatch_pattern` inteiro ser **pulado**: o custo cai de "uma linha por passada do padrão
sobre a área" para O(bordo), e é essa garantia de convergência que um degrau precisa ter. As duas
alternativas caem por motivo próprio: `SHOW_SOLID` custa o mesmo e **pinta por cima** de cota e texto
(a tarja preta do §9.06 de novo), e `SHOW_APPROXIMATE_PATTERN` está no enum sem nenhum ramo que o
trate — desenha igual ao `NORMAL`, com o custo dele.

**Quem desce a escada é quem provou não caber.** A primeira passada é sempre a fiel, e a degradação é
decidida pelo orçamento **tendo sido estourado** — nunca por um limiar que adivinhe o peso do
arquivo. É o que garante que nenhuma prancha que hoje converte bem mude de aparência: degradar por
palpite trocaria um problema de custo por um de confiança, e a prancha do cliente é o produto.

A escada mora no **pipeline** e não no motor, porque é lá que o orçamento é armado: dentro do motor a
segunda passada herdaria o que a primeira consumiu do relógio e do teto, e estouraria já degradada.
E o motor recusa descer quando não há hachura no arquivo — desenhar sem hachura o que não tem hachura
é repetir a conversão que acabou de falhar, gastando outro orçamento para chegar ao mesmo lugar.

**O teto só existe se ninguém o embrulhar no caminho.** `RLIMIT_AS` age levantando `MemoryError`, que
é `Exception` como qualquer outra — e os `except Exception` que dão dono à falha de leitura e de
desenho o capturavam antes de o orçamento poder traduzi-lo. O estouro virava `falha_motor`
(`retentavel`: três vezes o mesmo estouro, pela DLQ) ou `arquivo_corrompido`, que culpa o arquivo do
cliente por um limite nosso. O `NAO_EMBRULHAR` é a lista do que atravessa esses `except` intacto, e é
o que faz a escada existir de fato.

**A regra é do contrato de motor, e levou um dia para chegar lá.** Ela nasceu dentro do `dxf.py` — que
foi onde a medição doeu — e ficou só ali: PDF, imagem, IFC e o preview embutido do DWG seguiram
embrulhando `MemoryError`, cada um com a frase errada da sua família. Dois casos valem registro porque
mostram formas diferentes de o mesmo defeito se esconder: no **IFC**, a metade cara (tesselação do
OpenCascade) traduzia para `FalhaMotor`, que é **retentável** — a DLQ repetia três vezes um estouro
determinístico, três picos de memória pelo preço de um upload; no **preview do DWG**, virava
`SemPreviewEmbutido`, motivo da família *"ninguém age"* (§11), ou seja, o teto agindo sem aparecer em
fila nenhuma. Desde 07/08/2026 o `NAO_EMBRULHAR` mora em
[motores/base.py](../../backend/moduloprancheta/motores/base.py) e vale para os quatro motores; motor
novo herda a regra, e uma varredura de AST sobre os adaptadores **registrados** (não sobre uma lista
escrita no teste) cobra o `except NAO_EMBRULHAR` de todo `except Exception` que troque a exceção por
outra — com controle negativo, porque teste estrutural que nunca dispara passa igual num código onde
a regra foi apagada.

**Limite declarado — o teto de memória não alcança o C++ da mesma forma.** `RLIMIT_AS` faz o `malloc`
falhar para todo mundo, mas só o CPython transforma isso em `MemoryError`: no OpenCascade a falha
aparece como `std::bad_alloc`, que pode chegar como exceção traduzida pelo binding, como falha
genérica ou como *abort* do processo. Nos dois primeiros casos o `NAO_EMBRULHAR` não ajuda (não é
`MemoryError`) e o desfecho é `falha_motor` — errado no dono, certo em não cobrar do cliente; no
terceiro, quem age é o `mem_limit`/`--max-memory-per-child`, e a derivada fica presa em `convertendo`,
que é justamente o que o orçamento existe para evitar. **Por que não está resolvido:** o remédio é
tesselar em subprocesso (como o `dwg2dxf` já é), e isso é a fatia que também resolve o §12.4 — o
`ifcopenshell` é a dependência mais pesada da imagem e a primeira candidata a sair para um worker
próprio. O `TETO_ELEMENTOS` de 250 mil cobre o caso comum por contagem, mas **depois** de o parser já
ter lido o arquivo inteiro.

**Os três freios, e por que são três.** `mem_limit` do container protege a **máquina** (e a fatura da
VM); `--max-memory-per-child` protege a **fila** de um vazamento lento, reciclando o processo;
`orcamento_de_conversao` protege o **cliente**, e é o único que transforma o estouro em frase legível.
Por isso ele é o mais apertado dos três: quem estoura primeiro tem de ser quem sabe explicar. Os
outros dois só matam processo, e processo morto deixa a derivada presa em `convertendo` para sempre.

**`recurso_excedido` é motivo próprio, e não é upsell.** Reusar `tempo_excedido` traria o
`retentavel = True` junto — repetir uma conversão que estourou o orçamento reproduz o estouro, três
vezes, por conta da DLQ. E `falha_motor` diria que o motor quebrou, quando ele foi **interrompido por
nós**. Vender a APS aqui seria cobrar do cliente por um limite nosso, e nada garante que o motor
premium aguente o mesmo desenho: a fronteira comercial continua sendo a do §4.1, medida.

**O que fica para o paywall decidir** (estudo, não decisão): se o custo por conversão é ilimitado
hoje e o tamanho do arquivo **não** é proxy dele — os arquivos que estouraram a RAM passam folgado no
teto de MB do §6.1 —, então a unidade de cobrança candidata deste módulo é **crédito de
processamento**, medido como a família de COGS já declarada e inerte (IA, NF, boleto). O número que
falta para decidir é o consumo real por conversão, que a instrumentação acima passa a produzir.

### 4.7 Medir o custo de UM arquivo — e as três vezes em que medimos outra coisa

O número que o §4.6 pede parece trivial de obter e não é. Três vezes este projeto publicou um custo
de recurso que media outra grandeza, e as três produziram conclusão de **produto**:

| | O que se lia | O que era |
|---|---|---|
| [D76](../historico-correcoes.md) | "o plano dá 1.536 MB à conversão" | o `RLIMIT_AS` contava o processo inteiro; a conversão recebia ~384 MB |
| [D78](../historico-correcoes.md) | "3 arquivos exigem o motor premium" | o `RLIMIT_AS` herdado matava o subprocesso; os três convertem no motor livre |
| [D82](../historico-correcoes.md) | "6 arquivos custam ~1.755 MB no `dwg2dxf`" | `ru_maxrss` de `RUSAGE_CHILDREN` é **marca d'água acumulada**, e conta as páginas que o filho herdou do pai no `fork`. Custam 23–230 MB |

**A causa das três é a mesma, e vale escrever como regra: um contador que só cresce não responde
"quanto custou este arquivo".** Marca d'água (`ru_maxrss`, RSS de processo de vida longa) nunca desce
— o segundo arquivo herda o pico do primeiro, e subtrair antes/depois não salva, porque a diferença
dá **zero** para todo arquivo que não bateu o recorde. Num worker Celery que converte centenas de
arquivos no mesmo processo, isso não é imprecisão: é somar o acervo inteiro e atribuir a soma a
quem passou por último.

O medidor mora em [nucleo/consumo.py](../../backend/nucleo/consumo.py), ao lado do
[orcamento.py](../../backend/nucleo/orcamento.py) — teto e medidor são a mesma grandeza vista de dois
lados, e duas cópias divergiriam. Três regras, e as três são sobre atribuição:

1. **o pai por janela, não por processo** — amostragem em thread, com a linha de base subtraída;
2. **o filho por dentro, não por herança** — o `VmHWM` do `/proc` do próprio subprocesso, que o
   `exec` zera. É a diferença entre medir o `dwg2dxf` e fotografar o pai no instante do `fork`;
3. **não medido ≠ zero** — subprocesso curto demais para cair numa amostra sai `n/d`. Zero se leria
   como "não custou nada", e é a irmã que faltava da marca `≥`, que já existia para pico censurado
   por teto.

O que **pode** ser somado é tempo de CPU: é contador monotônico, então a diferença é o gasto da
janela. Confundir as duas coisas é o D82 em uma frase.

**A amostragem tem um buraco, e quem o fecha é o cgroup.** As três regras acima resolvem *atribuição*
e não resolvem *cobertura*: amostrar a 50 ms perde o pico que dura menos que isso, e no acervo de 159
arquivos isso foi **76 arquivos sem número** — quase metade do corpus. O kernel já mantém essa conta
sem amostrar. Um cgroup v2 criado para a janela tem `memory.peak` começando em zero, e como o v2 não
migra a cobrança das páginas que o processo já tinha, o que ele acumula é a memória **nova** da
operação — pai e subprocessos juntos, sem linha de base a subtrair e sem herança de `fork` a
descontar. As duas grandezas convivem porque respondem a perguntas diferentes:

| | responde | quem consome |
|---|---|---|
| `pico_cgroup_mb` | **quanto** a máquina precisou ter, exato | `mem_limit` do worker, dimensionamento |
| `pico_filho_mb` / `pico_va_mb` | **onde** o custo aconteceu | decidir qual metade otimizar |

E a diferença entre elas não é de precisão, é de grandeza: em teste controlado (13/08/2026) o cgroup
leu **454 MB** onde `max(filho, em_processo)` dava 372 — as duas metades **coexistem**, e o maior
das duas nunca foi o pico da operação. O número que dimensiona a máquina estava subestimado.

**É opt-in de deploy, e a trava que o protege é o caminho de volta.** Um cgroup por operação exige um
diretório `cgroup2` delegado e gravável (`SGI_CGROUP_MEDICAO`); sem ele, a janela cai na amostragem e
declara isso em `custo["fonte"]`. O medidor **testa se consegue voltar antes de sair**: medido em
container real, uma delegação montada fora do cgroup do container mede certo, não consegue devolver o
processo e o deixa **fora do próprio cgroup** — o `mem_limit` do §4.6 deixaria de valer, e o terceiro
freio simplesmente sumiria. Medir melhor não vale perder o freio que protege a máquina, então a
configuração insegura não liga.

**O custo é dado de primeira classe da derivada**, em `memoria["custo"]`, gravado também no caminho
de erro — `recurso_excedido` sem quanto custou é veredito sem prova. Num arquivo multifolha ele vai
**só na folha #1**: uma conversão produz N folhas de uma passada só, e repetir o custo em cada linha
faria qualquer soma multiplicar a conta pelo número de folhas — o mesmo erro, cometido no relatório.
A leitura é o comando
[`custo_do_acervo`](../../backend/moduloprancheta/management/commands/custo_do_acervo.py), que separa
o que **se soma** (CPU, relógio, bytes de entrada — conta de custo) do que **não se soma** (pico de
memória — conta de dimensionamento, e é ela que decide o `mem_limit` do worker). A tabela por
**caminho de arquivo** do acervo real está em
[docs/medicoes/custo-acervo-160.md](../medicoes/custo-acervo-160.md).

**O caminho da pasta sobrevive à importação, e custou o campo que já se sabia custar.** A
`RevisaoDocumento` guarda `caminho_origem` além do `nome_original`: o lote da R18 sempre leu o
caminho relativo para adivinhar disciplina, código e revisão, e apenas o descartava em seguida.
Como o acervo real tem nomes repetidos entre subpastas (`006.dwg`, `AEGS06.DWG`), o nome não
identifica o arquivo — sem o campo, *"de qual pasta do escritório veio esta prancha?"* só tinha
resposta enquanto alguém ainda tivesse a pasta, e a tabela de custo precisou reconstruir a coluna por
SHA-256 contra ela.

É **texto de quem enviou e não decide nada**, pela mesma regra do `nome_original`: não escolhe motor,
não vira caminho de gravação (quem grava é `caminho_revisao`, a partir de tenant e obra) e é
`read_only` no serializer — campo de rastreabilidade que o próprio cliente reescreve por PATCH é o
oposto de rastro. Fica vazio em todo acervo carregado antes desta fatia, e nada quebra com isso: o
relatório usa o campo quando existe e cai no pareamento por SHA-256 quando não.

## 5. Arquitetura proposta

```
Arquivo (upload/seam)  ──►  Derivada (pipeline Celery)  ──►  Visualizador (React)
   RVT/DWG/IFC/DXF            web-nativo: glTF/Fragments,        um só, por tipo de
   KMZ/SHP/LAS/PDF            SVG/tiles, MVT, COPC               derivada — não um
                              + memória de conversão             viewer por formato
```

- `ArquivoProjeto` — o arquivo como o cliente o entregou (obra/etapa, disciplina, **revisão**,
  procedência), `TenantScopedModel` com RLS fail-closed. Revisão é cidadã de primeira classe:
  a pergunta do canteiro é *"esta é a última?"*.
- `DerivadaProjeto` — o produto da conversão, com o **motor que a gerou** carimbado. Um arquivo tem
  N derivadas (o mesmo IFC vira Fragments para o 3D e SVG para a prancha).
- **A conversão é assíncrona e falível por natureza** — Celery, estado visível, e o motivo do erro
  na tela. Um RVT de 300 MB não converte no request.
- **Entitlement:** `RequireModule("prancheta")`; permissões `prancheta.*` no padrão
  `modulo.recurso.acao` do [catálogo da IAM](../acesso-e-permissoes.md).
- **Importação em lote** entra pelo [`funcoesimpexp`](funcoesimpexp.md), que já resolve conferência
  linha a linha e desfazer — não se escreve um segundo importador.

## 6. Paywall — caso a caso, por plano

Decisão do dono: **não há um "pacote Prancheta"**. Cada capacidade é um knob em
[`payment/planos.py`](../../payment/planos.py) — plano que abre tudo, plano que abre uma parte. O que
isso exige do desenho: **o formato é a unidade de cobrança**, então o gate mora no motor de
conversão (não na tela), e a quota de tradução paga (APS) é medida por arquivo, como as demais COGS.
A régua de dados honestos vale aqui também: formato não contratado aparece **travado com o motivo**,
nunca escondido.

**Onde cada metade mora, e por quê:** o **vocabulário** (que formatos existem, por qual extensão
chegam, por qual assinatura de bytes são reconhecidos, qual motor os abre e sob qual licença) é
engenharia e vive em [`backend/moduloprancheta/formatos.py`](../../backend/moduloprancheta/formatos.py);
**quais** deles cada plano aceita — e **até que tamanho** — é comercial e vive em
[`payment/planos.py`](../../payment/planos.py). É a mesma separação que `nucleo/quotas.py` faz com
`QUOTAS_DE_OBJETO`, e pelo mesmo motivo: o dono do software mexe no segundo sem abrir o primeiro.
Os dois lados precisam casar, e um teste falha nas **quatro** divergências possíveis — formato
vendido que não existe no registry, formato vendido cujo **motor** o plano não habilita (o caso do
RVT, que só a APS traduz: o upload passaria, ocuparia storage pago e a conversão nunca rodaria),
formato do registry **sem teto** declarado, e teto **acima** do que o caminho de upload direto
aguenta.

> **O tamanho mudou de lado em 08/08/2026** *(decisão do dono: todo teto ou limite vive em
> `payment/`)*. Os MB por formato eram campo do registry, escritos ao lado da assinatura de bytes;
> viraram [`PRANCHETA_MB_POR_FORMATO`](../../payment/planos.py) §5.3, e com eles foram o teto do
> snapshot e os três da leitura de BCF. O que revelou a regra foi pequeno e exato: a recusa por
> tamanho é sempre **402**, e o 402 diz *"faça upgrade do plano"* — uma frase que só é verdade se o
> número for do dono. Enquanto o teto do snapshot era constante de engenharia, o sistema oferecia um
> upgrade que nenhum plano vendia. De quebra sumiu um número duplicado: `TETO_UPLOAD_DIRETO_MB` e
> `IMPEXP_TETO_INFRA_ARQUIVO_MB` diziam 300 cada um, em arquivos diferentes.

**A recusa é na entrada, e responde 402 — não 403.** O cliente não está *proibido* de subir um RVT;
ele não contratou o plano que o abre, e a saída é comprar. O corpo espelha o da `QuotaExcedida` de
`nucleo/quotas.py` para o frontend tratar **um** contrato de parede comercial. Extensão que nenhum
plano abre, essa sim, é **400**: mandar pagar por algo que o produto não lê seria pior que recusar.

### 6.1 A regra de custo que decide o motor premium

**O plano básico não pode custar nada ao dono; o premium é comprado e distribuído.** Essa regra não é
comercial só — ela **elimina uma das opções técnicas**:

| Motor premium | Como cobra | Encaixa? |
|---|---|---|
| **APS / Model Derivative** | **por arquivo traduzido**, sem piso | ✅ só custa quando um usuário premium converte |
| ODA (*Sustaining*) | milhares de USD **por ano**, fixos | ❌ custo antes do primeiro cliente premium |

Por isso a PRA.4 é a APS, e não a ODA, apesar de a ODA ter a melhor qualidade do mercado. O mesmo
critério reprova qualquer dependência de licença comercial fixa no caminho básico — o `PyMuPDF`
(AGPL/comercial) é o exemplo que já apareceu, ao ser avaliado como backend PDF do `ezdxf`.

**O que o plano básico entrega, e é grátis de verdade:** o caminho livre inteiro (LibreDWG + `ezdxf`),
o preview embutido (§4.4) e **marcar e medir** — a §13 é código próprio, com o BCF lido e escrito por
`zip` + `ElementTree`, sem nenhuma dependência de terceiro a licenciar.

**O que o plano pago compra, em ordem de visibilidade para o cliente:** o **texto do carimbo e das
cotas** (SHX, §4.3 — hoje desenhado em Liberation Sans, com a forma trocada), a fidelidade geral do
desenho, os formatos que só a APS traduz (RVT/NWD) e o **DWG acima do teto de tamanho**.

#### O teto de tamanho do DWG — o degrau que a plataforma sabe antes de converter

O número vive em [`payment/planos.py::DWG_MB_MOTOR_LIVRE`](../../payment/planos.py) e é **medido**
(§4.1): acima de **40 MB** o caminho livre não entrega nada — 0 de 10 arquivos, todos com a mesma
assinatura de CRC. É a única fronteira do módulo que se conhece **pelo peso do arquivo**, sem abrir
nada, e por isso a única que pode ser dita **no upload**.

**Avisa e deixa passar.** Recusar venderia como fronteira de plano um motor premium que ainda não
existe (PRA.4): o arquivo entra no acervo, continua baixável na íntegra, e reconverte sozinho quando
o motor melhor chegar — porque a `DerivadaProjeto` é única por motor. Duas frases, porque são dois
problemas: quem não contratou o premium tem o que comprar; quem contratou merece ouvir que ele ainda
não está ligado neste servidor, que é a mesma distinção que `pipeline._traduzir` faz *depois* da
falha. A tela recebe o teto no catálogo de formatos (`motor_livre_max_mb`), então pode avisar antes
mesmo de o arquivo subir.

**Isso valeu até 09/08/2026, e a segunda metade caiu.** A PRA.1b concluiu que "o teto é do binário e
não há para onde subir", porque a 0.13.3 era a última estável publicada em `ftp.gnu.org` (26/02/2024)
e trocá-la por uma nightly encareceria a oferta de fonte da GPLv3. O [D43](../historico-correcoes.md)
fez a troca: commit fixado (`0.14.8566`), fonte da GPLv3 **embarcado na imagem**, e a cobertura do
mesmo corpus passou de 84,4% para **99,4%** — com a faixa de 20–40 MB saindo de 64% para **100%**.

**O teto de 40 MB segue no plano, e agora é o *eixo* dele que está em dúvida, não só o valor.** A
remedição dos 10 arquivos acima de 40 MB ([§4.1](#41-o-nó-do-dwg--não-há-caminho-grátis-e-limpo),
09/08/2026) mediu **30%** de conversão nessa faixa — o "0%" que originou o degrau caiu — e mostrou que
**nenhum corte em MB separa os baldes**: 87,2 MB converteu, 62–65 MB estourou o orçamento. Das 7
falhas, **4 são do nosso teto de memória** e só 3 são do motor, essas com a causa cortada pela
instrumentação. Mexer no número sem escolher o eixo (peso × versão do DWG × orçamento de memória)
seria trocar um palpite por outro. Nota completa em
[payment/planos.py §5.1](../../payment/planos.py).

## 7. Seams (o que conversa com o quê)

| Módulo | Seam |
|---|---|
| [obras](obras.md) | todo arquivo pendura em obra/etapa — é o eixo que o SIL e o Orçamento já falam |
| [Maps](modulomaps.md) | prancha georreferenciada vira camada; o `Local` da obra centra o modelo no mundo |
| drone | ortofoto e nuvem de pontos abrem na mesma tela — **projeto × as-built**, a comparação que hoje ninguém faz |
| [Orçamento](moduloorcamento.md) | horizonte 4D/5D: linha orçada ↔ elemento do modelo (quantitativo extraído do BIM). **O ponto de pouso já existe do lado de lá desde o ORC.7:** `LinhaMedicao` guarda a parcial do quantitativo com `referencia_projeto` — a extração do modelo entra como mais uma parcial, ao lado das digitadas, e não pede model novo. É o que o Arquimedes/CYPE faz a partir de DWG/DXF e Revit, e é a única lacuna do orçamento que depende de um módulo que ainda não existe |
| [PDCA](modulos-planejados.md) | o 4D depende do cronograma físico de lá; a FVS aponta para o ponto do modelo |
| [funcoesimpexp](funcoesimpexp.md) | carga em lote de acervo, com conferência e desfazer |
| DMS ([funcoesimpexp](funcoesimpexp.md) §13) | a Prancheta **abre**; o DMS registra e coordena (guardados, entraram, saíram) e governará distribuição, aprovação e assinatura. É dele também a **capacidade de PDF** (marca d'água, carimbo, juntar/dividir), cujo endereço já está reservado em [modulos-planejados.md](modulos-planejados.md) |

## 7.1 A porta de leitura do acervo — por que não `/media/`

O arquivo (original e derivada) **sai por endpoint da API**, nunca pela URL de mídia do `FileField`.
Nenhuma resposta da API publica caminho de mídia — `arquivo` é campo **write-only** no upload e sai
como `arquivo_url` já apontando para o gate.

> **PRA.5a — a rota mudou de dono, o contrato não.** As três ações `arquivo/` que ficavam neste módulo
> saíram: hoje a saída é `GET /api/impexp/prancheta.acervo/arquivo/{revisao|derivada}/<id>/` e
> `GET /api/impexp/prancheta.marcacao/arquivo/snapshot/<id>/`. **São dois recursos porque são dois
> gates** — o acervo é `prancheta.documento`, a marcação é `prancheta.marcacao`, e a segregação da
> PRA.3 não podia ser apagada por conveniência de agrupamento. O que ficou aqui é o que de fato é
> deste módulo: **qual MIME cada formato tem** (o motor não conhece DWG nem glTF) e as URLs que o
> serializer publica. O frontend não mudou uma linha — ele consome `arquivo_url`.
>
> As três decisões abaixo continuam valendo palavra por palavra; o que mudou é que elas deixaram de
> ser reimplementadas aqui e viraram [`funcoesimpexp/entrega.py`](../../backend/funcoesimpexp/entrega.py),
> valendo para todo módulo que sirva arquivo.

Os dois motivos se somam, e um deles só apareceria em produção:

- **`/media/` não existe fora de `DEBUG`**: `config/urls.py` só monta `MEDIA_URL` em desenvolvimento;
  em produção o gateway encaminha `/media/` ao backend, que responde 404. O visualizador nasceria
  apontando para o vazio;
- **e, quando existe, é aberto**: o `django.views.static.serve` não passa por autenticação,
  entitlement nem RLS — quem soubesse o caminho leria a prancha de qualquer tenant. É o mesmo buraco
  do **S10** (assets do drone) que o **MAP.3** recusou repetir ao trazer o tile da ortofoto para
  dentro do backend.

Três decisões de entrega que valem para qualquer módulo que sirva arquivo:

- **o `Content-Type` sai do registry**, não do nome do arquivo — `nome_original` é texto do cliente, e
  deixá-lo decidir seria dar a quem envia o poder de escolher como o browser interpreta o upload;
- **nada é servido como página**: `nosniff` + `Content-Disposition: attachment` em tudo, inclusive o
  SVG da derivada (documento executável). A tela o exibe por `fetch`+blob dentro de `<img>`, onde
  script não roda — então um `<script>` que atravessasse o conversor não vira XSS na nossa origem;
- **cache `private, immutable` de um ano, com a versão na URL**: o arquivo da revisão é write-once
  (§9) e `immutable` nele é verdade. A **derivada não é** — a linha é única por `(revisão, tipo,
  motor)` e é reescrita a cada reconversão (`reprocessar/`, motor novo, upgrade para a APS). Por isso
  a URL da derivada carrega `?v=<hash de origem + motor + conclusão>`: sem ela, `immutable` significava
  que **ninguém que já abriu a prancha veria a conversão consertada**, e o sintoma acusa o lado errado
  (o cliente jura que nada mudou, e está certo sobre o que vê). Com a versão, `immutable` volta a ser
  verdade e o cache offline da §8 passa a saber quando a prancha mudou.

## 8. Conectividade — online, e o offline como expansão

**Decidido: a 1ª fatia é online.** O canteiro já tem 4G/5G; desenhar em torno de "internet ruim"
seria pagar a complexidade de um PWA com cache por um problema que o cliente não tem. A tela carrega
a derivada do servidor, como qualquer outra do sistema.

O que se faz **agora** é não fechar a porta — na régua dos seams declarados e inertes (a mesma da
Esfera de Rede no SCM):

- **derivada imutável e endereçável** — cada `DerivadaProjeto` tem conteúdo fixo e URL estável por
  revisão. É isso que torna cache possível depois: o cliente offline nunca precisa perguntar "mudou?"
  para um arquivo que, por construção, não muda — revisão nova é derivada nova.
- **a revisão é quem invalida**, não um TTL. Já é assim para a tela online (a pergunta do canteiro é
  *"esta é a última?"*), e é exatamente o gancho que um cache precisaria.

Com esses dois, cache offline (ou app nativo) vira **acréscimo**, não reescrita.

## 9. Modelos

Três tabelas sustentam o acervo, e a separação entre elas é a resposta à pergunta do canteiro
(*"esta é a última?"*); as quatro seguintes sustentam a **marcação** (§13):

| Modelo | O que é | Chaves |
|---|---|---|
| `DocumentoProjeto` | o documento **lógico** — "Planta baixa pavimento tipo", disciplina, obra/etapa. Não guarda arquivo | `unique(tenant, obra, codigo)` |
| `RevisaoDocumento` | cada **revisão** (R00, R01…): o arquivo como o cliente entregou, autor, data, `hash`, formato e situação (`rascunho`/`vigente`/`superada`) | `unique(tenant, documento, revisao)`; só **uma** vigente por documento |
| `DesenhoProjeto` | **uma folha da revisão** — a página que se abre, mede e marca. Ordem, nome dado por gente, envolvente em unidade de desenho, contagem de traços e a **escala** (§13.2) | `unique(revisao, ordem)` |
| `DerivadaProjeto` | o produto da conversão, por revisão, **desenho** e tipo (2D, 3D, miniatura), com o **motor e a versão do motor** carimbados, estado, motivo do erro, `hash_origem` e a memória de conversão | `unique(revisao, tipo, motor)` quando não há desenho; `unique(revisao, tipo, motor, desenho)` quando há |
| `Marcacao` | o **tópico BCF**: o que precisa ser resolvido nesta prancha — título, tipo, situação, prioridade, responsável, prazo, rótulos + a âncora **na folha em que foi fincada** | `unique(tenant, guid)` |
| `PontoDeVista` | o `Viewpoint` do BCF — câmera 3D (preservada como veio) e/ou **snapshot** do trecho | `unique(tenant, guid)` |
| `ComentarioMarcacao` | o `Comment` do BCF — a conversa que faz do apontamento um laço, e não um recado | `unique(tenant, guid)` |
| `Medicao` | distância ou área sobre uma folha, com a **escala carimbada** no momento da medida | — |

Consequências de desenho que valem registrar:

- **A folha é a unidade que se abre, mede e marca — não a revisão.** É por isso que a escala mora no
  `DesenhoProjeto` e não no `RevisaoDocumento`: `escala_valor` é *"quantas unidades reais cabem na
  largura inteira"*, e as coordenadas de marcação e medição são normalizadas por essa mesma largura.
  Com duas folhas de tamanhos diferentes na mesma revisão, um número só descreveria no máximo uma
  delas — **e em silêncio para a outra**, que é como erro de escala vira parede no lugar errado.
  `Marcacao` e `Medicao` apontam para a folha pelo mesmo motivo.
- **O nome da folha é de gente, e atravessa revisões.** Vazio é o estado normal, e a tela mostra
  `Desenho N` (ou `Traço solto`, para o aglomerado de um registro) — guardar o rótulo automático como
  valor de fábrica tornaria impossível distinguir o que o sistema gerou do que alguém escolheu. Quando
  a revisão seguinte chega, o nome é herdado pelo desenho de **maior sobreposição de envolvente**
  (interseção sobre união ≥ 0,5, em unidade de desenho), não pela ordem: o projetista mexe no desenho
  entre a R01 e a R02 e a ordem pode trocar, mas o lugar no terreno não. Sem candidato bom o bastante,
  o desenho nasce sem nome — herdar por proximidade vaga poria o rótulo certo no desenho errado, que é
  o defeito que ninguém confere. A herança fica registrada em `herdado_de`, para o nome que aparece
  sozinho numa revisão nova não ser indistinguível de um que alguém digitou ali.
- **Reconverter não apaga o que é de gente.** O pipeline reaproveita a linha de mesma `ordem`, então
  nome e calibração sobrevivem ao `reprocessar/`. Folha que a conversão nova não produziu mais é
  removida, e a marcação dela **fica** (`SET_NULL`), sem pino e dizendo por quê — perder o apontamento
  do canteiro por causa de uma decisão nossa seria perder trabalho de campo.
- **Revisão nova é linha nova, nunca UPDATE.** É o que torna a derivada imutável (§8) e o que permite
  ao campo comparar R01 com R02 em vez de descobrir que o desenho mudou embaixo dele. Na prática isso
  significa **arquivo write-once**: trocar o arquivo de uma revisão existente é recusado com 400, e
  não só porque contradiz a regra — hash, formato e tamanho passariam a descrever o arquivo anterior,
  que é justamente o que o pipeline lê para decidir se reconverte.
- **`vigente` é ato, não campo.** Não se muda a situação por `PATCH`; muda-se por `publicar/`, que é o
  verbo com permissão própria. Se fosse campo comum, a segregação de alçada seria decoração. O mesmo
  ato em massa é `POST revisoes/publicar-pendentes/ {"obra"}`, com a **mesma** permissão e alcance só
  sobre documento **sem** vigente — sem ele, exercer a alçada num acervo histórico custava um clique
  por prancha, e o resultado medido foi ninguém exercer ([D85](../historico-correcoes.md)).
- **A derivada carrega a versão do motor.** Motor novo (upgrade do `ezdxf`, troca de APS por
  pipeline própria) invalida por comparação, sem precisar de flag manual. Junto com `hash_origem`
  (SHA-256 do arquivo de origem no momento da conversão) é a **chave de idempotência** do pipeline:
  a dupla que ainda bate é pulada, qualquer outra reconverte. Como o arquivo é write-once, na
  prática quem invalida é sempre o motor.
- **A conversão falha, e a falha é dado.** Estado e motivo ficam no modelo e aparecem na tela — a
  régua de dados honestos vale para o erro também. São **seis** motivos, e a distinção entre os dois
  primeiros (`motor_insuficiente` × `motor_indisponivel`, §4.2) é a que não pode ser refeita em cada
  tela: por isso o serializer expõe `exige_upgrade` como campo, e a fila de decisão do cockpit conta
  as duas coisas **separadamente** — o que o cliente resolve comprando e o que nós resolvemos
  consertando.
- **A memória de conversão é dado do projetista.** `memoria` guarda o que o motor conseguiu ler:
  versão do DWG, schema do IFC, se o DXF precisou de reparo. É o insumo do `medir_cobertura_dwg` e o
  que dá uma resposta melhor que "deu erro".
- **Motor sem adaptador não gera derivada.** Um formato vendido cujo motor ainda não existe (RVT,
  que espera a APS da PRA.4) **não** nasce como linha `pendente`: ela ficaria pendurada para sempre
  e "aguardando conversão" viraria mentira permanente. O planejamento devolve vazio e quem explica o
  vazio é o `status/`, que declara cada motor em três colunas — `habilitado` (o **plano** vende),
  `implementado` (o **código** tem) e `disponivel` (esta **imagem** tem instalado).
- **Mas a ausência de linha não prova a ausência de motor.** O `agendar()` cria a derivada de forma
  **síncrona**, antes de enfileirar: motor planejado implica linha existindo, nem que seja `pendente`.
  Então zero derivadas com motor planejado é o estado inverso — o motor existe e a conversão **nunca
  foi agendada** (revisão gravada fora do pipeline, `on_commit` perdido). O resumo responde
  `nao_agendada`, e não `sem_motor`: a saída de um é reprocessar e a do outro é esperar a fatia que
  traz o motor. Confundi-los manda o cliente comprar plano por causa de um job que não rodou — a
  mesma troca de ator que `motor_insuficiente` × `motor_indisponivel` evita do outro lado.
- Todas as tabelas são `TenantScopedModel` com **RLS fail-closed**, como o resto da plataforma.

**Upload é caso à parte:** o [`nucleo/upload_validation.py`](../../backend/nucleo/upload_validation.py)
de hoje (A4) tem teto pensado para foto e documento. Um RVT de 300 MB não passa, e afrouxar o teto
global para caber CAD abriria a porta em todos os outros módulos. O teto é **por formato** — um PDF
não precisa do mesmo espaço que um IFC —, e desde a PRA.5a quem o aplica é a porta única, pelo gancho
`Recurso.teto_mb_do_formato`; desde 08/08/2026 quem o **declara** é
[`payment/planos.py`](../../payment/planos.py) §5.3, porque todo teto é knob do dono (§6).

**O teto de cima é do caminho, não do formato**, e isso é um limite consciente: o multipart do request
carrega o arquivo inteiro numa chamada, então há um teto de **300 MB**
(`IMPEXP_TETO_INFRA_ARQUIVO_MB`) acima do qual nenhum formato pode declarar. Não é o que os formatos
precisam (um E57 de levantamento real passa de 10 GB) — é o que este caminho aguenta. Subir o teto
exige **upload retomável** (chunked/presigned), que é fatia própria; até lá, o teste falha se alguém
declarar um formato acima dele, para o limite não ser esquecido e virar timeout na cara do cliente.

## 9.05 Carga real — a prancha pesada no navegador

Medido em 02/08/2026 com prancha de verdade do acervo, pelo gateway, no Chrome: um projeto de
**instalações elétricas** (`UFRB-CTC-SEG-PE-002-IE`, duas plantas de pavimento com legendas, carimbo
e tabela de penas) — **35.401 traços, 3,33 MB de SVG**.

| Passo | Tempo |
|---|---|
| upload do DWG pelo gateway | 0,0 s (1,7 MB) |
| conversão (assíncrona, no worker) | **6,1 s** |
| baixar a derivada pela porta gateada | 0,0 s (3,33 MB) |
| **abrir no visualizador** (blob → `<img>` → desenho na tela) | **0,19 s** |
| mover (arrasto contínuo) | **60 fps** (mediana 16,7 ms · p95 16,8 ms) |
| zoom até 2445% | **60 fps**, e o traço continua vetorial — sem pixel |

**O visualizador aguenta.** A escolha do `<img>` com `transform` CSS (§7.1) paga aqui: o navegador
rasteriza uma vez e o movimento vira composição, então arrastar uma prancha de 35 mil traços custa o
mesmo que arrastar uma foto. O gargalo do módulo **não é a tela** — é a conversão, que é assíncrona
por desenho e por isso não faz ninguém esperar.

**O que o mesmo teste expôs:** uma prancha pode converter com `pronto`, abrir em 0,19 s e a 60 fps, e
ainda assim mostrar **uma tarja preta** — quando a folha sai com quilômetros porque o arquivo tem
duas áreas distantes. Foi o [D46](../historico-correcoes.md) e depois o [D52](../historico-correcoes.md), e a resposta
final está na §4.5: o problema não era o zoom nem a folha grande demais, era **haver uma folha só**.

**Estes números descrevem o `<img>`, e é ele que vai sair.** Os 60 fps saem de o navegador rasterizar
uma vez e o movimento virar composição — o que também é o motivo de o zoom ter teto e de não haver um
vértice acessível para snap. A troca pelo render vetorial (§12.6) tem de **repor** este patamar, não
supô-lo: ≥30 fps no `MaxPlast`, que é 62.433 entidades contra as 35.401 medidas aqui.

## 9.06 O zoom — porque é ele que resolve a prancha difícil

O visualizador nasceu com limites de zoom **absolutos** (`0,02×` a `40×`), que servem enquanto a
prancha tem tamanho de prancha. Numa folha de aspecto 1:18 o ajuste inicial produz `z = 0,0000261`, e
aí os dois limites viram armadilha: o primeiro clique do scroll cai em `max(0,02; …)` e **salta 766×
de uma vez**, o desenho passa voando, e o teto de 40× fica muito abaixo dos **~7.865×** que ler uma
das poligonais exige.

**Os limites passaram a ser relativos ao ajuste** (`0,2×` a `50.000×`): um clique é sempre um clique,
em qualquer prancha. E o percentual também — **100% = ajustado à tela** —, porque absoluto ele abria
marcando `0%`, um número que não informa nada e faz a tela parecer quebrada antes de alguém tentar
mover. Acima de 20× o rótulo vira `7.865×`, que é a grandeza que o CAD usa nesse patamar.

Sobre essa base, quatro maneiras de chegar ao desenho — nenhuma delas mexendo no arquivo:

| Gesto | O que faz |
|---|---|
| roda do mouse | aproxima **acelerando**: giro rápido (< 120 ms entre eventos) aumenta o expoente até 3 cliques num. É o "gira devagar para ajustar, rápido para atravessar" que a mão já sabe |
| **Shift + arrastar** | *zoom window* — enquadra a área do laço. Fica atrás do Shift porque o arrasto simples é mover, e no canteiro mover é o gesto de todo minuto |
| duplo clique · Shift + duplo | aproxima · afasta, onde se clicou |
| `+` · `−` · `0` | aproxima · afasta · volta ao ajuste |

**Trocar de desenho deixou de ser zoom.** Enquanto tudo vivia numa folha só, chegar ao segundo
desenho era voar 7.865× até um canto da página, e a tela oferecia atalhos para isso. Com cada desenho
na própria folha (§4.5) o gesto é outro: abre-se **outra prancha**, pela lista lateral (§9.1), e o
zoom volta a ser o que o CAD chama de zoom — navegar dentro do desenho que está aberto.

**O teto que sobra não é o do código.** Os limites relativos cobrem o que a prancha pede, mas o
`<img>` tem um teto próprio: o navegador rasteriza a folha, e rasterização sempre acaba. Zoom sem teto
prático — o do AutoCAD — exige geometria viva no cliente, que é a decisão do §12.6.

## 9.1 A tela — o canteiro, não o escritório

A Prancheta é **lente na topbar** (ao lado de Mapas e Calendário), não item de sidebar: não é um lugar
do ciclo, é o projeto consultado de qualquer ponto dele. A rota `/app/prancheta` fica **fora** do
`ModuleRoute` pelo mesmo motivo do Maps — a tela que explica o módulo é justamente a que quem não o
contratou precisa ver; o gate real é o do backend.

**A tela não herda a moldura dos outros módulos**, e isso é decisão de desenho: cockpit com KPIs em
cima é linguagem de escritório. Aqui o primeiro toque abre uma prancha.

### Três telas, e nenhuma aba

O módulo teve seis abas (Início · Pranchas · Histórico · Acervo · Conversões · Formatos) e não tem
mais nenhuma. O motivo é que elas não eram seis assuntos: **quatro delas eram o mesmo `useAcervo` com
filtros diferentes** — `inicio`, `pranchas`, `acervo` e `conversoes` rodavam o mesmo
`flatMap(g => g.documentos)`, mudando só o recorte — e as outras duas falavam de **uma prancha
específica**, que é justamente o que a pessoa tem na frente quando faz a pergunta.

O sintoma disso está registrado duas vezes no próprio módulo: o `AcervoPendente` nasceu como *"a
faixa que fecha o buraco entre as abas"* (141 pranchas convertidas que o canteiro não abria, com o
diagnóstico numa aba e o remédio noutra), e o `publicarUma` nasceu três semanas antes pelo mesmo
motivo. Duas emendas para a mesma causa: **o corte por aba particiona por estado do objeto, e a
pessoa navega por tarefa.**

| Tela | O que é | Quem vê |
|---|---|---|
| **A grade** | as pranchas da obra, ordenadas favorita → mais aberta → resto | todos |
| **A prancha** | o desenho em tela cheia + as gavetas (folhas · apontamentos · entregas) | todos |
| **A entrada** | pôr projeto novo dentro — o único gesto que não é de nenhuma prancha | quem tem `documento.edit` |

- **A ordem é a navegação.** Favorita primeiro (a planta baixa que se consulta o dia inteiro), depois
  o que o aparelho mais abriu, depois o resto por código — sem título de seção: rola e acaba. Foi o
  que substituiu Início e Pranchas, e é o que dispensa o encarregado de entender que existem duas
  listas para a mesma coisa.
- **Favoritas em seção própria**, com título, **quando nada está recortando a grade**. Sob filtro a
  separação atrapalharia — o que se procura é a prancha, não o status de favorita dela —, e por isso
  ela some junto com o recorte em vez de existir sempre.
- **Mobile-first de verdade:** alvo de toque de 46–60 px (luva erra os 44 do manual), **disciplina
  como cor** e não como palavra — "hidrossanitário" é difícil de ler e impossível de digitar com luva
  —, e cartão com miniatura ocupando metade da altura: ninguém reconhece uma prancha lendo
  "ARQ-PLB-001".
- **A disciplina é um seletor, não uma fileira** — e essa foi a terceira tentativa. Primeiro foi
  `overflow-x` com barra escondida (a mesma crítica que o módulo fez às abas, repetida); depois
  quebrando linha com "mais N", que resolvia dez disciplinas e **quebrava com cem**: expandir empurrava
  a grade de pranchas para o fim da página, e o controle roubava a tela de quem veio ver desenho. O
  seletor **ocupa uma linha, sempre**, tem busca dentro (é ela que torna cem navegáveis) e a lista rola
  **no painel**, com altura fixa. Não é `<select>` nativo porque ele não mostra cor, exige Ctrl+clique
  para múltipla e no celular abre a lista cinza do sistema — as três coisas que este módulo usa para a
  pessoa reconhecer a disciplina sem ler. O painel vai num **portal**: aberto dentro da lista de envio
  ou da gaveta de revisões, que rolam, um `absolute` seria cortado na borda do container.
- **Busca por voz.** O microfone (`useDitado`, Web Speech API) existe porque quem não escreve
  "hidrossanitário" consegue dizê-lo, e essa é a diferença entre achar a prancha e desistir dela. Só
  aparece onde o navegador suporta — botão que não funciona é pior que botão ausente, ainda mais para
  quem não vai ler o motivo.
- **Prancha que não abre não entra na grade do campo.** Quem executa não tem verbo para resolver
  conversão falhada, e um triângulo de defeito no andaime só produz "o sistema não funciona". Quem
  governa o acervo vê tudo.
- **O cockpit são dois chips.** `12 não abrem` · `4 esperando publicação`, clicáveis, filtrando a
  própria grade — o número **leva ao lugar** em vez de contar de longe, que era o defeito das faixas
  de fila da antiga aba Início. Não há página de painel: ela seria mais uma parada no caminho.
  Ligar um chip **limpa disciplina e busca**: os contadores são do acervo inteiro, e cruzar os dois
  eixos fazia o chip dizer "4 esperando publicação" com a grade mostrando zero.
- **Nenhum recorte sobrevive ao que o criou, e nenhum vazio é sem saída.** Os dois são a mesma lição,
  aprendida junto: um filtro cujo único desligador é um controle condicional tem de se desarmar
  quando o controle sai da tela, e o `Empty` de grade filtrada carrega o botão que a devolve inteira.
- **Modo sol:** um botão reescreve os **tokens da Malha** só dentro da página (preto sobre branco,
  borda escura, sombra fora do caminho). Não é tema novo do sistema: é condição de uso deste módulo,
  fica no aparelho (é propriedade do lugar, não da pessoa) e some ao sair.
- **Visualizador em tela cheia**, com pan/zoom por ponteiro (mouse, caneta e dedo no mesmo caminho) e
  pinça de duas mãos; PDF vai para o leitor do próprio browser e o `.glb` do IFC para o 3D, que só
  então baixa o `three` (`import()` dentro do efeito — quem foi ver um PDF não paga por ele).
- **A lista de desenhos é gaveta, não coluna.** Um arquivo pode trazer dezenas de folhas (§4.5), e no
  celular do canteiro qualquer coluna permanente rouba metade da tela — o que a pessoa veio fazer é
  olhar o desenho. O botão só existe com mais de uma folha (com uma só seria interruptor ligado a
  nada, a lição do **D5**) e mostra no rótulo a folha aberta, para saber onde se está sem abrir a
  lista. Dentro dela: nome editável na hora, contagem de traços e a régua de cada folha — ou `sem
  escala`, dito com todas as letras.
- **O nome é dado por quem abre a prancha**, não numa tela de cadastro: quem descobre que o "Desenho
  3" é a planta de cobertura é justamente quem acabou de abri-la. Trocar de folha zera o gesto em
  curso, porque os vértices são normalizados pela largura *daquela* folha e carregá-los para a
  seguinte mediria com a régua errada num lugar que não é o mesmo.
- **A faixa do topo continua existindo mesmo com a lista**, e é decisão de produto: quem abre a
  primeira folha de um arquivo de cinquenta precisa **saber que há cinquenta** sem ter de procurar.
  Ela diz também quando o desenho está georreferenciado — que é a explicação de por que a régua não
  bate com o que um template errado mostraria.
- **A gaveta de entregas é onde três abas foram parar.** Histórico, Acervo e Conversões falavam do
  mesmo objeto por eixos diferentes, e o objeto é a prancha: rótulo, situação, formato, quem enviou,
  quem publicou, as duas datas, a observação do projetista, o motor com a versão e o motivo do erro —
  tudo continua, mais perto de quem pode fazer algo a respeito. O estado da derivada aparece **na
  linha da revisão que falhou**, com a frase de *quem resolve* (comprar · consertar · reenviar · nada
  a fazer), que é o melhor que a aba Conversões tinha e sobreviveu inteiro.
- **O catálogo de formatos abre de dentro do envio.** Era aba ao lado das telas de trabalho e não
  recebia obra nenhuma: fala de assinatura, não de acervo. Agora responde a pergunta no único momento
  em que ela existe — *"posso mandar este arquivo?"*. Quando a tela de Plano e quotas existir
  ([frontend.md §5.16](../frontend.md)), muda para lá.

### A disciplina é vocabulário do cliente

*(decisão do dono, 14/08/2026.)* As 13 de `Disciplina` são o **piso** — o que o carimbo brasileiro
escreve, e de onde a [taxonomia](taxonomia.py) adivinha a pasta no lote. Faltava o andar de cima:
construtora que separa "Fachada" de "Arquitetura", ou que trabalha com "Impermeabilização", não tinha
onde pôr, **a tela não mandava disciplina no envio**, e o resultado era todo arquivo caindo em *Outra*
— com a fileira de filtro da grade virando um botão só.

`DisciplinaProjeto` ([migration 0010](../../backend/moduloprancheta/migrations/0010_pra9b_disciplina_do_tenant.py),
RLS na mesma migration) guarda **rótulo, cor e ordem** por tenant, e o catálogo em
[disciplinas.py](../../backend/moduloprancheta/disciplinas.py) soma as duas fontes.

**É tag, não FK**, e as três consequências são o desenho:

- o documento continua guardando o **código como texto**, então o acervo que já existe não precisa de
  migração de dados — os slugs das 13 valem sem nenhuma linha na tabela nova;
- **apagar uma disciplina não apaga prancha**: ela volta a se exibir pelo próprio slug, que é feio e
  honesto. `CASCADE` aqui apagaria acervo por causa de uma faxina de rótulo, e exibir "Outra" mentiria
  sobre uma classificação que a prancha ainda carrega;
- o campo perdeu os `choices`: com eles, o `full_clean` recusaria a disciplina que o próprio cliente
  acabou de cadastrar.

**A cor mora no servidor**, e a troca é deliberada: era um dicionário em `pages/grade.ts`, e no
momento em que o cliente pôde criar disciplina a tela teria de inventar cor para o que não conhece —
duas fontes para o mesmo atributo, divergindo na primeira disciplina nova (uma cor no filtro, outra no
cartão). Quem não escolhe recebe uma **derivada estável do código**, nunca sorteada: sorteio daria cor
nova a cada carga, e cor é justamente o que faz a pessoa reconhecer a disciplina sem ler.

### Várias disciplinas por prancha, e o palpite que as marca

*(decisão do dono, 15/08/2026 — e ela **inverte** a precedência que a PRA.9b tinha escrito.)*

O desenho real não obedece a uma classificação só: a planta de forro é arquitetura **e** elétrica, o
corte de shaft é hidrossanitário **e** incêndio. Obrigar a escolher uma fazia escolher errado — ou não
escolher, que era o caminho para tudo cair em *Outra*.

`DocumentoDisciplina` ([migration 0011](../../backend/moduloprancheta/migrations/0011_pra9c_varias_disciplinas.py))
guarda o conjunto, e o `disciplina` do documento continua existindo como a **principal** (a de
`ordem = 0`), porque três coisas dependem de haver uma: a ordenação do acervo, a coluna do lote e a
cor de destaque do cartão. Quem escreve é o `definir_disciplinas`, **a única porta** — a
denormalização só é segura enquanto ninguém atribuir o campo por fora.

**Sem migração de dados**, e é o que torna a fatia barata: documento anterior não tem vínculo, o
`codigos_de_disciplina` cai na coluna, e acervo, filtro e agrupamento continuam respondendo certo.

Duas consequências assumidas:

- **a prancha aparece em todos os seus grupos** no acervo, e a soma dos grupos passa a ser maior que
  `total_documentos`. Não é inconsistência — é o que "várias disciplinas" significa —, e por isso o
  total continua saindo da lista de documentos e não da soma;
- **`?disciplina=` saiu do `filterset_fields`**: lá ele compararia só a coluna principal, e a planta
  de forro sumiria do filtro de elétrica. Vira um `Q` sobre o vínculo, com `distinct`.

**A precedência do lote inverteu, e o motivo é de uso.** A PRA.9b fez a escolha da tela sobrescrever
tudo; o dono achou o defeito mandando a pasta **da obra inteira**, com elétrica, hidráulica e
arquitetura dentro — um carimbo só classificava as três igual, pior do que o palpite, que ao menos
acerta as subpastas organizadas. Agora a ordem é: **pasta que declara** manda; **nome que declara**
(`ARQ-ELE-PLB-001.dwg`, pela `disciplinas_do_nome`) manda em seguida; e a escolha da tela cobre só o
que sobrou — o arquivo solto no meio. A **R1 não é afrouxada**: o que a plataforma vai gravar é o que a
conferência mostra, palpite ou escolha.

**O palpite é o desenho, não um enfeite.** A linha da conferência já **chega classificada**: o
`dados_do_arquivo` lê a pasta e o nome de cada arquivo e preenche a célula de disciplina, e a pessoa
confere e ajusta em vez de preencher. Um seletor vazio na frente de trinta arquivos é o que desmotiva
a classificar, e não classificar era exatamente o estado anterior. Nome sem sigla deixa a célula em
*Outra* sem inventar sigla — inventar classificação é pior do que não ter.

O palpite do **nome** devolve **todas** as disciplinas que o código declara, e não a primeira:
`ARQ-ELE-PLB-001.dwg` chega marcado nas duas, que é o que a coluna `multipla` sempre permitiu. A
**pasta** declara uma só, porque é uma só que ela declara.

**E na pasta a correção é linha a linha** — a [R19](funcoesimpexp.md) do motor, nascida deste caso. A
coluna `disciplina` é declarada `editavel=True, multipla=True`, e o `opcoes_da_coluna` publica o
vocabulário do tenant com a cor junto; a conferência abre a célula, com "aplicar a todos" acima da
tabela. As outras colunas seguem de leitura: código e revisão são o que a conferência existe para o
operador **conferir**, não reescrever. Antes disso, o arquivo solto no meio da pasta da obra só tinha
uma saída — recusar a linha e subi-lo à parte.

E a elegância é requisito, não acabamento: chips com bolinha da cor (nunca `<select multiple>`, que
exige Ctrl+clique e não mostra cor), **a mesma gramática** no filtro, no seletor e no cartão, marcadas
sempre à frente, *aplicar a todos* para a remessa homogênea, e o selo *"do nome"* que some assim que
alguém ajusta — porque depois disso ele mentiria sobre a origem da classificação.

Um detalhe de implementação que vale registrar porque volta: o `codigo` é derivado do nome em
`to_internal_value`, e **não** no `validate` — a `UniqueConstraint(tenant, codigo)` faz o DRF montar
um `UniqueTogetherValidator` que torna o campo obrigatório passando por cima de `extra_kwargs`, e a
requisição morria com "este campo é obrigatório" antes de o `validate` rodar.

### O arquivo cria a prancha

*(decisão do dono, 14/08/2026.)* O acervo nascia ao contrário do que a pessoa faz: cadastrava-se o
documento num formulário (código, título, disciplina) e **só então** se enviava o arquivo. Quem chega
com um DWG na mão não tem essas respostas ainda — e havia um efeito colateral pior, da família do
[D39](../pendencias.md): arquivo recusado na porta deixava para trás o documento vazio, ocupando o
`unique(tenant, obra, codigo)` sem nenhuma revisão.

São dois gestos, e os dois gravam documento e revisão **numa transação**:

| Gesto | Verbo | O que resolve |
|---|---|---|
| *Enviar projetos* (pasta ou arquivos soltos) | `<WizardArquivos>` sobre `prancheta.acervo` (impexp) | põe acervo dentro — do arquivo único à pasta com anos de projeto —, com conferência antes de gravar |
| *Atualizar arquivo* (dentro da prancha) | `POST documentos/<id>/atualizar/` | a entrega seguinte; o rótulo sai do nome ou é o **seguinte ao maior** — ninguém digita "R03" |

**Uma porta para o acervo, e a segunda não sobreviveu ao uso.** Existiu um `POST documentos/enviar/`
— o upload avulso, um arquivo por requisição, gravando direto sem conferência. Ele era um **segundo
caminho para o mesmo gesto** do wizard, que sempre teve tanto *escolher pasta* quanto *escolher
arquivos soltos*, e cujo palpite lê disciplina do caminho **e** do nome. O que o avulso fazia a menos
era peneirar formato e peso antes de subir; o que ele fazia a mais era pular a conferência. Duas
telas de entrada para um destino só é como uma delas envelhece sem ninguém notar — e não era violação
da [R17](funcoesimpexp.md), porque os dois caminhos sempre passaram pela `porta.admitir`: a
duplicação era de **interface**. Com ele saiu o `POST disciplinas/adivinhar/`, que existia só para
aquela tela pré-marcar os chips.

O `atualizar/` **ficou**, e não por exceção: ali o documento já está escolhido — é o que a pessoa tem
aberto na tela — e não há acervo a conferir. Pedir uma passada de conferência para trocar o arquivo de
uma prancha que se está olhando seria cerimônia sem decisão.

Três invariantes que os gestos **não** afrouxam: nasce sempre `rascunho` (publicar é
`revisao.publicar`, e subir não pode mudar o que o andaime executa); `get_or_create` no documento, para
duas entregas da mesma prancha virarem duas revisões dela e não um 400 de unicidade; e a gravação
continua passando pela `porta.admitir`, delegando ao `RevisaoDocumentoSerializer` em vez de reescrever
a admissão — uma segunda gravação escrita à mão nasceria sem porta, que é a forma do
[D75](../historico-correcoes.md) do lado de dentro.

**Uma regra de numeração, e ela é a `proximo_rotulo`.** O rótulo do nome vale quando o nome
**declara** um (`revisao_declarada`) e ele está livre; senão vem o **seguinte ao maior**. Houve duas
regras enquanto houve duas portas: o lote tapava o primeiro buraco (a colisão dele é `PLANTA.dwg` ×
`PLANTA (cópia).dwg` do mesmo acervo histórico) e o avulso seguia do maior. As duas resolvem a
colisão do lote igual; divergiam só no rótulo **não declarado**, e aí tapar buraco põe a entrega de
hoje atrás da que está em campo — o documento tem `R04` vigente, chega `HID-001.pdf` sem marca, o
`R00` está livre. Inofensivo enquanto o lote só recebia acervo histórico (documento novo, nenhuma
revisão); com uma porta só, ele recebe os dois casos.

Daí a célula **Revisão** da conferência vir vazia quando o nome não declara nada: `codigo_e_revisao`
devolve `R00` tanto para quem diz `_R00` quanto para quem não diz nada, e mostrar um `R00` que não vai
ser o gravado é a conferência mentindo sobre o que vai acontecer. Quem resolve o rótulo é o
`aplicar_linha`, que é onde se sabe o que o documento já tem.

### Achar o desenho na prancha difícil

Quatro instrumentos, e nenhum deles inventa dado.

**A vista de conjunto** ([Panorama.tsx](../../frontend/src/modules/prancheta/visualizador/Panorama.tsx)) é
por onde o arquivo de **várias folhas abre**: elas aparecem lado a lado, cada uma no lugar em que
está no terreno, e entrar numa folha vira escolha em vez de condição de entrada. A posição não é
enfileiramento decorativo nem reconversão — sai do `mundo` medido na emissão (`origem_x`,
`origem_y`, `por_folha`) mais o aspecto real da imagem, aritmética sobre dado já publicado. As
envolventes são pintadas antes de as imagens chegarem, porque até 64 folhas somam dezenas de MB e
esperar por todas daria tela vazia justamente no arquivo em que a pessoa mais precisa se orientar.

**É vista de navegação, não de trabalho.** Marcar, medir e o leitor de coordenadas continuam na
`Vista2D`, por folha. Trazer a marcação para cá exigiria uma segunda régua de normalização
convivendo com a primeira, e duas réguas divergem no primeiro ajuste: o sintoma seria o pino a dois
dedos de onde alguém o pôs — a família do D54.

**O minimapa** ([Minimapa.tsx](../../frontend/src/modules/prancheta/visualizador/Minimapa.tsx)) é a
**vista de cima do arquivo**: cada folha desenhada como uma mancha no lugar em que ela está *no
terreno*, a partir da `DesenhoProjeto.caixa` — a mesma envolvente, em unidades de desenho, que o
agrupador usa para cortar as folhas e que a herança de nome usa para reconhecer o mesmo desenho na
revisão seguinte. Duas plantas lado a lado no CAD aparecem lado a lado aqui; o eixo Y é invertido
porque o do desenho cresce para cima e o do SVG para baixo, e sem isso o mapa mandaria a pessoa para
o canto oposto. Ele mora no **canto superior esquerdo**: centralizado no topo, como nasceu, cobria a
faixa do carimbo e o começo do desenho — a ajuda tapava o que ela ajudava a achar.

**O mapa inteiro é a região clicável**, e não só as manchas. Uma poligonal de 40 m ao lado de um
loteamento de 8 km ocupa menos de um pixel, e alvo de menos de um pixel não é alvo: o clique abre o
desenho **mais próximo** do ponto, medido por distância à caixa e não ao centro dela (com escalas tão
desiguais, o centro do grande fica longe de quase toda a área que ele ocupa). Cada mancha é numerada,
e os chips com o rótulo de cada folha repetem o número — é o que permite falar de um desenho sem
dizer "o de cima à direita".

**O zoom tem dois gestos, e a separação é o conserto.** A roda solta acelera com o giro (é o que
torna praticável atravessar os ~7.865× que ler uma poligonal exige); **`Ctrl` + roda** é passo fixo de
3%, sem aceleração nenhuma. Existem os dois porque a aceleração estava certa e ainda assim
atrapalhava: a janela de giro rápido é de 120 ms e um mouse girado com naturalidade dispara eventos a
cada 50–80 ms, de modo que o passo comum era o acelerado, não o de base.

**O snap se desliga.** Ligado é o padrão — é a mira que faz a cota valer, e sem ela o ponto gravado é
o do dedo, o que numa folha onde 1 px vale 4 cm é medida errada com cara de medida conferida. Mas
grudar atrapalha quando o alvo **não tem vértice**: o meio de um vão, um ponto no terreno. O selo de
estado é o próprio interruptor, e a mira some junto ao desligar.

A régua comum aos três: **ferramenta de ajuda se desliga**. A que não se desliga vira estorvo no dia
seguinte — é a mesma decisão da ressalva dispensável da folha que abre incompleta.

### A fila da conversão

A Prancheta **não tem fila própria**: ela é a primeira cliente da frota da plataforma
([`nucleo/frota.py`](../../backend/nucleo/frota.py)). `pipeline.agendar` chama `frota.enfileirar()` no
lugar do `.delay()`, com a chave `prancheta.derivada:<id>` — que é a identidade do *trabalho* e o que
impede o upload reenviado, o `reprocessar` clicado duas vezes e o retry do Celery de virarem três
lugares na fila para o mesmo arquivo.

**O plano viaja congelado**, pela mesma razão que os `tiers` e o `teto_snap`: o despachante roda sem
usuário e o worker sem token. Plano vazio cai na classe do meio, nunca em premium — na dúvida o
benefício não é presumido.

**A frota cresce em cadeiras, não em filas.** A fila é uma só, e é isso que torna a reserva por plano
possível: filas paralelas não sabem quantas cadeiras a classe vizinha ocupa, e a repartição vira
palpite. Somar capacidade é somar `FROTA_VAGAS`, que acompanha o `--concurrency` do worker. **Cada
cadeira nova exige um núcleo novo, não só mais memória** — a conversão é trabalho de CPU de uma linha
só (aproveitamento medido: 100%), então vCPU compartilhada entrega cadeira que anda devagar e sofre
com o vizinho. O gatilho de comprar a próxima cadeira é a **espera do cliente**, não a conta de infra:
converter é barato e o custo por cadeira é pequeno perto do plano; o que dói é a fila no primeiro
uso. Régua e números em [`payment/planos.py`](../../payment/planos.py) §5.4c e no estudo de
[viabilidade econômica](../medicoes/viabilidade-economica.md).

**A conversão que passa do turno não morre: ela para entre duas folhas e volta ao fim da fila**
(PRA.11). O `MotorDxf` confere o prazo entre folhas e devolve um marcador `Retomada`; o pipeline grava
as folhas desta passada — que **já abrem** — e recoloca o arquivo. O que toda passada repete é a
gravação da geometria; o que ela pula é reemitir o que já está pronto. Motor que converte numa unidade
indivisível declara `retomavel = False` e mantém o contrato antigo: estoura o teto, para tudo e
explica.

**Mas o turno vencido não basta: tem de haver alguém para receber a vez.** O motor consulta
`frota.ha_espera()` entre uma folha e outra — e só cede se existir tarefa **aguardando** (quem já
roda ocupa outra cadeira, e a própria chave sai da conta). Com a fila vazia ele continua trabalhando,
porque devolver a cadeira a ninguém custaria repetir o custo fixo à toa. Como a pergunta é refeita a
cada folha, o atraso máximo de quem chega é **uma folha**, não uma passada.

Dois relógios, e a diferença importa: `PRANCHETA_CONVERSAO_SEGUNDOS` é o **turno** (quanto um arquivo
segura o worker de uma vez) e `PRANCHETA_CONVERSAO_TOTAL_SEGUNDOS` é o **arquivo inteiro**, somado
entre as voltas. Estourando o segundo, a conversão encerra em `recurso_excedido` com as folhas já
convertidas preservadas — a prancha abre pelo que deu, e a frase diz quantas faltaram.

O **teto duro** de uma passada de motor retomável não é mais o turno, e sim o que resta do acumulado
daquele arquivo (`_relogio_da_passada`): sem isso, a passada que ultrapassa o turno de propósito —
porque a fila está vazia — seria morta em pleno trabalho útil, destruindo o próprio progresso que a
retomada existe para preservar. O orçamento total do arquivo não mudou; mudou poder gastá-lo de uma
vez quando isso não atrapalha ninguém.

**A memória é degrau de plano** (`planos.py` §5.4d). `PRANCHETA_CONVERSAO_MEMORIA_MB_POR_PLANO`
alimenta o `RLIMIT_AS` da conversão e `PRANCHETA_SUBPROCESSO_MEMORIA_MB_POR_PLANO` viaja por
`ContextVar` até os quatro pontos em que `dwg.py` arma o subprocesso — os motores não conhecem
Django, então quem traduz plano em número é o pipeline, com o plano já congelado na linha da fila.
É a memória, e não os MB do arquivo, que decide se o desenho grande abre: o DWG guarda hachura como
*declaração*, grandeza que o tamanho do arquivo não limita.

**A retomada tem preço, e ele está medido.** Cada passada repete a gravação da geometria, então
terminar em N voltas custa `N × gravação + emissão` contra `gravação + emissão` de uma passada só. No
`01_LOTEAMENTO_PORTAL_RESIDENCE` (16 MB, 4 folhas) isso deu **115 s contra 36 s — 3,2×**, com a
numeração saindo `[1, 2, 3, 4]` sem repetição nem perda. O mecanismo troca *"nunca terminar"* por
*"terminar mais caro"*, e a conta de quando isso compensa está em
[medicoes/fila-da-frota.md](../medicoes/fila-da-frota.md) e
[medir_retomada.py](../../ferramentas/medicao/medir_retomada.py).

### As duas visões

O corte sai das **permissões que já existem**, não de um campo de perfil novo
([visao.ts](../../frontend/src/modules/prancheta/visao.ts)):

| | **campo** (só `prancheta.documento.view`) | **responsável** (tem `documento.edit` e/ou `revisao.publicar`) |
|---|---|---|
| Obra | uma só, lembrada no aparelho | alterna entre todas |
| Grade | só o que abre | tudo, + os dois chips de estado e o botão de envio |
| Gaveta de entregas | lê a história da prancha | + atualizar arquivo · publicar · reconverter |

**Não é modo, é permissão.** Não há chave para o usuário virar: o `visao.ts` já calcula o papel a
partir das permissões, e o que mudou é que ele passou a decidir **o que a tela carrega** em vez de
filtrar uma fileira de abas. Quem não governa o acervo nunca soube que a outra metade existe.

> **Limite declarado:** esconder as outras obras é decisão de **interface**, não controle de acesso —
> o backend não tem vínculo usuário↔obra (não há `Obra.responsavel` nem alocação em `rh`), então o
> servidor não sabe "a obra dele". Isso evita o erro honesto (abrir a prancha da obra errada) e não
> impede o acesso mal-intencionado. Fechar de verdade exige a alocação no backend + filtro no
> `acervo/` — fatia própria, não um `if` no cliente.

**A história de uma prancha** (`revisoes/?documento=`) mostra o que o sistema de fato registra: quem
enviou cada revisão e quando, **quem publicou** e quando, e a observação do projetista. Não é *diff*
de desenho — comparar geometria de dois DWG é outro problema; dizer "o que mudou" a partir destes
campos seria inventar. Era um feed da obra inteira (`?documento__obra=`) numa aba própria, e a
pergunta real nunca foi "o que mudou na obra": foi *"esta prancha aqui, quem mandou e quando?"* — que
só se faz com ela aberta na frente.

**Favoritos e mais vistas vivem no aparelho** ([preferencias.ts](../../frontend/src/modules/prancheta/preferencias.ts)),
e a tela rotula "neste aparelho" em vez de fingir sincronia: não há tabela para isso no backend, e um
"mais visto" global fabricado no cliente contrariaria a régua de dados honestos. Quando existirem
`AcessoDocumento`/`FavoritoDocumento`, estas funções viram o cache local do mesmo dado.

**Presença** ("quem mais está vendo esta prancha") é a única coisa da tela que o frontend **não pode
responder sozinho** — `localStorage`/`BroadcastChannel` só enxergam o mesmo navegador e mostrariam
você mesmo como companhia. O slot existe com o selo *em breve* e o cliente já está escrito e
desligado por constante ([presenca.ts](../../frontend/src/modules/prancheta/presenca.ts)); acende com
um heartbeat `SETEX presenca:<revisao>:<user>` no Redis (TTL ~90 s — o celular do canteiro perde
sinal, e presença que depende de despedida vive cheia de fantasma).

## 10. Permissões e paywall

**Permissões** (`modulo.recurso.acao`, catálogo da IAM):
`prancheta.documento.view` · `.edit` · `prancheta.revisao.publicar` · `prancheta.marcacao.view` ·
`.edit` · `.resolver` · `prancheta.acervo.importar` · `prancheta.conversao.reprocessar`.

Cada uma entra no catálogo **junto da fatia que a gateia** — documento, publicar, reprocessar e
**marcação (PRA.3)** já estão lá; `acervo.importar` entra com a PRA.5. Declarar antes poria na tela
de papéis um interruptor ligado a nada, que é o espelho do problema do **D5** (permissão criada, verbo
gateado, ninguém com a chave).

**`marcacao.resolver` é o terceiro verbo de alçada do módulo** — detalhe e personas em §13.3. A
importação de BCF **não** tem permissão própria: ela cria marcação, então é `marcacao.edit`, e a
parede dela é **comercial** (o formato `bcf` no plano), não de permissão.

**`renomear` a folha é `documento.edit`**, junto de `calibrar` e pelo mesmo raciocínio: o nome viaja
por herança para as revisões seguintes (§9), então quem nomeia a folha de hoje nomeia a de todas as
próximas até alguém trocar. Não é permissão nova — é o mesmo verbo de quem governa o acervo.

**`reprocessar` é verbo separado porque queima recurso** — CPU hoje e, com a APS da PRA.4, dinheiro
por tradução. Quem lê o acervo não deve poder mandar reconverter o acervo inteiro de uma obra. Fica
só na `projetista`: é quem conhece o arquivo que sabe se a derivada saiu torta.

**`publicar` é ato separado de `editar`, de propósito** — publicar uma revisão muda o que o campo vai
executar; é a mesma classe do `aprovar` do Orçamento (a lição do **D28**: verbo de alçada precisa de
permissão própria **e** de uma persona que a tenha, senão só o admin do tenant consegue).

**Persona nova:** `projetista` (publica revisão). `engenharia` lê e marca; quem só executa em campo
lê e marca, não publica.

**Paywall** ([payment/planos.py](../../payment/planos.py)) — o **formato e o motor** são as unidades
de cobrança, e são knobs diferentes:

- `motores_prancheta` — quais motores o plano habilita. O **livre** (LibreDWG/`ezdxf`/IfcOpenShell)
  está em todos; o **premium** (APS) é o degrau. É aqui que mora o desenho do §4.1: DWG abre nos dois,
  com fidelidade diferente; RVT/NWD só no premium.
- `formatos_prancheta` — quais formatos o plano **aceita no acervo**. Gate no **upload**, não só na
  conversão: recusar o arquivo na entrada, dizendo o porquê, é mais honesto do que aceitá-lo e travar
  depois — e não gasta storage que o cliente não contratou.
- `storage_projeto_gb` — teto de acervo (quota de objeto, como as do SIL/Orçamento).
- `conversoes_pagas_mes` — traduções que passam pelo motor premium (COGS, medida como IA/NF/boleto).

## 11. Roadmap em sub-fases (PRA.x)

| Fatia | Entrega | DoD |
|---|---|---|
| **PRA.0** ✅ | **Fundação**: os 3 modelos + RLS + `RequireModule("prancheta")` + permissões/persona na IAM + upload com teto próprio (e gate de formato por plano) + **upload manual** + `GET acervo/?obra=` (documentos por disciplina, cada um com a vigente embutida + fila de decisão) | suíte verde sobre PG; isolamento e entitlement provados |
| **PRA.1** ✅ | **Pipeline + motor livre**: registry declarativo de motores (um adaptador por formato), Celery com `tenant_context` (a lição do **D8**), estados `LENDO/CONVERTENDO/PRONTO/ERRO`, idempotência por `hash`+versão do motor, retry/DLQ. Motores: PDF, DXF (`ezdxf`), IFC (IfcOpenShell) e **DWG (LibreDWG)** — com a **taxa de sucesso sobre DWGs reais medida e registrada** (§4.1) | arquivo real de cada formato vira derivada; falha do motor livre em DWG diz "exige alta fidelidade", não "erro" |
| **PRA.1b** ✅ | **Fidelidade do motor livre** — o que o PRA.1 entregou convertia, mas desenhava mal e perdia conteúdo. `dwgbmp` no build stage + preview embutido como 2ª derivada (§4.4, [D49](../historico-correcoes.md)); `Configuration` com espessura **relativa à folha** (§4.3, [D48](../historico-correcoes.md)); aba de layout quando o modelspace não desenha (§4.5, [D44](../historico-correcoes.md)); **três** `MotivoErro` novos — desenho vazio · XREF ausente · sem preview ([D45](../historico-correcoes.md)/[D49](../historico-correcoes.md)) — com a fila do cockpit contando por **quem age**; teto de peso do DWG avisado no upload (§6.1, [D47](../historico-correcoes.md)) | traço equivalente com o modelo em metro e em milímetro (medido: 41× → ≤3,3% de quantização); remedição no **mesmo corpus de 150 DWGs** do D42, antes/depois |
| **PRA.1c** ✅ | **Um desenho, uma folha** (§4.5) — o `DesenhoProjeto` como unidade que se abre, mede e marca; separação por lacuna maior que o próprio desenho, sem teto prático; **escala por folha** (sai da revisão) e unidade corrigida pela coordenada UTM (§13.2); `/api/prancheta/desenhos/` com `renomear` e `calibrar`; nome herdado entre revisões por sobreposição de envolvente; gaveta de folhas na tela (§9.1) | o arquivo com duas áreas distantes abre como duas pranchas de tamanho normal, cada uma medindo em metro; prancha de folha única sai byte a byte igual; reprocessar não apaga nome nem calibração |
| **PRA.1d** ✅ | **Teto de recurso e frota separada** (§4.6, [D57](../historico-correcoes.md)) — fila `conversao` + `worker-conversao` com `mem_limit`/`cpus`, `orcamento_de_conversao` (RLIMIT_AS + relógio) traduzindo estouro em `recurso_excedido`, e degradação em camadas que **declara** cada camada. Instrumentação de tempo/pico por conversão, para o paywall ter número | nenhum arquivo de cliente consegue passar do orçamento; o que passa vira erro legível, não worker morto; a remedição do §4.1 volta a rodar sob os mesmos tetos |
| **PRA.2** ✅ | **Visualizador**: **lente na topbar** (ao lado de Mapas/Calendário) + página própria com cockpit e fila de decisão; viewer 2D (SVG pan/zoom) e 3D (Fragments); responsivo para o celular do canteiro | abrir a revisão vigente de uma obra pelo celular, sem PDF |
| **PRA.3** ✅ | **Medir e marcar**: medição sobre 2D (com **escala calibrada**, §13.2) e **marcação BCF** (ponto de vista + comentário + situação + responsável), com import/export BCF 2.1 | **← 1ª entrega a cliente real.** A marcação feita no campo abre no software do projetista |
| **PRA.4** | **Motor premium (APS)**: RVT/NWD + DWG de alta fidelidade, credencial da plataforma, medidor de tradução, quota e **reconversão ao subir de plano**. **Dimensionar por RVT/NWD e acabamento — o DWG saiu da conta, agora com prova nos dois extremos do acervo**: limite real do caminho livre em **0% de 170 arquivos** (corpus de 160 + os 10 acima de 40 MB, §4.1). Os 3 `motor_insuficiente` da faixa pesada foram investigados e são falsos — convertem crus, e o que os derruba é o nosso `RLIMIT_AS` herdado pelo subprocesso ([D78](../pendencias.md)) | RVT abre; consumo aparece em `GET /api/plano/`; upgrade melhora a derivada sem perder a antiga |
| **PRA.5a** ✅ | **A porta única, nos dois sentidos** ([funcoesimpexp §2, R17/R18](funcoesimpexp.md)) — `uploads.py` **sai** e a entrada da revisão passa por `entrada.admitir` (assinatura de bytes, [D75](../historico-correcoes.md)); as 3 rotas de saída passam por `entrega.servir`; os 20 formatos ganham assinatura e entram na allowlist da plataforma; o que sobrou do `uploads.py` vira [planos.py](../../backend/moduloprancheta/planos.py), que só declara **o que se vende**. Motor ganha `formatos_contratados` e `teto_mb_do_formato` — exigidos pelo 1º consumidor, porque o mesmo PDF é planilha no Orçamento e prancha de 100 MB aqui | `payload.exe` renomeado para `.dwg` é recusado na porta; RVT verdadeiro fora do plano ainda é 402; o `campo` continua abrindo a prancha |
| **PRA.5b** ✅ | **As duas entradas que restam** — snapshot do ponto de vista e `importar-bcf` — e a **carga em lote** do acervo histórico, com conferência (R18) e desfazer. As duas portas passam a chamar `entrada.admitir` pelo recurso `prancheta.marcacao` (que ganha `formatos_arquivo = ("bcf", "imagem")` e teto **próprio** para o snapshot); a tradução das recusas em HTTP sai do serializer e vira [porta.py](../../backend/moduloprancheta/porta.py), um lugar só para os três chamadores. O lote entra pelo `prancheta.acervo`, que ganha `aplicar_linha`/`desfazer_linha` e a [taxonomia da pasta](../../backend/moduloprancheta/taxonomia.py) — **disciplina, código e revisão** saem do caminho; **a obra não** (§12 item 11) | pasta com anos de projeto vira acervo, sem gravar nada antes da decisão |
| **PRA.5c** ✅ | **O gesto que faltava** — a porta de lote da PRA.5b existia e nenhuma tela a chamava: o `<WizardArquivos>` do kit compartilhado ([impexp §10](funcoesimpexp.md)) monta *Enviar pasta* na entrada da grade (§9.1), com peneira de formato e teto **antes** do envio, remessas de dez e uma decisão só sobre o conjunto. Junto vieram os dois defeitos que só aparecem quando uma tela consome a declaração: [D83](../historico-correcoes.md) (o catálogo publicava o teto da planilha para formato de arquivo) e [D82](../historico-correcoes.md) (§4.7) | um acervo real entra pela tela, no navegador, e nada é gravado antes da confirmação |
| **PRA.1e** | **Trocar o renderizador: `dwg2SVG` como caminho principal** (§4.1). A causa do custo está medida — o nosso caminho **expande cada inserção de bloco em geometria própria**, e o `dwg2SVG` emite o bloco uma vez e o referencia (`<use>`); daí 945 MB × **225 MB** e 14 s × **0,8 s** no arquivo comum. Exige refazer as três coisas que o `Recorder` produz hoje: **separação de folha** (a envolvente passa a ser de referência, não de geometria expandida), **escala por folha** (a saída vem em coordenada de mundo, UTM) e **âncora de marcação** (hoje normalizada pela largura da folha). E mais três, achadas ao conferir o formato de saída em 10/08: **`--mspace` obrigatório** (sem a flag ele desenha o *paper space*, não o modelo), **calcular o `viewBox`** (o dele contém 0,3% da geometria) e **consertar o texto** (`%%D`/`%%P`/`%%C` sem decodificar e `font-family="Courier"` cravado — carimbo e cota). O degrau de resgate de 10/08 **não resolve o custo**: só é alcançado depois do estouro, e o arquivo comum nunca estoura, então continua pagando 945 MB | conversão comum cai a ~¼ da memória e ~1/15 do tempo, com folha, escala, marcação e **texto** preservados |
| **PRA.6** | **Pasta sincronizada** (Drive/OneDrive): OAuth por tenant, detecção de revisão nova, resolução de conflito | o projetista salva onde já salva e a revisão aparece no sistema |
| **PRA.7** | **Seams**: georreferenciar prancha → camada no [Maps](modulomaps.md); **projeto × as-built** contra a ortofoto do drone | a comparação projeto × executado numa tela só |
| **PRA.8** ✅ | **E2E vivo pelo gateway** ([pra8_prancheta_test.py](../../testes/e2e/pra8_prancheta_test.py)) — **155/155** (138 na PRA.5a, 155 na PRA.5b), com amostras próprias ([amostras_pra8.py](../../testes/e2e/amostras_pra8.py)) para rodar em clone limpo | o padrão do MAP.6/ORC.6: gate com token real, seam causal, formato/motor não contratado travado |

**Os três caminhos de entrada estão todos no plano** (upload manual, lote e pasta sincronizada), em
ordem de custo: o manual é indispensável e vem no PRA.0; o lote reusa motor que já existe; a pasta
sincronizada é uma **integração OAuth por tenant** e por isso vem depois da 1ª entrega — sequência
escolhida para não atrasar o loop completo, e fácil de inverter se a implantação exigir.

**Fila de decisão do cockpit** (a régua exige que o módulo *resolva*, não só liste): revisão publicada
que o campo ainda não abriu · conversão que falhou · documento sem revisão vigente · marcação aberta
atribuída a mim.

**A conversão que falhou é contada por quem age** (PRA.1b), e não como um número só:

| Contagem | Quem resolve | Como |
|---|---|---|
| `conversoes_que_exigem_upgrade` | **o cliente** | comprando o motor de alta fidelidade |
| `conversoes_aguardando_anexo` | **quem enviou** | reenviando a prancha com os XREF |
| *o resto* (total − as outras três) | **nós** | deploy ou conserto de motor |
| `conversoes_sem_desenho` | **ninguém** | o arquivo não tem desenho dentro; existe para ser subtraído |

O último parece supérfluo e é o que sustenta os outros: sem ele, "conversões com erro" cresce com
linha que nenhum trabalho faz desaparecer, e o badge da aba vira ruído permanente.

## 12. Em aberto

00. **O teto de memória do subprocesso decide se os 7 arquivos pesados abrem — e o número agora é
    medido.** *(decisão do dono, aberta em 10/08/2026.)*

    `PRANCHETA_SUBPROCESSO_MEMORIA_MB = 2.048` em [payment/planos.py](../../payment/planos.py). O
    último degrau da escada (o `dwg2SVG`, §4.1) **desenha** esses arquivos, mas pede **2.410 a
    3.069 MB** — faltam de 400 MB a 1 GB. A condição que o dono pôs em 09/08 para mexer no teto
    (*"não vamos subir o teto sem antes saber o custo real da operação"*) está cumprida: o custo foi
    medido arquivo a arquivo.

    | Caminho | 2.048 MB (hoje) | ~3.100 MB |
    |---|---|---|
    | Arquivo comum | abre | abre |
    | Os 7 pesados (~1% do acervo) | **não abrem** | abrem, reservando 3 GB da VM por conversão |

    **O que pesa contra subir:** o `worker-conversao` tem `mem_limit` de 3 GB, então os dois maiores
    ficariam raspando o teto do contêiner — e a invariante do bloco de `planos.py` diz que o freio que
    sabe explicar tem de estourar **antes** do que só mata. Subir para 3.100 MB exigiria subir o
    contêiner junto.

    **O que pesa a favor:** é ~1% do acervo, e é justamente o projeto executivo completo — o arquivo
    que o módulo existe para abrir no canteiro.

0. **NWD e SKP saíram da venda até a PRA.4 — não têm assinatura de bytes publicada.**
   *(decisão do dono, 08/08/2026; limite consciente, com gatilho de reabertura.)*

   Com a R16/R17 valendo, um formato só entra se a plataforma souber reconhecê-lo pelos **bytes**. Os
   outros 18 têm assinatura verificável — DWG abre com `AC10`, IFC com `ISO-10303-21`, RVT é OLE2
   (`D0CF11E0…`), LAS é `LASF`. Estes dois não:

   - **NWD/NWC** — o contêiner é proprietário, e quem o descreve é o próprio autor do formato na
     Autodesk: *"em vez de simplesmente adotar ZIP, criei o meu"*. Não há assinatura publicada;
   - **SKP** — não tem número mágico estável: o cabeçalho muda entre versões, e do SketchUp 2021 em
     diante o contêiner passou a ser outro (VFF).

   **Nada se perde hoje**, e é o que torna a decisão barata: o motor deles é o `aps`, que a PRA.4 ainda
   não construiu. Antes desta fatia um `.nwd` entrava pelo nome, gastava `storage_projeto_gb` e gerava
   **zero derivadas** — a mesma forma do [D39](../pendencias.md). Recusar na porta dizendo a verdade é
   mais honesto do que aceitar bytes que não sabemos identificar e entregá-los a nada.

   Eles **continuam aparecendo** no catálogo de formatos, com o campo `reconhecido: false`: a régua do
   §6 manda mostrar travado com o motivo, nunca esconder. O que mudou é que agora há um terceiro
   estado além de "contratado/não contratado" — *"a plataforma ainda não sabe abrir isto"*.

   **Gatilho:** um `.nwd` e um `.skp` reais em mãos. A assinatura sai **medida** sobre arquivo do
   acervo, como a PRA.1d fez com os 160 DWGs, e eles voltam ao plano junto com o motor que os abre.
   A lista vive em `formatos.SEM_ASSINATURA_CONHECIDA`.

1. **Credencial APS**: conta única da plataforma × credencial por tenant (via [moduloapi](moduloapi.md)).
   Decisão do PRA.4, não bloqueia nada antes.
2. **Fronteira com o DMS** (§7), que hoje é placeholder.
3. **Formato-alvo do 3D**: o pipeline serializa IFC em **glTF**, e não em *Fragments*. Fragments
   comprime melhor, mas é gerado por biblioteca **JS** — plugá-lo no backend poria Node de volta,
   contra a Fase 11 inteira, que acabou de tirá-lo. glTF é o denominador aberto que o próprio
   `web-ifc`/Fragments consome. Se a PRA.2 medir que o ganho compensa, a conversão vira um passo **do
   frontend** sobre o glTF, não um serviço novo no backend.
4. **Tamanho da imagem**: o `ifcopenshell` traz o wrapper compilado do OpenCascade e é a dependência
   mais pesada do backend. Se o tamanho virar problema, é a primeira candidata a sair para um worker
   de conversão próprio.
5. **Os formatos geo já estão vendidos, e o `gdal` não tem adaptador** (achado do PRA.8 →
   [D39](../pendencias.md)). `payment/planos.py` inclui KMZ/GeoJSON no plano de entrada e mais quatro
   no `profissional`; o arquivo passa o paywall, ocupa storage e não gera derivada. As duas saídas —
   fechar o seam com o [Maps](modulomaps.md) (que é a **PRA.7**, e esbarra no entitlement próprio
   dele) ou recuar no plano até o seam existir — são decisão de produto. Enquanto isso, o registry
   declara a lacuna (`implementado: false`) e o E2E a cobra, para ela não virar silêncio.
6. **Quem redesenha a prancha, e quando** — *decidido: o navegador, sobre o que o `Recorder` já
   achatou.* Abrir DWG sem redesenho não existe: o formato guarda o **modelo** (entidades, camadas,
   estilos), não a imagem, e quem a calcula é sempre alguém, o AutoCAD inclusive. Só três formatos
   abrem sem interpretação, por já carregarem aparência: **PDF** e **imagem** (nativos do navegador, é
   o que o módulo já faz) e o **DWF**, o "PDF do CAD", que está na tabela da §3 sem motor e depende de
   o escritório publicá-lo — rota a pesquisar, não a supor.

   O que **era** decidível é a *sede* do redesenho, e duas exigências a fecharam: **zoom sem teto
   prático** (o `<img>` sempre tem o teto da rasterização, §9.06) e **snap a vértice** (a tela não tem
   um único ponto da geometria enquanto o desenho for imagem). As duas pedem geometria viva no
   cliente.

   **A rota escolhida não é o `dxf-viewer`** (WebGL, **MPL-2.0**, compatível), e a razão é o custo que
   adiou esta decisão: ele recebe o **DXF**, e a âncora da marcação, a escala e a medição — que
   derivam da folha do SVG — teriam de ser refeitas; além de o DXF intermediário do `MaxPlast` passar
   de 40 MB no 4G do canteiro. O caminho melhor **já está construído e ninguém usou**: o `Recorder`
   que a §4.5 introduziu já achata tudo (blocos resolvidos, hachura, texto virado traço, espessura)
   na **mesma folha** que a âncora e a escala usam. Serializá-lo num buffer compacto em vez de — ou
   além de — SVG dá carga direta em buffer de GPU, os vértices para o snap, **zero retrabalho de
   âncora**, e resolve de quebra os 13,6 MB da §4.5.

   Continua sem resolver **SHX**, que é limite do formato (§4.3), e traz uma exigência de aceite
   própria: o `<img>` de hoje faz 60 fps porque o navegador rasteriza uma vez e arrastar vira
   composição — o render vetorial tem de **provar** ≥30 fps no `MaxPlast` (62.433 entidades) antes de
   substituir o que funciona.

7. **Presença — "quem está vendo esta prancha"**: é a única parte da tela que o frontend **não pode**
   responder sozinho, porque saber que *outra pessoa* abriu o mesmo arquivo exige alguém no meio —
   `localStorage` e `BroadcastChannel` só enxergam o mesmo navegador, e mostrariam "1 pessoa vendo"
   (você) como se fosse companhia, que é pior do que não mostrar nada. O slot já existe na tela com o
   selo *em breve*, e o cliente inteiro está escrito e desligado por constante
   ([presenca.ts](../../frontend/src/modules/prancheta/presenca.ts)): os componentes já tratam
   avatares e contagem, então acender é trocar `SUPORTE_A_PRESENCA`. A fatia que falta é pequena e
   reusa o que já existe — `POST /api/prancheta/revisoes/<id>/presenca/` como *heartbeat* a cada ~30 s
   gravando `SETEX presenca:<revisao>:<user>` no Redis (o mesmo da revogação de sessão) com TTL de
   ~90 s, e o `GET` do mesmo caminho devolvendo quem está no ar, escopado por tenant. **TTL, e não
   "avisar ao sair"**: o celular do canteiro perde sinal, bloqueia e volta — presença que depende de
   despedida vive cheia de fantasma.

8. **Não existe vínculo usuário↔obra: a visão de campo é interface, não fechadura.** O módulo quer que
   o trabalhador veja **só a obra em que trabalha**, para não cruzar material de outro
   empreendimento, mas o backend não sabe qual é essa obra — não há `Obra.responsavel`, não há
   alocação em `rh.Funcionario` e o JWT não carrega obra. O que a tela faz é honesto e útil: a obra
   fica **fixada no aparelho** (o tablet do canteiro escolhe uma vez), as outras somem da navegação e
   o `acervo/` só é chamado para ela — mas isso **não impede** quem digitar outro id, porque o gate do
   servidor é por tenant, módulo e permissão, e nesse recorte todas as obras do tenant são legítimas.
   Está declarado assim aqui e no código ([visao.ts](../../frontend/src/modules/prancheta/visao.ts),
   `preferencias.ts`) para ninguém confundir conveniência com fechadura depois. Fechar de verdade pede
   alocação usuário↔obra no backend — o candidato natural é `rh.Funcionario`, que já é a ponte entre
   pessoa e obra no SIL — mais filtro no `acervo/`/`documentos/` derivado dela, com 403/404 para obra
   fora da alocação. **Vale além da Prancheta:** Diário, SIL e PDCA têm a mesma pergunta.

9. **Marcar sobre PDF não tem onde ancorar**, e importa porque PDF é o formato mais comum do canteiro.
   A sobreposição de marcação e medição só existe onde **nós** desenhamos a prancha — o SVG que sai do
   `ezdxf`/LibreDWG, ou a imagem enviada. O PDF é servido como está e abre no leitor do próprio
   navegador dentro de um `<iframe>`: não há como pôr camada sobre ele, e a única derivada de PDF é a
   miniatura de 600 px, declarada em [`motores/documento.py`](../../backend/moduloprancheta/motores/documento.py)
   como "reconhecer a prancha, não ler a cota" — marcar sobre ela seria apontar num lugar que ninguém
   consegue conferir. No 3D o limite é outro: o ponto de vista do BCF ali é **câmera**, não ponto na
   folha. Nos dois casos a marcação **continua funcionando sem âncora** (apontar, conversar, resolver
   e exportar em BCF; medir não) — `Marcacao.ancora` é opcional no modelo justamente por isto, e a
   tela diz o que não dá, em vez de oferecer um gesto que erra o alvo. Fechar pede **renderizar o PDF
   nós mesmos** (pdf.js/PDFium no cliente, ou uma derivada `vetor_2d` de PDF pelo motor que já
   existe). A decisão de servir o PDF nativo continua certa: reimplementar o leitor daria um
   visualizador pior justamente no formato que nunca dependeu de nós — o que muda é só a **camada**.

10. **As fontes LFF do texto SHX — decisão de licença, do dono** (§4.3). O caminho livre existe e o
    `ezdxf` já o lê; falta o arquivo da fonte. Embarcar as LFF do LibreCAD faz a imagem redistribuir
    **GPL como dado lido em processo** — forma de acoplamento diferente da do `dwg2dxf`, que é
    subprocesso e por isso não contamina o nosso código (§4.2). O que está em jogo, dimensionado: SHX
    (`txt`, `romans`, `isocp`) é o padrão de carimbo, cota e legenda no CAD brasileiro, então isto
    atinge o texto de praticamente toda prancha do acervo; com as fontes embarcadas o carimbo sai com
    a forma que o projetista escreveu **já no plano básico**, o que **remove um item da lista do que o
    motor premium vende** (§6) — e essa é a segunda metade da decisão. Enquanto não se decide, nada
    está quebrado: o texto é legível, com a forma trocada e larguras diferentes (o que desalinha
    carimbo e faz cota vazar da caixa). `support_dirs` é configurável em runtime, então ligar as
    fontes depois é acrescentar arquivos e uma linha — não uma refatoração.

11. **A obra do lote é escolhida, não adivinhada — e é limite consciente** *(PRA.5b, 08/08/2026)*.
    A R18 previa que o motor inferisse **obra e disciplina** do caminho da pasta. Disciplina, código e
    revisão saem de lá; a obra não, e o critério é o custo do erro: disciplina errada custa um filtro
    (a prancha aparece em "Outra", e o carimbo do desenho desmente a tela na hora), obra errada **põe
    a planta de um prédio no canteiro de outro** — a mesma família de erro que fez o `importar-bcf`
    exigir a revisão de destino em vez de adivinhá-la.

    O que torna a assimetria necessária **hoje** é a conferência: ela aceita *aceitar* e *recusar*
    (R1/R5), e não **corrigir linha a linha**. Com um palpite de obra errado o operador só poderia
    recusar a linha — e num acervo de trezentas pranchas isso é recusar o lote. Com a obra no
    `contexto_requerido`, a decisão é uma só, explícita, validada antes de o primeiro byte ser lido.

    **Gatilho de reabertura:** quando a tela de conferência aceitar correção por linha, a obra pode
    virar palpite como as outras — a taxonomia já sabe lê-la do primeiro nível do caminho.

*(Resolvido no PRA.1: a **conformidade GPL do LibreDWG** — o binário segue chamado como subprocesso,
a licença viaja na imagem e a oferta de fonte aponta para a tarball estável do GNU. Registro em
[THIRD-PARTY-LICENSES.md](../../THIRD-PARTY-LICENSES.md), origem do build em §4.2.)*

## 13. Marcar e medir (BCF)

O ponto em que o módulo deixa de **mostrar** e passa a **resolver**: até a PRA.2 ele respondia "qual
desenho vale"; daqui em diante carrega a pergunta de volta — *"esta viga não bate com a alvenaria, e
agora?"*.

### 13.1 O vocabulário é o do BCF, não um nosso

`Marcacao`, `ComentarioMarcacao` e `PontoDeVista` têm os campos do **BCF 2.1** (BuildingSMART), com os
mesmos nomes e o mesmo **GUID**. É a decisão central da fatia: o valor da marcação está em ela abrir
no Revit, no Navisworks, no Solibri e no BIMcollab do projetista. Um modelo "mais limpo" e nosso
exigiria um de-para na exportação, e todo de-para perde o que não coube.

O GUID é a **identidade fora daqui**: exportar um tópico, respondê-lo no software do escritório e
reimportar o arquivo reencontra a *mesma* linha. Sem isso, cada ciclo duplicaria a caixa de entrada do
canteiro — o defeito que faz equipe abandonar integração BCF na segunda semana. Por isso o `unique` é
**por tenant**: dois clientes podem importar o BCF do mesmo projetista terceirizado, e um unique
global viraria erro de gravação para o segundo.

**O que o BCF não carrega, e por isso não prometemos.** O padrão é centrado em modelo 3D — o tópico
aponta para componente IFC e para uma câmera no espaço. Marcação feita sobre prancha 2D não tem nem um
nem outro. Atravessam para o escritório: o tópico inteiro, os comentários e o **snapshot** (o recorte
da folha com a cruz no ponto). Não atravessa: a coordenada na folha (`Marcacao.ancora`), que fica aqui
e sobrevive à reimportação porque a conciliação nunca a toca. Leitor/escritor em
[`bcf.py`](../../backend/moduloprancheta/bcf.py); a ponte com o ORM em
[`interop.py`](../../backend/moduloprancheta/interop.py), separados de propósito — o parser não conhece
ORM, e é isso que o mantém testável sem banco quando os nossos modelos mudarem.

**BCF não é formato de acervo.** Ele figurava no registry com motor `ifcopenshell`, como se fosse
arquivo a converter em derivada; um `.bcfzip` não tem geometria nenhuma. Passou a `interop=True` em
[`formatos.py`](../../backend/moduloprancheta/formatos.py): sem motor, recusado no upload de revisão
com a porta certa na mensagem, e entrando/saindo por endpoint próprio.

**Segurança na leitura** — o arquivo vem de fora, e três guardas fecham uma classe cada: DOCTYPE
recusado (mata *billion laughs* e entidade externa; nenhum BCF legítimo traz DTD), teto de tamanho
descomprimido lido do cabeçalho do zip antes de descomprimir, e **nada é extraído para disco** (leitura
por nome, em memória — sem `extractall` não há *path traversal*). Snapshot vindo de fora só vira
arquivo depois de o Pillow confirmar que é imagem.

### 13.2 Medir exige escala declarada — e o desenho às vezes a declara

O PDF não carrega unidade e foto de prancha menos ainda. **Inventar metro em cima de pixel seria
fabricar dado** — num campo onde o erro vira parede no lugar errado. Aí a escala é **calibrada por
uma pessoa**: alguém traça sobre uma cota conhecida ("esta parede tem 3,50 m") e o servidor converte
para *quantas unidades reais cabem na largura do desenho* — a grandeza que as coordenadas
normalizadas exigem.

**Mas o DXF/DWG declara** (PRA.3b), e a versão original desta seção errava ao tratá-lo como os
outros. As coordenadas de um CAD estão em unidades de desenho e o cabeçalho diz qual é a unidade
(`$INSUNITS`): é daí que o AutoCAD tira o "3,50 m" sem ninguém calibrar nada. Jogar essa informação
fora na conversão e depois pedir a uma pessoa que a redescubra com o dedo é perder precisão de graça
— então o motor a extrai ([`escala_do_desenho`](../../backend/moduloprancheta/motores/dxf.py)) e o
pipeline a publica na revisão. A conta tem duas metades, e as duas são medidas: a largura da página
que o próprio `ezdxf` emitiu (lida do SVG, com `Settings(scale=1.0)` fixando *1 unidade = 1 mm*) e o
fator de `$INSUNITS`. Um teste com desenho de tamanho conhecido prende a premissa, porque uma
mudança de default do ezdxf transformaria todo metro do módulo em número errado sem quebrar nada.

**`escala_origem` diz de onde veio o metro**, e define a precedência: `desenho` pode ser
substituída por outra leitura (motor melhor, reprocessamento), `calibrada` **não é tocada por
máquina nenhuma** — a mesma soberania do pin `exata` do [MAP.6](modulomaps.md), e pela mesma razão:
quem foi conferir a cota sabe o que o cabeçalho não sabe (prancha em unidade errada, bloco inserido
escalado, modelo em milímetros declarado em metros). Sem essa regra, uma reconversão em massa mudaria
em silêncio o valor de toda medida já anotada no canteiro. Fora da tabela de unidades plausíveis, e
fora de uma janela de largura plausível, **não há escala** — a prancha volta a medir em fração da
largura e diz isso.

**A janela de plausibilidade não é paranoia — o primeiro DWG real testado caiu nela.** *Portal
Residence II*, `AC1032`, declara `$INSUNITS = 2` (**pés**); aceitá-lo daria uma prancha de **143 km**
de largura e faria toda parede medir ~300× o valor certo. É o caso comum do template de AutoCAD que
ninguém trocou: o cabeçalho **mente com frequência**, e num desenho de construtora brasileira "pés"
é quase sempre resíduo, não declaração. Por isso o metro derivado é sempre *conferível* — a
procedência aparece na tela, e corrigir é traçar uma cota. Validação viva do caminho inteiro (os dois
desfechos + a soberania) em
[pra3b_escala_test.py](../../testes/e2e/pra3b_escala_test.py).

**Quando a coordenada contradiz o cabeçalho, ganha a coordenada.** O mesmo `confrontantes.dwg` que
declara pés desenha em `(469.347 , 8.564.841)` — *easting* e *northing* de UTM no hemisfério sul, que
**por definição estão em metros**. O cabeçalho é o template que ninguém trocou; a coordenada é
evidência. Se um aglomerado tem o centro dentro da janela UTM (§4), o motor usa metro e **declara que
sobrepôs** (`unidade_corrigida` na memória e na faixa da tela).

Isso não é refinamento — é o que impede a §4.5 de piorar o defeito que veio consertar. Enquanto a
folha media 143 km a escala era recusada e a prancha ficava sem régua, que é ruim mas honesto. Com
cada desenho na folha certa, a conta em pés cairia **dentro** da janela e o módulo publicaria **338 m
para um desenho de 1.109 m** — errado por 3,28× e com cara de certo, que é o desfecho pior. O ganho
que passa despercebido é o oposto: o levantamento que **não declara** `$INSUNITS` (o caso mais comum
desta seção) passa a ter régua, em vez de exigir que alguém calibre com o dedo o que o arquivo já
sabia.

Três consequências de desenho:

- **Coordenada normalizada pela LARGURA nos dois eixos.** Normalizar `y` pela altura (o óbvio)
  distorceria o aspecto e faria a mesma diagonal medir diferente conforme a folha.
- **Sem escala, mede-se assim mesmo** e o valor sai em *fração da largura*, declarado na tela. A régua
  de dados honestos aplicada ao caso em que a resposta certa é "não sei em quanto isso dá".
- **A medida carimba a escala com que foi tirada** (`Medicao.escala_aplicada`), como a linha do
  orçamento guarda o snapshot do item. Recalibrar depois **não** reescreve o número que alguém já
  anotou e levou para o canteiro: o que muda é a medida passar a se declarar `desatualizada`.

**Quem calibra não é quem mede.** `calibrar/` exige `prancheta.documento.edit` (quem governa o acervo),
não `marcacao.edit` (que o campo tem): recalibrar muda, de uma vez, o valor de toda medida que qualquer
um tirar dali. A referência usada fica gravada, para a calibração ser auditável.

### 13.3 Permissões — e o verbo separado

Três permissões novas, e a terceira é a que importa:

| Permissão | O que abre | Personas de fábrica |
|---|---|---|
| `prancheta.marcacao.view` | ler a caixa de apontamentos | `projetista`, `engenharia`, `campo`, `diretoria` |
| `prancheta.marcacao.edit` | apontar, comentar e medir | `projetista`, `engenharia`, **`campo`** |
| `prancheta.marcacao.resolver` | encerrar ou reabrir o tópico | `projetista`, `engenharia` |

O `campo` recebe `edit` porque **apontar o que está errado no desenho é o trabalho dele** — é a razão
de a fatia existir — e **não** recebe `resolver`: quem aponta não é quem declara que acabou, senão a
fila esvaziaria pelo lado errado, antes de o projetista responder. Mesma classe do `publicar` (§9) e
do `aprovar` do Orçamento, com a lição do **D28** aplicada na fatia que cria o verbo: ele nasce com
persona que o tenha.

Ler a prancha e ler os apontamentos são permissões **separadas**: há cliente que compra o acervo para o
campo consultar sem abrir a conversa técnica para todo mundo.

**A parede do BCF é comercial, não de permissão.** Marcar dentro do sistema vem com o módulo;
*atravessar* para o software do projetista é o formato `bcf` de `formatos_prancheta` em
[payment/planos.py](../../payment/planos.py) — que já estava lá antes desta fatia. Exportar e importar
respondem **402** (reusando a `FormatoNaoContratado` do upload, para o frontend tratar um contrato de
parede comercial no módulo inteiro), nunca 403: o cliente não está proibido, ele não contratou, e a
saída é comprar.

### 13.4 A tela

A caixa de ferramentas do visualizador tem cinco modos (mover · marcar · medir · área · escala), alvos
de 46 px e rótulo a partir do tablet — a régua da §9.1. Em modo de desenho **um dedo aponta e dois
continuam dando pinça**: perder o zoom enquanto se mede tornaria a medida imprecisa justamente onde
ela importa.

A camada de marcação recebe as coordenadas já convertidas pelo enquadramento que a `Vista2D` publica,
em vez de recalcular a transformação por fora. Duas cópias da mesma matriz divergiriam no primeiro
ajuste de gesto, e o sintoma seria o pino a dois dedos de onde alguém o colocou — o pior defeito
possível numa ferramenta cujo produto é apontar *onde*.

**O limite declarado:** a sobreposição só existe onde **nós** desenhamos a prancha. O PDF abre no leitor
do próprio navegador dentro de um `<iframe>` e não aceita camada (e a única derivada de PDF é a
miniatura de 600 px, declarada como "reconhecer a prancha, não ler a cota"); no 3D o ponto de vista do
BCF é câmera, não ponto na folha. Nos dois casos a marcação **continua funcionando sem âncora** — dá
para apontar, conversar, resolver e exportar em BCF — e a tela diz isso, em vez de oferecer um gesto
que erra o alvo. Registrado como [D37](moduloprancheta.md).

A fila de decisão do cockpit ganhou as três linhas que faltavam: marcações abertas, **atribuídas a
mim** (a linha que a PRA.0 declarou e deixou por preencher) e **abertas em revisão superada** — ninguém
resolveu e o desenho mudou embaixo. A última é pergunta, não lixo: a resposta ("ainda vale?" / "já
era") é humana, por isso é fila e não limpeza automática.

**Toda linha da fila carrega o próprio verbo, e é isso que separa fila de placar.** A régua do módulo
([frontend.md §1.6](../frontend.md)) pede cockpit com fila de decisão; contar sem oferecer a saída
manda a pessoa procurar o remédio noutra aba, que é o silo que um sistema de gestão *integrada*
existe para não ter. Vale nos dois sentidos: a faixa do **acervo pendente** publica o lote inteiro, e
o **cartão** publica a sua própria prancha — mesma decisão, alcance diferente, mesma alçada
(`prancheta.revisao.publicar`). Quem não tem a permissão continua vendo o estado e a frase de quem
resolve; esconder a linha faria a prancha que não abre parecer defeito do sistema. Como isso faltava
e o que custou está no [D85](../historico-correcoes.md).

**A fronteira que o verbo em massa respeita:** ele só alcança documento **sem** vigente. Trocar o
desenho que o campo executa continua sendo decisão prancha a prancha, com motivo — publicar em lote
por cima de vigentes seria mudar o que se executa em obra como efeito colateral de um botão.

### 13.9 Recalibrar CONVERTE a medida — e deixa recibo

A regra anterior era não tocar: a medida tirada com outra régua ficava como estava e apenas se
declarava `desatualizada`, tracejada na tela, para não reescrever um número que alguém pudesse ter
anotado e levado para o canteiro.

**O uso derrubou a regra** *(decisão do dono, 15/08/2026)*. Ninguém recalibra por esporte — recalibra
porque a régua estava errada, e a medida com ela. Deixar o número velho na tela entregava o erro com
aparência de conferido, que é o defeito mais caro deste módulo.

Converter é **exato**, e é o desenho que permite isso: `Medicao.pontos` guarda os vértices normalizados
pela largura da folha, então a medida sempre foi derivável e `valor` era cache. Recalcular não inventa
dado — refaz a conta que o `medir()` já fazia, com a régua certa.

E não é reescrita silenciosa. O valor anterior vai para **`valor_anterior`** com a régua que o produziu
e o instante; a resposta do `calibrar/` traz `medidas_recalculadas`, para a tela poder dizer "3 medidas
foram recalculadas" em vez de o número mudar sozinho. Recalibrar com a **mesma** régua não gera linha
de histórico — recibo cheio de ruído é recibo que ninguém lê quando precisa.

## 14. Snap de medição — a mira que gruda no traço

Medir clicando "por cima" da linha entrega o número errado **com cara de certo**. Numa folha onde 1
pixel vale 4 cm, dois cliques a três pixels do canto viram 8 cm de erro numa cota que ninguém
confere — e no canteiro isso vira parede no lugar errado. O CAD resolveu isso há trinta anos com o
OSNAP, e é ele que esta seção reconstrói: a mira gruda na **extremidade**, no **meio**, no **centro**,
no **quadrante**, no **nó** e no **cruzamento**.

### 14.1 De onde sai a geometria — e por que não das entidades

A prancha é mostrada dentro de um `<img>`, e isso é **decisão de segurança** (§9.05): o SVG que sai
do conversor carrega texto vindo do arquivo do cliente, e injetá-lo inline no DOM executaria qualquer
`<script>` que atravessasse o motor. Dentro de `<img>` o SVG é imagem — e imagem não tem vértice que
se possa consultar. Logo, a geometria precisa chegar **por fora**.

Ela sai de um `Recorder`, e **nunca** das entidades cruas do modelspace. A diferença não é de gosto:
o gravador guarda a geometria já achatada, com transformação de bloco, XREF e escala de inserção
aplicadas. Percorrer as entidades cruas daria pontos no sistema de coordenadas do bloco, e a mira
grudaria a metros do traço que a pessoa está vendo — o pior defeito possível numa ferramenta cujo
produto é apontar *onde*.

**E o gravador é o do `SVGBackend`, lido depois de o arquivo sair** — não o `recortado` que entrou
nele. É contraintuitivo e é a regra central desta seção: o índice tem de descrever o arquivo que a
tela recebe, então ele é tirado da mesma geometria que virou `<path>`, já no espaço do `viewBox`.
Normalizar vira uma divisão pela largura do `viewBox`, e **nenhuma página é recalculada em lugar
nenhum** — a mesma política que a régua da escala já segue (§13.2: quem arbitra margem e extensão é o
`ezdxf`, e a resposta se pergunta a ele).

As duas armadilhas que essa regra fecha estão registradas no
[D90](../historico-correcoes.md): a página deduzida não é a emitida (o `ezdxf` arredonda para
0,1 mm, reescala com `fit_page` e centraliza a sobra), e o `Player.replay()` entrega `PathRecord` e
`FilledPathsRecord` **por referência**, de modo que emitir o SVG transforma *in place* a geometria de
quem a emprestou.

O recorte por folha continua vindo antes da emissão, e pela razão de sempre: com o player inteiro,
cada folha indexaria o desenho todo, e a mira grudaria em traço de outra prancha.

**Hachura, sólido e texto não entram no índice** — é a regra do AutoCAD, onde OSNAP não pega em
hachura nem em contorno de glifo, e aqui ela foi medida antes de virar regra: o preenchimento rendia
95% do índice e **metade dos seus pontos não tem tinta embaixo** (o contorno de uma hachura é a
fronteira de um `<pattern>`, não um traço). Entrando como `extremidade`, ganhavam da parede que a
pessoa mirava.

### 14.1b O zoom é da CAIXA, não do `scale()`

A prancha é um `<img>`, e ampliá-la com `transform: scale(z)` **não** dá zoom vetorial: o navegador
rasteriza o SVG uma vez, no tamanho de layout, e estica o bitmap. A 81× cada pixel do raster vira um
bloco de 38 px, e o traço aparece a até **17,9 px** de onde ele matematicamente está — com a mira
certa por cima. Por isso a vista cresce a **caixa** (`width`/`height` em pixels de tela) e deixa o
`scale()` só para o que passar de `LARGURA_MAXIMA_DE_CAIXA`, patamar em que o navegador desistiria de
pintar. Custa o mesmo: o Chromium pinta o SVG por tiles, e só o que está visível.

**A caixa só existe se o aspecto exato do `viewBox` chegar — e ele é correção, não conforto.** Sem
ele a vista cai no `scale()` sobre uma caixa de lados **arredondados a inteiro** pelo navegador
(`naturalWidth`/`naturalHeight`), e o `preserveAspectRatio` passa a escalar o conteúdo por
`naturalHeight/viewBoxAltura` em vez da razão exata: sobra erro **relativo** de ~2×10⁻⁴, ancorado no
topo da folha, invisível no enquadramento e multiplicado pelo zoom. Por isso `prepararSvg` devolve a
geometria **mesmo quando não há espessura a renormalizar** — antes ele devolvia `null` nesse caso, e
a falha do conforto derrubava junto a correção, sem aviso, porque a prancha continuava abrindo. No
acervo de 15/08/2026 eram 15 de 528 SVGs nessa situação, com desvio calculado de **16.000 a 20.000 px
a 5.000×** (folhas pequenas, onde arredondar a inteiro pesa mais).

### 14.2 O sidecar

Um binário por folha, ao lado do SVG, servido pela porta única do impexp (espécie `snap`, mesmo gate
e mesmo `?v=` da derivada — o cache velho aqui é especialmente cruel, porque a mira *parece*
funcionar: gruda com precisão no traço que não existe mais).

```
SNAP2 · uint32 n · uint32 m · uint8 truncado
      · float64[n] x · float64[n] y · uint8[n] tipo · float64[4m] segmentos
```

**`SNAP2` desde 15/08/2026** — o `SNAP1` era `float32`, e 32 bits em coordenada normalizada dão
degrau de 6×10⁻⁸, que numa folha A1 vale 0,00005 unidade de desenho: a quarta casa decimal, e o
sistema promete a quinta (§14.13). O leitor da tela aceita os dois marcadores; sidecar antigo abre
com a precisão que tem.

X e Y em **blocos separados**, não intercalados: a busca varre X primeiro para descartar candidatos, e
intercalar puxaria para o cache um Y que não vai ser usado. Binário e não JSON porque o mesmo milhão
de pontos custa um parse que trava a aba no celular, enquanto o binário vira `Float32Array` com uma
cópia de memória.

### 14.3 O teto é ponto indexado, nunca megabyte

A medição de 15/08/2026 ([custo-snap.md](../medicoes/custo-snap.md)) matou a ideia de cobrar por
tamanho de arquivo com dois casos do próprio acervo:

| Arquivo | Tamanho | Pontos |
| --- | ---: | ---: |
| `fundações_3.4.dwg` | 0,18 MB | **464.268** |
| `Poligonal.dwg` | 6,36 MB | **466** |

Trinta e cinco vezes maior em disco, mil vezes menor em custo. A régua que converte teto em custo —
**~10,9 bytes de banda e ~0,23 KB de RAM por ponto** — está em `payment/planos.py §5.7`, junto dos
valores.

### 14.4 O teto degrada, não recusa

Passou do teto do plano, o índice sai **parcial** — indexa primeiro linha, arco e polilinha, que é
onde se mede, e preenchimento depois — e a tela diz "snap parcial" com a oferta do pacote. Medir
continua funcionando sempre, com ou sem mira: cobrar não pode virar prancha que não abre.

Pela mesma lógica, **falha na extração nunca leva o SVG junto**. O snap é um extra pago; a prancha é
o produto. Cliente que perde a visualização porque um índice estourou abriria chamado dizendo que o
sistema quebrou — e estaria certo.

### 14.5 A interseção, e por que ela não explodiu

Cruzar todo-com-todo é O(n²): numa planta de 300 mil segmentos são 4,5 × 10¹⁰ pares, a mesma classe do
estouro de 62 GB do D57. A varredura em grade só compara segmentos que dividem célula, e a travessia
de cada segmento é **exata** (Amanatides & Woo), não pela caixa envolvente — uma diagonal tem caixa de
185 mil células e toca ~860.

Hachura e texto ficam **fora do cruzamento**, de propósito: uma hachura densa gera milhões de
interseções reais e inúteis (ninguém mede até o cruzamento de dois riscos de hachura), e seriam elas
que estourariam o teto, expulsando a extremidade de parede que importa. No acervo medido, interseção
ficou entre 0,03% e 1,4% dos pontos.

### 14.6 O limite declarado: arco não tem centro

Curva **fechada** ganha centro e quadrante — num círculo ou elipse o centro da envolvente *é* o centro
da figura, e os meios das arestas *são* os quadrantes, exatos. Arco **aberto** não ganha: a envolvente
dele não contém o centro da circunferência, e publicá-lo daria uma mira que gruda no vazio com a
confiança de quem acertou. Arco aberto entrega extremidade e meio-do-arco, que são verdade.

### 14.7 A tela

Forma, não cor: quadrado é extremidade, triângulo é meio, círculo é centro, losango é quadrante, X é
interseção e **ampulheta é "próximo"** (algum lugar sobre o traço). É a convenção do AutoCAD, que todo
projetista já lê sem aprender — e distinguir só por cor excluiria quem tem daltonismo, além de que a
tela sob sol perde saturação muito antes de perder forma.

O "próximo" **precisa de glifo próprio**, e não do triângulo do meio: os dois caem sobre a linha, e um
glifo só para os dois faria a pessoa medir do meio do segmento achando que mediu de onde apontou — erro
que a mira não denuncia, porque ela acendeu.

**A escolha é por faixa, não por distância pura.** Mirando o canto de uma parede, o meio do segmento
vizinho pode estar 3 px mais perto do cursor que a própria extremidade; por distância, a mira agarra o
meio. Canto e cruzamento formam a primeira faixa, geometria de círculo a segunda, "algum lugar da
linha" a terceira — e só dentro da mesma faixa a distância decide. A abertura do ponto notável é de
18 px e a do traço, 8 px, para o traço nunca competir com o vértice.

A mira é desenhada em tamanho de **tela**, como o resto da camada de marcação: se escalasse com o
zoom, aproximar para conferir um canto faria a mira cobrir exatamente o canto. E o **clique cai no
ponto grudado**, não no do dedo — se não caísse, a mira seria enfeite: mostraria o canto certo e
mediria o lugar errado.

### 14.8 A prancha antiga ganha snap por pedido, não por varredura

O acervo já convertido não é reprocessado em massa quando alguém assina o recurso: seria uma onda de
conversão pesada de uma vez, sobre desenho que talvez ninguém vá medir. O caminho é o verbo
`reprocessar/` que já existe, oferecido na prancha aberta como *ativar snap* — quem quer, pede, e paga
só o que pediu.

### 14.9 O índice descreve ESTA folha — e o defeito que ensinou isso

O desenho tem geometria que a folha não mostra. Registros cuja envolvente o `_caixas` descarta não
entram no `_agrupar`, não dimensionam a página e **não são desenhados pelo backend de SVG** — mas o
extrator, que percorre a geometria já achatada do gravador, os colhia assim mesmo.

Medido na prancha `001` em 15/08/2026, com a folha indo de 0 a 1 em X:

| | índice de snap | geometria do SVG |
| --- | --- | --- |
| x | 0,0116 … **1126,43** | 0,0116 … 0,988 |
| y | **−793,90** … 0,70 | 0,0116 … 0,70 |

**99,88% dos pontos daquela prancha eram fantasma** (516.587 → 627 depois do filtro). O sintoma na tela
era cruel: a mira grudava *com precisão* em vértices que não existem no desenho, perto de onde o cursor
estava. Quem media via a mira acender e o número sair errado — e nada na tela sugeria por quê.

Por isso o índice agora **descarta o que cai fora da folha**, ponto e segmento, com folga para a borda
do recorte. A regra é a que dá nome à seção: o sidecar descreve a folha que está na tela; o que não
cabe nela não é ponto de snap. O descarte vai para a memória de conversão (`pontos_fora_da_folha`) —
número grande ali é sinal de desenho com sujeira, não de defeito nosso.

### 14.10 A bancada: por que pixel não se afere no olho

Três tentativas de conserto falharam porque o defeito foi diagnosticado por leitura de código e
aritmética, não por medição. As duas primeiras hipóteses — letterbox do `<img>` e arredondamento de
`naturalWidth` — eram plausíveis, calculáveis e **erradas**.

O que fechou o caso foi medir no navegador de verdade (Chromium headless), com duas perguntas:

1. **A transformação imagem→tela erra quanto?** Comparando `getScreenCTM()` do browser com o
   `paraTela` da vista: **0,30 px em X e 0,01 px em Y a 81× de zoom**. Não era a transformação.
2. **Há traço desenhado onde o snap gruda?** Desenhando o SVG num canvas ampliado 81× em volta de
   pontos reais do sidecar e procurando o pixel de traço mais próximo: antes, **7 de 8 pontos sem
   traço nenhum na janela**; depois do filtro, **9 de 9 com distância 0 px**.

A segunda pergunta é a que vale para qualquer suspeita futura de mira desalinhada, e é barata: não
depende de opinião sobre o que "parece" fora do lugar.

### 14.11 O leitor de coordenadas — a barra de status do CAD

Ao lado do distintivo de zoom, uma pílula mostra onde o ponteiro está; clicada, ela abre um painel
com o resto ([`Coordenadas.tsx`](../../frontend/src/modules/prancheta/visualizador/Coordenadas.tsx)).
Existe pela mesma razão que existe no AutoCAD: **quem desenha percebe a tela discordar do desenho
antes de gravar medida errada** — e, quando discorda, tem número para relatar em vez de "parece
torto", que foi o que custou três consertos falhos ao D90.

| bloco | o que diz | para que serve |
| --- | --- | --- |
| ponteiro | **coordenada de desenho** · fração de folha · mm de papel · unidade de `viewBox` | a primeira é a do CAD (§14.12) e encabeça o painel; as outras três são réguas nossas — a fração é como tudo é gravado, o mm é a linguagem de quem confere na prancha impressa e a unidade de `viewBox` é o número exato que o backend indexou |
| snap | tipo, ponto e **Δ em pixels de tela** | com o cursor sobre o traço, o Δ é o afastamento da mira — medido, não estimado |
| do último vértice | distância e rumo | a entrada dinâmica do CAD, durante a medição; sai do ponto do **snap**, que é o que o clique vai gravar |
| tela | zoom · escala · **caixa pedida × caixa real** · `viewBox` · papel | pedir uma largura não é receber uma largura; se as duas divergirem, o desenho está pintado numa escala e a mira posicionada em outra — erro relativo, multiplicado pelo zoom |

O botão **copiar leitura** despeja tudo em texto, para o relato vir com número. Fora de contexto
seguro (acesso por IP, comum no canteiro) não há `navigator.clipboard`: aí o painel é selecionado e o
Ctrl+C resolve, em vez de um botão que não faz nada e não diz por quê.

**Ele se escreve por fora do React.** O ponteiro emite dezenas de eventos por segundo; virar estado
faria a árvore inteira — inclusive a camada com todas as marcações — re-renderizar a 60 Hz, travando
a prancha justamente enquanto se mede. A vista publica uma função de escrita e o componente atualiza
os próprios nós de texto — a mesma razão pela qual o índice de snap vive em `ref`.

**Aferido a 15/08/2026** na `001`, no app de verdade (ampliar primeiro, snap depois, foto por
último), em Chromium com tela a 100% e a 150%:

| zoom | escala | caixa pedida | caixa real | mira até a tinta |
| ---: | ---: | ---: | ---: | ---: |
| 83× | 113.103 px | 113.103 × 80.656 | idem | **0,00 px** |
| 1.005× | 1.368.579 px | 1.368.579 × 975.967 | idem | **0,00 px** |
| 5.503× | 7.491.009 px | 7.491.009 × 5.342.018 | idem | **0,00 px** |

### 14.12 A coordenada de desenho — devolver o que a conversão tinha trocado

A conversão troca a régua do arquivo pela da folha, e as três que o leitor mostrava eram todas
nossas. **A planta já vinha com coordenada**, a mesma que o AutoCAD exibe na barra de status, e é
contra ela que se confere um vértice contra o arquivo de origem. `DesenhoProjeto.mundo` a devolve:

```
x_desenho = origem_x + x_folha · por_folha
y_desenho = origem_y − y_folha · por_folha        ← o SVG cresce para baixo, o CAD para cima
```

`origem` é o **canto superior-esquerdo da folha**, margem incluída; `por_folha` é quantas unidades de
desenho cabem na largura inteira da folha — a mesma grandeza de `escala_valor`. Na `001`:
`origem (−10, 604)`, `por_folha 861` — os 841×594 mm do desenho mais os 10 mm de margem de cada lado.

**É medida na emissão, nunca deduzida** ([`dxf.py::_mundo_da_folha`](../../backend/moduloprancheta/motores/dxf.py)),
e a técnica é o defeito do D90 virado do avesso: como o `get_string()` transforma os registros *in
place*, a envolvente do gravador do backend **antes** dele está em unidade de desenho e **depois**
está em unidade de `viewBox`. Duas envolventes da mesma geometria dão a afinidade inteira, sem tocar
em interno do `ezdxf` e sem refazer a conta da página — que erraria, porque o `ezdxf` ainda arredonda
a folha para 0,1 mm, reescala com `fit_page` e centraliza a sobra.

Vazio (`{}`) é resposta e não falta: folha convertida antes desta medida existir, envolvente
degenerada, motor que não rende coordenada (PDF, imagem). Aí o leitor mostra `—` e a palavra
**reprocessar** — não some, porque some, a linha de baixo seria lida como se fosse ela.

**A folha antiga não ganha o número retroativamente**, e não é preguiça: deduzi-lo depois é
exatamente a conta que o D90 provou errada. Quem quer a coordenada numa prancha já convertida
reprocessa a revisão.

### 14.13 A quinta casa decimal — decisão do dono, e o que ela exigiu

**"Todos os projetos terão 5 casas decimais"** *(decisão do dono, 15/08/2026)*, e o pedido foi
explícito em não arredondar: é **resolução**, não formatação. Cada etapa do caminho tem de *carregar*
1e-5 unidade de desenho; a que não carregar é a que manda, e era assim que a mira "travava na casa
decimal mais próxima" — o índice guarda a coordenada exata e a **tinta** só existe onde a grade do
SVG permite. Como o desvio é uma fração de unidade da grade, ele é invisível no enquadramento e
cresce proporcional ao zoom.

Medido na `001` (folha de 861 unidades de largura) **antes** da mudança, os três funis que a violavam:

| funil | passo em unidade de desenho | contra 1e-5 |
| --- | ---: | --- |
| grade do SVG (inteiros, 10⁶) | 0,000861 | **86× grosso** |
| `float32` do sidecar | 0,0000513 | **5× grosso** |
| `TOLERANCIA_FUSAO` (10⁻⁶ da largura) | 0,000861 | **86× grosso** |

Os três foram abertos:

1. **A grade passou a ser dimensionada pela precisão** (`_grade_de_saida`), e não só pela regra do
   D46: `lado_maior_da_folha / PRECISAO_DE_DESENHO`, com folga de 0,1% porque a folha emitida é um
   fio maior que a estimada — modelar a página inteira seria refazer o erro do D90. Na `001` a grade
   foi de 10⁶ para **86.186.100**, e o passo de 0,000861 para **0,00000999**.
2. **O sidecar virou `SNAP2`, em `float64`.** Trinta e dois bits em coordenada normalizada dão degrau
   de 6×10⁻⁸ — 0,00005 unidade nesta folha, a quarta casa. O leitor da tela aceita os dois
   marcadores: sidecar antigo abre com a precisão que tem, e não se reescreve precisão que um arquivo
   não carrega.
3. **A fusão de pontos passou a valer uma unidade da grade emitida** (`Folha.fusao`). Abaixo disso os
   dois pontos ocupam o mesmo inteiro no `<path>` e são o mesmo lugar no arquivo; acima, fundir apaga
   vértice que o projeto distingue.

A conversão **confere e registra** o que obteve (`detalhe["precisao_desenho"]`) em vez de prometer:
folha grande demais para a grade ganha `precisao_insuficiente`, porque o teto de `GRADE_MAXIMA`
continua valendo e num levantamento de milhões de unidades a quinta casa pediria 8,5×10¹¹.

**O custo, medido na `001`:**

| | antes | depois | |
| --- | ---: | ---: | ---: |
| SVG | 214.484 B | 278.650 B | **+29,9%** |
| sidecar | 51 KB (`float32`) | 99 KB (`float64`) | ~2× |
| pontos do índice | 3.074 | 3.079 | +5 (fusão mais fina) |
| relógio da conversão | — | — | sem mudança |

**Vale para folha reprocessada.** A precisão nasce na emissão: prancha convertida antes não a ganha
retroativamente, e o leitor mostra `reprocessar` em vez de anunciar cinco casas que não tem.

### 14.14 O fundo da folha sai em `100%`, e a grade é a razão

O `SVGBackend` emite o papel como um `<rect>` com os lados em unidade de `viewBox`. Depois que a
grade passou a ser dimensionada pela precisão (§14.13), esses lados chegaram a 8,6×10⁷ na `001` — e
**o Chromium para de pintar um caminho preenchido em 2²⁵ (33.554.432)**. O fundo cobria um terço da
folha; o resto ficava sem papel.

O traço não sofre, porque é feito de segmentos curtos que não esbarram no teto. É por isso que o
sintoma é da família da tarja preta do §9.06: a prancha abre inteira, a 60 fps, e vira linha clara
sobre fundo claro em dois terços da área. E o `librsvg` pinta a folha inteira nos dois casos — logo
**miniatura e PDF não denunciam**; o defeito só existe no navegador, que é onde a prancha é lida.

`dxf.py::_fundo_em_porcentagem` reescreve o retângulo para `width="100%" height="100%"`, que cobre a
mesma área sem o navegador construir um caminho de 8,6×10⁷ unidades. **A grade não é tocada** — é ela
que carrega a quinta casa, e o papel não precisa de precisão nenhuma. A troca só vale para o
retângulo cujos lados batem **dígito a dígito** com os do `viewBox`: qualquer outro é desenho do
projetista.

Vale para folha reprocessada, pela mesma razão da §14.13 — o fundo nasce na emissão.

### 14.15 O degrau do `dwg2SVG` devolve folhas, não o documento cru

O último degrau da escada de economia (§4.1) troca o nosso desenhista pelo `dwg2SVG` do LibreDWG. A
saída crua dele tem três defeitos conhecidos — texto em código de escape, símbolo com origem
deslocada e desenhos distantes na mesma folha —, e `motores/svg_do_motor.py` existe para os três.

**A convenção do degrau:** `corrigir_texto` roda primeiro (substituição byte a byte sobre o documento
inteiro, não mexe em coordenada) e a separação depois, que é a que lê geometria. O degrau devolve
`partes`, como o caminho do DXF, e `detalhe` carrega `renderizador="dwg2SVG"` e `convencao="mundo"`,
que é o que a tela lê para **não** aplicar a normalização de folha por cima.

**A correção de origem é por símbolo, e é medida — nunca aplicada em bloco.** O `dwg2SVG` escreve o
`<defs>` em duas convenções misturadas, e qual é qual só o próprio símbolo diz: a interpretação certa
é a que deixa a geometria mais perto da origem local. Medido sobre 18 DWGs do acervo, a fração de
geometria que cai dentro do `viewBox` que o próprio arquivo declara:

| Grupo | Cru | Corrigido |
|---|---:|---:|
| Blocos por referência (família AutoCAD Electrical) | 50–61 % | 99–100 % |
| Sem `<use>` nenhum | inalterada | inalterada |
| Já corretos crus | inalterada | inalterada |

Onde há bloco por referência — que é **por que este degrau existe** — metade do desenho ficava fora
da folha. Onde não há, a correção é inerte por construção.

**A separação não pode derrubar o degrau.** Aqui a alternativa a uma folha imperfeita não é uma folha
melhor: é `recurso_excedido`, nenhuma prancha. Documento com forma que o leitor não previu sai
inteiro e sem separar, com `separacao_falhou` no detalhe — para não virar melhora silenciosa.

---

## 15. Espessura de traço — o fio de cabelo do CAD

A prancha é um `<img>` escalado por `transform`, então o traço amplia junto com o desenho: a 20× o que
era um fio vira uma tarja, e o detalhe que a pessoa ampliou para conferir fica coberto pela própria
linha que queria ver.

**O conserto cabe no cabeçalho.** O `ezdxf` emite a espessura em **classes CSS** — `.C1 { stroke-width:
405 }` —, uma por combinação de cor e espessura, e não em cada `<path>`. São algumas centenas de bytes
no começo do arquivo, qualquer que seja o tamanho do desenho. A vista reescreve só esse pedaço a cada
degrau de zoom e remonta o blob **por partes**, sem nunca copiar o corpo do SVG, que pode ter 10 MB.

**Constante ao ampliar, proporcional ao reduzir.** Segurar 1,1 px também na saída faz a prancha
reduzida virar um borrão: a 20% do enquadramento, uma planta densa tem mais traço que pixel e todo
traço de largura inteira se funde num bloco. Reduzir é o gesto de "ver o conjunto", e ele precisa de
traço sub-pixel. Medido sobre prancha real:

| Zoom | 20% | 50% | 100% | 1.000% | 10.000% | 50.000% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| px de tela | 0,22 | 0,55 | 1,1 | 1,1 | 1,1 | 1,1 |

**A regra de preenchimento é reemitida verbatim.** O `ezdxf` escreve `stroke-width: none` nas classes
de hachura e sólido; a primeira versão descartava essas regras ao remontar — **10 das 15** no arquivo
real —, e a classe sumia do SVG, jogando o preenchimento no preto padrão. É a família da tarja preta do
D46: a folha abre, parece pronta e esconde desenho.

### 15.1 Hierarquia de penas: o que o arquivo não traz

A queixa "todas as linhas saem iguais" não é perda nossa. Medido em 4 DWGs do acervo:

| Arquivo | Espessuras distintas | Cores | Camadas sem espessura |
| --- | ---: | ---: | --- |
| `014.dwg` | **1** | 12 | **53/53** |
| `AEGS06.DWG` | **1** | 9 | **20/20** |
| `AEGS10.DWG` | **1** | 2 | **40/40** |
| `3ª_Etapa…dwg` | 6 | 5 | 3/13 |

Três de quatro **não carregam espessura nenhuma** — toda camada é `DEFAULT` — e ainda assim têm várias
cores. É a assinatura do desenho penado por **CTB**: a espessura mora na tabela de penas por cor, que
fica no computador do projetista e não viaja no DWG.

O que a vista faz é o que o AutoCAD faz no modelspace com exibição de espessura desligada: **fio de
cabelo constante**. Onde o arquivo declara espessura de verdade, a razão entre elas é preservada (a
mais fina vira ~1,1 px, com teto de 4 px); onde não declara, sai uniforme. Derivar espessura da cor
exigiria adotar uma tabela de penas, que é convenção de escritório e não de plataforma — fica como
expansão, não como padrão.
