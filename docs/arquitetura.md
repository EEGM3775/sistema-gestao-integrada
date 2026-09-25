# Arquitetura — Plataforma SaaS de Gestão Integrada

> A **planta** do sistema: o projeto autoritativo de **como a plataforma é** — todos os serviços e
> componentes como um desenho único. Esta página é a **planta baixa** (visão macro + diagrama); o
> detalhamento de execução está nas **pranchas** em [arquitetura/](arquitetura/). O acompanhamento de
> obra (o que já foi entregue, o que falta) é o [roadmap.md](roadmap.md).
>
> **Stack:** IAM e backend em **Django 5.2 + DRF** (SimpleJWT no IAM); shell em **React 19 + Vite + TS**;
> drone (`funcoesODM`) em **Spring Boot + Angular + NodeODM/Potree**; microsserviços em **Node.js**;
> borda em **Nginx**; dados em **PostgreSQL 16** + **Redis**. Orquestração:
> [docker-compose.yml](../docker-compose.yml) (`--profile full` → 11 serviços).

## 1. Visão geral

Plataforma **SaaS multi-tenant** com **módulos vendidos à la carte**, para **construção civil /
incorporação imobiliária** (empreendimentos, obras, clientes-compradores, financeiro, RH). Vários
produtos compartilham uma identidade comum, mas podem ser contratados de forma independente — em
especial o **funcoesODM** (drone), que pode ser vendido sozinho.

Três requisitos moldam toda a fundação:

1. **Multi-tenant** — cada empresa-cliente enxerga **somente** os seus dados.
2. **RBAC intra-tenant** — dentro de uma empresa, papéis diferentes têm acessos diferentes.
3. **Entitlements por módulo** — um tenant (e cada usuário dele) acessa só os módulos contratados.

Como o sistema lida com **valor financeiro e dados pessoais**, a **robustez do banco** é requisito de
primeira classe, não detalhe de deploy.

## 2. Decisões de arquitetura (registradas)

| #    | Decisão                                                                                                                                                                                     | Justificativa                                                                                                                                                                                                                    |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AD-1 | **funcoesODM integra como microsserviço federado** — mantém sua stack (Spring + Angular + NodeODM/Potree); **não** é reescrito.                                             | Aplicação madura; reescrever desperdiçaria trabalho e introduziria risco.                                                                                                                                                     |
| AD-2 | **SSO via JWT** (RS256/JWKS; HS256 como fallback).                                                                                                                                     | Login único; só a IAM assina.                                                                                                                                                                                                  |
| AD-3 | **Multi-tenant** com isolamento por tenant + **RBAC intra-tenant**.                                                                                                              | Requisito de negócio e validade legal entre clientes.                                                                                                                                                                           |
| AD-4 | **Entitlements por módulo** (assinatura tenant↔módulo e usuário↔módulo).                                                                                                         | Permite vender módulos à la carte (ex.: funcoesODM isolado).                                                                                                                                                                   |
| AD-5 | **IAM é um serviço separado** (não dentro do Django).                                                                                                                               | Nenhum produto é dono da identidade; máxima independência.                                                                                                                                                                    |
| AD-6 | **PostgreSQL** como banco de registro, endurecido (cluster gerenciado, backups, PITR, réplica, roles de menor privilégio).                                                           | Valor financeiro exige ACID, concorrência, constraints e recuperação.                                                                                                                                                         |
| AD-7 | **Cada produto tem banco próprio** (IAM, backend, funcoesODM).                                                                                                                        | Cada um é unidade destacável/vendável; isolamento de falhas.                                                                                                                                                                  |
| AD-8 | **Estratégia de consolidação de stack**: Python e JAVA são a linguagem de aplicação padrão; Java permanece em recursos especificos; Node.js e PHP são eliminados gradualmente. | Cada linguagem adicional multiplica o custo de manutenção (auth reimplementada, builds separados, runtimes distintos). Java permanece onde Python tem limitação concreta. Ver[Seção 6](#6-estratégia-de-stack-tecnológica). |
| AD-9 | **Camada 2 (dentro do tenant) evolui para RBAC + ABAC**: catálogo **global** de permissões (em código) + **papéis por tenant** que as agrupam + granularidade **ação/campo** (mascaramento de PII). Endpoints checam **permissão**, não nome de papel. *(Proposto; desenho em [arquitetura/rbac-abac.md](arquitetura/rbac-abac.md).)* | Checar nome de papel é imprevisível e inseguro (papel homônimo vazio passa) e não tem granularidade ver/editar/campo. O catálogo dá previsibilidade mesmo com papéis por tenant; o mascaramento de campo atende à LGPD (Fase 9). |

## 3. Topologia de serviços

```
                         ┌─────────────────────────────┐
                         │   Nginx Gateway (:8090)      │
                         │ / → React   /api → Django    │
                         │ /auth → IAM /drone → Angular │
                         │ /odm-api → Java  /ws → Java  │
                         └──────────────┬──────────────┘
            ┌───────────────┬───────────┼───────────────┬───────────────┐
     ┌──────▼─────┐  ┌──────▼─────┐  ┌──▼──────┐  ┌──────▼──────┐  ┌─────▼──────┐
     │   IAM      │  │  backend   │  │ React   │  │ funcoesODM  │  │  Node µsvc │
     │ (auth/     │  │ Django+DRF │  │ (app UI)│  │ Java + Ang. │  │ nf/lead/wa │
     │ tenants/   │  │            │  │         │  │ +NodeODM/   │  │            │
     │ RBAC/      │  │            │  │         │  │  Potree     │  │            │
     │ entitle.)  │  │            │  │         │  │             │  │            │
     └─────┬──────┘  └─────┬──────┘  └─────────┘  └──────┬──────┘  └────────────┘
           │ emite JWT     │ valida JWT                  │ valida JWT
     ┌─────▼──────┐  ┌─────▼──────┐               ┌──────▼──────┐
     │  IAM DB    │  │ backend DB │               │ funcoesODM  │
     │ (Postgres) │  │ (Postgres) │               │   DB (PG)   │
     └────────────┘  └────────────┘               └─────────────┘
              Cluster PostgreSQL (iam_db + erp_db + spicedb_db)  +  Redis
```

**Quem é dono do quê:**

- **IAM** ([iam/](../iam/)) — única autoridade de identidade. Dona de tenants, usuários,
  papéis/permissões e entitlements. Emite e assina os JWT.
- **backend (Django)** ([backend/](../backend/)) — **resource server**: valida o JWT da IAM e aplica
  isolamento de tenant + RBAC + entitlement nas queries. Apps de negócio em [modulos/](modulos/README.md).
  Toda pergunta "pode?" passa por um lugar só ([nucleo/autorizacao.py](../backend/nucleo/autorizacao.py)).
- **PDP (SpiceDB)** — responde "o que esta pessoa pode fazer?" a partir de relações que **só a IAM
  escreve**; não autentica ninguém. Decide módulo a módulo, com o token conferido em sombra até a
  virada. Desenho em [acesso-e-permissoes.md §10](acesso-e-permissoes.md) (construído: §10.15).
- **funcoesODM (Java/Angular)** ([ImgDrone/funcoesODM/](../ImgDrone/funcoesODM/)) — produto destacável;
  valida o JWT, exige o entitlement `drone`, escopa por tenant, faz **JIT provisioning**.
- **Microsserviços Node** (`funcoesnf`, `funcoeswhatsapp` + o worker embutido em `funcoesia`) —
  acionados pelo backend; validam o JWT quando expõem endpoints. Stack em descontinuação
  (AD-8 / Fase 11; o `funcoeslead` já foi absorvido pelo backend na 11.2).

## 4. Macro por área (e onde está a prancha executiva)

Cada área tem uma **prancha** com o detalhamento construtivo:

- **Identidade & SSO** — a IAM é a única autoridade; todos validam o JWT (RS256/JWKS) e leem as claims
  (`sub`, `tenant_id`, `roles`, `modules`). Login único; o shell injeta o token no drone.
  → [arquitetura/auth-sso.md](arquitetura/auth-sso.md). Política de acesso (entitlement + RBAC) em
  [acesso-e-permissoes.md](acesso-e-permissoes.md).
- **Dados & multi-tenancy** — um banco por produto; toda entidade de negócio herda `tenant`
  (`TenantScopedModel`); isolamento em duas camadas (mixin de aplicação + RLS no Postgres).
  → [arquitetura/dados-e-tenancy.md](arquitetura/dados-e-tenancy.md). Entidades de negócio em
  [dominio.md](dominio.md).
- **Serviços & integrações** — contratos entre serviços (gateway, APIs, eventos) e os fluxos de
  sequência dos casos-chave (emitir NF, criar projeto de drone vinculado à obra).
  → [arquitetura/servicos-e-integracoes.md](arquitetura/servicos-e-integracoes.md).
- **Deploy & segurança** — containers, rede, volumes, portas, gateway de borda, modelo de ameaças,
  segredos, escala e DR. → [arquitetura/deploy-e-seguranca.md](arquitetura/deploy-e-seguranca.md).
  Como subir/desenvolver em [desenvolvimento.md](desenvolvimento.md).

## 6. Estratégia de stack tecnológica

> Decisão registrada em **AD-8**. Toda adição de linguagem multiplica o custo operacional:
> JWT reimplementado em mais um lugar, mais um runtime, mais uma cadeia de build, mais um conjunto
> de dependências para auditar.

### Stack alvo (consolidada)

| Camada               | Tecnologia                                           | Justificativa                                                                                            |
| -------------------- | ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Backend              | **Python — Django + DRF + Celery + Channels** | Domínio rico em dados, IA, LGPD; ORM + migrações + admin + signals em uma linguagem                   |
| Backend              | **Java — Spring Boot**                        | Especifico caso a caso                                                                                   |
| Frontend shell (app) | **TypeScript — React + Vite**                 | Componentes de negócio, auth, navegação condicional por entitlement                                   |
| Frontend de drone    | **TypeScript — Angular**                      | Mantido enquanto o drone não precisar de reescrita; absorver no React quando houver manutenção pesada |
| Banco de dados       | **PostgreSQL 16**                              | ACID, RLS nativa (isolamento multi-tenant), PITR, constraints, UUID                                      |
| Cache / broker       | **Redis**                                      | Celery + cache Django; já presente no stack                                                             |
| Gateway              | **Nginx**                                      | Roteamento de borda, rate limiting, headers de segurança                                                |
| Fotogrametria        | **NodeODM + Potree**                           | Processo externo; Python e Java apenas orquestram via HTTP                                               |

### O que eliminar e como

| Linguagem         | Serviço(s)                                         | Destino                                                                           | Quando                                                   |
| ----------------- | --------------------------------------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------- |
| **Node.js** | `funcoesnf`, `funcoeswhatsapp`, worker de `funcoesia` (`funcoeslead` já absorvido — 11.2) | Celery tasks no backend (Redis e Celery já existem)    | Próxima manutenção significativa em qualquer um deles |
| **PHP**     | `backend/funcoesnf/php-support`                   | Consolidar no serviço Python de emissão de NF                                   | Junto com a migração do Node                           |

### Regra para novos módulos e serviços

```
Novo módulo de negócio   → Django app (Python)
Nova integração externa  → Celery task (Python)
Novo webhook/bot         → Django view + Celery (Python)
Nova feature de IA       → Python (ecossistema sem equivalente)
Nova feature de drone    → Spring Boot (Java), se não couber no backend
Novo componente de UI    → React (TypeScript)
```

**Nunca** criar um novo microsserviço Node.js ou um novo serviço Java para lógica que o Django cobre.

### Por que Java fica (e não cresce)

Java é superior em concorrência CPU-bound e tem tipagem estática verificada em compile-time.
Para o funcoesODM esses atributos importam: WebSocket com múltiplas conexões simultâneas de
processamento, integração com NodeODM que gera workloads pesados, e pipeline Potree que
demanda coordenação fina. Python resolve o mesmo problema com Django Channels + Celery, mas
exigiria reescrita de código maduro sem ganho funcional imediato — custo não justificado agora.

O critério para manter Java é **limitação concreta e mensurável**, não preferência geral.
Para o backend (I/O bound, domínio de negócio, IA), essa limitação não existe.

---

## 5. Mapa de documentos

| Camada                           | Documento                                                                                                                                                        |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Planta baixa (esta página)      | `arquitetura.md`                                                                                                                                               |
| Pranchas executivas              | [arquitetura/](arquitetura/README.md) (auth-sso · dados-e-tenancy · servicos-e-integracoes · deploy-e-seguranca)                                                 |
| Migração v01 → v02            | [arquitetura/migracao-v01.md](arquitetura/migracao-v01.md) (documento único: dados, cutover, backend e frontend) |
| Domínio de negócio             | [dominio.md](dominio.md)                                                                                                                                            |
| Acesso & permissões (política) | [acesso-e-permissoes.md](acesso-e-permissoes.md)                                                                                                                    |
| Módulos                         | [modulos/README.md](modulos/README.md)                                                                                                                              |
| Frontend                         | [frontend.md](frontend.md)                                                                                                                                          |
| Desenvolvimento / como rodar     | [desenvolvimento.md](desenvolvimento.md)                                                                                                                            |
| Acompanhamento de obra (status)  | [roadmap.md](roadmap.md)                                                                                                                                            |
