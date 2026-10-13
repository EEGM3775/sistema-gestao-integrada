# Maps — dimensão espacial da plataforma (`modulomaps`)

> **Planta do módulo.** Descreve o **desenho e o contrato de API** (sem status/datas — o status vive
> no [roadmap](../roadmap.md)). Destrava o placeholder `modulomaps` e cria a **coordenada** que o
> sistema nunca teve: hoje obra, empreendimento, fornecedor e almoxarifado têm só `endereco` em
> texto, e o único acervo geográfico (ortofoto, marcador, medição) está preso dentro do
> [drone](../arquitetura.md).

## 1. O que é (e por que é fundação com camadas vendáveis)

Duas coisas que os grandes separam, e que aqui também se separam:

- **Onde as coisas ficam** — a *dimensão espacial* de entidades que já existem. É atributo de
  cadastro, no mesmo nível de "quanto custa" ou "de quem é". Ninguém vende isso à parte: SAP põe geo
  no *Business Partner Address*, Oracle no `HZ_LOCATIONS`. **É fundação.**
- **O que se faz com espaço** — acervo de ortofotos, plano de voo, roteirização, geofence, camadas
  públicas, banco de terrenos. Cada uma é uma capacidade com custo próprio (storage raster, motor de
  rota, geocodificação fina). **É vendável.**

Por isso o módulo tem **duas metades**: a fundação `Local` sem `RequireModule` (como
[catalogo](catalogo.md) e [funcoesimpexp](funcoesimpexp.md)) e as camadas atrás do entitlement
`maps`. Sem essa divisão, um tenant que não assina Maps ficaria com [SIL](modulosil.md) e
[SCM](moduloscm.md) sem dimensão espacial — o almoxarifado não saberia onde fica, e a régua de
"integração visível entre módulos" quebraria para quem não pagou.

O módulo **não é um visualizador de mapa**. O visualizador maduro já existe no drone (Leaflet +
GeoTIFF + proj4, em `shared/components/map-viewer`). O que não existe é a **coordenada no banco** e o
**vocabulário compartilhado** que faz obra, suprimento, voo e fornecedor caberem no mesmo mapa.

## 2. Acesso

| Metade | Gate | Permissões |
|---|---|---|
| **Fundação** — `Local`, geocodificação | **sem `RequireModule`** | `mapa.local.{view,edit}` |
| **Camadas** — feições, ortofotos, voo, rotas, cercas | `RequireModule("maps")` | `mapa.feicao.{view,edit}` · `mapa.ortofoto.{view,edit}` · `mapa.plano_voo.{view,edit}` · `mapa.rota.{view,edit}` · `mapa.geofence.{view,edit}` · `mapa.camada_externa.view` (MAP.7) |

No catálogo da IAM as duas metades aparecem em módulos diferentes: `mapa.local.*` fica em **`base`**
(como `cadastro.item.*`) e o resto em **`maps`**. Não é detalhe de arrumação — é o que impede a
permissão de fundação de ser podada pela trava anti-escalada quando o tenant não assina Maps.

Todos os modelos herdam `TenantScopedModel` (RLS fail-closed). Persona nova **`topografo`**
(feições, voo, ortofoto); `almoxarife` ganha `mapa.rota.*`; `engenharia` e `gestor_obra` ganham
`mapa.local.edit` e `mapa.feicao.*`.

> Permissão e persona novas exigem **rebuild da imagem `sgi-iam` + re-seed** — o catálogo
> ([iam/identity/catalog.py](../../iam/identity/catalog.py)) viaja na imagem, não no código montado.

## 3. Fundação espacial — PostGIS

Geometria de verdade, não dois `DecimalField`. A decisão é de sequência, a mesma que a Fase 9
registrou (fundação antes da feature, para não re-migrar): rota, polígono de voo, geofence e
zoneamento são **predicados espaciais**, e nenhum deles se resolve com latitude e longitude soltas.

O que muda no stack:

| Onde | Mudança |
|---|---|
| Banco (compose e CI) | `postgres:16` → **`postgis/postgis:16-3.4`** (`base.yml` e [ci.yml](../../.github/workflows/ci.yml)) |
| Imagem do backend | `binutils` + `gdal-bin` no `Dockerfile` — `gdal-bin` puxa GEOS e PROJ como dependência, e **nomes versionados de lib não se fixam** (`libgdal32`/`libproj25` mudam a cada release do Debian) |
| Django | `django.contrib.gis` em `INSTALLED_APPS`; engine `django.contrib.gis.db.backends.postgis` |
| Extensão | `CREATE EXTENSION postgis` **no `template1`, pelo superuser** — não numa migration |

**Por que a extensão não vem de migration.** `CREATE EXTENSION postgis` exige SUPERUSER (a extensão
não é *trusted*), e o backend roda como `erp_app`, que é role comum **de propósito** — é disso que
depende a RLS `FORCE` valer. Criar no `template1` resolve os dois casos de uma vez: `erp_db` nasce com
a extensão (é copiado do template) e o `test_erp_db` que o runner cria a cada execução também. Fica em
[infra/postgres/init/](../../infra/postgres/init/) e no passo equivalente do CI.

> **Ambiente já existente:** o volume `pg_data` continua válido (mesma major, só muda o que vem
> instalado), mas o script de init **não reroda** num volume já inicializado. Uma vez, à mão:
>
> ```sh
> docker compose exec postgres psql -U postgres -d template1 -c 'CREATE EXTENSION IF NOT EXISTS postgis;'
> docker compose exec postgres psql -U postgres -d erp_db    -c 'CREATE EXTENSION IF NOT EXISTS postgis;'
> ```

A RLS convive sem ajuste: a política é por coluna `tenant`, indiferente ao tipo geométrico. O índice
espacial é **GiST**, criado por `spatial_index=True` (padrão nos campos geométricos).

**SRID 4326** (WGS84) como sistema de armazenamento único — é o que o GPS, o KML e o GeoJSON falam.
Cálculo métrico (distância, área) usa `geography` ou reprojeção sob demanda; **nunca** se guarda em
UTM/SIRGAS por zona, que quebraria toda obra perto de divisa de fuso.

## 4. Modelos

### 4.1 Fundação

| Modelo | Papel |
|---|---|
| `Local` | **Onde uma entidade fica.** `ponto` (`PointField`), `area` (`PolygonField`, opcional — perímetro do canteiro/terreno), endereço estruturado (`cep`, `logradouro`, `numero`, `bairro`, `cidade`, `uf`, `ibge`), **`precisao`** e **`fonte`** (§5). Vínculo **polimórfico opcional** — `obra`, `empreendimento`, `fornecedor`, `local_estoque`, `unidade` — no mesmo padrão de `moduloscm.CentroCusto` e `modulosil.LocalEstoque`, com `tipo` discriminador |

O vínculo é polimórfico (FKs nuláveis + `tipo`) e não `GenericForeignKey`: preserva integridade
referencial, permite `select_related` e é o padrão que a casa já usa em dois módulos.

### 4.2 Camadas (entitlement `maps`)

| Modelo | Papel |
|---|---|
| `Camada` | Agrupa feições e controla visibilidade/cor/ordem. Uma camada por assunto (progresso da obra, sondagens, interferências, marcos topográficos) |
| `Feicao` | Desenho livre do usuário: `geom` (`GeometryField` — ponto, linha ou polígono), `tipo`, `camada`, `obra` opcional, **`data_referencia`**, `propriedades` (JSON) e anexos. É onde vivem os **pins de acompanhamento de obra** |
| `Ortofoto` | **Acervo raster.** `chunk_uuid` (o task do drone), `bbox` (`PolygonField`), `data_voo`, `gsd_cm`, `crs_origem`, `url_cog`, `obra`. É o índice que permite mostrar o voo no mapa da empresa **sem abrir o drone** |
| `PlanoVoo` | `area` (`PolygonField`), `tipo` (grid · duplo grid · perímetro · orbital/POI · corredor), `altura_m`, `gsd_alvo_cm`, `sobreposicao_frontal_pct`, `sobreposicao_lateral_pct`, `camera`, `obra`. Gera a rota de voo e exporta (§7) |
| `Rota` / `ParadaRota` | Roteirização de suprimento: origem, paradas ordenadas com janela de horário, `linha` (`LineStringField`) devolvida pelo motor, distância e duração estimadas |
| `Geofence` | Cerca de canteiro derivada de `Local.area` — o gancho de ponto por geolocalização e de foto georreferenciada do diário |
| `CamadaExterna` | Camada pública WMS/WFS por tenant (CAR/SICAR, SIGEF, zoneamento municipal, embargos) — URL, tipo, atribuição. Só referência, sem cópia do dado |

## 5. Geocodificação em cascata — a procedência é o produto

Nenhuma fonte que o sistema já usa devolve coordenada: o ViaCEP dá endereço, o IBGE dá município.
A cascata estende [nucleo/geo.py](../../backend/nucleo/geo.py) — que **já declara `maps` como
consumidor** e já devolve `fonte` — com um `geocodificar()` que retorna `(ponto, precisao, fonte)`:

| Ordem | Fonte | Precisão | Custo |
|---|---|---|---|
| 1 | **Pin arrastado à mão** | `exata` | — |
| 2 | EXIF de foto do diário/drone | `exata` | — |
| 3 | Geocodificação por endereço (Nominatim self-host; Google como *add-on*) | `endereco` | infra ou COGS |
| 4 | Centroide de CEP | `cep` | — |
| 5 | Centroide de município (IBGE) | `municipio` | — |

**A regra de ouro: precisão nunca é invisível.** Um pin de centroide de município e um pin arrastado
à mão não podem parecer a mesma coisa na tela — é a mesma exigência de "dados honestos" que fez o
Orçamento declarar `cobertura_pct` e `realizado_cobertura`. Um mapa que mostra a obra no meio da
cidade porque só sabia o município, com a mesma confiança de um ponto de porta, mente.

**O degrau 4 está inerte com o provedor grátis, e isso muda o que se vê na tela.** A BrasilAPI v2
responde `location: {"type": "Point", "coordinates": {}}` — objeto vazio — para os CEPs medidos
(Salvador, Belo Horizonte, Curitiba, São Paulo, Rio), todos servidos pelo `open-cep`:
`coordenada_por_cep` lê `coordinates.longitude/latitude`, não acha e devolve `None`. O código está
correto e degrada como desenhado — o que falta é **dado do provedor**. A consequência é de produto:
na configuração padrão (sem `NOMINATIM_URL`) a cascata tem só **dois degraus vivos**, `exata`
(pin/EXIF) e `municipio` (centroide do IBGE), então todo endereço geocodificado sozinho vira pin no
centro da cidade e a fila `precisao_grosseira` nasce cheia — corretamente, porque a precisão é
declarada, mas com trabalho manual que o cliente não pediu. As saídas, em ordem de custo: **Nominatim
self-host** (§9), que resolve o degrau 3 e torna o 4 dispensável; trocar o provedor de CEP por um com
coordenada de verdade; ou aceitar o pin de município contando com o arrasto à mão. A medida para
decidir é a contagem de `precisao_grosseira` na fila de decisão dos primeiros clientes reais.

## 6. Endpoints (`/api/maps/`)

| Rota | Verbo de domínio |
|---|---|
| `status/` | O que a instalação tem: `provedores` (geocodificação, motor de rota, tiles) e `provedores_publicos` (os ligados no servidor público do OSM) |
| `mapa/` | O mapa da empresa num payload só: pins + resumo por tipo/precisão + **fila de decisão**. Sem entitlement (são `Local`); as camadas pagas só entram se o tenant assina |
| `locais/` | CRUD — `PATCH` com `ponto` vira `exata/manual` (`ponto: null` volta a "sem coordenada"); `DELETE` de local em rota dá **409**; `{id}/geocodificar/[?forcar=1]` (cascata); `proximos/?de=&raio_km=&tipo=` |
| `camadas/` · `feicoes/` | CRUD; `feicoes/?bbox=&desde=&ate=` (recorte espacial **e temporal**) |
| `ortofotos/` | Índice do acervo; `?bbox=&obra=`; `{id}/tiles/{z}/{x}/{y}/` |
| `planos-voo/` | CRUD — `PATCH` em área/tipo/GSD/sobreposição **apaga o cálculo** (linha, waypoints, altura); **`do-local/`** (cria o plano a partir de um `Local` — perímetro desenhado se houver, círculo de `raio_m` se não, e a resposta declara qual dos dois em `origem_da_area`); `{id}/calcular/` (traçado + altura + memória de cálculo); `{id}/exportar/?formato=kml|plan|litchi|wpml` ||plan\|litchi\|wpml` |
| `rotas/` · `paradas/` | CRUD — a rota aceita **`paradas_locais`** (ids na ordem; no PATCH substitui as paradas e apaga o traçado velho); `{id}/tracar/` (ordem atual); `{id}/otimizar/` (reordena + devolve violações de janela) |
| `geofences/` | CRUD; `gerar/` (do perímetro do `Local` ou de um raio); `conter/?lon=&lat=` |
| `detectar-endereco/` | Texto livre **ou XML de NF-e** → endereços candidatos (§7, item 5) |
| `camadas-externas/` | Catálogo de WMS/WFS do tenant — **MAP.7** |

### 6.1 A unidade imobiliária no mapa

`Local.Tipo.UNIDADE` tem entrada em `services.VINCULOS`, como os outros quatro vínculos, com **uma
dedução que nenhum deles tem**: quando `Unidade.endereco` está vazio, a **frente do lote**
(`confrontante_frente`) é a rua, e é dela que sai o endereço do `Local`. Sem isso o mapa mostrava um
pin "QD 4 · LT 06" sem nenhuma pista de onde aquilo fica.

Os dois serializers (`LocalSerializer` e `LocalResumoSerializer`) trazem `unidade_detalhe` — `null`
fora de `tipo: unidade` —, com áreas, **medidas e confrontações dos quatro lados**, o memorial em uma
frase e a rua da frente. Área não descreve terreno: o que o contrato, a matrícula e o vizinho
reconhecem é quanto mede cada lado e com quem cada lado divide.

**`rua_confere` tem três estados, e o terceiro é o que evita o alarme falso:** `true` (bate), `false`
(diverge) e **`null`** — não há como dizer, porque falta o confrontante ou falta o endereço. Cadastro
incompleto não é cadastro errado, e acusar divergência onde só falta dado ensina a ignorar o aviso. A
comparação é por conteúdo, não literal: tira acento, caixa, pontuação, o tipo do logradouro ("R.",
"Av.") e os artigos — o memorial e o endereço nunca são digitados iguais, e exigir igualdade acusaria
divergência em todo cadastro correto.

A divergência vira item da **fila de decisão** do cockpit (`tipo: "rua_divergente"`), que abre a
tabela de locais já filtrada em `tipo=unidade`. A varredura roda em Python — a comparação é tolerante
e SQL faria igualdade literal — e por isso tem teto declarado (`_TETO_VARREDURA_RUA`): guarda-corpo de
laço, **não** limite de produto (§5.6 do `planos.py`).

## 7. Integrações — o "tudo se conecta"

| Com | O que passa a existir |
|---|---|
| [obras](obras.md) · [empreendimentos](empreendimentos.md) | `Local` da obra e do empreendimento; perímetro do canteiro; **mapa da carteira** (obras por cidade/UF já existem estruturadas na `Unidade` e no empreendimento) |
| [fornecedores](fornecedores.md) | `Local` do fornecedor → **"fornecedores num raio de X km da obra"**, que hoje é impossível. Alimenta o mapa comparativo do SCM com **distância**, não só preço e estrela |
| [modulosil](modulosil.md) | `Local` do `LocalEstoque` (central e canteiro); **`Rota`** de transferência entre almoxarifados e de entrega ao canteiro; geofence do canteiro no recebimento |
| [moduloscm](moduloscm.md) | Distância entrega→canteiro como critério de adjudicação; prazo de entrega confrontado com a rota |
| **drone** (`funcoesODM`) | `Ortofoto` indexa o acervo por `bbox` e data → a ortofoto vira **camada do mapa da empresa**; `PlanoVoo` nasce do polígono da obra e volta como missão executável; `Feicao` com `data_referencia` permite o **antes/depois** do mesmo pin em voos de datas diferentes |
| [modulodiario](modulodiario.md) | Foto georreferenciada (EXIF) vira `Feicao` na data do diário |
| [modulocalendar](modulocalendar.md) | Precedente direto: módulo de plataforma que serve a todos sem ser função de ERP. O `Local` também resolve a localidade de feriado — e é dele que sai o **código IBGE** que o [dia útil bancário](modulocalendar.md) usa para empurrar o vencimento do boleto pelo feriado **municipal** do empreendimento ([clientes.md](clientes.md)) |
| [funcoesimpexp](funcoesimpexp.md) | **Item 5**: endereço detectado em texto entra pela **conferência linha a linha** do motor (nova/duplicada/inválida, nada grava antes da decisão) em vez de virar pin direto. O `IE.n` do Maps |

### Detecção de endereço em texto (item 5) — a distinção que importa

No **XML da NF-e o endereço já vem estruturado** (`xLgr`/`nro`/`xBairro`/`cMun`/`UF`/`CEP`): ali é
*parsing*, e o ganho é ligar fornecedor a coordenada de graça. O problema difícil é **texto livre**
(contrato, e-mail, mensagem de WhatsApp), e aí a ordem de esforço é: regex ancorado em CEP (metade já
está em `parse_endereco`) → **a LLM local que já está na stack** (`LLM_VISION_URL`, do
[funcoesia](funcoesia.md)) para extração estruturada → NER dedicada só se as duas não bastarem.

## 8. Frontend

Componente **`<Mapa>` no kit compartilhado** [components/malha/](../../frontend/src/components/malha/) —
não um quinto kit de módulo (a dívida dos kits paralelos já está declarada em
[frontend.md §2](../frontend.md)).

**MapLibre GL** no React, e não Leaflet, por dois motivos concretos: *vector tiles* aguentam milhares
de feições sem derrubar o browser (o mapa da empresa é isso), e o **estilo é JSON** — ou seja, claro e
escuro da Malha saem do mesmo mecanismo de tema, sem trocar de provedor de tile. O Leaflet **fica** no
drone; são dois contextos, não uma migração.

Página no padrão da régua ([frontend.md §1.6](../frontend.md)): **uma fileira de abas** — Mapa da
empresa · Vizinhança · Planos de voo · Acervo de voos · Rotas —, com fila de decisão real — *obras sem
coordenada*, *pins no centro da cidade*, *ortofoto vencida* (último voo há N dias), *plano de voo sem
autorização*. Pin com **precisão visível** (§5).

O corte fundação × produto **é o do backend, mas não vira dois níveis de navegação**: as abas do
módulo pago (voos, acervo, rotas) ganham um cadeado sem o entitlement e abrem o cartão que explica o
que existe do outro lado — nunca somem ([identidade §3.2](../identidade-visual.md)). Por isso a rota
`/app/maps` **não** fica atrás de `ModuleRoute`: pendurá-la no entitlement daria 403 exatamente na
tela que existe para quem ainda não contratou entender o módulo.

**Mapa da empresa = mapa + painel + camadas.** O mapa e a lista de locais ficam **lado a lado, com a
mesma altura**, e quem rola é a lista (em tela estreita ela desce para baixo do mapa com altura
limitada) — lista e pins obedecem aos mesmos filtros (tipo, precisão, busca). A linha escolhida
enquadra o pin; o pin clicado traz a linha. No local escolhido: **posicionar/mover o pin à mão**
(marcador arrastável ou clique no mapa → `PATCH ponto`, que vira `exata/manual`), rodar a cascata,
excluir ponto avulso; **Novo ponto** cria um `Local` avulso pelo clique. Por cima do mapa ligam e
desligam as **camadas**: planos de voo, rotas, envelopes do acervo e as `Camada` temáticas — é onde
cadastro, voo e entrega se encontram no mesmo enquadramento. A **legenda** usa a mesma tabela de cores
do pin (`mapaCores.ts`): cor = tipo (cada tipo filtra ao clicar), halo = precisão.

**Planos de voo = um mapa com todos os planos**, enquadrado neles, e o mapa como prancheta: o polígono
se **desenha** (clique marca canto, arrasto ajusta, botão direito remove) para criar e para **editar**
a área; salvar recalcula. Criar a partir de um `Local` continua (`do-local/`). **Rotas** nascem na
tela (origem + paradas na ordem marcada) e são traçadas na hora; traçado estimado aparece
**tracejado**, para não se passar por rua. As abas dizem o que a instalação não tem (`status/`):
sem geocodificador ou motor de rota, o aviso nomeia a variável que liga; no servidor público do OSM,
avisa que é de teste.

**`<Mapa>`**: os fundos (Esri cinza claro/escuro + rótulos, Esri satélite + rótulos de ruas e lugares;
os cinzas com `maxzoom: 16`, acima disso a Esri não tem imagem e o MapLibre amplia) vivem todos no
estilo e trocar é mudar **visibilidade** — nunca `setStyle`, que descartava pins e polígonos. O worker
do MapLibre 6 é empacotado explicitamente (`?worker&url` + `setWorkerUrl`). Modos de edição: `edicao`
(pin arrastável) e `desenho` (polígono com vértices arrastáveis); camadas que saem da lista saem do
mapa; sem pins, o enquadramento é pelas camadas.

**A precisão é desenhada, não escrita:** cada pin ganha um halo cujo raio cresce com a incerteza —
ponto firme é porta, mancha larga é "algum lugar nesta cidade". Legenda existe, mas a forma já conta.

**Maps e Calendário moram na topbar, não na sidebar** (26/07/2026). Nenhum dos dois é um *lugar* do
ciclo: são **lentes transversais** sobre o que já existe (o território de obra/fornecedor/almoxarifado;
a agenda de todos os módulos). Ficam ao lado do sino de notificações, que é a família do que se
consulta sem sair de onde se está — a sidebar segue sendo o farol dos lugares da edição.

## 9. Provedores e custo

Padrão **grátis/self-host**, com o pago como *knob* em [payment/](../../payment/README.md) — knob que
muda o que o cliente paga não vive no código de engenharia:

| Capacidade | Padrão (incluso) | Add-on |
|---|---|---|
| Basemap | Esri World Imagery · Esri Canvas (cinza claro/escuro) · OpenTopoMap (já em uso no drone, com atribuição) | MapTiler/Mapbox · Carto (passou a exigir chave) |
| Geocodificação | Cascata própria (CEP → centroide IBGE) | Nominatim self-host · **Google Geocoding** (precisão de porta) |
| Rota | **OSRM** self-host (traçado + matriz) + **heurística própria** para a ordem (vizinho-mais-próximo + 2-opt) | Google Routes · Valhalla (isócronas) · **OR-Tools** quando entrar frota/capacidade |
| Raster | **COG + range request**; **TiTiler** (Python, sem 4º runtime) | tile server dedicado |

> **Atenção ao tile do OSM público:** a *tile usage policy* restringe uso comercial pesado. O drone
> hoje o lista entre os basemaps; num mapa de SaaS multi-tenant o padrão deve ser Esri, com OSM
> como opção consciente.

**Traçar × ordenar são coisas diferentes, e só a primeira vem de fora.** O traçado é geometria de rua
e exige o OSRM; sem motor configurado, a rota é a reta entre paradas e sai carimbada
`procedencia=estimada` — estimativa que se declara estimativa dá ordem de grandeza da entrega; a que
se passa por rota de rua faz o comprador prometer prazo que não cumpre. Já a **ordem** é combinatória
e roda dentro do backend: o problema desta fase é um veículo, sem capacidade, saindo de origem fixa —
um TSP aberto de dezenas de paradas, onde vizinho-mais-próximo + 2-opt chega ao ótimo ou a fração de
por cento dele. OR-Tools entra quando o problema virar **VRPTW de verdade** (frota, capacidade, janela
dura); antes disso, seriam ~100 MB de dependência nativa na imagem e no CI para resolver um problema
que não existe ainda. A **janela de horário não é violada em silêncio**: o otimizador devolve, junto
da ordem, as violações que ela produziu — quem remaneja é quem conhece o canteiro.

**Configuração** (`.env` da raiz → `deploy/compose/base.yml` repassa ao `erp` e ao `worker`):
`NOMINATIM_URL` (+ `NOMINATIM_API_KEY` para provedor compatível com chave, como o LocationIQ — vai
como `?key=` e nunca aparece em log), `NOMINATIM_USER_AGENT`, `OSRM_URL`, `TITILER_URL`. O exemplo de
**dev** aponta para os servidores públicos do OSM (Nominatim e OSRM de demonstração) — servem para
testar, e a tela avisa; staging e produção ficam vazios até haver self-host ou chave.

Quotas de COGS (`geocodificacoes_mes`, `rotas_mes`, `storage_raster_gb`) nascem **declaradas e
inertes**, como as demais — medem e cobram, não travam.

## 10. Seams (prontos, inertes)

- **Banco de terrenos e viabilidade** ([expansão §7](../expansão/03-mapa-de-modulos.md)) — `Local.area`
  + `CamadaExterna` (CAR/SIGEF/zoneamento) já são o substrato; o módulo de terrenos entra por cima.
- **Marketplace de terrenos** ([expansão §4](../expansão/04-rede-e-marketplaces.md)) — `ref_externa` /
  `origem_tenant` nas feições, mesmo padrão inerte do SCM.
- **Ponto de obra por geofence** ([expansão §9](../expansão/03-mapa-de-modulos.md)) — `Geofence` existe;
  o consumo é do RH.
- **BIM/3D** — o Potree do drone já entrega nuvem de pontos; `Feicao` guarda `Z` quando houver.
- **Benchmark espacial anônimo** ([expansão E4](../expansão/06-dados-ia-automacao.md)) — custo por m²
  por região exige o `Local` com precisão declarada para o número ser comparável.

## 11. Sub-fases

| Fase | Escopo | Requisito atendido |
|---|---|---|
| **MAP.0** | PostGIS no stack (compose, CI, Dockerfile, extensão), `Local`, cascata de geocodificação em `nucleo/geo.py`, permissões e persona na IAM, backfill dos endereços existentes. Sem tela | fundação |
| **MAP.1** | `<Mapa>` no kit Malha + mapa da empresa (obras, empreendimentos, almoxarifados, fornecedores) com precisão visível | **1** |
| **MAP.2** | `Rota`/`ParadaRota` (OSRM + OR-Tools), raio de fornecedor no SCM, `Geofence` de canteiro | **2** |
| **MAP.3** | `Ortofoto` (índice + bbox + COG/TiTiler) sobreposta ao mapa; `Camada`/`Feicao` com `data_referencia` para o antes/depois | **3** (ortofoto) · **4** |
| **MAP.4** | `PlanoVoo` (grid/duplo/perímetro/orbital/corredor, GSD→altura) + exportação KML · MAVLink `.plan` · Litchi CSV · DJI WPML | **3** (voo) |
| **MAP.5** | Detecção de endereço em texto → conferência pelo `funcoesimpexp`; endereço do XML da NF-e georreferenciando fornecedor | **5** |
| **MAP.6** | E2E vivo pelo gateway ([map6_maps_test.py](../../testes/e2e/map6_maps_test.py)) — as duas metades do gate com token real, cascata contra a rede, seam do SCM, tile gateado, R1 do motor | fecha 1–5 |
| **MAP.7** | `CamadaExterna` (CAR/SICAR, SIGEF, IBGE, zoneamento) + seam do banco de terrenos | **6** / expansão §7 |

## 12. Decisões registradas

- **PostGIS/GeoDjango**, não lat/long solto — rota, polígono e zoneamento são predicados espaciais.
- **Fundação + camadas vendáveis** — georreferenciar entidade é cadastro; acervo, voo e rota são produto.
- **SRID 4326** único no armazenamento; métrica por reprojeção sob demanda.
- **Grátis/self-host por padrão**, pago como knob em `payment/`.
- **MapLibre no React, Leaflet fica no drone** — dois contextos, não uma migração.
- **Precisão e procedência sempre visíveis** — pin de centroide não se parece com pin de porta.
- **A extensão do banco vem do `template1`, pelo superuser** (§3) — não de migration, porque o role
  de aplicação é comum de propósito.
- **Ordem de rota por heurística própria; OR-Tools só com frota/capacidade** (§9). O sinal concreto de
  que chegou a hora de trocar é o modelo, não a intuição: a `Rota` ganhar veículo/motorista, ou a
  `carga_kg` da `ParadaRota` deixar de ser registro e passar a valer como restrição — aí o problema
  virou VRPTW e troca de pares não basta mais.
- **O tile da ortofoto é servido pelo backend, com gate** — a alternativa (mandar o browser no COG do
  drone) ampliaria para todo o acervo histórico a superfície pública do `/chunks/*/assets/*`, que é
  `permitAll` por desenho do visualizador (**S10**). Custa um salto de rede e vale.
- **O `bbox` da ortofoto é recebido, não deduzido** — o `Project` do drone não tem coordenada; o
  backend aceita o envelope na criação e o `chunk_uuid` amarra ao voo. Extrair do GeoTIFF ao concluir
  o processamento é otimização do repo do drone, não pré-requisito deste módulo.
- **A `Rota` desta fase é planejamento** (o que vai sair), não execução — rastro de motorista exige
  app de campo, que é a [expansão §5](../expansão/05-portais-e-apps.md).
- **SARPAS/DECEA é campo de controle, não integração** — o órgão não expõe API, e prometer integração
  seria vender o que não existe. O que o sistema faz é não deixar esquecer: plano sem autorização
  válida vira item da fila de decisão.

## 13. Questões em aberto (decidir antes da sub-fase relevante)

- **MAP.5** — a escalada da extração de endereço em texto livre para em qual degrau? Hoje há regex
  ancorado no CEP (que valida contra o ViaCEP) e o parsing do XML da NF-e — que não é detecção: ali o
  endereço já vem estruturado e conferido pela SEFAZ. A LLM local (§7) só se paga se a conferência
  linha a linha mostrar volume de texto que o regex não alcança — a régua R1 do motor existe
  justamente para a extração poder ser imperfeita. **A medida é a contagem de linhas classificadas
  como inválidas no histórico do motor**, e o gatilho é documento que o regex não alcança por
  natureza: contrato sem CEP, e-mail de fornecedor, mensagem de WhatsApp. Ligar a LLM antes disso é
  acrescentar um caminho que nenhum teste percorre e nenhum usuário pediu.
- **MAP.7** — `CamadaExterna` (CAR/SICAR, SIGEF, zoneamento) fica fora desta leva: é a fronteira com
  o banco de terrenos da [expansão §7](../expansão/03-mapa-de-modulos.md).
