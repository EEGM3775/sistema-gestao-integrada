# Pendências — achados de revisão em aberto

> **Natureza: status.** Este documento lista **só o que está quebrado ou em risco** — nada mais.
> Achado corrigido **sai daqui** e vai inteiro para [historico-correcoes.md](historico-correcoes.md);
> limite consciente e decisão de desenho vão para a **planta** do módulo; trabalho planejado vai para
> o [roadmap.md](roadmap.md). Guardar as três coisas aqui foi o que fez este arquivo chegar a 251 KB.
>
> IDs: `S*` segurança · `L*` bugs de lógica · `A*` backend/arquitetura · `F*` frontend ·
> `D*` achados de auditoria posteriores. Herdados dos dois laudos de 02/07/2026 (v01 segurança,
> v02 bugs/arquitetura/frontend), já absorvidos.

**Onde foi parar o que saiu daqui:**

| O que | Para onde | Por quê |
| --- | --- | --- |
| 125 achados corrigidos | [historico-correcoes.md](historico-correcoes.md) | Corrigido não é pendência — é histórico |
| D29 · D30 · D32 (Maps) | [modulos/modulomaps.md](modulos/modulomaps.md) | Desvio consciente da planta, com gatilho de reabertura |
| D35 · D36 · D37 · D55 (Prancheta) | [modulos/moduloprancheta.md](modulos/moduloprancheta.md) | Limite declarado do desenho, não defeito |
| D74 (antivírus) | [modulos/funcoesimpexp.md](modulos/funcoesimpexp.md) | Decisão do dono, adiada com método definido |
| D6 · D13 · D60 + backlog de ideias | [roadmap.md](roadmap.md) | Trabalho planejado, não achado |
| Decisões do Orçamento | [modulos/moduloorcamento.md](modulos/moduloorcamento.md) | Decisão de módulo |

---

## 🔴 Críticos

Nenhum em aberto. O **D76** — o orçamento de memória que media o processo e matava toda importação em
todo plano — foi achado e fechado em 08/08/2026, no mesmo dia; relato em
[historico-correcoes.md](historico-correcoes.md).

O crítico anterior foi o **D57** — a conversão sem teto de recurso, que levou uma passada
de medição a 62 GB de RAM —, fechado em 07/08/2026 pela PRA.1d; relato inteiro em
[historico-correcoes.md](historico-correcoes.md). O resíduo que ele deixou — **D61**, os 11 arquivos
que estouravam o orçamento mesmo no degrau — **fechou em 08/08/2026 pela remedição**, e não por
decisão de produto: eram consequência do teto que o D76 consertou. O outro — **D71**, o teto de
contêiner que faltava na frota geral — foi fechado em 07/08/2026, também no histórico.

## 🟠 Altas

### F2 — Selects carregam tabelas inteiras · 🟠 parcial 25/07/2026

Formulários carregam todos os clientes/fornecedores/empreendimentos para montar selects.
**Correção:** select assíncrono com busca server-side paginada (o backend precisa de
`SearchFilter` + paginação nesses endpoints).
**Andamento (25/07):** o SCM já resolveu dentro dele (`AsyncEntitySelect`) e a **listagem de
clientes** deixou de ser client-side — virou a carteira paginada com rolagem infinita
([frontend.md §5.8](frontend.md)). Efeito colateral tratado: como `/api/clientes/` passou a ser
paginado, `useClienteOptions` ([useEntityOptions.ts](../frontend/src/modules/erp/hooks/useEntityOptions.ts))
truncaria a lista em 50 **em silêncio** — pediria a primeira página e o cliente nº 200 sumiria do
formulário do ERP. Mitigado com `page_size=300` e comentário no código. **Falta** o select com busca
server-side de verdade nos formulários (clientes, fornecedores, empreendimentos).

### D39 — Os planos vendem 6 formatos geo, e o motor `gdal` não tem adaptador · 🟠 aberto

Achado ao escrever o PRA.8, e ele importa porque é o único desta leva com consequência para **quem
já paga**.

[`payment/planos.py`](../payment/planos.py) inclui `kmz` e `geojson` no plano **`basico`** — com o
comentário dizendo, nas próprias palavras, *"já cobrem o construtor pequeno, que recebe DXF do
projetista **e KMZ do topógrafo**"* — e o `profissional` acrescenta `shp`, `gpkg`, `qgis` e
`geotiff`. Mas [`motores/`](../backend/moduloprancheta/motores/__init__.py) tem quatro adaptadores
(`documento`, `dxf`, `dwg`, `ifc`) e **nenhum `gdal`**: o arquivo passa o paywall, sobe, consome
`storage_projeto_gb` e gera **zero derivadas**.

**Não é desonestidade do código** — e é por isso que é 🟠 e não 🔴. `planejar()` devolver lista vazia
é caminho previsto e documentado ali mesmo; `estado_dos_motores()` declara `implementado: false`; o
`conversao` do acervo responde `outro_modulo`, que é estado diferente de `sem_motor` justamente para
não dizer "tudo certo". O teste [pra8_prancheta_test.py](../testes/e2e/pra8_prancheta_test.py)
passou a **cobrar** essa declaração (§1), para a lacuna não virar silêncio. O problema é comercial: o
plano de entrada vende metade do caso de uso que o próprio comentário descreve.

**Duas saídas, e a escolha é de produto, não de engenharia:**

- **fechar o seam** (é a **PRA.7**): KMZ/SHP na Prancheta vira `Camada` no [Maps](modulos/modulomaps.md),
  que é o dono do dado geo (planta §3 — "a Prancheta abre, o Maps guarda"). Esbarra num nó: o Maps
  tem entitlement próprio, e o cliente `basico` provavelmente não o assina;
- **recuar no plano**: tirar os formatos geo de `formatos_prancheta` até o seam existir. Barato,
  reversível, e alinhado com a régua — melhor não vender do que vender travado.

Enquanto nenhuma das duas acontece, o teste que casa registry × planos
(`RegistryEPlanosTests`) **não pega isto**: ele confere que o formato existe e que o *tier* de motor
bate, e `gdal` é `livre`, que o plano habilita. Falta a terceira pergunta — *o motor tem adaptador?*

### D53 — A folha do projeto executivo pesa 13,6 MB e converte em 26 s · 🟠 aberto

Consequência direta do **D52**, e ela é honesta: enquanto o desenho era destruído na emissão
(coordenadas arredondadas a zero na grade esticada), o SVG era pequeno **porque estava perdendo
traço**. Com a folha certa a geometria é emitida inteira e pesa o que pesa.

Medido no `MaxPlast.dwg` (62.433 entidades no modelspace): folha #1 sai com **13,6 MB** e a conversão
leva **26 s**. A conversão é assíncrona e não faz ninguém esperar — o problema é o **download**: 13,6
MB no 4G do canteiro é justamente o cenário para o qual o módulo existe.

**Não é bug do recorte, é o teto do formato de entrega.** Um SVG descreve cada segmento em XML, com
coordenadas em texto; o mesmo desenho num buffer binário de coordenadas é uma fração disso, carrega
direto em GPU e dispensa parsear. É a fatia do render vetorial
([planta §12.6](modulos/moduloprancheta.md)), que já estava decidida por outros dois motivos (zoom sem
teto e snap) — este é o terceiro, e é o que mais aperta.

Enquanto isso não chega, o número está declarado e o acervo típico não sofre: a prancha de disciplina
comum (`UFRB…-IE`, 35.401 traços) sai com 3,4 MB.

### D17 — Duas trilhas de auditoria sem leitura unificada · 🟠 aberto

Criado junto do **D11**. A plataforma passou a ter **duas** trilhas append-only e independentes:
`nucleo.AuditLog` (backend — escritas de RH, leitura de PII, baixa financeira, NF, LGPD) e
`identity.EventoSeguranca` (IAM — reset de senha, troca de e-mail, escalada de privilégio,
desativação). A separação é consequência de a IAM ser autocontida (mesma razão de ela ter ganhado
SMTP próprio), mas **o auditor não tem onde ver as duas juntas**: `GET /api/auditoria/` só enxerga a
do backend, e a da IAM hoje só é legível por shell/admin.

Isso importa no incidente que motivou o D11: reconstituir "admin comprometido" exige cruzar o
`reset_assistido` (IAM) com o que a conta fez depois (backend), hoje manualmente e sem correlação por
`request_id`.
**Correção sugerida:** endpoint de leitura na IAM (`GET /iam/eventos-seguranca/`, gateado por
`plataforma.auditoria.view` — permissão que **já existe** no catálogo) + uma visão no frontend que
consulte as duas fontes, ou envio dos eventos da IAM ao `AuditLog` por JWT de serviço (Fase 10.8) com
outbox local para não perder evento se o backend estiver fora.

## 🟠 Altas

### D113 — a demo nasce com o dobro de clientes que o plano dela permite · 🟠 aberto 22/08/2026

Achado pelo dono, olhando o hub: o card **Requer sua decisão** anuncia
permanentemente *"Limite de clientes atingido — 2004 de 1000"*, e o bloqueio é
real (`POST /api/clientes/` → **402 `quota_excedida`**). Ou seja: **na demo não dá
para cadastrar cliente**, que é fundação e é justamente o que alguém quer
exercitar numa demonstração.

A causa é uma colisão entre dois artefatos do próprio projeto, e nenhum dos dois
está errado sozinho:

- [`semear_carteira_demo`](../backend/clientes/management/commands/semear_carteira_demo.py)
  tem `--clientes 2000` como **padrão**, e existe para provar que a carteira
  aguenta volume — *"com 20 cadastros qualquer implementação parece rápida"*;
- o tenant `demo` está no `profissional`, cujo teto de `clientes` é **1000**, e
  `clientes` está em `QUOTAS_APLICADAS` (trava de verdade).

Três saídas, todas baratas, e é escolha de quem opera a demo: baixar o padrão do
seeder (perde parte da prova de volume); re-semear menor após `--limpar`; ou pôr
o `demo` num plano sem esse aperto, deixando o `acme` (free) como o tenant onde a
parede de quota é visível de propósito — papel que o `planos.py` já dá a ele.

### D114 — no `profissional`, o teto de clientes não conversa com o de empreendimentos · 🟠 aberto 22/08/2026

Levantado junto do D113, e é a metade **comercial** dele — a de engenharia é
aquela; esta é decisão do dono.

O `profissional` (R$ 449) vende **10 empreendimentos** e **1000 clientes**. O
seeder modelou uma incorporadora realista e chegou a 6 empreendimentos, 2.706
unidades e 2.186 vendas: estourou o teto de clientes sem chegar perto do de
empreendimentos.

A conta que expõe a inconsistência: dez empreendimentos de porte médio — 200
unidades cada — dão 2.000 compradores, o dobro do teto. **Quem vende unidade
cadastra um cliente por unidade vendida**, então o limite que morde primeiro não é
o do portfólio que ele contratou: é o de clientes, e ele chega no meio de uma
venda.

Duas leituras possíveis, e a escolha é de posicionamento:

- **o portfólio é o limite de valor** → `clientes` sobe para acompanhar 10
  empreendimentos de porte real (2.000–3.000);
- **o `profissional` é para construtora que executa obra**, não para incorporadora
  que vende unidade → o teto está certo e vender 2.000 unidades é caso de
  `empresarial`. Aí é upsell legítimo, não fricção.

Não trava nada em produção hoje (nenhum cliente real). Fica aberto porque o
módulo de venda de unidade e carnê **existe** no produto, e é ele que faz o número
de clientes crescer rápido.

### D105 — as 200 conversões premium do `empresarial` podem custar mais que o plano · 🟠 aberto 16/08/2026

O `empresarial` (R$ 1.199/mês) vende **200 conversões pagas/mês** com `motores_prancheta` incluindo
`premium` — que é a Autodesk, custo dela e não nosso. O estudo de
[viabilidade](medicoes/viabilidade-economica.md) mostra que o desfecho depende inteiramente de qual
formato essas 200 são:

| As 200 conversões são… | Custo/mês | Contra R$ 1.199 |
| --- | ---: | --- |
| DWG (0,2 crédito) | R$ 206 | 17% da receita — sadio |
| Revit (1,5 crédito) | **R$ 1.548** | **negativo antes do armazenamento** |

É a **única linha da plataforma capaz de inverter a margem** — todo o resto do COGS medido é nosso e
é desprezível (converter um acervo inteiro custa centavos). E o risco cresce: o Model Derivative
subiu de preço em 2026 e atividades antes gratuitas passaram a ser cobradas.

→ **decisão comercial, antes da PRA.4 existir**: ou a quota passa a ser por formato ("200 conversões
*de DWG*"), ou vira cobrança por uso, ou o preço do plano absorve o pior caso. Enquanto o motor
premium não existe, nada quebra — mas o número já está publicado no catálogo.

### D103 — o degrau de RAM do plano caro não cabe na máquina · 🟠 aberto 16/08/2026

O [D101](historico-correcoes.md) transformou a memória da conversão em degrau de plano, e a medição
que o motivou mostrou que **servir o arquivo grande é questão de máquina, não de código**: o DWG de
64,9 MB converte no `dwg2dxf` (sai `0`, produz 531,8 MB de DXF) e morre só no nosso orçamento; o
`dwg2SVG` pede **2.410–3.069 MB** nos 7 pesados do acervo (roadmap PRA.1f).

A escada de hoje é `1.536 MB (nosso teto, explica) < 2.048 (Celery recicla o filho) < 3.072
(`mem_limit` do contêiner)`. O limite não é teórico — foi **medido no arquivo de 64,9 MB**: com
2.048 MB no subprocesso ele devolve `recurso_excedido` em 8,9 s; com 2.800 MB o processo morre com
**exit 137 (SIGKILL), sem exceção e sem rastro**, porque os 3.072 MB são do contêiner inteiro e o
Python pai já reserva ~1.150 MB de VA. Por isso o mapa do subprocesso está **achatado no topo**
(2.048 do `essencial` para cima) e o da conversão para em 1.900.

→ **decisão de dimensionamento**: subir `mem_limit` e `CELERY_WORKER_MAX_MEMORY_PER_CHILD` no deploy
e, **no mesmo commit**, os degraus de cima. `EscadaDeMemoriaPorPlanoTests` (4 testes) falha se a ordem
for invertida — foi ele que pegou a primeira versão deste mapa prometendo 2.800.

### D104 — o disco por tarefa suspensa é uma variável sem número · 🟠 aberto 16/08/2026

`FROTA_DISCO_POR_TAREFA_SUSPENSA_MB = 0` (`planos.py` §5.4e) existe desligado por decisão do dono
(16/08/2026: *"o disco será determinado por medição quando o software estiver próximo do
lançamento"*). Enquanto valer 0, a retomada **recomputa** o estado a cada volta — 56% do relógio,
medido — em vez de guardá-lo.

Quem for medir precisa de três grandezas que ninguém tem: quantas tarefas ficam suspensas ao mesmo
tempo em carga real, o tamanho mediano e de cauda do estado por tarefa (~85 MB só do DXF no arquivo
comum, **531,8 MB** no de 64,9 MB) e **o custo em segundos de serializar e reler** — que pode comer a
economia que o número existe para gerar. Referência de indústria e o porquê de este ser o caminho
mais caro dos quatro: [laudo §10](medicoes/fila-da-frota.md).

### D99 — o acervo já convertido não recebeu os consertos de 16/08 · 🟠 aberto 16/08/2026

Os consertos do [D92](historico-correcoes.md) (fundo da folha) e do
[D93](historico-correcoes.md) (origem dos símbolos no degrau `dwg2SVG`) agem **na emissão**. As
**758 derivadas** que já estão no storage foram gravadas antes e continuam como saíram: fundo
cobrindo um terço da folha, e prancha que caiu no degrau `dwg2SVG` sem a correção de origem.

O verbo existe e está pronto — `reprocessar` no `DocumentoProjetoViewSet`, com permissão própria
(`prancheta.conversao.reprocessar`) e botão na tela. **Falta rodá-lo**, e é decisão de quando: é CPU
do `worker-conversao` sobre o acervo inteiro, e enquanto a fila não tiver porteiro ([D98](#d98--o-trabalho-pesado-tem-freio-mas-não-tem-porteiro))
isso concorre com a conversão de quem estiver usando o sistema.

É a mesma classe de pendência que a §14.13 da planta já declara para a quinta casa decimal — e agora
são três motivos para a mesma passada, o que torna vantajoso fazer uma só.

### D91 — o dono ainda vê a mira fora do traço, e a bancada não reproduz · 🟠 aberto 15/08/2026

Depois dos quatro defeitos do [D90](historico-correcoes.md) fechados, o relato continua: **o desvio
cresce com o zoom e diminui perto do topo da planta** ("a 5.000× para eu conseguir ver o erro" perto
do topo; ~10 quadrados de snap até o vértice a 4.000× mais abaixo). Isso é a assinatura de um erro
**relativo** de escala em Y, ancorado no topo da folha.

Dois defeitos dessa família foram achados por leitura e corrigidos em 15/08/2026 (§14.1b da planta):
`prepararSvg` devolvia `null` quando não havia espessura reescrevível, derrubando junto o aspecto
exato; e o papel em mm nunca era lido, porque o recorte do cabeçalho parava no `?>` do prólogo XML.
Os dois valem para 15 dos 528 SVGs do acervo — **não explicam "em todos os arquivos"**.

**A bancada não reproduz.** Na `001`, no app de verdade, ampliando primeiro e medindo depois, em
Chromium com tela a 100% e a 150%: caixa pedida = caixa real e **mira a 0,00 px da tinta a 83×,
1.005× e 5.503×** (§14.11). Ou seja, o caminho medido está correto e o caso do dono tem alguma coisa
que a bancada não tem — prancha, navegador ou ambiente.

**Próximo passo é captura, não conjectura:** o leitor de coordenadas (§14.11) foi instalado para isso.
No caso que erra, a linha `caixa` × `real` decide entre "o navegador não deu a caixa pedida" (aí é
teto de rasterização de outro motor — o `LARGURA_MAXIMA_DE_CAIXA` foi medido **só no Chromium**) e
"a caixa confere e a tinta ainda assim discorda" (aí é o índice, não a pintura). Com a **coordenada
de desenho** (§14.12) o leitor passou a dar o número que fecha o cerco por fora: o vértice lido aqui
e o mesmo vértice lido no AutoCAD têm de bater — se baterem, o índice está certo e sobra a pintura;
se não baterem, o erro nasceu antes da tela. **Folha convertida antes de 15/08/2026 precisa ser
reprocessada** para trazer a coordenada.

**Uma causa concreta foi achada e fechada em 15/08/2026, e ela tem a forma certa do sintoma**
(§14.13): as coordenadas do SVG são **inteiras**, e com a grade de 10⁶ numa folha A1 a tinta só podia
existir em múltiplos de 0,000861 unidade de desenho, enquanto o índice guardava o valor exato. Meia
unidade de grade é invisível no enquadramento e **cresce proporcional ao zoom** — ~3 px a 5.000×,
metade do glifo da mira. O dono descreveu isso como "trava na casa decimal mais próxima" e decidiu a
régua: **precisão na quinta casa, sem arredondar**. Grade, sidecar e tolerância de fusão foram
redimensionados. Falta confirmar, com o acervo do dono reprocessado, se era **a** causa ou **uma
delas** — a `001` media 0,00 px de mira à tinta antes e depois, então este defeito não aparecia na
bancada de tinta (ela é cega a deslocamento **ao longo** do traço).

### D88 — o teto do snap é conferido entre registros, e um registro pode ser gigante · 🟠 aberto 15/08/2026

`indice_de_snap` confere o teto do plano **entre registros**, não entre pontos. No acervo normal isso
custa um excesso de 98 a 13.186 pontos sobre 600.000 (2,2%, ~143 KB) e é generosidade barata — erra
para o lado do cliente.

**A cauda muda a conta.** A remedição de 15/08/2026 achou `HS-UFBACALMAS_Cob.dwg` (0,77 MB em disco)
rendendo **9,1 milhões de pontos, 1,36 GB de RAM e 175 s**. Se uma parte grande disso vier de poucos
registros densos, um único deles pode somar milhões de pontos antes da próxima conferência — e aí o
teto não protege nem a memória nem o relógio, que é a família do D57 e do D76.

**Não está medido quantos pontos o maior registro do acervo rende** — é isso que decide se o risco é
teórico ou presente. Antes de mexer, medir; o conserto provável é conferir o teto dentro de
`_colher_polilinha` a cada N vértices, com N grande o bastante para não pesar no laço quente.

Enquanto isso, o orçamento de conversão (`limites.orcamento_de_conversao`) segue como rede: o estouro
vira `RecursoExcedido` com motivo, não morte do worker.

### D89 — os tetos de `snap_pontos` foram fixados sobre medição contaminada · 🟠 aberto 15/08/2026

`payment/planos.py §5.7` traz 150k (Essencial), 600k (Profissional) e 2M (Empresarial). Os três saíram
da **primeira** passada de 15/08/2026, que media 11 de 15 arquivos e contava geometria fora da folha —
publicou mediana 65 mil e cauda 473 mil.

A passada corrigida ([custo-snap.md](medicoes/custo-snap.md)) mede 13 de 15 e dá **mediana 98 mil e
cauda 9,4 milhões**. Ou seja: a mediana subiu 50% e a cauda, vinte vezes. Os degraus continuam
funcionando — o teto corta e a tela declara "snap parcial" —, mas a fronteira comercial foi desenhada
sobre um acervo que não é o real, e o Essencial em 150 mil agora fica **abaixo** da prancha mediana.

Decisão do dono, com o número novo na mão. Não trava nada hoje.

## 🟡 Médias

### D113 — a plataforma não tem documentação de produção · 🟡 aberto 21/08/2026

Decisão do dono (21/08/2026): **tem que ter documentação de produção**. Hoje não há — e a lacuna não
é de conteúdo espalhado, é de destinatário: **nenhum documento fala com quem vai operar o sistema no
ar**. O que existe cobre outros públicos e nenhum deles é esse:

| Documento | Para quem | Por que não serve |
| --- | --- | --- |
| `comandos.md` | o dono, na própria máquina | guia de bancada — Docker Desktop, dev × staging, e o caminho da pasta pessoal escrito dentro; não é indexado no `docs/README.md` |
| `desenvolvimento.md` | quem vai desenvolver | subir a infra local e rodar a suíte |
| plantas (`modulos/`, `arquitetura*`) | quem vai mexer no código | descrevem **desenho**, sem passo a passo e sem status, por regra |
| `deploy/README.md` | quem opera a máquina | compose, imagem, variável de ambiente — não o *uso* da plataforma |

**O caso que expôs isso** foi a importação da base-mãe (ORC.9c). O procedimento só existe em dois
lugares: a mensagem que o comando devolve quando recusa, e o
[README ao lado do arquivo](../backend/moduloorcamento/dados/classes/README.md) que o superuser
edita. Instrução no ponto de uso é bom desenho e deve continuar — mas ela só aparece **depois** de a
pessoa já ter tentado, e não cobre o que não tem comando associado.

**Por que importa mais aqui do que na média dos produtos:** a base-mãe é global e read-only, só o
superuser a importa, e o que ele importa **todos os tenants enxergam**. Classe traduzida errado é
preço errado para a plataforma inteira de uma vez — e essa é exatamente a operação sem documentação
prévia. O mesmo vale para o que é decisão do dono e não tem tela: teto e preço em
[`payment/planos.py`](../payment/planos.py), quota, publicação de plano.

**Não trava nada hoje** — o sistema não está no ar. Fica aberto porque **vira bloqueio na virada**:
no dia em que a primeira SINAPI de verdade for carregada, quem a carrega precisa saber o que fazer
antes de rodar, não ao ler o erro. Escopo, formato e destinatário (o dono opera? um cliente opera?
há suporte no meio?) são decisão do dono, e é ela que falta para começar.

### D86 — os preços dos pacotes de snap são chute de engenharia · 🟡 aberto 15/08/2026

`pacote_snap_200k`, `_500k` e `_1m` entraram em [payment/addons.py](../payment/addons.py) com R$ 39,
79 e 139. Os **tetos** são medidos ([custo-snap.md](medicoes/custo-snap.md)); os **preços** não —
foram postos para o mecanismo ficar completo e testável de ponta a ponta.

Pela regra de 08/08/2026 o valor comercial é do dono, e este ficou pendente. Não trava nada: o teto
por plano já funciona e o add-on só entra quando alguém o contrata no IAM. Fica aberto porque um
preço inventado que ninguém revisou é exatamente o tipo de número que vira tabela de preços por
inércia.

### D80 — `remedir_dwg.sh` morre no fim quando o acervo perdeu um arquivo do corpus · 🟡 aberto

Achado ao rodar a passada de custo de 12/08/2026. O laço usa `TOTAL="$(wc -l < "$LISTA")"` — 160 —,
mas o comando **descarta** o arquivo da lista que não está mais na pasta e mede 159. A última janela
(`--pular 159 --limite 1`) fica vazia, o comando sai com `CommandError: Nenhum arquivo .dwg
encontrado.` e o `set -e` mata o script **antes do `--consolidar`**. Os parciais estão todos gravados,
então nada se perde — mas a passada termina sem relatório, e a consolidação tem de ser refeita à mão.

**Correção:** contar o corpus **efetivo** (o que o comando mediu) em vez das linhas da lista, ou
tolerar janela vazia como fim normal. É decisão de instrumento, não de engenharia de produto: mexer no
que conta a cobertura é o que o `--consolidar` existe para conferir.

### D41 — As amostras que provaram os 4 motores estão fora do repositório · 🟡 aberto

`backend/media/amostras_prancheta/` está sob `media/`, que o [.gitignore](../.gitignore) exclui
inteiro (linha 115). Foram elas que provaram os quatro motores em 31/07 — e junto com elas está
ignorado o `gerar_amostras.py`, o script que as produz. Em clone limpo, nada disso existe: o
instrumento da prova não é versionado.

**Contornado no PRA.8**, não resolvido: o E2E carrega as próprias amostras em
[amostras_pra8.py](../testes/e2e/amostras_pra8.py) — PDF, DXF e IFC escritos à mão em texto (que
de quebra documentam o que cada motor precisa receber) e o DWG comprimido em base64, porque é binário
e o `dxf2dwg` que o escreveria vive só no *build stage*.

**Para fechar:** mover `gerar_amostras.py` para um caminho versionado (o candidato natural é um
management command, ao lado do `medir_cobertura_dwg`), de modo que a origem das amostras volte a ser
código revisável em vez de um arquivo que existe na máquina de quem o rodou.

### D50 — As 4 regressões do S8 não rodam onde o sistema está configurado como em produção · 🟡 aberto

Apurado em 02/08/2026 ao rodar a suíte completa junto do **D46**: `manage.py test` no container `erp`
dá **901 testes com 4 erros**, todos em `nucleo/test_s8_jwt_throttle.py::S8IssuerAudienceTests`, e
todos com a mesma causa — `jwt.exceptions.InvalidKeyError`. Nada a ver com a fatia; o defeito é do
**arranjo de chaves**, e é anterior.

O teste assina o próprio token com `settings.SIMPLE_JWT["SIGNING_KEY"]`. No container o backend é
**resource server**: tem `JWT_PUBLIC_KEY_PATH` e **não tem** privada, então `ALGORITHM` é `RS256` e
`SIGNING_KEY` é **string vazia** — assinar é impossível, por desenho. No CI a suíte roda **sem**
`JWT_PUBLIC_KEY_PATH` ([ci.yml](../.github/workflows/ci.yml) — a chave efêmera só existe no passo do
`check --deploy`), cai no ramo HS256 do **S3** e assina com o `JWT_SECRET`. Daí o teste passar lá e
errar aqui.

**Por que isso importa mais do que parece:** são as regressões que provam o **S8** (`iss`/`aud`
obrigatórios), e elas só exercitam o backend na configuração que **não** é a de produção. A
configuração que é — RS256, sem privada — é exatamente onde elas não rodam. Um erro no caminho RS256
passaria pelo gate.

**Correção sugerida:** gerar um par RSA efêmero no `setUp` do teste e assinar com a privada dele
(a pública já vira `VERIFYING_KEY` por `override_settings`), tornando-o independente de como o
ambiente está configurado. Alternativa mais fraca: `skipUnless` que declare o pulo — resolve o
vermelho, não a lacuna de cobertura.

### D54 — Marcação e medição anteriores à PRA.1c ficam sem folha · 🟡 aberto

A âncora de uma marcação é normalizada pela largura da folha em que foi fincada. Quando uma revisão
que era **uma** folha vira **várias**, o espaço de coordenadas da folha antiga deixa de existir, e a
`Marcacao.desenho` daquelas linhas fica nula (`SET_NULL` de propósito — a marcação sobrevive, é o
apontamento do canteiro).

O efeito é limitado e conhecido: elas continuam na conversa, exportam em BCF e podem ser resolvidas;
o que não têm é **pino sobre o desenho**. A tela diz isso em vez de fingir um lugar.

**Não foi remapeado automaticamente, e é decisão.** Dava para converter a coordenada antiga em
coordenada de desenho, achar o aglomerado que a contém e reprojetá-la — mas isso é a plataforma
movendo o dedo de quem apontou, com base numa aritmética que ninguém conferiu, num campo cujo produto
é dizer *onde*. Errar por alguns centímetros é pior que não ter pino, porque o pino errado é
acreditado.

**O alcance real é pequeno:** só atinge revisão que (a) já tinha marcação com âncora e (b) foi
reconvertida em mais de uma folha. Revisão de folha única não é tocada — o backfill da
[migration 0006](../backend/moduloprancheta/migrations/0006_pra1c_desenho_por_folha.py) pendura tudo
no desenho #1 e nada se move.

**Se virar incômodo**, o caminho é oferecer o remapeamento como **ação de quem governa o acervo**
(`documento.edit`), mostrando antes e depois — decisão de gente, não migração silenciosa.

## 🟡 Médias — herdadas dos laudos v01/v02

| ID  | Achado → correção                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | Status                                                             |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| A5  | `CobrancaCliente` duplica `ContaReceber`+`Boleto` → consolidar repetindo o playbook da `Fatura`. **Levantado 25/07/2026:** confirmado que **nada escreve** em `CobrancaCliente` (nenhum service, task, seed ou signal — só o CRUD exposto em `/api/erp/cobrancas-cliente/`): a tabela está vazia e a cadeia viva é `ContaReceber`→`Boleto`. A única capacidade que ela tinha a mais — amarrar a parcela ao **contrato/unidade** — passou a existir na `ContaReceber` (FKs `cliente_empreendimento`/`contrato`, migration `moduloerp/0013`), então a consolidação virou basicamente **remover** o modelo e a rota.                                                                                                                                                                                                                                                                                  | 🔴 aberto                                                          |
| A7  | N+1 na galeria de IA e no CRM; busca de telefone O(N) em Python →`select_related`/`prefetch_related` + paginação + query no banco *(v01-B9)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | 🔴 aberto                                                          |
| A8  | Acoplamento duro ao Redis (`delete_pattern` do django-redis; sem `IGNORE_EXCEPTIONS`) → cache tolerante a queda. **Parcial 19/07:** `IGNORE_EXCEPTIONS: True` no backend e na IAM — virou obrigatório com o S8, que faz o throttle consultar a cache em TODA requisição (sem isso, Redis fora deixaria de ser lentidão e passaria a ser API inteira fora do ar). **Falta** o `delete_pattern`, que segue amarrando o código ao django-redis.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | 🟠 parcial 19/07/2026                                              |
| A14 | **Bases sem leitor: SICRO, SEINFRA e SEDOP** *(reescrito na ORC.8, 21/08/2026)* — a ORC.8 fechou o A13 e trocou o que falta aqui. `Fonte` aceita as seis desde o ORC.0 e o importador manual é genérico, mas o motor de carga automática lê **um** formato: o arquivo largo da Caixa (27 UFs em colunas). `carga.fontes_conhecidas()` declara isso, a tela diz na cara (*"o motor ainda não lê o formato desta fonte"*) e o agendamento se recusa a tentar — nada finge funcionar. Para cada base nova é preciso um leitor do formato dela, e aí ela entra no botão; enquanto não houver, o caminho continua sendo o comando por publicação. | 🟠 aberto |
| F13 | **O `Modal` do Orçamento reimplementa o modo `alto` em vez de usar o do `malha`** *(17/08/2026)* — [frontend.md §2.2](frontend.md) descreve o modo `alto` do `Modal` compartilhado para "diálogo cujo miolo é uma lista": cartão em coluna flex, cabeçalho e rodapé presos, miolo com `flex: 1`. O kit local do Orçamento (`modules/orcamento/ui.tsx`) **não tem esse modo**, então o modal de inserir item chegou à mesma altura por conta própria (`height: min(62vh, 660px)` na linha da lista) — funciona e respeita a regra de não usar pixel fixo, mas é a terceira implementação do mesmo comportamento. É um caso concreto do **F12** (quatro kits de UI paralelos), e o remédio é o mesmo: migrar para `components/malha/`. Enquanto não migrar, mexer no modo `alto` compartilhado não conserta este modal. | 🔴 aberto |
| A16 | **A adoção nunca remove componente que a fonte aposentou** *(17/08/2026)* — `services._adotar_componentes` e `bancos._adotar_componentes` usam só `update_or_create`: quando a SINAPI tira um insumo de uma composição, o `ComponenteComposicao` correspondente **fica para sempre** no catálogo do tenant, e a composição adotada passa a ter um item a mais que a oficial. É o irmão do D99 — lá o defeito era no preço da planilha, aqui é na receita do catálogo. **Não corrigido de propósito:** apagar componente é mexer em dado do cliente, e o tenant pode ter ajustado o coeficiente à mão; sem procedência por componente não dá para distinguir "veio da SINAPI e sumiu" de "o cliente acrescentou". → decidir com o dono entre (a) remover na re-adoção e relatar quantos, ou (b) marcar como órfão e deixar a decisão na tela; (b) exige campo novo, (a) não. | 🔴 aberto |
| A15 | **`--dry-run` do importador grava a publicação** *(17/08/2026)* — `importar_base_referencial` diz "nada foi gravado", mas o `BaseReferencial.objects.get_or_create` roda **antes** do desvio do `--dry-run`, sem transação em volta. Quem só quer conferir um arquivo (o uso que o próprio `help` do comando sugere) deixa para trás uma publicação **vazia**, que já aparece no seletor de base pela `bases-resumo` com 0 insumos e 0 composições — dado falso numa tela de escolha de data-base. Achado ao carregar a SINAPI BA 10/2024, cuja publicação nasceu de um `--dry-run` que falhou no sintético (D98). → criar a publicação só depois do desvio, ou envolver o `handle` em `transaction.atomic` com rollback quando `seco`. | 🔴 aberto |
| A9  | `except Exception → str(e)` no corpo do 500 vaza detalhes internos → mensagem genérica + traceback só no log *(v01-B7)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | 🔴 aberto                                                          |
| F3  | Acessibilidade: ordenação/linhas de tabela sem teclado,`Sheet` sem focus trap, hover via JS → handlers de teclado + focus trap + CSS *(v01-F3)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | 🔴 aberto                                                          |
| F9  | **Breadcrumb da topbar não conhece os módulos novos** — `SEGMENT_LABELS` em [AppTopbar.tsx](../frontend/src/components/layout/AppTopbar.tsx) não tem `sil`, `orcamento`, `orcar`, `encargos`, `controlar`, `cronograma`, `bases`, `incorporacao` nem `notas-fiscais`: nessas telas a trilha mostra o **slug cru** (`orcamento › orcar`), quebrando a promessa de "toda tela declara seu endereço" ([frontend.md §3.3](frontend.md)). O mapa é uma lista manual que ninguém atualiza ao criar rota. → completar os rótulos e, de preferência, derivá-los do catálogo de páginas de cada módulo (o Orçamento já tem o seu em `modules/orcamento/paginas.ts`) em vez de manter uma segunda lista. **Piorou na ORC.9 (21/08/2026):** o Orçar passou a ter três níveis
de rota (`orcar` › `obra/{id}` › `orcamento/{id}`), então a trilha da topbar agora mostra também
`obra` e o **id cru** no meio do caminho. A página desenha a própria trilha (obra e versão pelo nome),
o que resolve na tela — mas deixa as duas trilhas contando histórias diferentes na mesma janela.                                                                                                                                                                                                                           | 🔴 aberto                                                          |
| F10 | **`--topbar-h` não existe** — [PaginaShell.tsx](../frontend/src/modules/orcamento/components/PaginaShell.tsx) dimensiona as páginas do Orçamento com `calc(100vh - var(--topbar-h, 56px))`, mas **nenhum arquivo declara** essa variável (nem `index.css`, nem o `AppTopbar`, cuja altura real vem de `padding: 12px` + conteúdo). Sempre cai no fallback, então a grade com `semRolagem` (Orçar) fica com altura errada por alguns pixels — rolagem dupla ou faixa cortada. → declarar `--topbar-h` no `AppShell`/`index.css` a partir da altura real da topbar (ou medir por `ResizeObserver`), já que outros módulos vão precisar do mesmo cálculo.                                                                                                                                                                                                                                                            | 🔴 aberto                                                          |
| F11 | **Duas listas de módulos que divergem** — o farol da sidebar (`NAV_SECTIONS` em [AppSidebar.tsx](../frontend/src/components/layout/AppSidebar.tsx)) e o catálogo do hub (`CATALOGO` em [pages/app/home/catalogo.ts](../frontend/src/pages/app/home/catalogo.ts)) descrevem o mesmo conjunto com vocabulários diferentes (`implemented: boolean` × `situacao: pronto/backend/planejado`) e **já discordam**: Drone é `implemented: false` num e `situacao: 'backend'` no outro; Maps/DMS/Prancheta/PDCA/terrenos/viabilidade estão no hub e não na sidebar. Como os dois são "o farol da edição" ([frontend.md §3.2](frontend.md)), o usuário vê dois inventários da mesma casa. → uma fonte só (o `CATALOGO`, que é mais rico), com a sidebar derivando dela o seu recorte — mesmo remédio do `paginas.ts` do Orçamento, que já resolveu isso dentro do módulo.                                                     | 🔴 aberto                                                          |
| F12 | **A convenção de estilo escrita não é a praticada** — [frontend-convencoes.md](frontend-convencoes.md) manda "Tailwind classes inline; `cn()` para condicionais; sem arquivos `.css` por componente", mas **todo** o código nascido na Malha (sidebar, topbar, hub da home, SCM, SIL, Orçamento) é escrito com objetos `style={{}}` inline, sem Tailwind e sem `cn()`. Some-se a isso **quatro kits de UI paralelos** (`components/malha/` + kit local do SCM + `sil/ui.tsx` + `orcamento/ui.tsx`, cada um com seu `Card`/`Pill`/`Btn`/`Modal`) — a dívida dos kits já está declarada em [frontend.md §2](frontend.md), a da convenção não. Quem ler o documento antes de escrever a próxima tela vai escrever no padrão errado. → decidir o padrão de fato (inline `style` + tokens parece ser o vencedor) e reescrever a regra; e datar a migração dos kits locais para `components/malha/`. | 🔴 aberto                                                          |

## 🟢 Baixas

| ID  | Achado → correção                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Status                  |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------- |
| A10 | Higiene do repo:`nul`, `terminal*.txt`, scripts soltos na raiz → remover + `.gitignore` *(v01-G1)*. **Parcial 19/07:** o que tinha valor foi movido em vez de apagado — `terminal.txt` (guia de comandos atualizado) → [docs/comandos.md](comandos.md), `test_browser.py` → `testes/e2e/browser_smoke_test.py`, `serve_spa.py` → `infra/`. Docker e env saíram da raiz para [deploy/](../deploy/README.md). `.gitignore` ganhou `_verify_*.txt` e — achado no caminho — teve os padrões de virtualenv **ancorados** (`/env/` em vez de `env/`): sem a âncora, `env/` casava qualquer diretório com esse nome e escondia o `deploy/env/` inteiro, incluindo os modelos que precisam ser versionados. **Falta (exige decisão/ação do dono do repo):** (a) apagar 4 arquivos mortos na raiz — `nul` (um 502 do nginx capturado por engano), `_verify_testes.txt` (resíduo do bridge PHP removido) e `package.json`/`package-lock.json` (vestígio do monorepo Node; **nada os referencia** — o CI usa `frontend/package-lock.json`); (b) decidir o `requirements.txt` da RAIZ — não é usado por CI nem por Dockerfile algum (esses usam `backend/` e `iam/`), mas é plausível que seja o manifesto do `.venv` que roda as duas suítes localmente, e por isso **não foi tocado**. Se for isso, vale torná-lo explícito (`requirements-dev.txt`, somando backend+iam, hoje desatualizado: falta `django-redis`); se não, pode sair.                                                                                                                             | 🟠 parcial 19/07/2026   |
| A12 | Modelagem: validador CPF/CNPJ sem dígito verificador no backend;`Boleto.VENCIDO` nunca setado; rota duplicada `/api/api/`; duplicata no fallback de tipos de IA *(v01-B8)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | 🔴 aberto               |
| F6  | Sem`ErrorBoundary` nem padrão de loading/erro/vazio; i18n ausente → padronizar componentes de estado                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | 🔴 aberto               |
| D77 | **`X-Content-Type-Options` sai duplicado em toda resposta do gateway** — o nginx o adiciona (`add_header … always`, Fase 5) e o Django também (`SecurityMiddleware`), então o cliente recebe `nosniff, nosniff`. Inofensivo hoje (mesmo valor, e o browser honra), mas é um header de segurança que ninguém sabe de onde vem: se um dia as duas fontes divergirem, uma delas fica invisível. Achado ao escrever o E2E do D70 em 09/08/2026, e ele explica por que nenhum E2E anterior o viu — todos leem headers com `dict(resp.headers)`, que descarta a duplicata em silêncio. → `proxy_hide_header` no gateway **ou** deixar o header por conta de uma fonte só, e ajustar as asserções que hoje comparam por igualdade. | 🔴 aberto               |
