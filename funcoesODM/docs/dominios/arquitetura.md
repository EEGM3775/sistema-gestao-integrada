# Domínio: Arquitetura — FuncoesODM

> Cole junto com CONTEXT.md quando a sessão envolver decisões arquiteturais, novos módulos ou estrutura do backend.

---

## Visão do Produto

Plataforma SaaS de fotogrametria para engenharia civil.  
ODM/NodeODM = caixa-preta de processamento consumida via API REST.  
FuncoesODM = camada proprietária: UI, lógica de negócios, persistência, autenticação.

**Estratégia de licenciamento:** comunicação apenas via API → camada proprietária independente dos componentes GPLv3 do ODM.

---

## Arquitetura de Serviços

```
Browser (Angular)
      │ HTTP/WS
      ▼
Nginx :8088 (reverse proxy)
      │ /api/*  → funcoesodm-java:8080
      │ /*       → Angular SPA
      ▼
Spring Boot :8080
      │  JDBC
      ├──► PostgreSQL :5433
      │
      │  HTTP REST
      └──► NodeODM :3000
```

---

## Decisões Arquiteturais (ADR resumido)

| Decisão | Escolha | Motivo |
|---------|---------|--------|
| Frontend framework | Angular 18 | Standalone + Signals = estado reativo sem NgRx |
| State management | Signals + RxJS | Signals para estado local; RxJS para HTTP/eventos |
| Mapas | Leaflet + georaster | Leve, extensível, bom suporte GeoTIFF |
| Change detection | OnPush em todos | Performance + previsibilidade |
| Backend | Spring Boot 3.2 + Java 17 | Produção enterprise, Spring Security maduro |
| Banco | PostgreSQL 15 | Extensões GIS disponíveis para futuro |
| Processamento | NodeODM via API | Não modificar GPL, desacoplamento |
| Autenticação | JWT stateless | Compatível com escala horizontal |
| WebSocket | STOMP sobre SockJS | Abstração confiável, suporta heartbeat |

---

## Multi-tenancy

Planejado desde o início:
- Todo recurso (projeto, medição, imagem) tem `userId` ou `project.userId`
- `ProjectSecurityService` valida ownership em todas as operações
- Banco: sem Row-Level Security ainda, mas isolamento por `user_id` em todas as queries

---

## Fluxo de Autenticação

```
POST /api/v1/auth/login { username, password }
  → AuthController → AuthService → BCrypt verify → JWT gerado
  → Resposta: { token: "eyJ..." }

Requests subsequentes:
  Header: Authorization: Bearer eyJ...
  → JwtAuthenticationFilter → valida token → popula SecurityContext
  → Controller recebe `@AuthenticationPrincipal UserDetails`
```

---

## Estrutura Backend (pacotes)

```
java-service/src/main/java/com/funcoesodm/
├── controller/
│   ├── AuthController.java
│   ├── ProjectController.java
│   ├── ChunkController.java          # Serve assets do NodeODM
│   └── MeasurementController.java
├── service/
│   ├── AuthService.java
│   ├── ProjectService.java
│   ├── NodeODMClientService.java     # HTTP client para NodeODM API
│   ├── MeasurementService.java
│   └── WebSocketService.java         # STOMP broadcast
├── model/
│   ├── User.java
│   ├── Project.java
│   ├── ProcessingTask.java
│   └── Measurement.java
├── repository/                        # JpaRepository para cada entidade
├── security/
│   ├── JwtAuthenticationFilter.java
│   └── ProjectSecurityService.java
├── dto/                               # Request/Response DTOs com @Valid
└── exception/
    ├── ResourceNotFoundException.java
    └── UnauthorizedException.java
```

---

## Roadmap de Produto (fases)

| Fase | Status | Descrição |
|------|--------|-----------|
| 1 | ✅ Concluída | Fundação: auth, projetos, docker, NodeODM básico |
| 2 | ✅ Concluída | Upload, processamento, WebSocket, visualizadores |
| 3 | 🔄 Em andamento | Módulos de engenharia (medições, PDF, NDVI, anotações) |
| 4 | ⏳ Pendente | Produção: CI/CD, escala, monitoramento, SaaS |

---

**Visão completa:** [architecture/VISION.md](../architecture/VISION.md)  
**Boas práticas de código:** [architecture/BEST_PRACTICES.md](../architecture/BEST_PRACTICES.md)
