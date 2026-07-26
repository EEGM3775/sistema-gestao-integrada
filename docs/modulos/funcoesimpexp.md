# funcoesimpexp — importação e exportação de plataforma

> **App-fundação**, como o [catalogo](catalogo.md): não se vende, não tem entitlement próprio e
> nenhum módulo depende dele para existir. É o **motor** de entrada e saída de dados; cada módulo
> declara *o que* sai e entra, e o motor cuida do resto.

## 1. O que é e por que é fundação

Toda página que mostra dado acaba precisando de dois botões: **Exportar** e **Importar**. Hoje isso
existe em um módulo só — o [Orçamento](moduloorcamento.md) —, e existe **dentro dele**: leitor de
planilha, conferência linha a linha, escritor de XLSX e de PDF, tudo em `moduloorcamento/`. Funciona,
e é justamente por funcionar que precisa sair de lá: o segundo módulo que precisar da mesma coisa vai
copiar, e a partir da cópia as duas versões divergem. Divergência em leitor de planilha não aparece
como erro — aparece como **preço errado semanas depois**, e ninguém sabe de onde veio.

A função **não é vendável sozinha**: exportar a carteira de clientes é uma capacidade do módulo
Clientes, não um produto. Por isso não há entitlement `impexp`; quem autoriza é sempre o módulo dono
do dado (§3). Mesma classe do `catalogo`, mesmo lugar na arquitetura.

**A cobertura cresce sob demanda, um recurso por vez** — é assim por desenho, não por falta de plano.
O que este documento fixa não é a lista de recursos: é a **régua** (§2) e o **contrato de declaração**
(§4), para que o décimo segundo recurso se comporte exatamente como o primeiro.

## 2. A régua

Regras destiladas do que os softwares que fazem isso bem já provaram — django-import-export,
Salesforce Data Loader, Shopify, HubSpot, Stripe, Metabase, Sienge. Cada uma existe porque uma falha
concreta a exigiu. **Declaração que viola a régua não entra.**

| # | Regra | A falha que ela evita |
|---|---|---|
| **R1** | **Importar nunca é um `POST` que grava.** É `preparar → conferir → aplicar`, com veredito por linha (nova · duplicada · inválida) e parada obrigatória antes de tocar no destino. | Arquivo com coluna trocada entra inteiro e só aparece semanas depois, como dado estranho no meio de algo já aprovado. *(o `dry_run` do django-import-export, a prévia do HubSpot; já provado no ORC.5b)* |
| **R2** | **Uma declaração governa as três saídas:** a planilha-modelo que o usuário baixa, o validador da importação e o layout da exportação. Fonte única, sempre. | Modelo e validador nascem em lugares diferentes, um campo muda em um só, e o usuário preenche o modelo "certo" que a importação recusa — ou pior, aceita torto. |
| **R3** | **Chave de identidade declarada** (o *upsert key*): a coluna que decide se a linha cria ou atualiza. Sem chave, a declaração não é aceita. | Sem chave, "importar de novo" significa **duplicar tudo**. *(external ID do Salesforce Data Loader)* |
| **R4** | **De-para de colunas explícito.** O motor tenta casar por sinônimos; quando não casa, **mostra os cabeçalhos que viu** e deixa o operador mapear à mão — **nos dois caminhos, inclusive no job** (§7.1). Nunca adivinha. O mapa fica salvável para a importação recorrente. | Adivinhar cabeçalho é como preço vai para a coluna errada em silêncio. *(Power Query, Shopify)* |
| **R5** | **Erro volta como arquivo**: as linhas recusadas saem num XLSX com a linha original e o motivo, para corrigir e reenviar. | Numa carga de 4.000 linhas, "37 falharam" sem dizer quais obriga a refazer tudo. *(Shopify)* |
| **R6** | **Lote reversível.** Toda aplicação é um lote identificado e desfazível enquanto for o último; desfazer restaura o valor **e a procedência**. | Sem desfazer, o único conserto de uma carga ruim é restaurar backup — o que joga fora o trabalho legítimo do mesmo período. *(já provado na reprecificação do ORC.5b)* |
| **R7** | **Exportar entrega o recorte da tela** — os mesmos filtros, ordem e agrupamento que a pessoa está vendo, e nunca mais linhas do que ela veria. | Um export que ignora o filtro entrega 40.000 linhas para quem pediu 12, e um que ignora a permissão de linha vira porta paralela mais permissiva que a UI. *(Metabase, Retool)* |
| **R8** | **Número é número, data é data.** Nada de valor formatado como texto no XLSX. | A primeira coisa que o destinatário faz é reconverter a planilha inteira — e reconversão de `1.234,56` erra. |
| **R9** | **Cabeçalho de procedência em toda saída:** o que é, de qual recorte, emitido por quem e quando, com os totais de conferência repetidos no rodapé. | Peça sem procedência não é conferível, e é a primeira coisa que um analista procura. |
| **R10** | **Pequeno é síncrono; grande é job** com progresso e link de validade limitada. O corte é do motor, não de quem declara. | Request travado em 30.000 linhas estoura timeout no gateway e o usuário reenvia — dobrando a carga. *(Stripe, AWS)* |
| **R11** | **Acesso total ou nada** (§3): quem não tem o conjunto inteiro de permissões do recurso não vê o botão. Meia permissão bloqueia; não existe arquivo parcial. | Arquivo parcial é arquivo silenciosamente errado: quem recebe não sabe que o CPF vazio é máscara, e soma uma coluna que não está toda lá. |
| **R12** | **Toda exportação é auditada** no `AuditLog`, com recurso, recorte e volume — sem PII no `detalhes`. | Exportação é o evento LGPD por excelência: é o momento em que o dado sai do sistema. |
| **R13** | **Teto do plano checado antes de materializar** as linhas. | Ler um arquivo de 90 mil linhas para recusar no fim é pagar o custo inteiro por nada. |
| **R14** | **Idempotência:** reimportar o mesmo arquivo não duplica — a chave da R3 mais o veredito da R1 garantem. | O usuário sempre clica duas vezes. |

## 3. Quem pode — acesso total ou nada

**A regra:** só importa e exporta quem tem **acesso total** ao recurso — o conjunto inteiro de
permissões que a declaração exige. **Meia permissão bloqueia o botão**, permissão nenhuma idem. Não
existe operação parcial, nem arquivo com coluna capada.

Isso é mais estrito do que o gate normal da API, de propósito. Nas telas, o
[mascaramento 9.C](../acesso-e-permissoes.md) protege o **campo**: o CPF vira `•••123` e a página
continua útil. Num arquivo, não: a planilha que sai com uma coluna mascarada parece completa, viaja
para fora do sistema, é somada e conferida por quem não estava na tela e não tem como saber que
aquela coluna foi capada. **Meio-arquivo é pior que arquivo nenhum.**

### Como isso é verificado

Uma checagem só, e é de conjunto: `permissoes_exigidas ⊆ permissões do token`. Falta uma → **403
nomeando quais faltam**, e o frontend some com o botão antes disso (§10) para a pessoa não descobrir
no clique.

Bloquear na entrada em vez de conferir campo a campo no meio da operação é o que torna a regra barata
e previsível: o motor não precisa cruzar as colunas declaradas com os `sensitive_fields` de cada
serializer em tempo de request, e o resultado é o mesmo — **desde que a declaração inclua as
permissões de máscara das colunas sensíveis que exporta**. Se um recurso traz a coluna CPF, o
`cadastro.cliente_doc.view` entra em `permissoes_exigidas`. Essa é a única obrigação que a
simplificação transfere para quem declara, e está no contrato (§4).

O backend **não conhece o catálogo de permissões da IAM** — elas chegam como lista plana na claim
`permissions` do JWT ([nucleo/permissions.py](../../backend/nucleo/permissions.py)), então "todas as
permissões do módulo" não é computável do lado de cá; por isso o conjunto é **declarado** pelo módulo,
que conhece as próprias. Admin de tenant e admin de plataforma passam pelo mesmo bypass que já vale em
`RequirePermission`.

> **Evolução possível:** a IAM emitir uma claim `modulos_totais` calculada do catálogo no momento da
> emissão do token tornaria o conjunto central em vez de declarado. Fica registrado como opção; a
> forma declarada resolve sem mexer em contrato de token e mantém a regra ao lado do dado.

## 4. O contrato — o que cada módulo declara

Quando chega a vez de um módulo, o que se escreve é **uma declaração**, em `<modulo>/impexp.py`. O
motor não é tocado.

```python
# backend/moduloorcamento/impexp.py
from funcoesimpexp.registro import Coluna, Recurso, registrar


@registrar("orcamento.planilha")
class PlanilhaOrcamentaria(Recurso):
    rotulo = "Planilha orçamentária"
    modulo = "orcamento"
    permissoes_exigidas = (            # §3 — acesso total ao módulo
        "orcamento.orcamento.view", "orcamento.orcamento.edit",
        "orcamento.item.view", "orcamento.item.edit",
    )
    chave = "codigo_eap"               # R3 — upsert key

    colunas = (
        Coluna("codigo_eap",     "Item",        obrigatoria=True, exemplo="1.2.1"),
        Coluna("descricao",      "Descrição",   obrigatoria=True, exemplo="Alvenaria de vedação"),
        Coluna("unidade",        "Und",         exemplo="m²"),
        Coluna("quantidade",     "Quantidade",  tipo=Decimal, exemplo="128,50"),
        Coluna("custo_unitario", "Custo unit.", tipo=Decimal, exemplo="87,30"),
    )

    def queryset(self, request, recorte):   # R7 — o recorte da tela, já tenant-scoped
        ...

    def aplicar_linha(self, linha, existente):  # o que pode criar/atualizar — e o que nunca
        ...
```

| Campo | Obrigatório | Para que serve |
|---|---|---|
| id do recurso | sim | `modulo.recurso`, chave do registry e do endpoint |
| `rotulo` | sim | nome do arquivo e cabeçalho de procedência (R9) |
| `modulo` | sim | o módulo dono — de quem vem a autorização (§3) |
| `permissoes_exigidas` | sim | o conjunto que caracteriza acesso total (§3). **Inclui a permissão de máscara de toda coluna sensível declarada** — ex.: exportou CPF, então `cadastro.cliente_doc.view` entra aqui |
| `chave` | sim na importação | decide criar × atualizar (R3) |
| `colunas` | sim | governa modelo, validador e export (R2); `exemplo` vira a linha-exemplo do modelo |
| `queryset` | sim na exportação | o recorte, já escopado por tenant (R7) |
| `aplicar_linha` | sim na importação | a gravação, com as regras de negócio do módulo |
| `formatos` | não | restringe o que o motor oferece; o padrão é XLSX + CSV + PDF |
| `contexto_requerido` | não | chaves de **destino** que a tela pergunta antes do upload (§4.1) |
| `validar_contexto` | não | resolve e valida o destino **antes** de ler o arquivo |
| `checar_quota_objeto` | não | teto de **acervo** do módulo (§9) |
| `desfazer_linha` | não | sem ele o lote não é reversível (R6) |
| `contar` | não | quantas linhas o recorte tem, para o corte da R10 |

### 4.1 Contexto — o destino da operação

Importar quase nunca é "para o tenant": é para **este** banco de preço, **esta** publicação,
**este** orçamento. Esse dado não cabe no recorte (que é filtro de leitura) nem nas colunas (que são
o arquivo), então o motor o carrega à parte, do pedido até os ganchos.

O registry guarda **uma instância sem estado** por processo. Quando há destino, o motor chama
`com_contexto()`, que devolve uma **cópia rasa** com `self.contexto` preenchido — e é nela que os
ganchos rodam. Guardar o destino no singleton produziria o defeito que só aparece sob concorrência,
em produção: duas importações simultâneas para bancos diferentes gravando uma no destino da outra.

O contexto escolhido no upload fica **persistido no lote**, e não é relido da tela na hora de
aplicar: entre subir o arquivo e confirmar passa-se um café — exatamente o que a R1 pede —, e o
destino que recebe as linhas tem de ser o que a pessoa escolheu, não o que estiver selecionado
depois.

Recurso pode ser **só de exportação** (curva ABC, DRE) ou **só de importação** (contagem de
inventário). Declara-se o que existe.

## 5. As três saídas de uma declaração só

É a R2 na prática, e o que o dono pediu por "gerar os modelos de importação e exportação":

```
                      ┌─→ modelo.xlsx   cabeçalhos + linha-exemplo + coluna-chave marcada
  colunas declaradas ─┼─→ validador     tipo, obrigatoriedade, de-para, veredito por linha
                      └─→ exportação    mesmas colunas, mesma ordem, mesmos rótulos
```

O modelo que o usuário baixa é, por construção, o que a importação aceita. Não há como divergirem.

## 6. Formatos

| Formato | Entrada | Saída | Biblioteca |
|---|---|---|---|
| **XLSX** | ✔ | ✔ | `openpyxl` |
| **CSV / TXT delimitado** | ✔ | ✔ | `csv` (delimitador brasileiro: `;` vence — ver §7.1) |
| **PDF** | — | ✔ | `weasyprint`, via template HTML |
| **PDF (extração de tabela)** | ✔ | — | `pdfplumber` — frágil por natureza, só com conferência (R1) |
| **JSON** | ✔ | ✔ | nativo — para integração, não para humano |

DOCX e ODS ficam de fora até haver caso real: dependência nova por antecipação é custo de supply
chain (Fase 10.4) sem contrapartida.

### 6.1 O que já está pronto e é promovido

O leitor do Orçamento ([leitura.py](../../backend/moduloorcamento/leitura.py)) resolve coisas que
custaram caro para descobrir e **sobem inteiras** para o motor:

- **`csv.Sniffer` não serve no Brasil.** Em `1379;CIMENTO;KG;0,58` ele elege a vírgula — que é o
  separador **decimal** — e parte a última coluna em duas, sem erro, com dado silenciosamente errado.
  A detecção prefere `;`.
- **Número brasileiro**: `1.234,56`, `1234,56` e o `float` que vem do XLSX, todos para `Decimal`.
- **Cabeçalho por sinônimos normalizados** (sem acento, minúsculo), procurado nas primeiras linhas —
  publicação oficial põe título e legenda antes da tabela.

## 7. Os dois fluxos

### Importação

```
upload ─→ valida tipo/tamanho ─→ lê ─→ de-para de colunas ─→ classifica linha a linha
   (nucleo/upload_validation)                                        │
                                                                     ▼
                            CONFERINDO ──→ [confirmar tudo · confirmar seleção · negar tudo]
                                                                     │
                                                       ┌─────────────┴─────────────┐
                                                       ▼                           ▼
                                                  APLICADA (lote                DESCARTADA
                                                  desfazível, R6)              (nada gravado)
```

Nada toca o destino antes da decisão (R1). O teto do plano é checado **antes** de materializar as
linhas (R13). A porta de entrada reusa o [`UploadValidationMixin`](../../backend/nucleo/upload_validation.py),
que já é fundação compartilhada.

### 7.1 O de-para também vale no job

No caminho síncrono, cabeçalho não reconhecido responde **422** e a tela abre o de-para manual. No
caminho de job não há para quem devolver 422 na hora — e a tentação é encerrar o lote com "não
reconheci as colunas".

**Isso seria um beco sem saída no único caminho que mais precisa da saída.** Arquivo grande é
justamente o de origem mais estranha (o PDF de 90 mil linhas da prefeitura, a publicação que mudou de
layout): virar job é *consequência* de ser o caso difícil. Então o lote interrompido:

- guarda `cabecalhos_vistos` e as colunas declaradas nos `parametros`, com `aguarda_de_para`;
- **preserva o arquivo** — sem ele, "escolha qual coluna é cada campo" viraria "suba os 90 mil de
  novo";
- deixa `decidida_em` vazio, que é o que distingue *interrompido* de *erro terminal* na listagem.

`POST …/importacoes/<id>/remapear/` relê o **mesmo arquivo** com o mapa na mão. O arquivo cru só é
descartado quando a leitura dá certo — dado de entrada (folha, carteira, tabela de custo) não fica
no disco por mais tempo do que a operação exige.

### Exportação

Recorte da tela → `queryset` da declaração → escritor do formato → arquivo com cabeçalho de
procedência (R9) e `AuditLog` (R12). Abaixo do corte de volume, resposta direta; acima, job Celery com
progresso e link de validade limitada (R10).

> **Celery com contexto de tenant, sempre.** Task que lê o ORM sem `rls_bypass()` → `tenant_context()`
> não acha linha nenhuma sob a RLS fail-closed do worker — foi exatamente o **D8** (cobrança que
> respondia 202 e nunca gerava boleto). Toda task daqui arma o contexto no início.

## 8. Modelo de dados

Tudo `TenantScopedModel` com RLS fail-closed, no padrão do resto do backend.

| Model | Papel |
|---|---|
| `Importacao` | o lote: recurso, **contexto** (§4.1), arquivo, parâmetros do de-para, status (`LENDO`/`CONFERINDO`/`APLICADA`/`DESCARTADA`/`DESFEITA`/`ERRO`), progresso, quem decidiu. **Aplicada, é também a unidade que a R6 desfaz** |
| `LinhaImportacao` | a linha: número no arquivo, `valores` extraídos, **veredito** + motivo, `aceita`, a linha bruta original (para a R5 e para auditar o extrator) e o `estado_anterior` que a R6 restaura |
| `Exportacao` | o rastro do que saiu: recurso, recorte, formato, volume, quem pediu — mais, no caminho de job, o arquivo gerado e o `expira_em` da R10 |
| `MapaColunas` | o de-para salvo (R4), para a importação **recorrente**: a mesma prefeitura publica a mesma planilha torta todo mês |

`LENDO` existe só no caminho assíncrono e **não é decidível**: aplicar um lote a meio caminho de ser
classificado gravaria só o pedaço que o worker já materializou. Sem um estado próprio, a tela teria
de escolher entre mentir ("em conferência", com zero linhas) e mostrar erro — e as duas coisas fazem
o usuário reenviar o arquivo.

`MapaColunas` guarda `campo → índice`, não `campo → nome da coluna`: o nome é justamente o que não
casou (senão o de-para automático teria resolvido), e a posição é o que se manteve estável entre as
publicações que motivaram a função.

O `estado_anterior` mora **na linha**, e não numa tabela de lote à parte, porque é
por linha que se reverte: desfazer uma criação é apagar, desfazer uma atualização é
restaurar os valores de antes, e as duas coisas convivem no mesmo arquivo.

As duas primeiras são a promoção do `ImportacaoPreco`/`LinhaImportacao` do
[moduloorcamento](moduloorcamento.md), generalizadas: onde hoje há campos de preço (`codigo`,
`custo_unitario`, `grupo`), passa a haver um `valores` JSON governado pelas colunas declaradas.

## 9. Quotas e plano

O knob comercial já existe em [payment/planos.py](../../payment/planos.py) e hoje só o Orçamento o
consome — passa a valer para todo recurso:

- **`importacao_linhas`** — quota de **operação**: protege processamento (ler, classificar, conferir).
- **`banco_preco_linhas`** — quota de **objeto**, específica do acervo de preço do Orçamento; cada
  módulo que precise de teto de acervo declara o seu.

Exportação não tem quota de linhas por ora; se virar vetor de custo (arquivo grande, storage,
tráfego), o lugar de decidir é `payment/`, nunca o código de engenharia.

## 10. Frontend

Dois componentes no [kit Malha compartilhado](../../frontend/src/components/malha/impexp/), e é tudo
o que um módulo consome:

- **`<BotaoExportar recurso="..." recorte={...} />`** — abre o diálogo de formato, respeita o recorte
  da tela (R7) e some quando a pessoa não tem acesso total (§3), em vez de dar erro no clique. Acima
  do corte de volume, mostra o progresso do job e o botão de baixar quando fica pronto.
- **`<WizardImportacao recurso="..." contexto={...} />`** — upload → de-para → **conferência linha a
  linha** → decisão. Promoção do `ConferenciaImportacao.tsx` do Orçamento, generalizada: onde lá
  havia colunas de preço fixas no JSX, aqui a tabela é montada das colunas que o **recurso declarou**.

Nenhum dos dois recebe prop de permissão: quem decide é `/api/impexp/recursos/`. Repetir a regra no
frontend criaria um segundo lugar para ela divergir — e o que divergisse seria justamente o que o
usuário vê.

O cliente HTTP e os hooks ficam em [`impexp/api.ts`](../../frontend/src/components/malha/impexp/api.ts)
e [`impexp/hooks.ts`](../../frontend/src/components/malha/impexp/hooks.ts). Módulo novo **não escreve
API nova**.

## 11. Anatomia do app

| Peça | Arquivo | Responsabilidade |
|---|---|---|
| Registry e contrato | `registro.py` | `Recurso`, `Coluna`, `@registrar` — o vocabulário da declaração |
| Descoberta | `apps.py` | `autodiscover_modules("impexp")` no `ready()`: módulo novo se registra sozinho, e declaração torta derruba o **boot**, não o clique do usuário |
| Formatos | `formatos/` | leitores e escritores XLSX/CSV/PDF/JSON; absorveu o `leitura.py` do Orçamento |
| Motor de importação | `importacao.py` | `preparar → marcar → aplicar/descartar/desfazer` + o corte de volume da R10 |
| Motor de exportação | `exportacao.py` | recorte → escritor → arquivo com procedência; abre e fecha o lote do job |
| Jobs | `tasks.py` | as três tasks Celery da R10, todas armando `tenant_context` (a lição do **D8**) |
| Modelo gerado | `modelo.py` | a planilha-modelo a partir das colunas (R2) |
| Acesso | `acesso.py` | a regra do §3, num lugar só |
| Persistência | `models.py` | §8, RLS fail-closed (`migrations/0002` e `0004`) |
| API | `views.py` | endpoints únicos; rotas em `config/urls.py` (padrão do projeto) |

### 11.1 Os endpoints

Um conjunto só serve todo recurso de todo módulo — **módulo novo não ganha rota nova**:

| Rota | Faz |
|---|---|
| `GET /api/impexp/recursos/` | o que **esta pessoa** pode operar (o frontend some com o botão antes do clique) |
| `GET /api/impexp/<recurso>/exportar/?formato=&…` | exporta; o que o recurso declarou como destino é contexto, **todo o resto é recorte** (R7) |
| `GET /api/impexp/<recurso>/modelo/` | a planilha-modelo (R2) |
| `POST /api/impexp/<recurso>/importar/` | sobe o arquivo → confere → para em `CONFERINDO` (R1) |
| `GET /api/impexp/<recurso>/importacoes/` | o histórico do recurso, com `pode_desfazer` por lote |
| `GET /api/impexp/<recurso>/mapas/` · `POST` | os de-para salvos (R4) |
| `DELETE /api/impexp/mapas/<id>/` | apaga um de-para salvo |
| `GET /api/impexp/importacoes/<id>/` | resumo + linhas com veredito (e o progresso, no job) |
| `POST /api/impexp/importacoes/<id>/{marcar,aplicar,descartar,desfazer}/` | a decisão |
| `POST /api/impexp/importacoes/<id>/remapear/` | relê o arquivo guardado com o de-para escolhido (§7.1) |
| `GET /api/impexp/importacoes/<id>/recusadas/` | as recusadas de volta como XLSX (R5) |
| `GET /api/impexp/exportacoes/<id>/` · `?baixar=1` | acompanha e baixa o que saiu por job (R10) |

Cabeçalho irreconhecível responde **422** com os cabeçalhos vistos, para o de-para
manual (R4); teto do plano responde **402** com quota e limite, no mesmo contrato
que a UI já trata em `nucleo/quotas.py`. Acima do corte de volume, `importar` e `exportar`
respondem **202** com o id do lote, e a tela acompanha pelos endpoints de detalhe.

**Só o último lote aplicado é desfazível.** Desfazer um lote do meio restauraria valores por cima do
que veio depois, e o resultado não seria nem o estado anterior nem o atual — é por isso que a
listagem calcula `pode_desfazer` no servidor, em vez de deixar a tela adivinhar.

## 12. Sub-fatias

| Fatia | Escopo |
|---|---|
| **IE.0** | **Fundação, caminho síncrono:** registry + contrato, formatos (absorvendo o `leitura.py`), modelo gerado, os dois motores, models com RLS fail-closed, regra de acesso do §3 e os endpoints |
| **IE.0b** | **Volume:** o job assíncrono da R10 (Celery com `tenant_context`, progresso e link de validade limitada) e o de-para salvável da R4 |
| **IE.0c** | **Frontend:** `<BotaoExportar>` e `<WizardImportacao>` no kit Malha, promovendo o `ConferenciaImportacao.tsx` |
| **IE.1** | **Orçamento migra para a fundação** — o ORC.5b inteiro passa a rodar pelo motor sem perder função. É o teste do desenho: o que a fundação não der conta aqui está errado |
| **IE.n** | Um módulo por vez, sob demanda: cada um ganha seu `impexp.py` e os botões nas páginas onde o dado vive |

**Por que o Orçamento primeiro:** é o único caso já resolvido em produção. Migrar código que funciona
prova a fundação contra requisitos reais (PDF de prefeitura, base com 90 mil linhas, lote desfazível)
em vez de contra requisitos imaginados — e se algo não couber, o custo é descobrir agora, com um
consumidor, e não com seis.

### 12.1 O que a migração do primeiro consumidor exigiu do motor

A fatia IE.1 pagou o que prometia: **duas lacunas** do IE.0 só apareceram com um módulo real em cima.

1. **Contexto de destino** (§4.1) — o IE.0 sabia gravar "no tenant"; não sabia gravar "neste banco de
   preço". Sem isso, metade dos recursos plausíveis do sistema não caberia na fundação.
2. **Quota de acervo** (§9) — o motor cuida de `importacao_linhas`, que é de operação e vale para
   todos; `banco_preco_linhas` conta linhas de tabela de preço e só o módulo sabe contar. Virou o
   gancho `checar_quota_objeto`.

Uma terceira veio da tela: sem **listagem** de importações, o desfazer da R6 era inalcançável — o
lote aplicado ontem não tinha por onde ser encontrado, e "desfazível" seria uma promessa que só o
`curl` cumpre.

**Armadilha registrada.** `limpar()` (em `tests.py`) esvazia um registry **global e povoado no boot**.
Chamá-lo num teste sem guardar o estado antes apaga as declarações reais de todos os módulos — e o
estrago não aparece na suíte daquele app, e sim nos testes que rodarem depois, como recurso que "não
existe" (404). Use sempre `instantaneo()` + `restaurar()`.
