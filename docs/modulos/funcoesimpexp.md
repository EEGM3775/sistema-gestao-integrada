# funcoesimpexp — importação, exportação e coordenação de todo arquivo (o DMS)

> **App-fundação**, como o [catalogo](catalogo.md): não se vende, não tem entitlement próprio e
> nenhum módulo depende dele para existir. É o **motor** de entrada e saída de dados; cada módulo
> declara *o que* sai e entra, e o motor cuida do resto.
>
> **É a fronteira de arquivo do software, nos dois sentidos** — upload e download, planilha e binário.
> Nenhum módulo valida, mede, admite ou entrega arquivo por conta própria: ele *declara*, e o motor
> *admite* e *entrega*. Duas funções, uma implementação: [`entrada.admitir`](../../backend/funcoesimpexp/entrada.py)
> e [`entrega.servir`](../../backend/funcoesimpexp/entrega.py).

> **É também o DMS** *(decisão do dono, 03/10/2026)*: o módulo de coordenação de documentos —
> todos os arquivos, dentro e fora do sistema — **não é um segundo app**. Coordenar documentos é
> responder, sobre os arquivos que já passam por esta porta, *o que está guardado, o que entrou e o
> que saiu*; as três respostas moram aqui (§13). O `modulodms`, que era um placeholder vazio, saiu
> do repositório.

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
| **R15** | **Todo limite é do PLANO, e é dito antes.** Tamanho, formato aceito, memória e relógio de uma operação vivem em [payment/planos.py](../../payment/planos.py) §5.2, por plano, e são publicados em `GET recursos/` — nunca descobertos no erro. Tetos duros de infraestrutura por cima: contrato ilimitado não compra o direito de derrubar o worker compartilhado. | Limite escondido no código de engenharia é botão comercial que o dono não vê; e limite que só aparece no 402 faz a pessoa esperar o upload de 40 MB para descobrir que não podia. *(o método do assinador gov.br: capacidade é atributo do nível da conta, formato e teto publicados antes do envio)* |
| **R17** | **Porta única nos DOIS sentidos, e ela se adapta — não o contrário.** *(decisão do dono, 08/08/2026)* Todo arquivo que **entra** vindo do cliente e todo arquivo que **sai** para ele passam por aqui, qualquer que seja o tipo: planilha, prancha, foto, documento. Módulo não abre porta própria — declara o que aceita (`natureza = "arquivo"`, `formatos_arquivo`) e o que entrega (`entregar_arquivo`), e o motor cresce para atendê-lo. Item que o **sistema** cria (o XML que o worker baixa da NFE.io, a derivada que a Prancheta gera) **não é importação** — é registro, e não passa pela conferência; mas quando ele **sai**, sai por esta porta como tudo o mais. | A R16 já mandava decidir pelos bytes — e **a Prancheta decidia pelo nome**, porque tinha porta própria e a regra não a alcançava ([D75](../historico-correcoes.md)). Regra não herdada é regra que não existe: com seis portas, o guarda-corpo divergente aparece só na que ninguém revisou. Do lado da saída o preço era o mesmo: `moduloprancheta/entrega.py` reimplementava sozinha `nosniff`, `attachment`, o tipo declarado por nós e o saneamento do nome — quatro guarda-corpos certos, e em segunda cópia. É a razão de o [nucleo/orcamento.py](../../backend/nucleo/orcamento.py) ter subido para a fundação, aplicada a arquivo. |
| **R18** | **Confere-se o que a PLATAFORMA adivinhou.** Lote em que o motor inferiu algo do arquivo — obra e disciplina do caminho da pasta (`TorreA/ARQ/p.dwg`) — para na conferência da R1. Envio avulso em que a pessoa escolheu o destino e digitou os campos **grava direto**, pela mesma porta e pelos mesmos guardas. O que decide não é o volume: é se há palpite nosso a confirmar. | Conferência de um item só, sobre dado que a própria pessoa acabou de digitar, é cerimônia — e cerimônia ensina o usuário a clicar "confirmar" sem ler, o que mata a R1 justamente onde ela vale. *(é o modelo do Procore: ao subir prancha ele roda OCR para inferir número e disciplina e por isso exige confirmação; Box, Drive e Dropbox não param nunca — o que eles fatiam é arquivo grande, e o "commit" é técnico, não humano)* |
| **R19** | **O palpite se corrige na conferência — não se reenvia o arquivo.** *(15/08/2026)* A decisão deixou de ser só aceitar/recusar a linha: a coluna que o **recurso** declarar `editavel` abre na tela, com as opções que ele der em `opcoes_da_coluna` (`{valor, rotulo, cor?}`), uma linha por vez ou em massa. Três limites que ela não afrouxa: só em importação **pendente**, só em coluna declarada, e **corrigir não aceita** — a R1 é sobre a decisão, e corrigir não é decidir. | A R18 mandava conferir o palpite, e a tela só deixava recusá-lo inteiro. No acervo isso apareceu na cara: manda-se a pasta **da obra**, o palpite acerta as subpastas organizadas (`TorreA/ARQ/…`) e erra o arquivo solto no meio — e a única saída era recusar a linha e subir aquele arquivo à parte, o que faz a pessoa desistir de classificar. O gancho é do recurso porque o motor não conhece disciplina, obra nem centro de custo, e não deve conhecer: a alternativa era um `if recurso === "prancheta.acervo"` dentro do wizard compartilhado. |
| **R16** | **O que entra é reconhecido pelos BYTES; o que sai não é executável.** Entrada: allowlist por assinatura (§6), e o nome do arquivo nunca decide. Saída: nada que o Excel leia como fórmula sai sem neutralização (§6.2). | Sufixo é dado do atacante — `payload.exe` renomeado para `.xlsx` era gravado em disco antes de qualquer leitura. E exportar `=cmd\|'/c calc'!A1` transforma a plataforma no **veículo** de entrega contra quem recebe o arquivo. *(OWASP, CSV Injection — o defeito é de quem gera o arquivo)* |

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

### 3.1 Entrar exige o módulo contratado; sair, não

O conjunto de permissões **já carrega o entitlement por transitividade**: `permissoes_efetivas()` na
IAM filtra as permissões pelos módulos efetivos, então quem não assina o Orçamento não tem
`orcamento.*` no token e não passa pelo gate acima. Elegante — e o **bypass de admin** passava por
cima dele, porque devolve conjunto vazio antes de olhar permissão nenhuma. O tenant que cancelava o
Orçamento levava 403 em `/api/orcamento/**` e seguia importando e exportando por aqui
([D66](../historico-correcoes.md)).

A correção é **assimétrica de propósito**, e a assimetria é o padrão de mercado:

- **importar** exige o módulo contratado, para todo mundo, inclusive admin — é entrada de dado em
  produto não pago;
- **exportar** segue aberto ao admin mesmo sem o módulo, porque é **portabilidade**. Salesforce
  retém o dado por 180 dias e a HubSpot rebaixa a conta para o free em vez de apagar; prender o dado
  do cliente no dia em que ele cancela gera processo, não receita. O que faltava para isso ser
  decisão em vez de acidente era o **rastro** — e ele veio junto (R12, [D67](../historico-correcoes.md)).

Recurso de **fundação** declara `entitlement = None`: o `maps.local` é o caso, porque `Local` é a
metade do Maps que abre para todo tenant e as permissões `mapa.local.*` moram no módulo `base`.

`impexp_exportar_apos_cancelar_dias` (§9.1) dá o prazo dessa janela e está **inerte**: aplicá-la
exige a IAM emitir a data de cancelamento na claim — hoje `modules` só diz o estado de agora, e
módulo cancelado é indistinguível de módulo nunca contratado.

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
| **PDF** | — | ✔ | `weasyprint`, via template HTML — **porta única**, com buscador de URL fechado (§6.1b) |
| **PDF (extração de tabela)** | ✔ | — | `pdfplumber` — frágil por natureza, só com conferência (R1) |
| **JSON** | ✔ | ✔ | nativo — para integração, não para humano |

DOCX e ODS ficam de fora até haver caso real: dependência nova por antecipação é custo de supply
chain (Fase 10.4) sem contrapartida.

**O `pdfplumber` é a única dependência opcional da lista, e é assim de propósito.** Ele está no
`backend/requirements.txt` e portanto passa pelos gates de `pip-audit`/Dependabot, mas
[leitura.py](../../backend/funcoesimpexp/formatos/leitura.py) o importa **tardiamente** e degrada com
mensagem clara se faltar: tirar a linha do `requirements` desliga só o caminho de extração de tabela
de PDF, e o resto do motor segue inteiro. Quem não quiser a dependência não precisa de nenhuma outra
mudança.

**A entrada é uma allowlist por assinatura de bytes** ([limites.py](../../backend/funcoesimpexp/limites.py)):
`PK\x03\x04` → XLSX · `%PDF-` → PDF · texto que decodifica e não tem byte nulo → CSV. O **sufixo do
nome só desempata** entre formatos que compartilham assinatura (todo XLSX é um ZIP) — ele nunca
decide sozinho, porque é dado que o cliente escolhe. A amostra de 4 KB é lida **antes** do arquivo
inteiro: o teto de tamanho tem de barrar antes de trazermos 50 MB para a memória.

Quais desses formatos cada plano importa é knob comercial (`impexp_formatos`, §9). Formato existente
mas não contratado volta **402** nomeando o que o plano abre; bytes que não casam com nenhuma
assinatura voltam **400** — a mesma distinção que a Prancheta faz entre "seu plano não abre" e "isto
não é um desenho".

### 6.1b O PDF sai por aqui, e por uma porta só

**`html_para_pdf` em [escrita.py](../../backend/funcoesimpexp/formatos/escrita.py) é o único ponto do
backend que chama `write_pdf()`** — e isso é desenho, não arrumação. O WeasyPrint roda com um
`url_fetcher` padrão que **busca URL de verdade**: bastaria o primeiro logo de tenant no cabeçalho
para o gerador de relatório virar leitor de `http://169.254.169.254/…` e de `file:///etc/…`. O
buscador daqui entrega **só o que já veio embutido** (`data:` URI) e recusa o resto, e o WeasyPrint
pula o recurso recusado — o PDF sai sem a imagem, em vez de não sair.

Por isso o [moduloorcamento](moduloorcamento.md) emite a planilha em PDF **chamando esta função**, e
não o WeasyPrint direto. Duas chamadas seriam duas políticas de rede, e a segunda nasceria aberta —
foi exatamente o que o [D73](../historico-correcoes.md) encontrou. Uma regressão varre o backend
atrás de um segundo `write_pdf()` e falha com o nome do arquivo: é a mesma lógica da porta única de
arquivo (§2), aplicada à emissão.

### 6.2 O arquivo que sai não pode executar nada

Um valor de cadastro que comece com `=`, `+`, `-`, `@`, tabulação ou CR é lido como **fórmula** por
Excel, Sheets e Calc. Como o dado vem de fora (razão social de fornecedor, descrição de item), sem
tratamento a exportação vira o veículo de um ataque contra quem recebe o arquivo — e o remédio é
diferente em cada formato, porque o mecanismo é diferente:

| Formato | O que acontece sem tratamento | O que fazemos |
|---|---|---|
| **CSV** | o Excel interpreta **cada célula** como se tivesse sido digitada | prefixo `'` nos seis gatilhos (mitigação da OWASP). Custa um apóstrofo visível, e é aceitável no formato que existe "para quem vai ler com script" |
| **XLSX** | célula de string é string e o Excel **não** reinterpreta — mas o `openpyxl` infere o tipo no `append` e grava um `<f>` de verdade quando o texto começa com `=` | `data_type = "s"` depois da atribuição: desfaz a inferência **sem sujar o valor** |
| **PDF** | não executa fórmula | nada |

Número e data saem tipados (R8) e não passam pelo escape — valor negativo continua intacto.

### 6.3 Varredura de vírus — adiada por decisão, e é aqui que ela entra

Não existe varredura de vírus em lugar nenhum da plataforma: `clamav|antivirus|virustotal|malware`
não aparece em `backend/`, `iam/`, `deploy/` nem `payment/`. Vale para este motor, para a
[Prancheta](moduloprancheta.md) e para todo `FileField` do sistema. **O dono decidiu adiar**; por ora
entra só o teto de recurso (§9).

Quando entrar, entra **aqui** — é a outra metade da tese de que todo arquivo que entra e sai do
sistema passa por esta porta (§1): varrer numa função só é muito mais barato do que em dezenas de
módulos, e com dezenas é garantido que um fica de fora.

**O risco não é simétrico entre os dois consumidores, e isso ordena o trabalho.** Neste motor o
binário é lido e **descartado** ([tasks.py](../../backend/funcoesimpexp/tasks.py)), nunca devolvido a
ninguém — ele já é, de fato, um **CDR** (*Content Disarm & Reconstruction*): o XLSX vira linhas
tipadas e o original morre. O risco que sobra é **ser derrubado** por arquivo hostil, e é o que o teto
de recurso da §9 fecha. Na Prancheta é o contrário — o arquivo do cliente é guardado e servido de
volta —, e é lá que o AV vale de verdade e deve estrear.

Método de mercado, para quando for a hora: varredura **assíncrona com quarentena** (o arquivo existe
mas não é alcançável até liberar); **ClamAV em sidecar** como a opção honesta de custo zero — a paga
por arquivo colide com a régua de o plano básico não custar nada ao dono; e **CDR** como degrau acima
para documento, seguindo NCSC e NSA, que convergiram para sanitização por transformação em vez de
detecção.

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

## 7.2 As portas que ainda não são esta (IE.4+)

Inventário levantado em 08/08/2026 ao abrir a **R17**. A IE.3 deu ao motor a natureza `arquivo`; o que
falta é cada módulo entregar a sua porta. **Uma por vez, e nesta ordem** — a Prancheta primeiro porque
é a única com achado de segurança aberto ([D75](../historico-correcoes.md)) e a que já tem o lote pedido pela
própria planta.

**A Prancheta terminou de atravessar na PRA.5b**, e o que ela deixa para as próximas é mais do que o
exemplo: o lote do acervo é o **primeiro consumidor real** do caminho `preparar_arquivos → conferir →
aplicar → desfazer`, que até aqui só tinha um recurso de teste. Quem vier depois (IE.4–IE.7) copia
uma forma já exercitada — `contexto_requerido` para o destino, `dados_do_arquivo` para o palpite,
`aplicar_linha` com `FileField.save()` para a cópia própria — em vez de descobri-la:

| Porta | Onde | O que muda | Fatia |
| --- | --- | --- | --- |
| ~~Acervo de projeto (revisão)~~ | ~~`moduloprancheta/uploads.py`~~ | **migrada.** O arquivo saiu; virou o recurso `prancheta.acervo`. O avulso grava direto pela R18 (não virou "lote de 1", como esta tabela previa — a régua nasceu depois, ao ver que conferência de um item só é cerimônia) | PRA.5a ✅ |
| ~~Saída do acervo (3 rotas)~~ | ~~`moduloprancheta/entrega.py`~~ | **migrada.** As ações `arquivo/` de revisão, derivada e snapshot saíram do módulo; o mecanismo virou `entrega.servir` | PRA.5a ✅ |
| ~~Snapshot de marcação (BCF)~~ | ~~`moduloprancheta` (`Marcacao.snapshot`)~~ | **migrada.** A entrada passou a `entrada.admitir` pelo recurso `prancheta.marcacao`, que agora declara `formatos_arquivo` nos dois sentidos. O teto do snapshot é **do recurso**, não do formato: `imagem` no acervo é prancha escaneada (25 MB) e aqui é recorte de tela | PRA.5b ✅ |
| ~~Importação de BCF~~ | ~~`moduloprancheta` (`marcacoes/importar-bcf/`)~~ | **migrada.** Era o último upload da Prancheta fora do motor. O teto de entrada passou a ser o do registry (50 MB, o pacote **como chega**); o orçamento de descompressão continua dentro do leitor e mede outra coisa | PRA.5b ✅ |
| ~~Acervo histórico em lote~~ | ~~(não existia)~~ | **construída.** O `prancheta.acervo` ganhou `aplicar_linha`/`desfazer_linha` e é o **primeiro consumidor real da natureza `arquivo`** fora do teste: pasta do projetista → conferência → acervo, com R1 e R6. A obra é `contexto_requerido`; disciplina, código e revisão são o palpite da R18 | PRA.5b ✅ |
| Mídia do diário de obra | `modulodiario` (`MidiaDiario.arquivo`) | foto do canteiro: o maior volume real e o melhor candidato a lote | IE.4 |
| Documento do cliente | `clientes` (`DocumentoCliente.arquivo`) | contrato/RG — é PII, então o gate do recurso carrega a permissão de máscara (R11) | IE.5 |
| Documentos do funcionário | `rh` (CTPS · ASO · documento · holerite) | **quatro** campos, e é onde a carga em lote mais paga (admissão de turma) | IE.6 |
| Documento da obra | `obras` (`DocumentoObra.arquivo`) | o mais simples; bom para fechar | IE.7 |

**O que NÃO entra, e é a metade que a R17 delimita:** `moduloerp` (`arquivo_pdf`/`arquivo_xml` de NF) e
`empreendimentos.arquivo_xml` são **baixados pelo worker** da NFE.io, e as `DerivadaProjeto` são
**geradas** pelo nosso motor de conversão. Nenhum é importação — são registros que o sistema cria, como
um cliente ou um produto. Passá-los por uma conferência seria pedir a uma pessoa que aprovasse o que a
plataforma acabou de produzir sozinha.

## 7.3 A saída já atravessou inteira — as portas do D70

**A tabela acima é sobre ENTRADA, e a saída andou primeiro.** A distinção é a mesma que o
`ArquivoEntregue` faz: entregar é deixar sair um binário que o recurso já guarda; importar é a
máquina de conferência. São verbos com gates diferentes, e o segundo é muito mais caro de migrar —
mexe em tela, em wizard e no gesto de quem usa. Um vazamento de **leitura** não podia esperar por
isso.

Em 09/08/2026 os nove prefixos que ainda saíam por `/media/` ganharam recurso de entrega
([D70](../historico-correcoes.md)). O agrupamento é por **gate**, não por app — um `Recurso` tem um
conjunto de permissões, e juntar o ASO com o RG trocaria em silêncio o gate do prontuário médico:

| Recurso | Onde | Espécies | Gate de entrega |
| --- | --- | --- | --- |
| `rh.documentos` | [rh/impexp.py](../../backend/rh/impexp.py) | `documento` · `ctps` | `rh.documento.view` |
| `rh.aso` | idem | `aso` | `rh.dado_medico.view` |
| `rh.holerite` | idem | `holerite` | `rh.folha.view` |
| `cadastro.documento_cliente` | [clientes/impexp.py](../../backend/clientes/impexp.py) | `documento` | `cadastro.cliente.view` |
| `obra.documento` | [obras/impexp.py](../../backend/obras/impexp.py) | `documento` | `obra.obra.view` |
| `obra.diario_midia` | [modulodiario/impexp.py](../../backend/modulodiario/impexp.py) | `midia` | `obra.diario.view` |
| `obra.custo_nfe` | [empreendimentos/impexp.py](../../backend/empreendimentos/impexp.py) | `xml` | `obra.empreend_custo.view` |
| `erp.nota_fiscal` | [moduloerp/impexp.py](../../backend/moduloerp/impexp.py) | `nfse_pdf/xml` · `nfe_pdf/xml` · `entrada_pdf/xml` | `erp.nf.view` |
| `pdca.avanco_foto` | [modulopdca/impexp.py](../../backend/modulopdca/impexp.py) | `foto` | `pdca.avanco.view` |

**Três regras que este lote fixou, e valem para quem vier depois:**

1. **Prefixo não é dono; modelo é.** `nfe_xmls/` é escrito por dois apps, com gates diferentes —
   fechar "o prefixo do ERP" deixaria o XML do custo do empreendimento aberto.
2. **Entregar não obriga a importar.** Estes recursos só têm `entregar_arquivo`; a régua que a
   PRA.5b inverteu é o que permite isso, e é o que separou o conserto de leitura da migração de
   entrada (IE.4–IE.7 continuam de pé, na mesma ordem).
3. **Recurso de fundação declara `entitlement = None`.** `cadastro.*` e `obra.*` moram no módulo
   `base` do catálogo: cobrar entitlement ali faria a ficha do cliente exigir assinatura que ninguém
   vende. É o precedente do `maps.local`.

**A lista não fechou em nove, e não era para fechar.** `pdca.avanco_foto` entrou depois, quando a
PDCA.2 criou `pdca_apontamento/` sem porta e o teste do D70 a acusou pelo nome
([D120](../historico-correcoes.md)) — que é exatamente o que ele existe para fazer. O que esse caso
acrescentou às três regras acima é uma **quarta**, e ela custou o dobro do conserto:

4. **Declarar a porta não fecha o vazamento — o serializer também publica endereço.** Um `FileField`
   em `fields = "__all__"` emite a URL de `/media/` no JSON, e o teste do D70 não olha para
   serializers: ele varre modelos. Dá para satisfazê-lo com o vazamento inteiro de pé. Quem declarar
   um recurso de arquivo tem de trocar o endereço na saída também, com `url_do_arquivo`.

O que o módulo dono ganha de graça: `nosniff`, `attachment`, tipo declarado por nós, nome saneado,
trilha (R12) e a checagem de tenant — via `entregar_campo` e `buscar_do_tenant`, que subiram para
[entrega.py](../../backend/funcoesimpexp/entrega.py) neste mesmo lote.

**A garantia é cobrada por teste, não por lista:**
[test_d70_portas_de_midia.py](../../testes/backend/funcoesimpexp/test_d70_portas_de_midia.py) varre todos os
`FileField` instalados e falha quando um `upload_to` novo aparece sem porta. `/media/` é 404 no
gateway, sem exceção nomeada.

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

- **`importacao_linhas`** — quota de **operação**: limita quantas linhas são **gravadas**.
- **`banco_preco_linhas`** — quota de **objeto**, específica do acervo de preço do Orçamento; cada
  módulo que precise de teto de acervo declara o seu.

Exportação não tem quota de linhas por ora; se virar vetor de custo (arquivo grande, storage,
tráfego), o lugar de decidir é `payment/`, nunca o código de engenharia.

### 9.1 O orçamento de uma operação — e por que as quotas acima não bastavam

As duas quotas contam **linhas**, e linha só se conta depois de ler o arquivo. O custo de **ler** —
descomprimir um XLSX, extrair tabela de um PDF — é anterior a qualquer contagem e não tinha teto
nenhum até 07/08/2026: um arquivo de poucos MB expandia sem limite superior, no worker que também
carrega cobrança e NF-e. É o [D57](../historico-correcoes.md) num segundo caminho ([D63](../historico-correcoes.md)).

Por isso o plano declara **quatro** números além das quotas (§5.2 de `planos.py`), e eles são a
R15 na prática:

| Knob | O que limita | Estourar dá |
|---|---|---|
| `impexp_max_mb` | tamanho do arquivo de entrada | 402, antes de ler um byte |
| `impexp_formatos` | quais formatos o plano importa | 402 nomeando o que o plano abre |
| `impexp_memoria_mb` | memória de **uma** leitura+classificação | 402 (`RecursoExcedido`), não worker morto |
| `impexp_segundos` | relógio da mesma operação | idem |

O mecanismo é o [nucleo/orcamento.py](../../backend/nucleo/orcamento.py), promovido do
`moduloprancheta/limites.py` quando o segundo consumidor apareceu — `RLIMIT_AS` faz o estouro virar
`MemoryError` (exceção Python que sobe e explica) em vez de OOM do kernel (processo morto que não
explica nada). Dois cuidados que o E2E da PRA.1d ensinou e valem aqui: **`MemoryError` é
`Exception`**, então qualquer `except Exception` no caminho o captura antes e o limite nosso passa a
acusar o arquivo do cliente; e os dois tetos só armam na **thread principal**, porque `RLIMIT_AS` é
do processo.

`impexp_exportar_apos_cancelar_dias` é o quinto knob e é de outra natureza — janela de
**portabilidade**, §3.1. Declarado e inerte.

## 10. Frontend

Três componentes no [kit Malha compartilhado](../../frontend/src/components/malha/impexp/), e é tudo
o que um módulo consome:

- **`<BotaoExportar recurso="..." recorte={...} />`** — abre o diálogo de formato, respeita o recorte
  da tela (R7) e some quando a pessoa não tem acesso total (§3), em vez de dar erro no clique. Acima
  do corte de volume, mostra o progresso do job e o botão de baixar quando fica pronto.
- **`<WizardImportacao recurso="..." contexto={...} />`** — upload → de-para → **conferência linha a
  linha** → decisão. Promoção do `ConferenciaImportacao.tsx` do Orçamento, generalizada: onde lá
  havia colunas de preço fixas no JSX, aqui a tabela é montada das colunas que o **recurso declarou**.
- **`<WizardArquivos recurso="..." contexto={...} />`** — **pasta ou arquivos soltos** → conferência
  → decisão. O gesto do recurso de natureza `arquivo` (§6): escolhe-se um diretório, o navegador
  entrega a árvore por `webkitRelativePath`, e é o **caminho** — não o nome — que carrega a taxonomia
  do acervo. O cartão de *arquivos soltos* fica ao lado do de pasta e cai no mesmo caminho, com o
  palpite saindo do nome quando não há pasta a ler. Isso é o que dispensa o módulo de manter uma
  segunda tela de upload avulso — a Prancheta tinha uma e ela saiu na PRA.9d.
  Prop `ajuda`: a regra que só o **módulo** sabe, renderizada acima dos cartões, no passo de escolher.
  O wizard declara o que o destino recebe e até quantos MB porque isso está no `Recurso`; o que o
  arquivo **vira** ao entrar (no acervo, `ARQ-PLB-001_R02.dwg` é a prancha `ARQ-PLB-001` na revisão
  `R02`) só o módulo sabe dizer. Existe para essa frase não precisar de uma janela anterior só para
  ser lida — uma janela que se abre para hospedar o botão que abre a janela seguinte é um clique
  cobrado por nada.

**Os dois wizards são componentes distintos pela mesma razão que as portas são endpoints distintos**
(§11.1): a natureza muda tudo o que a tela faz. Numa a unidade de decisão é a **linha** de uma
planilha e o passo do meio é o de-para; na outra a unidade é o **arquivo**, e o que se confere é o
que a plataforma adivinhou do caminho. Um `if natureza` no meio de um só daria uma tela com dois
corpos costurados — e quem escolhe qual montar não é a tela do módulo, é a declaração: cada wizard
some sozinho quando a `natureza` do recurso não é a dele.

**O envio em remessas é do teto, e a decisão continua sendo uma.** Uma requisição não pode levar mais
que `DATA_UPLOAD_MAX_NUMBER_FILES` (100, no Django 5.1+), e uma pasta de acervo passa disso com
folga; então o `<WizardArquivos>` pica o envio em remessas de dez. O que **não** se pica é a R1: as
remessas ficam todas em `CONFERINDO` até "Confirmar tudo", e a conferência mostra o conjunto somado.
Aplicar remessa a remessa enquanto o resto sobe deixaria meio acervo gravado se a aba fechasse no
meio — que é exatamente o que a conferência existe para impedir.

Nenhum dos três recebe prop de permissão: quem decide é `/api/impexp/recursos/`. Repetir a regra no
frontend criaria um segundo lugar para ela divergir — e o que divergisse seria justamente o que o
usuário vê.

### 10.1 O teto é dito antes, e ele é do RECURSO

O catálogo é a terceira parte do método do assinador gov.br (§9.1): a tela diz *"até 150 MB, nestes
formatos"* **antes** de a pessoa escolher o arquivo, em vez de o cliente descobrir o limite no 402
depois de esperar o upload.

Para formato **tabular** o número é do plano (`impexp_max_mb`) e `limites.formatos[].max_mb` basta.
Para formato **de arquivo** ele é do **recurso** — `Recurso.teto_mb_do_formato` —, e por um motivo
que aparece dentro de um módulo só: `imagem` no `prancheta.acervo` é prancha escaneada (25 MB) e
`imagem` no `prancheta.marcacoes` é recorte de tela (10 MB). Nenhum número global representa os dois.

Por isso `GET /api/impexp/recursos/` publica **`tetos_mb` por recurso** de natureza `arquivo`,
calculado pela mesma função que a porta chama na hora de aceitar (`teto_do_formato`). A tela prefere
esse campo ao do catálogo global. Publicar por uma conta e aceitar por outra é o
[D83](../historico-correcoes.md): o catálogo anunciava 25 MB para DWG enquanto a porta aceitava 150,
e a primeira tela a acreditar no anúncio recusou sozinha um arquivo bom.

O cliente HTTP e os hooks ficam em [`impexp/api.ts`](../../frontend/src/components/malha/impexp/api.ts)
e [`impexp/hooks.ts`](../../frontend/src/components/malha/impexp/hooks.ts). Módulo novo **não escreve
API nova**.

## 11. Anatomia do app

| Peça | Arquivo | Responsabilidade |
|---|---|---|
| Registry e contrato | `registro.py` | `Recurso`, `Coluna`, `@registrar` — o vocabulário da declaração; `ArquivoRecebido` e `ArquivoEntregue`, as duas pontas da R17 |
| **Porta de entrada** | `entrada.py` | `admitir()` — assinatura de bytes → o que o destino aceita → o que o plano vende → teto → hash. **É o único lugar do sistema que decide se um arquivo entra**, e é onde o antivírus do [D74](#63-varredura-de-vírus--adiada-por-decisão-e-é-aqui-que-ela-entra) entra quando entrar |
| **Porta de saída** | `entrega.py` | `servir()` — `nosniff` + `attachment` (guarda-corpo, não knob: nenhum recurso pede `inline`), tipo declarado pelo recurso, nome saneado, cache que só promete o que a URL sustenta, e o rastro da R12 quando é dado do cliente saindo |
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
| `GET /api/impexp/<recurso>/arquivo/<espécie>/<chave>/` | **a saída de um binário do acervo** (R17). `espécie` e `chave` são opacas ao motor e vão inteiras para `entregar_arquivo`, que é quem conhece domínio |

**Entrega não é exportação, e as duas convivem.** Exportar gera um arquivo tabular a partir do
`queryset`, com recorte (R7), procedência (R9), caminho de job (R10) e linha em `Exportacao`. Entregar
deixa sair **um binário que o recurso já guarda** — não há o que recortar nem o que gerar. Por isso o
gate é outro: `permissoes_entrega`, que é de leitura. A regra do §3 nasceu do risco da planilha com
coluna capada, e abrir *uma* prancha que a pessoa já pode ver no módulo não tem essa forma — foi o
que impediu o gate da saída de fechar o visualizador para o `campo`, que tem `view` e não tem `edit`.

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

## 13. O DMS — coordenação de todo arquivo, dentro e fora do sistema

**Por que aqui, e não num `modulodms`.** A R17 já fazia deste app a porta única de todo arquivo que
entra (`entrada.admitir`) e sai (`entrega.servir`, exportação). Um módulo de documentos à parte
teria duas saídas possíveis, e as duas são a divergência que a R17 existe para impedir: **copiar** o
arquivo para um repositório próprio (dois lugares para o mesmo binário, um deles desatualizado) ou
**reimplementar** a porta (segunda cópia dos guarda-corpos de tipo, nome, gate e auditoria). O que o
DMS acrescenta é **leitura e coordenação** sobre os arquivos que já estão aqui — então ele é este app.

**As três lentes** (`GET /api/impexp/arquivos/?lente=…`, [`arquivos.py`](../../backend/funcoesimpexp/arquivos.py)):

| Lente | Pergunta | De onde vem |
|---|---|---|
| `guardados` | o que está dentro do sistema, de quem, desde quando | cada `Recurso` declara `guardados` — `Guardado(especie, modelo, campo, quando, titulo, onde, filtro)` —, ao lado do `entregar_arquivo` que já tinha. A `especie` é a mesma: listar e baixar fecham pelo mesmo par `(espécie, chave)` |
| `entraram` | o que chegou por lote | `Importacao` (§8) |
| `sairam` | o que deixou o perímetro | `Exportacao` (planilha, PDF) + a entrega de binário auditada (`AuditLog`, `EXPORTAR_DADOS` com `entrega`) |

**O gate é o da entrega** (`acesso.exigir_entrega`): o registro mostra só o que a pessoa poderia
baixar no módulo dono — entitlement e `permissoes_entrega` do recurso —, e o link de cada linha é a
própria URL da entrega. Por isso o DMS **não tem entitlement**, como o resto deste app: quem autoriza
é sempre o dono do dado (§3).

**O invariante** (`test_dms_arquivos`, no molde do D70): todo `FileField` instalado com arquivo do
cliente está em algum `guardados`. Ficam de fora, declarados no teste, só o que o motor produz
(derivada, snap e snapshot da Prancheta), as próprias lentes (`Importacao`, `Exportacao`) e o ZIP da
base-mãe (sem tenant, sem porta). Upload novo sem `Guardado` derruba a suíte com o nome do campo.

**Busca** sem acento no título e no contexto (`__unaccent__icontains`), e no caminho do arquivo.
Página: `PAGINA_PADRAO/MAXIMA["dms"]` do [`planos.py`](../../payment/planos.py), lida pelo
`DmsPageNumberPagination`.

**Tela:** `/app/documentos`, na topbar ao lado de Mapas, Prancheta e Calendário — é uma lente sobre
tudo, não um lugar do ciclo.

**O que o DMS faz a seguir, sobre esta mesma base** (sem segundo armazenamento):

- **Distribuição (GRD — guia de remessa de documentos):** um conjunto de revisões enviado a um
  destinatário, com confirmação de recebimento. É registro sobre arquivos que já existem.
- **Operações de PDF** (marca d'água, carimbo, juntar/dividir) com `pikepdf`: o produto é uma
  **revisão nova**, que entra pela porta como qualquer arquivo (decisões em
  [modulos-planejados.md](modulos-planejados.md)).
- **A base referencial fora do dev** (D185): os arquivos-fonte de cada publicação oficial
  (ZIP/PDF/XLSX) guardados aqui e recarregados em outro ambiente pelo mesmo `carga.executar`
  (`carregar_base_oficial --arquivo`), em vez de um transporte próprio.
- **Convergência dos documentos com ciclo de vida próprio:** `obras.DocumentoObra` tem um fluxo de
  status (rascunho → aprovado → publicado) que repete o de revisão da Prancheta. Unificá-los é a
  próxima convergência, não um terceiro fluxo.

