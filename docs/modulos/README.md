# Índice de módulos

> Todos os módulos da plataforma. **Entitlement** = código exigido no claim `modules` do JWT
> (`RequireModule`); em branco = app base, disponível a qualquer usuário autenticado do tenant. Modelo
> de acesso em [../acesso-e-permissoes.md](../acesso-e-permissoes.md); ligações de domínio em
> [../dominio.md](../dominio.md).

## backend — apps Django

| Módulo | Entitlement | Doc | O que faz |
|---|---|---|---|
| `empreendimentos` | — (base) | [empreendimentos.md](empreendimentos.md) | Empreendimentos, contas bancárias, custos |
| `obras` | — (base) | [obras.md](obras.md) | Obras, etapas, documentos |
| `clientes` | — (base) | [clientes.md](clientes.md) | Clientes-compradores, aquisições, contratos |
| `fornecedores` | — (base) | [fornecedores.md](fornecedores.md) | Fornecedores e catálogo de produtos/serviços |
| `catalogo` | — (base) | [catalogo.md](catalogo.md) | **Item mestre de plataforma** (bem/serviço/equip./ativo/composição) — compartilhado por SCM, SIL e futuros (planejado, Fase 7) |
| `modulodiario` | — (base)¹ | [modulodiario.md](modulodiario.md) | Diário de obra + mídia → análise de IA |
| `moduloerp` | **`erp_financeiro`** (+ papel `financeiro`) | [moduloerp.md](moduloerp.md) | Financeiro: contas a pagar/receber, NF, boletos, centros de custo |
| `rh` | **`rh`** | [rh.md](rh.md) | Funcionários, cargos, folha, dados médicos/bancários |
| `modulocrm` | **`crm`** | [modulocrm.md](modulocrm.md) | Funil: leads → contas → oportunidades |
| `moduloscm` | **`scm`** | [moduloscm.md](moduloscm.md) | Suprimentos: catálogo → demanda → cotação → pedido → recebimento (backend ✅; sem UI) |
| `modulosil` | **`sil`** | [modulosil.md](modulosil.md) | Estoque & logística interna (full-stack ✅): saldo valorado, requisição, inventário, **EPI/NR-6**, **ferramentaria**, **curva ABC**, **aplicado por obra/etapa** (Operação × Gestão) |
| `moduloorcamento` | **`orcamento`** | [moduloorcamento.md](moduloorcamento.md) | Orçamento de obra: **base referencial de plataforma** (SINAPI/ORSE, importada por comando) + adoção no catálogo do tenant ✅; planilha, composição/BDI, curva S e as quatro colunas (orçado × comprometido × aplicado × realizado) 🚧 |
| `moduloapi` | — (base) | [moduloapi.md](moduloapi.md) | Credenciais de APIs externas (Google OAuth) |
| `nucleo` | — (base) | [nucleo.md](nucleo.md) | Identidade/tenancy/auditoria (espelho da IAM) |
| `modulocalendar` | — (base) | [modulocalendar.md](modulocalendar.md) | Eventos/tarefas de calendário |
| `funcoesia` | — (base) | [funcoesia.md](funcoesia.md) · [análise IA](funcoesia-analise-ia.md) | Análise de imagens por IA |
| `funcoescobrancas` | (integração do `moduloerp`) | [funcoescobrancas.md](funcoescobrancas.md) | Adaptador Python (Celery + webhook) do gateway **Asaas** — boleto/PIX/cartão (sandbox→real; MVP 08/06/2026) |

¹ `modulodiario` usa `IsResponsavelTecnicoDaObra` (permissão por objeto), não `RequireModule`.

## Microsserviços Node (acionados pelo backend)

> Stack em **descontinuação** (Fase 11 do [roadmap](../roadmap.md)): nenhuma feature nova nasce
> aqui. A comunicação Node→backend usa a auth legada, quebrada desde a Fase 6 — ver
> [../pendencias.md](../pendencias.md) (achado D1; confirmado por teste em 03/07/2026).

| Serviço | Doc | O que faz |
|---|---|---|
| `funcoesnf` | [funcoesnf.md](funcoesnf.md) · [integração PHP](funcoesnf-integracao-php.md) | Emissão de NF-e/NFS-e (NFE.io → **Asaas** sandbox→real) |
| `funcoeslead` | [funcoeslead.md](funcoeslead.md) | **Absorvido pelo backend** (Fase 11.2): conversão/score/agenda/notificações em `modulocrm`/`modulocalendar` |
| `funcoeswhatsapp` | [funcoeswhatsapp.md](funcoeswhatsapp.md) | Bot de WhatsApp (diário de obra por chat) |
| worker de `funcoesia`² | [funcoesia.md](funcoesia.md) | Chama o Google Gemini na análise de imagens |

² `funcoesia` é **híbrido**: app Django (`/api/ia/`) + worker Node no mesmo diretório.

## Produto destacável (stack própria)

| Produto | Entitlement | Doc |
|---|---|---|
| **funcoesODM** (drone, Spring + Angular) | **`drone`** | [../../ImgDrone/funcoesODM/docs/](../../ImgDrone/funcoesODM/docs/) |

## Planejados (placeholders vazios)

`moduloprancheta` (ex-`moduloaps`), `modulodms`, `modulopdca`, `modulomaps` — ver
[modulos-planejados.md](modulos-planejados.md). (`moduloscm` **saiu** desta lista: backend portado —
[moduloscm.md](moduloscm.md); `modulosil` **saiu**: porte planejado — [modulosil.md](modulosil.md).)
