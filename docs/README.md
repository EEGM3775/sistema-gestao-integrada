# Documentação — Sistema de Gestão Integrada

Plataforma **SaaS multi-tenant e modular** para **construção civil / incorporação imobiliária**:
empreendimentos, obras, clientes, fornecedores, financeiro e RH, com módulos **vendidos à la carte**,
identidade central (IAM) e SSO. A arquitetura é de **microsserviços federados** (backend Django + shell
React + módulo de drone Spring/Angular + microsserviços Node), unificados por um gateway.

## Por onde começar

A documentação tem **quatro naturezas** — saber qual você procura já resolve metade da busca:

> 🏗️ **Analogia de obra:** a **planta** descreve o sistema inteiro (como é/será, sem status);
> o **status** diz o que está pronto, o que falta e o que está quebrado;
> o **histórico** é o diário de obra (o que aconteceu, quando e por quê);
> a **estratégia** é o plano diretor (o que a plataforma deve se tornar).

### 📐 Planta — como o sistema é

| Quero entender… | Documento |
|---|---|
| **A arquitetura** — planta baixa (visão macro + diagrama) | [arquitetura.md](arquitetura.md) |
| **A arquitetura em detalhe** — pranchas executivas (auth-sso, dados-e-tenancy, serviços, deploy, lixo, migração v01) | [arquitetura/](arquitetura/README.md) |
| **O domínio de negócio** — como empreendimento↔obra↔cliente↔financeiro↔RH se ligam | [dominio.md](dominio.md) |
| **O modelo de acesso** — entitlement de módulo + RBAC, genérico por módulo | [acesso-e-permissoes.md](acesso-e-permissoes.md) |
| **Cada módulo** do backend em detalhe | [modulos/README.md](modulos/README.md) |
| **O frontend** (shell React) — design system, páginas, rotas, dados | [frontend.md](frontend.md) |
| **A identidade visual** (Sistema Malha: marca, cor, tipografia, voz — todas as superfícies) | [identidade-visual.md](identidade-visual.md) |
| **As convenções de código do frontend** (obrigatórias para desenvolver) | [frontend-convencoes.md](frontend-convencoes.md) |
| **Rodar / desenvolver** a plataforma | [desenvolvimento.md](desenvolvimento.md) |

### 📊 Status — o que está pronto, o que falta

| Quero saber… | Documento |
|---|---|
| **Status das fases + plano** (fases 0–11, módulos, gaps) | [roadmap.md](roadmap.md) |
| **O que está quebrado ou em risco** — achados de revisão em aberto, priorizados | [pendencias.md](pendencias.md) |

### 📜 Histórico — o que aconteceu, quando

Entregas datadas, bugs corrigidos e decisões vivem no **histórico do git** (`git log`), não em
documento versionado, quando for solicitado fazer o git.

### 🧭 Estratégia — o que a plataforma deve se tornar

| Quero saber… | Documento |
|---|---|
| **Visão, ecossistema, novos módulos, rede/marketplaces, monetização e o plano de 5 anos** | [expansão/](expansão/README.md) |

Propostas — sem status nem compromisso; quando aprovadas, **graduam** para o
[roadmap.md](roadmap.md) e para as plantas.

## Os serviços

| Serviço | Stack | Papel |
|---|---|---|
| **IAM** ([iam/](../iam/)) | Django | Autoridade única de identidade; emite/assina os JWT |
| **backend** ([backend/](../backend/)) | Django + DRF | Resource server; módulos de negócio |
| **Shell** ([frontend/](../frontend/)) | React + Vite | UI do app; login na IAM e injeção de token |
| **funcoesODM** ([ImgDrone/funcoesODM/](../ImgDrone/funcoesODM/)) | Spring + Angular | Drone/fotogrametria; produto destacável vendável sozinho |
| **Node** | Node.js | `funcoesnf`, `funcoeswhatsapp` + worker de `funcoesia` (em descontinuação — Fase 11; `funcoeslead` já absorvido) |
| **Gateway** ([infra/gateway/](../infra/gateway/)) | Nginx | Domínio único (:8090) |

## Status do roadmap (resumo)

| Fase | Tema | Status |
|---|---|---|
| 0 | Fundação (banco, IAM, multi-tenancy no backend) | ✅ |
| 1 | SSO ponta a ponta (entitlement por módulo) | ✅ |
| 2 | UI integrada (gateway, domínio único) | ✅ |
| 3 | Vínculo drone ↔ obra/empreendimento | ✅ |
| 4 | Deploy unificado (`docker compose --profile full`) | ✅ |
| 5 | Endurecimento — RS256/JWKS + borda | ✅ núcleo; operacionais pendentes |
| 6 | Consolidação de identidade & RBAC de plataforma | ✅ |
| 7 | Migração v01 → v02 (frontend + backend dos módulos) | 🚧 em andamento |

Detalhe em [roadmap.md](roadmap.md).

## Como rodar (resumo)

```bash
cp .env.example .env
bash infra/keys/generate.sh                 # par de chaves RSA do JWT (RS256)
docker compose --profile full up -d         # sobe os 11 serviços
# abra http://localhost:8090/
# → Landing page → "Acessar" → login demo/demo123 → Hub de módulos
```

Setup completo (venvs, portas, seed) em [desenvolvimento.md](desenvolvimento.md).

## Convenções da documentação

- **Cada documento tem UMA natureza** (planta · status · estratégia) e não mistura as outras:
  - status/plano → **só** no [roadmap.md](roadmap.md) e [pendencias.md](pendencias.md);
  - a planta (arquitetura, módulos, frontend) descreve o sistema inteiro **sem** status nem datas;
  - a estratégia ([expansão/](expansão/README.md)) propõe o futuro **sem** virar planta nem status
    até graduar.
- **Uma revisão técnica só** — achados e backlog de ideias vivem consolidados em
  [pendencias.md](pendencias.md); não criar novas pastas de laudo versionadas.
- **O que é de plataforma** (arquitetura, domínio, acesso, módulos do backend) fica em `docs/`.
- **O drone** mantém a sua própria `docs/` ([ImgDrone/funcoesODM/docs/](../ImgDrone/funcoesODM/docs/)) —
  é produto separado e autossuficiente; aqui só o referenciamos.
- Arquivos **curtos** (alvo ~400 linhas), um assunto por arquivo, para leitura barata (humanos e LLMs).

### Regra de sincronização — nunca deixar docs desatualizados

Toda implementação significativa exige atualização imediata dos documentos afetados.
Ver regra completa em [CLAUDE.md](../CLAUDE.md).
