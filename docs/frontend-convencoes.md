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

### Erro sem escrita não é erro (D187)

*(Decisão do dono, 20/09/2026, depois de ver a página de 502 do nginx inteira dentro de um diálogo:
"ninguém sabe o que é isso".)*

**Toda saída do `parseApiErrors` é uma frase em português.** Não existe caminho que devolva o corpo
cru da resposta, e a razão é que os corpos que chegam ali nem sempre são da API: um 502 traz HTML do
nginx, uma rede caída não traz nada, e um 500 em modo de depuração traz a página do Django. Nenhum
dos três é mensagem; os três são a encanação do sistema aparecendo na tela de quem está trabalhando.

Quem separa os casos é o **`status`**, nunca o corpo. E cada frase responde às duas perguntas que a
pessoa tem naquele instante:

1. **de quem é o problema** — dela, da rede, ou nosso. Sem isso ela não tenta de novo, porque conclui
   que digitou algo errado;
2. **se o que ela escreveu se perdeu.** É a parte acionável. Num 502 a requisição não chegou a ser
   processada, então nada foi gravado e o certo é repetir — e sem essa frase ninguém sabe se o que
   acabou de registrar existe.

Os três buracos que a regra fecha, e que valem como lista de conferência para qualquer tradutor de
erro novo: corpo em **HTML**, resposta **ausente**, e corpo **JSON vazio** (`{}` sai do laço sem uma
única frase e a tela mostra espaço em branco onde deveria estar a explicação).

> **Como se prova isso sem derrubar nada:** o teste de navegador forja o 502 com `page.route()` e
> confere que a página do nginx **não** aparece. Derrubar o backend no meio de uma suíte que divide
> máquina atingiria outra sessão — e o que se está provando é a tela, não o gateway.

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
| Atributo `min=` / `max=` em `type="date"` | **`minCalendarioISO` / `maxCalendarioISO`** — sempre os dois, sempre esses |
| Validar `type="date"` onBlur | `validateISO_Calendario` · `validateISO_Nasc` · `validateISO_Vigencia` · `validateISO_Pagamento` · `validateISO_ExameASO` · `validateISO_ValidadeASO` |
| Validar DD/MM/AAAA onBlur | `validateDataNasc` · `validateDataAdmissao` · `validateDataDemissao` |

### A faixa do calendário é uma só: **1900–2100**

**Decisão do dono (15/09/2026):** *"Data mínima e máxima de todo o calendário é 1900 e 2100"* — em
todo campo de data, **sem exceção**.

Antes, cada família tinha a sua janela e **todas andavam com o relógio**: vigência era `hoje−10 …
hoje+20`, pagamento era `hoje−1 … hoje+5`. O sintoma foi achado no Expediente do PDCA, que usa a
família da vigência para a data de exceção do calendário: em 15/09/2026 o seletor abria em
**2016–2046**, e não havia como cadastrar o feriado de 2047. Janela que anda com o relógio é pior do
que janela estreita — a mesma tela aceita hoje o que vai recusar no ano que vem, e ninguém consegue
explicar o porquê para quem está do outro lado.

**O `min`/`max` do input não é o lugar da regra de negócio.** Ele apaga o dia do calendário do
navegador **sem dizer nada**: a pessoa clica, não acontece nada, e a conclusão dela é que o sistema
travou. O que é absurdo continua recusado, mas pelos **validadores**, que têm frase:

| Regra | Onde ela vive | O que a pessoa vê |
|---|---|---|
| 1900–2100 | `min`/`max` do input | o calendário do navegador, com 200 anos |
| Nascimento não pode ser futuro | `validateISO_Nasc` / `validateDataNasc` | *"Data de nascimento não pode ser futura."* |
| Exame de ASO não pode ser futuro | `validateISO_ExameASO` | *"A data do exame não pode ser futura."* |
| Demissão ≥ admissão | `validateDataDemissao` | *"Data de demissão deve ser posterior à admissão."* |

`minNascISO`, `minVigenciaISO()`, `maxPagamentoISO()` e companhia continuam exportadas como
**apelidos** da faixa única: o nome diz em que campo o valor está sendo usado e continua legível no
JSX, e mudar a faixa de todos é mudar duas constantes. Nenhuma delas anda mais com o relógio.
`maxTodayISO()` sobreviveu, mas **deixou de ser `max` de input** — é o que os validadores de "não pode
ser futura" comparam, e o que a tela usa como valor padrão.

**Padrão onBlur:**
```tsx
<input type="date"
  min={minCalendarioISO} max={maxCalendarioISO}
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

> **Esta regra já foi descumprida em silêncio por nove filtros** ([D163](historico-correcoes.md),
> 16/09/2026). O helper existia, o backend cumpria a régua, e nove listas client-side continuavam em
> `.toLowerCase().includes()` — o dono achou pelo filtro de obras do Orçar. Ao escrever filtro novo,
> a pergunta é *"o termo veio de um teclado?"*: se veio, `contemSemAcento`.

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

## 9. O texto da tela é para quem opera, não para quem escreveu o sistema

Regra de 15/09/2026, nascida de uma frase que o dono leu na medição por administração:

> *"O número é declarado — a apropriação automática de HH ainda não existe, e o boletim diz isso em
> vez de fingir que o sistema apurou."* — **"que mensagem bosta pro usuário final"**

Ela estava **correta** e era inútil: respondia à pergunta de quem escreveu o software (*por que este
campo é digitado?*) e não à de quem está na frente do campo (*o que eu escrevo aqui?*). O trecho
final é pior que jargão — é o software se defendendo de uma acusação que ninguém fez.

**A divisão, e ela é simples:**

| Onde | O que responde | Vocabulário |
|---|---|---|
| Comentário de código / docstring | *por que é assim*, para quem mantém | fatia, planta, §, seam, achado, RLS |
| String da tela | *o que a pessoa está tentando fazer agora* | o da obra: custo, medição, folha, nota |

Na prática, três coisas que **não** entram em texto visível: número de fatia (`PDCA.9`), referência
de documento interno (`§4.9`, "a planta diz") e defesa do próprio comportamento ("em vez de fingir",
"não é um bug"). Se a razão de engenharia parece necessária na tela, quase sempre o que falta é a
**instrução**: *"Confira com a folha, as notas e o material aplicado no período."*

**Aviso que aparece sempre e não pede ação não é aviso, é ruído** — e ensina a ignorar a faixa onde
um dia aparece algo que importa. O registro do fato (quem informou o número, quando) vai para o
**documento**, que é onde alguém o lê ao decidir.

## 10. Campo que não aceita digitação não é campo

`<input readOnly>` tem borda, cursor e fundo de campo: convida a clicar e não aceita nada. Em
leitura, **número é texto**.

Achado em 15/09/2026, com o elemento colado pelo dono: *"a parte mais importante da medição não
consigo editar"* — era a grade da **prévia**, somente leitura por desenho, e a tela não dizia isso em
lugar nenhum. Vale para toda grade: `somenteLeitura` troca o `input` por um `<span>` alinhado, e a
tela diz onde se digita.

## 11. Regra que mora só na interface não é regra — é aviso

Também de 15/09/2026, e o achado foi caro: a tela do contrato afirmava *"a planilha não se edita mais
aqui"* enquanto a API aceitava o `PATCH` — o dono mudou uma quantidade contratada de 53.150 para
631.500 em segundos. Uma prop `editavel` não protege o comando de bancada, a importação, nem a aba
antiga aberta no navegador.

**O padrão, nesta ordem:**

1. a regra vira **uma função** no serviço, que devolve *se* e *por quê*
   (`services.planilha_editavel → (bool, motivo)`);
2. a **view** a aplica — é ela que protege todos os caminhos de escrita;
3. o **serializer** a publica (`planilha_editavel`, `planilha_fechada_porque`), e a tela **lê a
   resposta** em vez de reimplementar a condição.

O terceiro passo é o que impede a tela e a API de divergirem — e é o que permite a mensagem na tela
ser exatamente a mesma que a API devolveria.

**Corolário:** antes de fechar um caminho, procure o beco. A primeira versão dessa trava fechou a
planilha por *status do contrato*, e criou um pior que o defeito — contrato vigente **sem itens**
ficava impossível de preencher, com a tela pedindo "cadastre os itens" e nenhuma porta. Toda trava
nova merece a pergunta: *qual estado legítimo eu acabei de tornar impossível?*

## 12. Mensagem que manda fazer algo mostra o caminho

*"Este contrato ainda não tem planilha contratual. Cadastre os itens para poder medir."* — e o dono
procurou o botão e não achou, porque ele estava em outra tela.

Estado vazio que pede uma ação ou **traz o botão** que leva até ela, ou não deveria estar pedindo.
Na grade de medição isso virou uma prop (`acaoVazia`) que a página preenche com o caminho certo;
noutros lugares é um link. A régua: ninguém deveria precisar adivinhar onde fica o que a tela
acabou de mandar fazer.

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
