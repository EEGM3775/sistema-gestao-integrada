# FuncoesODM - Visão Geral do Projeto

Plataforma SaaS para processamento de imagens aéreas e análise topográfica, construída sobre o ecossistema OpenDroneMap.

## Início Ultra-Rápido

**Windows:** Duplo clique em `start.bat` ou `menu.bat`
**Linux/WSL:** Execute `./start.sh` ou `./menu.sh`

**[Guia de Início Rápido Completo](../GETTING_STARTED.md)**

---

## Visão Geral

Aplicação moderna de fotogrametria focada em engenharia civil, com arquitetura desacoplada:
- **Frontend**: Angular 18+ com signals
- **Backend**: Java Spring Boot + PostgreSQL
- **Processamento**: NodeODM/ClusterODM (via API)

**[Visão Arquitetural Completa](VISION.md)**

---

## Quick Start

### Pré-requisitos
```bash
- Docker & Docker Compose
```

### Iniciar Ambiente (Modo Fácil - RECOMENDADO)

**Windows:**
```bash
# Duplo clique em start.bat
# OU execute no PowerShell:
.\start.ps1
```

**Linux/WSL:**
```bash
./start.sh
```

Os scripts fazem tudo automaticamente:
- Verificam Docker
- Criam arquivo .env
- Iniciam todos os containers
- Aguardam serviços ficarem prontos
- Abrem aplicação no navegador

**Para parar:** Duplo clique em `stop.bat` ou execute `./stop.sh`

**[Documentação Completa dos Scripts](SCRIPTS.md)**

### Modo Manual (Para Desenvolvimento)
```bash
docker-compose up -d
cd frontend && npm install && npm start
cd backend/java-service && ./mvnw spring-boot:run
```

**[Guia Completo de Setup](../setup/SETUP.md)**

---

## Estrutura do Projeto

```
funcoesODM/
├── frontend/          # Angular 18+ (Signals, Standalone)
│   ├── src/app/
│   │   ├── core/     # Guards, Interceptors, Services
│   │   ├── features/ # Módulos de funcionalidade
│   │   └── shared/   # Componentes compartilhados
│   └── ...
├── backend/
│   └── java-service/ # Spring Boot API
├── docs/             # Documentação organizada
│   ├── setup/
│   ├── guides/
│   ├── reference/
│   └── architecture/
├── scripts/          # Scripts utilitários
│   └── test/        # Scripts de teste
├── init-db/         # SQL de inicialização
└── docker-compose.yml
```

---

## Recursos Principais

### Interface Moderna
- Dashboard interativo com visualização de projetos
- Editor de mapas com Leaflet
- Visualizador 3D de modelos
- Upload drag-and-drop de imagens

### Processamento Avançado
- Integração completa com NodeODM/ClusterODM
- Suporte a GPU (NVIDIA)
- Processamento distribuído
- Configurações avançadas de qualidade

### Análise Topográfica
- Geração de Ortofoto
- DSM/DTM
- Cálculo de volumes
- Curvas de nível

### Segurança
- Autenticação JWT
- Multi-tenancy
- Permissões granulares

---

## Stack Tecnológica

### Frontend
- **Framework**: Angular 18+ (Standalone Components)
- **State**: Signals & RxJS
- **UI**: TailwindCSS-like custom styles
- **Maps**: Leaflet
- **3D**: Three.js (planejado)

### Backend
- **API**: Spring Boot 3.2+
- **Database**: PostgreSQL 15+
- **Auth**: JWT
- **Storage**: MinIO (S3-compatible)

### Infraestrutura
- **Container**: Docker & Docker Compose
- **Proxy**: Nginx
- **Processing**: NodeODM + ClusterODM

---

## Testes

### Frontend
```bash
cd frontend
npm test           # Unit tests
npm run e2e        # E2E tests
```

### Backend
```bash
cd backend/java-service
./mvnw test
```

### Integração
```bash
cd scripts/test
./test-auth.sh     # Testa autenticação
./test-jwt.sh      # Testa JWT
./test-login.sh    # Testa login
```

---

## Contribuindo

1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/MinhaFeature`)
3. Commit suas mudanças (`git commit -m 'Adiciona MinhaFeature'`)
4. Push para a branch (`git push origin feature/MinhaFeature`)
5. Abra um Pull Request

### Regras Importantes de Desenvolvimento

**REGRA CRÍTICA:** Não use emojis em código

NÃO adicione emojis em scripts PowerShell, Batch, Shell ou código fonte. USE marcadores ASCII:
- `[OK]` - Sucesso
- `[ERRO]` - Erro
- `[INFO]` - Informação
- `[AVISO]` - Aviso

**Motivo**: Emojis causam erros de parser no PowerShell e problemas de encoding

Encoding de Arquivos:
- PowerShell (.ps1): ASCII ou UTF-8 **sem BOM**
- Batch (.bat): ASCII ou Windows-1252
- Shell (.sh): UTF-8 sem BOM
- TypeScript/Java: UTF-8

Ver [BEST_PRACTICES.md](../architecture/BEST_PRACTICES.md) para mais diretrizes.

---

## Licença

- **FuncoesODM**: Proprietário (camada de aplicação)
- **OpenDroneMap/NodeODM**: GPLv3 (componentes base)

Ver [VISION.md](VISION.md) seção 4 para detalhes sobre licenciamento.

---

## Suporte

- E-mail: [seu-email]
- Issues: [GitHub Issues]
- Discussões: [GitHub Discussions]

---

**Última atualização**: 26 de janeiro de 2026
