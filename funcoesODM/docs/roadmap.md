# Roadmap - FuncoesODM

> Plano de evolucao do produto. Para bugs ativos e investigacao detalhada, use [development/TODOODM.md](development/TODOODM.md).

## Status geral

| Fase | Descricao | Status |
|------|-----------|--------|
| Fase 1 | Fundacao e arquitetura base | Concluida |
| Fase 2 | PoC vertical com NodeODM | Concluida |
| Fase 3 | Modulos de engenharia iterativos | Em andamento |
| Fase 4 | Preparacao para producao | Pendente |
| Fase 5 | Nivel profissional | Roadmap |

## Agora

Fase 3 concluida (M3 com arquitetura corrigida na sessao 19). Proxima prioridade: acabamento de produto (responsividade, temas, i18n).

## Modulos da Fase 3 — todos concluidos

| Modulo | Status |
|--------|--------|
| M1: NDVI / VARI | Concluido |
| M2: Viewer 3D (Three.js + Potree streaming) | Concluido e testado |
| M3: Anotacoes Colaborativas | Concluido (sessoes 18-19, arquitetura corrigida) |

## Proximas entregas

## Acabamento de produto

- Responsividade avancada
- Dark/Light mode
- i18n PT-BR + EN
- Testes automatizados
- Biblioteca de icones
- PWA / offline
- Settings / Preferencias

## Producao

- CI/CD
- Testes de carga / performance
- HTTPS, dominio e variaveis de producao
- Swagger / OpenAPI
- Backup automatizado do banco
- Monitoramento e alertas
- Hardening de multi-tenancy
- Plano de licenciamento SaaS

## Referencias uteis

- [CONTEXT.md](CONTEXT.md) - estado atual do projeto
- [development/TODOODM.md](development/TODOODM.md) - bugs ativos e historico de sessoes