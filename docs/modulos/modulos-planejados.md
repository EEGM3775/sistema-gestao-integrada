# Módulos planejados (placeholders)

> Diretórios de app que **existem mas estão vazios** (sem `models.py`/`views.py`). São intenções de
> produto, ainda não implementadas. Quando forem construídos, devem seguir o **contrato de módulo
> novo** ([../acesso-e-permissoes.md](../acesso-e-permissoes.md) §7).

## Lista

| App | Nome pretendido (provável) |
|---|---|
| `moduloaps` | APS — acompanhamento/planejamento de serviços |
| `modulodms` | DMS — gestão de documentos |
| `modulopdca` | PDCA — ciclo de melhoria contínua |
| `modulomaps` | Maps — geolocalização/mapas |

> `moduloscm` (SCM — suprimentos) **saiu da lista de placeholders**: porte iniciado (fatia 1 ✅
> 20/07/2026 — catálogo + centro de custo). Desenho e faseamento em
> [../expansão/modulos/moduloscm.md](../expansão/modulos/moduloscm.md); status no
> [../roadmap.md](../roadmap.md) (Fase 7).

> `modulosil` (SIL — estoque & logística interna) **saiu da lista de placeholders**: desenho
> aprovado (Estoque + logística interna ampla, sobre um **catálogo-mestre de plataforma** novo —
> app-fundação `catalogo`). Plantas em [modulosil.md](modulosil.md) + [catalogo.md](catalogo.md);
> expansão em [../expansão/modulos/modulosil.md](../expansão/modulos/modulosil.md); status no
> [../roadmap.md](../roadmap.md) (Fase 7).

> Os nomes acima são inferidos pela sigla; confirmar a intenção com o produto antes de implementar.

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
