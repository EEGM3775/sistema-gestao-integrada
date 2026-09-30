# Convenções — FuncoesODM

> Referência rápida de padrões obrigatórios do projeto.  
> Sem histórico, sem narrativa — só as regras.

---

## Encoding / Emojis

**Proibido em todo código executável:**

```
.ps1  .bat  .sh  .ts  .java  .py  .json  .sql
```

**Obrigatório em código:**

| Marcador | Uso |
|----------|-----|
| `[OK]` | Sucesso |
| `[ERRO]` | Erro crítico |
| `[AVISO]` | Atenção |
| `[INFO]` | Informação |
| `[DEBUG]` | Debug |

**Encoding por tipo de arquivo:**

| Tipo | Encoding |
|------|----------|
| `.ps1` | UTF-8 SEM BOM |
| `.bat` | ASCII / Windows-1252 |
| `.sh` | UTF-8 sem BOM |
| `.ts`, `.java`, `.html`, `.scss`, `.json` | UTF-8 sem BOM |
| `.md` | UTF-8 (emojis permitidos) |

---

## Angular

**Componente base obrigatório:**
```typescript
@Component({
  selector: 'app-nome',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [...],
  templateUrl: './nome.component.html',
  styleUrls: ['./nome.component.scss']
})
```

**Estado → Signals. HTTP/async → RxJS:**
```typescript
// Estado local
items = signal<Item[]>([]);
count = computed(() => this.items().length);
isLoading = signal(false);

// HTTP
this.http.get<Item[]>('/api/items')
  .pipe(takeUntilDestroyed())
  .subscribe(data => this.items.set(data));
```

**Template:**
```html
<!-- Iteração -->
@for (item of items(); track item.id) { ... }

<!-- Condicional -->
@if (isLoading()) { <app-spinner /> } @else { ... }
```

**Limites de tamanho:**

| Tipo | Máximo | Crítico |
|------|--------|---------|
| Componente `.ts` | 300 linhas | 500 |
| Service `.ts` | 200 linhas | 400 |
| Template inline | 30 linhas | 50 |

Se ultrapassar → extrair sub-componente ou service.

**Lazy loading obrigatório para features:**
```typescript
{ path: 'projects', loadComponent: () => import('./features/projects/...') }
```

**Memory leaks — sempre usar:**
```typescript
private destroyRef = inject(DestroyRef);
observable$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(...)
```

---

## Nomenclatura

| Artefato | Padrão | Exemplo |
|----------|--------|---------|
| Componente | `kebab-case.component.ts` | `project-card.component.ts` |
| Service | `kebab-case.service.ts` | `measurement-api.service.ts` |
| Model | `kebab-case.model.ts` | `measurement-data.ts` |
| Const | `kebab-case.const.ts` | `api-endpoints.const.ts` |
| Spec | `mesmo-nome.spec.ts` | `project-card.component.spec.ts` |
| Seletor | `app-kebab-case` | `app-meas-drawing-toolbar` |

---

## Estrutura de Feature

```
features/nome-feature/
├── nome-feature.component.ts     # Orquestrador (coordena, não lógica)
├── nome-feature.component.html
├── nome-feature.component.scss
├── components/
│   └── sub-a/
│       ├── sub-a.component.ts
│       ├── sub-a.component.html
│       └── sub-a.component.scss
├── services/
│   └── nome-feature.service.ts
└── models/
    └── nome-feature.model.ts
```

---

## Java / Spring Boot

**Pacotes:** `controller`, `service`, `model`, `repository`, `security`, `dto`, `exception`

**Validação obrigatória em DTOs:**
```java
public record CreateProjectRequest(
    @NotBlank String name,
    @NotNull @Valid List<@NotBlank String> tags
) {}
```

**Exceções customizadas:** `ResourceNotFoundException`, `UnauthorizedException`

**Ownership:** sempre validar via `ProjectSecurityService` antes de operar sobre recursos do usuário

---

## Checklist antes de commitar

- [ ] Nenhum `.ts` acima de 300 linhas
- [ ] Sem emojis em código executável
- [ ] Templates externos (não inline)
- [ ] `ChangeDetectionStrategy.OnPush` no componente
- [ ] `takeUntilDestroyed()` em subscriptions
- [ ] `track item.id` em `@for`
- [ ] `ng build` passa sem erros

---

**Referências completas:** [architecture/BEST_PRACTICES.md](architecture/BEST_PRACTICES.md)
