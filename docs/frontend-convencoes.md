# Frontend — Convenções de código

> **Leitura obrigatória antes de tocar o frontend.** Regras que valem para todo componente novo;
> a planta (design system, páginas, rotas, camada de dados) está em [frontend.md](frontend.md).
> Violações típicas: declarar máscara de CPF local num componente, parsear data manualmente,
> montar upload sem `useFileUpload`.

## Convenções gerais

- Componentes: PascalCase, um por arquivo
- Hooks: `use` prefix, em `hooks/` do módulo
- Estilos: Tailwind classes inline; `cn()` para condicionais; sem arquivos `.css` por componente
- Tipos: interfaces explícitas em `types/index.ts` (domínio) ou inline no módulo (local)
- Imports: aliases `@/` mapeando para `src/` (configurado em `tsconfig.app.json` + `vite.config.ts`)
- Sem comentários explicativos — nomes descritivos fazem o trabalho
- Sem `any` — `unknown` onde necessário

## 1. Erros de formulário

Todos os formulários usam as utilidades de `@/utils/formErrors.ts`:

```ts
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'

// No catch do handleSubmit:
setFieldErrors(parseApiErrors(err))   // erros por campo do DRF → FieldErrors

// No JSX:
<FieldError msg={fieldErrors.nome_campo} />   // inline abaixo do input (⚠ msg)
<FormErrorBanner errors={fieldErrors} />       // banner para erros gerais (_form)
```

`FieldErrors = Record<string, string>`. O campo especial `_form` é reservado para erros não
vinculados a um campo específico.

## 2. CPF, CNPJ e CPF/CNPJ

Toda interação com esses campos usa **exclusivamente** `@/utils/masks.ts`. Nunca declarar funções
locais de máscara ou validação de CPF/CNPJ em componentes.

| Situação | Função |
|---|---|
| Digitação em input CPF | `maskCPF(v)` → valor exibido no `value={}` |
| Digitação em input CNPJ | `maskCNPJ(v)` → valor exibido no `value={}` |
| Digitação em input CPF ou CNPJ | `maskCPFCNPJ(v)` → adapta máscara conforme o comprimento |
| Validação no `onBlur` / submit | `validateCPF(d)` · `validateCNPJ(d)` · `validateCPFCNPJ(d)` → `null` (válido) ou mensagem de erro |
| Exibição somente-leitura | `formatCPF(v)` · `formatCNPJ(v)` · `formatCPFCNPJ(v)` — aceita dígitos brutos ou valor já formatado |

**Padrão de armazenamento:** o estado do formulário guarda **dígitos puros** (sem pontuação). A
máscara é aplicada apenas no `value={}` do input. O payload enviado à API também vai com dígitos puros.

```tsx
// Armazena dígitos puros; exibe com máscara
<input
  value={maskCPF(form.cpf)}
  onChange={e => {
    setFieldErrors(prev => ({ ...prev, cpf: '' }))
    set('cpf', e.target.value.replace(/\D/g, ''))
  }}
  onBlur={() => {
    const err = validateCPF(form.cpf)
    if (err) setFieldErrors(prev => ({ ...prev, cpf: err }))
  }}
/>
```

## 3. Datas

Toda lógica de data usa **exclusivamente** `@/utils/dates.ts`. Nunca declarar `parseDateBR`,
`maskDate` ou constantes de limites localmente em componentes.

| Situação | Função/Constante |
|---|---|
| Máscara DD/MM/AAAA ao digitar | `maskDate(v)` |
| Parse DD/MM/AAAA → Date | `parseDateBR(br)` → `Date \| null` |
| Converter DD/MM/AAAA → YYYY-MM-DD (payload) | `dateFromBR(br)` |
| Converter YYYY-MM-DD → DD/MM/AAAA (display) | `dateToBR(iso)` |
| Atributo `min=` / `max=` em `type="date"` | funções `min*/max*ISO()` (dinâmicas — recalculam "hoje") |
| Validar `type="date"` onBlur | `validateISO_Nasc` · `validateISO_Vigencia` · `validateISO_Pagamento` · `validateISO_ExameASO` · `validateISO_ValidadeASO` |
| Validar DD/MM/AAAA onBlur | `validateDataNasc` · `validateDataAdmissao` · `validateDataDemissao` |

**Limites por categoria:**

| Categoria | Min | Max | Uso |
|---|---|---|---|
| Nascimento | 01/01/1900 | hoje | `data_nascimento` (clientes, funcionários) |
| Admissão/Demissão | 01/01/1940 | hoje + 2 anos | `data_admissao`, `data_demissao` |
| Vigência/Contrato | hoje − 10 anos | hoje + 20 anos | datas de obra, etapa, empreendimento, contrato, ASO |
| Pagamento | hoje − 1 ano | hoje + 5 anos | `data_pagamento`, `data_compra`, `data_custo`, `mes_referencia` |

**Padrão onBlur:**
```tsx
<input type="date"
  min={minVigenciaISO()} max={maxVigenciaISO()}
  onChange={e => { set('data_inicio_prevista', e.target.value); setFieldErrors(p => ({ ...p, data_inicio_prevista: '' })) }}
  onBlur={e => { const err = validateISO_Vigencia(e.target.value); if (err) setFieldErrors(p => ({ ...p, data_inicio_prevista: err })) }} />
```

## 4. Upload e download de arquivos

Use `@/utils/fileUpload.ts` para operações de arquivo e `@/hooks/useFileUpload.ts` para estado
reativo em componentes.

```ts
// Hook em componentes:
const { upload, download, validate, loading, progress, error, acceptAttr, config } = useFileUpload()

// Upload com progresso:
const result = await upload('/api/documentos-funcionarios/', 'arquivo', file, { funcionario: id })

// Download autenticado:
await download('/api/documentos-funcionarios/42/arquivo/', 'contrato.pdf')

// Validação local antes de mostrar o picker:
const err = validate(file)  // retorna null se OK, ou mensagem de erro
```

A configuração de tamanho máximo e tipos aceitos é editável pelo administrador em `/admin/` →
**Configurações de Arquivos**. O hook busca esses parâmetros da API
(`GET /api/configuracoes/upload/`) e cai nos padrões (10 MB · PDF/JPG/PNG/XLSX/DOCX) se o endpoint
não responder.

## 5. Dinheiro

Valores monetários trafegam como **centavos inteiros** na UI — use **exclusivamente**
`@/utils/money.ts` (`formatBRL` · `maskMoney` · `digitsToCents` · `centsToApiDecimal` ·
`apiDecimalToCents`) e os componentes `MoneyInput`/`MoneyDisplay` do ERP. Nunca `parseFloat` em
valor monetário.

## 6. Botões inativos — como funciona e como ativar um módulo

Módulos ainda não implementados aparecem como **itens inativos** — visíveis mas não clicáveis.
Intencional: mostra o que existe na plataforma sem enganar sobre o que está disponível.

- **Sidebar (`AppSidebar.tsx`):** item com `implemented: false` renderiza como `<span>` com cadeado
  `<Lock>` e opacidade 60%; com `implemented: true`, vira `<NavLink>` navegável.
- **Hub (`AppHomePage.tsx`):** `implemented: false` → botão "Acessar" `disabled`; módulo pago não
  contratado (`!hasModule(code)`) → "Contratar módulo", independente de `implemented`.

### Como ativar um módulo concluído

1. Em `AppSidebar.tsx`: setar `implemented: true` no item correspondente.
2. Em `AppHomePage.tsx`: setar `implemented: true` e adicionar `route: '/app/<modulo>'` no catálogo.
3. Em `App.tsx`: adicionar as rotas `<Route path="<modulo>" element={<ListPage />} />` etc.
4. Reconstruir o container React — ver o procedimento e o **gotcha de cache do browser** em
   [desenvolvimento.md](desenvolvimento.md#rebuild-do-frontend-react-gotcha-de-cache).
