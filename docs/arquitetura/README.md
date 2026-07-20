# Pranchas executivas da arquitetura

Detalhamento construtivo do sistema. A **planta baixa** (visão macro + diagrama) é
[../arquitetura.md](../arquitetura.md); aqui estão as **pranchas** com o nível de execução. Cada
prancha descreve o desenho completo da sua área (não o status — status é o [roadmap](../roadmap.md)).

| Prancha | Cobre |
|---|---|
| [auth-sso.md](auth-sso.md) | Identidade, SSO, claims do JWT (RS256/JWKS), fluxos de login/refresh/logout, JIT |
| [dados-e-tenancy.md](dados-e-tenancy.md) | Bancos por serviço, multi-tenancy (mixin + RLS), integridade, dados macro |
| [servicos-e-integracoes.md](servicos-e-integracoes.md) | Inventário de serviços, contratos (gateway/APIs/eventos), fluxos de sequência |
| [deploy-e-seguranca.md](deploy-e-seguranca.md) | Containers, rede, portas, borda, modelo de ameaças, segredos, escala, DR |
| [migracao-v01.md](migracao-v01.md) | **Migração v01→v02 (documento único):** princípios, dados (greenfield), cutover, régua de backend e o que garimpar no frontend |
| [lixo.md](lixo.md) | Sistema de exclusão segura — tabela genérica `Lixo`, papel `gestor_lixo`, garantia de ID, auto-purge |
| [rbac-abac.md](rbac-abac.md) | **Proposto** — modelo-alvo da camada 2: catálogo de permissões + papéis por tenant + ABAC + mascaramento de campo (PII). Espinha da Fase 9 |
| [diario-ia-reintegracao.md](diario-ia-reintegracao.md) | Plano de reintegração do canal WhatsApp → IA → Diário de Obra (contrato JSON da análise) |
| [rate-limiting.md](rate-limiting.md) | Três camadas de limite: entrada (IP/usuário/tenant/endpoint), saída (token bucket por fornecedor, protege cota e dinheiro) e cota comercial de plano |

Política de acesso (entitlement + RBAC) em [../acesso-e-permissoes.md](../acesso-e-permissoes.md);
entidades de negócio em [../dominio.md](../dominio.md).
