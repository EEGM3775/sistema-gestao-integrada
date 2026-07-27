# Roadmap — status e plano

> **O que está pronto e o que falta** para concluir a plataforma (visão em
> [arquitetura.md](arquitetura.md)). Este documento guarda **só status e plano**; a narrativa datada
> de cada entrega (bugs encontrados, decisões, validações) e os
> achados de revisão ainda abertos em [pendencias.md](pendencias.md). A **ordem importa**: a fundação
> precede a integração — não faz sentido federar um módulo sobre SQLite e sem isolamento de tenant.

## Status das fases

| Fase | Tema                                                                             | Status                                               |
| ---- | -------------------------------------------------------------------------------- | ---------------------------------------------------- |
| 0    | Fundação (banco, IAM, multi-tenancy no backend)                                | ✅                                                   |
| 1    | SSO ponta a ponta (entitlement por módulo)                                      | ✅ 31/05/2026                                        |
| 2    | UI integrada (gateway, domínio único)                                          | ✅ 31/05/2026                                        |
| 3    | Vínculo drone ↔ obra/empreendimento                                            | ✅ 31/05/2026                                        |
| 4    | Deploy unificado (`docker compose --profile full`)                             | ✅ 31/05/2026                                        |
| 5    | Endurecimento — RS256/JWKS + borda                                              | ✅ 01/06/2026 (núcleo); operacionais → Fase 10     |
| 6    | Consolidação de identidade & RBAC de plataforma                                | ✅ 02/06/2026                                        |
| 7    | Migração v01 → v02 (frontend + backend dos módulos vazios)                   | 🚧 em andamento                                      |
| 8    | Fundação de dados: Postgres real +`tenant` obrigatório + uniques por-tenant | ✅ 04/07/2026 (8.1–8.5)                             |
| 9    | RBAC de campo — catálogo de permissões + mascaramento de PII                  | ✅ A–E (fatia E 12/07, suíte 76/76); D3/D4/D5 ✅ 11/07; D6 = extensão planejada |
| 10   | Observabilidade & redução de superfície operacional                           | 🚧 em andamento (10.1 base ✅ · 10.3.1/10.4/10.5.1-2/10.6/10.7/10.8/10.9/10.10 ✅ · **10.2 parcial ✅ 19/07: deploy/ unificado + funcoesemail**) |
| 11   | Consolidação de linguagens (Python como stack principal)                       | 🚧 11.2 ✅ 03/07 (funcoeslead) · 11.3 IA ✅ 14/07 + WhatsApp Fase C.0–C.4 ✅ 15/07 · **11.1 NF ✅ 16/07 (funcoesnf + bridge PHP absorvidos → Celery task NFE.io, Node/PHP removidos)** · **11.4 ✅ 16/07 (resíduo Node limpo: dir `funcoeslead` + arquivos Node do `funcoesia` — zero `.js` no backend)**; resta só o LLM local no compose (11.3) + 11.5 Angular oportunístico |

Cada fase concluída foi validada por um script E2E em [infra/gateway/](../infra/gateway/)
(`phase4_e2e.py`, `phase5_rs256_test.py`, `phase6_rbac_test.py`, `phase7_sil_test.py`,
`ie_impexp_test.py`, `orc6_orcamento_test.py`, `map6_maps_test.py`).

> **Bloqueio para produção:** as Fases **8 e 9** são **pré-requisito para operar com dados reais** —
> travam o *cutover* da Fase 7 com dados de cliente. Prioridade: **8 → 9 → 10**. A Fase 10 é
> transversal e absorve as pendências operacionais da Fase 5. Os **4 achados críticos** da revisão
> v02 foram **corrigidos em 03/07/2026** (o L4 pela antecipação da Fase 11.2 — `funcoeslead`
> absorvido pelo backend); os demais achados seguem em [pendencias.md](pendencias.md).

---

## Fases concluídas (0–6) — o que existe e o que ficou pendente

Narrativa completa de cada entrega (validações, bugs corrigidos) no histórico do git (`git log`).

### Fase 0 — Fundação

Banco por env (PostgreSQL+Redis via compose), serviço **IAM** próprio ([iam/](../iam/)) e o **backend** como
**resource server** com tenancy (`TenantScopedModel` + `TenantScopedViewSetMixin` + RLS).
**Pendências → Fase 8:** `tenant` nullable; `unique` globais; RLS validada só no SQLite/no-op.

### Fase 1 — SSO ponta a ponta

funcoesODM valida o JWT da IAM (JIT por `sub`, entitlement `drone` → 403); Angular captura o token;
middleware `iamAuth` nos serviços Node.
**Pendências:** entidades-filhas do drone escopadas por owner, não tenant → **Fase 8.5**; auth do
WebSocket → **✅ Fase 10.8** (CONNECT STOMP exige o token da IAM).

### Fase 2 — UI integrada

Gateway nginx em `:8090` roteia tudo (`/`, `/api`, `/auth`, `/drone`, `/odm-api`, `/ws`); React com
`AuthContext`→IAM, menu condicional `hasModule`, drone em iframe com token injetado.

### Fase 3 — Vínculo drone ↔ obra

`Project` ganhou `empreendimentoId`/`obraId` + filtros + soft-unlink; contexto propagado
React→iframe→Angular.
**Pendências:** gatilho `post_delete` no backend (auth serviço→serviço) → **✅ Fase 10.8** (JWT de
serviço da IAM → desvincula no drone via Celery); exibição na ficha da obra no React.

### Fase 4 — Deploy unificado

`docker-compose.yml` raiz com profiles: `--profile full` sobe os 11 serviços numa rede `sgi`, com
healthchecks e migrações no start.
**Pendências:** fluxo visual upload→processa→ortofoto no browser.

### Fase 5 — Endurecimento (RS256/JWKS + borda)

IAM assina RS256 (chave em `infra/keys/`, não versionada) e publica JWKS; backend/drone validam só com a
pública; gateway com headers de segurança + rate limit no login.
**Pendências operacionais → Fase 10:** JWK_URL + `kid` (rotação sem redeploy), LGPD, gestão de
segredos, observabilidade, DR, pentest.

### Fase 6 — Consolidação de identidade & RBAC

Login local do backend removido; entitlement genérico `RequireModule("codigo")` + RBAC `RequireRole`
([nucleo/permissions.py](../backend/nucleo/permissions.py)); detalhe da política em
[acesso-e-permissoes.md](acesso-e-permissoes.md).
**Pendências:** remover modelos `nucleo.Perfil`/`Permissao` (migration); mascaramento de campos →
**Fase 9**; aplicar o contrato aos módulos vazios ([modulos-planejados.md](modulos/modulos-planejados.md)).

---

## Fase 7 — Migração v01 → v02 🚧

**Objetivo:** abastecer a v02 com o que vale a pena da versão anterior
(`01sistema_gestao_integrada`) — sem reescrever o que já existe nem migrar dados. Plano completo em
[arquitetura/migracao-v01.md](arquitetura/migracao-v01.md).

- **Dados:** **greenfield** — banco novo, sem ETL da v01. Tenants/usuários (re)provisionados na IAM.
- **Frontend:** reconstruído do zero (04/06/2026, base de design da v01); módulos entram um a um.
  Padrão de porte: [migracao-v01.md §6](arquitetura/migracao-v01.md).
- **Backend (caso a caso):** onde a v02 já é mais madura, nada se porta; os módulos vazios recebem a
  lógica da v01 adaptada a tenancy/entitlement/RBAC: [migracao-v01.md §5](arquitetura/migracao-v01.md).
- **Cutover:** v01 (GCP) e v02 coexistem; rollback = reapontar domínio. **Com dados reais, o cutover
  depende das Fases 8 e 9.**

### Estado dos módulos — backend (07/06/2026)

| Módulo                                                                          | Entitlement        | Status                                                                                                                     |
| -------------------------------------------------------------------------------- | ------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| nucleo, empreendimentos, obras, fornecedores, modulodiario, moduloapi, funcoesia | —                 | ✅ Completo                                                                                                                |
| clientes                                                                         | —                 | ✅ 04/06/2026                                                                                                              |
| modulocalendar                                                                   | —                 | ✅ Completo + testes                                                                                                       |
| rh                                                                               | `rh`             | ✅ Completo                                                                                                                |
| moduloerp                                                                        | `erp_financeiro` | ✅ 07/06/2026 (`Fatura`→`ContaPagar`/`ContaReceber`; +`CentroCusto`/`Rateio*`/`LoteRemessa`/`RevisaoBaixa`) |
| modulocrm                                                                        | `crm`            | ✅ Completo                                                                                                                |
| funcoescobrancas (Asaas)                                                         | via`moduloerp`   | ✅ MVP 08/06/2026 ([doc](modulos/funcoescobrancas.md))                                                                      |
| moduloscm                                                                        | `scm`            | ✅ Backend (fatias 1–3) 20/07/2026. F1: catálogo (`Produto`/`OfertaFornecedor`/`FaixaPrecoOferta`) + `CentroCusto` próprio. F2: pivô `Demanda`(+`ItemDemanda`) publicável + `Cotacao`→`Proposta`(+`ItemProposta`), verbos `publicar`/`adjudicar`. F3: `PedidoCompra`→`Recebimento`+`AvaliacaoFornecedor` com as **duas vias** (`comprar_direto`/`gerar_de_cotacao`) e seams ERP/SIL/NF-e. Seams de rede (`ref_externa`/`origem_tenant`) prontos, inertes; lado vendedor + marketplace → Esfera de Rede. 19 perms `scm.*`; agg de reputação no `PropostaSerializer` + endpoint `dashboard/`; suíte **34/34** sobre PG. Desenho em [expansão/modulos/moduloscm.md](../expansão/modulos/moduloscm.md). **Frontend React ✅ 22/07/2026, reconstruído p/ resolutivo 23/07/2026** (mapa comparativo com estrelas/menor/delta, hub com trilho de fluxo, catálogo em cards + Comprar direto, IA inerte; aba Esfera de Rede bloqueada — cadeado/teaser) |
| `catalogo` (item mestre de plataforma)                                          | — (fundação)      | ✅ **SIL.0 24/07/2026** — `catalogo.Item` (bem/serviço/equip./EPI/ativo/composição) + `ComponenteComposicao`, `cadastro.item.*`, RLS fail-closed. `Produto` do SCM **migrado preservando PKs** (`catalogo/0002`) + 3 FKs do SCM repontadas (`moduloscm/0004`) + `Produto` removido; seed/IAM ajustados. Suíte **catalogo+moduloscm 37/37** sobre PG. Planta [catalogo.md](modulos/catalogo.md) |
| modulosil (estoque & logística interna)                                          | `sil`             | ✅ **SIL.1–5 (24/07) + SIL.6 v2 (25/07/2026)** — full-stack. Núcleo (local/saldo/lote/movimentação/requisição/transferência/devolução/inventário), **custo médio ponderado móvel**, RLS fail-closed. **Laço vivo com o SCM:** Recebimento→**ENTRADA** (signal idempotente); saldo<mínimo→`gerar_demanda`. **v2 construtora-native:** **EPI/NR-6** (`EntregaEPI`, CA+validade, comprovante), **ferramentaria** (`Ferramenta`/`EmprestimoFerramenta`, comodato+calibração), **apropriação por etapa** (`obras.EtapaObra` em mov./requisição), **curva ABC** e **aplicado×orçado** (endpoints; orçado→[Orçamento](modulos/moduloorcamento.md)). Colaborador integra ao RH. **26 perms `sil.*`** + persona `almoxarife`. Suíte **modulosil 23/23** (60/60 c/ catalogo+SCM), IAM 115/115. **E2E [phase7_sil_test.py](../infra/gateway/phase7_sil_test.py) 40/40 no stack vivo pelo gateway ✅ 25/07** (entitlement fecha p/ quem não assina; Recebimento→ENTRADA no local do seam, idempotente no re-save; custo médio ponderado; mínimo→Demanda `origem=estoque` no SCM; requisição aprovar→atender com reserva e apropriação obra+etapa; `aplicado/` com `orcado` nulo). Frontend **Operação×Gestão** com drill-downs — planta [modulosil.md](modulos/modulosil.md) |
| moduloorcamento (orçamento de obra)                                              | `orcamento`      | ✅ **ORC.0–ORC.6 26/07/2026** (full-stack, E2E vivo). **ORC.0** fundação: **base referencial de plataforma** (`BaseReferencial`/`InsumoReferencia`/`ComposicaoReferenciaItem`, globais **sem tenant/RLS** por serem dado público — [planta §11.1](modulos/moduloorcamento.md)), comando `importar_base_referencial` (SINAPI/ORSE, XLSX/CSV, idempotente, `--dry-run`), **adoção no catálogo do tenant**, API read-only + `adotar`/`adotar-lote`, `Item.Fonte` ampliado (`catalogo/0003`), entitlement + **9 perms** + persona `orcamentista`. **ORC.1** planilha **versionada** (`Orcamento`/`ItemOrcado`/`RevisaoOrcamento`): árvore EAP sintético×analítico, **snapshot** na linha, aprovar congela / revisar cria a versão seguinte; **seam do SIL fechado** (`orcado`/`saldo`/`estourado` no `aplicado/`, contra custo direto). **ORC.2** `ComposicaoBDI` pela fórmula do **Acórdão 2622/2013-TCU** (+BDI diferenciado por linha), explosão recursiva → `ItemOrcadoInsumo` (memória de cálculo), encargos só sobre mão de obra, curva ABC do orçado, **precificar pelo histórico real** do SCM/SIL. **ORC.3** **quatro colunas** (orçado×comprometido×aplicado×realizado; *realizado* cobre só o que passou por pedido — o ERP amarra despesa a empreendimento, lacuna é a D.1.4) + cronograma (`ParcelaEtapa`) e **curva S**. **ORC.4** paramétrico por **CUB** (`ParametroObra`, projeto-padrão) + **quadros da NBR 12721** (I–IV calculados, V–VIII descritivos via `MemorialNBR`; coeficiente de proporcionalidade ≠ fração ideal). RLS fail-closed em todas as tabelas do tenant; sem permissão nova ([planta §12.1](modulos/moduloorcamento.md)). **ORC.5 ✅ 25/07** (frontend Malha — hub + 5 páginas; + endpoint `por-categoria/`, que declara `cobertura_pct`). **ORC.5b ✅ 25/07** — 8 models novos com RLS fail-closed ([migration 0006](../backend/moduloorcamento/migrations/0006_orc5b_bancos_importacao_reprecificacao.py)): **`BancoPreco` do tenant** (tabela **separada** da base-mãe pública — não `tenant` nulável, para a política fail-closed não ganhar exceção —, com obra opcional, pastas e **trava** com rastro), **importação com conferência linha a linha** (XLSX/CSV/PDF → `ImportacaoPreco`/`LinhaImportacao` classificadas em nova/duplicada/inválida; confirmar tudo · confirmar seleção · negar tudo; nada grava antes da decisão), **reprecificação** como **lote desfazível** (`Reprecificacao`/`LinhaReprecificacao`: prévia item a item sobre **qualquer** publicação, data de corte à la Sienge, desfazer restaura preço **e** procedência e só do último lote; orçamento aprovado exige revisar), **duplicar/copiar** (planilha nova, não revisão — etapa descartada ao trocar de obra, com aviso) e **exportação** XLSX/PDF. Quotas `banco_preco_linhas` (objeto, contada em `ItemBancoPreco`) e `importacao_linhas` (operação) em [payment/planos.py](../payment/planos.py). Leitura de planilha extraída para `leitura.py`, compartilhada com o comando. **Regressão pega na revisão:** `permission_map={"GET": …}` não é contrato de `RequirePermission` (as chaves são `view`/`write`) e desligava o gate de leitura dos 5 ViewSets novos — corrigido, com teste. Suíte `moduloorcamento` **200/200**, **backend 541/541** sobre PG · IAM 115/115. **IE.1 ✅ 26/07/2026** — a importação de preço saiu do módulo e virou declaração sobre o `funcoesimpexp`: 3 recursos (`orcamento.banco_preco`, `orcamento.base_referencial`, `orcamento.planilha`) em [impexp.py](../backend/moduloorcamento/impexp.py); `importacao.py`, `ImportacaoPreco`/`LinhaImportacao` ([migration 0007](../backend/moduloorcamento/migrations/0007_ie1_importacao_absorvida_pelo_motor.py)), as rotas `/api/orcamento/importacoes/**`, o `ConferenciaImportacao.tsx` e a API/tipos do módulo **removidos**; `leitura.py` reduzido ao que é da analítica (as primitivas subiram para o motor). Documento formatado (planilha EAP, curva ABC, cronograma) **fica** — não é exportação tabular. Gate passou a ser "acesso total ou nada". Suíte `moduloorcamento` **206/206**, **backend 610/610** sobre PG. **ORC.6 ✅ 26/07/2026** — E2E [orc6_orcamento_test.py](../infra/gateway/orc6_orcamento_test.py) **55/55 no stack vivo pelo gateway**: entitlement fecha p/ quem não assina; base referencial pública e read-only (POST → 405); adoção no catálogo idempotente; planilha nasce rascunho editável com **snapshot** (renomear o item no catálogo não mexe na linha); explosão da composição + `por-categoria` declarando `cobertura_pct`; **segregação de alçada** (o `orcamentista` recebe 403 em `aprovar`, por desenho); aprovar congela (PATCH e nova linha → 409); **o seam causal** — a obra que não tinha `orcado` em `/controle/` passa a ter as quatro colunas + BDI + nota de cobertura; revisar exige motivo e cria v+1; cronograma linear fechando 100% em toda etapa (`validacao.consistente`) + curva S; **reprecificação desfazível** (prévia inerte → aplicar → desfazer restaura o preço); duplicar não mexe no estado da origem; XLSX pelo gateway; NBR 12721. **Achado do E2E: [D28](pendencias.md) — `orcamento.orcamento.aprovar`/`.revisar` não estão em nenhuma persona de fábrica**, então hoje só o admin do tenant aprova. → [planta §12](modulos/moduloorcamento.md) |
| `funcoesimpexp` (importação/exportação de plataforma)                         | — (fundação)      | ✅ **IE.0–IE.1 26/07/2026** — motor completo e com o 1º consumidor. **IE.0** 25/07 (registry declarativo, formatos XLSX/CSV/PDF, modelo gerado das colunas, conferência linha a linha, desfazer, gate "acesso total ou nada", RLS fail-closed). **IE.0b** 26/07: job Celery da R10 (corte de volume no motor, `LENDO` + progresso, arquivo com `expira_em` + faxina no beat, `tenant_context` sempre — a lição do D8), **contexto de destino** (`com_contexto`/`validar_contexto`, cópia por operação para dois destinos simultâneos não se cruzarem), gancho `checar_quota_objeto` (teto de acervo é do módulo) e **de-para salvável** (`MapaColunas`, RLS na [migration 0004](../backend/funcoesimpexp/migrations/0004_rls_mapa_colunas.py)); +5 endpoints (histórico com `pode_desfazer`, mapas, acompanhamento/baixa do job). **IE.0c** 26/07: `<BotaoExportar>` e `<WizardImportacao>` em [components/malha/impexp/](../frontend/src/components/malha/impexp/) — somem sozinhos sem acesso total (quem decide é `/api/impexp/recursos/`, não uma prop); `Btn`/`Modal` promovidos ao kit. **De-para também no job** ([planta §7.1](modulos/funcoesimpexp.md)): lote interrompido guarda os cabeçalhos vistos e **preserva o arquivo**, e `remapear` relê o mesmo — sem isso a R4 morria no único caminho que mais precisa dela. Suíte `funcoesimpexp` **63/63**, **backend 649/649** sobre PG. **E2E [ie_impexp_test.py](../infra/gateway/ie_impexp_test.py) 16/16 no stack vivo pelo gateway ✅ 26/07** (4.000 linhas → job → de-para → conferência → aplicar → desfazer → exportar; R1 provada: zero linhas no destino antes da decisão). Falta só **IE.n** (um módulo por vez, sob demanda) — [planta](modulos/funcoesimpexp.md) |
| modulomaps (dimensão espacial)                                                   | `maps` (parcial)  | ✅ **MAP.0–MAP.5 26/07/2026** (full-stack). **Duas metades:** `Local` é **fundação sem entitlement** (georreferenciar obra/empreendimento/fornecedor/almoxarifado/unidade é cadastro, como `catalogo`) e as camadas ficam atrás de `maps`. **MAP.0** — **PostGIS no stack**: imagem do banco `postgres:16-alpine`→**`postgis/postgis:16-3.4`** em [base.yml](../deploy/compose/base.yml) e no CI, `binutils`+`gdal-bin` no Dockerfile do backend, `django.contrib.gis` + engine postgis; a **extensão nasce no `template1` pelo superuser** ([init](../infra/postgres/init/01-init-databases.sh)) e não numa migration, porque `erp_app` é role comum de propósito (é disso que a RLS FORCE depende) — assim `erp_db` **e** o `test_erp_db` de cada execução herdam. `Local` (ponto+área+endereço estruturado+`precisao`/`fonte`, vínculo polimórfico com CheckConstraint) + **cascata de geocodificação** em [nucleo/geo.py](../backend/nucleo/geo.py) (endereço via Nominatim → CEP via BrasilAPI → centroide de município pela malha do IBGE, com *shoelace* em Python puro p/ o `nucleo` não exigir GEOS) + comando `georreferenciar_cadastros` (idempotente, `--dry-run`, **nunca rebaixa um pin `exata`**). **MAP.1** — `<Mapa>` (MapLibre) no kit **compartilhado** + página **Operação × Território**. **MAP.2** — `Rota`/`ParadaRota` (OSRM p/ traçado; sem motor, reta carimbada `procedencia=estimada`) + ordem por vizinho-mais-próximo+2-opt com **violações de janela declaradas**, `Geofence` (perímetro real ou raio) e o **seam do SCM**: `distancia_km` no mapa comparativo de propostas via `cotação→demanda→centro de custo→obra`. **MAP.3** — `Camada`/`Feicao` com `data_referencia` (antes/depois) + `Ortofoto` (índice por bbox/data; **tile servido pelo backend com gate**, não o COG `permitAll` do drone — S10). **MAP.4** — `PlanoVoo`: altura **derivada do GSD** e da geometria da câmera, grid/duplo/perímetro/orbital/corredor recortados pelo GEOS, e exportação **KML · MAVLink `.plan` · Litchi CSV · DJI WPML (KMZ)**. **MAP.5** — detecção de endereço (regex ancorado no CEP + XML da NF-e) → conferência pelo **`funcoesimpexp`** (recurso `maps.local`, desfazível). **10 perms `mapa.*`** (`mapa.local.*` em `base`; o resto em `maps`) + persona **`topografo`**; quotas de COGS (`geocodificacoes_mes`/`rotas_mes`/`storage_raster_gb`) declaradas e inertes em [payment/planos.py](../payment/planos.py). RLS fail-closed nas 8 tabelas. Suíte `modulomaps` **44/44**, **backend 730/730 sobre PostGIS** · IAM 115/115 · build do frontend (`npm ci`+`tsc -b`+`vite build`) limpo. **MAP.6 ✅ 27/07/2026** — E2E [map6_maps_test.py](../infra/gateway/map6_maps_test.py) **103/103 no stack vivo pelo gateway**: as **duas metades** do gate com token real (tenant sem `maps` lê `Local` e leva 403 em camada/voo/rota; sem `mapa.local.view` nem a fundação abre); cascata contra a rede de verdade (CEP→cidade/UF/IBGE) declarando precisão e procedência; **pin `exata` soberano** (nem `?forcar=1` o rebaixa); discriminador incoerente vira 400, não 500; fila de decisão real (obra sem coordenada + pin de município) e, sem o módulo, sem pendência de camada; vizinhança por raio com `ST_DWithin`; **o seam do SCM causal** — a proposta que não tinha distância passa a ter pela cadeia cotação→demanda→centro de custo→obra, e o fornecedor sem local segue `null`; antes/depois por `?ate=` e recorte por `?bbox=`; **tile do acervo gateado** (401 sem token, 403 sem entitlement — o contraste com o `permitAll` do S10); **altura batendo com a geometria da câmera** (73,0 m para GSD 2 cm/px) + os 4 formatos de exportação; sem OSRM a rota se carimba `estimada` e o otimizador devolve a violação de janela; cerca por raio + `conter`; e a **R1 do motor** (detecção não grava, conferência grava, linha fora do Brasil recusada, lote desfeito). **Dois achados do E2E: [D31](pendencias.md) — nenhum tenant assinava `maps` no stack vivo (o módulo estava inalcançável; re-seed corrigiu) e o seed não tinha ator para provar as duas metades; [D32](pendencias.md) — o degrau do CEP da cascata está inerte com o provedor grátis.** **Falta:** só MAP.7 (`CamadaExterna`/banco de terrenos — expansão). Planta [modulomaps.md](modulos/modulomaps.md) |
| moduloaps · modulodms · modulopdca                                               | próprio           | 📋 Placeholder (alvos do porte v01)                                                                                        |

> Rotas de apps simples registradas direto em `config/urls.py` (padrão correto, sem `urls.py` local).
> Cobertura de testes ainda pontual: `modulocalendar`, `modulocrm`, `nucleo` e `moduloerp`.
> `tenant` nullable e `unique` globais são bloqueadores da **Fase 8**.

### Estado dos módulos — frontend React (08/06/2026)

Arquitetura, design system e convenções em [frontend.md](frontend.md); fases de construção
(A/B/C/D/E/F) definidas lá na §10 equivalem às linhas abaixo. **Todo módulo de frontend segue a
régua de módulo** (grandioso + expansível, o **SCM** como referência): cockpit com fila de decisão,
loop do domínio ponta a ponta, dados honestos, **integração visível entre módulos** (o que conversa
no backend conversa na tela — um sistema, não silos) e costura com a expansão — [frontend.md §1.6](frontend.md).

> **Identidade visual Malha v1** ✅ 20/07/2026 — definida, **aplicada ao shell no protótipo**
> (sidebar/corpo, uma tela só — telas de produto ficam fora por decisão: **hub é um por edição**,
> padrão na planta §9) e com passe de contraste (tokens §5.3); planta em
> [identidade-visual.md](identidade-visual.md) + [protótipo](identidade-visual-prototipo.html).
> **Migração React em partes (decisão 21/07): fundação do shell primeiro, protótipo como alvo, marca
> completa, claro+escuro desde já** — módulos v01 migram um a um. **Parte 1 ✅ 21/07/2026:** tokens
> Malha (dois temas + `data-theme`) em [index.css](../frontend/src/index.css), fontes Archivo/Inter/
> JetBrains, `ThemeProvider`/`useTheme`/`ThemeToggle` (default `prefers-color-scheme` + toggle, anti-flash
> no index.html) e aliases de compatibilidade v01 theme-aware (app inteiro acompanha o tema sem reescrita);
> `tsc` limpo. **Parte 2 ✅ 21/07/2026:** sidebar da marca — marco [Quarteirão](../frontend/src/components/brand/Quarteirao.tsx)
> + lockup + régua do ciclo, seções endereçadas, item ativo = quarteirão aceso (ponto âmbar), recorte do
> [Bairro](../frontend/src/components/brand/BairroRecorte.tsx) no rodapé (dia/noite via `--city-*`), acompanha o tema;
> [AppSidebar](../frontend/src/components/layout/AppSidebar.tsx) reescrito (colapso preservado; Suprimentos/Esfera de
> Rede como itens-farol travados). `tsc` limpo, imagem `react` rebuildada. **Parte 3 ✅ 21/07/2026:** topbar glass
> ([AppTopbar](../frontend/src/components/layout/AppTopbar.tsx)) — breadcrumb por rota, [chip de estágio](../frontend/src/components/brand/EdicaoChip.tsx)
> "Edição Construtora · Construir" (§9), [ThemeToggle](../frontend/src/components/ThemeToggle.tsx) (o gesto de tema é
> movimento de marca §7), sino de notificações e menu do usuário nos tokens Malha. **⌘K dispensado por ora**: command
> palette exige busca cross-entidade que não existe (ver **F2** em pendencias) — volta quando houver busca real. `tsc`
> limpo, imagem `react` rebuildada. **Parte 4 ✅ 21/07/2026 — fundação do shell fechada:** design system Malha
> em [components/malha/](../frontend/src/components/malha/) — `Card` (superfície `--surface`), `Pill` (estado nomeado,
> 6 kinds semânticos + ponto pulsante), `Num` (leitura de instrumento mono tabular) e `KpiCard` (valor mono + delta nos
> `--*-ink` + variante `accent`). Biblioteca para o SCM e os próximos módulos; legados migram um a um. `tsc` limpo,
> imagem `react` rebuildada. **Shell Malha v1 pronto**. **Frontend do SCM ✅ 22/07/2026** — 1º módulo nascido sobre a fundação
> ([modules/scm/](../frontend/src/modules/scm/)): S.1 catálogo (Produtos/Ofertas+faixas/Centros de
> custo), S.2 demanda→cotação (mapa comparativo de propostas + adjudicar), S.3 pedido (duas vias:
> comprar direto/gerar de cotação)→recebimento+avaliação, S.4 hub de KPIs. Kit de UI Malha próprio do
> módulo (DataTable/Drawer/Modal/inputs/Pager), **selects com busca server-side** (`AsyncEntitySelect`
> + paginação nos viewsets — fecha o F2 dentro do SCM) e **chips de seam read-only**
> (rede/ERP/NF-e/estoque) que aparecem só quando preenchidos. `tsc` dos arquivos SCM limpo.

| Fase         | Módulo / componente                                       | Status                                                                         |
| ------------ | ---------------------------------------------------------- | ------------------------------------------------------------------------------ |
| A            | Fundação (Tailwind 4, AuthContext, AppShell, roteamento) | ✅ 04/06/2026                                                                  |
| B            | Landing + Login + Hub de módulos                          | ✅ 04/06/2026                                                                  |
| C.1          | Dashboard de KPIs                                          | ❌ Pendente                                                                    |
| C.2–C.4     | Empreendimentos · Obras · Clientes                       | ✅ 04/06/2026 · **Clientes reconstruído como carteira ✅ 25/07/2026**: grade tipo planilha (rolagem infinita virtualizada, cabeçalho/1ª coluna congelados, colunas redimensionáveis e reordenáveis, Ctrl+C, teclado) com **visão Clientes × Unidades** e **Agrupar por** até 3 níveis com subtotais em `GROUP BY` sobre a carteira inteira; unidade **estruturada** (quadra/lote/bloco/andar) + cidade/UF no empreendimento; **adimplência** derivada de `ContaReceber` (pílula p/ todos, números atrás de `erp.cobranca.view`); ficha com 6 abas incluindo **Financeiro** (extrato + boletos) e **Obra** (avanço por etapa). `/api/clientes/` passou a ser **paginado**. **Venda por unidade cadastrada ✅ 26/07/2026**: `empreendimentos.Unidade` (identificação única + preço de tabela + situação) com aba **Unidades** no empreendimento e contagem na Visão Geral; a aquisição virou **proposta** — seletor de unidade, desconto, entrada parcelável, **Price/SAC**, balões, simulação ao vivo (`/simular/`) e carnê por ato explícito (`/gerar-parcelas/`, sem boleto). Base de dev recriada com CPF/CNPJ válidos. Suíte `clientes` 69/69 sobre PG, E2E vivo pelo gateway. **26/07/2026 — pacote de achados do usuário (F17–F20):** venda com **permissão própria** (`cadastro.venda.view`/`.edit`/`.gerar_carne` — comercial vende, financeiro emite o carnê); **condição de pagamento rege o plano** (à vista vira parcela única no motor, balões renomeados p/ parcelas anuais); **unidade com medidas e confrontantes por lado** (memorial montado no backend, fora da grade e dentro da ficha); **correção monetária por índice** (`nucleo.IndiceEconomico`/`ValorIndice` globais + `corrigir/` com prévia); `carteira/opcoes/` voltou do 500. Backend **686/686** sobre PG |
| C.5          | Fornecedores                                               | ✅ 05/06/2026                                                                  |
| C.6          | Diário de Obra + IA                                       | ✅ 06/06/2026                                                                  |
| D.1.0–D.1.1 | ERP: fundação UI + Contas a pagar/receber                | ✅ 07/06/2026                                                                  |
| D.1.2        | ERP: Boletos & Asaas (telas + botão gerar cobrança)      | ✅ 08/06/2026 · **18/07: erro do Asaas persistido em Boleto `ERRO` (payload/códigos) e clicável na UI; cancelamento de boleto (botão → `cancelar_payment`) + aba Cancelados + webhook `PAYMENT_DELETED`; abrir documento verifica o Asaas ao vivo (online=verdade do gateway / offline=última versão + aviso)** |
| D.1.3        | ERP: notas fiscais (**emitir NFS-e por diálogo**, abas emitidas/canceladas/recebidas, cancelar NFS-e, PDF/XML) | ✅ 16/07/2026 · **E2E de emissão feliz validado 17/07** (empresa real NFE.io de teste com Inscrição Municipal + certificado): emitir → `EMITIDA` (nº atribuído) → **PDF/XML baixam pelo gateway** (após D9: resolver do 302 + volume `media_data` compartilhado). NFS-e é **assíncrona** (fica `PROCESSANDO` até uma consulta atribuir o número). Suíte `moduloerp`/`funcoescobrancas`/`modulocrm` 69/69. **18/07: erro da NFE.io persiste o payload/códigos e vira botão clicável na UI; abrir documento verifica a NFE.io ao vivo (serve a versão CANCELADA quando cancelada); cancelamento carimba `data_cancelamento` e rebaixa PDF/XML.** Falta só UI de emissão em lote + auto-poll das PROCESSANDO |
| D.1.4        | ERP: financeiro por obra (DRE)                             | ❌ ([moduloerp.md §13](modulos/moduloerp.md#13-roadmap-em-sub-fases-fase-d1x)) |
| D.2          | RH                                                         | ✅ 06/06/2026                                                                  |
| D.3          | CRM                                                        | ✅ 05/07/2026 (dashboard + leads + accounts + contacts + opportunities)                                           |
| E.1–E.2     | Drone wrapper (iframe+SSO) · Calendário                  | 🚧 Calendário Fatia A (UI) + **Fatia B (recorrência RRULE) ✅ 13/07/2026** + **Fatia F (feriados federais/estaduais/municipais por localidade) ✅ 13/07/2026** (fed+est via python-holidays, mun via dataset MIT + comando `sincronizar_feriados`; seletor obra→estado→município; cor por escopo; carimbo de atualização p/ superuser; suíte 25/25) — **rebuild do sgi-react aplicado 13/07; Fatia B validada E2E 10/10 via gateway (expansão de série, override/exclusão "somente esta", exclusão total); polimento UX: cursor de ponteiro nos eventos, reticências em título longo, localidade persistida (localStorage), clique em evento não-editável (feriado/diário/CRM) abre diálogo de leitura com o nome inteiro** + **Fatia C (lembretes por evento + centro de notificações in-app) ✅ 14/07/2026** (`EventReminder` + `nucleo.Notificacao` tenant-scoped/RLS; task Celery `despachar_lembretes` a 60s → notificação in-app + e-mail opcional; sino no `AppTopbar` com badge/polling; chips de lembrete no diálogo; **validado 14/07: suíte 27/27 sobre Postgres, typecheck limpo na fatia, E2E do sino vivo pelo gateway** — beat@60s + worker despacham o lembrete → notificação in-app); D–E planejadas ([modulocalendar.md §6](modulos/modulocalendar.md)) |
| D.4          | **SCM** (`scm`) — suprimentos                              | ✅ 22/07/2026 (S.1–S.4). **Reconstruído p/ resolutivo 23/07/2026**: mapa comparativo (estrelas de fornecedor via `AvaliacaoFornecedor` agregada, "menor" por item, delta vs. menor total, moldura da recomendada) + barra de **IA inerte**; hub com **trilho de fluxo** + KPI Compras/mês (endpoint `dashboard/`, mês selecionável); catálogo de ofertas em **cards** + Comprar direto; **aba Esfera de Rede bloqueada** (cadeado; teaser de visão, sem feature de rede — seams inertes no backend). Full-stack; suíte 34/34; typecheck do SCM limpo; sub-fases em [modulos/moduloscm.md](modulos/moduloscm.md#frontend-fase-atual--escopo-e-sub-fases) |
| E.3          | **SIL** (`sil`) — estoque & logística · PDCA / DMS / APS | ✅ **SIL v2 25/07/2026** — [LogisticaPage](../frontend/src/modules/sil/pages/LogisticaPage.tsx) Malha com seletor **Operação × Gestão** (dois públicos, uma página): Operação (cockpit reenquadrado, **almoxarifados clicáveis** + **kardex do item** em drawer, movimentações c/ etapa, requisições, transf./devol., inventário, **EPI**, **ferramentaria**) · Gestão (**curva ABC**, **custo por obra orçado×aplicado**, giro & ruptura, Esfera de Rede 🔒). Colaborador via RH. Kit em `ui.tsx`, abas em `tabs/`; `vite build` limpo. PDCA / DMS / APS ❌ aguardam backend |
| E.4          | **Orçamento** (`orcamento`) — Orçar × Controlar             | ✅ **ORC.5 + ORC.5b 25/07/2026 · ORC.6 (E2E vivo 55/55) 26/07/2026** — hub + 5 páginas em [modules/orcamento/](../frontend/src/modules/orcamento/): **Hub** (fila de decisão real, KPIs com link p/ SCM/SIL), **Orçar** (grade tipo Excel: edição na célula, Tab/Enter/F2, colar bloco do Excel, EAP recolhível, sintético×analítico, janela virtual, inserir item com 3 origens; + duplicar, reprecificar e exportar), **Controlar** (quatro colunas + curva ABC em Pareto + composição por natureza + curva S), **Cronograma** (grade percentual editável + curva S), **Bases & bancos** (bases-mãe travadas + **bancos próprios** + **importação com conferência linha a linha**), **Incorporação** (paramétrico CUB + quadros NBR). `tsc` limpo no módulo. **26/07 (IE.1):** a aba Bases & bancos trocou a conferência própria pelo `<WizardImportacao>` do kit Malha (+ `<BotaoExportar>` e o histórico com **desfazer**); a API/tipos de importação do módulo saíram. **ORC.6 ✅ 26/07** — módulo fechado |
| E.5          | **Maps** (`maps` parcial) — Operação × Território            | ✅ **MAP.1–MAP.5 26/07/2026** — [TerritorioPage](../frontend/src/modules/maps/pages/TerritorioPage.tsx) com seletor **Operação × Território**, que é o **mesmo corte do backend**: Operação (mapa da empresa com fila de decisão, locais com precisão/procedência e ação de localizar, vizinhança "fornecedores num raio de X km") abre para **todo tenant** porque `Local` é fundação; Território (camadas com recorte temporal, acervo de voos com idade e sobreposição raster, planos de voo com memória de cálculo + 4 formatos de exportação, rotas com otimizar e violações de janela) trava no cadeado sem o entitlement — a rota **não** fica atrás de `ModuleRoute`, senão a tela que explica o módulo daria 403 a quem não o contratou. **`<Mapa>` (MapLibre) entrou no kit compartilhado** [components/malha/Mapa.tsx](../frontend/src/components/malha/Mapa.tsx), não num 5º kit de módulo: obra, fornecedor, almoxarifado e voo caem no mesmo mapa. Estilo é JSON → claro/escuro saem do `ThemeProvider` sem trocar provedor de tile (Carto claro/escuro · Esri satélite; OSM público fica de fora pela *tile usage policy*); `transformRequest` anexa o access token nos tiles de ortofoto, que são servidos pelo **backend**. **A precisão é desenhada:** halo cujo raio cresce com a incerteza — ponto firme é porta, mancha larga é "algum lugar nesta cidade". **Maps e Calendário saíram da sidebar e viraram ícone na topbar** (ao lado do sino): nenhum dos dois é um *lugar* do ciclo, são lentes transversais — régua em [frontend.md §3.2](frontend.md) |
| F.1          | **Hub da Edição Construtora** (`/app/dashboard`)            | ✅ 25/07/2026 — [AppHomePage](../frontend/src/pages/app/AppHomePage.tsx) reconstruída no padrão de hub da identidade §9: faixa Meia-Noite + **5 abas** (Visão geral · Requer decisão · Agenda · Módulos · Atividade, aba na URL `?aba=`). KPIs **compostos** dos agregados reais de cada módulo, condicionados ao entitlement ([useHomeResumo](../frontend/src/pages/app/home/useHomeResumo.ts): `plano/` + `erp\|scm\|sil/dashboard/` + `calendar/events/`) — sem módulo, sem KPI (nunca um zero); sem fonte, `em breve`. Catálogo com **todos** os módulos agrupados pelo **estágio do ciclo** + futuros com horizonte H1/H2/H3. Primeiros consumidores do kit `components/malha/`. `tsc`/`eslint`/`vite build` limpos |

> **Fluxo testável hoje** (`http://localhost:8090/`, demo/demo123): Landing → Login → Hub →
> Empreendimentos · Obras · Clientes · Fornecedores · Diário+IA · RH (4 abas, mascaramento por
> papel) · ERP (`/app/erp`: hub com KPIs/gráficos; workspaces contas a pagar/receber com baixa e
> rateio; boletos com timeline do webhook Asaas). Rebuild do container React necessário a cada
> mudança de frontend.

### Sistema de Lixo — exclusão segura 📋

Exclusão reversível com auditoria em todos os módulos; implementar após as Fases C–E do frontend.
Decisões já registradas (tabela genérica `Lixo` com payload JSON, papel `gestor_lixo`, auto-purge
configurável por tenant, IDs nunca reutilizados). Plano: [arquitetura/lixo.md](arquitetura/lixo.md).

---

## Fase 8 — Fundação de dados (Postgres real + tenancy forte) ✅

**Objetivo:** fechar o **calcanhar de Aquiles do isolamento**. Hoje `tenant` é `nullable` e os
`unique` são globais — um bug aqui é **vazamento de dados entre empresas**. RLS, `CheckConstraint` e
transações **só são reais no PostgreSQL**, não no SQLite (fallback de dev). Fase de **maior
prioridade**; precede qualquer dado real.

- **8.1 Rodar sobre Postgres:** ✅ 04/07/2026 — suíte completa **verde sobre Postgres** (37/37) como
  o role `erp_app` (não-superuser/não-BYPASSRLS, `FORCE ROW LEVEL SECURITY`), com a política
  fail-closed valendo de fato; SQLite segue verde (5 RLS pulados). Entregou: `TEST_RUNNER` ciente da
  RLS ([nucleo/test_runner.py](../backend/nucleo/test_runner.py)) que arma o bypass de plataforma por
  sessão para o seed; `arm_rls_for_tenant` passou a **desligar** o bypass (armar um tenant é
  autocontido — corrige vazamento de contexto entre métodos de `TestCase`, achado ao rodar sob PG);
  teste do S1 lê a linha do outro tenant sob `rls_bypass()`. Ver
  [desenvolvimento.md](desenvolvimento.md#rodar-os-testes).
- **8.2 `tenant` obrigatório:** ✅ 04/07/2026 — FK `tenant` do `TenantScopedModel` agora **NOT
  NULL** (11 migrações `AlterField`, uma por app, sobre ~40 modelos concretos). Backfill defensivo
  ([nucleo/migrations/0012](../backend/nucleo/migrations/0012_backfill_tenant.py)) roda antes do
  `SET NOT NULL` (todas dependem dele), sob bypass da RLS (a fail-closed esconde linha `tenant` NULL
  do role de app): órfãs → tenant único; aborta se ambíguo (0 ou >1 tenants). Aplicado no `erp_db`
  (0 órfãs) e provado no test DB (suíte 37/37). `perform_create` + RLS + coluna NOT NULL = 3 camadas.
- **8.3 Uniques por-tenant:** ✅ 04/07/2026 — cada `unique=True` global escalar em modelo de
  negócio (CPF/CNPJ, e-mail, razão social, nº/chave de NF, nome de cargo/obra/conta, etc.) virou
  `UniqueConstraint(fields=["tenant", …])` (7 migrações). Como o DRF descarta o validador quando o
  constraint inclui `tenant`, um mixin reutilizável
  ([nucleo/tenant_validators.py](../backend/nucleo/tenant_validators.py)) reintroduz a checagem
  **escopada ao tenant do request** (deriva o validador das próprias `UniqueConstraint`) → duplicata
  no mesmo tenant dá **400 limpo**, não 500. Necessário também porque no SQLite a RLS é no-op. Os
  `unique_together` sobre FKs já tenant-scoped (ex.: `(obra, nome_etapa)`) permaneceram — a FK-pai já
  amarra o tenant. Provado (`test_tenant_isolation::PerTenantUniquenessTests`): mesmo CPF em tenants
  distintos OK; duplicado no mesmo tenant → 400. Aplicado no `erp_db`; suíte 39/39 (PG e SQLite).
- **8.4 RLS ponta a ponta:** ✅ 04/07/2026 (S2) — política **fail-closed** (`migrations/0011`) +
  contexto armado na autenticação; provado no Postgres que sessão sem `app.current_tenant` não
  enxerga nem grava linha e que o acesso *cross-tenant* é bloqueado (defesa além do mixin). Bypass
  explícito (`app.rls_bypass`) para plataforma/webhook/jobs.
- **8.5 Tenant nas entidades-filhas do drone:** ✅ 04/07/2026 — `tenant_id` **NOT NULL** nas 6
  filhas do funcoesODM (`Chunk`/`ChunkImage`/`Measurement`/`Annotation`/`ProcessingTask`/
  `ProjectImage`), herdado do projeto-pai na criação. Isolamento imposto na **borda** por um
  `ProjectTenantInterceptor` (`config/`): todo `/api/v1/projects/{projectId}/**` exige que o projeto
  da URL pertença ao tenant do token → senão **404** (fechou vazamento real: `Measurement`/`Annotation`
  só validavam existência do projeto, não o tenant). Backfill idempotente no start promove a coluna a
  NOT NULL onde não há nulos. Seed ganhou 2º tenant `acme` (drone) p/ o E2E. Também travado o anexo de
  imagem cross-projeto em `addImagesToChunk`. Ver [phase8_tenancy_test.py](../infra/gateway/phase8_tenancy_test.py).

**DoD:** [test_tenant_isolation.py](../backend/nucleo/test_tenant_isolation.py) verde **em
Postgres**; `phase8_tenancy_test.py` provando NOT NULL + unique por-tenant + RLS + isolamento do drone.

## Fase 9 — RBAC de campo: catálogo de permissões + mascaramento de PII 🚧

**Objetivo:** o RBAC atual controla **endpoints** por *nome de papel* (tudo-ou-nada), não **campos**.
Para PII do RH (`DadoMedicoFuncionario`, `DadoBancarioFuncionario`) e dados financeiros, mascaramento
por permissão é **requisito LGPD**. Hoje só há um mascaramento *ad-hoc* (`salario_base` num único
serializer) e papéis são strings mágicas — três exigidos no código, dois nunca provisionados (origem
dos **403** na ficha do funcionário).

> **Desenho-alvo (AD-9):** RBAC + ABAC, catálogo global de permissões, papéis por tenant e
> mascaramento de campo em [arquitetura/rbac-abac.md](arquitetura/rbac-abac.md). A Fase 9 executa esse
> plano **por fatias A→E**; a fatia C fecha o mascaramento. **Decisão de sequência (04/07/2026):**
> fazer a fundação antes da máscara — sem chavear PII em nome de papel para não re-migrar depois.
> **Decisões resolvidas:** catálogo é registry Python **na IAM** (fonte única) sincronizado p/ a
> tabela `Permissao`; a checagem passa a ser por **permissão** (claim `permissions` no JWT), não por
> nome; máscara de leitura é **parcial** (`•••` + últimos dígitos) onde fizer sentido, `null` no resto.

- **9.A Catálogo + destravar (fundação):** ✅ 05/07/2026 (ativado no stack) — catálogo
  único [catalog.py](../iam/identity/catalog.py) com **99 permissões `modulo.recurso.acao`** (rh,
  erp_financeiro, crm, drone, base, plataforma; PII como recurso próprio) e **14 personas de fábrica**
  (com descrição legível); `sync_authz` reflete p/ `Permissao` e compõe papéis por tenant;
  `permissions` no JWT. **Personas dinâmicas** com trava anti-escalada (permissão ⊆ módulos assinados)
  e **UI de administração** ([modules/admin/](../frontend/src/modules/admin/): `/app/admin/papeis`
  cria/edita/**clona**/exclui papéis com picker por módulo; `/app/admin/usuarios` atribui papéis a
  usuários) — só `is_tenant_admin`, via gateway `/iam/`. Seed ganhou usuário `admin`. Testes 13/13 +
  E2E vivo (o 403 do RH destravado de verdade). Padrão de extensão p/ módulos da v01 em
  [rbac-abac.md §9](arquitetura/rbac-abac.md).
- **9.B Permissão no enforcement:** ✅ 05/07/2026 —
  [`RequirePermission`](../backend/nucleo/permissions.py) substitui `RequireRole`: ViewSet declara
  `required_resource="modulo.recurso"` (GET→`.view`, escrita→`.edit`) ou `permission_map`; auth expõe
  `iam_permissions`. RH (dado_medico/dado_bancario/folha) migrado; `RequireRole` **depreciado** com
  **fallback** (token sem `permissions` cai no papel → zero-downtime). CRM inteiro gateado por
  módulo+permissão, fechando **S5** (`OpportunityProductViewSet` só tinha `IsAuthenticated`). Testes
  DRF verdes sobre Postgres (`rh/tests.py`, `modulocrm/tests.py` — 15/15) + E2E vivo. **Estendido
  05/07** aos cadastros-base (`clientes`/`fornecedores`/`obras`/`empreendimentos`), que estavam sem
  camada 2 — achado **D5** (operacional criava cliente/venda). **Fatia B fechada 11/07 (D3/D4/D5):**
  `moduloerp` migrado de `RequireRole` p/ `RequirePermission` nos 14 viewsets, com verbos de domínio
  (baixa, cobrança, NF, lote, resolver) gateados por `action_permission_map`; camada 2 em
  `modulocalendar`/`moduloapi`/`funcoesia`; fallback agora **fail-closed** (D4: `None`=legado→papel,
  `[]`=nega); `tenant` read-only sistêmico nos serializers (D3, base `TenantScopedModelSerializer`).
  Suíte 71/71 verde. **Fatia E fechada 12/07:** `RequireRole` **removido** (a classe e o fallback
  por papel); `RequirePermission` ficou estritamente **fail-closed** — sem a permissão no token → 403,
  sem cair em papel (a autenticação deixou de distinguir `None`/`[]`, já que todo token da IAM traz
  `permissions` desde a 9.A). `required_role` retirado dos 20 viewsets/APIViews (moduloerp, rh,
  funcoescobrancas). Suíte **76/76 verde** sobre Postgres (role `erp_app`, RLS real).
- **9.C Campo/PII (mascaramento):** ✅ 05/07/2026 — `FieldMaskingSerializerMixin`
  ([nucleo/field_masking.py](../backend/nucleo/field_masking.py)) com **dois eixos**:
  `sensitive_fields` (leitura — mascara: CPF/CNPJ/conta → `••••`+dígitos; valores/PIX/texto → `null`;
  **fail-closed** sem contexto) e `write_protected_fields` (escrita — trava explícita com a `.edit`
  concedível). Aplicado em RH (`Funcionario` CPF/salário, `DadoMedico`, `DadoBancario`, `Pagamento`,
  `Folha`), clientes (`Cliente` CPF via `cadastro.cliente_doc.view`, `DadoBancarioCliente`) e
  fornecedores (só `DadoBancarioFornecedor` — CNPJ é público, não mascarado). Substituiu o hack do
  `salario_base`. **Correção pós-revisão (05/07):** a 1ª versão derivava a escrita da leitura
  (`rh.cpf.edit`, inexistente) e **travava a criação** de funcionário/cliente/fornecedor p/ não-admins;
  os eixos foram separados. **Correlato Fase 8.2:** `tenant` obrigatório no POST → `tenant` read-only
  nos serializers de RH/fornecedores. Testes `rh/test_field_masking.py` (11); E2E: não-admin cria ficha.
- **9.D LGPD além da máscara:** ✅ 05/07/2026 — **portabilidade** (`GET /api/lgpd/<tipo>/<id>/exportar/`,
  `plataforma.lgpd.exportar`) e **esquecimento** (`POST …/esquecer/`, `plataforma.lgpd.excluir`) p/
  funcionário/cliente ([nucleo/lgpd.py](../backend/nucleo/lgpd.py): exporta PII integral; anonimiza +
  apaga filhos de PII + desativa login). **Incidente ANPD** (`IncidenteLGPD`, RLS fail-closed): nasce
  **pendente**; só o **dono da plataforma** (`is_platform_admin`) **confirma** (inicia prazo de **72h**)
  ou **descarta** (falso positivo) — a trava anti-falso-positivo. Endpoints usam `RequirePermissionStrict`
  (fail-closed, sem fallback de papel). Testes `nucleo/test_lgpd.py` (8) verde. Falta a UI (Fase 7).
- **9.E Trilha de auditoria:** ✅ 11/07/2026 — `AuditLog` **imutável
  append-only** tenant-scoped: `save`/`delete` bloqueados no modelo
  ([nucleo/models.py](../backend/nucleo/models.py)), **trigger PostgreSQL** barrando UPDATE/DELETE mesmo
  em SQL cru/`queryset` ([migration 0017](../backend/nucleo/migrations/0017_auditlog_imutavel.py)), RLS
  fail-closed ([0016](../backend/nucleo/migrations/0016_auditlog_rls.py)) e API **read-only**
  `GET /api/auditoria/` restrita a `plataforma.auditoria.view` + admin de tenant/plataforma (fail-closed).
  Helper `registrar_auditoria` + mixins opt-in `AuditedModelViewSetMixin`/`PiiReadAuditMixin`
  ([nucleo/auditoria.py](../backend/nucleo/auditoria.py)); FK `usuario` congelado (`db_constraint=False`,
  rótulo durável em `usuario_nome`). **Coberto:** escritas de RH (funcionário, dado médico/bancário, ASO,
  pagamento, folha) com **nomes dos campos alterados** no update; **leitura de PII** (retrieve de
  médico/bancário/ASO → `visualizar_pii`); **baixa** financeira (choke point manual + Asaas); **emissão de
  NF** e **gerar cobrança**; **LGPD** export/forget. `detalhes` só metadados não-PII. **Legado:**
  `LogAtividadeUsuario` demovido a telemetria operacional (Celery/microsserviço) e sua API de leitura
  `/api/logs-atividade/` removida — a trilha sensível é o `AuditLog`; remoção do modelo + telemetria
  estruturada → Fase 10. **Validado:** `nucleo/test_auditoria.py` + **suíte completa verde (71/71)** sob
  Postgres (role `erp_app`, RLS real) **+ E2E [phase9_auditoria_test.py](../infra/gateway/phase9_auditoria_test.py)
  — 15/15 no stack vivo** (criar/atualizar+`campos_alterados`/`visualizar_pii`/`exportar_lgpd`; leitura
  restrita a admin/permissão; POST/DELETE → 405); migrations 0015–0017 aplicadas no `erp_db`.

**DoD:** `phase9_field_mask_test.py` verde; checagem por permissão em todo endpoint pago; procedimento
LGPD documentado em [infra/](../infra/); `AuditLog` populado; exportação e exclusão de titular via
endpoint admin.

## Fase 10 — Observabilidade & redução de superfície operacional 📋

**Objetivo:** 11 serviços, 3 stacks e 2 frontends é muita superfície para equipe pequena; sem
observabilidade, incidente multi-serviço é difícil de diagnosticar. Fase **transversal**; absorve as
pendências operacionais da Fase 5.

- **10.1 Observabilidade:** 🚧 fatia base ✅ 15/07/2026 (backend+IAM+gateway) — logs **JSON** com
  `request_id`/`tenant_id` correlacionados ponta a ponta (gateway gera/propaga `X-Request-ID`;
  `ObservabilityMiddleware` cronometra + loga acesso; `tenant_id` vem do choke point da RLS);
  **métricas Prometheus** (`sgi_http_requests_total`/`_duration_seconds`) em `GET /metrics`;
  **healthchecks estendidos** `/healthz` (liveness) + `/readyz` (banco/cache/broker), com o compose
  sondando `/readyz`; perfil `observability` sobe o Prometheus ([infra/observability/](../infra/observability/)).
  **Falta:** Grafana + alertas (DoD), paridade no Java/Node, tracing (opcional).
- **10.2 Reduzir superfície:** coabitar os microsserviços Node; unificar build/CI; runbook único.
  **Parcial ✅ 19/07/2026 — deploy unificado:** compose e env saíram da raiz para
  [deploy/](../deploy/README.md), com um arquivo por ambiente (`base` + `dev`/`staging`/`prod`) e os
  modelos `*.env.example` correspondentes; `deploy/README.md` traz a tabela dev × staging × produção. O
  **prod é esqueleto NÃO VALIDADO** (serve de contraste e checklist de cutover; premissa: banco e Redis
  gerenciados, fora do compose). Dois pontos que a mudança expôs e exigiram correção: o Compose passou a
  derivar o nome do projeto de `compose/` (renomeando rede e volumes — o dev subiria com banco e mídia
  **vazios**), fechado com `name:` fixo no base; e o `COMPOSE_FILE` precisou de `COMPOSE_PATH_SEPARATOR=:`
  para o mesmo `.env` valer no Windows e no WSL. O `.env` real segue na **raiz** de propósito — é de lá
  que o compose e o `load_dotenv()` dos dois Djangos o leem.
  **E-mail centralizado:** [funcoesemail/](../funcoesemail/README.md) — pacote na raiz, importado por IAM
  **e** backend, com o texto de todo e-mail em `templates/`. Não virou app do backend nem serviço com hop
  de rede porque recuperação de senha precisa funcionar com o backend fora do ar (é o que fazem Entra ID,
  WSO2 e ForgeRock: o IdP entrega os próprios e-mails de segurança). Por isso as imagens de backend e IAM
  agora buildam com **contexto na raiz** (+ `.dockerignore` raiz). `identity/emails.py` ficou só com a
  tradução `Usuario`→contexto. Testes: `funcoesemail/tests.py` (9) + E2E d11 **17/17 no stack vivo**.
  **Concluído 19/07:** `modulocrm/tasks.py` e `modulocalendar/tasks.py` migrados — **nenhum `send_mail`
  fora do pacote** em backend e IAM. A migração destapou o **D20**: o compose nunca passava `MAIL_*` ao
  backend e o STARTTLS era forçado na porta do Mailpit, ou seja, os lembretes de tarefa e de evento
  **nunca saíram em nenhum ambiente** (o aviso in-app do calendário mascarava). Corrigido e provado com os
  dois e-mails chegando ao Mailpit.
- **10.3 Operacional (herdado da Fase 5):** segredos (Vault/Secrets Manager), DR (PITR + ensaios de
  restore), varredura de deps (`pip-audit`/`trivy`), pentest.
- **10.3.2 Ingress público de webhooks (produção):** substituir o andaime de dev (túnel **ngrok** +
  `infra/ngrok-webhook-proxy`) por solução profissional — recomendado **Cloudflare Tunnel** (sidecar do
  compose, zero portas inbound, TLS+WAF, ingress só nos paths de webhook); alternativa: LB gerenciado +
  WAF. Mesmo princípio para os demais andaimes de dev (sandbox Asaas, SQLite, segredos de dev, LLM stub):
  aposentados antes do go-live. Desenho em [arquitetura/deploy-e-seguranca.md §3.1](arquitetura/deploy-e-seguranca.md).
- **10.3.1 Config segura por padrão:** ✅ 12/07/2026 (antecipada, fecha **S3+S4**). `DEBUG`/`IAM_DEBUG`
  default **False** + fail-fast de `SECRET_KEY`/`ALLOWED_HOSTS` fora de DEBUG; **RS256 obrigatório em
  produção** (HS256 só em dev); cookies seguros + HSTS quando não-DEBUG. Gate `check --deploy` no CI ✅ 14/07 (10.5.1).
- **10.4 Supply chain:** `npm ci` + lockfile obrigatório nos Dockerfiles/CI (10.4.1) ✅ — **o
  `frontend/Dockerfile` só passou a cumprir em 26/07/2026** (era `npm install --legacy-peer-deps`,
  que ignora o lock; causa raiz do **F6**);
  **10.4.2/10.4.5/10.4.6 ✅ 14/07/2026** — job `security-scan` no CI ([ci.yml](../.github/workflows/ci.yml)):
  `npm audit --omit=dev --audit-level=high` (frontend), `pip-audit` (backend+iam) e `trivy fs`
  (vuln com correção + **segredos**), todos **bloqueantes** em HIGH/CRITICAL, com allow-lists de
  triagem ([.trivyignore](../.trivyignore), [.github/pip-audit-ignore.txt](../.github/pip-audit-ignore.txt));
  **Dependabot** ([.github/dependabot.yml](../.github/dependabot.yml)) semanal nos ecossistemas
  versionados (pip backend/iam, npm frontend, github-actions) como motor de remediação. Falta:
  revisão dos `postinstall` (10.4.3), checklist de adição de deps (10.4.4), Maven/Angular (repo do drone).
- **10.5 CI/CD mínimo:** pipeline a cada push/PR (10.5.1) ✅ 14/07/2026 — GitHub Actions
  ([.github/workflows/ci.yml](../.github/workflows/ci.yml)): 3 jobs — **backend** (`manage.py test`
  sobre Postgres 16 + role `erp_app` não-superuser/CREATEDB → RLS fail-closed real; Redis de serviço;
  libs do WeasyPrint), **iam** (`manage.py test` no SQLite de dev) e **frontend** (`npm ci` bloqueante
  + `lint`/`build` informativos enquanto os 45 erros de `tsc` não forem zerados — **D27**). **O gate só
  passou a valer de fato em 26/07/2026 (D26):** o job do backend rodava um rótulo de app inexistente e
  **não executava nenhum** dos seus testes, e `frontend`/`security-scan` estavam vermelhos pelo `npm ci`
  do F6 — 3 dos 4 jobs. Linha de base na correção: **801 verdes** (backend 677 + `funcoesemail` 9 +
  IAM 115). Inclui o **gate
  `check --deploy`** (fecha S3/S4): o backend sobe em modo produção (DEBUG=False + RS256 efêmera) e passa
  o checklist com `--fail-level WARNING` (só `security.W008`/SSL-redirect silenciado — TLS no gateway).
  O drone (Java/Maven) fica no repo próprio. **10.5.2 ✅ 14/07/2026** — gates de CVE alta no job
  `security-scan` (ver 10.4). **Falta:** build/push de imagens em merge (10.5.3).
- **10.6 JWT em cookie HttpOnly:** ✅ 11/07/2026 (antecipada, fecha o **F1**). Ciclo de sessão padrão
  SaaS: **access token em memória** + **refresh em cookie HttpOnly** (`SameSite=Strict`,
  path `/auth/`) renovado em silêncio (10.6.1/10.6.2). Rotação + blacklist com **detecção de reuso** e
  **teto absoluto**; login com **"Lembrar de mim"**. O refresh
  **recalcula as claims** (revogação/mudança de permissão vale em ≤ access TTL). *(Os tempos vigentes
  não estão aqui de propósito — fonte única em [acesso-e-permissoes.md §5.2](acesso-e-permissoes.md);
  este bullet cravava "15 min / 12h / 30d / 90d" e ficou defasado em silêncio.)* Iframe do drone deixou o
  `?token=` — recebe o token por **postMessage** do shell e o atualiza a cada rotação (10.6.3). CSRF:
  `SameSite=Strict` + checagem de `Origin` no refresh/logout (10.6.4). IAM
  ([tokens.py](../iam/identity/tokens.py)/[cookies.py](../iam/identity/cookies.py)/views) validado
  (19/19); React ([api/session.ts](../frontend/src/api/session.ts) + `attachAuth`/`tokenStore`) e Angular
  do drone (postMessage) exigem rebuild dos containers p/ validação E2E.
  - **10.6.5 Revogação imediata de sessão (época no Redis):** ✅ 13/07/2026 — access TTL 15→**5 min**;
    troca/reset de senha e desativação carimbam `sess:revoked_after:<uid>` no Redis (DB 2) e o
    `IamJWTAuthentication` do backend rejeita access com `iat` anterior (fecha a janela residual do access
    stateless). Fail-open + **circuit breaker** (queda do Redis não deixa o request lento). **E2E backend+IAM
    validado** (revogação imediata ~40 ms; fail-open/closed; persistência AOF sobrevive a restart).
    **Drone replicado 13/07/2026:** `SessionRevocationService` (Jedis, mesmo Redis/DB2/chave) no
    `JwtAuthenticationFilter` do funcoesODM — sessão revogada → não autentica → 401; fail-open + breaker,
    testes unitários da decisão (`SessionRevocationServiceTest`, 7/7). Node (`funcoesia`/`nf`/`whatsapp`)
    fora de escopo: sem rota de usuário na borda (gateway não os roteia) e absorvidos na Fase 11.
    **E2E do drone validado no stack vivo 13/07/2026** (imagem Java rebuildada): token com módulo drone →
    200; carimbo `sess:revoked_after:<uid>` no Redis DB2 → **mesmo token 401**; relogin (iat>carimbo) → 200.
    Desenho: [acesso-e-permissoes.md §5.1](acesso-e-permissoes.md).
- **10.7 Ambiente de staging:** ✅ 18/07/2026 — mesmo `docker-compose.yml` + override
  ([docker-compose.staging.yml](../docker-compose.staging.yml)) + env de produção
  ([.env.staging.example](../.env.staging.example), `DEBUG=False`/RS256/cookies Secure/Celery async),
  gateway com **TLS** ([nginx.staging.conf](../infra/gateway/nginx.staging.conf)), isolamento do dev
  (`COMPOSE_PROJECT_NAME`+`SGI_PREFIX`, banco/portas/volumes próprios) e runbook + **gate automático da
  leva 8→11** reusando os E2E das fases ([infra/staging/](../infra/staging/): `up`/`seed`/`validate`/`down`).
  **Validado 18/07/2026:** stack no Docker + `validate.sh` **6/6 verde** (phase4/5/6/8/9/C sob
  TLS/RS256/DEBUG=False/Celery async). A 1ª subida **greenfield** expôs e corrigiu 7 defeitos de
  modo-produção que o dev escondia (ver [pendencias.md](pendencias.md) D10). Fora do gate: **phase10_8
  7/7** no staging (service-token na borda + WS CONNECT contra o `java-service`, rodado de dentro da rede
  com o Origin do gateway); **falta** só a sessão 10.6 (refresh silencioso) no browser.
  **Revalidado 18/07/2026** após a revisão do modelo de sessão (§5.2), a correção do cookie `Secure`
  (D16) e o frontend de inatividade: **gate 6/6 + phase10_8 7/7**, com imagens IAM/React rebuildadas.
- **10.10 Recuperação de senha e endurecimento de identidade (D11):** ✅ 18/07/2026 — fluxo "esqueci
  minha senha" por token de e-mail (uso único, hash no banco, TTL 30 min, teto 5/h, resposta genérica
  sem enumeração), **um caminho só**: o link vai para a caixa do próprio usuário e os admins do tenant
  recebem **aviso sem o link** (supervisão sem poder de takeover). **`email` obrigatório e único** no
  `Usuario` (migration 0004 com guarda legível); **troca de e-mail** saiu do PATCH genérico e passa a
  confirmar no endereço **ANTIGO**, armando cooldown de 24 h na emissão de token — é o que fecha a
  cadeia de takeover por admin comprometido; escalada de privilégio auditada; **`EventoSeguranca`**
  append-only na IAM (trigger PG), que até aqui não auditava nada; IAM ganhou **SMTP próprio**
  (`MAIL_HOST` obrigatório fora de DEBUG) e o compose, o **Mailpit** (perfil `mail`, UI `:8025`) como
  caixa de captura de dev/staging. **UI React ✅** — link na tela de login + telas
  esqueci/redefinir/confirmar-email sobre a moldura `AuthShell`. A troca de e-mail é **assimétrica**:
  direta para funcionário (o admin é o dono da empresa e administra aquelas contas; exigir confirmação
  num endereço morto travaria a pessoa), confirmada no endereço antigo quando o alvo é **admin**.
  Suíte IAM **69/69** + **E2E 17/17 no dev e 17/17 no staging**
  ([d11_recuperacao_senha_test.sh](../infra/gateway/d11_recuperacao_senha_test.sh) — parametrizável por
  `SGI_GW`/`SGI_MP`/`SGI_IAM_CONTAINER`, restaura o ambiente ao final), imagens `iam`/`react`
  rebuildadas nos **dois** ambientes. O `.env.staging` ganhou `MAIL_HOST=mailpit` (obrigatório com
  `IAM_DEBUG=False`) e `FRONTEND_BASE_URL=https://localhost:8443`. Detalhe e modelo de ameaça em
  [pendencias.md](pendencias.md#d11).
- **10.8 Auth do WebSocket e serviço→serviço:** ✅ 15/07/2026 (fecha pendências das Fases 1 e 3).
  **WebSocket:** o frame **STOMP CONNECT** do `/ws` passou a exigir o access token da IAM (o handshake
  HTTP segue `permitAll` — o browser não manda header no upgrade nativo). Novo
  `WebSocketAuthChannelInterceptor` (java-service) aplica o mesmo contrato do filtro REST — assinatura+
  `exp`, entitlement `drone` e revogação por época — e **recusa** CONNECT sem token/sem módulo/revogado;
  o cliente Angular (`websocket.service.ts`) manda o token no header STOMP `Authorization` (reavaliado a
  cada reconexão, acompanha a rotação). Correlato descoberto na validação E2E: o CORS do drone
  (`SecurityConfig`) não listava a origem do **gateway** (`localhost:8090`) → o browser do domínio único
  era barrado (403) antes do handshake; agora a allowlist é configurável (`app.cors.allowed-origins`/
  `APP_CORS_ALLOWED_ORIGINS`) e inclui o gateway. **Serviço→serviço:** a IAM emite **JWT de serviço** de vida curta
  (`POST /auth/service-token/`, segredo compartilhado `SERVICE_TOKEN_SECRET`, tempo constante; **interno** —
  bloqueado na borda) via `tokens.issue_service_token` (sem `user_id` → revogação no-op; só `tenant_id`+
  `modules:[drone]`). O backend, em `post_delete` de **Obra/Empreendimento** ([nucleo/drone_sync.py](../backend/nucleo/drone_sync.py)),
  enfileira uma Celery task que pede o token à IAM e chama o desvínculo do drone
  (`DELETE /api/v1/projects/links/{obra,empreendimento}/{id}`, endpoints que já existiam). **Validado:**
  IAM `ServiceTokenTests` (4/4) + backend `nucleo.test_drone_sync` (5/5) sobre Postgres; **E2E
  [phase10_8_service_ws_test.py](../infra/gateway/phase10_8_service_ws_test.py) 7/7 no stack vivo pelo
  gateway** (imagens IAM/java-service/drone-nginx rebuildadas): service-token bloqueado na borda (404),
  desvínculo do drone gateado por módulo (sem token 401 / com token 200), WS CONNECT recusado sem token
  (ERROR) e aceito com o token do demo (CONNECTED). **Correlato S10:** `/chunks/*/assets/*` segue download
  público por UUID (intencional p/ o visualizador Potree/GeoTIFF, sem header de auth) — mantido.
- **10.9 Executor Celery (worker+beat):** ✅ 12/07/2026 (antecipada, fecha o **A1**). Serviços
  `worker` e `beat` no `docker-compose.yml` (perfil `full`), reusando a imagem do backend; stack `full`
  roda assíncrona (`CELERY_TASK_ALWAYS_EAGER=False`). Sem isto, o webhook Asaas e a geração de
  cobrança processavam síncrono e nada periódico (lembretes CRM) disparava. Validação E2E do fluxo
  enfileirado depende de subir o compose.

**DoD:** dashboard mínimo (erros+latência) e alertas; runbook em [infra/](../infra/); pipeline CI
verde com gates; `npm ci`+`npm audit`+`trivy`+`pip-audit` automatizados; JWT em cookie `HttpOnly`;
staging funcional; WebSocket e serviço→serviço autenticados; checklist de dependências documentado.

## Fase 11 — Consolidação de linguagens 📋

**Objetivo:** reduzir de **5 stacks para 3**, eliminando o Node.js do backend e planejando a saída
do Angular — sem reescrever o que funciona.

**Decisão permanente de linguagens:** **Python** (models),
**Java** (drone e serviços onde performance/JVM justifiquem) e
**TypeScript** (todo o frontend). Ver AD-8 em [arquitetura.md](arquitetura.md).

Os microsserviços Node são wrappers finos sobre APIs REST — não justificam um quarto runtime:

| Serviço Node                            | O que faz                                        | Equivalente Python                                                                                                                       |
| ---------------------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `funcoesnf`                            | Chama NFE.io REST para emitir NF-e/NFS-e         | ✅**Absorvido 16/07/2026** (11.1): cliente REST `moduloerp.nfe_client` + Celery tasks `emitir/consultar_nota_fiscal_servico`; Node + bridge PHP removidos                                        |
| `funcoeslead`                          | Conversão/score de lead, agenda, notificações | ✅**Absorvido 03/07/2026**: `modulocrm/services.py` + actions, agenda in-process no `modulocalendar`, Celery task de lembretes |
| `funcoeswhatsapp`                      | Webhook WhatsApp → pré-cadastro do diário     | ✅ **Fase C.0–C.4 15/07/2026**: app Django `funcoeswhatsapp` (webhook + Celery), canal multi-tenant, fluxos diário/lead in-process, Node removido, **E2E 13/13 pelo gateway**                                     |
| worker de`funcoesia` (embutido no app) | Chama o Gemini na análise de imagens            | ✅**Absorvido 14/07/2026** (11.3): Celery task Python `analisar_documento_ia` lê a imagem in-process e chama a LLM local (`LLM_VISION_URL`) — [plano](arquitetura/diario-ia-reintegracao.md) |

O Angular migra por último (Leaflet, Three.js/Potree, GeoTIFF, STOMP): o gatilho é **manutenção
significativa do drone**, não uma data.

- **11.1** ✅ 16/07/2026 — `funcoesnf` (+ bridge PHP `NotaFiscalManager`) **absorvido** em
  `moduloerp`: cliente REST fino da NFE.io ([nfe_client.py](../backend/moduloerp/nfe_client.py), sem ORM/
  Celery, exceções tipadas `NFeIndisponivel`/`NFeErro`) + Celery tasks `emitir_nota_fiscal_servico`/
  `consultar_nota_fiscal_servico` ([tasks.py](../backend/moduloerp/tasks.py), base `DLQTask`, `rls_bypass`→
  `tenant_context`, retry/DLQ). As views deixaram de chamar `localhost:3003` (emissão enfileira → 202;
  consulta enfileira). **Node + PHP removidos** (0 `.php`/`.js` de `funcoesnf` no repo). Fecha **D1**
  (NF), **A2** (NF) e **L8** (status validado contra `StatusNFE.values` + timeout nos downloads de PDF/XML).
  Suíte `moduloerp/tests.py` estendida (cliente + task, cliente mockado). **Falta:** credencial NFE.io real
  (`NFE_IO_API_KEY`/`NFE_IO_COMPANY_ID`) + E2E no stack vivo — validação sob demanda.
- **11.2** ✅ 03/07/2026 — `funcoeslead` absorvido em `modulocrm`/`modulocalendar` (antecipada
  pelo achado L4, sem esperar a 11.1).
- **11.3** worker de IA (`funcoesia`) → Celery task Python ✅ 14/07/2026 (task `analisar_documento_ia`:
  lê a imagem in-process, chama a LLM local via `LLM_VISION_URL`, grava `AnaliseImagemIA`; fecha a parte de
  IA do **D1**; suíte 6/6 sobre Postgres). **`funcoeswhatsapp` → Python (Fase C) ✅ C.0–C.3 15/07/2026:**
  app Django `funcoeswhatsapp` — webhook (`/webhooks/whatsapp`, GET verify + POST HMAC → enfileira → `200`),
  `CanalWhatsApp` multi-tenant (resolução por `phone_number_id`, credenciais Meta por tenant), idempotência +
  estado da conversa no Redis, identidade telefone→pessoa tenant-scoped, roteador por papel e fluxos
  **diário** e **lead** rodando **in-process** (padrão da Fase B; sem JWT de serviço no caminho feliz).
  Escrita do diário unificada em `modulodiario.services.registrar_contribuicao` (web + WhatsApp). Suíte
  `funcoeswhatsapp/tests.py` **19/19 sobre Postgres** (payload/HMAC/webhook/idempotência/identidade/serviço/
  fluxos). **C.4 ✅ 15/07/2026:** servidor Node do WhatsApp **removido** (`.js`/`package.json`/`node_modules`
  do app + monorepo `backend/package.json`); sem resíduo Node no `grep`; fecha o **A2** (WhatsApp) e a parte
  WhatsApp do **D1**. **E2E ✅ 15/07/2026:** gateway passou a rotear `/webhooks/` → backend
  ([nginx.unified.conf](../infra/gateway/nginx.unified.conf)) e
  [phaseC_whatsapp_test.py](../infra/gateway/phaseC_whatsapp_test.py) **13/13 no stack vivo pelo gateway**
  (handshake GET verify/challenge, número desconhecido descartado, HMAC inválida→403, status→200, conversa
  de lead nos 3 passos → **Lead criado in-process** via worker Celery; canal demo no `seed_demo_data.py`).
  **Falta:** só o serviço da **LLM local** no compose (`LLM_VISION_URL`, em dev pelo cliente) — ver
  [plano](arquitetura/diario-ia-reintegracao.md) e [modulos/funcoeswhatsapp.md](modulos/funcoeswhatsapp.md).
- **11.4** Descomissionar os processos Node. ✅ 16/07/2026 — `funcoeswhatsapp` removido (C.4, 15/07),
  `funcoesnf` removido (11.1, 16/07, Node + bridge PHP), diretório Node do `funcoeslead` excluído
  (incl. `client_secret` OAuth local, nunca versionado) e resíduo Node do `funcoesia` limpo
  (`index/config/logger/package*` + `controllers/routes/services/prompts/middleware`; o app Django
  permanece). Zero `.js`/`package.json` no backend; `IA_SERVICE_URL` legada removida do settings
  (`manage.py check` limpo).
- **11.5** Angular → React (oportunístico, sem dependência de 11.1–11.4).

**DoD:** compose sem containers Node; os três serviços operando como Python com testes; `pip-audit`
limpo; decisão de linguagem de cada novo serviço registrada como AD em [arquitetura.md](arquitetura.md).

---

## Gaps conhecidos (resumo)

Achados das revisões técnicas com status vivo: [pendencias.md](pendencias.md).

- **Banco:** Postgres gerenciado + PITR + réplica é operação de produção; SQLite é fallback de dev —
  **Fases 8 e 10**.
- **Tenancy:** `tenant` nullable + `unique` globais + RLS não validada — **Fase 8** (calcanhar de
  Aquiles do isolamento).
- **RBAC fino / LGPD:** mascaramento de campos por papel, esquecimento, portabilidade, auditoria —
  **Fase 9**.
- **Drone:** entidades-filhas escopadas por tenant (`tenant_id` NOT NULL + gate na borda) — **✅ 8.5**;
  WebSocket e serviço→serviço — **✅ 10.8** (CONNECT STOMP autenticado + JWT de serviço backend→drone).
- **Módulos vazios:** `moduloaps`/`modulodms`/`modulopdca` —
  porte da **Fase 7** ([plano](arquitetura/migracao-v01.md)). `moduloorcamento` 🚧 ORC.0 (fundação:
  base referencial SINAPI/ORSE + adoção no catálogo) — [planta](modulos/moduloorcamento.md).
  `moduloscm` ✅ backend + frontend (23/07),
  desenho em [expansão/modulos/moduloscm.md](expansão/modulos/moduloscm.md). `modulosil` (estoque &
  logística interna) 🚧 **desenho aprovado, porte planejado** sobre um novo **catálogo-mestre de
  plataforma** (app-fundação `catalogo`, promove o `Produto` do SCM): plantas
  [modulos/modulosil.md](modulos/modulosil.md) + [modulos/catalogo.md](modulos/catalogo.md).
  `modulomaps` (dimensão espacial) ✅ **MAP.0–MAP.5 26/07/2026** — a coordenada que o sistema nunca
  teve (até aqui obra/empreendimento/fornecedor/almoxarifado tinham só `endereco` em texto, e todo o
  acervo geográfico estava preso no drone). `Local` é **fundação sem entitlement**; camadas, acervo,
  voo e rota ficam atrás de `maps`, sobre **PostGIS** — [planta](modulos/modulomaps.md). **MAP.6
  (E2E vivo pelo gateway) ✅ 27/07 — 103/103.** Falta MAP.7 (`CamadaExterna`/banco de terrenos, que é
  fronteira com a expansão).
- **Monetização / paywall (catálogo ✅ 19/07 · trava de seats/objetos ✅ 19/07; checkout sem código):**
  o modelo de planos vive **inteiro** em [payment/](../payment/README.md) — `planos.py`/`addons.py`
  (valores, editáveis pelo dono) + `regras.py` (engenharia) —, com o plano **`free`** como default.
  Aplicados hoje:
  **requisições/hora** (D23) e a **trava dura de seats e de objetos** (D24 item 2 — quotas viajam na
  claim `quotas`; objetos travam em [nucleo/quotas.py](../backend/nucleo/quotas.py), seats em
  [identity/quotas.py](../iam/identity/quotas.py); medidor em `GET /api/plano/`). A família de COGS
  (IA, NF, boleto, drone, storage) segue **declarada e inerte** por desenho — mede e cobra, não trava.
  **Atenção no cutover:** tenant sem `plano` explícito é tratado como `free` (1 seat, 2 obras).
  Falta: auto-serviço (landing → checkout → pagamento Asaas → código de ativação), medidores mensais
  de consumo com excedente, e a UI (**fase G** do [frontend.md §5.16](frontend.md)).
  Planos híbridos (planos + add-ons), **quotas** por plano (usuários,
  empreendimentos, obras, clientes, storage, processamento de drone, IA, NF, boletos), trial de 28
  dias. Vínculo **usuário↔funcionário** (seat = funcionário com login). Estudo do consultor +
  faseamento em [arquitetura/monetizacao.md](arquitetura/monetizacao.md); ABAC por objeto (acesso a
  empreendimento) é a **fatia D** do [AD-9](arquitetura/rbac-abac.md).
- **Frontend pendente:** dashboard de KPIs, CRM, drone wrapper, calendário — tabela da Fase 7 acima.
- **Operacional:** LGPD, secrets, DR, pentest — **Fase 10**; observabilidade base (logs JSON
  correlacionados + métricas Prometheus + health estendido) ✅ **10.1** (15/07); falta Grafana/alertas.
- **Deploy e configuração:** compose/env por ambiente em [deploy/](../deploy/README.md) ✅ 19/07; TLS no
  banco configurável (**D14**) ✅ 19/07 — falta validar contra um Postgres com TLS real.
- **Borda da API:** `iss`/`aud` verificados + throttling no DRF (**S8**) ✅ 19/07.
- **Limites (3 camadas — [arquitetura/rate-limiting.md](arquitetura/rate-limiting.md)):** camada 2
  (saída, token bucket por fornecedor — protege cota de terceiro e dinheiro) ✅ 19/07 (**D22**);
  camada 1 completa ✅ 19/07 (**D23**: eixo por **tenant** com teto **derivado do plano contratado**
  (claim `rate_hora` da IAM), `limit_req` de `/api/` no gateway, `X-RateLimit-*` na resposta e
  fail-open ruidoso nos quatro eixos). Camada 3 (cota por plano) 🟠 **D24 parcial** — trava de
  seats/objetos ✅ 19/07; falta consumo/checkout. O modelo de planos vive inteiro em
  [payment/](../payment/README.md) (valores + regras), com as quotas de COGS declaradas e inertes.
- **Supply chain:** varredura automatizada (pip/npm/trivy + Dependabot) ✅ **10.4** (14/07); falta
  Maven/Angular (repo do drone), `postinstall` e checklist de deps — **10.4.3/10.4.4**.
- **CI/CD:** pipeline mínima (backend/iam/frontend) ✅ **10.5.1** + gates de CVE ✅ **10.5.2** (14/07);
  **executando de fato desde 26/07** (**D26** — 3 dos 4 jobs estavam vermelhos e o do backend não rodava
  a suíte); **gate de tipo do frontend ✅ 26/07** (**D27**: `tsc -b` a zero, `Build + typecheck`
  bloqueante e o `frontend/Dockerfile` rodando `npm run build` — antes o `npx vite build` transpilava
  sem type-check e o erro não aparecia em canto nenhum). Falta build/push de imagens — **10.5.3** — e o
  lint como gate, que depende da decisão do **F12** (22 dos 23 erros são a regra `react-refresh` sobre
  os quatro kits de UI).
- **JWT em `localStorage` e em query param (iframe):** ✅ **10.6** (11/07) — access em memória + refresh
  em cookie HttpOnly; iframe do drone via postMessage (sem `?token=`).
- **Staging ausente:** validações vão direto para produção — **10.7**.
- **Superfície:** 11 serviços, 3 stacks, 2 frontends — **Fases 10 e 11**.
