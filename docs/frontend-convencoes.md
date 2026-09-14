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

## 6. Busca por texto — nunca compare acento

**Decisão do dono (16/08/2026):** *"quero que todo o software seja acessível, ninguém tem que ficar
digitando exatamente a palavra para conseguir achar o que quer"*. Quem digita rápido digita sem
acento, e no celular do canteiro ninguém caça o `ç`. Busca que exige `Fundação` para achar `Fundação`
faz a pessoa concluir que **o dado não existe** — a pior forma de falha, porque não parece falha.

Filtro que roda na tela usa **exclusivamente** `@/utils/texto.ts`:

```ts
import { contemSemAcento } from '@/utils/texto'

const visiveis = itens.filter(i => contemSemAcento(i.nome, termo))
```

Nunca `.toLowerCase().includes(...)` em texto que a pessoa digitou. `normalizar()` está exposto para
quem precisa da chave normalizada (ordenação, agrupamento).

**As duas pontas precisam da mesma régua.** No servidor, quem faz o mesmo é
[`nucleo/busca.py`](../backend/nucleo/busca.py) — o `BuscaSemAcento` já é o `filter_backend` de toda
view com `search_fields`. Uma busca que o servidor resolve sem acento e a tela refiltra **com** acento
devolve menos do que veio, e o sintoma é o pior possível: a lista pisca com o resultado certo e some.

Limite declarado: `ß` e `ø` não são letra + sinal, sobrevivem à decomposição e não são normalizados.
Nenhum aparece em nome de disciplina, obra ou insumo de projeto brasileiro.

## 7. Botões inativos — como funciona e como ativar um módulo

Itens sem acesso aparecem **inativos** — visíveis mas não clicáveis. Intencional: mostra o alcance
da edição sem enganar sobre o que está disponível.

- **Sidebar (`AppSidebar.tsx`) — farol da edição:** a sidebar mostra **sempre todos os itens da
  edição atual** (nunca esconde por falta de entitlement). Um item é navegável (`<NavLink>`) só quando
  `interativo = implemented && (sem module || hasModule(module)) && (não adminOnly || isTenantAdmin)`;
  caso contrário vira `<span>` travado (`<Lock>`, opacidade ~72%) com o motivo no `title`
  (`Módulo não contratado` / `Somente administradores` / `Em breve`/`Em construção`). **O farol é por
  edição/tipo:** a Construtora não lista módulos exclusivos de outra vertical (Loja, Imobiliária) e
  vice-versa — cada edição tem o seu conjunto de itens ([frontend.md §3.2](frontend.md)).
- **Hub (`AppHomePage.tsx`):** `implemented: false` → botão "Acessar" `disabled`; módulo pago não
  contratado (`!hasModule(code)`) → "Contratar módulo", independente de `implemented`.

### Como ativar um módulo concluído

1. Em `AppSidebar.tsx`: setar `implemented: true` no item correspondente.
2. Em `AppHomePage.tsx`: setar `implemented: true` e adicionar `route: '/app/<modulo>'` no catálogo.
3. Em `App.tsx`: adicionar as rotas `<Route path="<modulo>" element={<ListPage />} />` etc.
4. Reconstruir o container React — ver o procedimento e o **gotcha de cache do browser** em
   [desenvolvimento.md](desenvolvimento.md#rebuild-do-frontend-react-gotcha-de-cache).


## 8. Excluir: a tela não pode dizer que é irreversível (D116)

Desde a lixeira, **excluir marca a lápide** — o registro sai das listagens e volta inteiro dentro do
prazo do plano. Toda mensagem de confirmação que diz *"esta ação não pode ser desfeita"* passou a ser
**falsa**, e a falsidade custa dos dois lados: assusta quem ia excluir e **esconde o recurso que o
cliente pagou** (`lixo_retencao_dias` é a paywall da lixeira, §5.5g do `planos.py`).

Use o componente, nunca escreva a frase à mão:

```tsx
import { AvisoDaLixeira } from '@/components/AvisoDaLixeira'
...
<AvisoDaLixeira oQue="A obra" />
```

Para diálogo nativo (`window.confirm`, que não aceita JSX):

```tsx
const textoLixeira = useTextoDaLixeira()   // '@/hooks/useRetencaoDoLixo'
if (confirm(textoLixeira('este lead'))) { ... }
```

**O prazo vem do servidor**, da chave `janelas` de `/api/plano/` — nunca de uma constante no
frontend. O número é por plano (3 dias no `free`, 15 nos contratados, 30 no Sob Medida), e um `15`
escrito em código prometeria duas semanas a quem tem três dias. Sem o prazo carregado, o componente
promete a lixeira mas **não** promete prazo: melhor omitir que mostrar o número errado.

**Só onde o modelo tem lixeira.** Prometer restauração para o que é apagado de verdade é a mentira
oposta, e a pior das duas — a pessoa exclui confiando que dá para voltar. Hoje herdam `Excluivel`:
`Obra`, `EtapaObra`, `DocumentoObra`, `Empreendimento`, `Cliente`, `ClienteEmpreendimento`,
`ContratoCliente`, `Fornecedor`, `ContaPagar`, `ContaReceber`, `NotaFiscal`, `Cargo`, `Funcionario`,
`Lead`, `Account`, `Opportunity`, `Orcamento`. O `Contact` do CRM **não** herda — a mensagem dele continua sem
lixeira, de propósito.

**E não vale para o que sai da nossa máquina.** Cancelar boleto no Asaas e cancelar NFS-e na NFE.io
são irreversíveis de verdade: aquelas mensagens estão certas e ficam como estão. Ter lixeira aqui não
desfaz ato em sistema de terceiro.

## Visibilidade: omitir × trancar

Regra de 22/08/2026, com a fronteira escrita para não virar caso a caso:

- **trancar** (cadeado + motivo) — o caminho existe para aquele usuário e ele pode
  destravá-lo: módulo não contratado, área que exige admin do tenant. O cadeado é
  informação útil, e às vezes é venda;
- **omitir** (`platformOnly`) — o caminho **não é dele em hipótese alguma**:
  operação de plataforma, que nenhum tenant contrata. Mostrar trancado anuncia uma
  porta que não é para o lado de cá.

A rota acompanha: quem tranca explica (`AccessNotice`); quem omite redireciona em
silêncio (`PlatformRoute`). Detalhe em [frontend.md](frontend.md).
