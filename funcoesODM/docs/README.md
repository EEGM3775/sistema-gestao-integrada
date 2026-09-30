# FuncoesODM - Documentacao

Plataforma de fotogrametria e processamento de imagens baseada em OpenDroneMap, com frontend Angular, backend Spring Boot, PostgreSQL e NodeODM.

## Dentro do SGI

O drone é o módulo `drone` do SGI e é versionado no repositório do SGI, em `funcoesODM/`. Lá ele
**não** roda pelos scripts standalone descritos em [GETTING_STARTED.md](GETTING_STARTED.md) e
[guides/SCRIPTS.md](guides/SCRIPTS.md) — esses scripts e o `docker-compose.yml` próprio ficaram no
`ImgDrone/`, fora do git. No SGI:

- **Sobe** com o compose da plataforma: `deploy/compose/base.yml`, profile `full` (serviços
  `java-service`, `drone-nginx`, `nodeodm`, `potree-converter`, `funcoesodm-db`) — ver
  `docs/desenvolvimento.md` do SGI.
- **Entra** pelo gateway: a SPA em `/drone/`, a API em `/odm-api/` (→ `/api/v1`), o WebSocket em `/ws/`.
- **Autentica** só pela IAM do SGI (BFF: o gateway troca o cookie da sessão pelo token com
  `aud=sgi-drone`). O login local (`/api/v1/auth/login`) fica desligado
  (`APP_LOCAL_LOGIN_ENABLED=false`), e com ele as credenciais de teste do `init-db`.
- **Autoriza** pelo PDP do SGI (`security/AutorizacaoService`) — desenho em
  `docs/acesso-e-permissoes.md §10` do SGI.

## Comece aqui

- [Início rápido](GETTING_STARTED.md) - fluxo de 3 passos para abrir a aplicação
- [Setup](setup/SETUP.md) - instalação e execução manual
- [Visão geral](guides/OVERVIEW.md) - stack, arquitetura e visão do produto
- [Guia de scripts](guides/SCRIPTS.md) - start/stop/status/menu

## Setup e operação

- [SETUP.md](setup/SETUP.md) - instalação completa
- [VERIFICACAO_NODEODM.md](setup/VERIFICACAO_NODEODM.md) - validação do NodeODM
- [SETUP_DOCKER.md](setup/SETUP_DOCKER.md) - solução de problemas do Docker/Desktop
- [SETUP_COMPLETO.md](setup/SETUP_COMPLETO.md) - resumo do setup concluído

## Guias de uso

- [OVERVIEW.md](guides/OVERVIEW.md) - visão geral do projeto
- [SCRIPTS.md](guides/SCRIPTS.md) - scripts disponíveis
- [GPU_ACELERACAO.md](guides/GPU_ACELERACAO.md) - uso de GPU
- [GUIA_RAPIDO_OPCOES.md](guides/GUIA_RAPIDO_OPCOES.md) - opções NodeODM/ODM

## Referência técnica

- [OPCOES_NODEODM_COMPLETAS.md](reference/OPCOES_NODEODM_COMPLETAS.md) - opções completas do NodeODM
- [MEASUREMENT.md](reference/MEASUREMENT.md) - medições e exportação
- [STATUS_PROJETO.md](reference/STATUS_PROJETO.md) - estado geral do projeto

## Arquitetura e padrões

- [VISION.md](architecture/VISION.md) - visão arquitetural
- [BEST_PRACTICES.md](architecture/BEST_PRACTICES.md) - padrões e convenções
- [convencoes.md](convencoes.md) - regras práticas do projeto

## Solução de problemas

- [NODEODM_SOLUTION.md](troubleshooting/NODEODM_SOLUTION.md) - correção do NumPy/GDAL
- [VERIFICACAO_CORRECOES.md](troubleshooting/VERIFICACAO_CORRECOES.md) - correções aplicadas

## Planejamento e contexto

- [roadmap.md](roadmap.md) - o que ainda falta fazer
- [CONTEXT.md](CONTEXT.md) - contexto completo para sessões com IA
- [TODOODM.md](development/TODOODM.md) - histórico de tarefas e sessões

## Domínios

- [medicoes.md](dominios/medicoes.md) - medições e exportação
- [gcp.md](dominios/gcp.md) - GCP e editor visual
- [nodeodm.md](dominios/nodeodm.md) - processamento e Dockerfile
- [gpu.md](dominios/gpu.md) - aceleração GPU
- [arquitetura.md](dominios/arquitetura.md) - decisões arquiteturais

## Para desenvolvedores

Antes de alterar código, leia:

1. [CONTEXT.md](CONTEXT.md)
2. [BEST_PRACTICES.md](architecture/BEST_PRACTICES.md)
3. O domínio específico da tarefa

## Estrutura
```
docs/
├── GETTING_STARTED.md
├── CONTEXT.md
├── roadmap.md
├── convencoes.md
├── setup/
├── guides/
├── reference/
├── architecture/
├── troubleshooting/
├── development/
└── dominios/
```

## Ajuda rapida

- Se nao encontrar algo, pesquise no VS Code com Ctrl+Shift+F.
- Se estiver em duvida sobre o estado do projeto, veja [CONTEXT.md](CONTEXT.md).
- Se quiser saber o que falta fazer, veja [roadmap.md](roadmap.md).

## Licenca

- FuncoesODM: proprietario (camada de aplicacao)
- OpenDroneMap/NodeODM: GPLv3 (componentes base)
