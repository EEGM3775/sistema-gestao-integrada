# Sistema de Gestão Integrada (SGI)

Plataforma **SaaS multi-tenant e modular** para **construção civil / incorporação imobiliária** —
empreendimentos, obras, clientes, fornecedores, financeiro e RH — com **módulos vendidos à la carte**,
identidade central (IAM) e SSO. Arquitetura de **microsserviços federados**: backend (Django + DRF) +
shell React + módulo de drone `funcoesODM` (Spring + Angular) + microsserviços Node, unificados por um
gateway Nginx.

> 📚 **A documentação vive em [`docs/`](docs/README.md)** — comece por lá:
> [arquitetura](docs/arquitetura.md) · [domínio de negócio](docs/dominio.md) ·
> [acesso & permissões](docs/acesso-e-permissoes.md) · [módulos](docs/modulos/README.md) ·
> [frontend](docs/frontend.md) · [desenvolvimento](docs/desenvolvimento.md) ·
> [roadmap & status](docs/roadmap.md) · [pendências](docs/pendencias.md).

## Como rodar

```bash
cp deploy/env/dev.env.example .env
bash infra/keys/generate.sh                 # par de chaves RSA do JWT (RS256)
docker compose --profile full up -d         # sobe os 11 serviços
# abra http://localhost:8090/  → login demo/demo123
```

Setup local (venvs, portas, seed) em [docs/desenvolvimento.md](docs/desenvolvimento.md).

## Estrutura do repositório

| Caminho | O quê |
|---|---|
| [iam/](iam/) | Serviço de identidade (autoridade única; emite os JWT) |
| [backend/](backend/) | backend em Django/DRF (resource server) — apps de negócio |
| [frontend/](frontend/) | Shell React (UI do app) |
| [ImgDrone/funcoesODM/](ImgDrone/funcoesODM/) | Módulo de drone (produto destacável; docs próprias) |
| [infra/](infra/) | Gateway Nginx, chaves do JWT, init do Postgres |
| [docs/](docs/README.md) | Documentação da plataforma |

## Modelo de acesso

A identidade é **uma só: a IAM**. Cada serviço apenas valida o JWT (RS256/JWKS) e aplica três níveis
ortogonais: **autenticação** (SSO), **entitlement de módulo** (a empresa contratou? o usuário pode?) e
**RBAC** por papel — sempre com **isolamento por tenant**. Detalhe em
[docs/acesso-e-permissoes.md](docs/acesso-e-permissoes.md).

> ⚠️ **Nota de segurança (histórico):** versões anteriores tinham endpoints sem autenticação e sem
> filtro por tenant. A fundação de segurança foi endereçada nas Fases 0 e 6 (resource server da IAM,
> `TenantScopedViewSetMixin`, `RequireModule`/`RequireRole`). O estado atual e as pendências (ex.:
> mascaramento de campos por papel, LGPD) estão em [docs/roadmap.md](docs/roadmap.md) e
> [docs/acesso-e-permissoes.md](docs/acesso-e-permissoes.md).
