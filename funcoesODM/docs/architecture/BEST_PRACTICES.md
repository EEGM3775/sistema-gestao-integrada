# Guia de Boas Práticas - FuncoesODM

## Objetivo

Este guia estabelece as melhores práticas para desenvolvimento no projeto FuncoesODM, visando manter o código organizado, manutenível e otimizado para trabalho com agentes de IA.

---

## Regras Críticas de Encoding

### NÃO USE EMOJIS EM CÓDIGO

**Regra Zero: Emojis são PROIBIDOS em todo código executável.**

#### ❌ NUNCA Faça Isso

```powershell
# ERRADO - Causa parser error
Write-Host "✅ Serviço iniciado!" -ForegroundColor Green
Write-Host "🚀 Iniciando aplicação..." -ForegroundColor Blue
echo "🛑 Parando containers..."
```

```typescript
// ERRADO - Causa problemas de encoding
console.log('✅ Upload concluído com sucesso!');
throw new Error('❌ Falha na validação');
```

```java
// ERRADO - Incompatível com codepages
System.out.println("🚀 Iniciando processamento...");
logger.error("❌ Erro crítico detectado");
```

#### ✅ SEMPRE Faça Isso

```powershell
# CORRETO - Use marcadores ASCII
Write-Host "[OK] Servico iniciado!" -ForegroundColor Green
Write-Host "[INFO] Iniciando aplicacao..." -ForegroundColor Blue
echo "[STOP] Parando containers..."
```

```typescript
// CORRETO - ASCII puro
console.log('[OK] Upload concluido com sucesso!');
throw new Error('[ERRO] Falha na validacao');
```

```java
// CORRETO - Compatível com todos os sistemas
System.out.println("[INFO] Iniciando processamento...");
logger.error("[ERRO] Erro critico detectado");
```

#### Por Que Essa Regra Existe?

| Problema | Impacto |
|----------|---------|
| **PowerShell Parser** | Emojis causam `Token inesperado` errors no Windows |
| **Encoding UTF-8 BOM** | PowerShell falha ao parsear arquivos com BOM |
| **CMD/Batch** | Não renderiza emojis, mostra caracteres inválidos (ðŸš€) |
| **VBScript** | Não suporta Unicode estendido |
| **Cross-platform** | Diferentes sistemas renderizam emojis diferentemente |
| **IDE/Editor** | Alguns editores corrompem emojis ao salvar |

#### Marcadores Padrão do Projeto

Use **SEMPRE** estes marcadores ASCII:

| Marcador | Uso | Exemplo |
|----------|-----|---------|
| `[OK]` | Sucesso/Confirmação | `[OK] Arquivo salvo com sucesso` |
| `[ERRO]` | Erro crítico | `[ERRO] Falha ao conectar no banco` |
| `[AVISO]` | Aviso/Atenção | `[AVISO] Espaco em disco baixo` |
| `[INFO]` | Informação geral | `[INFO] Iniciando servico...` |
| `[DEBUG]` | Debug/Diagnóstico | `[DEBUG] Valor da variavel: 42` |

#### Encoding de Arquivos por Tipo

| Tipo de Arquivo | Encoding Obrigatório | Observações |
|-----------------|---------------------|-------------|
| **PowerShell (.ps1)** | ASCII ou UTF-8 **SEM BOM** | BOM causa parser errors |
| **Batch (.bat)** | ASCII ou Windows-1252 | Evite acentos quando possível |
| **Shell (.sh)** | UTF-8 sem BOM | Compatible com Linux/WSL |
| **TypeScript (.ts)** | UTF-8 sem BOM | Padrão do Angular |
| **Java (.java)** | UTF-8 sem BOM | Padrão do Spring Boot |
| **HTML (.html)** | UTF-8 sem BOM | Declare `<meta charset="UTF-8">` |
| **CSS/SCSS** | UTF-8 sem BOM | |
| **JSON (.json)** | UTF-8 sem BOM | Sem comentários |
| **Markdown (.md)** | UTF-8 sem BOM | Emojis permitidos apenas em docs |

#### Configuração do VS Code

Adicione ao `settings.json`:

```json
{
  "files.encoding": "utf8",
  "files.eol": "\n",
  "files.insertFinalNewline": true,
  "files.trimTrailingWhitespace": true,
  "[powershell]": {
    "files.encoding": "utf8"
  },
  "[shellscript]": {
    "files.encoding": "utf8"
  }
}
```

#### Quando Emojis SÃO Permitidos

✅ Emojis podem ser usados **APENAS** em:
- Documentação Markdown (README.md, docs/\*.md)
- Comentários de commit do Git
- Issues e Pull Requests no GitHub
- Mensagens exibidas para usuários finais (frontend UI)

❌ Emojis são **PROIBIDOS** em:
- Código executável (scripts, source code)
- Logs de aplicação (console.log, logger)
- Mensagens de erro/aviso programáticas
- Nomes de arquivos ou variáveis
- Strings de configuração

---

## Regras de Tamanho de Arquivos

### Limites Recomendados

| Tipo de Arquivo | Máximo Recomendado | Crítico (Nunca Exceder) |
|-----------------|-------------------|------------------------|
| Componente (.ts) | 300 linhas | 500 linhas |
| Service (.ts) | 200 linhas | 400 linhas |
| Template inline | 30 linhas | 50 linhas |
| Arquivo de constantes | 150 linhas | 300 linhas |
| Modelo/Interface | 100 linhas | 200 linhas |

### Por Que Esses Limites?

- **Contexto de IA**: Modelos de linguagem têm limite de tokens (geralmente 4K-8K)
- **Legibilidade**: Humanos também têm limite de memória de trabalho
- **Manutenibilidade**: Arquivos menores são mais fáceis de testar e refatorar
- **Reusabilidade**: Componentes focados são mais reutilizáveis

---

## Arquitetura de Componentes

### Princípio da Responsabilidade Única

Cada componente deve ter **uma única responsabilidade clara**.

❌ **Evite:**
```typescript
// results-viewer.component.ts (1821 linhas)
// Faz TUDO: renderiza mapa, processa DSM, gerencia downloads, exibe avisos
```

✅ **Prefira:**
```typescript
// results-viewer.component.ts (150 linhas)
// Apenas coordena os sub-componentes

// map-tab.component.ts (200 linhas)
// Apenas renderiza o mapa

// dsm-tab.component.ts (180 linhas)
// Apenas processa e exibe DSM/DTM

// downloads-tab.component.ts (150 linhas)
// Apenas gerencia downloads
```

### Hierarquia de Componentes

```
feature/
├── feature.component.ts          # Componente pai (coordenador)
├── feature.component.html        # Template sempre externo
├── feature.component.scss        # Estilos sempre externos
├── components/                   # Sub-componentes
│   ├── sub-feature-a/
│   │   ├── sub-feature-a.component.ts
│   │   ├── sub-feature-a.component.html
│   │   └── sub-feature-a.component.scss
│   └── sub-feature-b/
├── services/                     # Lógica de negócio
│   └── feature.service.ts
├── models/                       # Interfaces e tipos
│   └── feature.model.ts
└── utils/                        # Funções utilitárias
    └── feature.utils.ts
```

---

## Padrões de Código Angular

### 1. Templates

**❌ NUNCA faça isto:**
```typescript
@Component({
  template: `
    <div class="huge-template">
      <!-- 500 linhas de HTML aqui -->
    </div>
  `
})
```

**✅ SEMPRE faça isto:**
```typescript
@Component({
  templateUrl: './my-component.component.html'
})
```

### 2. Estilos

**❌ NUNCA:**
```typescript
@Component({
  styles: [`
    /* 200 linhas de CSS */
  `]
})
```

**✅ SEMPRE:**
```typescript
@Component({
  styleUrls: ['./my-component.component.scss']
})
```

### 3. Signals vs RxJS

**Use Signals para:**
- Estado local do componente
- Valores que mudam com frequência
- Computed values simples

```typescript
// ✅ Bom uso de signals
currentTab = signal<TabType>('map');
isLoading = signal(false);
itemCount = computed(() => this.items().length);
```

**Use RxJS para:**
- Chamadas HTTP
- Eventos complexos
- Pipes de transformação

```typescript
// ✅ Bom uso de RxJS
this.http.get<Project[]>('/api/projects')
  .pipe(
    map(projects => projects.filter(p => p.active)),
    catchError(err => this.handleError(err))
  )
  .subscribe(projects => this.projects.set(projects));
```

### 4. Standalone Components

**SEMPRE use standalone components:**

```typescript
@Component({
  selector: 'app-my-component',
  standalone: true,  // ✅
  imports: [CommonModule, FormsModule, OtherComponent],
  templateUrl: './my-component.component.html'
})
```

---

## Organização de Services

### Princípios

1. **Um service = uma responsabilidade**
2. **Máximo 200 linhas por service**
3. **Métodos públicos no topo**
4. **Métodos privados no final**

### Exemplo de Service Bem Estruturado

```typescript
@Injectable({ providedIn: 'root' })
export class MapService {
  // Dependências
  private http = inject(HttpClient);
  
  // Estado (signals)
  private mapInstance = signal<L.Map | null>(null);
  
  // API Pública (métodos públicos)
  initializeMap(containerId: string, options: MapOptions): void {
    // ...
  }
  
  addLayer(layer: L.Layer): void {
    // ...
  }
  
  // Utilitários privados
  private validateOptions(options: MapOptions): boolean {
    // ...
  }
}
```

### Quando Dividir um Service

**Se o service tem mais de 200 linhas, pergunte:**

1. Ele está fazendo mais de uma coisa?
2. Alguns métodos são relacionados entre si mas não com outros?
3. Há grupos naturais de funcionalidade?

**Exemplo de divisão:**

```
❌ map-service.ts (500 linhas)
   - Renderiza mapa
   - Processa GeoTIFF
   - Gerencia layers
   - Calcula áreas

✅ Divida em:
   map-renderer.service.ts (150 linhas) - Renderização
   geotiff-processor.service.ts (120 linhas) - Processamento
   layer-manager.service.ts (100 linhas) - Gerenciamento
   geometry-calculator.service.ts (130 linhas) - Cálculos
```

---

## Constantes e Configurações

### Organização por Categoria

**❌ Um arquivo gigante:**
```typescript
// odm-options.const.ts (450 linhas)
// Todas as opções misturadas
```

**✅ Dividido por categoria:**
```
constants/odm-options/
├── index.ts                    # Exporta tudo
├── quality-levels.const.ts     # Níveis de qualidade
├── camera.const.ts             # Opções de câmera
├── mesh.const.ts               # Opções de mesh
├── point-cloud.const.ts        # Opções de nuvem de pontos
└── dem.const.ts                # Opções de DEM
```

**index.ts:**
```typescript
export * from './quality-levels.const';
export * from './camera.const';
export * from './mesh.const';
export * from './point-cloud.const';
export * from './dem.const';
```

---

## Testes

### Estrutura de Testes

```
feature/
├── feature.component.ts
├── feature.component.spec.ts       # Teste do componente
├── services/
│   ├── feature.service.ts
│   └── feature.service.spec.ts     # Teste do service
└── utils/
    ├── feature.utils.ts
    └── feature.utils.spec.ts       # Teste das utils
```

### Cobertura Mínima

- **Services**: 80% de cobertura
- **Utils**: 90% de cobertura
- **Componentes**: 60% de cobertura

---

## Documentação

### JSDoc para Funções Complexas

```typescript
/**
 * Calcula o volume de corte/aterro entre duas superfícies
 * 
 * @param surface1 Primeira superfície (GeoTIFF)
 * @param surface2 Segunda superfície (GeoTIFF)
 * @param options Opções de cálculo
 * @returns Volume em metros cúbicos (positivo = aterro, negativo = corte)
 * 
 * @example
 * const volume = calculateVolume(dsm1, dsm2, { resolution: 5 });
 * console.log(`Volume de aterro: ${volume}m³`);
 */
calculateVolume(
  surface1: GeoTIFF,
  surface2: GeoTIFF,
  options: VolumeOptions
): number {
  // ...
}
```

### README em Cada Feature

Cada feature complexa deve ter um README explicando:

```markdown
# Feature Name

## Responsabilidade
O que esta feature faz?

## Componentes
- `main.component.ts`: Descrição
- `sub-a.component.ts`: Descrição

## Services
- `feature.service.ts`: Descrição

## Fluxo de Dados
Como os dados fluem pela feature?

## Exemplos de Uso
Código de exemplo
```

---

## Convenções de Nomenclatura

### Componentes

```
feature-name.component.ts
feature-name.component.html
feature-name.component.scss
feature-name.component.spec.ts
```

### Services

```
feature-name.service.ts
feature-name.service.spec.ts
```

### Models

```
feature-name.model.ts        # Interfaces e tipos
feature-name.interface.ts    # Apenas interfaces (alternativa)
```

### Utils

```
feature-name.utils.ts
array.utils.ts
date.utils.ts
```

### Constants

```
feature-name.const.ts
api-endpoints.const.ts
```

---

## Performance

### Lazy Loading

**SEMPRE use lazy loading para features:**

```typescript
// app.routes.ts
export const routes: Routes = [
  {
    path: 'projects',
    loadComponent: () => 
      import('./features/projects/project-list/project-list.component')
        .then(m => m.ProjectListComponent)
  }
];
```

### Change Detection

**Use OnPush quando possível:**

```typescript
@Component({
  selector: 'app-my-component',
  changeDetection: ChangeDetectionStrategy.OnPush,  // ✅
  // ...
})
```

### TrackBy em *ngFor

**SEMPRE use trackBy:**

```typescript
// ❌ Sem trackBy
<div *ngFor="let item of items">{{ item.name }}</div>

// ✅ Com trackBy
<div *ngFor="let item of items; trackBy: trackById">{{ item.name }}</div>

// Component
trackById(index: number, item: any): number {
  return item.id;
}
```

---

## Segurança

### Sanitização

**SEMPRE sanitize dados externos:**

```typescript
import { DomSanitizer } from '@angular/platform-browser';

constructor(private sanitizer: DomSanitizer) {}

getSafeUrl(url: string): SafeResourceUrl {
  return this.sanitizer.sanitize(SecurityContext.URL, url);
}
```

### Validação de Inputs

**SEMPRE valide @Input():**

```typescript
@Input() set projectId(value: string) {
  if (!value || value.trim() === '') {
    console.error('Invalid projectId');
    return;
  }
  this._projectId = value;
}
private _projectId: string = '';
```

---

## Métricas de Qualidade

### Checklist Antes de Commit

- [ ] Nenhum arquivo TypeScript >300 linhas
- [ ] Todos templates >30 linhas foram externalizados
- [ ] Services têm responsabilidade única
- [ ] Testes passam (`npm test`)
- [ ] Sem erros de linting (`npm run lint`)
- [ ] Sem console.log em produção
- [ ] Comentários JSDoc em funções complexas

### Code Review

**O revisor deve verificar:**

1. **Tamanho**: Arquivos dentro dos limites?
2. **Responsabilidade**: Um arquivo = uma responsabilidade?
3. **Nomenclatura**: Segue as convenções?
4. **Testes**: Funcionalidade está testada?
5. **Performance**: Usa OnPush e trackBy?
6. **Segurança**: Dados externos são sanitizados?

---

## Otimização para IA

### Por Que Isso Importa?

Agentes de IA (como GitHub Copilot) funcionam melhor com:

1. **Arquivos pequenos e focados**: Cabem inteiramente no contexto
2. **Nomenclatura clara**: IA entende a intenção
3. **Estrutura consistente**: Padrões são reconhecidos
4. **Comentários úteis**: JSDoc treina o modelo

### Exemplos

**❌ Ruim para IA:**
```typescript
// huge-component.ts (1500 linhas)
// Múltiplas responsabilidades
// Nomes genéricos: data, result, temp
// Sem comentários
```

**✅ Bom para IA:**
```typescript
// map-renderer.service.ts (180 linhas)
// Responsabilidade: Renderizar mapas Leaflet

/**
 * Inicializa um mapa Leaflet com camadas base
 */
initializeMap(options: MapOptions): L.Map {
  const map = L.map(options.containerId, {
    center: options.center,
    zoom: options.zoom
  });
  // ...
  return map;
}
```

---

## Uso de Tiles e APIs de Terceiros

### Google Maps Satellite — Aviso Legal

O GCP Editor Visual utiliza tiles de satélite do Google (`mt{0-3}.google.com/vt/lyrs=s`) para o mapa de posicionamento de pontos GCP.

> **ATENCAO:** Este uso **viola os Termos de Serviço do Google Maps Platform**.
> Os tiles são consumidos sem API key, o que é explicitamente proibido pelo ToS do Google.

#### Por que foi implementado assim?

- Alternativas legais gratuitas (Esri World Imagery, Bing Maps via plugin) têm cobertura inferior no Brasil.
- O uso é interno/desenvolvimento; para produção SaaS, avaliar custo do Google Maps Platform API.

#### Alternativas legais de qualidade similar

| Provedor | URL | Licença |
|----------|-----|---------|
| **Esri World Imagery** | `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}` | Gratuita para uso não-comercial |
| **Bing Aerial** (via leaflet-bing-layer) | Requer API key gratuita | Gratuita com key |
| **Mapbox Satellite** | Requer API key | Gratuita até 50k requests/mês |

#### Antes de ir para produção

- [ ] Substituir tiles Google por Esri World Imagery **ou** contratar Google Maps Platform
- [ ] Se Esri: adicionar atribuição `Esri, Maxar, Earthstar Geographics` conforme exigido
- [ ] Avaliar cobertura de satélite sobre área de operação antes de escolher provedor

#### Impacto na precisão do GCP

Independente do provedor de tiles, a precisão do posicionamento via clique no mapa é limitada pela resolução do satélite:

| Fonte de coordenada | Precisão horizontal | Uso recomendado |
|--------------------|--------------------|----------------|
| Google / Esri Satellite (clique) | ±1 a 5 m | Orientação geral do ortofoto |
| Open-Elevation / SRTM (altitude) | ±5 a 30 m | Altitude aproximada |
| GPS GNSS de campo | ±0.5 a 2 m | Topografia |
| GPS RTK de campo | ±1 a 3 cm | Topografia de precisão |

---

## Padrões Backend (Java/Spring Boot)

### Estrutura de Projeto

```
backend/
├── java-service/
│   ├── src/main/java/com/funcoes/
│   │   ├── controller/           # Controllers (máx 200 linhas)
│   │   ├── service/              # Services (máx 200 linhas)
│   │   ├── repository/           # JPA Repositories
│   │   ├── entity/               # Entidades JPA
│   │   ├── dto/                  # Data Transfer Objects
│   │   ├── util/                 # Utilitários
│   │   ├── config/               # Configurações
│   │   └── exception/            # Exceções customizadas
│   ├── src/test/java/           # Testes unitários
│   ├── pom.xml
│   └── mvnw
```

### Anotações e Injeção de Dependência

**✅ SEMPRE use constructor injection:**

```java
@Service
public class ProjectService {
    private final ProjectRepository repository;
    private final NotificationService notificationService;
    
    // Constructor injection via Lombok
    @RequiredArgsConstructor
    public ProjectService(
        ProjectRepository repository,
        NotificationService notificationService
    ) {
        this.repository = repository;
        this.notificationService = notificationService;
    }
}
```

**❌ NUNCA use field injection:**

```java
// ERRADO - difícil de testar
@Service
public class ProjectService {
    @Autowired
    private ProjectRepository repository;
}
```

### Métodos de Service

**Organize métodos por responsabilidade:**

```java
@Service
@RequiredArgsConstructor
@Slf4j
public class ProjectService {
    private final ProjectRepository repository;
    
    // ===== CRUD Básico =====
    public Project createProject(CreateProjectDTO dto) {
        Project project = new Project();
        project.setName(dto.getName());
        return repository.save(project);
    }
    
    public Project getProjectById(Long id) {
        return repository.findById(id)
            .orElseThrow(() -> new ResourceNotFoundException("Project not found"));
    }
    
    // ===== Queries Customizadas =====
    public List<Project> getUserProjects(Long userId) {
        return repository.findByUserId(userId);
    }
    
    // ===== Validações =====
    private void validateProjectData(Project project) {
        if (project.getName() == null || project.getName().isEmpty()) {
            throw new ValidationException("Project name is required");
        }
    }
}
```

### DTOs vs Entities

**✅ Use DTOs para API:**

```java
// DTO para criar projeto
@Data
@Builder
public class CreateProjectDTO {
    @NotBlank(message = "Name is required")
    private String name;
    private String description;
}

// Entity para persistência
@Entity
@Table(name = "projects")
@Data
@NoArgsConstructor
@AllArgsConstructor
public class Project {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    
    @Column(nullable = false)
    private String name;
    
    private String description;
    
    @ManyToOne
    @JoinColumn(name = "user_id")
    private User user;
}
```

### Tratamento de Exceções

```java
@RestControllerAdvice
@Slf4j
public class GlobalExceptionHandler {
    
    @ExceptionHandler(ResourceNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public ErrorResponse handleNotFound(ResourceNotFoundException ex) {
        log.warn("Resource not found: {}", ex.getMessage());
        return ErrorResponse.builder()
            .message(ex.getMessage())
            .status(404)
            .build();
    }
    
    @ExceptionHandler(ValidationException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ErrorResponse handleValidation(ValidationException ex) {
        log.warn("Validation error: {}", ex.getMessage());
        return ErrorResponse.builder()
            .message(ex.getMessage())
            .status(400)
            .build();
    }
}
```

### Logging

**Use Lombok @Slf4j e estruture logs:**

```java
@Service
@Slf4j
public class ProjectService {
    
    public Project createProject(CreateProjectDTO dto) {
        log.info("[INFO] Creating project: {}", dto.getName());
        
        try {
            Project project = new Project();
            project.setName(dto.getName());
            Project saved = repository.save(project);
            log.info("[OK] Project created with ID: {}", saved.getId());
            return saved;
        } catch (Exception e) {
            log.error("[ERRO] Failed to create project", e);
            throw new RuntimeException("Failed to create project", e);
        }
    }
}
```

---

## Padrões Scripts (PowerShell/Shell/Bash)

### Estrutura de um Script PowerShell

```powershell
# ============================================================================
# Script: start-application.ps1
# Descrição: Inicia a aplicação com Docker Compose
# Uso: .\start-application.ps1
# ============================================================================

param(
    [Parameter(Mandatory=$false)]
    [string]$Environment = "development"
)

# ===== Configuração =====
$script:ScriptDir = Split-Path -Parent $MyInvocation.MyCommandPath
$script:ProjectRoot = Split-Path -Parent $ScriptDir
$script:LogFile = "$ProjectRoot\logs\start-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

# ===== Funções Auxiliares =====

function Write-LogInfo {
    param([string]$Message)
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Host "[$timestamp] [INFO] $Message" -ForegroundColor Cyan
    Add-Content -Path $script:LogFile -Value "[$timestamp] [INFO] $Message"
}

function Write-LogOk {
    param([string]$Message)
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Host "[$timestamp] [OK] $Message" -ForegroundColor Green
    Add-Content -Path $script:LogFile -Value "[$timestamp] [OK] $Message"
}

function Write-LogError {
    param([string]$Message)
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Write-Host "[$timestamp] [ERRO] $Message" -ForegroundColor Red
    Add-Content -Path $script:LogFile -Value "[$timestamp] [ERRO] $Message"
}

function Test-DockerInstalled {
    try {
        docker --version | Out-Null
        return $true
    } catch {
        return $false
    }
}

# ===== Fluxo Principal =====

Write-LogInfo "Iniciando aplicacao ($Environment)"

if (-not (Test-DockerInstalled)) {
    Write-LogError "Docker nao encontrado. Instale Docker Desktop para continuar."
    exit 1
}

Write-LogInfo "Validando Docker Compose..."
try {
    Push-Location $ProjectRoot
    docker-compose pull
    Write-LogOk "Docker Compose validado"
} catch {
    Write-LogError "Falha ao validar Docker Compose: $_"
    Pop-Location
    exit 1
}

Write-LogInfo "Iniciando containers..."
try {
    docker-compose up -d
    Write-LogOk "Containers iniciados com sucesso"
} catch {
    Write-LogError "Falha ao iniciar containers: $_"
    Pop-Location
    exit 1
}

Pop-Location
Write-LogOk "Aplicacao iniciada em http://localhost:8088"
```

### Estrutura de um Script Shell/Bash

```bash
#!/bin/bash

# ============================================================================
# Script: start-application.sh
# Descrição: Inicia a aplicação com Docker Compose
# Uso: ./start-application.sh
# ============================================================================

set -e  # Exit on error

# ===== Configuração =====
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_ROOT/logs/start-$(date +%Y%m%d-%H%M%S).log"

# ===== Funções de Log =====

log_info() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [INFO] $message" | tee -a "$LOG_FILE"
}

log_ok() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [OK] $message" | tee -a "$LOG_FILE"
}

log_error() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [ERRO] $message" | tee -a "$LOG_FILE"
}

# ===== Validações =====

check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker nao encontrado. Instale Docker para continuar."
        exit 1
    fi
}

# ===== Fluxo Principal =====

mkdir -p "$PROJECT_ROOT/logs"

log_info "Iniciando aplicacao"

check_docker
log_ok "Docker validado"

cd "$PROJECT_ROOT"

log_info "Validando Docker Compose..."
docker-compose pull || {
    log_error "Falha ao validar Docker Compose"
    exit 1
}

log_info "Iniciando containers..."
docker-compose up -d || {
    log_error "Falha ao iniciar containers"
    exit 1
}

log_ok "Aplicacao iniciada em http://localhost:8088"
```

### Convenções de Scripts

| Elemento | Padrão | Exemplo |
|----------|--------|---------|
| Nomes | `kebab-case` | `start-application.sh` |
| Marcadores | ASCII `[OK]` `[ERRO]` | Nunca emojis |
| Encoding | UTF-8 sem BOM | Consistente |
| Exit codes | 0 = sucesso, 1+ = erro | `exit 1` |
| Logs | Timestamp + nível | `[2026-03-12 10:30:45] [INFO]` |

---

## Banco de Dados (PostgreSQL)

### Estrutura de Migrations

```
backend/java-service/src/main/resources/db/migration/
├── V1__initial_schema.sql
├── V2__add_gcp_table.sql
├── V3__add_measurements_table.sql
└── V4__optimize_queries.sql
```

### Padrão de Migrations

```sql
-- V1__initial_schema.sql
-- ============================================================================
-- Descrição: Schema inicial do banco de dados
-- Data: 2026-03-12
-- ============================================================================

-- Tabela de usuários
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_email (email)
);

-- Tabela de projetos
CREATE TABLE IF NOT EXISTS projects (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_status (status)
);
```

### Otimizações de Query

**✅ USE índices inteligentemente:**

```sql
-- Index em coluna frequentemente filtrada
CREATE INDEX idx_projects_user_status ON projects(user_id, status);

-- Query otimizada
SELECT * FROM projects 
WHERE user_id = 123 AND status = 'ACTIVE'
ORDER BY created_at DESC;
```

**✅ EVITE N+1 queries:**

```java
// ❌ Ruim - N+1 queries
List<Project> projects = repository.findAll();
for (Project project : projects) {
    User user = userRepository.findById(project.getUserId());  // N queries!
}

// ✅ Bom - 1 query com JOIN
@Query("SELECT p FROM Project p JOIN FETCH p.user")
List<Project> findAllWithUsers();
```

### Connection Pool

```properties
# application.properties
spring.datasource.hikari.maximum-pool-size=20
spring.datasource.hikari.minimum-idle=5
spring.datasource.hikari.connection-timeout=30000
spring.datasource.hikari.idle-timeout=600000
spring.jpa.properties.hibernate.jdbc.batch_size=20
```

---

## Testes

### Estrutura de Testes

```
backend/java-service/src/test/java/com/funcoes/
├── controller/
│   └── ProjectControllerTest.java
├── service/
│   └── ProjectServiceTest.java
├── repository/
│   └── ProjectRepositoryTest.java
└── util/
    └── ProjectTestDataBuilder.java
```

### Testes Unitários

**Use JUnit 5 + Mockito:**

```java
@ExtendWith(MockitoExtension.class)
class ProjectServiceTest {
    
    @Mock
    private ProjectRepository repository;
    
    @InjectMocks
    private ProjectService service;
    
    @Test
    @DisplayName("Should create project successfully")
    void createProjectSuccess() {
        // Arrange
        CreateProjectDTO dto = CreateProjectDTO.builder()
            .name("Test Project")
            .build();
        
        Project expected = Project.builder()
            .id(1L)
            .name("Test Project")
            .build();
        
        given(repository.save(any()))
            .willReturn(expected);
        
        // Act
        Project result = service.createProject(dto);
        
        // Assert
        assertThat(result)
            .isNotNull()
            .hasFieldOrPropertyWithValue("name", "Test Project");
        
        verify(repository).save(any());
    }
    
    @Test
    @DisplayName("Should throw exception when project name is empty")
    void createProjectThrowsException() {
        // Arrange
        CreateProjectDTO dto = CreateProjectDTO.builder()
            .name("")
            .build();
        
        // Act & Assert
        assertThatThrownBy(() -> service.createProject(dto))
            .isInstanceOf(ValidationException.class);
    }
}
```

### Testes de Integração

**Use @SpringBootTest + TestContainers:**

```java
@SpringBootTest
@ActiveProfiles("test")
class ProjectServiceIntegrationTest {
    
    @Autowired
    private ProjectService service;
    
    @Autowired
    private ProjectRepository repository;
    
    @BeforeEach
    void setUp() {
        repository.deleteAll();
    }
    
    @Test
    @DisplayName("Should persist project to database")
    void createProjectIntegration() {
        // Arrange
        CreateProjectDTO dto = CreateProjectDTO.builder()
            .name("Integration Test Project")
            .build();
        
        // Act
        Project result = service.createProject(dto);
        
        // Assert
        Project persisted = repository.findById(result.getId()).orElseThrow();
        assertThat(persisted.getName()).isEqualTo("Integration Test Project");
    }
}
```

### Executar Testes

```bash
# Frontend - Angular
npm test

# Backend - Maven
cd backend/java-service
./mvnw test

# Com cobertura
./mvnw test jacoco:report
# Resultado: target/site/jacoco/index.html
```

### Cobertura Mínima

| Tipo | Cobertura | Observação |
|------|-----------|-----------|
| **Services** | 80% | Toda lógica de negócio |
| **Controllers** | 70% | Validação de input/output |
| **Utils** | 90% | Funções críticas |
| **Componentes UI** | 60% | Template + lógica |
| **Global** | 75% | Mínimo aceitável |

---

## Recursos Adicionais

- [Angular Style Guide](https://angular.io/guide/styleguide)
- [Spring Boot Best Practices](https://spring.io/guides/gs/rest-service/)
- [VISION.md](VISION.md) - Visão do projeto
- [Documentação Completa](../README.md) - Índice de documentação

---

**Última atualização**: 12 de março de 2026
