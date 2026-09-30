# Projeto Phoenix: Plataforma de Fotogrametria para Engenharia Civil

*Este documento descreve a visão arquitetônica e o plano de desenvolvimento para um software de nível comercial, focado nas necessidades de construtoras e engenheiros, construído sobre a fundação do ecossistema OpenDroneMap.*

---

## 1. Visão Geral

O objetivo deste projeto é criar uma plataforma SaaS (Software as a Service) robusta, intuitiva e poderosa que traduza dados de drones em inteligência acionável para o canteiro de obras. O produto final não será uma mera modificação do ODM/NodeODM, mas sim uma aplicação coesa e profissional que resolve problemas de alto valor no setor da construção.

---

## 2. Filosofia de Arquitetura: Construindo sobre Ombros de Gigantes

Nossa estratégia não é reinventar a roda, mas sim construir um veículo de alta performance usando os melhores componentes de código aberto disponíveis.

*   **Base Open Source:** Utilizaremos o ecossistema OpenDroneMap (ODM, NodeODM, ClusterODM) como a fundação para o processamento de imagens, tratando-o como um serviço de "caixa-preta" que consumimos via API.

*   **Aplicação Proprietária (FuncaoODM):** Nosso valor agregado será construído como uma **aplicação completamente separada e distinta**, chamada **FuncaoODM**. Esta aplicação seguirá uma arquitetura de microsserviços moderna para máxima escalabilidade e flexibilidade:

    *   **Frontend:** A interface do usuário será desenvolvida com **Angular**. Esta escolha nos dá uma fundação robusta e escalável, ideal para uma aplicação complexa de nível comercial, com um ecossistema poderoso para criar uma experiência de usuário rica e profissional.

    *   **Backend (Microsserviços):**
        *   **Serviço Principal (Java):** O núcleo da lógica de negócios residirá em um serviço construído com **Java e o framework Spring Boot**. Ele será responsável pelas APIs principais, gerenciamento de usuários, projetos, e a persistência de dados do "Diário de Obras" em um banco de dados relacional.

    *   **API Gateway:** Um gateway de API será colocado na frente dos microsserviços para fornecer uma interface única, segura e coesa para o frontend Angular.

    Essa arquitetura desacoplada nos permite usar a melhor tecnologia para cada função, garante a manutenibilidade e cumpre o requisito de não modificar o código-fonte do NodeODM/ODM.

Essa abordagem desacoplada é crucial para garantir a manutenibilidade do nosso produto, permitindo-nos incorporar atualizações do ecossistema base sem quebrar nossa aplicação.

---

## 3. Os Quatro Pilares do Produto Completo

### Pilar 1: Experiência do Usuário (UX) Profissional

A interface será projetada do zero para ser centrada no fluxo de trabalho do engenheiro.

*   **Portal de Projetos:** Um dashboard centralizado para visualização e gerenciamento de todos os projetos.
*   **Visualizador de Dados Unificado:** Uma interface de mapa e 3D de alta performance como peça central da experiência.
*   **Fluxos de Trabalho Guiados:** Processos passo a passo para criação de projetos, upload de dados e processamento, minimizando a chance de erro do usuário.

### Pilar 2: Arquitetura de Backend Escalável e Segura

A plataforma será projetada para multi-tenancy (múltiplos clientes) desde o primeiro dia, garantindo segurança e performance.

*   **Arquitetura Distribuída:**
    *   **Servidor de Aplicação (FuncoesODM):** Gerencia usuários, projetos e metadados.
    *   **Balanceador de Carga (ClusterODM):** Distribui o trabalho de processamento de forma inteligente.
    *   **Cluster de Processamento (NodeODM):** Um conjunto escalável de "trabalhadores" que executam o processamento pesado, podendo ser expandido na nuvem.
*   **Armazenamento de Dados:** Uso de armazenamento de objetos (como Amazon S3) para garantir escalabilidade, segurança e backup dos dados massivos gerados.

### Pilar 3: O Conjunto de Ferramentas de Engenharia (Feature Suite)

Este é o coração do nosso valor agregado.

*   **Módulo de Análise Topográfica:**
    *   Cálculo de Volume de Pilhas de Material.
    *   Mapa de Corte e Aterro (vs. Superfície de Projeto).
    *   Ferramenta de Perfil e Seção Transversal.
    *   Geração de Curvas de Nível.
*   **Módulo de Controle de Qualidade (As-Built vs. As-Designed):**
    *   Sobreposição de Projetos 2D (DXF, DWG) e 3D (IFC).
    *   Linha do Tempo Visual para comparação de progresso.
*   **Módulo de Colaboração e Relatórios:**
    *   Sistema de Anotações e Medições compartilháveis.
    *   Geração de Relatórios em PDF customizáveis.
*   **Módulo de Precisão:**
    *   Fluxo de trabalho simplificado para uso de Pontos de Controle (GCPs), integrando o `Find-GCP`.
    *   Geração de Relatórios de Acurácia do processamento.

### Pilar 4: Modelo de Produto e Entrega

*   **Modelo de Negócio:** SaaS (Software as a Service) com assinaturas mensais/anuais.
*   **Componentes do Produto:** Além do software, o produto "completo" incluirá documentação detalhada, tutoriais e um sistema de suporte técnico.

---

## 4. Licenciamento e o Uso de Código Aberto (AGPLv3 / GPLv3)

Esta seção é de extrema importância.

*   **As Licenças:** O ecossistema OpenDroneMap utiliza licenças "copyleft" fortes. O NodeODM/ODM é licenciado sob **GPLv3**.
*   **Implicações da AGPLv3:** A licença AGPLv3 estipula que se você modificar o código e oferecer seu uso através de uma rede (como em um modelo SaaS), você **deve** disponibilizar o código-fonte modificado para os usuários daquele serviço.
*   **Nossa Estratégia Arquitetônica:** Nossa abordagem de construir uma **camada de aplicação desacoplada** é a estratégia recomendada para criar um produto comercial em cima de uma base GPL. Ao nos comunicarmos com o NodeODM principalmente através de suas APIs, podemos desenvolver nosso código proprietário (nossa interface de usuário customizada, algoritmos específicos em nossos plugins) de forma mais independente.
*   **Transparência:**
    *   Qualquer modificação que fizermos diretamente nos componentes base (NodeODM, ODM) será mantida em conformidade com suas respectivas licenças e o código-fonte dessas modificações será disponibilizado.
    *   Nossa "propriedade intelectual" e diferencial competitivo residirão na camada de aplicação, na UX e na lógica de negócios que construiremos em volta do núcleo open source.

**Aviso:** Esta é uma interpretação de engenharia de software. É **altamente recomendável** consultar um advogado especializado em licenciamento de software para validar a estratégia comercial e de licenciamento do produto final.

---

## 5. Plano de Desenvolvimento (Roadmap)

A construção seguirá uma abordagem incremental, mesmo com a visão do produto completo.

1.  **Fase 1: Fundação e Ambiente.** Configurar o ambiente de desenvolvimento com a arquitetura distribuída em mente.
2.  **Fase 2: MVP Funcional.** Implementar a primeira funcionalidade de ponta a ponta (Cálculo de Volume) dentro da nova arquitetura.
3.  **Fase 3: Expansão do Feature Suite.** Desenvolver os demais módulos de engenharia (Controle de Qualidade, Colaboração, etc.).
4.  **Fase 4: Polimento e Lançamento.** Focar na UX, segurança, documentação, sistema de cobrança e preparação para o lançamento comercial.
---

## Status Atual (Novembro de 2025)

A **Fase 2: Prova de Conceito Vertical** foi concluída e a **Fase 3** está em andamento. O projeto possui uma arquitetura completa e funcional de ponta a ponta.

### ✅ Funcionalidades Implementadas

#### 1. Autenticação e Segurança
- Sistema de login com JWT
- Proteção de rotas com AuthGuard
- Refresh token automático
- Credenciais de teste: `admin` / `admin123`

#### 2. Gerenciamento de Projetos
- CRUD completo de projetos
- Dashboard com lista de projetos
- Página de detalhes do projeto
- Contagem de imagens e tarefas por projeto

#### 3. Upload de Imagens
- Upload múltiplo com drag-and-drop
- Barra de progresso individual por arquivo
- Galeria de imagens do projeto
- Exclusão de imagens

#### 4. Processamento de Imagens
- Fila de processamento com estados (QUEUED, RUNNING, COMPLETED, FAILED)
- Progresso em tempo real via WebSocket (STOMP)
- Opções de processamento configuráveis
- Simulação de etapas do ODM

#### 5. WebSocket em Tempo Real
- Conexão STOMP sobre SockJS
- Atualização automática de progresso
- Reconexão automática em caso de falha
- Notificações por projeto

### 🏗️ Arquitetura de Containers

```
┌─────────────────────────────────────────────────────────────┐
│                        NGINX (8088)                         │
│                    Reverse Proxy + Frontend                 │
└─────────────────────┬───────────────────────┬───────────────┘
                      │                       │
          ┌───────────▼───────────┐ ┌─────────▼─────────┐
          │   Java Service (8080) │ │ NodeODM (3000)    │
          │   - Auth/JWT          │ │ - Processing API │
          │   - Projects API      │ │ - Downloads      │
          │   - Tasks API         │ │                  │
          │   - WebSocket         │ │                  │
          └───────────┬───────────┘ └───────────────────┘
                      │
          ┌───────────▼───────────┐
          │  PostgreSQL (5433)    │
          │  - users              │
          │  - projects           │
          │  - project_images     │
          │  - processing_tasks   │
          └───────────────────────┘
```

### 🚀 Como Executar

```bash
# Clonar o repositório
cd funcoesODM

# Iniciar todos os serviços
docker compose up -d

# Verificar status
docker compose ps

# Acessar a aplicação
# Frontend: http://localhost:8088
# API Health: http://localhost:8088/api/v1/health
```

### 📋 Endpoints da API

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/auth/login` | POST | Autenticação |
| `/api/v1/projects` | GET/POST | Listar/Criar projetos |
| `/api/v1/projects/{id}` | GET/PUT/DELETE | CRUD projeto |
| `/api/v1/projects/{id}/images` | GET/POST/DELETE | Imagens |
| `/api/v1/projects/{id}/tasks` | GET/POST | Tarefas |
| `/api/v1/projects/{id}/tasks/{taskId}/cancel` | POST | Cancelar |
| `/ws` | WebSocket | STOMP endpoint |

### 🔜 Próximos Passos (Fase 3)

1. **Integração Direta com NodeODM** ✅ (Backend Implementado)
    - Cliente NodeODM direto no Java
    - Polling de status com WebSocket
    - Download de assets (orthophoto, DSM, DTM, pointcloud)
    - Requer NodeODM em execução

### 🌐 Integração NodeODM (Direta)

A integração direta com NodeODM foi implementada no backend. Para ativar o processamento real:

```bash
# 1. No .env, configure o NodeODM:
NODEODM_URL=http://nodeodm:3000
NODEODM_SKIP_REPORT=true

# 2. Reinicie os containers:
docker compose up -d
```

#### Endpoints NodeODM (via proxy)

Os downloads e chamadas diretas ao NodeODM são expostos via proxy:

```
/nodeodm-api/*  →  nodeodm:3000/*
```

### 📥 Sistema de Downloads

O sistema oferece uma interface completa para download dos resultados do processamento fotogramétrico.

#### Interface de Downloads no Frontend

A aba **Downloads** no visualizador de resultados oferece:

1. **Seleção Múltipla**
   - Checkbox para selecionar arquivos individualmente
   - Botão "Selecionar Todos" para marcar todos os arquivos
   - Contador de itens selecionados

2. **Download Individual**
   - Cada arquivo pode ser baixado individualmente
   - Botão de preview para ortofoto e DSM/DTM

3. **Download em Lote**
   - **📦 Baixar Tudo (ZIP)**: Baixa o pacote completo `all.zip` (~100MB)
   - **📥 Baixar Selecionados**: Baixa apenas os arquivos selecionados

#### Arquivos Disponíveis para Download

| Arquivo | Descrição | Formato | Tamanho Típico |
|---------|-----------|---------|----------------|
| **Ortofoto** | Mosaico ortorretificado georreferenciado | GeoTIFF (.tif) | 5-50 MB |
| **DSM** | Modelo Digital de Superfície (inclui objetos) | GeoTIFF (.tif) | 2-20 MB |
| **DTM** | Modelo Digital de Terreno (apenas terreno) | GeoTIFF (.tif) | 2-20 MB |
| **Nuvem de Pontos** | Nuvem de pontos 3D georreferenciada | LAZ (.laz) | 10-100 MB |
| **Modelo 3D** | Modelo texturizado (OBJ + texturas) | ZIP (.zip) | 5-50 MB |
| **Relatório** | Relatório de processamento | PDF (.pdf) | 1-5 MB |
| **Pacote Completo** | Todos os resultados em um arquivo | ZIP (.zip) | ~100 MB |

#### Endpoints de Download (NodeODM)

```bash
# Baixar arquivo específico
GET /nodeodm-api/task/{task_uuid}/download/{asset}

# Assets disponíveis:
# - orthophoto.tif
# - dsm.tif  
# - dtm.tif
# - georeferenced_model.laz
# - textured_model.zip
# - report.pdf
# - all.zip

# Exemplos:
curl -O http://localhost:8088/nodeodm-api/task/{uuid}/download/orthophoto.tif
curl -O http://localhost:8088/nodeodm-api/task/{uuid}/download/all.zip
```

#### Copiar Arquivos para o Host

Para copiar os arquivos do volume Docker para sua máquina local:

```bash
# Copiar toda a pasta de resultados
docker compose cp nodeodm:/var/www/data/{task-uuid}/ ~/meus_mapas/

# Copiar apenas o ZIP completo
docker compose cp nodeodm:/var/www/data/{task-uuid}/all.zip ./

# Localização dos dados no container:
# NodeODM: /var/www/data/{task-uuid}/
```

#### Estrutura de Arquivos de uma Task

```
/var/www/data/{task-uuid}/
├── all.zip                    # Pacote completo (~100MB)
├── images.json                # Metadados GPS das imagens
├── cameras.json               # Calibração das câmeras
├── odm_orthophoto/
│   └── odm_orthophoto.tif    # Ortofoto
├── odm_dem/
│   ├── dsm.tif               # Digital Surface Model
│   └── dtm.tif               # Digital Terrain Model
├── odm_texturing/
│   └── odm_textured_model_geo.obj  # Modelo 3D
├── entwine_pointcloud/        # Nuvem de pontos (3D Tiles)
├── odm_georeferencing/        # Dados georreferenciados
└── odm_report/                # Relatórios de processamento
```

#### Fluxo de Processamento

```
1. Frontend cria tarefa → Java Service
2. Java Service inicia processamento async
3. Java Service envia imagens para o NodeODM
4. Inicia polling de status (10s intervalo)
5. Atualiza progresso via WebSocket
6. Ao completar, retorna URLs dos assets
```

### ⚠️ Problemas Conhecidos e Workarounds

#### Bug do Relatório no ODM 3.5.6

O NodeODM versão 3.5.6 possui um bug conhecido no GDAL que causa falha na geração do relatório PDF/HTML. O erro ocorre na etapa final do processamento (90%+) com a mensagem:

```
ImportError: cannot import name '_gdal_array' from 'osgeo'
```

**Impacto:** A task é marcada como FAILED mesmo que os produtos principais (orthophoto, DSM, DTM, nuvem de pontos) tenham sido gerados com sucesso.

**Solução:** A opção `skip-report` pula a geração do relatório, permitindo que o processamento seja concluído com sucesso.

#### Configuração do Skip-Report

**No Frontend:**
- Na tela de criação de tarefa, a opção "📄 Relatório PDF" está **desmarcada por padrão**
- Se marcar, um ícone ⚠️ aparece indicando o risco de falha
- O usuário pode decidir se quer arriscar gerar o relatório

**Via Variável de Ambiente:**
```bash
# No docker-compose.yml ou .env
NODEODM_SKIP_REPORT=true   # Pula relatório por padrão (recomendado para ODM 3.5.6)
NODEODM_SKIP_REPORT=false  # Tenta gerar relatório (pode falhar)
```

**Via API:**
```bash
# Passar skip_report como parâmetro
curl -X POST "http://localhost:8001/api/v1/tasks" \
  -F "images=@image1.jpg" \
  -F "images=@image2.jpg" \
  -F "skip_report=true"
```

**Verificar Versão e Bug:**
```bash
# Endpoint de diagnóstico
curl http://localhost:8001/api/v1/nodeodm/version

# Resposta esperada para ODM 3.5.6:
{
  "version": "3.5.6",
  "has_report_bug": true,
  "skip_report_default": true,
  "recommendation": "Use skip-report=true"
}
```

#### Status COMPLETED_WITH_WARNINGS

Quando uma task falha por causa do bug do relatório, mas os produtos principais foram gerados com sucesso, o sistema marca a task como `COMPLETED_WITH_WARNINGS` em vez de `FAILED`. Isso permite:

- Baixar os arquivos gerados (orthophoto, DSM, etc.)
- Ver qual foi o problema no campo `warningMessage`
- Não perder o trabalho de processamento

#### Validação de Assets

Para verificar se os assets foram realmente gerados:

```bash
# Validar que os arquivos existem e são acessíveis
curl http://localhost:8001/api/v1/tasks/{task_id}/assets/validate

# Resposta:
{
  "task_id": "uuid-da-task",
  "all_valid": true,
  "valid_assets": ["orthophoto.tif", "dsm.tif", "georeferenced_model.laz"],
  "invalid_assets": []
}
```

### 📊 Opções de Processamento

| Opção | Descrição | Padrão |
|-------|-----------|--------|
| `dsm` | Gerar Modelo Digital de Superfície | true |
| `dtm` | Gerar Modelo Digital de Terreno | false |
| `orthophoto-resolution` | Resolução da ortofoto (cm/pixel) | 5.0 |
| `pc-quality` | Qualidade da nuvem de pontos | medium |
| `skip-report` | Pular geração do relatório | true* |
| `auto-boundary` | Auto-detectar bordas | true |
| `use-3dmesh` | Gerar modelo 3D texturizado | false |

*\* Padrão `true` devido ao bug no ODM 3.5.6*

2. **Visualização de Resultados** ✅ (Implementado)
   - `ResultsService` para gerenciar assets e URLs
   - `ResultsViewerComponent` com abas (Mapa, DSM/DTM, Downloads)
   - Ortofoto no mapa Leaflet com controles de zoom
   - Preview de DSM/DTM com escala de cores
   - Lista de downloads com todos os arquivos gerados
   - Integração com seleção de tarefa no project-detail

3. **Cálculo de Volume**
    - Extração de resultados do NodeODM
   - Interface de medição

4. **Gerenciamento de GCPs**
   - Upload de arquivo GCP
   - Marcação nas imagens

5. **Visualizador 3D**
   - Nuvem de pontos com Potree/Three.js

**Próximos Passos:** O projeto está pronto para continuar a **Fase 3**, com foco nas funcionalidades de engenharia restantes (cálculo de volume, GCPs, visualizador 3D).

---

## Pilar 5: O Diário de Obras Inteligente e a Visão de Futuro

Esta é a evolução que transforma nosso software de uma simples ferramenta de análise para o **sistema nervoso central do canteiro de obras**. O conceito de Diário de Obras (RDO/DO) é o alicerce.

### O Conceito: Diário de Obras como "Single Source of Truth"

Cada processamento de drone se torna uma entrada imutável e georreferenciada no diário. Esta entrada não é apenas um relatório, é um "snapshot digital" completo do canteiro em um determinado dia, contendo:
*   O Ortomosaico, o Modelo Digital de Elevação (MDE) e o Modelo 3D.
*   A partir deste registro visual, o sistema permite vincular todas as outras informações relevantes:
    *   **Anotações Manuais:** Registros da equipe de campo sobre atividades do dia, problemas, decisões tomadas.
    *   **Fotos de Detalhe:** Fotos tiradas com celular no campo podem ser uploadadas e "pinadas" em sua localização exata no mapa 2D/3D.
    *   **Documentos:** Anexar relatórios de segurança, notas fiscais de materiais, etc.
    *   **Dados Externos:** Integração com APIs de clima para registrar automaticamente as condições do dia.

### Ideias Inovadoras para o Futuro (Onde a IA Transforma o Jogo)

Com o Diário de Obras Inteligente como base, podemos implementar funcionalidades de ponta que realmente nos diferenciarão no mercado:

*   **Análise de Progresso Automatizada (IA):** O sistema compara o "as-built" (modelo 3D do dia) com o modelo BIM e seu cronograma (o "as-planned") e gera insights automáticos:
    *   *"Alerta: 7 das 10 fundações planejadas para esta semana foram concluídas."*
    *   *"Status: 85% da terraplanagem do Setor 2 finalizada, 3 dias adiantado em relação ao cronograma."*

*   **Detecção e Quantificação Automática de Mudanças (IA):** Em vez de um engenheiro comparar visualmente dois mapas, o sistema aponta as mudanças e as quantifica:
    *   *"Novos Materiais: +500m³ detectados na área do estoque A."*
    *   *"Atividade: 150 metros de novas valas de drenagem escavadas no Setor B."*

*   **Reconhecimento de Ativos e Segurança (IA):**
    *   **Logística:** Identificar e contar automaticamente equipamentos no canteiro (ex: "12 escavadeiras, 3 guindastes no local hoje"), otimizando a gestão de ativos.
    *   **Segurança:** Treinar a IA para detectar potenciais riscos de segurança, como ausência de barreiras de proteção, pessoal trabalhando em áreas de risco ou equipamentos muito próximos.

*   **Rumo ao Gêmeo Digital (Digital Twin) 4D:**
    *   **Simulação 4D (3D + Tempo):** Combinando o modelo BIM (3D) com o cronograma do projeto (Tempo), podemos criar uma simulação que mostra o **planejado vs. real** lado a lado ao longo do tempo.
    *   **Análise Preditiva:** Analisando a velocidade do progresso ao longo de várias semanas, o sistema pode começar a prever o futuro. *"Atenção: Mantendo o ritmo atual, a fase de terraplanagem está projetada para terminar com 8 dias de atraso."* Isso transforma a gestão de reativa para **proativa**.
    *   **Realidade Aumentada (AR):** Disponibilizar uma função de exportação ou um app complementar que permita a um engenheiro, no canteiro de obras com um tablet, ver o modelo BIM (ex: tubulações subterrâneas, estruturas) sobreposto ao mundo real.
