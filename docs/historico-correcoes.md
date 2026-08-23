# Histórico de correções — achados fechados

> **Natureza: histórico.** Achados de revisão **já corrigidos**, arquivados na íntegra com o
> relato de causa e correção. Saíram de [pendencias.md](pendencias.md), que por definição lista
> só o que está **em aberto**. Nada aqui é pendência: é registro de como o sistema chegou ao
> estado atual. O **desenho** resultante vive nas plantas ([modulos/](modulos/README.md),
> [arquitetura/](arquitetura/README.md)); este arquivo guarda o *porquê* e a data.

IDs: `S*` segurança · `L*` bugs de lógica · `A*` backend/arquitetura · `F*` frontend ·
`D*` achados de auditoria posteriores.

---
### A operação de plataforma morava dentro de um produto vendido, e o hub oferecia upsell ao dono · ✅ corrigido 22/08/2026

Três achados do dono na mesma passada, olhando a tela depois da ORC.8. Os três
são a mesma regra vista de ângulos diferentes: **o que é da plataforma e o que é
do cliente não se misturam, nos dois sentidos.**

**1. A carga da base-mãe morava no módulo Orçamento.** Ela nasceu na tela de
*Bases & bancos*, e o argumento na época era bom: o lugar onde alguém percebe que
a base envelheceu é olhando as publicações. O problema é que a base-mãe não é dado
da empresa — vale para todos os tenants ao mesmo tempo e nenhum deles a edita —, e
ali ela dependia do entitlement `orcamento`, que é régua errada para decidir quem
carrega a SINAPI: o supervisor pode não assinar o módulo, e o assinante não deve
carregar. Mudou-se para **Sistema → Bases oficiais** (`/app/sistema/bases`), com o
painel seguindo como componente do módulo e a tela hospedeira sendo de plataforma.

**2. Não podia aparecer para tenant "nem mesmo como trancado".** O padrão da
sidebar até aqui era mostrar com cadeado o que a pessoa não alcança — e é o certo
para módulo não contratado ou área de admin, porque é caminho que existe para ela
e ela pode destravar. Operação de plataforma não é nada disso: não é vendável, não
é contratável, não é dela. Cadeado ali anunciaria uma porta que não é para o lado
de cá e convidaria a perguntar o que tem atrás.

Saiu daí uma fronteira que agora está escrita em
[frontend-convencoes.md](frontend-convencoes.md) — **omitir × trancar**: `NavItem`
ganhou `platformOnly`, que remove o item da árvore (e a seção vazia some junto,
senão sobraria um título "Sistema" sem nada embaixo, levantando a mesma pergunta);
e [`PlatformRoute`](../frontend/src/components/PlatformRoute.tsx) redireciona em
silêncio, sem o `AccessNotice` que os irmãos dele usam. Para quem não é
supervisor, a rota não existe — que, para ele, é a verdade.

**3. E o inverso: o hub do supervisor mostrava plano e quota.** Este foi o mais
sutil, e o dono o apontou na minha própria fala: eu havia discutido o card
*"Limite de clientes atingido — 2004 de 1000"* **como se fosse normal aparecer
para ele**. Não é. Plano e quota descrevem o que uma *empresa* contratou — quanto
pode cadastrar, quando trava, qual o próximo degrau de venda. Mostrá-los a quem
vende o produto é oferecer upsell a si mesmo, e transformar um número de fixture
num alarme que ele não tem por que resolver. `TabVisaoGeral` oculta a seção e
recolhe a grade para uma coluna.

**Um efeito colateral apareceu no meio disso, e valia mais que o incômodo.** Eu
havia **desativado** (em vez de apagar) as publicações de teste que a ORC.8
deixou. Na rodada seguinte a carga regravou os preços e a tela continuou vazia,
porque `bases-resumo` só lista `ativa=True`. Carregar passou a **reativar** a
publicação que grava: carregar é ato afirmativo — diz *"este mês agora está
aqui"* —, e terminar com sucesso deixando o resultado escondido é a pior das duas
leituras possíveis.

**Provado:** IAM 129/129, backend 1.476 (só os 4 do [D50](pendencias.md)),
E2E ORC.6 59/59 e ORC.8 28/28, `tsc` limpo.

---

### A corrida de carga órfã travava a fonte em definitivo · ✅ corrigido 22/08/2026

Apanhado ao rodar o E2E da ORC.8 pela primeira vez. O `worker` ainda rodava a
imagem antiga (os serviços `worker`/`beat`/`worker-conversao` têm `build:`
próprio no compose — `docker compose build erp` não os toca) e recusou a task com
`unregistered task`. A corrida ficou `pendente` para sempre.

O dano não foi a corrida perdida: foi que **a trava anti-concorrência via uma
carga "em andamento" e recusava toda tentativa nova**, sem saída pela tela. Uma
fonte bloqueada em definitivo por um job que nunca começou.

É a mesma morte violenta que o `nucleo.liberar_cadeiras_presas` trata na frota
desde o D98 — OOM do cgroup, contêiner derrubado, broker reiniciado —, e a
resposta virou a mesma: **"em andamento" passou a ter prazo** (`MINUTOS_ATE_ORFA`,
reusado do `nucleo.frota` em vez de inventar outro número), e a corrida sem
notícia vira `falhou` com o motivo escrito, em vez de sumir — senão o histórico
guardaria uma corrida eternamente "na fila" e ninguém saberia por quê. O
`atualizada_em` é reescrito a cada degrau (baixando, lendo, gravando cada UF),
então carga viva nunca chega perto do prazo; há teste para os dois lados.

---
### O supervisor da plataforma herdava o catálogo do tenant, e aprovou um orçamento de empresa · ✅ corrigido 22/08/2026

Achado pelo dono, testando, horas depois de o usuário `dono` nascer: ele entrou
com o supervisor e **aprovou um orçamento** do tenant `demo` — ato de alçada
financeira, e o oposto exato da regra escrita no mesmo dia (*"superuser não é
para fazer alterações em bancos de dados de empresas"*).

**Causa.** Na IAM, `modulos_efetivos()` e `permissoes_efetivas()`
(`identity/models.py`) tratavam `is_superuser` **igual** a `is_tenant_admin`:
ambos pulavam o filtro de `AcessoUsuarioModulo` e recebiam o catálogo inteiro. O
supervisor tinha **zero papéis** e **zero acessos concedidos**, e mesmo assim o
token dele saía com os 9 módulos e as 184 permissões do tenant onde mora. As duas
camadas do backend fizeram o certo com o que receberam — `RequireModule` viu o
módulo, `RequirePermission` viu a permissão — e deixaram passar.

A herança fazia sentido quando foi escrita: `is_superuser` era o admin do Django,
usado em desenvolvimento, e não havia supervisor no seed. O papel nasceu depois, e
ninguém releu a linha.

**Correção, em duas metades — e a primeira estava errada.**

A primeira tirou a herança do supervisor: ele passou a não receber módulo nem
permissão nenhuma. Durou algumas horas, até o dono olhar a tela: *"ele não pode
ter restrição a nenhum módulo. Tá quase tudo trancado."* E estava certo — um
supervisor que abre o sistema e encontra tudo fechado não é teste supremo de
nada. O erro foi meu, de leitura: confundi **alcance** (o que ele pode abrir) com
**fronteira** (de quem é o dado), e cortei o primeiro para proteger o segundo.

A correção que ficou separa os dois. O supervisor ganhou **régua própria**, a
terceira do arquivo: alcança **todo módulo do catálogo, contratado ou não** — nem
mesmo o admin de tenant tem isso, porque ele para no que a empresa assinou. O que
protege a empresa não é tirar módulo dele; é a **fronteira de tenant**, que vale
para ele como para qualquer um, e o consentimento que ainda vai existir para o
dia em que ele precisar alcançar o banco de um cliente.

O admin de tenant não foi tocado, e há teste cobrando isso: módulo que a empresa
não contratou continua fechado para ele — senão o entitlement não valeria nada
para quem administra o tenant.

**A parte que ensina mais é por que o teste não pegou.** Havia um teste novo em
folha (`nucleo/test_supervisor_nao_le_empresa.py`), escrito horas antes
exatamente para prender esta fronteira, e ele estava **verde**. Ele monta o
cenário com `iam_modules` e `iam_permissions` escritos à mão — ou seja,
**presume** o que o emissor manda, e testa só o que o backend faz depois. A
metade que faltava era perguntar ao emissor.

A régua que fica: *para garantir o que um usuário **pode**, teste o emissor do
token; para garantir o que o backend **faz com** o que recebeu, teste o backend.*
As duas metades existem agora — `iam/identity/tests.py::PermissoesEfetivasTests`
ganhou cinco testes que leem o JWT montado, e o arquivo do backend ganhou no topo
a nota do que ele não prova. Ele também **mudou de nome**, porque o antigo virou
mentira no desenho final: era `test_supervisor_nao_le_empresa.py`, e o supervisor
lê, sim, a empresa onde está — o que ele não faz é atravessar para outra. Agora é
[test_supervisor_nao_atravessa_tenant.py](../backend/nucleo/test_supervisor_nao_atravessa_tenant.py).

**Provado com token real pelo gateway, no desenho final:**

```
dono   modulos=9 perms=184 platform=True  tenant_admin=False | orcamento=200 ORC8=200
demo   modulos=9 perms=173 platform=False tenant_admin=False | orcamento=200 ORC8=403
admin  modulos=9 perms=184 platform=False tenant_admin=True  | orcamento=200 ORC8=403
```

O supervisor alcança tudo; a operação de plataforma continua fechada para o
tenant, **inclusive para o admin dele** com as 184 permissões do catálogo. Suíte
da IAM 129/129, backend 1.476 (só os 4 do [D50](pendencias.md)), E2E ORC.6 59/59
e ORC.8 28/28.

**Sem dano ao dado:** o orçamento aprovado era artefato de E2E (`E2E ORC.6 —
planilha do teste vivo`, v17, total R$ 0,00, sem base referencial).

---
### A linha sem preço na base nova ficava com a data antiga — e o motivo era um só para duas causas · ✅ corrigido 22/08/2026

Pergunta do dono ao fechar a ORC.8: *"quando altera... a base de orçamento e não tem preço na base
mais atual, fica com a data antiga"*. **Fica, e é o desenho certo** — o [D99](#) o construiu: a linha
entra na prévia como aviso (`descontinuado`), nunca é aplicada, mantém preço e `data_base_preco`
antigos enquanto o cabeçalho anda para a data-base nova, e a
[`GradeOrcamento`](../frontend/src/modules/orcamento/components/GradeOrcamento.tsx) a marca em
vermelho depois, por `avisos_de_data_base`. Nada disso mudou.

**O que a ORC.8 quebrou foi a precisão do motivo**, e só apareceu quando alguém foi olhar. Até
então, "não achei este código na publicação de destino" tinha **uma** causa: a fonte aposentou o
item. Com a carga do arquivo nacional passou a ter **duas**, porque a regra 1 do §4.1 — preço em
branco numa UF é ausência, não zero — faz o insumo sem pesquisa naquele estado simplesmente não ter
linha ali. A mensagem, escrita para a primeira causa, dizia da segunda: *"código X não existe na
publicação de destino"*.

Verdade literal, mentira prática. As duas causas pedem **ações opostas**: item aposentado precisa de
substituto; item sem pesquisa está vivo, tem preço em outros estados no mesmo mês, costuma voltar no
mês seguinte, e o caminho é a publicação vizinha, a cotação ou o banco de preço da empresa. Mandar
procurar substituto para um insumo que não morreu é o tipo de erro que só é descoberto depois de
alguém ter feito o trabalho errado.

**Correção:** `_onde_mais_existe` responde, numa consulta só e só quando falta alguém, em que outras
UFs o código existe naquele fonte + mês — excluindo a UF inteira do destino, senão a mensagem
mandaria o orçamentista da Bahia procurar preço na Bahia. Com resposta, o motivo vira *"sem pesquisa
de preço nesta publicação — o item existe no mesmo mês em MG, RJ, SP"*; sem resposta, *"item
aposentado pela fonte"*. O efeito continua idêntico (não há preço novo, a linha fica com a data
antiga, e é isso que o dono descreveu); o que mudou é que quem lê a prévia agora sabe o que fazer.

A distinção mora no `motivo` e não em dois estados de propósito: o **efeito** é um só, e um estado
novo obrigaria todo consumidor de `LinhaReprecificacao` a aprender uma diferença que não muda o que
ele faz.

---
### A13 — a sincronização de bases avisava, mas não buscava · ✅ corrigido 21/08/2026 (ORC.8)

O calcanhar do módulo de orçamento nunca foi cálculo: é **dado fresco**. Desde a ORC.7 a
`moduloorcamento/tasks.py` varria as publicações todo dia e reportava quantos meses cada fonte
estava atrasada — e parava aí. A importação continuava sendo o comando manual, com alguém baixando
o ZIP da Caixa e digitando `--insumos`/`--composicoes`/`--analitica`. Manter 27 UFs × 3 regimes × 12
meses assim não escala, e trabalho recorrente humano é o que atrasa.

**Por que ficou aberto até agora, e isso não foi omissão.** A decisão nº 1 escrita no topo da
`tasks.py` dizia: *"nada de baixar da internet sem fonte declarada — um job que inventa fonte é um
job que um dia importa dado errado com a confiança de um robô"*. O que faltava não era vontade, era
**onde declarar**. A ORC.8 deu esse lugar: [`FonteOficial`](../backend/moduloorcamento/models.py) é
a declaração, escrita por gente, e sem template cadastrado a fonte simplesmente não é tentada — a
regra continua valendo na íntegra.

**O que entrou.** A carga virou um botão para o dono da plataforma (`is_platform_admin`, o mesmo
gate que já guardava a base-mãe em `impexp.py`), com download pausado, leitura do arquivo nacional,
resumo antes de gravar e histórico do que foi tentado. O motor é
[`carga.py`](../backend/moduloorcamento/carga.py) e a busca,
[`oficial.py`](../backend/moduloorcamento/oficial.py); o comando
[`carregar_base_oficial`](../backend/moduloorcamento/management/commands/carregar_base_oficial.py)
abre a mesma porta pela bancada, para a hora em que Celery ou gateway estiverem fora.

**Quatro coisas que o caminho aprendeu e que valem para quem mexer nele:**

1. **O formato largo rende 54 publicações de um arquivo só.** Desde 01/2025 a Caixa publica um ZIP
   nacional com as 27 UFs em **colunas** (abas `ISD`/`ICD`/`ISE` e `CSD`/`CCD`/`CSE`). `SD` é *sem
   desoneração* = regime **onerado**; `CD` é *com* = **desonerado**; `SE` entrou como o regime novo
   `sem`, que é a base legítima do quadro de encargos analítico do ORC.7 — aplicar quadro próprio
   sobre preço que já embute encargo é contar duas vezes.
2. **Preço em branco numa UF é ausência, não zero**, e essa foi a regra que mais moldou o código. O
   `para_decimal` do motor devolve `Decimal("0")` tanto para célula vazia quanto para texto ilegível
   — escolha certa lá, onde zero é um total a somar; aqui seria um insumo a R$ 0,00 atravessando a
   planilha do cliente sem alarme. Daí o `numero_ou_ausencia`, estrito, e a linha que não entra na
   publicação daquele estado.
3. **A analítica é nacional e é guardada uma vez.** O coeficiente não varia por UF — o que varia é o
   preço. Amarrada a cada publicação, seriam ~3,6 milhões de linhas/mês; em `AnaliticaNacional`, ~67
   mil. Convive com `ComposicaoReferenciaItem` sem ambiguidade porque **quem lê é uma função só**,
   `services.componentes_da_composicao`, e a analítica da própria publicação vence quando existe.
4. **O D112 valeu nesta porta também.** Classe que não sabemos traduzir para natureza **para** a
   carga antes de gravar, com o estado `aguardando` — que não é falha, é uma pergunta — e a lista do
   que não soube fazer. O caminho de volta é `cargas/{id}/repetir/`, com ou sem `aceitar_sem_classe`.

**Um defeito real foi achado pelo próprio teste, e ele é do tipo que só aparece no plano B:**
`abrir_pacote` perguntava "é ZIP?" antes de olhar a extensão — e um `.xlsx` **é** um ZIP (o OOXML é
um pacote de XMLs). A planilha enviada à mão era descompactada em `sheet1.xml`, `styles.xml` e
companhia, e o erro reclamava que não havia planilha dentro da planilha. A ordem das duas perguntas
foi invertida e o caso virou teste.

**Um segundo achado veio do guard do [D70](#):** o `FileField` do arquivo enviado nasceu sem porta
declarada, e o teste que varre todos os `upload_to` o pegou na hora. A saída não foi criar um
`Recurso` — o registry é tenant-scoped e gateado por permissão do catálogo, e a base-mãe não tem
tenant nem permissão própria; inventar uma só para satisfazê-lo seria abrir uma porta que ninguém
usa. O ZIP entrou na tabela como `cargas_base: "—"`, **entrada que nunca vira saída**, e o
`CargaBaseSerializer` exclui o campo para que isso continue verdade — com teste cobrando.

**Um terceiro achado veio do próprio E2E, e é o mais operacional dos três: a corrida órfã.** A
primeira execução enfileirou a carga para um worker que ainda rodava a imagem antiga e não conhecia
a task. A corrida ficou `pendente` para sempre — e, pior, **travou a fonte em definitivo**: a trava
anti-concorrência via uma carga "em andamento", recusava toda tentativa nova, e a tela não oferecia
saída nenhuma. É a mesma morte violenta que o `nucleo.liberar_cadeiras_presas` trata na frota desde o
D98, e a resposta virou a mesma: "em andamento" passou a ter prazo (`MINUTOS_ATE_ORFA`, reusado do
`nucleo.frota`), e a corrida sem notícia vira `falhou` com o motivo escrito em vez de sumir. O
`atualizada_em` é reescrito a cada degrau — baixando, lendo, gravando cada UF —, então carga viva
nunca chega perto do prazo; há teste para os dois lados.

**Provado:** 53 testes novos ([test_orc8.py](../backend/moduloorcamento/test_orc8.py)), suíte do
módulo em **380/380**, suíte do backend em **1.467** com só os 4 erros pré-existentes do
[D50](pendencias.md), `tsc` limpo, e o **E2E pelo gateway em 28/28**
([orc8_carga_base_test.py](../../testes/e2e/orc8_carga_base_test.py)), com as imagens reconstruídas e
o stack re-seedado.

**O E2E só existiu porque a IAM ganhou o primeiro `is_superuser` do seed** (`dono`/`dono123`). Até
aqui nenhum usuário tinha `is_platform_admin`, e isso deixava **três** operações sem ator para token
real: a carga da base-mãe, a confirmação de incidente ANPD (9.D) e a publicação de base pública pelo
`impexp`. O contraste que ele permite é o teste mais valioso da leva: o `admin`, que é
`is_tenant_admin` e herda as 184 permissões do catálogo, recebe **403** na carga — porque mandar em
tudo dentro da empresa não é mandar no que vale para todas elas.

**O [A14](pendencias.md) mudou de conteúdo em vez de fechar:** o que falta para SICRO, SEINFRA e
SEDOP deixou de ser "alguém rodar o comando" e passou a ser **um leitor por formato**.

---
### D112 — classe que o sistema não sabe ler era indistinguível de classe ausente · ✅ corrigido 21/08/2026

Pergunta do dono (21/08/2026), ao decidir o D111: *"quando eu importar bases que não tiverem as
mesmas classes de itens, o software vai alucinar, vai me avisar ou vai parar?"*. A resposta era
**nenhuma das três**: caía no plano B da unidade, calado.

**Causa.** `natureza_da_classificacao` casa a classe da fonte por **prefixo** contra uma lista
escrita para o vocabulário da SINAPI. Prefixo que não casa devolve `None` — o **mesmo** `None` de
"campo vazio". As duas causas seguiam para o mesmo lugar sem distinção, e a segunda é pior que a
primeira: no campo vazio (D111) ao menos a ausência é evidente; aqui a fonte **respondeu**, nós é que
não entendemos, e o indicador `classifica_insumo` acendia **verde** porque media só se a coluna veio
preenchida. Uma sondagem contra vocabulários reais mostrou o tamanho: `MATERIAIS` (a classe mais
comum de ORSE e de SICRO) não começa por `material` — troca o `l` pelo `i` — e passava por não
classificada; `LOCAÇÃO DE EQUIPAMENTO`, como a prefeitura escreve, também. Este último é o que
custa dinheiro: em `H`, o plano B o chama de mão de obra, e mão de obra **leva encargo social** sobre
um custo que não é salário — o [D109](#) renascido em outra fonte.

**Correção.** As três causas passaram a ser distinguíveis por `classificacao_desconhecida`: campo
vazio (D111, contado à parte), classe que declara não ser natureza (`ESPECIAIS`, `TAXAS` — essas são
**reconhecidas**, e a resposta delas é "não classifico", então não viram alarme) e vocabulário
desconhecido, o único reportável. O de-para de prefixos virou tabela nomeada
(`services.PREFIXOS_DE_CLASSE`) e ganhou as grafias que faltavam — `materiais`, `maos de obra`,
`locacao de equipamento` —, cada uma com o comentário de por que existe. **Nenhuma delas é
inferência**: é de-para escrito por gente e preso por teste, que é coisa diferente de deduzir
natureza da descrição (o que segue proibido).

O aviso aparece onde alguém o lê: no **`importar_base_referencial`**, com o texto literal da classe e
quantos insumos a usam, no momento em que o operador está olhando; no relatório do
**`reclassificar_itens_catalogo`**, com quantos itens do catálogo dependem de cada uma; e em
**`bases-resumo/`** (`classes_desconhecidas`), que fecha o indicador e escreve as palavras no card da
publicação.

**E a importação passou a parar** *(decisão do dono no mesmo dia, ao ler a primeira versão desta
correção: "quando não puder definir a classe de uma base, deve avisar com uma lista do que não foi
feito e solicitar ao superuser")*. A assimetria com a coluna ausente é o ponto: a diferença entre os
dois casos é **quem tem a resposta**. Base-mãe é global e read-only — só o superuser importa, e o que
ele importa todos os tenants enxergam —, então classe traduzida errado é alavanca de preço para a
plataforma inteira de uma vez, e quem pode respondê-la é justamente quem está rodando o comando. Ele
para **antes de gravar** (publicação meio importada parece completa, e é pior que nenhuma), lista o
que não soube fazer com a contagem por classe, e devolve a pergunta com as duas saídas escritas:
declarar a tradução ou `--aceitar-sem-classe`, que é a decisão consciente de deixar aqueles insumos
entrarem pela unidade. Coluna **ausente** continua não interrompendo: ali não há pergunta a fazer a
ninguém.

Para a pergunta não voltar toda virada de mês, a tradução declarada é **por fonte** e não por
publicação: [`dados/classes/<fonte>.csv`](../backend/moduloorcamento/dados/classes/) (`classe;natureza`),
lido por `services.classes_declaradas` e vencendo o de-para embutido. Em arquivo e não em tabela
porque a decisão é do superuser e vale para a plataforma: assim ela entra no diff e é revisável, em
vez de alguém mudar a natureza de uma classe inteira sem deixar rastro. O casamento ali é **exato**,
e não por prefixo, o que também é o escape do único resíduo conhecido do prefixo — capítulo que
começa com palavra de natureza. O seed tinha um: `grupo="Serviços preliminares"` num ajudante geral
em `H` casava com `servico`, e o item virava serviço de terceiro em vez de mão de obra, deixando de
levar encargo social.

Achado ao rodar contra o banco vivo, e é a prova de que a guarda funciona: as publicações de
demonstração usavam `Agregados`, `Aço`, `Alvenaria`, `Aglomerantes` e `Madeira` como classe —
famílias de material, não naturezas —, e ninguém sabia. Eram ruído do seed, corrigido nele (que
passou a convergir a classificação também nas linhas que já existiam, porque `defaults` do
`get_or_create` só vale na criação) e nas publicações já gravadas.

Três regressões pegas no caminho, todas pelos testes: célula com só espaços passava por resposta
(`if not texto` não pega `"   "`; quem decide é o `normalizar`), o `distinct()` do banco separa
`"Agregados"` de `"Agregados "` e a mesma classe saía duas vezes na tela, e a primeira versão desta
correção deixava a importação seguir — o que a decisão do dono reverteu.

O E2E passou a cobrir as duas garantias no stack vivo (**59/59**): o item adotado chega com a edição
de origem preenchida, e nenhuma publicação do seed tem classe ilegível.

Arquivos: [services.py](../backend/moduloorcamento/services.py) ·
[importar_base_referencial.py](../backend/moduloorcamento/management/commands/importar_base_referencial.py) ·
[reclassificar_itens_catalogo.py](../backend/moduloorcamento/management/commands/reclassificar_itens_catalogo.py) ·
[views.py](../backend/moduloorcamento/views.py) ·
[BasesPage.tsx](../frontend/src/modules/orcamento/pages/BasesPage.tsx).

---
### D111 — publicação anterior a 01/2025 não classifica insumo, e o catálogo ficava todo em "material" · ✅ corrigido 21/08/2026

Achado do dono na tela (21/08/2026), olhando a analítica: escavadeira hidráulica, caminhão trucado e
caçamba basculante todos como **Material**.

**Causa — e não é defeito de importação, foi conferido no banco.** A publicação carregada é a SINAPI
BA 10/2024, com 12.548 linhas e **nenhuma** com preço zerado (escavadeira R$ 903.480,94 em `UN`, que
é o custo de aquisição como a fonte publica; óleo diesel R$ 5,97 em `L`). O que falta é a
classificação: das 7.737 composições, todas têm `grupo` preenchido — mas é o **capítulo**
("MOVIMENTO DE TERRA", "FUNDAÇÕES E ESTRUTURAS"), que não classifica insumo; dos 4.811 insumos,
**zero**. A coluna `Classificação` só existe a partir de 01/2025. Sem ela a adoção cai no plano B,
que é a unidade; e `UN` não é hora nem mês, então tudo o que não é mão de obra vira material. A
ORC.9 corrigiu **quem pergunta** — a classificação da fonte passou a mandar —, mas não inventa
resposta onde a fonte não deu. Encargo social **não** é afetado (esse depende de mão de obra, que a
unidade acerta); o que sai torto é a leitura "material × mão de obra × equipamento" na composição
por natureza, na curva ABC de insumos e no resumo do Controlar.

**Correção — declarar o buraco e dar a ferramenta, sem adivinhar.** O que **não** se fez, e fica
registrado para não ser proposto de novo: deduzir a natureza pelo texto da descrição ("contém
CAMINHÃO → equipamento"). É a mesma classe de palpite que produziu o D109 — serviço de terceiro
levando encargo social porque a unidade dizia hora. No lugar disso:

1. **O sistema passa a dizer.** `GET /api/orcamento/bases-resumo/` devolve `classifica_insumo` e
   `insumos_classificados`, e o card da publicação em Bases & bancos marca *"não classifica insumo —
   tudo que não é hora/mês é adotado como material"*. O usuário sabe disso **ao escolher a base**, e
   não estranhando a analítica meses depois — que foi como este achado apareceu. O comando
   `reclassificar_itens_catalogo` conta e declara o mesmo no relatório, separando "sem classificação
   na fonte" (o caso daqui) de "sem publicação carregada" (procedência órfã).
2. **`--de-para arquivo.csv` existe** — era o caminho 2 dos três levantados, e o único que precisava
   de código. A empresa classifica em planilha só o que importa — as poucas centenas de equipamentos,
   não os 4.811 insumos — em `codigo;natureza[;fonte]`, com cabeçalho opcional, aceitando tanto o
   rótulo publicado (`EQUIPAMENTO`, `MÃO DE OBRA`) quanto a chave interna (`equipamento`,
   `mao_de_obra`). Declaração explícita da empresa **vence** a classificação da fonte — quem escreveu
   o arquivo estava olhando o item —, e quando as duas discordam isso sai no relatório em vez de
   passar calado. Linha que o comando não sabe aplicar **derruba o arquivo inteiro** com a lista do
   que está errado: pular em silêncio faria quem classificou trezentos itens ir embora achando que
   aplicou trezentos.

**O que a decisão do dono foi, com os números na mesa (21/08/2026).** O levantamento no banco mudou o
tamanho do problema: dos 4.811 insumos da publicação, o tenant **adotou 86 itens**, e só **29**
dependem dela — todos em uso (28 em composição). Desses 29, **15 estavam certos** pela unidade
(pedreiro, servente, armador, motorista, operador em `H`; areia, aço, arame, cabo, diesel, gasolina)
e **14 errados**, em dois grupos: 4 equipamentos em `UN` lidos como material (escavadeira, caminhão
trucado, caçamba, compactador — a queixa que abriu o achado) e **10 encargos complementares em `H`
lidos como mão de obra** (EPI, ferramenta, alimentação, transporte, exame, seguro), que por isso
recebiam encargo social de 84,70% sobre custo que não é salário. Não havia dinheiro perdido ainda —
nenhum orçamento com preço usava essa publicação —, mas o erro estava armado nas composições.

Escolhido o caminho 2: o de-para de **14 linhas** em
[`dados/classificacao-sinapi-ba-2024-10.csv`](../backend/moduloorcamento/dados/classificacao-sinapi-ba-2024-10.csv),
aplicado em 21/08/2026 (`Mão de obra → Encargos complementares: 10`, `Material → Equipamento: 4`). O
caminho 1 **segue aberto** e não foi descartado: importar uma publicação 2025+ classifica os 4.811 e
faz a adoção futura nascer certa, e a conferência de identidade do D110 é o que o torna seguro. Ele
custa mais do que a pendência supunha — não há arquivo SINAPI em disco, e o importador ainda não lê o
formato largo de 2025 sozinho (seria `--aba ISD --colunas preco=<posição da UF>` na mão; é a ORC.8
que faz disso um clique). O caminho 3 fica para quando a empresa quiser o **próprio nome** do item,
que é outra conversa.

**Nota de leitura, que confundiu na primeira olhada:** a planilha que o dono abriu mostrava também
coeficiente e preço zerados em todas as linhas. Aquilo era outra coisa — o orçamento em questão
(`E2E ORC.6 — planilha do teste v17`, resíduo da suíte E2E) está **sem base referencial vinculada**,
e insumo sem preço conhecido entra com custo zero de propósito, para o furo ficar visível
([precificacao.py](../backend/moduloorcamento/precificacao.py)). Em orçamento com base — o
"Orçamento executivo — Torre A" — os números saem certos.

Arquivos: [reclassificar_itens_catalogo.py](../backend/moduloorcamento/management/commands/reclassificar_itens_catalogo.py) ·
[views.py](../backend/moduloorcamento/views.py) ·
[BasesPage.tsx](../frontend/src/modules/orcamento/pages/BasesPage.tsx).

---
### D110 — o código casava insumo por **código** e não conferia que era o mesmo item · ✅ corrigido 21/08/2026

Decisão do dono (21/08/2026), logo depois do D109: *"o código tem que detectar quando os itens não
são os mesmos e não inventar classificação"*.

**Causa.** Dois lugares tratavam "mesmo código" como "mesmo insumo", sem olhar mais nada. A
**adoção** (`services._localizar_item` e o irmão em `bancos.py`) achava o `catalogo.Item` pelo par
`(fonte, codigo_referencia)` e o `adotar_no_catalogo` **sobrescrevia `descricao` e `unidade`** com o
que a publicação nova dissesse. A **reclassificação** montava o de-para lendo `InsumoReferencia` por
`codigo__in`, indexava por `(fonte, código)` e deixava o **último registro lido vencer**.

Enquanto for a SINAPI — estável nos códigos de insumo — e uma publicação por fonte, funciona. Deixa
de funcionar quando a fonte reaproveita o número entre edições, que é o que tabela de prefeitura faz,
e é para onde o produto ia: várias publicações por fonte (o histórico que a ORC.8 planeja), bancos
próprios copiados da base pública e tabelas de prefeitura importadas pelo motor. O `1379` que era
*cimento CP II, KG* vira *locação de betoneira, H*; a adoção não estranha nada, reescreve descrição e
unidade, e o item do catálogo passa a se chamar outra coisa **carregando o histórico do anterior** —
as composições que o referenciam e as planilhas continuam apontando para ele. A reclassificação então
lê o `1379` da edição nova, conclui "equipamento" e carimba essa natureza no item que, para as
composições antigas, ainda é cimento: encargo, relação de compra e saldo em estoque passam a seguir a
regra errada. E ninguém vê — não há erro na tela nem linha vermelha em lugar nenhum, só um preço
diferente do que deveria ser, descoberto pelo orçamentista que estranhar o total.

**Correção — divergiu, não classifica e não sobrescreve: reporta.** A pergunta que faltava (*"o item
que eu achei pelo código é mesmo o item que a publicação está descrevendo?"*) virou
[`identidade.py`](../backend/moduloorcamento/identidade.py). Descrição e unidade estão nas duas
pontas e respondem, cada uma do seu jeito:

- **unidade** por igualdade sobre a forma normalizada (sem acento, sem pontuação, caixa única), com
  as poucas grafias que as publicações alternam para a mesma unidade reunidas num de-para curto
  (`UND`/`UN`, `m³`/`M3`). Unidade diferente é sinal forte: o coeficiente da composição foi escrito
  contra a régua antiga;
- **descrição** por **semelhança de conjunto de palavras** (Jaccard), e não por igualdade. A fonte
  reescreve a redação entre edições sem trocar o insumo — igualdade estrita acusaria divergência em
  toda republicação, e guarda que grita errado é desligada na terceira vez. O limiar fica em código
  de engenharia por ser parâmetro de **acerto**, não teto de plano: registrado na §5.6 do
  [`planos.py`](../payment/planos.py), ao lado do `JANELA` do extrator de CEP.

Com a resposta na mão, cada ponta decide:

- **adoção** — item existente cuja identidade não confere não é atualizado em silêncio: levanta
  `IdentidadeDivergente` e **não grava nada**. Em lote, o divergente fica de fora e volta listado, os
  outros entram. Pela API é **409** (não 400: nada está errado com o pedido — o conflito é de
  identidade) com os dois lados no corpo, e `{"forcar": true}` é a decisão de quem olhou e disse que
  é o mesmo item. Composição cujo componente diverge derruba a composição inteira, e o `atomic`
  desfaz tudo — pai apontando para filho errado é o mesmo dano com outro nome;
- **reclassificação** — o de-para deixou de ser "último lido vence": todos os candidatos de cada
  `(fonte, código)` são conferidos contra o item. Nenhum confere → fica de fora e sai no relatório
  como "não confere — conferir à mão"; conferem mas discordam da natureza → "ambíguo", também de
  fora, porque duas edições afirmando coisas diferentes sobre o mesmo item é pergunta para gente e
  não para o comando.

**A procedência que faltava.** O par `(fonte, código)` era tudo o que o item guardava, e com ele não
havia como saber de qual edição veio a descrição gravada. `catalogo.Item` ganhou
`publicacao_referencia` ([migration 0005](../backend/catalogo/migrations/0005_d110_publicacao_de_origem_do_item.py)),
rótulo durável e não FK — pelo mesmo motivo do `importada_por_nome` da base: o catálogo é do tenant,
a publicação é global, e apagar uma publicação não pode apagar a procedência do item.

Na tela, o que ficou de fora aparece: painel com os dois lados na aba de bases, aviso no modal de
inserir item (senão o orçamentista marca cinco, vê quatro na planilha e não sabe do quinto) e
contagem no recado da adoção de banco.

Arquivos: [identidade.py](../backend/moduloorcamento/identidade.py) ·
[services.py](../backend/moduloorcamento/services.py) ·
[bancos.py](../backend/moduloorcamento/bancos.py) ·
[reclassificar_itens_catalogo.py](../backend/moduloorcamento/management/commands/reclassificar_itens_catalogo.py) ·
[views.py](../backend/moduloorcamento/views.py) · [catalogo/models.py](../backend/catalogo/models.py) ·
[BasesPage.tsx](../frontend/src/modules/orcamento/pages/BasesPage.tsx) ·
[InserirItemModal.tsx](../frontend/src/modules/orcamento/components/InserirItemModal.tsx).
Testes: [test_identidade.py](../backend/moduloorcamento/test_identidade.py) (32).

---
### D109 — serviço de terceiro levava encargo social, e a coluna que resolvia isso era descartada · ✅ corrigido 21/08/2026

Achado do dono (20/08/2026): *"Colocar Mão de obra em 'itens, composição, equipamentos…'. Já existe
algo do tipo na documentação e tem que ver o que a tabela SINAPI considera, para aplicar também"*.
O pedido era de vocabulário; embaixo dele havia um defeito de preço.

**Causa.** `catalogo.Item.Tipo` não tinha `mao_de_obra`. A adoção olhava a **unidade** (`H`/`MES`) e
gravava `Tipo.SERVICO`; do outro lado, `precificacao.categoria_do_item` lia **todo** `SERVICO` como
mão de obra para aplicar encargo social. O par funcionava por acidente para o pedreiro e errava para
o **serviço terceirizado**: ele levava o percentual de encargos sobre um preço que já vem com o
encargo do subcontratado dentro. Ninguém via — não é erro, é número maior.

Do mesmo jeito, `ENCARGOS COMPLEMENTARES` (EPI, exame, alimentação, transporte) caíam em "material":
some da leitura o fato de que eles acompanham a hora de mão de obra **sem** receber encargo por cima.

E a resposta estava disponível o tempo todo: a SINAPI publica desde 01/2025 a coluna
`Classificação`, com MATERIAL · MÃO DE OBRA · EQUIPAMENTO · ENCARGOS COMPLEMENTARES · SERVIÇOS ·
ESPECIAIS. O importador a lia e **descartava**, porque `ALIASES` tinha `grupo`, `classe` e
`categoria` — e não `classificacao`. O `moduloorcamento.md` já descrevia a coluna; faltava o
sinônimo de uma palavra.

**Correção.** `Item.Tipo` ganhou `mao_de_obra` e `encargos_complementares`, e `servico` passou a
significar o que o nome diz — serviço de terceiro, que **não** leva encargo. `ItemOrcadoInsumo`
ganhou a categoria correspondente. A adoção decide por ordem de confiança: composição → classificação
da fonte → unidade (plano B, agora devolvendo mão de obra) → material; capítulo de composição
("ESTRUTURAS") não é lido como natureza. Quem incide encargo saiu de `categoria == MAO_DE_OBRA`
espalhado para `precificacao.leva_encargo_social`, um lugar só.

O que já estava adotado é corrigido por
[`reclassificar_itens_catalogo`](../backend/moduloorcamento/management/commands/reclassificar_itens_catalogo.py):
`--dry-run` imprime o de-para antes de gravar; sem o flag corrige o catálogo e refaz **só os
rascunhos** (planilha aprovada é a régua da medição feita contra ela). Linha cujo custo unitário
deixou de ser a soma dos insumos — preço real do SCM/SIL ou digitado — tem a categoria corrigida e o
**preço mantido**, com o aviso no relatório. No `demo`: 18 itens de `Serviço` → `Mão de obra`, 1 de
material → equipamento, sem mudança de valor (esses já vinham recebendo encargo pelo caminho errado).

O desenho que veio junto — tipos próprios do tenant e as permissões `orcamento.banco.*` /
`cadastro.tipo_item.*` — está nas plantas: [moduloorcamento.md §12.1](modulos/moduloorcamento.md) e
[catalogo.md](modulos/catalogo.md).

Arquivos: [catalogo/models.py](../backend/catalogo/models.py) ·
[services.py](../backend/moduloorcamento/services.py) ·
[bancos.py](../backend/moduloorcamento/bancos.py) ·
[precificacao.py](../backend/moduloorcamento/precificacao.py) ·
[leitura.py](../backend/moduloorcamento/leitura.py).

---
### D106 — o seletor sintético × analítico não mudava nada na planilha · ✅ corrigido 20/08/2026

Achado do dono (20/08/2026): *"O sintético e analítico não altera nada em orçamento. Deveria mostrar
os itens e subitens"*.

**Causa.** Os dois modos eram lidos como **profundidade de EAP**, não como as duas peças da SINAPI. A
grade filtrava `tipo_linha === 'sintetico' || nivel <= 1` e a exportação, `codigo_eap.count(".") <= 1`
— numa planilha de dois níveis (etapa 1 → serviço 1.1, que é a esmagadora maioria) **nada** é
escondido e os dois modos desenham exatamente a mesma tela; numa de três níveis, o corte escondia
serviço com preço e a planilha deixava de fechar com o total do rodapé. Pior: "analítico" nunca abria
a composição — os insumos existiam (`ItemOrcadoInsumo`, `memoria/`, `composicao-natureza/`) mas só
dentro do drawer de uma linha por vez.

**Correção.** Sintético e analítico passaram a ser o que são na fonte: a **mesma planilha inteira**
com e sem a composição. Nenhum serviço some ao trocar de modo. O analítico pendura, embaixo de cada
serviço, as linhas de insumo com natureza, consumo (coeficiente × quantidade do serviço), preço e a
parcela — que soma o custo direto daquele serviço, para conferir sem refazer conta. Insumo não repete
BDI nem peso do orçamento (já está contido no serviço acima) e não entra na navegação por teclado nem
no colar-do-Excel: o cursor da grade continua andando só sobre as linhas da planilha.

Serviço **sem composição gravada** deixou de parecer serviço sem insumo: a linha diz *composição não
explodida* com o atalho para explodir (quando veio do catálogo) ou *preço digitado* (quando não tem o
que abrir). Dado honesto, não silêncio.

A composição da planilha inteira vem numa consulta só, em
`GET /api/orcamento/orcamentos/{id}/analitica/` — resposta separada da `arvore/` de propósito: trocar
de modo não pode descartar a planilha já carregada, e quem lê em sintético nunca chega a pedir esta.
A exportação XLSX/PDF ganhou a mesma régua, com as linhas de insumo recuadas e o rodapé do PDF
explicando por que elas não repetem BDI.

Arquivos: [GradeOrcamento.tsx](../frontend/src/modules/orcamento/components/GradeOrcamento.tsx) ·
[precificacao.py](../backend/moduloorcamento/precificacao.py) ·
[exportacao.py](../backend/moduloorcamento/exportacao.py) ·
[views.py](../backend/moduloorcamento/views.py).

---
### D107 — não havia como voltar para todas as obras de dentro de um orçamento · ✅ corrigido 20/08/2026

Achado do dono (20/08/2026): *"Em orçamento, não consigo voltar para todas as obras quando estou em
um orçamento"*, com a régua de *"verifique como os grandes sites fazem isso"* — respondida com o
desenho do setor (Sienge, OrçaFácil): entra-se **pela obra**.

**Causa.** Não era falta de botão, era estado. Orçar era uma tela só, dirigida por dois `<select>` no
cabeçalho, com o orçamento em `?orcamento=`. Um efeito reescrevia o filtro —
`useEffect(() => { if (orcamento && obraId === '') setObraId(orcamento.obra) }, [orcamento, obraId])`
— com `obraId` na lista de dependências: escolher "Todas as obras" era desfeito no mesmo tique pela
obra do orçamento aberto. Fora isso, **não existia lugar nenhum para voltar**: filtro não é endereço,
e por isso não havia trilha, link colável nem botão voltar do navegador.

**Correção.** Três níveis, três rotas: `…/orcar` (as obras, com quantos orçamentos cada uma tem e o
valor da versão que vale), `…/orcar/obra/{obra}` (as versões daquela obra) e
`…/orcar/orcamento/{id}` (a planilha), com trilha clicável no topo — *Obras › Residencial Alfa ›
Orçamento base v2*. Criar orçamento saiu da planilha e foi para a lista, que é onde a pergunta
"em qual obra?" já está respondida (o modal virou
[ModalNovoOrcamento.tsx](../frontend/src/modules/orcamento/components/ModalNovoOrcamento.tsx), usado
pelos dois níveis). Revisar e duplicar passaram a **navegar** para a planilha nova em vez de reescrever
um parâmetro de busca. Os links de outras páginas (Hub, Controlar, Incorporação) foram atualizados.

Arquivos: [ObrasOrcamentosPage.tsx](../frontend/src/modules/orcamento/pages/ObrasOrcamentosPage.tsx) ·
[OrcarPage.tsx](../frontend/src/modules/orcamento/pages/OrcarPage.tsx) ·
[routes.tsx](../frontend/src/modules/orcamento/routes.tsx).

---
### D108 — o modal de revisar orçamento estava escrito em bloco · ✅ corrigido 20/08/2026

Achado do dono (20/08/2026): *"Revisar orçamento a escrita do texto esta desorganizada"*.

**Causa.** O aviso era um parágrafo só com **três fatos** dentro (a versão atual vira superada; as
medições já feitas não mudam de base; a nova nasce em rascunho com a árvore copiada) — e o do meio,
que é a garantia que interessa a quem tem medição em campo, era justamente o que se perdia na
leitura. Abaixo dele, um `<select>` com Aditivo · Supressão · Reequilíbrio · Correção **sem dizer o
que cada um significa**, embora a escolha vire histórico de contrato e seja o que se mostra numa
auditoria.

**Correção.** O aviso virou três linhas, uma por fato, sob um título que diz do que se trata
(*o que acontece ao confirmar*). O select virou quatro opções com o efeito de cada uma em uma linha
("acrescenta ao aprovado, o valor sobe" · "retira do aprovado, o valor desce" · "mesmo escopo, preço
corrigido" · "conserta erro sem mudar o combinado"). O motivo ganhou a dica que explica **para onde
ele vai** — o histórico da revisão, junto com o valor antes e depois — e a mensagem de erro deixou de
falar em "aditivo" quando o tipo escolhido pode ser outro.

Arquivo: [OrcarPage.tsx](../frontend/src/modules/orcamento/pages/OrcarPage.tsx).

---
### D102 — inserir item na planilha: sem passar página, sem cesta e com a rolagem vazando · ✅ corrigido 17/08/2026

Três pedidos do dono no mesmo modal (17/08/2026), depois do D101: *"Não preciso buscar por codigo
para chegar no resto. Quero a lista toda. Ou no mínimo um seletor de quantidade com um passar
página"* · *"o scroll... tem que ser mais suave"* · *"Coloque para ver os itens marcados e poder
desmarcar"*, e em seguida *"Ao invés de abaixo. Coloque do lado. Apenas nome e codigo"*.

**Passar página.** O modal buscava `page_size: 40`, uma requisição só, e o rodapé mandava buscar por
código — resposta errada para quem não sabe o código. Ganhou seletor de **quantidade** (25/50/100) e
navegação `« ‹ › »` com `página X de Y` e o total. A lista inteira numa requisição **não é possível**:
`PAGINA_MAXIMA["orcamento"]` é 100 em [planos.py](../payment/planos.py), e o teto é decisão do dono,
não de engenharia — para vir mais por vez, o número muda lá.

**Rolagem.** O que fazia "pegar" não era o número de itens: o container tinha `330px` fixos e **sem
`overscroll-behavior`**, então ao terminar a lista a rolagem vazava para a página atrás do modal
(*scroll chaining*). Agora `overscroll-behavior: contain`, `scrollbar-gutter: stable` (a lista saltava
de lado quando a barra aparecia), altura `min(52vh, 520px)` no lugar dos 330px fixos, e a barra fina
do `.orc-grade` que o resto do módulo já usava. Trocar de página volta ao topo com `scrollTo`
suave — sem isso a página nova começava na altura da anterior e parecia que nada acontecera.

**Cesta.** O rodapé só dizia *"5 item(ns) marcado(s)"*: um número sem rosto. Quem marca ao longo de
várias páginas e buscas perde a conta, e tirar um errado exigia reencontrá-lo na lista — depois de
trocar de filtro, uma caçada. Entrou um painel **lateral** (não embaixo: embaixo sai de vista quando
se rola, e cesta que some não serve de conferência) com **só código e nome** — preço e unidade já
estão na linha da lista, e repeti-los encolheria o nome. Cada linha tem o `×` para desmarcar, mais um
`limpar`. As duas origens (base pública e catálogo da empresa) aparecem juntas, porque para quem monta
a planilha *"o que eu já escolhi"* é uma lista só.

**Corrigido no mesmo dia, ainda antes de sair da mão do dono:** a cesta nasceu **elástica** e comia a
lista. Dois enganos de flexbox, um por dimensão. Na **altura**, a linha não tinha altura própria, então
assumia a do filho mais alto: cada item marcado esticava o bloco e empurrava a seleção para fora da
tela → `height: min(52vh, 520px)` fixa na linha, e a lista virou `flex: 1; min-height: 0` para rolar
por dentro. Na **largura**, `flex: 0 0 246px` não segura sozinho — item flex nasce com
`min-width: auto`, e conteúdo largo empurra a caixa → `minWidth: 0` + `maxWidth: 246` explícitos, com
teto e reticências também no código do item. O bloco agora tem o mesmo tamanho vazio ou com cinquenta
itens.

Junto disso, `title` nas descrições truncadas — na cesta e nas listas de seleção do modal e da
`BasesPage`. Descrição de composição da SINAPI passa de 130 caracteres e o que cabe na linha é sempre
um pedaço; sem o `title`, escolher entre "ARMAÇÃO… VERGALHÃO DE 5,0 MM" e "…DE 12,5 MM" dependia de
adivinhar o final.

**Ainda a pedido do dono, no mesmo dia — a linha da lista devolvida à descrição.** Dois elementos
comiam largura no meio da linha e, por só existirem em algumas delas, faziam as colunas da direita
dançar: a pílula escrita `já no catálogo` e o botão de texto `ver analítica`. Viraram marcas, em
`ui.tsx` para as três listas usarem a mesma: `MarcaCatalogo` (bolinha cheia/vazada — o estado
negativo é **desenhado** justamente para a coluna ter largura constante) e `BotaoAnalitica` (seta,
que aponta para baixo quando aberta, como a árvore da planilha já faz). `LegendaLista` explica as
duas embaixo da lista: marca sem legenda é charada. A janela também cresceu — `largura` 880 → 1240 e
o respiro do overlay de `7vh` para `4vh`, que devolveu 6% da altura da tela ao conteúdo.

---
### D101 — a base referencial era inalcançável a partir do item 51 · ✅ corrigido 17/08/2026

Relatado pelo dono (17/08/2026): *"Só vejo algumas dezenas no 2024"*, sobre a publicação **SINAPI BA
10/2024**, que tem **12.548 itens**. O dado estava correto no banco e correto na API — a tela é que
não tinha como pedir a página 2.

`BasesPage` chamava `useReferencias` com `page_size: 50` e **uma requisição só**. A lista terminava
na quinquagésima linha dentro de uma caixa de 330px de rolagem, e a única saída oferecida era um
rodapé dizendo *"refine a busca"*. Para um catálogo de 12,5 mil linhas isso não é navegação: quem não
sabe o código exato precisa **percorrer**, e percorrer era impossível — o item 51 não existia para a
interface.

**Correção.** `useReferenciasInfinitas` (`useInfiniteQuery`), com `page_size: 100` — o teto real,
`PAGINA_MAXIMA["orcamento"]` em [planos.py](../payment/planos.py) — e botão **Carregar mais** ao pé
da lista, com quantos faltam. O `getNextPageParam` decide pelo `next` que o DRF devolve, e não por
uma conta de `count ÷ page_size`, que erraria justamente na última página. O rodapé passou a dizer
`N de 12.548 itens desta publicação`, com o total em negrito: uma lista que acaba sem dizer o
tamanho do todo é o que produziu a leitura "só tem algumas dezenas".

Conferido contra a publicação real: 126 páginas, a última com `next: null`.

**Mesmo defeito, remédio diferente, no `InserirItemModal`:** ali a lista é curta de propósito (num
modal se acha buscando, não rolando 12 mil linhas), mas ela também terminava sem avisar. Ganhou só a
frase do corte — `Mostrando 40 dos 12.548 itens da publicação`. Rolagem infinita ali seria responder
à pergunta errada.

---
### D100 — a data de corte da reprecificação derrubava a requisição com 500 · ✅ corrigido 17/08/2026

Relatado pelo dono (17/08/2026) direto da tela: preencher *"Só linhas com preço até"* e clicar em
**Ver a prévia** devolvia `500 Internal Server Error` / "Não foi possível concluir a operação".

```
TypeError: '>' not supported between instances of 'datetime.date' and 'str'
```

`somente_ate` vem do corpo do POST, e **JSON não tem tipo data**: a view passava a string crua
(`request.data.get("somente_ate") or None`) para o serviço, que a comparava com o `date` de
`item.data_base_preco`.

**Por que a suíte não pegou**, embora houvesse teste para a data de corte: os testes chamam
`gerar_previa` com `date(2026, 7, 1)` já pronto. O defeito morava exatamente no degrau entre a API e
o serviço — o único trecho que nenhum dos dois lados exercitava. É o mesmo formato de armadilha do
D76 (o objeto indo onde se esperava o código).

**Correção** em `_como_data()`, na fronteira do serviço e não na view: quem chama pelo shell continua
mandando `date`, quem chama pela API manda string, e a coerção fica num lugar só. Aceita ISO
(`2026-08-17`, o que o `<input type="date">` manda) e `dd/mm/aaaa`. O que não for data vira
`ReprecificacaoInvalida`, que a view já traduzia para **400** — pedido ruim é do cliente, não falha
do servidor. Três testes novos, um deles cobrindo justamente a string ISO. Suíte **269/269**.

**Também nesta correção, a pedido do dono:** o item aposentado **permanece** na planilha com o preço
e a data-base que tinha (já era o comportamento do D99), e a grade do Orçar ganhou a coluna
**Data-base**, ao lado do custo unitário — a linha anterior à data-base do cabeçalho aparece marcada
em `danger` com o motivo no *tooltip*. Sem a coluna, o aviso existia só na API e no lote; agora está
onde a pessoa olha.

---
### D99 — o item aposentado pela SINAPI sumia da prévia, e a planilha mentia a data-base · ✅ corrigido 17/08/2026

Pedido do dono (17/08/2026), ao desenhar a carga automática da SINAPI: *"os excluídos não podem
aparecer com valor 0. Caso isso ocorra, no orçamento do usuário tem que ter o aviso."*

Ao conferir, o defeito era pior que o zero — era o **silêncio**. Em `gerar_previa`, o código ausente
na publicação de destino caía num `continue`:

```python
novo = precos.get(item.codigo_referencia)
if novo is None:
    continue          # pulado, sem contagem e sem rastro
```

A SINAPI aposenta item todo mês. A linha não virava zero: ficava com o **preço velho**, fora da
prévia e fora do lote. Aplicado o lote, o cabeçalho passava a anunciar a data-base nova e aquela
linha continuava na antiga. A peça que vai para a licitação dizia "julho" carregando junho por
dentro, com aparência de correta — que é o que a torna perigosa numa auditoria.

**Correção em três camadas, porque o problema aparece em três momentos:**

1. **No lote** — a linha descontinuada passa a **existir**, com `descontinuado=True`,
   `custo_depois == custo_antes` e `selecionada=False`. Entra para ser vista, nunca para ser
   aplicada; `aplicar` a filtra mesmo que venha marcada no pedido, porque aceitar a seleção gravaria
   preço velho com procedência nova. `linhas_afetadas` deixa de contá-la (ela não muda preço) e
   `linhas_descontinuadas` a conta à parte.
2. **No orçamento** — `avisos_de_data_base()` e `GET /api/orcamento/orcamentos/{id}/avisos/`: as
   linhas cujo `data_base_preco` é anterior à `data_base` da planilha. Fica no orçamento, e não no
   lote, porque é a **planilha** que vai para a licitação — quem a abrir meses depois não vai atrás
   do histórico de lotes. É **derivado**, não gravado: um campo "está desatualizada" seria uma
   terceira verdade a sincronizar, e dessincronizaria na primeira reprecificação parcial.
3. **No total** — `_total_simulado` ignora a descontinuada, senão a prévia anunciaria efeito que não
   tem.

O aviso pega mais que o item aposentado: pega também a linha que o operador desmarcou na prévia. É
deliberado — para a auditoria as duas são o mesmo defeito.

Migration `0009_orc7b_aviso_item_descontinuado`. Seis testes novos em `test_orc5b.py`
(`ItemDescontinuadoTests`); suíte `moduloorcamento` **266/266**. Provado também contra dado real: o
orçamento demo reprecificado para a SINAPI BA 10/2024 acusa o insumo `00000370` como descontinuado —
antes, o lote vinha vazio e o usuário lia "nada a atualizar".

---
### D98 — o importador não reconhecia o arquivo mais usado da SINAPI · ✅ corrigido 17/08/2026

Achado ao carregar a primeira publicação **real** da SINAPI (BA 10/2024 não desonerado, o pacote
oficial da Caixa) para começarem os testes de usuário. Dos três XLSX do pacote, o comando lia o de
insumos e a analítica, e falhava no **sintético** — justamente o arquivo que traz o custo de todas as
7.737 composições:

```
CommandError: Não reconheci o cabeçalho de sintetico.xlsx (esperava ('codigo', 'descricao', 'unidade', 'preco')).
```

**Causa.** A detecção casa o cabeçalho por **igualdade exata** com os sinônimos de `ALIASES`
([leitura.py](../backend/moduloorcamento/leitura.py)). No sintético a Caixa não escreve `CODIGO` nem
`DESCRICAO`: escreve **`CODIGO DA COMPOSICAO`** e **`DESCRICAO DA COMPOSICAO`** — nomes que existiam
no `ALIASES`, mas sob os campos `codigo_composicao`/`descricao_composicao`, que só são obrigatórios na
analítica. `unidade` e `preco` (por `custo total`) casavam; os dois primeiros não, e sem eles a
planilha inteira caía no `--colunas` manual.

**Por que não bastou acrescentar os dois nomes ao `ALIASES` geral.** Foi a primeira tentativa, e ela
quebra a analítica: lá as mesmas colunas **pertencem** a `codigo_composicao`/`descricao_composicao`, e
como o mapeamento marca a posição usada, um `descricao` genérico capturaria a coluna 8 antes e
deixaria `descricao_composicao` sem mapa — a composição criada a partir da analítica nasceria **sem
descrição**. Um sinônimo certo para um arquivo é errado para o outro; o que faltava era escopo.

**Correção.** `EXTRAS_POR_ARQUIVO` em `leitura.py`: sinônimos que valem para **um** tipo de arquivo,
acrescentados ao **fim** da lista do campo (o nome genérico continua ganhando quando existe na
planilha), e `detectar_colunas` ganhou o parâmetro `extras`, que
[importar_base_referencial.py](../backend/moduloorcamento/management/commands/importar_base_referencial.py)
passa a partir do tipo de arquivo. A analítica segue com o `ALIASES` puro.

Com isso o pacote oficial entra **sem `--colunas`**: 4.811 insumos, 7.737 composições e 40.193 linhas
analíticas em 8s, com `0 filhos novos` na analítica — todo código citado já existia nos outros dois
arquivos, que é o sinal de que os três foram lidos de forma coerente. Conferido contra o XLSX de
origem em amostra de 5 preços (exatos), a composição 97141 reproduzindo os 5 componentes com seus
coeficientes, e nenhum item sem unidade, com custo zero ou composição sem analítica. Suíte
`moduloorcamento` **88/88**.

---
### D97 — a prancha difícil não tinha localizador, e o passo do zoom acelerava sozinho · ✅ corrigido 16/08/2026

Pedido do dono (16/08/2026): *"seria bom destacar onde estão os itens"* e *"se eu coloco um pouco
mais de zoom ele já aproxima muito e não tem como eu achar nada porque levaria muito tempo
arrastando"*. Ao detalhar, ele corrigiu a nossa leitura do sintoma: **"tarja preta" era só o fundo
escuro da tela**, não um defeito de renderização — *"quando abro o desenho eu vejo tudo que está nos
desenhos, mas em desenhos separados; eu quero ver o desenho completo"*.

Isso mudou o remédio. A separação por folha (PRA.1c) está certa e fica: um arquivo com duas
poligonais a 8,5 milhões de unidades uma da outra numa folha só produz uma página de 469 m × 8,5 km,
que nenhum navegador rasteriza. O que faltava não era desfazê-la — era a **vista de cima**.

**Três coisas, e as três eram pedido literal:**

1. **O minimapa localizador** ([Minimapa.tsx](../frontend/src/modules/prancheta/visualizador/Minimapa.tsx)):
   a planta inteira em miniatura, com cada desenho no lugar em que ele está *no terreno*, clicável
   para enquadrar. O dado já existia e não foi inventado — `DesenhoProjeto.caixa` é a envolvente em
   unidades de desenho, a mesma que o agrupador usa para cortar as folhas. Junto vai uma fileira de
   chips, porque uma poligonal de 40 m ao lado de um loteamento de 8 km vira um pixel no mapa, e um
   alvo de um pixel não é alvo. Abre sozinho com mais de uma folha (esconder a resposta atrás de um
   botão que a pessoa não sabe que existe seria não a ter dado) e se desliga no cabeçalho.
2. **`Ctrl` + roda = passo fino** de 3%, sem aceleração
   ([Vista2D.tsx](../frontend/src/modules/prancheta/visualizador/Vista2D.tsx)). **A causa estava
   medida:** `JANELA_RAPIDA` são 120 ms e um mouse girado com naturalidade dispara eventos a cada
   50–80 ms — ou seja, o giro normal quase nunca pegava o passo de 1,12; pegava o de até 1,40, e três
   cliques viravam 2,7×. Remover a aceleração trocaria um defeito por outro (atravessar os ~7.865%
   que ler uma poligonal exige, de 12% em 12%, é inviável), então ela ficou e ganhou um modificador:
   `Ctrl` para procurar, roda solta para viajar — os dois gestos que o CAD sempre teve, agora
   separados.
3. **O snap desligável**, pedido no mesmo relato. O selo de estado virou interruptor (`aria-pressed`,
   alvo de 32 px) e a mira some junto ao desligar — deixá-la na tela diria que o próximo clique ainda
   vai grudar nela. Ligado continua sendo o padrão, porque é a mira que faz a cota valer; desligado
   serve ao caso em que o ponto não tem vértice — o meio de um vão, um ponto no terreno.

### D101 — o teto do arquivo grande era nosso, não do LibreDWG · ✅ corrigido 16/08/2026

**O que estava escrito, e estava errado.** A planta e o laudo da frota diziam que o maior DWG do
acervo (64,9 MB) *"falha no `dwg2dxf`, antes de existir folha para gravar"* — lido por qualquer um
como limite do decodificador, o mesmo `checksum CRC mismatch` que originou o `DWG_MB_MOTOR_LIVRE` da
§5.1 do `planos.py`. A conclusão que se tirava disso era que não havia o que fazer.

**A medição.** Rodando o `dwg2dxf` **sem o nosso orçamento de memória**: sai `0` e produz um DXF de
**531,8 MB** (8,2× o DWG). O LibreDWG converte o arquivo sem dificuldade. Quem o mata somos nós — os
2.048 MB do `PRANCHETA_SUBPROCESSO_MEMORIA_MB`, em 9,7 s, com `recurso_excedido`. Não é limite de
motor: é teto nosso, e teto nosso é knob comercial.

**A correção.** A memória virou degrau de plano (`planos.py` §5.4d): dois mapas —
`PRANCHETA_CONVERSAO_MEMORIA_MB_POR_PLANO` e `PRANCHETA_SUBPROCESSO_MEMORIA_MB_POR_PLANO` — que o
`pipeline` resolve a partir do plano já congelado na linha da frota (D98) e aplica em
`orcamento_de_conversao(memoria_mb=…)` e num `ContextVar` novo (`motores/base.py`) que leva o teto do
subprocesso aos quatro pontos onde `dwg.py` o consulta. `ContextVar` e não global porque o worker
pode rodar em threads e um global vazaria o teto de um tenant para o do vizinho.

**Por que o eixo é memória e não MB de arquivo.** É a conclusão da PRA.1b por outro caminho: nenhum
corte em MB ordena o custo, porque o DWG guarda hachura como *declaração* (área ÷ espaçamento),
grandeza que o tamanho do arquivo não limita. O que o plano compra é quanta RAM a plataforma gasta.

**O que ficou aberto, e está em [pendencias.md](pendencias.md):** o degrau de cima **não cabe na
máquina de hoje**. A escada é `1.536 (explica) < 2.048 (Celery mata) < 3.072 (contêiner mata)`, e
servir o 64,9 MB exige subir os dois últimos, que são dimensionamento e não moram no `planos.py`.

**A primeira versão deste mapa errou justamente aí, e a medição pegou.** Ela dava 2.800 MB de
subprocesso ao `empresarial`; rodando o arquivo de 64,9 MB nos dois degraus: com 2.048 MB sai
`RecursoExcedido` em 8,9 s — erro legível —, com 2.800 MB o processo morre com **exit 137 (SIGKILL),
sem exceção e sem rastro**. Os 3.072 MB são do contêiner inteiro e o Python pai já reserva ~1.150 MB
de VA, então o subprocesso nunca teve 3 GB para si. O mapa foi achatado no topo em 2.048 e
`nucleo/test_tetos_no_payment.EscadaDeMemoriaPorPlanoTests` (4 testes) passa a falhar se alguém
prometer mais RAM do que a máquina entrega — trocar `recurso_excedido` legível por worker morto sem
rastro é o D71/D76 ao contrário.

---
### D102 — o arquivo pesado cedia a vez para uma fila vazia · ✅ corrigido 16/08/2026

**O defeito, achado pela medição e não por relato.** A retomada da PRA.11 cedia a vez ao vencer o
turno (80% de 300 s = 240 s) **sem perguntar se havia alguém para receber a cadeira**. Com a fila
vazia, o arquivo se interrompia, voltava para o fim de uma fila em que era o único, sentava de novo
na mesma cadeira e **repetia o custo fixo** — medido em 56% do relógio (laudo §8.2). Desperdício
puro: pagava-se 1,86× a mais para não dar lugar a ninguém.

Decisão do dono (16/08/2026): *"não precisa ceder a cada arquivo que chegar, pode ser por tempo, mas
isso se tiverem arquivos na fila; se não tiver não precisa ir para o final da fila"*.

**A correção, em três peças:**

1. `nucleo/frota.ha_espera(chave)` — existe alguém **aguardando** nesta frota, além de quem pergunta?
   Quem já está rodando não conta (ocupa outra cadeira, não espera por esta), e a própria chave sai
   da conta: uma tarefa recolocada reaparece como aguardando enquanto a passada anterior termina, e
   sem a exclusão ela cederia a vez para si mesma, para sempre.
2. `ceder` entrou no contrato de `Adaptador.converter` — pergunta de zero argumentos consultada **só
   depois** de o prazo vencer. `None` cede sempre, que preserva quem chama sem fila. `MotorDxf` a
   consulta entre folhas, então o atraso máximo de quem chega é **uma folha**, não uma passada.
3. `_relogio_da_passada` — a peça que faltava para isso não ser pior que o defeito. Se a passada
   passa do turno de propósito, o teto duro de 300 s a mataria em pleno trabalho útil, destruindo o
   progresso. O teto duro passa a ser **o que resta do orçamento acumulado do arquivo**
   (`PRANCHETA_CONVERSAO_TOTAL_SEGUNDOS` menos o gasto). Nada fica sem freio: o arquivo tem o mesmo
   orçamento total de antes — o que muda é poder gastá-lo de uma vez quando isso não atrapalha
   ninguém.

Coberto por `nucleo/test_frota.CederSoComFilaTests` (4 testes). Suíte do backend: **1290, só as 4
falhas pré-existentes do D50**.

---
### D98 — o trabalho pesado tinha freio, e agora tem porteiro · ✅ corrigido 16/08/2026

O `worker-conversao` protegia a máquina (`--concurrency 1`, `mem_limit`, `orcamento_de_conversao`) e
não tinha **admissão**: quem chegava primeiro ocupava a frota, quem chegava depois esperava sem
ordem, sem posição e sem garantia. Um tenant free podia segurar a única vaga enquanto um premium
esperava, e um premium podia segurar todas enquanto o free esperava indefinidamente.

**O endereço reservado virou código:** [`nucleo/frota.py`](../backend/nucleo/frota.py) e o modelo
`TarefaNaFila`. Fica no `nucleo` e não no `moduloprancheta` porque a Prancheta é a **primeira
cliente, não a dona** — importação de acervo, exportação grande e ortofoto do Maps entram pelo campo
`frota` sem uma segunda fila paralela.

**Tabela no Postgres e não a prioridade do Redis** *(decisão do dono, 16/08/2026)*. O broker sabe
entregar a próxima mensagem; não sabe dizer *quem está na frente*, não reserva fração de cadeiras nem
tem onde um job recolocado voltar. Quem enfileira chama `frota.enfileirar()` em vez de `.delay()` e
recebe a posição; o despachante escolhe pela política e só então publica.

**As três decisões do dono, aplicadas:**

- **Fila única com prioridade e cadeira marcada em FRAÇÃO da frota**, nunca fila separada por plano e
  nunca número absoluto — *"você não pode deixar 40 cadeiras premium e quando o programa lançar haver
  100.000.000 de pessoas na fila"*. A reserva vale nos dois sentidos: parte das cadeiras não recebe
  free, e parte não recebe premium. É o que prioridade pura não faz — ela alija o free
  indefinidamente.
- **O administrador passa na frente só da própria empresa.** A primeira implementação dava ao job
  urgente a `criada_em` do primeiro da empresa menos um instante, e **isso ultrapassava terceiros
  entremeados**: com a fila `[acme-1, beta-1, acme-2]`, subir a `acme-2` empurrava a `beta-1` de
  segunda para terceira — um cliente que não fez nada atrasava. O teste pegou (`4 != 3`). Hoje é uma
  **permutação dos lugares que a empresa já ocupa**: os lugares são os mesmos, muda quem está em
  cada um, e ninguém de fora se move.
- **Os tetos são do dono**: frações, penalidade da volta e degrau de envelhecimento nascem em
  [`payment/planos.py`](../payment/planos.py) §5.4c. ⚠️ **Os números são provisórios e estão
  declarados como tal** — *"isso tem que ser feito um estudo para determinar"*. O que o estudo
  precisa medir está escrito lá: distribuição de plano na base, tempo mediano e de cauda por plano
  (que converte "cadeira" em minutos de espera, a única unidade que o cliente sente) e o tamanho real
  da frota. O gancho de add-on também foi pedido junto e existe (`pacote_fila_prioritaria` →
  `cadeiras_frota`), com preço zerado pela mesma razão: precificar uma cadeira antes de medir o COGS
  por conversão seria arbitrar margem sobre custo desconhecido.

**Dois defeitos achados por teste, e o segundo é sutil:** a classe de cadeira era deduzida da **faixa
de prioridade**, e como o envelhecimento mexe na prioridade, um job free com voltas suficientes
passava a ser lido como `comum` e sentava em cadeira que não era dele — a reserva vazando justamente
para quem mais espera. Hoje a classe sai do **plano**, que é imutável na linha.

**A rede que o desenho exige:** o despachante não é um processo em laço — ele roda ao enfileirar e ao
liberar cadeira. Isso basta enquanto todo job avisa que terminou (o `DLQTask` garante o aviso até na
falha), e não cobre a morte violenta: OOM do cgroup, container derrubado. Para isso existe
`liberar_orfas`, no beat a cada 5 min. Sem ela, cada morte dessas reduziria a frota em uma vaga **para
sempre**, e o sintoma seria uma fila cada vez mais lenta sem nada nos logs. A órfã volta pelo caminho
da recolocação, e não ao lugar de origem: um job que mata o worker toda vez não pode monopolizar a
frota morrendo em série.

### PRA.11 / item 23 — o arquivo de 40 MB passou a terminar · ✅ 16/08/2026

*"Se esse arquivo não terminar em tantos segundos, volta pro final da fila e continua assim até
terminar, se o processo puder ser pausado."* O registro do D98 dizia que isso era **impossível**, e o
motivo era técnico e correto: sem checkpoint, devolver à fila um trabalho que recomeçaria do zero
gastaria mais CPU total do que deixá-lo terminar.

**O checkpoint é a folha** *(decisão do dono, 16/08/2026)*. `MotorDxf` emitia todas as folhas numa
compreensão de lista; passou a emiti-las num laço que confere o relógio **entre** folhas e devolve um
marcador `Retomada` quando o turno acaba. O pipeline grava o que veio — as folhas prontas **já
abrem** — e devolve o arquivo ao fim da fila.

**O que a retomada não evita, e está declarado:** a gravação da geometria (`Recorder`) roda inteira em
toda passada — é ela que expande o DWG em memória e não há como serializá-la mais barato que refazê-la.
O que se economiza é a emissão das folhas, que num arquivo de dezenas de desenhos é a maior parte do
relógio. Num arquivo de folha única não economiza nada, e por isso o pipeline nem tenta: `retomavel =
False` em PDF, imagem e IFC mantém o comportamento de sempre — estoura, para tudo e explica.

**Volta pro fim, mas com prioridade crescente** *(decisão do dono)* — e são **duas** coisas, o que a
primeira versão não tinha. Só com o degrau, a volta nº 1 já punha o arquivo à frente de todo mundo do
mesmo plano, que é o oposto de "volta pro fim". Hoje há penalidade (o fim da fila) que decai a cada
volta (o crescente): cede a vez nas dez primeiras e começa a ultrapassar na décima primeira. Some de
vista sem nunca sumir.

**A desistência é por tempo ACUMULADO, não por número de voltas** *(decisão do dono)*: contar voltas
mediria a nossa política, não o custo — um arquivo que faz trinta folhas por passada e outro que faz
uma gastariam o mesmo "orçamento" tendo custado dez vezes diferente. Estourando
`PRANCHETA_CONVERSAO_TOTAL_SEGUNDOS`, a conversão encerra com `recurso_excedido` **preservando as
folhas convertidas**: a prancha abre pelo que deu e a frase diz quantas faltaram.

**Um defeito destrutivo achado por teste:** `_remover_orfas` apaga o que a conversão não produziu — e
numa passada parcial "não produziu ainda" e "não produz mais" são indistinguíveis. A passada final
apagava as folhas de todas as anteriores, com as derivadas por cascata: um arquivo de cinco folhas
terminava com uma. Hoje o critério é a maior `ordem` emitida, e não a lista da última passada.

**Na tela**, a espera ganhou forma: *"3º da fila"*, *"12 de 40 folhas prontas"*, *"2ª passada"*.
"Convertendo" por meia hora sem mais nada é indistinguível de travado — era essa a queixa que abriu a
fila.

**Validação das três fatias:** `moduloprancheta` 414/414, `nucleo` verde (18 testes novos de frota),
backend inteiro **1277** com só os 4 conhecidos do [D50](pendencias.md); `tsc -b --force` e `eslint`
limpos.

---
### D100 — Duas portas de upload no acervo, e uma janela a mais para chegar numa delas · ✅ corrigido 16/08/2026

Achado do dono no uso, 16/08/2026: *"existem dois modos de subir arquivo em prancheta sendo que
escolher arquivos (botão amarelo) é inútil, já que tem enviar pasta e dentro tem escolher pasta e
escolher arquivos"* — e, no mesmo relato, *"todas as informações ficam na mesma janela ao invés de
abrir uma janela e depois abrir outra, diminui 1 clique"*.

**A premissa da dúvida do dono estava quase certa, e a metade errada muda o remédio.** Ele supôs que
o botão avulso furava a [R17](modulos/funcoesimpexp.md) (*"a própria documentação diz que o único
meio de subir e baixar um arquivo no sistema é por meio de funcaoimpexp"*). Não furava: o
`documentos/enviar/` delegava ao `RevisaoDocumentoSerializer`, que chama `porta.admitir` →
`entrada.admitir`. Os dois caminhos sempre passaram pela porta única. A duplicação era de
**interface** — e é por isso que o conserto é apagar uma tela, não reescrever uma porta.

**O que cada caminho fazia, medido e não suposto.** O wizard sempre teve os dois cartões (*escolher
pasta* e *escolher arquivos soltos*) e seu palpite lê disciplina do caminho **e** do nome — que era
todo o argumento do avulso. O avulso fazia **a menos**: seu `<input>` não tinha `accept`, então um
`.docx` de 300 MB subia inteiro para tomar 400 na porta, enquanto o wizard peneira formato e peso
antes de enviar. E fazia **a mais** só uma coisa: gravar direto, sem conferência — que o dono decidiu
não preservar (*"sempre confere"*).

**Saíram**: `POST documentos/enviar/`, `POST disciplinas/adivinhar/` (existia só para aquela tela
pré-marcar chips), o hook `useEnviarPrancha`, as funções `enviarPrancha`/`adivinharDisciplinas` do
`api.ts` e o `_rotulo_livre` do lote. Nenhum ficou como no-op: função que ninguém chama é mais difícil
de achar que um erro de compilação — a mesma lição que o [D70](#) deixou ao apagar a `mediaUrl` em vez
de a esvaziar. **Ficou** o `documentos/<id>/atualizar/`: ali o documento já está escolhido, é o que a
pessoa tem aberto na tela, e não há acervo a conferir.

**A janela intermediária sumiu junto.** "Enviar projetos" abria um modal cuja única função útil era
hospedar o botão que abria o modal do wizard. Agora o botão **é** o do wizard, e a regra que a janela
do meio existia para contar — o nome do arquivo virando prancha e revisão — desce pelo slot `ajuda`,
uma prop nova do `<WizardArquivos>` renderizada acima dos cartões. O wizard sabe dizer o que o destino
recebe e até quantos MB, porque isso está declarado no `Recurso`; o que o arquivo **vira** ao entrar
só o módulo sabe.

**Duas regressões que a remoção criaria, e que só apareceram ao ler o outro lado.** Nenhuma das duas
era defeito enquanto havia duas portas — cada uma servia a sua:

1. **O palpite do lote cortava as disciplinas do nome em `[0]`.** A coluna é `multipla` desde a
   PRA.9c, mas `ARQ-ELE-PLB-001.dwg` chegava à conferência só como Arquitetura; o avulso pré-marcava
   as duas. Manter o corte teria feito do caminho único uma regressão para o arquivo que declara mais
   de uma disciplina. Agora `dados_do_arquivo` devolve a lista inteira, e `aplicar_linha` parte a
   vírgula **antes** do `get_or_create` — o valor multi ia para o `defaults`, e
   `"arquitetura,eletrica"` não é `choices` de ninguém (o `create()` não valida; sobrevivia só porque
   o `definir_disciplinas` logo abaixo reescrevia o campo).
2. **O rótulo de revisão do lote tapava o primeiro buraco.** `_rotulo_livre` existia para a colisão
   `PLANTA.dwg` × `PLANTA (cópia).dwg` do mesmo acervo histórico, e era inofensivo enquanto o destino
   do lote nascia vazio. Com uma porta só, ele passou a receber também "a entrega de hoje de uma
   prancha viva": documento com `R04` em campo, chega `HID-001.pdf` sem marca, o `R00` está livre — e
   a entrega entraria **atrás** da que o canteiro executa. O `proximo_rotulo` resolve a colisão do
   lote igual e continua do maior, então ficou ele nos dois casos. Junto, `dados_do_arquivo` passou a
   usar `revisao_declarada`: a célula *Revisão* vem **vazia** quando o nome não declara, em vez de um
   `R00` inventado que não vai ser o gravado.

**Uma diferença de comportamento assumida:** o avulso reclassificava o documento que ainda estava em
*Outra* a cada envio; o lote nunca fez isso, porque uma remessa de trezentos arquivos reclassificando
o acervo existente desfaria decisão individual em massa. Vale a regra do lote, e reclassificar segue
possível pelo ato explícito, na própria prancha.

**Validação:** `moduloprancheta` **407/407**; backend inteiro **1258**, com só os 4 conhecidos do
[D50](pendencias.md); `tsc -b --force` e `eslint` limpos no frontend. Os testes do avulso não foram
apagados em silêncio — viraram os do lote (helper `_pelo_lote` na base), mais duas regressões novas:
a rota que não responde mais e o rótulo que não volta ao início.

---
### D95 — Bancada de medição e testes E2E moravam em `infra/` · ✅ corrigido 16/08/2026

`infra/` é **como o sistema sobe** — compose, nginx, init do Postgres, chaves, proxies. Tinha virado
gaveta: `infra/medicao/` (bancada que roda o motor sobre uma pasta de DWGs e não sobe nada) e 23
scripts de teste E2E dentro de `infra/gateway/`, misturados com os três `nginx*.conf` que são
infraestrutura de verdade. Relatado pelo dono como *"a pasta infra tá enchendo de lixo"*, e o
diagnóstico confirmou: nada ali era descartável — estava tudo no lugar errado.

`infra/medicao/` → [`ferramentas/medicao/`](../ferramentas/README.md), que é a pasta que já existe
para bancada e cuja regra é ter **endereço** (o módulo dono do problema); o dela é a Prancheta.
Os testes E2E → [`testes/e2e/`](../testes/e2e/README.md), com README separando teste de apoio
(`amostras_pra8.py`, `d11_mailpit_helper.py`, `carregar_acervo_dwg.py` não têm asserção). Em
`infra/gateway/` sobraram os `nginx*.conf` e o `docker-compose.gateway.yml`. As 37 referências de
documento e script foram reescritas junto — mover sem elas teria trocado gaveta por elo quebrado.

---
### D94 — A busca exigia o acento exato, no sistema inteiro · ✅ corrigido 16/08/2026

`fundacao` não achava `Fundação`; `concreto` não achava `Concreto Armado` se a pessoa escrevesse
`ç`. As duas pontas comparavam texto cru: o backend com `icontains` puro em ~50 `search_fields` de
11 apps, e os filtros de tela com `toLowerCase()`. Quem digita rápido digita sem acento, e no celular
do canteiro ninguém caça o `ç` — a conclusão de quem procura é que **o dado não existe**, que é a
pior forma de falha porque não parece falha.

Decisão do dono: *"quero que todo o software seja acessível, ninguém tem que ficar digitando
exatamente a palavra para conseguir achar o que quer"* — logo, comportamento padrão, não recurso de
um módulo. [`nucleo/busca.py`](../backend/nucleo/busca.py) registra `unaccent` como transform de
`CharField`/`TextField` e traz `BuscaSemAcento`, que interpõe a normalização **só no comparador
livre** (`=`, `^`, `@` e `$` do DRF seguem intactos, cada um pelo seu motivo, documentado lá). O SQL
resultante normaliza os dois lados: `UPPER(UNACCENT(coluna)) LIKE UPPER(UNACCENT(termo))`. Na tela,
[`utils/texto.ts`](../frontend/src/utils/texto.ts) faz o mesmo por `NFD` — os dois lados precisam da
mesma régua, senão a lista pisca com o resultado certo e some.

A extensão nasce no `template1` pelo superuser ([init](../infra/postgres/init/01-init-databases.sh)),
não numa migration, pelo mesmo motivo do PostGIS (MAP.0): `CREATE EXTENSION unaccent` exige SUPERUSER
e `erp_app` é role comum de propósito. Custo declarado: a busca deixa de usar o índice B-tree da
coluna; o conserto, quando doer, é índice funcional por tabela quente — não desligar a normalização.

---
### D93 — O `svg_do_motor` inteiro estava desligado · ✅ corrigido 16/08/2026

O dono pediu para conferir se *"a função de deslocamento"* da Prancheta estava certa, testando vários
DWG. Ela estava certa; o que estava errado é que **nada a chamava**. O
[`motores/svg_do_motor.py`](../backend/moduloprancheta/motores/svg_do_motor.py) — os três consertos da
saída crua do `dwg2SVG` (texto em código de escape, símbolo com origem deslocada, desenhos distantes
na mesma folha) — não tinha um único importador no repositório, e o `_svg_direto` devolvia o SVG do
LibreDWG como veio.

Medido sobre 18 DWGs do acervo, a fração de geometria que cai dentro do `viewBox` que o próprio
arquivo declara, sem e com o conserto de origem:

| Grupo | Antes | Depois |
|---|---|---|
| Família AutoCAD Electrical (5 arquivos, blocos por referência) | 50–61 % | 99–100 % |
| Arquivos sem `<use>` nenhum (7) | inalterada | inalterada |
| Arquivos já corretos crus (2) | inalterada | inalterada |

Ou seja: **onde há bloco por referência — que é exatamente por que este degrau existe — metade do
desenho estava fora da folha.** Onde não há, a correção é inerte por construção, porque a decisão de
deslocar é por símbolo (`_caixa_do_simbolo`) e não em bloco. O `_svg_direto` passou a chamar
`corrigir_texto` + `folhas` e a devolver `partes`, como o caminho do DXF; a separação é protegida por
`try` e declara `separacao_falhou` no detalhe, porque neste degrau a alternativa a uma folha imperfeita
não é uma folha melhor — é `recurso_excedido`, nenhuma prancha.

---
### D92 — O fundo da prancha cobria só um terço da folha no navegador · ✅ corrigido 16/08/2026

Relatado como *"alguns desenhos o fundo cinza está só em parte do desenho, e isso ocorreu depois de
colocar todos os desenhos com precisão de 5 casas decimais"*. As duas metades da frase estavam certas,
e a segunda é que explicou a primeira.

O `SVGBackend` emite o papel como um `<rect>` com os lados em unidade de `viewBox`. Até a decisão das
cinco casas (15/08/2026) a grade era o padrão do `ezdxf`, 10⁶. Dimensioná-la pelo desenho levou a
`001` a **8,6×10⁷** — e o Chromium **para de pintar** o retângulo em 2²⁵ (33.554.432). Medido em
16/08/2026 num `<img>` de 1250 px: o fundo cobria 486 px dos 1250, e `86.186.100 × 486/1250 ≈ 3,35×10⁷`
fecha com 2²⁵ sem sobra. Um `<rect>` sozinho, num SVG com nada além dele, reproduz o corte — é o
rasterizador de caminho do Skia, não o nosso desenho.

**O traço não sofre**, porque é feito de segmentos curtos que não esbarram no teto: a prancha "abre",
a 60 fps, com o desenho inteiro — só que virando linha clara sobre fundo claro em dois terços da área.
É a família de defeito do **D46** (neste mesmo arquivo), em que a folha parece pronta e esconde o que
importa. E o
`librsvg` pinta a folha inteira nos dois casos, que é por que miniatura e PDF nunca denunciaram nada:
**o defeito só existia no navegador**, que é justamente onde a prancha é lida.

Conserto em `dxf.py::_fundo_em_porcentagem`: o fundo sai em `width="100%" height="100%"`, que cobre a
mesma área e o navegador resolve sem construir um caminho de 8,6×10⁷ unidades. A troca é cirúrgica —
só reescreve o `<rect>` cujos lados batem **dígito a dígito** com os do `viewBox`, senão seria
geometria do projetista. **A grade não foi tocada**: é ela que carrega a quinta casa, e o fundo não
precisa de precisão nenhuma. Conferido nos dois rasterizadores (Chromium passa a cobrir a folha
inteira; `librsvg` idêntico) e preso por `FundoQueCobreAFolhaTests`.

---
### D96 — A conferência de arquivos não rolava, e era fina demais para ler · ✅ corrigido 16/08/2026

Relatado como *"quando abro a caixa de seleção de disciplina fica difícil mover a barra de rolagem da
tela e da caixa"*, e depois: *"a tela também é muito fina, todas as informações tomam a tela toda
deixando só uma fileira para o mais importante"*.

**Três rodadas, e as duas primeiras erraram o alvo — o que é a parte instrutiva deste achado.**

**Rodada 1 — a tela errada.** `overscroll-behavior: contain` foi aplicado às listas da Prancheta
([Disciplinas.tsx](../frontend/src/modules/prancheta/pages/Disciplinas.tsx),
[EnviarPranchas.tsx](../frontend/src/modules/prancheta/pages/EnviarPranchas.tsx)). O `contain` estava
certo e continua no lugar — mas a tela do relato é o **wizard compartilhado**
([WizardArquivos.tsx](../frontend/src/components/malha/impexp/WizardArquivos.tsx)), que serve todo
módulo com import/export. Consertar a tela vizinha não move a que se relatou.

**Rodada 2 — o véu, e um conserto que criou outro defeito.** O painel de disciplina se fechava por um
véu `position: fixed; inset: 0` invisível. Enquanto aberto, ele é o alvo do ponteiro em **toda** a
tela; sendo fixo, o encadeamento de rolagem dele vai para a viewport e não para a tabela que está
atrás no DOM. Conferido no Chrome: com o véu, `elementFromPoint` no meio da tabela devolve o próprio
véu; sem ele, devolve o `<td>`. O véu passou a fechar na roda — e isso **quebrou o pedido original**:
quem girava a roda para ler o fundo perdia a escolha que tinha aberto.

**Rodada 3 — a causa real: o painel estava dentro do container que rola.** Aberto `position:
absolute` na célula, ele era filho da tabela, e isso custava três coisas de uma vez:

| Sintoma | Causa |
|---|---|
| "o lateral só fica ativo quando disciplina tá aberto" | Os 240 px do painel entravam no `scrollHeight` da tabela — barra de rolagem que o conteúdo não pediu |
| "ao invés de mover o lateral está movendo o inferior" | Como a barra fantasma aparecia, a regra "sem vertical → roda vai para o lado" invertia conforme o painel estivesse aberto |
| Painel cortado na linha de baixo | `absolute` dentro de ancestral com `overflow` é clipado na borda dele |

Medido nos três estados: fechado `barraVertical=false`; aberto-absolute `true`; aberto-portal
`false`. O painel foi para um **portal no `body`** com coordenada `fixed` medida do gatilho, o véu foi
**removido** e o fechar-fora virou `mousedown` no documento — sem fechar na roda. É o mesmo desenho do
seletor da Prancheta, que já se comportava bem; agora os dois são iguais. As regras gerais estão na
[§2.1 do frontend.md](frontend.md).

**A segunda metade do relato — "muito fina" — tinha outra causa, e não era só largura.** O modal era
960 px para 11 colunas, mas o que espremia mesmo era o **hash**: `max-width` num `<td>` de tabela
`auto` é conselho, não regra, então a coluna do SHA-256 abria ~440 px e empurrava Código, Revisão e
Observação para fora da tela. O corte foi para um filho de bloco dentro da célula (110 px no hash,
valor inteiro no `title`), o modal passou a usar a janela com teto de 1760 px, e as 11 colunas
passaram a caber em 1600 px — conferido no Chrome, antes e depois.

Na altura, o cabeçalho de três fileiras virou uma (as pastilhas repetiam o número que os filtros já
dizem) e o `maxHeight: 400` fixo da lista virou `flex: 1` sob o novo modo `alto` do `Modal`
([§2.2](frontend.md)). E como roda de mouse não rola na horizontal, a roda vertical passa a ser
traduzida em horizontal **quando não há nada para rolar na vertical** — o caso de uma remessa de um
arquivo só.

---
### D90 — A mira do snap caía fora do traço, diferente em cada prancha · ✅ corrigido 15/08/2026

**Relatado pelo dono três vezes, e três consertos falharam antes deste.** O sintoma: aproximando o
cursor do vértice de uma linha, a mira acendia num lugar que não era o vértice — a ~81× de zoom, a
borda de baixo do quadrado do snap alinhava com a linha que ele deveria medir. A pista que destravou
o caso veio do relator na quarta vez: **o erro é diferente em cada prancha**. Erro que muda de
prancha para prancha não é constante de código, é geometria de página.

Eram **dois defeitos independentes**, e é por isso que consertar um de cada vez nunca fechava.

#### Primeiro: a página deduzida não é a página emitida

`snap.py::normalizador` recalculava a folha como `largura_do_desenho + 2·MARGEM_MM`. Parece a conta
do `ezdxf` e não é — ele faz mais três coisas depois: arredonda a página para **0,1 mm**
(`Page.width_in_mm`), reescala o conteúdo para caber nela (`fit_page`) e **centraliza a sobra** dentro
das margens (`MIDDLE_CENTER`). Sobra um erro de escala da ordem de `0,05 mm / largura_da_folha`, que
some no enquadramento, cresce com o zoom e depende do quanto *aquela* folha foi arredondada:

| Prancha | Folha emitida | Desvio a 81× |
| --- | --- | ---: |
| `001` | 861 × 614 mm (redonda) | **0,04 px** |
| `005` | 859,4 × 612,6 mm | 0,45 px |
| `01_02-DETALHE_DAS_SAPATAS` | 93,5 × 62 mm | 5,17 px |
| `Banco` | 112,7 × 65,5 mm | **8,69 px** |

A `001` é justamente A1 exato, então não arredonda — e era nela que as três tentativas anteriores
mediam. Mediram a única prancha do acervo em que este defeito não aparece.

#### Segundo: emitir o SVG destrói a geometria de quem a emprestou

Este é o grande, e não se vê lendo o nosso código. `Player.replay()` repassa `PathRecord` e
`FilledPathsRecord` **por referência** ao gravador do backend (só `PointsRecord` de 1–2 pontos e
`SolidLinesRecord` são reconstruídos), e o `get_string()` transforma esses registros *in place* para
o espaço do `viewBox`. Como o índice era tirado do player de origem **depois** da emissão, ele lia um
espaço misto — a bbox do `recortado` denuncia: `2,97 … 892.968`.

O efeito: reta e polilinha-de-duas-pontas sobreviviam; **todo arco, círculo, polilinha, hachura e
texto caía inteiro no filtro de "fora da folha"**, sem uma linha de log. Na
`01_02-DETALHE_DAS_SAPATAS` eram 1.699 dos 3.214 registros. Na tela isso não aparecia como mira
ausente e sim como **mira mentirosa**: sem os vértices da curva, ela grudava no ponto de reta mais
próximo, que é outro lugar.

**E era também o "fantasma" que a medição de 15/08/2026 tinha visto.** Os 516.587 pontos fora da
folha na `001`, com X indo a 1126, não eram geometria inventada: `1126 ≈ 10⁶/861` é a folha inteira
em unidade de `viewBox` dividida pela largura da página em mm. Era o desenho de verdade, no espaço
errado. O filtro `descartar_fora` criado então não matou fantasma nenhum — escondeu o defeito melhor,
e é o que fez a `001` cair de 517.214 para 627 pontos e **parecer** consertada.

#### O conserto

Um só, e ele mata os dois: **o índice é tirado do gravador do próprio `SVGBackend`, depois de o
arquivo sair.** Ali a geometria está inteira e toda no espaço do `viewBox` — são literalmente os
números escritos nos `<path>` —, e normalizar vira uma divisão pela largura do `viewBox` lida do
arquivo. Nenhuma página é recalculada em lugar nenhum, que é a mesma política que a régua da escala
(`escala_do_desenho`) já seguia: quem arbitra margem e extensão é o `ezdxf`, e a resposta se pergunta
a ele.

Resultado medido com a bancada nova, distância do ponto do sidecar ao traço do SVG, a 81×:

| Prancha | Antes (mediana) | Depois (mediana) | Sobre o traço (< 1 px) |
| --- | ---: | ---: | ---: |
| `001` | 0,04 px | 0,08 px | 96,3% |
| `005` | 0,45 px | 0,09 px | 93,8% |
| `01_02-DETALHE_DAS_SAPATAS` | 5,17 px | 0,09 px | 96,5% |
| `Banco` | 8,69 px | 0,06 px | 96,3% |

De brinde, ficou **mais rápido**: 66,8 s → 17,9 s na `SAPATAS`, 76,5 s → 26,6 s na `Banco`. A causa é
a mesma — curvas em unidade de `viewBox` estavam sendo achatadas com tolerância de milímetro, gerando
milhões de segmentos que a linha seguinte jogava fora.

#### Terceiro: com a curva entrando, o índice virou 95% contorno de letra

Sequela imediata do conserto acima, e o dono ainda via a mira errada. Com a geometria de curva
finalmente chegando, o `FilledPathsRecord` (hachura, sólido **e glifo de texto renderizado em
contorno**) passou a dominar: 61.257 dos 64.264 pontos da `001`. Pior, entrava como `EXTREMIDADE`,
que é a **faixa 0** do desempate — ganhava da parede que a pessoa estava mirando.

Medido no navegador, a 81×, separando as duas origens:

| origem | mediana até o traço | p90 | sobre o traço |
| --- | ---: | ---: | ---: |
| reta, arco, polilinha | 0,0 px | 0,0 px | **95%** |
| preenchimento | 1,0 px | 25 px | **52%** |

Metade dos pontos de preenchimento **não tem tinta embaixo**: o contorno de uma hachura é a fronteira
de um `<pattern>`, não um traço desenhado. **Decisão do dono (15/08/2026): ignorar, como o AutoCAD
faz** — lá o OSNAP não pega em hachura nem em contorno de letra. A `001` caiu de 64.264 para 3.074
pontos e o sidecar de 7,8 MB para 51 KB; de quebra, a pressão sobre o teto do plano (D88/D89) sumiu.

#### Quarto: a tela pintava o desenho torto, e a mira estava certa

Mesmo com tudo acima, o relato continuou: *"a medida pode ser até certa, mas visualmente incomoda"*.
Era literalmente isso, e a frase é que destravou — **coordenada certa e tinta no lugar errado são
duas coisas diferentes**, e todas as bancadas até aqui mediam a primeira.

A armadilha estava no caminho de pintura. As medições desenhavam o SVG num `<canvas>` (`drawImage`),
que re-rasteriza limpo na resolução do destino. A página fazia outra coisa: dispunha o `<img>` no
tamanho natural (3.254 px) e o ampliava por `transform: scale(z)`. **O navegador rasteriza o SVG uma
vez, no tamanho de layout, e estica o bitmap** — a 81× numa janela de trabalho, cada pixel do raster
vira um bloco de 38 px, e o traço aparece deslocado de onde ele matematicamente está.

O cabeçalho do `Vista2D.tsx` afirmava o contrário — *"o zoom continua vetorial porque o browser
rasteriza no fator aplicado"* —, e a afirmação nunca tinha sido medida. Ela era falsa.

| modo de pintar | mediana | p90 | máx | em cima da linha |
| --- | ---: | ---: | ---: | ---: |
| `transform: scale` (como era) | 3,16 px | 16,00 px | **17,89 px** | 45% |
| idem, sem `crisp-edges` | 3,16 px | 16,00 px | 17,89 px | 45% |
| **caixa no tamanho final** | **0,00 px** | **0,00 px** | 1,00 px | **100%** |

O conserto é crescer a **caixa** (`width`/`height` em px de tela) em vez do `scale()`: o vetor é
re-rasterizado na resolução final. `transformOrigin: 0 0` faz os dois caírem no mesmo lugar, então
`paraTela` não mudou e nenhuma marcação já anotada se moveu. E custa o mesmo — 33 ms por passo de
zoom nos dois, porque o Chromium pinta o SVG por tiles e só o que está visível.

O teto `LARGURA_MAXIMA_DE_CAIXA` (3×10⁷ px) também é medido: acima disso o navegador **desiste de
pintar** e a prancha some, que é pior que a mira torta. Passando dele o `scale()` volta a cobrir a
diferença — a ~19.600× o enquadramento, muito acima dos 7.865× que a prancha mais extrema do acervo
exige.

**A lição, e ela vale mais que o conserto:** *"está medido" precisa dizer **o quê**.* Três bancadas
mediram a coordenada e disseram 0,00 px enquanto o defeito estava na tinta. E a janela de medição
importa: o mesmo defeito aparece como 4,5 px numa janela de 320 px e como 17,9 px na janela real de
1.600 px — medir pequeno teria dado "tolerável".

**O que fica de método**, porque custou três tentativas: *descarte em massa não é limpeza, é
sintoma*. Um filtro que corta 99,9% do que recebe está descrevendo um defeito a montante. E as duas
colunas que ninguém confrontou — a bancada `medir_snap.py` (que não emite SVG) media centenas de
milhares de pontos onde a produção gravava 4.286 — eram o achado escrito por extenso desde o começo.

**Bancadas, para a próxima suspeita não recomeçar do zero — e são DUAS perguntas:**

- **a coordenada está certa?** → [conferir_snap.py](../ferramentas/medicao/conferir_snap.py), Python puro,
  segundos, sem navegador. Compara o sidecar com a geometria do SVG emitido;
- **a tinta está lá?** → [aferir_tela_snap.mjs](../ferramentas/medicao/aferir_tela_snap.mjs), Playwright.
  Reproduz o caminho de pintura da página e mede do centro da mira até o pixel desenhado. É a que
  fecha o caso, e a que faltava.

A [verificar_snap.mjs](../ferramentas/medicao/verificar_snap.mjs) segue útil para o `getScreenCTM()`.
Os três testes de regressão de backend estão em `moduloprancheta/tests.py::SnapExtratorTests` e
falham nos dois primeiros defeitos separadamente.

---
### D85 — O acervo importado entrava todo em rascunho, e não havia como publicá-lo · ✅ corrigido 13/08/2026

Achado do dono ao abrir a aba **Pranchas** depois da carga dos 160 DWGs: 141 cartões dizendo
*"sem revisão vigente"* com o arquivo já enviado e **já convertido**. Medido no acervo de
demonstração: 141 documentos, 159 revisões — **todas em rascunho** — e 168 derivadas `pronto`.

**O mecanismo tem duas metades, e a segunda é a que doeu.** A carga em lote (PRA.5b) cria toda
revisão em `rascunho`, e isso está certo: a conferência do lote é alçada de `documento.edit`, e
publicar é de `revisao.publicar` (§9). O que faltava era o **verbo em lote** — `publicar/` só existia
por revisão, então exercer a segunda alçada num acervo histórico custava 141 cliques. Ninguém
publicou, e o módulo passou a ter o diagnóstico numa aba e o remédio em outra.

**A terceira metade era de tela, e é a que explica "duas abas quase independentes".** O backend
sempre soube: `requer_decisao.documentos_sem_revisao_vigente` e `revisoes_em_rascunho` viajam no
mesmo `GET /acervo/` que pinta os cartões, e o tipo `RequerDecisao` já os declarava no frontend.
**Nenhuma tela os renderizava** — a faixa do Início mostrava só as linhas de marcação. A fila de
decisão existia na API e morria na UI, que é como um cockpit vira placar.

**A correção, nas três camadas:** `POST /revisoes/publicar-pendentes/` (mesma alçada, escopo
obrigatório por obra, publica o rótulo maior de cada documento **sem** vigente, nunca troca uma
vigente nem republica superada, e devolve o relatório do que fez); o serializer do documento passa a
expor `pendente` (o rascunho mais recente) para o cartão poder agir sozinho; e o Início ganha a faixa
do acervo pendente com o botão em massa, enquanto cada cartão ganha *Publicar Rxx* para quem tem a
permissão. Quem não a tem continua vendo a faixa, sem botão: o campo precisa saber **por que** a
prancha não abre, senão o defeito vira "o sistema não funciona".

---
### D84 — O relatório de custo desfazia a regra do medidor: não medido virava zero · ✅ corrigido 13/08/2026

Quarta vez que um número de recurso descreveu outra coisa, e a primeira em que o defeito **não**
estava no medidor: o [D82](#d82) deixou `nucleo/consumo.py` correto — `pico_filho_mb = None` quando
o subprocesso viveu menos que o intervalo de amostragem — e o gerador do relatório o desfazia numa
expressão.

**O mecanismo**, em `ferramentas/medicao/relatorio_custo_por_caminho.py`:

```python
pico = max(a["filho"] or 0, a["va"])   # ← o `or 0` é o defeito
```

Aquele `or 0` traduzia *"não medido"* por **zero**, e o zero contaminava dois números publicados:

- **a mediana do acervo.** 76 dos 159 arquivos saíram `n/d`, entraram na lista como zero, e a
  mediana passou a ser decidida por *onde os zeros acabavam* — não pela distribuição de custo.
  Publicou-se **9 MB**; a mediana dos 83 arquivos efetivamente medidos é **32 MB**;
- **a coluna `MB/MB`**, que imprimia `0×` em 76 linhas — exatamente as linhas cuja legenda, duas
  seções acima na mesma página, dizia *"**não é zero.** Zero se leria como 'não custou nada'"*.

Dois defeitos menores da mesma família saíram junto: o pico de quem estourou o orçamento é o do
instante da interrupção (o arquivo pediria mais, e ninguém sabe quanto) e a planta §4.7 já mandava
marcá-lo com `≥` — o gerador não marcava, e o maior número da tabela saía com cara de valor exato.
E a soma "memória não se soma" vale porque o `worker-conversao` roda `--concurrency 1`: é
propriedade do **deploy**, não da medição, e a tabela não dizia isso.

**O mesmo defeito estava no instrumento de dentro do sistema**, em dose menor: o comando
`custo_do_acervo` já filtrava zeros da mediana (por isso os 51 MB dele estavam certos), mas **não**
da série por quarto da fila — que é justamente o controle que prova o D82. Com os não medidos
valendo zero, ela saía `71 · 116 · 1 · 85` MB de média; medida só sobre quem tem pico, é
`183 · 291 · 76 · 161`. O teste passava nos dois casos, mas o "1 MB" do terceiro quarto era o número
de arquivos curtos daquele trecho da fila, não o custo deles.

**A correção** é `pico_do_arquivo()`, que devolve `None` quando nada mediu, e uma mediana calculada
só sobre os medidos. A lição vale além deste arquivo: *a regra "ausência ≠ zero" tem de valer no
agregado também*, porque é no agregado que ela vira frase de produto — o medidor pode estar certo e
o relatório publicar o erro do D82 assim mesmo.

---
### D83 — O catálogo publicava o teto da PLANILHA para formato de arquivo · ✅ corrigido 12/08/2026

Achado no primeiro minuto em que uma tela finalmente leu o campo — o que é a metade interessante do
achado. `/api/impexp/recursos/` anunciava **25 MB** para DWG (o `impexp_max_mb` do plano
`profissional`) enquanto a porta do `prancheta.acervo` aceita **150**; para IFC, 25 contra 300.

**A causa é de camada.** O teto de um formato de arquivo é do **recurso**, não do plano nem do
formato — o mesmo PDF é planilha de preço no Orçamento e prancha de 100 MB na Prancheta, e é por isso
que existe `Recurso.teto_mb_do_formato` (PRA.5a). Só que quem publicava o número era
`Limites.descrever()`, que não conhece recurso nenhum e por isso só sabia devolver o do plano. A
porta usava `_teto_do_formato(recurso, …)`; o catálogo usava outra conta. **Duas contas para a mesma
pergunta, e elas divergiam em 6×.**

**Por que nenhum teste pegou.** O campo estava certo do lado que se testava: o E2E cobre o que a
*porta* aceita, e ela sempre aceitou 150 MB. O que ninguém exercitava era o **anúncio** — porque
nenhuma tela o lia. O `WizardArquivos` da [PRA.5c](roadmap.md) foi o primeiro consumidor, e o efeito
apareceu na primeira passada: a peneira do navegador recusou sozinha, com a frase do plano, o
`J2 - S_PROJETO EXECUTIVO FINAL COM LAZER.dwg` de **64,9 MB** — um arquivo que o servidor teria
aceito. 158 de 159 subiram, e o que faltou foi o mais pesado do corpus.

É o padrão do [D39](pendencias.md) visto de outro ângulo: declaração que ninguém consome fica errada
em silêncio. E é a razão de o conserto **não** ter sido "corrigir o número": foi fazer o catálogo
chamar `teto_do_formato`, **a mesma função que a porta chama**
([views.py](../backend/funcoesimpexp/views.py)). Duas contas parecidas voltariam a divergir.

**A correção:**

- `_teto_do_formato` virou público, `teto_do_formato`, em
  [limites.py](../backend/funcoesimpexp/limites.py);
- `RecursosView` passou a publicar `tetos_mb` por recurso de natureza `arquivo`, com o teto efetivo
  que **aquela** porta aplicará. Efeito colateral que prova o ponto: `prancheta.acervo` declara
  `imagem: 25` (prancha escaneada) e `prancheta.marcacoes`, `imagem: 10` (recorte de tela) — dois
  tetos do mesmo formato, que um catálogo global jamais poderia representar;
- o `WizardArquivos` prefere `tetos_mb[codigo]` e só cai no `limites.formatos[].max_mb` quando o
  backend é antigo demais para trazê-lo.

Na remedição, os **159 de 159** passaram pela peneira.

---
### D82 — O pico do subprocesso media o pai, não o filho · ✅ corrigido 12/08/2026

Terceira vez que um número de recurso mediu outra coisa — depois do [D76](#d76) e do
[D78](#d78) —, e as três levaram a conclusão de produto. Aqui a conclusão falsa era *"o teto de
2.048 MB do subprocesso tem 15% de folga"*.

**O sintoma** foi um platô suspeito: a passada de custo de 12/08 relatou seis arquivos de 1,0 a
9,6 MB custando todos entre **1.751 e 1.760 MB** no `dwg2dxf`. Rodados crus, esses mesmos arquivos
custam de **23 a 230 MB**.

**O mecanismo.** `_pico_dos_filhos_mb()` lia `getrusage(RUSAGE_CHILDREN).ru_maxrss`, que é marca
d'água **acumulada de todos os filhos** que o processo já teve — e, pior, o `fork` dá ao filho as
páginas do pai por *copy-on-write*, e o `ru_maxrss` do filho **conta essas páginas**. O número não
era do subprocesso: era o retrato do pai no instante do `fork`. Provado com controle trivial, e o
controle está no código:

```
subprocess.run(["/bin/true"])  → 14 MB com o pai pequeno
                               → 1.715 MB logo depois de o pai tocar 1,7 GB
```

Isso dispara **sempre** que um subprocesso nasce depois de o `ezdxf` já ter crescido — que é
exatamente o que a escada de degradação faz ao repetir a passada.

**A correção mudou a grandeza, e não o cálculo.** O filho passou a ser medido **por dentro**: o
`VmHWM` do `/proc` dele, amostrado enquanto ele vive. O `exec` cria um `mm` novo, então esse número é
do programa que rodou — sem as páginas herdadas. O controle acima agora responde `n/d`, e não 1.715.

- o mecanismo saiu do comando de bancada e virou fundação, em
  [nucleo/consumo.py](../backend/nucleo/consumo.py), ao lado do
  [orcamento.py](../backend/nucleo/orcamento.py) — teto e medidor são a mesma grandeza vista de dois
  lados, e duas cópias divergiriam;
- **número não medido não vira zero**: `pico_filho_mb` sai `None` com `filho_medido: False`. Zero se
  leria como "não custou nada", que é a mentira mais cara que um medidor pode contar. É a irmã que
  faltava da marca `≥`, que já existia para pico censurado por teto;
- `cpu_s` entrou junto, e a distinção importa: **tempo de CPU acumulado pode ser subtraído** (é
  contador monotônico, a diferença é o gasto da janela); **marca d'água não pode**. Confundir as duas
  é o D82 em uma frase;
- o parcial da medição subiu para **v4** e recusa somar com os v3, pelo mesmo motivo de sempre: são
  duas grandezas diferentes, não duas leituras da mesma.

**E o custo deixou de ser coisa de bancada.** O pipeline de produção passou a gravar o consumo de
**cada conversão** em `DerivadaProjeto.memoria["custo"]`
([pipeline.py](../backend/moduloprancheta/pipeline.py)), inclusive no caminho de erro — que é onde
ele mais serve: `recurso_excedido` sem quanto custou é veredito sem prova. O custo vai só na folha
#1 de um arquivo multifolha, para a soma de um relatório não multiplicar a conta pelo número de
folhas. A leitura é o comando
[`custo_do_acervo`](../backend/moduloprancheta/management/commands/custo_do_acervo.py).

---
### D81 — A prancha não abria, e o estado da conversão mentia sobre o motivo · ✅ corrigido 10/08/2026

**O sintoma**, herdado do [D80](#d80): seis pranchas de DWG do acervo real mostravam *"Ainda não há
visualizador para este formato"*, com backend e frontend aparentemente corretos e um 401 no console.

**As duas hipóteses registradas estavam ambas erradas, e o código já as refutava** — nenhuma exigia
devtools. (a) O retry *cobre* o download de arquivo: o [attachAuth](../frontend/src/api/attachAuth.ts)
refaz a chamada com `instance(original)`, e `original` carrega o `responseType: 'blob'`; o refresh é
single-flight ([session.ts](../frontend/src/api/session.ts)), então visualizador e miniatura em 401
simultâneo não brigam. (b) O 401 nem explicava a tela: se o blob falhasse, `useArquivoBlob` setaria
`erro` e o Visualizador mostraria *"o arquivo não voltou do servidor"* — **outra** mensagem. O ramo
observado só é alcançável com `!carregando && !erro && !objeto`, que é o efeito saindo na primeira
linha por URL nula. O 401 era ruído.

**As duas apurações olhavam obras diferentes.** No banco, `DEMO-01…06` existem **duas vezes**: obra 8
(*Torre B — Alvenaria*, carregada 10/08 23:28, `arquivo=SIM` e **zero derivadas**) e obra 9 (*Galeria
— Pavimento Inferior*, carregada 23:34, 2 derivadas + 1 desenho cada, `pronta`). As derivadas 182/183
citadas na pendência como prova de que "o backend está certo" pertencem à revisão 170 — **obra 9**. O
navegador estava na obra 8. Os dois relatos eram verdadeiros, sobre linhas diferentes.

**O defeito real, e ele é de vocabulário.** O `agendar()`
([pipeline.py](../backend/moduloprancheta/pipeline.py)) **cria** a `DerivadaProjeto` de forma síncrona
antes de enfileirar: motor planejado implica linha existindo, nem que seja `pendente`. Logo, zero
linhas com motor planejado significa o **oposto** do que o `get_conversao` respondia — o motor existe
e ninguém agendou. Dizer `sem_motor` ali manda o dono comprar plano por causa de um job que não rodou,
e é exatamente o erro que a planta §9 existe para evitar (os estados se separam por *quem age*). Os
logs do `sgi-worker-conversao` confirmam: nada às 20:28, 254 linhas às 20:34.

**A correção, em três pontos:**

- **Estado novo `nao_agendada`** em `get_conversao`
  ([serializers.py](../backend/moduloprancheta/serializers.py)): sem derivada nenhuma, pergunta ao
  `planejar()` se há motor no plano de quem lê antes de acusar falta de motor.
- **O contexto passou a viajar** no `get_vigente` — o resumo era montado com
  `RevisaoResumoSerializer(vigente)` **sem `context`**, então nunca alcançava o `request` e não teria
  como consultar o plano do leitor. Bug latente, achado no caminho.
- **A tela ganhou o verbo** — ramo próprio no `SemDesenho` com *"Converter agora"* (o endpoint
  `reprocessar` já existia e resolve sem reenviar o arquivo), pílula `conversão não enfileirada` no
  cartão e relógio em vez de triângulo de defeito: não há nada errado com o arquivo.

**Regressões:** `ConversaoNaoAgendadaTests` (3) — o DWG sem derivada diz `nao_agendada`; o RVT, cujo
`planejar()` é vazio em qualquer plano, **continua** dizendo `sem_motor` (sem esse contrapeso a
correção teria trocado uma mentira por outra); e o resumo alcança o plano do leitor. Suíte do módulo
331/331, `tsc -b` limpo.

**Dado corrigido:** as seis revisões da obra 8 foram agendadas e converteram — `pronta`, 1 folha,
visualizador OK nas seis.

**A regra que fica:** estado derivado da **ausência** de linha é dedução, não leitura. Se outro
caminho pode produzir a mesma ausência, o estado precisa perguntar, não supor.

---
### D80 — O aviso de "sem visualizador" prendia a pessoa na tela · ✅ corrigido 10/08/2026

**O achado**, relatado pelo dono ao abrir a demo: *"essa mensagem trava o clique em qualquer outro
lugar na página, ao invés de ser um popup com opção de fechar"*.

**A causa é de desenho, não de CSS.** O `SemDesenho` do
[Visualizador](../frontend/src/modules/prancheta/visualizador/Visualizador.tsx) tem quatro ramos, e
três deles oferecem verbo: *reprocessar* (conversão falhou), *abrir em Mapas* (o dono do dado é outro
módulo) e o upsell (limite de plano). O quarto — "ainda não há visualizador para este formato" —
oferecia **só a frase**. Como o visualizador ocupa a tela, um aviso sem ação ali não é um aviso: é um
bloqueio com texto explicativo.

Pior: a própria frase promete que *"está no acervo e pode ser baixado"*, e não havia como baixar.

**A correção.** O ramo ganhou a ação que a frase já prometia — `Baixar o arquivo`, por
`baixarParaDisco(revisao.arquivo_url)`, o mesmo caminho autenticado que o resto da tela usa (D70).
`tsc -b` limpo.

**A regra que fica:** todo ramo de estado vazio que ocupa a tela precisa de pelo menos um verbo. Sem
ele, o estado vazio vira armadilha — e é sempre no pior momento, porque estado vazio é onde a pessoa
já está frustrada.

**O que este achado NÃO resolve:** a mensagem estava errada. Isso virou o **D81** (acima), e a
apuração dele desmentiu a leitura feita aqui — a prancha que o navegador mostrava **não** tinha
derivada; a que tinha era outra, de outra obra.

---
### D79 — O último degrau entregava folha destruída como conversão pronta · ✅ corrigido 10/08/2026

**O achado.** Rodando o `dwg2SVG` à mão sobre `planta-amostra.dwg` para dimensionar a PRA.1e, ele
devolve `rc=0`, 4.464 bytes e **onze `<path>`** — e o `viewBox` é
`100000000000000000000 100000000000000000000 -200000000000000000000 -200000000000000000000`, com
**toda** coordenada de **todo** traço em `-1e20,-1e20`. É o sentinela de "extensão não calculada" do
LibreDWG (`EXTMIN`/`EXTMAX` não apurados) publicado como se fosse desenho.

**Por que passava.** O `_svg_direto` (o último degrau da escada, entregue em 10/08) herdou metade da
lição do D52. Ele pergunta *"saiu byte de traço?"* — `ELEMENTOS_DE_TRACO`, que cobre `<path>`,
`<use>`, `<line>` e mais quatro — e essa pergunta pega o arquivo **vazio**. Não pega o arquivo
**destruído**, que é justamente o modo de falha que o D52 ensinou a procurar: onze `<path>` satisfazem
a checagem com folga.

**Por que isso é pior que um erro.** Erro entra na fila do cockpit e alguém age. Folha destruída sai
`PRONTO`, com miniatura e tudo: o canteiro abre a prancha, vê o branco, e conclui que o sistema está
quebrado — sem que apareça uma linha em relatório nenhum. É a mesma família do D39 (o arquivo que
passa o paywall e gera zero derivadas), com o agravante de que aqui o sistema **afirma** que deu certo.

**A correção.** `folha_destruida()` em [motores/dwg.py](../backend/moduloprancheta/motores/dwg.py),
chamada no `_svg_direto` **depois** da checagem de traço. Duas perguntas, cada uma pegando um estrago:
dimensão não positiva no `viewBox` (o sentinela chegando invertido) e coordenada acima de
`LIMITE_COORDENADA_PLAUSIVEL = 1e15` (o sentinela chegando com o sinal certo). Traduz para
`FalhaMotor`, e **não** `DesenhoVazio`: pela taxonomia da fila (planta §11), desenho vazio é a coluna
do *"ninguém resolve"*, e contar isto ali o subtrairia justamente da conta que mede o **nosso**
trabalho.

**Três decisões que ficam registradas:**

- **a ordem das duas checagens é o contrato.** Se a geometria fosse conferida primeiro, todo SVG sem
  traço seria relatado como destruído e migraria de coluna na fila do cockpit;
- **`viewBox` ausente ou ilegível NÃO reprova** — quem julga é a evidência positiva de destruição, não
  a falta dela. O formato do `dwg2SVG` pode mudar entre builds, e um guarda que reprova o que não
  entende transforma atualização de motor em acervo que para de abrir;
- **o corte em 1e15 é folgado de propósito.** O `confrontantes.dwg`, que motivou a separação de folha,
  põe geometria a 8,5 milhões de unidades da origem (§4.5) — um corte apertado reprovaria o arquivo do
  próprio acervo. 1e15 deixa cinco ordens de grandeza entre o desenho legítimo mais extremo e o
  sentinela.

**Cobertura:** `FolhaDestruidaDoSvgDiretoTests` (9 casos) em
[tests.py](../backend/moduloprancheta/tests.py) — os quatro modos de destruição, os dois controles de
desenho legítimo (prancha comum e UTM de obra real), os dois de `viewBox` ilegível e a ordem das
checagens. Lógica verificada caso a caso; **a classe ainda não rodou dentro da suíte Django** — o venv
local não tem GDAL e a imagem dos containers é anterior a 10/08.

**Limite do que foi medido:** o arquivo onde isto apareceu é uma amostra sintética
(`gerar_amostras.py`, que é o [D41](pendencias.md)), então **não se sabe com que frequência o acervo
real cai neste caso**. O guarda vale de qualquer forma — ele é barato e a falha é silenciosa —, mas a
frequência só sai medindo sobre o corpus.

---
### D78 — O nosso teto de memória vazava para o `dwg2dxf` e saía como "compre o motor premium" · ✅ corrigido 09/08/2026

**O achado.** Investigando os 3 `motor_insuficiente` da remedição dos DWGs acima de 40 MB, nenhum dos
três era limite do motor livre. Rodado cru, fora do pipeline, o `dwg2dxf` converte os três **com
código 0 e `EOF` válido**:

| Arquivo | Entrada | DXF gerado | Tempo |
|---|---|---|---|
| `Arq.dwg` | 95,8 MB | **705 MB** | 37 s |
| `JS_PROJETO EXECUTIVO FINAL COM LAZER.dwg` | 138,4 MB | **1,05 GB** | 109 s |
| `JS 26062023.dwg` | 155,5 MB | **952 MB** | 110 s |

As ~6.700 linhas de stderr de cada um são `Warning:` recuperável — 3.170 delas o mesmo
`Unknown object, skipping eed/reactors/xdic`.

**O mecanismo, inteiramente nosso.** `orcamento_de_conversao()` arma o `RLIMIT_AS` e **só então**
chama `adaptador.converter()`, que spawna o `dwg2dxf` — e **`RLIMIT_AS` é herdado pelo filho**. Um
intermediário de 1 GB não cabe; o LibreDWG **não confere o retorno do `malloc`**, desreferencia nulo e
morre com **SIGSEGV**. O `dwg.py` lia "código ≠ 0" como fronteira do motor e respondia *"Ele exige o
motor de alta fidelidade"*. Confirmado 3 de 3, com e sem `ulimit -v`: soltos dão código 0 e DXF
íntegro; sob o teto dão **139** e zero byte.

**Por que era grave além do rótulo.** O mesmo teto produzia **dois vereditos com donos opostos**:
estourando no `ezdxf` (em processo) virava `recurso_excedido` → *nós*; estourando no `dwg2dxf`
(subprocesso) virava `motor_insuficiente` → *o cliente*. Um pede desculpa, o outro manda pagar — pela
mesma causa, decidida por qual metade do motor estourou primeiro. E como `motor_insuficiente` é a
única causa que a planta lê como fronteira comercial, o dimensionamento da **PRA.4** estava apoiado
num artefato do nosso próprio orçamento.

**A correção, em duas ações escolhidas pelo dono (09/08/2026), com a terceira recusada.** A saída
"subir o teto" foi descartada de saída — *"não vamos jogar dinheiro no problema; não vamos subir o
teto sem antes saber o custo real da operação"*.

1. **Classificar pelo sinal** (imediata): `morreu_por_falta_de_memoria()` em
   [motores/base.py](../backend/moduloprancheta/motores/base.py) — morte por `SIGSEGV`/`SIGABRT`/
   `SIGBUS`/`SIGKILL` **com teto nosso valendo** vira `RecursoExcedido`, que já existia com a
   semântica exata (*"É nosso, e não pode virar upsell"*, D57). Declarado no código que **não dá para
   distinguir com certeza** — um SIGSEGV sob teto poderia ser um bug do LibreDWG sem relação com
   memória —, e que na dúvida a plataforma assume a culpa: errar para o lado de pedir desculpa custa
   uma conversão, errar para o outro custa a confiança de quem paga.
2. **Orçamento próprio para o subprocesso** (definitiva): `rodar(..., memoria_mb=)` arma `RLIMIT_AS`
   no filho via `preexec_fn` — entre `fork` e `exec`, onde ele ainda pode ajustar o próprio limite,
   porque `teto_de_memoria` **preserva o limite duro** de propósito. Valor em
   [`payment/planos.py::PRANCHETA_SUBPROCESSO_MEMORIA_MB`](../payment/planos.py) = 2.048, declarado
   provisório. **Não sobe o gasto:** o filho herdava `VA_do_processo + 1536`, ~2,6 GB efetivos no
   `worker-conversao` — 2.048 é mais apertado, e apertar em vez de afrouxar enquanto o custo real não
   está medido foi a decisão.

**Duas arestas que só apareceram ao implementar:**

- **A escada ia triplicar o desperdício.** `_rodar_a_escada` desce um degrau a cada `RecursoExcedido`,
  e as economias do DWG agem no `ezdxf` — estágio que estes arquivos nem alcançam. Cada arquivo grande
  repetiria a decodificação inteira (37 s a 110 s) três vezes para falhar igual. O estouro do
  subprocesso passou a se declarar `degradavel=False`, e quem levanta é quem declara.
- **A classificação tinha furo pelo próprio conserto.** Filho morto pelo teto que *nós* demos a ele,
  com o pai sem orçamento armado (fora do pipeline), voltaria a ser lido como insuficiência de motor.
  `morreu_por_falta_de_memoria` passou a considerar os dois tetos.

**A prova, no stack:** os 3 saem agora como `recurso_excedido`, *"falhas que são NOSSAS: 100%"*,
*"limite REAL do caminho livre: 0,0%"* — e em **8,8 s a 10,6 s** cada, contra 37–110 s de uma
decodificação só, porque batem no teto antes e não descem escada inútil.

**O instrumento foi consertado três vezes no mesmo dia, e a terceira só a prova revelou.** A `nota`
do parcial cortava em 120 caracteres **pela cabeça** e o `MotorInsuficiente` cortava o stderr em 500,
também pela cabeça — o LibreDWG escreve os avisos no começo e o erro fatal no fim, então as duas
camadas juntas descartavam exatamente a causa (`_resumo_do_erro()` e `_stderr_util()`). Depois, com o
custo migrando para o filho, o amostrador de memória do processo pai passou a reportar **0 MB** —
verdadeiro e inútil —, e entrou `_pico_dos_filhos_mb()` por `RUSAGE_CHILDREN`, que é marca d'água
acumulada e **só é atribuível com um filho por processo**: garantia que o código não dá sozinho e o
protocolo dá (`LOTE=1`, um container por arquivo). Parcial subiu para **v3**, com `custo` por arquivo.

**O limite que fica declarado:** quem morre no teto teve o **teto** medido, não a exigência. Os três
marcaram 2.035–2.036 MB porque param nos 2.048 — piso, não medida. O relatório passou a marcar esses
valores com `≥` e a excluí-los da dispersão, porque misturá-los faria o custo parecer mais previsível
pelo tamanho do que é. Pelo que a passada crua mostrou (convertem em container de 3 GB sem
`RLIMIT_AS`), a exigência real dos três está **entre 2 e 3 GB**.

---
### D43 — O DXF que o nosso conversor gera é ilegível em 12% do acervo · ✅ corrigido 09/08/2026

**O que fechou: o decodificador não era consertável do nosso lado, e a versão que o conserta
existia.** Depois de cinco causas isoladas arquivo a arquivo (quatro do escritor de DXF do LibreDWG,
uma nossa), o que restava era o **grupo A** — o `dwg2dxf` não conseguia *decodificar* o DWG, escrevia
um intermediário truncado e saía com código 0. Nenhum reparo de saída traz de volta um dado que não
está no arquivo, e por isso a fila não andava mais com trabalho em Python.

O 0.13.3 pinado no [Dockerfile](../backend/Dockerfile) **é o release mais novo publicado** — não há
0.13.4 no ftp.gnu.org, e ele é de 2023. O ponto adiante era o git master, e a decisão foi **medir
antes de escrever C**: um build custa 10 minutos e podia fechar de graça bugs corrigidos a montante
havia dois anos.

**A medição, em três degraus, cada um respondendo a uma dúvida do anterior:**

| Passada | O que mediu | Resultado |
|---|---|---|
| decodificador cru, 19 alvos | 0.13.3 × 0.14.8566, `msp` e envolvente | 13 conservam · **0 regressões** · 0 "abre vazio" |
| pipeline inteiro, 19 alvos | o veredito de produção, nos dois binários | 0.13.3: **7/19** · master: **19/19** |
| corpus de 160, o mesmo de 07–09/08 | a taxa do acervo, motor novo | **159/160 = 99,4%** |

**Falhas que são nossas: 0,6% — um arquivo, e ele não é erro de código.** O
`J2 - S_PROJETO EXECUTIVO FINAL COM LAZER.dwg` estoura o orçamento de 1.536 MB
(`recurso_excedido`); é teto de recurso, que mora em [payment/planos.py](../payment/planos.py) e é
knob do dono, não defeito de engenharia. Registrado como limite consciente na
[planta §4.1](modulos/moduloprancheta.md).

**Não houve regressão, e isso é verificável e não opinião:** o conjunto de falhas novo (1 arquivo)
está **contido** no antigo (25) — nenhum arquivo que convertia deixou de converter. As duas passadas
falam do mesmo corpus, conferido linha a linha contra
[corpus-160.txt](../ferramentas/medicao/corpus-160.txt); foi para isso que o `remedir_dwg.sh` ganhou
`CORPUS=`, porque trocar motor e amostra na mesma passada produziria um número que não se pode
atribuir a nada.

**Três consequências que passam do achado:**

1. **O degrau de plano em DWG desapareceu.** `motor_insuficiente` era 3,1% e agora é **0%** — os 5
   arquivos que sustentavam a fronteira convertem no motor livre. A **PRA.4** perde o DWG como
   justificativa e fica dimensionada só por RVT/NWD, que é exatamente o que a planta já mandava fazer
   ("dimensionar por RVT/NWD, não por cobertura de DWG"). Vender o premium por cobertura de DWG
   agora seria o [D34](#) ao contrário, com número contra.
2. **O bug que remendávamos está consertado a montante.** `convertido_apos_reparo: continuacao_orfa`
   sumiu do relatório: o corte de texto em 255 bytes sem código de continuação não acontece mais. O
   `remendar_continuacoes` fica como **rede**, não como muleta — e continua auto-limitado, então não
   atrapalha.
3. **Ganhou fidelidade, não só legibilidade.** `com_blocos_ausentes` caiu a zero e `multifolha`
   subiu: arquivo que vinha pela metade passa a vir inteiro. É a diferença entre este caminho e o
   `--as rNNNN` refutado abaixo, que fazia tudo "abrir" com o modelspace vazio.

**O que a adoção custou.** O binário deixou de vir da tarball assinada do GNU e passa a vir de um
**commit fixado** (`a8ce2489`, 06/08/2026). Commit não é ponto arquivado — histórico pode ser
reescrito —, então a imagem passou a carregar o **fonte correspondente** da GPLv3 §6 gerado do próprio
commit (`git archive`), +25 MB. Detalhe em [THIRD-PARTY-LICENSES.md](../THIRD-PARTY-LICENSES.md).

**O que a adoção também custou, e não estava no plano: 11 miniaturas.** O `dwgbmp` vem do mesmo
fonte, então subiu junto — e extrai **menos** preview embutido que o 0.13.3 (49 → 40 sobre os mesmos
160). Aceito porque os 11 arquivos afetados **convertem**, e o cartão deles passou a mostrar o nosso
redesenho vetorial em vez do raster do CAD; o preview existe para quando a conversão falha, e nenhum
dos 11 está nesse caso. Gatilho de reabertura e o conserto (um segundo build stage só para o
`dwgbmp`) na [planta §4.4](modulos/moduloprancheta.md).

Achado, aliás, por comparar as duas passadas linha a linha em vez de olhar só a taxa — o número que
subia era o da conversão, e a regressão estava numa contagem ao lado.

**Fica valendo para a próxima:** subir o `LIBREDWG_COMMIT` é mudar o motor que produz a taxa de
cobertura — exige remedir o mesmo corpus, nunca só "conferir se builda". E conferir as **outras**
contagens do relatório, não só a que se queria mover.

O relato da investigação que levou até aqui segue abaixo, inteiro, porque as cinco causas e os dois
caminhos refutados (`--as rNNNN` e o resgate por `dwg2SVG`) são o que impede que cada um deles seja
tentado de novo.

---

### Investigação original do D43 — o relato de 08–09/08/2026


O maior resto do **D42**, e ele é **nosso**: o `dwg2dxf` termina com código 0 e arquivo não-vazio — ou
seja, o LibreDWG **não reclama** —, mas o `ezdxf` não consegue ler o DXF resultante nem com
`recover.readfile`. O cliente recebe a mensagem certa (a correção (b) do D42), que diz que o arquivo
com problema é o nosso; o que ele não recebe é a prancha. Com o D61 fechado, **este é o bolso que
sobrou** — e é o maior.

**Andamento medido sobre o mesmo corpus de 160** (`corpus_hash f8f5b542c6497a47`), passada a passada:

| | 08/08 | 09/08, depois dos consertos |
|---|---|---|
| convertido | 126 (78,8%) | **135 (84,4%)** |
| `dxf_intermediario_ilegivel` | 22 | **19** |
| `desenho_vazio` | 5 | **0** — ver abaixo, não é ganho |
| `recurso_excedido` | 0 | 0 |
| `motor_insuficiente` (fronteira do premium) | 5 (3,1%) | **5 (3,1%)** |
| falhas que são **nossas** | 21,2% | **12,5%** |

**Os 19 estão nomeados**, um a um, em
[ferramentas/medicao/resultado-2026-08-09.log](../ferramentas/medicao/resultado-2026-08-09.log) — o veredito por
arquivo é gravado no parcial da medição (v2), justamente porque a passada anterior deixou este achado
como um número sem lista. Não é mais preciso remedir para saber por onde começar.

**Por que 22 − 9 convertidos dá 19 e não 13, e a diferença importa.** Os 5 que a passada anterior
chamava de `desenho_vazio` ("de ninguém — o arquivo não tem desenho") e 1 de `falha_motor` mudaram de
causa, não de estado: todos têm DXF **sem a tag `EOF`**, e a conferência de decodificação passou a
recusá-los antes. A leitura antiga era um **falso "de ninguém"** — o modelspace vazio não era prova de
desenho vazio, era consequência de o intermediário ter sido cortado no meio. Eles não pioraram; a
conta é que ficou honesta, e agora estão na nossa fila, onde sempre deveriam ter estado.

**O corte barato foi medido em 09/08/2026 — e está REFUTADO.** A primeira hipótese da lista era a
flag de versão de saída do `dwg2dxf` (`--as rNNNN`, com `r12`/`r14`/`r2000`/`r2004`/`r2007`/`r2013`
disponíveis neste build). Ela **funciona demais**: com `--as r2000` os arquivos ilegíveis passam a
abrir no `ezdxf.readfile` — sem sequer precisar do `recover`. Parece o conserto, e não é.

Medido nas 6 amostras do AutoCAD (`AeData/Proj`), com contagem de entidade e não só de legibilidade:

| Arquivo | `atual` (sem `--as`) | `--as r2000` | `--as r14` |
|---|---|---|---|
| GbDemo/001 | 552 KB · **ilegível** | 122 KB · abre, **msp=0** | 91 KB · abre, **msp=0** |
| GbDemo/022 | 571 KB · **ilegível** | 122 KB · abre, **msp=0** | 90 KB · abre, **msp=0** |
| Tabular TermLay/T04 | 365 KB · **ilegível** | 122 KB · abre, **msp=0** | 92 KB · abre, **msp=0** |
| IecDemo/020 | 794 KB · **ilegível** | 133 KB · abre, **msp=0** | 98 KB · abre, **msp=0** |

`msp=0`, zero entidade em layout e **sem envolvente**: o DXF sai com a tabela de camadas e as
definições de bloco preservadas e **sem geometria nenhuma**. Aplicar a flag transformaria 22 linhas de
`erro`/`falha_motor` — que hoje dizem a verdade — em 22 pranchas `PRONTO` **em branco**. É o **D52**
outra vez, e desta vez com a maquiagem de um ganho de 13,8% de cobertura.

**O controle é o que fecha o argumento**, e por isso ele foi rodado: nos DWGs que o caminho atual
converte **hoje**, o mesmo instrumento conta `msp=190` (`Aegs/AEGS06`) e `msp=215` (`Demo/DEMO06`),
com envolvente real `(53,4 × 23,4)` — e os **mesmos dois arquivos** zeram (`msp=0`, sem envolvente)
quando se passa `--as r2000`. Não é que os 22 estejam vazios: é a conversão de versão deste LibreDWG
que esvazia o modelspace, calada, com código de saída 0. Sem o controle, o resultado teria sido lido
como "os 22 eram vazios mesmo".

**Fica valendo, então:** o `--as` não entra no motor; se algum dia entrar, tem de vir com asserção de
contagem de entidade junto, nunca só com teste de legibilidade. A investigação que ficou de pé — *quais
construções quebram o parser* — **foi feita em 09/08/2026** e está nas seções de causa abaixo: são
**cinco** defeitos distintos, nenhum deles o que a mensagem de erro sugeria, e um deles nosso.

**O caminho de resgate pelo `dwg2SVG` foi RECUSADO** *(decisão do dono, 09/08/2026)*. Ele funciona —
250 `<path>` em `GbDemo/001` e 290 em `IecDemo/020`, os dois hoje ilegíveis —, mas entregaria uma
prancha sem folha, sem escala e sem âncora: **sem medir e sem calibrar**, que é a promessa central do
módulo. Três razões, e a terceira é a que decide: quebra o valor prometido; gera chamado de suporte
perguntando por que as ferramentas sumiram naquele arquivo; e **paliativo tende a virar definitivo**,
com regra de interface (faixa de aviso, botão travado) sendo construída para acomodar a gambiarra em
vez de o motor. Mantém-se a falha clara, para não mascarar a dívida.

### A causa raiz — achada em 09/08/2026, e é um defeito do escritor de DXF do LibreDWG

Não é arquivo do cliente, não é construção exótica de CAD, e não é estatística: é mecânico e tem uma
linha só.

**O `dwg2dxf` corta valor de texto em 255 bytes e escreve o resto na linha seguinte sem emitir o
código de grupo `3` de continuação.** O DXF é estritamente pares linha-a-linha (código, valor), então
o parser lê a continuação órfã como se fosse um código de grupo e morre ali:

```
  1
图号=FILENAME;文件名称=DWGDESC;…;BY1=LINE14      ← 255 bytes exatos
;RD1=LINE15;REV2=LINE16;REV2DET=LINE17;…       ← órfã: faltou o "  3" antes
```
```
DXFStructureError: Invalid group code ";RD1=LINE15;REV2=LINE16;…" at line 19419
```

Medido nas 6 amostras do AutoCAD: **o valor que precede toda quebra tem exatamente 255 bytes**, sempre
em código `1`, com 2 a 5 continuações órfãs por arquivo. O `ezdxf.recover` também não salva — a quebra
é estrutural, não sujeira.

**O conserto é reinserir o `3`, e ele devolve o arquivo ao caminho normal** — `MotorDxf` → `Recorder`
→ folha, escala e âncora, tudo. Medido:

| | antes | depois do reparo |
|---|---|---|
| GbDemo/001 | ilegível | `readfile` · `msp=193` · caixa 977 × 625 |
| GbDemo/008 | ilegível | `readfile` · `msp=78` · caixa 975 × 625 |
| GbDemo/015 | ilegível | `readfile` · `msp=159` · caixa 975 × 625 |
| GbDemo/022 | ilegível | `readfile` · `msp=155` · caixa 975 × 625 |
| Tabular TermLay/T04 | ilegível | `readfile` · `msp=18` · caixa 977 × 625 |
| IecDemo/020 | ilegível | `readfile` · `msp=212` · caixa 1344 × 655 |

Leitura limpa por `readfile`, sem passar pelo `recover`, e a envolvente bate com folha de prancha
real. 6 de 6.

**A ordem do código 3 importa, e errá-la corrompe o texto em silêncio.** Pela spec, texto longo vai
como `3 <pedaço>` … `3 <pedaço>` **terminado** por `1 <pedaço final>` — o código 1 é o **último**.
Inserir o `3` *depois* do `1` conserta a estrutura e a geometria sai idêntica, mas o MTEXT remonta com
o fim na frente: `'7x; 34} 3.4{\Fmonotxt…'` em vez de `'{\Fmonotxt…} 3.4'`. Mesmo tamanho (266
chars), nada perdido — só embaralhado, e justamente em carimbo, legenda e chamada de cota. Um reparo
validado só por "abriu" passaria por isto.

**Residual a conferir junto do conserto:** o corte é em **bytes**, então pode cair no meio de um
caractere UTF-8 multibyte. Nas amostras não caiu (`001` corta em 255 bytes = 187 chars, fronteira
limpa), mas é o mesmo defeito com outra saída, e o reparo por linha não o cobre — as duas metades do
caractere ficam em linhas diferentes, decodificadas em separado.

**Onde o conserto vai:** em `MotorDwg._para_dxf`, **não** no `MotorDxf`. O DXF quebrado é o nosso
intermediário; um DXF que o *cliente* subiu com essa forma está genuinamente malformado, e o
`origem="dxf"` deve continuar dizendo isso.

**A montante:** é bug do LibreDWG 0.13.3 e vale reportar. O reparo local é auto-limitado (só dispara
em valor de exatamente 255 bytes seguido de linha que não é código), então continua inofensivo quando
uma versão corrigida chegar.

**Implementado e medido sobre os 22 — e o resultado corrige a expectativa.** O remendo está em
[`motores/dwg.py`](../backend/moduloprancheta/motores/dwg.py) (`remendar_continuacoes`, chamado por
`_para_dxf`), com 8 regressões de bytes escritos à mão em `RemendoDeContinuacaoTests`; suíte
`moduloprancheta` **298/298**. Rodado o motor real sobre a lista nominal, um contêiner por arquivo,
sob `orcamento_de_conversao`:

| | arquivos |
|---|---|
| **Conserta** — era só a continuação órfã | **7** (as 6 amostras do AutoCAD + `460017387_PES1…`, 8 remendos, 9,5 MB de SVG) |
| Remendo dispara, mas há defeito atrás | 1 (`JAMYLLE E PAULO…`, 8 remendos, depois `KeyError '00 - CADASTRO'`) |
| Outra causa, remendo não dispara | 14 |

Cobertura do corpus: **78,8% → 83,1%** (126 → 133 de 160). O `dxf_intermediario_ilegivel` cai de 22
para **15 (9,4%)**.

A lição do número: as 6 amostras eram **homogêneas** — mesma árvore do AutoCAD, todas `AC1032` — e
compartilhavam um defeito só. Extrapolar delas para o acervo real superestimou o ganho em cerca de 3×.
O corte barato continuou barato; o bolso é que era menor do que a amostra sugeria.

### O segundo defeito, e ele NÃO é do escritor: o `dwg2dxf` falha em decodificar e sai com 0

Dos 15 que sobram, ~13 têm a mesma assinatura, medida em `aerhetg.DWG` (DWG de 1,9 MB → DXF de
**59 KB**):

```
ERROR: Invalid object handle 0.3.0 at pos @9.2
ERROR: bit_read_BD: unexpected 2-bit code: '11'
ERROR: Some section size or address out of bounds
ERROR: BLOCK_HEADER *Model_Space first_owned_entity missing
```

O `dwg2dxf` **grita no stderr**, escreve um DXF truncado (termina em `ENDSEC`, **sem a tag `EOF`**) e
**retorna 0**. O `ezdxf` então morre em `missing EOF tag` e, no `recover`, em
`DXFTypeError: name has to be a string, got NoneType` — registro de tabela sem `name`, porque a tabela
nunca foi escrita inteira.

Natureza diferente da anterior, e isso muda o que dá para fazer: no primeiro defeito o LibreDWG
**decodificou bem e escreveu mal** (recuperável reescrevendo a saída); aqui ele **não conseguiu ler o
DWG** — o dado não existe no intermediário, e nenhum reparo de saída o traz de volta.

**Corrigido em 09/08/2026 — `_conferir_decodificacao` em
[`motores/dwg.py`](../backend/moduloprancheta/motores/dwg.py).** O `_para_dxf` só examinava
`returncode` e tamanho do arquivo; capturava o `stderr` e o usava **só quando o código era diferente
de zero**. A ferramenta avisava e não estávamos ouvindo. Agora o intermediário truncado é recusado ali
mesmo, com a causa do decodificador na frase, em vez de morrer dois passos adiante no `ezdxf` falando
de `name`/`NoneType` — que mandava investigar o leitor de DXF quando o defeito estava no leitor de
DWG. Suíte `moduloprancheta` **306/306**.

**O critério é a tag `EOF`, e só ela — o `stderr` nomeia, não julga.** A primeira versão também
reprovava quando havia linha `ERROR:` no stderr, e a medição derrubou a regra **antes de ela sair do
teclado**: numa amostra de 30 DWGs que **convertem hoje**, **25 emitem `ERROR:`** — o LibreDWG grita
por problema recuperável o tempo todo. Aquele critério teria reprovado ~83% das conversões que
funcionam, estrago muitas vezes maior que os 12 arquivos que consertaria. A falta da tag `EOF`, ao
contrário, é definicional, e a medida confirma: **0 falsos positivos em 35 arquivos que convertem**.
Há regressão travando o critério errado (`test_ERROR_no_stderr_NAO_reprova_arquivo_completo`), porque
ele é intuitivo o bastante para voltar.

**A separação exata dos 15, pela evidência e não pela mensagem de erro:**

| Grupo | O que houve | Arquivos | Depois dos consertos de 09/08 |
|---|---|---|---|
| **A** | `dwg2dxf` não decodifica: DXF truncado, **sem tag `EOF`** | **12** | **12** — o dado não existe no intermediário; nenhum reparo de saída o traz de volta |
| **B** | DXF **completo** e o `ezdxf` ainda assim não lê | 3 | **1** — dois abriram (seta de cota órfã e `recover` estreito); o `FILE.DWG` é truncamento disfarçado e passa para o grupo A |

Os 12 do grupo A têm de 7 a **2.115** linhas `ERROR:` do decodificador. Todos com cabeçalho `AC10xx`
dentro do alcance do motor livre — nenhum é limite de plano.

**O que não é decidível sem medida:** se esses arquivos são limite do LibreDWG (e portanto candidatos
a `motor_insuficiente`, a fila de quem compra o premium) ou defeito dele em arquivo que outros
leitores abrem. Reclassificar sem prova seria o falso upsell do [D34](historico-correcoes.md) ao
contrário. Enquanto não houver essa prova, seguem contados como **nossos**.

**A prova foi feita, e fecha a questão** *(dono, 09/08/2026)*. A lista nominal está em
[ferramentas/medicao/d43-alvos-2026-08-09.txt](../ferramentas/medicao/d43-alvos-2026-08-09.txt); ele abriu os 15
no AutoCAD: **todos abriram**. Os arquivos são bons. O defeito é do LibreDWG, e os 15 continuam na
fila do que **nós** consertamos — não são `arquivo_corrompido` (o arquivo do cliente está íntegro) nem
`motor_insuficiente` (não é limite de plano). A frase que o cliente lê hoje — *"O arquivo com problema
é o nosso, não o seu"* — está certa, e agora está provada.

**Não há padrão de versão**, o que descarta a hipótese mais barata: os 12 do grupo A se dividem em
exatamente 3 arquivos para cada uma de `AC1018` (2004), `AC1021` (2007), `AC1024` (2010) e `AC1027`
(2013). Não é "o LibreDWG não acompanha o formato novo".

**E o grupo A tem duas metades, que pedem consertos diferentes:**

- **arquivo íntegro** — o `01 LOTEAMENTO PORTAL RESIDENCE.dwg` (o pior de todos: **2.115** erros de
  decodificador) abriu **limpo**, sem recuperação, e o AutoCAD o declarou *"DWG Confiável, salvo por
  aplicativo da Autodesk"*. Aqui não há desculpa: é bug puro do decodificador sobre arquivo são;
- **arquivo danificado que o AutoCAD conserta sozinho** — o `Planta Projeto Impressão Final…` abriu
  **por recuperação**: *"Total de erros encontrados 15, corrigidos 15, apagados 1 objetos"*, incluindo
  uma hachura sem loop de contorno válido que foi **apagada**. O arquivo tem dano real; o que o torna
  utilizável é o AutoCAD ter uma **camada de recuperação** — que o LibreDWG não tem.

A distinção importa porque muda o alvo: a primeira metade se fecha consertando (ou trocando) o
decodificador; a segunda pede tolerância a arquivo danificado, que é software que o LibreDWG não
oferece. Contar as duas como um problema só levaria a estimar errado de novo, como já aconteceu com as
6 amostras homogêneas.

### A 3ª e a 4ª causa — o grupo B aberto, e ele não era o que a mensagem dizia

Os 3 do grupo B (DXF **completo**, com `EOF`, e o `ezdxf` recusando assim mesmo) foram abertos um a
um em 09/08/2026. Nenhuma das três mensagens apontava para o defeito real:

| Arquivo | A mensagem dizia | O que era, medido |
|---|---|---|
| `As-Built_REAL CONDOMINIO` | *"Invalid DXF attribute `name` for entity VERTEX"* | A `DIMSTYLE Standard` tem `342 → #7`, e o `#7` deste arquivo é um **VERTEX**. O arquivo tem **1.244 handles repetidos** (todos pares de VERTEX) |
| `FILE.DWG` (Aratuípe) | *"name has to be a string, got NoneType"* | Um `BLOCK_RECORD` **inteiramente vazio** fechando a tabela — sem handle, sem nome |
| `JAMYLLE E PAULO` | *"`KeyError: '00 - CADASTRO'`"* | **Nosso**: o `_ler` só caía no `recover` em `DXFStructureError`. Pelo `recover` o arquivo abre com **25.727 entidades** |

**A seta de cota (`descartar_setas_de_cota_orfas`).** O código `342` é o bloco da ponta da cota. A
`ezdxf` resolve handle→nome no 2º estágio da carga e **prevê o handle que não existe** — captura
`KeyError` e cai na seta padrão. O que ela não prevê é o handle que **existe e aponta para outra
coisa**: aí o `.dxf.name` levanta `DXFAttributeError`, que está fora do `except`, e a carga inteira
morre por causa de uma ponta de seta. O reparo tira a referência impossível, que é exatamente o que a
`ezdxf` faria se o handle não existisse. **Só descarta o que tem dono errado** — handle nulo e handle
não declarado ela já trata, e se **algum** dono do handle é `BLOCK_RECORD` a referência fica (erra-se
para o lado de preservar a seta).

**O registro vazio (`descartar_registros_vazios`).** Todo registro de tabela precisa de handle e
nome; um com zero tags não descreve coisa alguma, e descartá-lo não perde informação porque não há
informação ali. Dispara **só dentro da `TABLES`**: na `BLOCKS` e na `ENTITIES` a mesma forma é
entidade legítima sem atributo, e apagá-la seria apagar desenho.

**E o `FILE.DWG` não abriu assim mesmo** — o reparo tirou o registro vazio e apareceu o defeito atrás:
o arquivo declara **1 `BLOCK_RECORD` para 3 layouts** (dois deles reivindicando `#1F` e `#23`, que não
existem). A tabela foi escrita pela metade **apesar da tag `EOF`**, então ele é truncamento de
decodificação disfarçado de arquivo completo — vai para o mesmo balde dos 12, e consertá-lo exigiria
**inventar** os registros que faltam, que é fabricar estrutura e não reparar.

### A 5ª causa é nossa: o `recover` estava ali e não era chamado

O `_ler` do `MotorDxf` tenta `ezdxf.readfile` e cai no `recover` quando falha — essa é a intenção
escrita no próprio docstring. A implementação, porém, caía **apenas** em `DXFStructureError`:
qualquer outro erro virava "DXF ilegível" na hora, com a segunda tentativa ali do lado sem ser
chamada. O `JAMYLLE` morria assim, e abre com 25.727 entidades pelo caminho que existia.

Agora toda falha de **conteúdo** tenta o `recover`; ficam de fora só o `OSError` (é o arquivo, não o
conteúdo — o `recover` abriria o mesmo caminho e falharia igual) e o `NAO_EMBRULHAR`, que carrega o
teto de memória do [D57](historico-correcoes.md). E a frase de erro passou a nomear o **primeiro**
erro, não o segundo: é o primeiro que descreve o defeito, e foi assim que um `KeyError` virou achado
em vez de linha de log.

### O reparo que custou uma conversão — e o teste que impede a volta

A 1ª versão desta camada encadeava as três funções, cada uma fazendo `split` e `join` do arquivo
inteiro. Num DXF de **84 MB** (o maior do corpus, 86.191 entidades) são três listas de centenas de MB
para, quase sempre, não mudar um byte — e a remedição mediu o efeito: **um arquivo que convertia
passou a estourar** o orçamento de 1.536 MB e virou `recurso_excedido`. Reparo que custa conversão
não é reparo; é o [D57](historico-correcoes.md) voltando pela porta dos fundos.

Corrigido: divide as linhas **uma vez**, junta **uma vez**, e não junta se ninguém mexeu — cada
reparo varre antes de reconstruir e devolve o objeto original quando não achou nada (o mapa de
handles, que é caro, só é construído depois de provar que existe `DIMSTYLE` com referência de bloco).
A regressão cobra isso com `assertIs`, e não com `assertEqual`: conteúdo igual não prova que não
houve realocação.

**Nota de dimensionamento para a PRA.4:** se o AutoCAD abre os 15, o motor premium (APS) presumivelmente
também abre. O número que dimensiona o premium — 3,1% do acervo — mede só o `motor_insuficiente`, e
**não** inclui estes 9,4%. Isso não os transforma em upsell (vender plano para contornar bug nosso
continua sendo o [D34](historico-correcoes.md) ao contrário), mas é fato a considerar quando a PRA.4
for orçada.

**O experimento foi feito em 09/08/2026, e o ida-e-volta funciona.** O dono salvou o
`Planta Projeto Impressão Final…` depois da recuperação do AutoCAD (que o reescreveu de `AC1027` para
`AC1032`) e o arquivo salvo **converteu**: 16.391 traços, modelspace, sem recuperação nossa — num
arquivo que é o 2º pior do corpus em erro de decodificador (1.719).

Isso tem uma consequência imediata para quem usa o sistema hoje, e ela é maior que o arquivo: a frase
que o cliente lia dizia *"reexportar do CAD não resolve"*, e **resolve**. Dizer que não há saída
quando há é pior que não dizer nada — o cliente fica esperando por nós com a solução na mão. A
mensagem do `_conferir_decodificacao` passou a oferecer o caminho, com a palavra **"costuma"** e não
"resolve": a prova é de um arquivo, e a lição das 6 amostras homogêneas deste mesmo D43 é que amostra
pequena e parecida superestima. Regressão em `test_a_frase_oferece_o_caminho_que_funciona_em_vez_de_negar_um`.

**O que isto não resolve:** o defeito continua nosso, e o caminho depende de quem enviou ter o
AutoCAD e refazer o envio. Não vira `arquivo_corrompido` nem upsell — vira contorno declarado
enquanto o decodificador não for consertado.

**Pista barata achada na PRA.1b:** a tarball do LibreDWG que o build stage já compila produz **13
binários**, e um deles é o **`dwg2SVG`** — DWG direto para SVG, sem passar pelo `ezdxf`. Ou seja, a
"hipótese cara" acima pode custar uma linha de `COPY` para *medir*. Duas ressalvas antes de
entusiasmo: o SVG dele não passa pelo `Recorder`, então não teria a separação por folha (PRA.1c), a
âncora de marcação nem a escala — só serviria como caminho de resgate para os 13% que hoje não abrem
de jeito nenhum; e a qualidade do render dele é desconhecida. Vale como experimento, não como plano.

**Por que é 🟠 e não 🔴:** ninguém é acusado injustamente e nada fica pendurado — a derivada vai para
`erro` com motivo `falha_motor`, que é a fila do que nós consertamos, e o acervo continua servindo o
arquivo original para download.

---


### D73 — WeasyPrint com `url_fetcher` irrestrito · ✅ corrigido 09/08/2026

Achado **latente**, fechado antes de doer. `HTML(string=html).write_pdf()` roda com o buscador padrão
do WeasyPrint, que **busca URL de verdade**. Nos dois templates de então não havia `img`, `url()` nem
`|safe`, e o autoescape do Django segurava o resto — não havia SSRF. Havia a distância de **uma
linha** até haver: o primeiro logo de tenant no cabeçalho, e o PDF passa a buscar
`http://169.254.169.254/…` (metadado de nuvem) e `file:///etc/…` por conta do HTML. Quem escrevesse
essa linha não teria como saber.

**A correção é um buscador que não busca fora**, em
[funcoesimpexp/formatos/escrita.py](../backend/funcoesimpexp/formatos/escrita.py): `data:` passa
(não é busca — o conteúdo já está no documento), todo o resto levanta `RecursoExternoRecusado`.
Quando o logo embutido for pedido de verdade, o caminho é o `data:` URI, que já é aceito.

**O achado tinha duas portas, e fechar uma teria deixado a outra aberta.** `write_pdf()` aparecia em
dois módulos — o impexp e o [moduloorcamento/exportacao.py](../backend/moduloorcamento/exportacao.py)
—, cada um com sua chamada e, portanto, sua política de rede. Agora existe **uma** porta de PDF
(`html_para_pdf`), pela mesma razão que existe uma porta de arquivo: política que se repete é
política que diverge. O `planilha_pdf` do Orçamento chama por lá e traduz a exceção para o contrato
dele.

**Prova, e não confiança.** A frase "o WeasyPrint pula o recurso recusado em vez de abortar" estava
escrita como sabida — é comportamento de biblioteca de terceiro e muda de versão. Virou regressão:
[test_d73_pdf.py](../backend/funcoesimpexp/test_d73_pdf.py) emite um PDF a partir de HTML que aponta
para o IP de metadado e cobra que o `%PDF` saia mesmo assim. A diferença entre pular e abortar é a
diferença entre um PDF sem logo e um relatório que ninguém consegue emitir.

E há um teste que dá **durabilidade** ao conserto: `PortaUnicaDePdfTests` varre o backend atrás de um
segundo `write_pdf()`. Um `write_pdf()` novo em qualquer app derruba a suíte com o nome do arquivo —
sem ele, o D73 voltaria pela porta dos fundos no próximo módulo que exportar PDF. Suíte do módulo:
**6/6**.

---

### D72 — As dependências de parse não tinham versão fixada · ✅ corrigido 09/08/2026

`openpyxl`, `weasyprint`, `pdfplumber` e `Pillow` estavam em
[requirements.txt](../backend/requirements.txt) **sem pin**. São exatamente as bibliotecas que comem
arquivo de terceiro — planilha, PDF, imagem —, e é sobre elas que se dizia "openpyxl moderno não
resolve entidade externa (XXE)": verdade sobre a versão que o pip resolveu **naquele dia**. A
superfície de ataque mudava sozinha entre dois builds, e o gate de CVE do CI (10.5.2) confere o que
**foi** resolvido, não o que será.

Pinadas nas versões que a imagem roda e que a suíte provou — `Pillow==12.3.0`, `openpyxl==3.1.5`,
`weasyprint==69.0`, `pdfplumber==0.11.10` —, e **não** nas mais novas que existem: pinar numa versão
não medida seria trocar um risco por outro. Subir qualquer uma passa a ser mudança deliberada, que
quebra no CI e não no upload do cliente.

**Um achado de tabela junto:** `pandas` está no requirements e **nenhum `.py` do backend o importa** —
quem lê planilha é o `openpyxl`, em `funcoesimpexp/formatos/leitura.py`. Ficou sem pin de propósito,
com a constatação registrada no próprio arquivo: congelar peso morto não é higiene. A pergunta certa
— se ela sai da imagem — é de quem for medir o tamanho do build, e está anotada como tal.

---

### D70 — `/media/` servia ASO, holerite e nota fiscal sem token · ✅ corrigido 09/08/2026

O gateway proxeava `/media/` para o backend e o Django serve mídia sob `DEBUG`
([config/urls.py:234](../backend/config/urls.py)) — em produção, 404, correto. **No stack de dev onde
os E2E rodam, com `DEBUG=True`, o arquivo era baixável sem token**, fora de auth, entitlement e RLS.
É o **S10** outra vez, o mesmo que a PRA.2 recusou repetir quando tirou a leitura da Prancheta de
`/media/`.

**O alcance era maior do que o achado dizia.** Ele foi escrito sobre os XLSX do impexp; o
levantamento de 09/08 varreu todo `upload_to` do backend e encontrou 13 prefixos, entre eles
`asos_funcionarios/`, `holerites/`, `carteiras_trabalho/` e `documentos_funcionarios/`. ASO é **dado
de saúde** (LGPD art. 11), e nenhum desses caminhos carrega tenant — então nem o isolamento entre
clientes sobrevivia. Agravante de implantação: o default é `DEBUG:-True` em quatro serviços do
[base.yml](../deploy/compose/base.yml), e o único arquivo que o vira é o `prod.yml`, declarado
esqueleto **não validado**.

**E não era só um buraco de gateway: era um desvio do mascaramento.** A ficha do funcionário resume o
achado inteiro numa linha — o serializer mascarava `cpf` por falta de `rh.cpf.view` e o **mesmo
JSON** entregava a URL do PDF da carteira de trabalho, onde o CPF está em claro. O mesmo valia para o
salário e o holerite. A máscara protegia o campo e o arquivo passava por baixo dela.

**Primeira metade (09/08, manhã): o padrão foi invertido no gateway.** `location /media/` passou a
`return 404` nos dois arquivos ([unified](../infra/gateway/nginx.unified.conf),
[staging](../infra/gateway/nginx.staging.conf)), com uma **allowlist nomeada** dos nove prefixos que
ainda não tinham porta. Fechou `impexp/` e `prancheta/` (os dois já tinham endpoint gateado — eram
porta dos fundos de porta construída) e fez `upload_to` novo **nascer fechado**.

**Segunda metade (09/08): os nove prefixos ganharam porta, e a allowlist morreu.** Nove `upload_to`
em seis apps, agrupados por **gate** e não por app — um `Recurso` tem um conjunto de permissões, e
juntar ASO com RG trocaria em silêncio o gate do prontuário médico:

| Recurso | Prefixos | Gate de entrega |
| --- | --- | --- |
| `rh.documentos` | `carteiras_trabalho/` · `documentos_funcionarios/` | `rh.documento.view` |
| `rh.aso` | `asos_funcionarios/` | `rh.dado_medico.view` |
| `rh.holerite` | `holerites/` | `rh.folha.view` |
| `cadastro.documento_cliente` | `documentos_clientes/` | `cadastro.cliente.view` |
| `obra.documento` | `documentos_obras/` | `obra.obra.view` |
| `obra.diario_midia` | `diario_obra_media/` | `obra.diario.view` |
| `obra.custo_nfe` | `nfe_xmls/` (custo do empreendimento) | `obra.empreend_custo.view` |
| `erp.nota_fiscal` | `nfe_xmls/` · `notas_fiscais/` (6 campos, 3 modelos) | `erp.nf.view` |

**Prefixo não é dono — modelo é**, e `nfe_xmls/` é a prova: dois apps escrevem na mesma pasta com
gates diferentes. Fechar "o prefixo do ERP" teria deixado o XML do custo do empreendimento aberto.

**Três coisas subiram para o motor**, porque nove cópias de um guarda-corpo é um guarda-corpo que
diverge (a forma do [D75](#) do lado da entrada): `url_do_arquivo`, `buscar_do_tenant` (escopo de
tenant + chave validada, que estava dentro da Prancheta) e `entregar_campo`, que concentra as três
decisões repetidas — tipo pelo mapa fechado de extensões, `RASTRO_AUDITADO` e cache `no-store`.

**O cache é `no-store` de propósito, ao contrário da Prancheta.** Lá a revisão é *write-once* e a URL
identifica o conteúdo; aqui substituir o PDF do ASO reescreve o mesmo campo sob o mesmo id. Prometer
`immutable` seria o [D51](#) com agravante de LGPD — deixar cópia de atestado de saúde no cache do
navegador de quem o abriu.

**Dois vazamentos estavam fora dos serializers**, e foram os mais fáceis de não ver: a galeria de IA
do diário e o `documento/` da NFS-e montam payload **à mão** nas views
([modulodiario/views.py](../backend/modulodiario/views.py),
[moduloerp/views.py](../backend/moduloerp/views.py)) e emitiam `arquivo.url` direto. O mixin de
serializer não os alcançava. No ERP a distinção ficou explícita: o link assinado da NFE.io continua
sendo dela e navega direto; só a **cópia local** passa pela porta.

**O frontend teve de mudar junto, e não é detalhe.** O access token vive em memória (F1), então
`<a href>` e `<img src>` chegariam sem `Authorization` e levariam 401 — o download autenticado saiu
da Prancheta e virou `lib/arquivo.ts` (`baixarArquivo`, `baixarParaDisco`, `abrirEmNovaAba`,
`useArquivoBlob`), com o componente `ImagemDoArquivo` para as miniaturas do diário. `mediaUrl` foi
**removida**, e não mantida como no-op: uma função que devolve URL que sempre dá 404 é mais difícil
de achar do que um erro de compilação. O diário passou a publicar `arquivo_nome` à parte, porque a
URL gateada não carrega mais o nome e é pela extensão que a tela decide se há miniatura.

**A regressão que impede a volta** é [test_d70_portas_de_midia.py](../backend/funcoesimpexp/test_d70_portas_de_midia.py):
ele varre todos os `FileField` dos modelos instalados e falha com o nome do campo quando um prefixo
não tem recurso declarado. É o que torna a allowlist desnecessária — o achado não foi um arquivo
aberto, foi uma lista que crescia sozinha.

**Validado no stack vivo em 09/08/2026**, com rebuild das imagens de backend e frontend (elas rodam
imagem, não código montado) e o gateway recriado — `restart` falha depois de o arquivo montado ser
reescrito, porque o bind-mount aponta para o inode antigo:

- **[d70_media_fechada_test.py](../../testes/e2e/d70_media_fechada_test.py) 26/26** — os 9
  prefixos respondem 404 pelo gateway (com e sem token: o corte é antes do Django), o documento de
  RH sobe, o JSON não traz `/media/`, a porta entrega os bytes com `attachment`+`nosniff`+`no-store`,
  e o gate corta sem token (401), sem o módulo `rh` (403) e no tenant vizinho;
- **suíte `funcoesimpexp` + `rh` + `modulodiario` 166/166**;
- **[ie_impexp_test.py](../../testes/e2e/ie_impexp_test.py) 16/16** e
  **[pra8_prancheta_test.py](../../testes/e2e/pra8_prancheta_test.py) 155/155** — a Prancheta
  seguiu intacta depois de `buscar_do_tenant` e o mapa de MIME subirem para o motor;
- **`tsc -b` limpo** no build do frontend (é ele que pega o contrato das telas: `arquivo_nome`, os
  tipos e a `mediaUrl` removida).

**O que NÃO foi medido:** o gesto no browser (clicar em "Abrir" e receber o blob). O
[d70_browser_test.py](../../testes/e2e/d70_browser_test.py) está escrito e **não roda** — faltam
as libs de sistema do Chromium no WSL. Até lá, o caminho de download no navegador está provado por
analogia com o visualizador da Prancheta, que usa o mesmo `useArquivoBlob`, e não por medição.

**Achado de passagem, fora do D70:** toda resposta do gateway carrega
`X-Content-Type-Options: nosniff` **duas vezes** — o nginx o adiciona (`add_header ... always`, Fase
5) e o Django também (`SecurityMiddleware`). É inofensivo (mesmo valor) e é anterior a esta fatia; o
`pra8` nunca o viu porque lê headers com `dict(resp.headers)`, que descarta duplicata em silêncio.
Não foi mexido aqui para não misturar um refactor de header de gateway com o fechamento de um
vazamento.

**O que ficou declarado e não resolvido:** a mídia do diário sai com `RASTRO_AUDITADO` como os outros
oito, o que grava uma linha de `AuditLog` **por miniatura carregada**. Baixar o rastro deste recurso
resolveria o volume enfraquecendo a auditoria no mesmo commit que fecha um vazamento; a saída certa é
a da Prancheta — uma miniatura gerada por nós, servida como `RASTRO_INTERNO` —, registrada como
decisão em aberto na planta do [modulodiario](modulos/modulodiario.md).

### D59 + A6 — A telemetria de task nunca gravou, e o conserto óbvio era pior que o defeito · ✅ corrigido 09/08/2026

Dois achados que só se resolvem juntos, e a ordem em que se olha para eles decide se o conserto ajuda
ou piora. O **D59** dizia que toda task Celery com UUID nos argumentos perdia o registro; o **A6**,
mais antigo, dizia que os signals gravavam 2+ linhas por task com os `args` completos e sem índice.
São o mesmo código — [nucleo/signals.py](../backend/nucleo/signals.py) — e **a correção que o D59
pedia ligava o A6**.

**O que havia.** `log_task_start` (`task_prerun`) e `log_task_end` (`task_postrun`) gravavam `args` e
`kwargs` **verbatim** num `JSONField`. Desde a Fase 8 toda task escopada por tenant recebe `tenant_id`
(um `UUID`), e `UUID` não é serializável em JSON:

```
Signal handler <function log_task_start …> raised:
TypeError('Object of type UUID is not JSON serializable')
```

O `create` estourava, o `LogAtividadeUsuario` **nunca era criado** para nenhuma delas, e o log do
worker ganhava dois tracebacks por task. A ausência de linha é indistinguível de "não houve tarefa",
então o buraco não se via — e o ruído permanente é o que treina quem opera a ignorar traceback, que é
como o próximo defeito real passa despercebido.

**Por que a correção sugerida não foi a aplicada.** O D59 propunha "um encoder que saiba UUID, ou
coagir para `str` na borda". Isso conserta o sintoma e **liga** o defeito de verdade: com o encoder, o
handler passa a *gravar* — duas linhas por task, payload livre (o `args` carrega o que o chamador
quiser), num `JSONField` sem índice, numa tabela **mutável** e **não tenant-scoped**. Ou seja, o
`tenant_id` e o que mais viajasse como argumento passariam a ser persistidos fora do escopo de tenant,
crescendo com a fila, sem teto. Hoje isso só é inofensivo porque **quebra**. É consumo sem teto, que é
defeito de produto e não incômodo local — e as duas próximas fatias da Prancheta (PRA.4, tradutor APS
assíncrono; PRA.6, sincronização de pasta) são feitas de tasks.

**O que foi feito, no sentido do A6:** uma linha por task, **na conclusão**, sem `args`/`kwargs`. O
`task_prerun` saiu inteiro. Some junto a consulta `filter(detalhes__task_id=…).latest()` que o
`postrun` fazia sobre `JSONField` sem índice a cada task — e com ela a necessidade do índice que o A6
pedia. Fica registrado o que identifica a execução (`task_id`, nome, estado) e, na falha, a mensagem
**truncada em 500 caracteres**: `str(retval)` de um retorno grande era a mesma escrita sem teto por
outra porta.

O que a task *recebeu* não é guardado em lugar nenhum deste modelo, e é deliberado: para reconstituir
execução existe o log estruturado com `request_id`/`tenant_id` (Fase 10.1), e para a trilha sensível
existe o `AuditLog`, imutável e por-tenant. O `LogAtividadeUsuario` é telemetria — o próprio docstring
dele já dizia isso — e a Fase 10 prevê aposentá-lo.

### D77 — O compose reescrevia o teto do dono e desarmava o teste que o cobrava · ✅ corrigido 09/08/2026

Achado ao revisar o WIP da Prancheta, e a forma dele é a que interessa: **o guarda-corpo existia,
estava verde, e não guardava nada**.

[deploy/compose/base.yml](../deploy/compose/base.yml), no `worker-conversao`, declarava:

```yaml
PRANCHETA_CONVERSAO_MEMORIA_MB: ${PRANCHETA_CONVERSAO_MEMORIA_MB:-1536}
PRANCHETA_CONVERSAO_SEGUNDOS: ${PRANCHETA_CONVERSAO_SEGUNDOS:-300}
```

Dois defeitos numa linha. O primeiro é a régua de 08/08 violada pelo próprio commit que a instituiu: o
número é do dono e vive em [payment/planos.py](../../payment/planos.py), e voltou a existir em arquivo
de deploy — o mesmo motivo pelo qual os tetos saíram do `config/settings.py` (quem opera a máquina lê
esse arquivo; o dono não). As duas linhas eram, ainda por cima, **redundantes**: o `settings.py` já
resolvia o default a partir do `payment`.

O segundo é o que fazia dele um defeito silencioso.
[nucleo/test_tetos_no_payment.py](../backend/nucleo/test_tetos_no_payment.py) pula a asserção quando a
variável de ambiente existe — tolerância correta para o runner —, e **o compose fazia com que ela
existisse sempre**. Dentro do contêiner o teste era no-op. Os valores batiam por coincidência de
estarem sincronizados naquele dia; mudar o número em `payment/` deixaria o contêiner no valor antigo
sem nenhum teste reclamar.

**Correção:** as duas linhas saíram (com o porquê escrito no lugar delas, para não voltarem), e o
teste ganhou `DeployNaoRedeclaraTetoTests` — que não prende estes dois nomes, e sim cobra que
**nenhuma constante escalar do `payment/planos.py`** apareça como chave de ambiente em
`deploy/compose/*.yml`. É a única varredura por nome que a régua deste arquivo admite, porque não
adivinha o que é teto: pergunta ao próprio arquivo do dono. Medido na correção: 27 constantes
escalares, 4 arquivos de compose, **zero** reincidências; e o controle positivo confirma que as duas
linhas antigas seriam pegas, sem falso positivo em `JWT_PUBLIC_KEY_PATH` e afins.

Continua permitido exportar a env no ambiente para experimentar um teto diferente. O que não se pode é
**versionar** o número num arquivo de deploy.

### D61 — Os 11 arquivos que "estouravam o orçamento" eram o orçamento errado · ✅ fechado 08/08/2026

Não houve conserto: houve **medição**. O D61 nasceu da remedição de 07/08 como decisão de produto —
11 dos 160 DWGs (6,9%) recusados por `recurso_excedido` mesmo depois de descer para `SHOW_OUTLINE`, e
a pergunta que vinha junto era comercial (*se o COGS do módulo é o cômputo, a unidade de cobrança não
deveria ser o cômputo?*). O [D76](historico-correcoes.md), achado no dia seguinte, mostrou que
aqueles 11 nunca tiveram o orçamento que o plano declarava: o `RLIMIT_AS` media o processo inteiro, e
o teto de 1.536 MB entregava **~384 MB reais**. A hipótese ficou escrita ali mesmo, como não medida.

**A remedição sob o teto corrigido, mesmo corpus** (`corpus_hash f8f5b542c6497a47`, mesmo motor,
mesmos 16 lotes) responde:

| | 07/08 | 08/08 |
|---|---|---|
| convertido | 116 | **126** |
| taxa | 72,5% | **78,8%** |
| `recurso_excedido` | 11 | **0** |
| DXF intermediário ilegível ([D43](pendencias.md)) | 21 | **22** |
| `motor_insuficiente` (a fronteira do premium) | 5 (3,1%) | **5 (3,1%)** |

Os 11 estão contados um a um: **10 convertem** e **1 apenas avançou** — passou a ler o DWG inteiro e
morreu depois, no DXF intermediário, entrando no bolso do D43. Nenhum arquivo do acervo é recusado
por orçamento. A escada da PRA.1d, que o D61 acusava de ter um degrau só, aparece agora fazendo o
trabalho dela: 2 arquivos estouraram na 1ª passada, desceram para `SHOW_OUTLINE` e converteram
declarando a hachura simplificada.

**A conversa de produto que o D61 abriu não morre — muda de tamanho.** A fronteira do premium não se
moveu (os mesmos 5 arquivos, 3,1%), então a PRA.4 segue dimensionada por RVT/NWD e pelo peso do
arquivo, e não por cobertura de DWG. O que encolheu foi a **nossa** fila: 21,2% → 15,0%.

**Junto veio um conserto no instrumento, e ele é o que impede a próxima repetição.** A passada de
07/08 rodou sem `--detalhe` e guardou só agregados: "11 estouraram" e "21 geraram DXF ilegível" eram
números **sem nome**, em log nenhum — a investigação seguinte teria de remedir o acervo inteiro só
para reencontrar a amostra. O corpus já era versionado pela lição do [D41](pendencias.md); o
resultado, não. Agora o parcial é **v2** e grava a linha de cada arquivo (balde, versão, causa,
sinais), a consolidação imprime a lista **por causa e com o dono junto**, e a subida de versão
**recusa somar** parciais de antes do D76 — dois orçamentos diferentes não viram uma taxa. Efeito
imediato: o D43 deixou de ser um número e virou uma lista de 22 caminhos.

**Validação:** `moduloprancheta` + `nucleo.test_tetos_no_payment` **300/300**; passada de 16 lotes em
**7min15s**, 3 GB/2 CPUs por lote, nenhum lote caiu. Relatório em
[ferramentas/medicao/resultado-2026-08-08.log](../ferramentas/medicao/resultado-2026-08-08.log); leitura completa
na [planta §4.1](modulos/moduloprancheta.md).

### D76 — O orçamento de memória media o PROCESSO, não a operação · ✅ corrigido 08/08/2026

Achado ao rodar o `ie_impexp_test.py` no stack vivo: o job de importação morria com *"passou do limite
de 1024 MB de memória do plano contratado"* em um arquivo de **4000 linhas**. O número do plano não
estava errado — a **unidade** estava.

`teto_de_memoria` arma `RLIMIT_AS`, que limita o **espaço de endereçamento virtual do processo
inteiro**, não o que aquela operação alocou. Num processo de vida longa, tudo o que Django, psycopg2 e
os leitores de planilha reservaram **antes** do orçamento já conta. Medido no stack:

| Processo | VA já reservada | RSS real | Teto que o plano armava | Folga |
| --- | --- | --- | --- | --- |
| `sgi-worker` | 1152 MB | ~110 MB | 1024 MB (`profissional`) | **negativa** |
| `sgi-erp` (gunicorn) | 1491 MB | ~180 MB | 256 · 512 · 1024 · 1536 | **negativa em todos** |
| `sgi-worker-conversao` | 1152 MB | ~225 MB | 1536 MB (setting) | ~384 MB |

Os quatro degraus de `impexp_memoria_mb` estavam **todos** abaixo da linha de base: a importação
estava morta para todo tenant, em todo plano, nos dois caminhos. A Prancheta não caiu junto por dois
acidentes — o teto dela é maior que a base, e a parte cara roda em **subprocesso** (`dwg2dxf`), que
nasce com o espaço zerado. O limite estava honestamente declarado no docstring (*"VA reservada não é
memória usada"*); o que não se viu é que a base já passava de 1 GB.

Não foi a PRA.5a: o `orcamento()` na importação é do IE.3, escrito no mesmo dia e nunca rodado no
stack — a mesma raiz do [D75](historico-correcoes.md), código provado em Python puro e não no sistema de pé.

**Correção (três partes):**

1. **O teto passou a somar a linha de base** — `_va_do_processo_mb()` lê `VmSize` de `/proc/self/status`
   (a mesma grandeza que o `RLIMIT_AS` governa) e o limite vira `base + orçamento`. Com isso "512 MB"
   passou a significar *"esta operação pode alocar 512 MB"*, que é o que o plano vende. Fora do Linux
   devolve 0 e cai no comportamento antigo, que é o conservador. Provado no container: base 1268 MB →
   `RLIMIT_AS` 1780 MB; 200 MB alocam, 900 MB levantam `MemoryError`.
2. **A cópia divergente sumiu.** `moduloprancheta/limites.py` tinha o **original** desta função (o
   D57 a escreveu, o D63 a promoveu à fundação) e ficou com a cópia local, que não recebeu a correção
   — o teto de 1536 MB entregava ali ~384 MB reais. Agora delega para `nucleo.orcamento`. A
   **tradução** continua no módulo: o `RecursoExcedido` da conversão é da taxonomia dos motores
   (`ErroDeConversao`, com `retentavel` e fila própria no cockpit), e trocá-la mudaria o cockpit.
   Mecanismo compartilhado, vocabulário de cada módulo — que era a intenção da promoção.
3. **A terceira frota ganhou teto de container.** O D57 deu `mem_limit` à conversão, o D71 à frota
   geral, e sobrou justamente a que atende o cliente: o `erp`, onde roda o caminho **síncrono** do
   impexp, corria contra o host inteiro (47 GB). Agora `mem_limit: 3g`, pela invariante do D71 —
   1 worker gunicorn × 2.048 MB (`IMPEXP_TETO_INFRA_MEMORIA_MB`) ≈ 2,3 GB de pico legítimo, e o freio
   que sabe explicar estoura antes do cgroup que só mata. Mexer em `--workers` muda a conta, e isso
   está escrito no `base.yml`.

O `teto_de_memoria` também passou a **logar** quando não consegue se armar (lição do D21: protetor
fail-open silencioso é indistinguível de um funcionando).

**Validação:** suíte 1058/1058 exceto os 4 do D50; `ie_impexp_test` **16/16** (4000 linhas aplicadas
e desfeitas, que era o teste morto); **PRA.8 138/138** e **PRA.3b TODAS OK** — as duas frotas que
mudaram de mecanismo seguem verdes.

**A hipótese que ficou aberta aqui foi medida no mesmo dia, e confirmou-se inteira:** o **D61** (11
arquivos estouram o orçamento mesmo no degrau de hachura) tinha sido apurado quando o teto de 1536 MB
entregava ~384 MB reais. Remedido o corpus sob o teto declarado, **nenhum** arquivo é mais recusado
por orçamento — 10 convertem e 1 passou a falhar mais adiante, no D43. Relato acima.

### D75 — A porta da Prancheta decidia o formato pelo **nome** do arquivo, e o impexp já provou que isso não se faz · ✅ corrigido 08/08/2026

Achado em 08/08/2026 ao levantar as portas de entrada de arquivo para a PRA.5. A plataforma tem
**duas** portas de upload com guardas divergentes, e a divergência é exatamente o defeito que o
[D65](historico-correcoes.md) fechou de um lado só:

O quadro abaixo é o **estado que originou o achado** (antes da PRA.5a); a coluna da direita descreve
um arquivo que já não existe. Fica porque é ele que explica por que a régua mudou:

| | `funcoesimpexp` ([limites.py](../backend/funcoesimpexp/limites.py)) | `moduloprancheta` (`uploads.py`, removido em 08/08) |
| --- | --- | --- |
| Como decide o formato | **assinatura de bytes** (allowlist); o sufixo só desempata entre formatos-zip | **extensão do nome** ([formatos.py:170](../backend/moduloprancheta/formatos.py)) |
| Teto | `impexp_max_mb` por plano (5–50 MB, infra 100) | `min(formato.max_mb, 300)` |
| Orçamento de recurso | `orcamento()` do [D63](historico-correcoes.md) | não tem |
| Conferência / desfazer | R1 e R6 | grava direto |

O D65 registrou a razão nas próprias palavras: *"sufixo é dado do atacante: `payload.exe` renomeado
para `.xlsx` entrava pela porta, era gravado em disco e só falhava ao ser parseado"*. Na Prancheta
isso continua verdade — `payload.exe` renomeado para `.dwg` passa `validar_arquivo`, é **gravado**
como `RevisaoDocumento.arquivo`, conta storage e é entregue ao **LibreDWG**, que é parser em C rodando
no worker. É a pior metade do par: o impexp entrega bytes ao `openpyxl`; aqui entregam-se a três
binários compilados.

**A defesa que existe hoje, e por que não basta:** a entrega ([entrega.py](../backend/moduloprancheta/entrega.py))
serve tudo com `nosniff` + `attachment`, então o navegador não executa nada — isso fecha o vetor do
*cliente*, não o do *servidor*. E o argumento do docstring de `formato_da_extensao` é legítimo mas
incompleto: ele descarta o **Content-Type** (que o cliente controla, e que CAD não registra), o que
está certo, e conclui pela extensão — quando DWG (`AC10..`), PDF (`%PDF-`) e IFC (`ISO-10303-21`) têm
assinatura, e DXF/DXB são texto verificável.

**Não é 🔴 porque exige conta autenticada, com o entitlement `prancheta` e a permissão de escrita** —
não é porta anônima. Mas é a porta que mais convida: o módulo aceita 20 formatos, até 300 MB, e o
plano `sob_medida` aceita todos.

**A correção é a diretiva do dono (08/08/2026):** o `funcoesimpexp` é a **porta única** de arquivo e
se adapta a cada tipo de importação; toda outra entrada sai e passa para ele. Então isto não se
conserta copiando a allowlist para a Prancheta — seria a terceira cópia do mesmo guarda-corpo, e
[nucleo/orcamento.py](../backend/nucleo/orcamento.py) já foi promovido à fundação por esta razão
exata. Virou a **R17** da régua ([planta §2](modulos/funcoesimpexp.md)).

**Andamento (08/08/2026, 2ª entrada): a porta saiu; falta a validação no stack.** A **PRA.5a**
removeu o `moduloprancheta/uploads.py` — o arquivo não existe mais. A entrada da revisão passa por
[`funcoesimpexp/entrada.py`](../backend/funcoesimpexp/entrada.py), os 18 formatos com assinatura
verificável foram registrados na allowlist da plataforma
([formatos.py](../backend/moduloprancheta/formatos.py)) e o que sobrou virou
[planos.py](../backend/moduloprancheta/planos.py), que só declara o que se vende. Provado em
Python puro, sobre a porta montada: `payload.exe` renomeado para `.dwg` → **400**; texto renomeado
para `.nwd` → **400**; RVT verdadeiro (OLE2) fora do plano → **402**, com o CTA; IFC de 400 MB →
**402**, com o teto. A porta é em camadas e as duas camadas seguraram — a detecção crua devolve `csv`
para qualquer texto, e quem barra é o recurso declarando o que aquele destino aceita.

**Andamento (08/08/2026, 3ª entrada): validado no stack vivo — e a validação achou o que faltava.**
Os itens 1 e 3 abaixo estão **fechados**; o 2 é a PRA.5b e segue aberto. Números da rodada: suíte
**1058 testes, 4 erros — todos o [D50](pendencias.md#d50)**, anterior e sem relação; `moduloprancheta` +
`funcoesimpexp` **386/386**; **PRA.8 138/138** no stack vivo pelo gateway.

**O que só apareceu com o sistema de pé** (nenhum destes é achado novo de desenho — são as arestas
que a PRA.5a deixou por não ter rodado, todas corrigidas nesta entrada, relato em
[historico-correcoes.md](historico-correcoes.md)):

- **a suíte da Prancheta não importava.** `formatos.formato_da_extensao` foi removido pela PRA.5a — o
  ponto da fatia — e `tests.py` continuou a importá-lo: **254 testes apagados** desde a manhã, sem
  ninguém ver. Foi ele quem escondeu os dois seguintes;
- **as três recusas da porta saíam como 500.** O `admitir` levanta exceção **comum** de propósito (a
  mesma porta roda no worker, fora de HTTP) e documenta que *quem chama traduz* — e o serializer da
  revisão não traduzia. O gate de plano virava erro de servidor em vez da parede comercial com o CTA;
- **o `.bcfzip` perdeu o endereço.** A recusa genérica da porta única lista os formatos aceitos, que é
  a resposta errada para um formato de **interoperabilidade**: o arquivo não está errado, a rota está.
  `FormatoDesconhecido` passou a carregar o formato detectado para o módulo poder apontar a porta certa;
- **a extensão composta deixou de valer.** `nuvem.copc.laz` passou a ser detectado como `las`: LAS e
  COPC dividem a assinatura `LASF`, e a porta única olhava só o último segmento do nome. A regra
  existia no `formato_da_extensao` e não veio junto na mudança — é a única que não sobreviveu a ela.
  Sem efeito comercial hoje (nenhum plano explícito vende os dois), mas grava o rótulo errado;
- **o E2E estava desatualizado desde a PRA.1c**, e por isso não teria pego nada disso: `calibrar`
  mudou de `revisoes/{id}` para `desenhos/{id}` (a régua é da folha) e batia em **404** — que se
  parecia com o 403 esperado —, a fila do cockpit foi de 7 para 9 contagens na PRA.1b, e a saída do
  arquivo mudou para `/api/impexp/` na própria PRA.5a. Os três eram mudanças legítimas com asserção
  velha; onde a asserção fixava um número (`len(fila) == 7`) ela virou o **conjunto** nomeado.

**Continuou 🟠 aberto por um item só, até a PRA.5b:**

2. **Sobraram duas portas de upload no módulo** (PRA.5b): o snapshot do ponto de vista e o
   `marcacoes/importar-bcf/`. Nenhuma das duas entrega binário a parser em C — o `.bcfzip` vai para o
   nosso leitor de zip —, então o risco é bem menor que o do LibreDWG, mas continuam sendo porta.

Fechou com a **PRA.5b**.

**Fechado (08/08/2026, 4ª entrada): a PRA.5b tirou as duas portas que restavam — e construiu o
lote.** O item 2 acima está resolvido, e com ele o achado inteiro. Não sobrou upload de arquivo no
`moduloprancheta` fora do `funcoesimpexp`.

| Porta | O que ela fazia | O que faz agora |
| --- | --- | --- |
| Snapshot do ponto de vista ([views.py](../backend/moduloprancheta/views.py), `ponto-de-vista/`) | `request.FILES` direto em `PontoDeVista.snapshot`, com uma conferência de tamanho à mão. **O formato nunca foi olhado** | `entrada.admitir` pelo recurso `prancheta.marcacao` — assinatura de bytes, teto do recurso, e o lugar por onde o antivírus entra (D74) |
| `marcacoes/importar-bcf/` | formato pelo nome; teto de entrada era o orçamento de **descompressão** (200 MB) usado como se fosse teto de upload | `entrada.admitir` com o teto do registry (50 MB, o pacote como chega). O orçamento de descompressão continua dentro do `bcf.ler`, medindo o que ele vira ao abrir |

**A metade que o achado não previa e que a fatia entregou:** a **carga em lote** do acervo histórico.
O `prancheta.acervo` ganhou `aplicar_linha`/`desfazer_linha` e virou o **primeiro consumidor real** do
caminho `preparar_arquivos → conferir → aplicar → desfazer` do IE.3, que até aqui só tinha um recurso
de teste. A pasta do projetista entra inteira, a plataforma adivinha **disciplina, código e revisão**
do caminho ([taxonomia.py](../backend/moduloprancheta/taxonomia.py)), e nada toca o acervo antes do
sim — R1 e R6 valendo sobre bytes.

**Três coisas que a fatia acertou por já saber o preço de errá-las:**

- **a tradução das recusas virou um arquivo, não uma quarta cópia.** O D75.1 mostrou o custo de ela
  morar dentro do serializer: quando as três recusas saíam como 500, saíam nos três casos de uma vez,
  porque havia um lugar só. Com três chamadores, copiá-la seria repetir a forma do próprio D75 do lado
  de dentro — daí o [porta.py](../backend/moduloprancheta/porta.py), que também é quem sabe apontar a
  **porta certa** (um `.dwg` no importar-BCF ouve "suba como revisão", e não a lista de formatos);
- **o teto do snapshot é do recurso, não do formato.** `imagem` no acervo é prancha escaneada (25 MB);
  na marcação é recorte de tela, e o teto é o mesmo `MAX_SNAPSHOT_BYTES` que já valia para o snapshot
  vindo **dentro** do `.bcfzip`. Um número só faria os dois caminhos do mesmo dado divergirem — que é
  exatamente como a extensão composta se perdeu no D75.1;
- **o lote copia os bytes em vez de apontar para eles.** `revisao.arquivo.save(...)` e não
  `arquivo = ...`: atribuir o `FieldFile` da conferência copiaria só o nome do caminho, e a limpeza da
  área de conferência — que o `aplicar` agenda logo em seguida — apagaria o arquivo do acervo. O
  sintoma seria trezentas revisões com download 404, e só em produção.

**Uma decisão ficou registrada como limite consciente** na [planta §12](modulos/moduloprancheta.md),
e não é defeito: a **obra do lote é escolhida, não adivinhada** — a conferência ainda não corrige
linha a linha, e obra errada põe a planta de um prédio no canteiro de outro.

**E uma segunda virou regra do projeto no mesmo dia.** Ao fechar a fatia ficou apontado que o teto do
snapshot era constante de engenharia em `bcf.py`, e que isso fazia a recusa por tamanho — sempre
**402** — oferecer *"faça upgrade do plano"* quando nenhum plano vendia um recorte de tela maior. A
resposta do dono foi categórica: **todo teto ou limite vive em `payment/`**. Mudaram de casa, para
[payment/planos.py §5.3](../payment/planos.py): os **MB por formato** (que eram campo do registry de
engenharia, escritos ao lado da assinatura de bytes), o teto do snapshot e os três da leitura de BCF
(descomprimido, XML, tópicos). O `Formato.max_mb` virou propriedade que lê de lá, e a linha entre os
dois arquivos ficou mais nítida — `formatos.py` diz o que a plataforma **sabe fazer** com o formato,
`payment/` diz o que ela **vende** dele. Caiu junto um número duplicado que a própria nota do
`IMPEXP_TETO_INFRA_ARQUIVO_MB` dizia ter sido eliminado e não tinha: `TETO_UPLOAD_DIRETO_MB` repetia
os mesmos 300 MB no módulo, e virou alias.

A varredura do resto do módulo achou mais quatro, e o padrão delas é o mesmo — **o teto estava onde o
argumento que o justifica não estava**:

| Teto | Onde estava | O que o próprio comentário já dizia |
| --- | --- | --- |
| memória e relógio de UMA conversão | `config/settings.py` | são os gêmeos de `IMPEXP_TETO_INFRA_MEMORIA_MB`/`_SEGUNDOS`, que já moravam em `payment/`. `settings.py` é arquivo de **deploy** — o dono não o abre |
| folhas por arquivo (`MAX_DESENHOS`) | `motores/dxf.py` | *"cada desenho vira um arquivo no storage… e a conta de armazenamento seria do dono"* — se a conta é dele, o número é dele |
| elementos tesselados de IFC (`TETO_ELEMENTOS`) | `motores/ifc.py` | *"não é limite de plano"*, dizia. É COGS de **tempo** de worker compartilhado, e a decisão respondeu isso: `payment/` guarda inclusive o teto que ninguém compra, porque é lá que ele é visto |

Os dois de conversão **continuam sobrescritíveis por variável de ambiente**: apertar o orçamento numa
VM pequena é operação, não produto — o que mudou é de onde sai o padrão.

**A regra é do projeto, não do módulo** — e a segunda passada, pedida na mesma conversa, varreu o
repositório inteiro. Fora da Prancheta havia limite em mais seis lugares: o teto de upload do caminho
genérico do `nucleo`, os **dois cortes síncrono×job** do motor (a R10), a antecedência máxima de um
lembrete de calendário, o tamanho da lista de notificações, a profundidade da explosão de composição
de preço, e o `page_size`/`max_page_size` de **nove paginadores** — este último é limite dos dois
lados, porque sem `max_page_size` um `?page_size=100000` transforma qualquer listagem numa exportação
sem a auditoria da R12 nem o "acesso total ou nada" da R11.

**Nove e não seis, e o erro do meio vale registro** porque é o mesmo de sempre: a primeira varredura
de paginadores saiu com `| head -12` e a lista foi truncada em seis. Os três que ficaram de fora —
`modulomaps`, `clientes` e o paginador de Unidade, que é **classe solta dentro do `views.py` do
`empreendimentos`** e não um `pagination.py` — só apareceram na conferência final. É a razão de o
teste guardião listar módulo → `arquivo:Classe` explicitamente em vez de descobrir por nome de
arquivo: a busca que acha "o padrão" é a que perde o caso fora do padrão.

**O que ficou de fora, e por quê.** A régua tem fronteira: número que não diz *até onde alguém vai*
não é limite, é fato. Constante física (`RAIO_TERRA_M`, `SRID`), largura de campo (`max_length`),
parâmetro de parsing (a janela de 180 caracteres em torno do CEP), TTL de cache de CEP e a janela de
reentrega **da Meta** no WhatsApp continuam onde estão. A lista está escrita na §5.6 do `planos.py`
para a varredura não se repetir — e a regra inteira virou linha em [CLAUDE.md](../CLAUDE.md).

Quem impede a volta é [`backend/nucleo/test_tetos_no_payment.py`](../backend/nucleo/test_tetos_no_payment.py),
com 10 testes que prendem cada ponto conhecido. **Deliberadamente não varre o repositório atrás de
números**: heurística sobre literal acusaria constante física e largura de campo, e teste que grita
errado é desligado na terceira vez.

**Validação final:** suíte **completa** do backend **1.102 testes, 4 erros — todos o
[D50](pendencias.md#d50)**, anterior e sem relação (a chave pública do S8); e **PRA.8 155/155** pelo
gateway, com a frota inteira (`erp` + `worker` + `worker-conversao` + `beat`) reconstruída, e não só o
`erp` — eles rodam imagens próprias do mesmo Dockerfile e estavam com código anterior.

**Validado no stack vivo, e é onde a 1ª versão do E2E encontrou o próprio erro:** o lote mandava o
mesmo DXF que a seção 4 já subira naquela obra, e voltou `duplicada` — a idempotência por `hash`
funcionando. Virou verificação explícita em vez de amostra corrigida em silêncio. Números:
`moduloprancheta` + `funcoesimpexp` **418/418** (eram 386; 32 testes novos) e **PRA.8 155/155** pelo
gateway, com a seção 15 cobrindo as três entregas.

### D75.1 — As cinco arestas da PRA.5a que só a primeira execução no stack mostrou · ✅ corrigido 08/08/2026

A PRA.5a (porta única de arquivo) foi escrita e provada em **Python puro**, sobre a porta montada. Ao
subir a imagem e rodar de fato — suíte + `pra8_prancheta_test.py` pelo gateway —, cinco coisas
apareceram de uma vez. Nenhuma é defeito de desenho da fatia; são o custo de não ter rodado.

**A que escondia as outras:** `moduloprancheta/tests.py` continuava importando
`formatos.formato_da_extensao`, removido pela própria PRA.5a — remover a decisão por extensão *era* a
fatia. O módulo inteiro falhava no import, e com ele **254 testes** deixaram de existir sem que nada
ficasse vermelho de um jeito que se lesse. Com o import restaurado, a suíte foi de 133 para 386 testes
e três falhas reais apareceram atrás dele:

1. **As três recusas da porta saíam como 500.** `entrada.admitir` levanta exceção **comum** de
   propósito — a mesma porta roda no worker, onde `APIException` não significa nada — e o docstring
   declara que *quem chama traduz*. O `RevisaoSerializer` não traduzia: `FormatoNaoContratado` (402
   com o CTA), `ArquivoGrandeDemais` (402 com o teto) e `FormatoDesconhecido` (400) viravam erro de
   servidor. O gate comercial existia e não chegava ao cliente. **Correção:** tradução no serializer,
   reusando o 402 que o módulo já sabia montar ([planos.py](../backend/moduloprancheta/planos.py) —
   é ele que carrega `formatos_aceitos` e `plano`), mais `ArquivoAcimaDoTeto` com o mesmo corpo que o
   `funcoesimpexp/views.py` devolve, para a tela tratar "passou do teto" de um jeito só.
2. **O `.bcfzip` perdeu o endereço.** A recusa da porta única lista os formatos aceitos — resposta
   errada para um formato de **interoperabilidade**: o arquivo não está errado, a rota está, e mandar
   o cliente procurar entre formatos de desenho o que ele já tem é chamado de suporte.
   **Correção:** `FormatoDesconhecido` passou a carregar o formato detectado (`formato=`), e a
   Prancheta usa `interop` do registry para responder "importe por marcações → importar BCF".
3. **A extensão composta deixou de valer.** `nuvem.copc.laz` virou `las`: LAS e COPC dividem a
   assinatura `LASF`, e `detectar_formato` olhava só o último segmento do nome (`.laz`). A regra
   existia no `formato_da_extensao` e foi a única que não veio junto na mudança. **Correção:**
   `_extensao_casada` em [limites.py](../backend/funcoesimpexp/limites.py) — entre os candidatos que a
   assinatura aprovou, ganha o de extensão declarada **mais longa**. Sem efeito comercial (nenhum
   plano explícito vende os dois), mas gravava o rótulo errado na revisão.

**E os E2E estavam desatualizados desde a PRA.1c** — por isso não teriam pego nada acima. Três
asserções velhas sobre mudanças legítimas, no `pra8_prancheta_test.py`: `calibrar` migrou de
`revisoes/{id}` para `desenhos/{id}` (a régua é da **folha**, desde que uma revisão passou a trazer
várias) e devolvia **404**, que se parecia com o 403 esperado; a fila do cockpit foi de 7 para 9
contagens quando a PRA.1b partiu "conversão que falhou" por **quem age**; e a saída do arquivo virou
`/api/impexp/…` na própria PRA.5a. Corrigidas as três — e onde a asserção fixava um número
(`len(fila) == 7`) ela passou a fixar o **conjunto nomeado**, que é o que tem significado: um contador
quebra sem dizer o que mudou.

O **`pra3b_escala_test.py` estava inteiro do lado errado da mesma mudança** — lia a escala da revisão
(que já não a carrega) e calibrava na rota velha, recebendo a página de 404 do gateway como se fosse
resposta da API: 5 falhas. Migrado para a folha, inclusive relendo a **lista** de desenhos depois do
reprocessamento em vez de reusar o id — quem cria e apaga folha é o motor, e é justamente por a
reconversão poder refazê-la que o teste existe. Verde: `$INSUNITS=4` (mm) → 1,02 m de largura,
calibração humana soberana sobre a reconversão. O `pra1d_hachura_test.py` **não foi rodado** (é a
carga pesada do §4.6).

As amostras de teste que diziam RVT sem o ser (`b"nao importa o conteudo"`, `b"0" * 512`) ganharam
cabeçalho **OLE2** real — item 3 do [D75](historico-correcoes.md). Passavam porque o nome decidia; agora um
arquivo que se diz RVT e não é recebe recusa (400), não parede comercial (402), e o E2E provoca os
dois casos com o mesmo nome de arquivo e bytes diferentes.

**Validação:** suíte 1058 testes com 4 erros (todos o **D50**, anterior); `moduloprancheta` +
`funcoesimpexp` 386/386; **PRA.8 138/138** no stack vivo pelo gateway. A mesma rodada descobriu o
**D76** (orçamento de memória do impexp), que ficou em [pendencias.md](pendencias.md) por ser decisão
de produto.

### S1 — Vazamento entre tenants (dashboard ERP + views de NF) · ✅ corrigido 04/07/2026 (pontual)

`ERPDashboardView`, `AtualizarStatusNFView` e `ConsultarStatusNFView` eram `APIView` puras — não
usavam o `TenantScopedViewSetMixin`, logo **não filtravam por tenant nem armavam a RLS**. O
dashboard somava valores de **todos** os tenants; as views de NF liam/gravavam NF de qualquer
tenant por `id`.
**Correção (pontual):** novo `TenantScopedAPIViewMixin` em [nucleo/tenancy.py](../backend/nucleo/tenancy.py)
— arma a RLS em `initial()` e expõe `scope_qs()`; as três views herdam e escopam cada queryset →
cross-tenant some do somatório do dashboard e vira 404 nas NF. Vale em SQLite e Postgres. Testes:
`moduloerp/tests.py::S1TenantIsolationAPIViewTests` (3).
**Parte estrutural (S2) resolvida em 04/07/2026** — ver abaixo.

### S2 — RLS fail-open · ✅ corrigido 04/07/2026 · Fase 8.4

A política RLS (`nucleo/migrations/0007`) **liberava todas as linhas** quando `app.current_tenant`
não estava setado — e só o mixin o setava. Qualquer caminho fora dele (APIView, comando, shell,
task, webhook) rodava sem proteção, silenciosamente.
**Correção (entregue):** (a) contexto armado na **classe de autenticação** (`IamJWTAuthentication`),
não em middleware — o tenant vem do JWT resolvido em `initial()`, dentro da transação do
`ATOMIC_REQUESTS`; um middleware Django clássico veria `AnonymousUser` e rodaria fora da transação.
Assim **toda** requisição autenticada arma o contexto, mesmo views que não herdam o mixin (a brecha
do S1). (b) política **fail-closed** (`nucleo/migrations/0011`): sem contexto → 0 linhas; só passa
quem bate o `tenant_id` **ou** liga o bypass explícito `app.rls_bypass='on'` (superusuário/webhook/
migração/job, via `arm_rls_bypass()`/`rls_bypass()`). O role `erp_app` não é superuser nem BYPASSRLS
e as tabelas estão em `FORCE ROW LEVEL SECURITY`, então a política vale de fato; migrações/jobs
cruzam tenants sob o role `postgres` (BYPASSRLS) ou `rls_bypass()`. Webhook do Asaas e o comando
`analisar_divergencias_asaas` ajustados para armar o contexto. **Provado em Postgres**: sessão sem
contexto vê/insere 0 linhas; tenant A não enxerga B; bypass vê tudo (`nucleo/test_rls_fail_closed.py`,
pulado no SQLite). **Resta da Fase 8:** rodar a suíte inteira sobre Postgres (8.1 — hoje muitos
testes criam linhas via ORM sem contexto e quebrariam sob fail-closed), `tenant` NOT NULL (8.2) e
uniques por-tenant (8.3).

### S10 — Vazamento entre tenants nas filhas do drone · ✅ corrigido 04/07/2026 · Fase 8.5

No funcoesODM (Java), os recursos-filhos sob `/api/v1/projects/{projectId}/...` eram escopados
**só por `projectId`**: os serviços carregavam o projeto por `findById` **sem conferir o tenant**
(`MeasurementService`/`AnnotationService.validateProject` só checavam existência, e os controllers
não tinham guard). Um usuário do tenant A que passasse o `projectId` do tenant B **lia e gravava**
medições/anotações/chunks/tasks daquele projeto. As entidades-filhas também não tinham coluna de
tenant (isolamento apenas transitivo).
**Correção (Fase 8.5):** `tenant_id` **NOT NULL** nas 6 filhas (herdado do projeto na criação) +
`ProjectTenantInterceptor` na borda — todo `/api/v1/projects/{projectId}/**` exige que o projeto da
URL pertença ao tenant do token, senão **404** (não vaza existência). Endurece de quebra o
`update`/`delete` do próprio projeto (antes só o dono por username) e barra anexo de imagem
cross-projeto em `addImagesToChunk`. Provado por [phase8_tenancy_test.py](../testes/e2e/phase8_tenancy_test.py)
(2º tenant `acme` no seed). **Correlato revisado em 10.8 (15/07/2026):** `/api/v1/chunks/*/assets/*` segue
`permitAll` (download público por UUID) **por desenho** — o visualizador Potree/GeoTIFF carrega os assets por
URL simples, sem header de auth; o UUID opaco é a proteção. Mantido; endurecer exigiria token de asset
assinado (fora de escopo).

### S3 — Fallback HS256 com segredo compartilhado · ✅ corrigido 12/07/2026

Sem `JWT_PUBLIC_KEY_PATH`, IAM e backend caíam em HS256 com o mesmo `JWT_SECRET` — quem valida também
**assina**: qualquer serviço (ou `.env` vazado) forjava tokens de qualquer usuário/tenant.
**Corrigido (12/07):** fora de DEBUG o backend **exige** RS256 (`JWT_PUBLIC_KEY_PATH`) e a IAM exige a
privada (`JWT_PRIVATE_KEY_PATH`) — chave ausente → `ImproperlyConfigured` no boot; HS256 só com
`DEBUG=True`. Provado: prod sem chave não sobe; com chave sobe em `RS256`. **Gate no CI (14/07):** o job
backend roda `check --deploy` em modo produção (RS256 efêmera). **Resta (Fase 10):** validação via
JWKS + `kid` (rotação sem redeploy).

### S4 — Defaults inseguros ligados por omissão · ✅ corrigido 12/07/2026

`DEBUG=True`, `SECRET_KEY` e `JWT_SECRET` tinham fallback embutido (backend e IAM): produção sem as
variáveis **subia silenciosamente** com stack traces expostos e segredos conhecidos.
**Corrigido (12/07):** `DEBUG`/`IAM_DEBUG` default = **False**; helper `_config` **falha-rápido**
(`ImproperlyConfigured`) se `SECRET_KEY`/`ALLOWED_HOSTS` faltarem fora de DEBUG (o `JWT_SECRET` só vive
no ramo HS256/dev, coberto pelo S3); bloco de produção liga `SESSION/CSRF_COOKIE_SECURE`, HSTS e
`nosniff` (`SECURE_PROXY_SSL_HEADER` atrás do gateway). **Corrigido (14/07):** `manage.py check --deploy`
é gate no CI (job backend, modo produção + RS256 efêmera, `--fail-level WARNING`; só `security.W008`/SSL-redirect
silenciado — TLS no gateway).

### L1 — Calendário 500 em toda listagem · ✅ corrigido 03/07/2026

`modulocalendar/views.py` filtra `DiarioObra.objects.filter(usuario=...)` — o campo real é
**`criado_por`** → `FieldError` → todo `GET /api/calendar/events/` responde 500. Adjacentes: os
eventos locais são serializados **sem `id`** (impossível editar/excluir no front) e os feriados
só do ano de `start` (range dez→jan perde o ano seguinte).
**Correção:** `criado_por=request.user`; incluir `id` no `values()`; iterar
`range(start.year, end.year+1)` nos feriados; adicionar o smoke test de 1 linha que pegaria isso.

### L2 — Dead Letter Queue nunca grava · ✅ corrigido 03/07/2026

Dois defeitos: `FailedTask.task_id` é `PositiveIntegerField` mas o id do Celery é **UUID string**
(o create sempre falha e o `except` engole); e o hook é registrado como
`on_failure=handle_failed_task.s()`, assinatura incompatível com o protocolo do Celery. Falha
permanente (ex.: cobrança Asaas que esgotou retries) desaparece sem rastro.
**Correção:** `task_id = CharField(max_length=36, unique=True)`; registrar via
`link_error=handle_failed_task.s()` (assinatura `(request, exc, traceback)`) ou `BaseTask` com
`on_failure`; teste que força falha e verifica a linha na DLQ.

### L3 — NF emitida sem tenant e sem documento do tomador · ✅ corrigido 03/07/2026

`_emitir_nf_para_conta_receber` cria a NF **sem `tenant`** (nasce `NULL` e some das listagens
escopadas) e monta o payload com `getattr(cliente, 'cpf'/'cnpj', '')` — campos que não existem
(o real é **`cpf_cnpj`**) → documento sempre vazio; endereço vai sem cidade/UF/CEP.
**Correção:** `tenant=conta.tenant` no create; usar `cliente.cpf_cnpj` + endereço completo.
**Regra geral:** objeto criado fora de `perform_create` herda `tenant` explicitamente do pai.

### L4 — Integração `funcoeslead` ↔ backend morta · ✅ corrigido 03/07/2026 (Fase 11.2 antecipada)

O serviço Node autentica com `Authorization: Token …`; desde a Fase 6 o backend só aceita **JWT da
IAM** → tudo recebe 401. Agravante: os ViewSets do CRM não configuram `filter_backends`, então os
filtros da agenda (`assigned_to_id`, `due_date__gte`…) seriam ignorados mesmo autenticado.
**Correção recomendada:** antecipar a **Fase 11.2** (conversão de lead vira signal handler Python
em `modulocrm` — o problema desaparece por construção). Alternativa de curto prazo: JWT de serviço
emitido pela IAM + `DjangoFilterBackend`/`filterset_fields` no `InteractionViewSet`.

### D1 — Callbacks Node→backend usam o Token morto · ✅ corrigido 16/07/2026 (IA 14/07 + WhatsApp 15/07 + NF 16/07 absorvidos) · Fase 11

`funcoesia` (`services/apiService.js`), `funcoesnf` (`config.js`) e `funcoeswhatsapp`
(`services/apiClient.js`) usam o `DJANGO_API_TOKEN` legado — análise de IA, atualização de status
de NF e o bot recebem 401. **Confirmado por teste** (`nucleo/test_legacy_token.py`): todos os
endpoints-alvo exigem JWT da IAM e respondem 401 ao header `Token` (o `/api/log-interno/` também,
então nem o log central recebe os eventos). O `funcoeslead` saiu da lista: absorvido (L4).
**Correção:** Fase 11 (absorção em Python, caminho preferido) ou JWT de serviço (Fase 10.8).
**Progresso (14/07/2026 — Fase 11.3):** o **`funcoesia`** foi absorvido — a análise de IA virou a Celery
task Python `analisar_documento_ia` (lê a imagem in-process e chama a LLM local; não há mais callback
Node→backend com `Token`). **Progresso (15/07/2026 — Fase C.0–C.3):** o **`funcoeswhatsapp`** foi
absorvido — app Django `funcoeswhatsapp` com webhook (HMAC da Meta) + Celery, escrevendo **in-process**
(sem `Token`, sem auto-HTTP): fluxos diário/lead pelo ORM sob `tenant_context`. **O servidor Node do
WhatsApp foi removido (fatia C.4, 15/07/2026)** — sem resíduo Node no `grep`. **E2E validado 15/07/2026**
pelo gateway ([phaseC_whatsapp_test.py](../testes/e2e/phaseC_whatsapp_test.py), 13/13). **Progresso
(16/07/2026 — Fase 11.1):** o **`funcoesnf`** foi absorvido — emissão/consulta de NFS-e viraram Celery
tasks Python ([moduloerp.tasks](../backend/moduloerp/tasks.py)) que falam REST direto com a NFE.io
([nfe_client.py](../backend/moduloerp/nfe_client.py)); as views não chamam mais `localhost:3003` e o Node +
bridge PHP foram removidos. **Sem callback `Token` restante** → D1 fechado. **Falta:** só credencial NFE.io
real + E2E no stack vivo (validação sob demanda).

### D2 — Boleto Asaas emitido no cliente errado · ✅ corrigido 04/07/2026

Relatado por usuário: criou um `Cliente` novo e ao gerar cobrança o boleto saiu no nome de um
cadastro **pré-existente** no Asaas ("EEGM"), não no cliente do sistema ("Edison Goes").
Duas causas em `funcoescobrancas`: (a) `client.buscar_customer_por_cpf_cnpj` com documento vazio
fazia `GET /customers?cpfCnpj=` → o Asaas ignora o filtro vazio, devolve a **conta inteira** e o
código adotava `dados[0]`; (b) `garantir_customer_asaas` reusava qualquer customer com o mesmo
CPF/CNPJ **sem conferir o nome** e confiava cegamente no `id_cliente_gateway` salvo (já contaminado).
**Correção:** trava de identidade — nunca emitir para cadastro cujo **nome + CPF/CNPJ** não bata
com o cliente. `buscar_customer_por_cpf_cnpj` retorna `None` sem documento e confere o `cpfCnpj`
do candidato; nova `validar_cliente_para_cobranca` (leitura pura) roda **síncrona na view**
(`gerar-cobranca` → `409` com mensagem ao usuário, sem enfileirar) e também dentro de
`garantir_customer_asaas`; CPF igual + nome diferente vira bloqueio (provável digitação, comparação
tolerante a acento/caixa/espaço); `tasks.criar_cobranca` trata `CobrancaBloqueada` como falha
permanente (sem retry, registrada na DLQ); UI destaca o motivo no Sheet da conta. Testes:
`funcoescobrancas/tests.py` (12). Ver [modulos/funcoescobrancas.md](modulos/funcoescobrancas.md#trava-de-identidade--nunca-emitir-para-cadastro-divergente).

### D3 — UI e dashboards do ERP não sincronizam estado após criação/baixa · ✅ corrigido 13/07/2026

Ao criar um `Cliente`, ele não entra imediatamente no fluxo de cobrança até recarregar a página (browser);
ao gerar boleto, as divergências/pêndencias entre Asaas e banco/ERP não aparecem da mesma forma quando coloco em criar cliente;
os gráficos de custos e recebimentos do ERP não carregam ou ficam defasados; e, após clicar em
dar baixa, o boleto continua sendo exibido como `emitido` como se a mudança não tivesse sido
aplicada.
**Corrigido (12/07/2026):** (a) **boleto preso em `emitido` após baixa** era comportamento do backend —
só o handler do webhook Asaas marcava o boleto `PAGO`; a baixa **manual** não propagava. `ContaReceber.dar_baixa`
(choke point único) passou a marcar os boletos vinculados como `PAGO` quando o título fica `QUITADO`
(estados terminais `PAGO`/`CANCELADO` preservados) — `moduloerp/tests.py::D3BaixaPropagaBoletoTests` (3).
(b) o invalidador de contas a receber no front (`useContasAReceber`) passou a invalidar também `boletos.all`,
para o badge do boleto atualizar sem refresh. (c) **cliente novo não entrava na cobrança** — os selects de
entidade do ERP (`useEntityOptions`) cacheavam por 5 min e os cadastros vivem em outro módulo (não
invalidam esse cache); agora revalidam no mount (`refetchOnMount: 'always'`).
(d) **gráficos "não carregam"** — o hub `/api/erp/dashboard/` exige `erp.relatorio.view`, permissão que só
existia em `diretoria`/`financeiro`/`auditor`; personas com o módulo ERP mas sem ela (`tesouraria`, `fiscal`)
recebiam **403** → KPIs vazios + gráficos sem dados. `erp.relatorio.view` concedido a `tesouraria`/`fiscal`
no catálogo ([iam/identity/catalog.py](../iam/identity/catalog.py); `sync_authz` aditivo propaga no boot).
Admin de tenant já passava (bypass do `RequirePermission`). Testes: `moduloerp/tests.py::D3DashboardPermissionTests` (3)

+ `identity/tests.py::…relatorio_financeiro_visivel_aos_papeis_de_dinheiro`.
  (e) **rótulo do mês** do fluxo de caixa vinha como timestamp ISO cru (`TruncMonth` sem serializer) — o front
  passou a formatá-lo como `jul/2026` (`mesToBR` em [utils/dates.ts](../frontend/src/utils/dates.ts)).
  (f) **divergências Asaas × ERP inconsistentes entre as telas** — ao criar cliente havia um painel proativo
  (lista global banco × Asaas), mas ao **gerar boleto** o bloqueio só surgia reativo (409) depois do clique.
  Padronizado: o botão "Gerar cobrança" abre um **dialog de confirmação** ([GerarCobrancaDialog](../frontend/src/modules/erp/components/GerarCobrancaDialog.tsx))
  com opção de **ver as divergências** (mesmo painel, agora componente compartilhado
  [DivergenciasAsaasPanel](../frontend/src/modules/clientes/components/DivergenciasAsaasPanel.tsx)); confirmação
  dispara a cobrança (o 409 de bloqueio segue valendo). **Falha silenciosa corrigida:** quando a auditoria não
  roda (Asaas fora/sem permissão), as duas telas avisam "não foi possível verificar agora" em vez de painel
  vazio (falso "tudo certo"). **LGPD:** o relatório expunha CPF/CNPJ em texto puro fora do mascaramento 9.C —
  agora `divergencias-asaas` mascara o documento para quem não tem `cadastro.cliente_doc.view`
  ([nucleo/field_masking.mask_document_unless](../backend/nucleo/field_masking.py)). Testes:
  `funcoescobrancas/tests.py::AnalisarDivergenciasTests` (máscara com/sem permissão).
  **Fechado (13/07/2026, junto do F4):** a degradação amigável do hub para quem não tem `erp.relatorio.view` — o
  `ErpDashboardPage` detecta o **403** e vela só os indicadores consolidados (aviso âmbar, permissão nomeada),
  mantendo os atalhos de workspace; o banner de erro vermelho cru sobrou só para falhas reais de carga.
  **Correção de escopo (13/07/2026):** o painel de divergências banco × Asaas foi **removido do formulário Novo
  Cliente** ([ClienteForm](../frontend/src/modules/clientes/components/ClienteForm.tsx)) — o cadastro-base é
  escopo de dados pessoais, não de cobrança. A auditoria de divergências é escopo financeiro (ERP): passou a viver
  (a) sob demanda no [GerarCobrancaDialog](../frontend/src/modules/erp/components/GerarCobrancaDialog.tsx) na hora de
  emitir, e (b) num **botão-alerta permanente no hub do ERP**
  ([DivergenciasErpButton](../frontend/src/modules/erp/components/DivergenciasErpButton.tsx)) — colorido como alerta
  com a contagem quando há divergências, abrindo um modal com os dados (mesmo `DivergenciasAsaasPanel`). **Gate LGPD +
  escopo:** é dado financeiro com PII de cliente, então exige as DUAS permissões de **usuário** — `erp.cobranca.view`
  (ver cobranças) **e** `cadastro.cliente.view` (acesso aos clientes); `hasModule` **não** basta (é entitlement do
  tenant, não do usuário — um `operacional` num tenant com ERP não deve ver). Reforçado no **backend**
  ([clientes/views.py::divergencias_asaas](../backend/clientes/views.py)): checagem explícita de `erp.cobranca.view`
  além do `cadastro.cliente.view` do viewset; regressão em `funcoescobrancas/tests.py` (operacional → 403). O
  documento segue mascarado sem `cadastro.cliente_doc.view`. Isso reverte, de propósito, a duplicação do item (f).

### S5 — Bypass de entitlement no CRM · ✅ corrigido 04/07/2026 · Fase 9.B

`OpportunityProductViewSet` só tinha `IsAuthenticated` — tenant sem o módulo `crm` acessava
`/api/crm/opportunity-products/`. **Correção:** o viewset ganhou `RequireModule("crm")` +
`RequirePermission` (`required_resource="crm.oportunidade_produto"`); os demais viewsets do CRM já
herdavam de `BaseCrmViewSet` (agora com `RequireModule`+`RequirePermission`). Testes em
[modulocrm/tests.py](../backend/modulocrm/tests.py)::`S5EntitlementCrmTests` (sem módulo→403; com
módulo sem permissão→403; com permissão→200) — validados na lógica; execução DRF aguarda o Postgres.

### S6 — Rotas do `funcoeslead` sem autenticação · ✅ resolvido 03/07/2026 (serviço descomissionado — absorvido na Fase 11.2)

O serviço tem o middleware `iamAuth` mas **não o aplica**; quem alcança a porta 3004 executa
ações com o token de serviço. **Correção:** aplicar `requireModule('crm')` nas rotas; rede Docker
interna sem porta publicada; segredo dedicado por serviço nas chamadas internas.

### S7 — Segredos de serviço fracos · ✅ corrigido 14/07/2026

`IA_SERVICE_SECRET_TOKEN` tinha fallback público no código; o token do webhook Asaas era comparado
com `!=` (não constante). **Corrigido (14/07):** `IA_SERVICE_SECRET_TOKEN` passou pelo `_config`
(fail-fast fora de DEBUG, sem fallback público — o valor de dev nunca vale como segredo real) e os
4 usos em [funcoesia/views.py](../backend/funcoesia/views.py) leem `settings.IA_SERVICE_SECRET_TOKEN`
direto (sem `getattr` com default que ressuscitasse o token público); webhook Asaas
([funcoescobrancas/views.py](../backend/funcoescobrancas/views.py)) agora usa `hmac.compare_digest`
(tempo constante) e segue fail-closed sem token configurado. Passthrough da var no `docker-compose.yml`
(erp/worker/beat) e no gate `check --deploy` do CI; documentada no `.env.example`. Testes
`funcoescobrancas/tests.py::WebhookAsaasTokenTests` (4).

### L5 — Corrida na baixa (sem lock de linha) · ✅ corrigido 12/07/2026 *(v01-B3)*

`dar_baixa` fazia read-modify-write sem `select_for_update`, com dois produtores reais concorrentes
(baixa manual × webhook Asaas) — um sobrescrevia o `valor_pago` do outro.
**Corrigido (12/07):** ambos os `dar_baixa` (`ContaPagar`/`ContaReceber`) passaram a rodar dentro de
`transaction.atomic()` travando a linha do título (`select_for_update().get(pk=...)` + `refresh_from_db()`)
antes do read-modify-write; efetivo no Postgres (no-op no SQLite, que não é mais suportado). Prova de
consistência em `moduloerp/tests.py::IntegridadeFinanceiraBaixaTests` (baixas sequenciais acumulam).

### L6 — Edição de título não revalida consistência · ✅ corrigido 12/07/2026

`PATCH` podia reduzir `valor` abaixo de `valor_pago` (saldo negativo); rateios existentes não eram
revalidados quando só o `valor` mudava; a baixa aceitava valor **maior** que o saldo.
**Corrigido (12/07):** `_validar_edicao_valor` nos serializers de `ContaPagar`/`ContaReceber`
(novo total devido ≥ `valor_pago`; se o valor muda sem reenviar rateios, os existentes têm de
continuar fechando) e guard de **overpay** no `dar_baixa` — baixa que excede o saldo é represada em
`RevisaoBaixa` (mesma filosofia do guard de título já quitado/cancelado), não aplicada. Testes cobrem
os três casos (saldo negativo, rateio quebrado, baixa em excesso → 202).

### L7 — `Transacao.data_transacao = auto_now_add` · ✅ corrigido 12/07/2026 *(v01-B5)*

A data real do pagamento (inclusive a do webhook Asaas) não ia para o ledger → fluxo de caixa mensal
no mês errado. **Corrigido (12/07):** `Transacao.data_transacao` deixou de ser `auto_now_add` e virou
a data de **competência** (`default=timezone.now`), gravada por `dar_baixa` a partir da data da baixa
(`_data_baixa_para_datetime`); o carimbo imutável de lançamento no sistema migrou para o novo campo
`data_lancamento` (`auto_now_add`). Migration `moduloerp/0011`. Teste confirma competência = data do
pagamento, não "hoje".

### A1 — Celery sem executor no deploy · ✅ corrigido 12/07/2026 · Fase 10

O compose não tinha serviços `worker`/`beat` — em produção as tasks enfileirariam para sempre.
**Corrigido (12/07):** serviços `worker` (`celery -A config worker`, com healthcheck `inspect ping`)
e `beat` (`celery -A config beat`, dispara o `CELERY_BEAT_SCHEDULE` — hoje o lembrete de tarefas do
CRM) adicionados ao `docker-compose.yml` (perfil `full`), reusando a imagem do backend. A stack `full`
passou a rodar **assíncrona de verdade**: `CELERY_TASK_ALWAYS_EAGER=False` por padrão no `erp`/`worker`/
`beat` (antes o `erp` rodava eager por `DEBUG=True` e o worker ficaria ocioso). Validação E2E do fluxo
enfileirado depende de subir o compose (Docker).

### A2 — Microsserviços fora do compose + URLs fixas · ✅ corrigido 16/07/2026 · Fase 11 *(v01-B4)*

`funcoesnf`/`funcoeswhatsapp` não estavam no `docker-compose.yml` e o backend os chamava em
`localhost:300x` fixo (o `funcoeslead` foi absorvido — Fase 11.2). **`funcoeswhatsapp`** foi absorvido como
app Django (Fase C.0–C.4, 15/07/2026) — webhook vira rota do backend + worker Celery; Node removido.
**`funcoesnf`** foi absorvido (Fase 11.1, 16/07/2026) — emissão/consulta de NFS-e viraram Celery tasks que
chamam a NFE.io direto ([nfe_client.py](../backend/moduloerp/nfe_client.py)); sem `localhost:3003`, Node +
bridge PHP removidos. Nenhum microsserviço Node com URL fixa restante no backend → A2 fechado (o worker de
`funcoesia` já era in-process). **Fase 11.4 concluída 16/07/2026:** diretório Node do `funcoeslead` excluído
e resíduo Node do `funcoesia` limpo — zero `.js` no backend.

### A3 — Uniques por tenant + `tenant` NOT NULL · ✅ corrigido 04/07/2026 · Fase 8.2/8.3 *(v01-B1/B6)*

Unicidade global (CPF/CNPJ, e-mail, nº NF) impedia dois tenants de cadastrarem o mesmo documento e
`tenant` nullable era furo de isolamento. **Corrigido:** `tenant` **NOT NULL** (8.2) + cada
`unique=True` global escalar virou `UniqueConstraint(fields=["tenant", …])` (8.3), com validador DRF
escopado ao tenant (400 limpo em duplicata).

### A4 — Upload sem validação server-side · ✅ corrigido 14/07/2026 *(v01-B2)*

Tipo/tamanho só eram validados no cliente — POST direto à API subia arquivo de qualquer tipo/tamanho.
**Corrigido (14/07):** [nucleo/upload_validation.py](../backend/nucleo/upload_validation.py) —
`resolve_upload_config(tenant)` (fonte única compartilhada com o `ConfiguracaoUploadView`, mesma
precedência tenant→global→padrão) + `UploadValidationMixin` que valida tamanho e tipo de todo
FileField/ImageField escrito no serializer (só quando há upload novo; Content-Type genérico cai para
checagem de extensão, não confia só no header). Aplicado aos serializers com upload: `obras`
(DocumentoObra), `clientes` (DocumentoCliente), `modulodiario` (DocumentoDiario), `rh`
(Funcionario/ASO/Documento/Folha), `empreendimentos` (CustoEmpreendimento). Testes
`nucleo/test_upload_validation.py` (6).

### D3 — `tenant` obrigatório no POST quebra a criação via API · ✅ corrigido 11/07/2026

Regressão da **Fase 8.2** (`tenant` virou NOT NULL): o DRF passou a **exigir `tenant` no payload**,
mas o `perform_create` do `TenantScopedViewSetMixin` injeta o tenant **depois** do `is_valid()` → todo
`POST` de recurso tenant-scoped cujo serializer usa `fields='__all__'` **sem** `read_only_fields=['tenant']`
responde **400 "tenant é obrigatório"** (o front não envia tenant). Descoberto ao criar cargo/funcionário.
**Corrigido (11/07):** serializer-base `TenantReadOnlyFieldMixin` em
[nucleo/tenant_validators.py](../backend/nucleo/tenant_validators.py) — força `tenant` read-only quando
exposto (no-op se o modelo não tem `tenant`); dobrado dentro do `TenantScopedUniqueSerializerMixin`
(todo serializer que já o usava ficou coberto de graça) e exposto como base pronta
`TenantScopedModelSerializer`. Varredura sistêmica concluída: `read_only_fields=['tenant']` nos
serializers `__all__` remanescentes de **moduloerp** (Boleto/Transacao/CobrancaCliente), **empreendimentos**
(ContaBancaria), **obras** (Obra/Etapa/Documento), **modulocrm** (Interaction/OpportunityProduct/
Opportunity/Contact), **modulocalendar**, **moduloapi** e **funcoesia** (RH/clientes/fornecedores já tinham).

### D4 — `RequirePermission` é fail-open com `permissions` vazia · ✅ corrigido 11/07/2026

Como a autenticação sempre setava `iam_permissions = [...] or []`, não havia como distinguir "token legado
sem a claim" de "usuário sem nenhuma permissão" — e o fallback de transição (`permissions` vazia → cai
no `RequireRole`) **liberava** quem não tem papel exigido em endpoints sem `required_role`.
**Corrigido (11/07):** a autenticação passou a distinguir claim **ausente** → `iam_permissions = None`
(token legado → fallback por papel, zero-downtime) de claim **presente porém vazia** → `[]` (era das
permissões → checagem estrita, conjunto vazio **nega**). `RequirePermission` só cai no `RequireRole` quando
`iam_permissions is None` ([nucleo/permissions.py](../backend/nucleo/permissions.py),
[nucleo/authentication.py](../backend/nucleo/authentication.py)). Fecha o fail-open sem quebrar o fallback
legado (provado: `S5EntitlementCrmTests`, `RequirePermissionRHTests`). O `RequireRole` some de vez na fatia **E**.

### D5 — Cadastros-base sem camada 2 (broken access control) · ✅ corrigido 11/07/2026

Relatado por teste do usuário: `semdrone` (papel **operacional**, só `cadastro.cliente.view`)
**criou e editou clientes e criou uma "venda"** (`ClienteEmpreendimento`) — só não viu o CPF (mascarado
pela 9.C). Causa: a **fatia B** (`RequirePermission`) só fora aplicada a **RH e CRM**; os cadastros-base
(`clientes`, `fornecedores`, `obras`, `empreendimentos`) tinham apenas `IsAuthenticated` → qualquer papel
escrevia. O mascaramento de campo protege o **campo**, não a **operação** de escrita.
**Corrigido (05/07):** `RequirePermission` + `required_resource` em todos os viewsets de `clientes`
(`cadastro.cliente`/`cadastro.cliente_banco`), `fornecedores`, `obras` (`obra.obra`) e `empreendimentos`
(`obra.empreendimento`/`empreend_conta`/`empreend_custo`). Provado: `semdrone` vê (200) mas não escreve
(403); `demo` (comercial/engenharia) cria normalmente. `modulodiario` já tinha ABAC próprio
(`PodeModerarDiario`). **Concluído (11/07):** a fatia B foi fechada em todo o backend —
`moduloerp` migrou de `RequireRole("financeiro")` para `RequirePermission` nos 14 viewsets/APIViews,
com os verbos de domínio (baixa, cobrança, emissão de NF, lote de remessa, resolver revisão) gateados por
permissão específica via novo `action_permission_map` do `RequirePermission`; `modulocalendar`
(`calendario.evento`), `moduloapi` (`plataforma.integracao`) e `funcoesia` (`ia.analise.view`/`.executar`,
inclusive os proxies FBV) ganharam camada 2. Template `financeiro` recebeu `erp.lote_remessa.*`
(órfão no catálogo). Suíte 71/71 verde. **Deploy sem passo manual:** o `sync_authz` ficou **aditivo**
(soma as permissões do modelo aos papéis de fábrica sem apagar ajustes do admin; `--reset` para
realinhamento explícito) e roda `--all-tenants` no boot do IAM (CMD do Dockerfile), propagando o catálogo
e o `lote_remessa` automaticamente. Usuários pegam a permissão nova no próximo **refresh** do token
(tempos vigentes em [acesso-e-permissoes.md §5.2](acesso-e-permissoes.md)).

### D7 — Janela de acesso residual do access token stateless · ✅ corrigido 13/07/2026 (backend+IAM+drone, E2E validado)

Access token é validado só por assinatura+`exp`. Após trocar/resetar senha ou desativar um usuário,
o access **já emitido continuava válido até expirar** — blacklistar o refresh só impede a *renovação*.
Reprodução: senha do `demo` trocada, sessão seguiu ativa (inclusive **gravou** conta a pagar) até o F5.
**Correção:** access TTL 15→**5 min** + **revogação imediata por época no Redis** — a IAM carimba
`sess:revoked_after:<uid>` (DB 2) em troca/reset de senha e desativação; o `IamJWTAuthentication` do backend
rejeita access com `iat` anterior (fail-open + circuit breaker se o Redis cair). Desenho e trade-offs:
[acesso-e-permissoes.md §5.1](acesso-e-permissoes.md). **E2E backend+IAM validado 13/07/2026** (revogação
imediata ~40 ms; fail-open permite / fail-closed nega; carimbo sobrevive a restart com AOF). **Drone
replicado 13/07/2026** (`SessionRevocationService` no `JwtAuthenticationFilter`, mesmo Redis/DB2/chave,
fail-open + breaker, testes de decisão 7/7). Os 3 Node ficam para a Fase 11 (sem rota de usuário na
borda). **E2E do drone validado no stack vivo** (imagem Java rebuildada): token com módulo drone → 200;
carimbo no Redis DB2 → mesmo token **401**; relogin (iat>carimbo) → 200. **Falta:** nada — D7 fechado.

### F1 — Sessão expira sem refresh + sem 401 global · ✅ corrigido 11/07/2026 (junto da Fase 10.6)

O access token valia 60 min e o front não usava o refresh; 401 não deslogava nem redirecionava.
**Corrigido (11/07):** ciclo de sessão completo (ver **Fase 10.6** no roadmap) — access token
**em memória** + **refresh em cookie HttpOnly** renovado em silêncio; interceptor de resposta
(`attachAuth`) trata 401 → `/auth/refresh/` → retry; refresh **proativo** (~1 min antes de expirar) →
nenhuma requisição falha; bootstrap na carga chama `/auth/refresh/` (cookie) e repopula a sessão sem
relogar. **Validado ao vivo pelo gateway (:8090):** login (cookie 636 B,
sem refresh no corpo) → refresh (rotaciona, access com claims) → reuso do refresh antigo = 401
→ logout = 401. IAM 19/19; React e drone rebuildados e no ar (compilaram limpo). Refresh mínimo (só
`user_id`+`sst`/`rem`) p/ caber no limite de cookie; claims só no access.
*(Os TTLs citados na versão original desta entrada — 15 min / 12h / 30d — eram os de 11/07 e ficaram
defasados; tempos vigentes em [acesso-e-permissoes.md §5.2](acesso-e-permissoes.md).)*

### F5 — `.gitignore` engole `frontend/src/lib/` — o frontend não builda em clone limpo · ✅ corrigido 26/07/2026

A linha 13 do `.gitignore` da raiz (`lib/`, padrão de virtualenv Python) casa também com
**`frontend/src/lib/`**. Os dois arquivos de lá nunca foram commitados: `queryClient.ts` (o
`QueryClient` único do TanStack Query, importado por `main.tsx`) e `utils.ts` (usado pelo diário).
Na máquina de quem escreveu eles existem, então nada acusa; num **clone novo ou worktree** o
`tsc`/`vite build` quebra em `Cannot find module './lib/queryClient'`. Confirmado por
`git check-ignore -v frontend/src/lib/queryClient.ts` → `.gitignore:13:lib/`.
**Corrigido:** `lib/`/`lib64/` **ancorados** na raiz (`/lib/`, `/lib64/` — diretório de build do
Python é sempre da raiz, ancorar não perde nada) e os dois arquivos versionados. Mesma lição já
registrada no bloco "Virtual Environment" do `.gitignore`, que aprendeu isso com o `deploy/env/`:
padrão de diretório sem âncora casa **qualquer nível**. Verificado que a âncora não destapa mais
nada — os outros dois `lib/` da árvore (`ImgDrone/`, worktree do `.claude/`) são ignorados por
regra própria.

### F6 — `package-lock.json` do frontend fora de sincronia · ✅ corrigido 26/07/2026

`npm ci` falha com `EUSAGE`: faltam do lock os 6 pacotes `@fullcalendar/*` (6.1.21) e `preact`, que
estão no `package.json`. Como o gate de CI roda `npm ci` bloqueante (Fase 12), ele não passa.
Há também conflito de peer dep (`@hookform/resolvers` 5.4.3 exige `valibot ^1.0.0`, resolvido para
0.39.0) — hoje só contornável com `--legacy-peer-deps`.
**Corrigido:** lock regenerado (4936 → 5077 linhas, os 6 `@fullcalendar/*` de volta) e `npm ci`
provado limpo — 294 pacotes, **sem** `--legacy-peer-deps`, tanto no Node 20 (versão do CI) quanto no
22 (versão da imagem). Duas partes do achado envelheceram: **`preact`** saiu do `package.json`, e o
conflito de **`valibot`** dissolveu-se quando o projeto passou a usar `zod` (o `@hookform/resolvers`
v5 declara os validadores como peers *opcionais*) — não havia o que decidir.
**A causa raiz era outra, e foi fechada junto:** o `frontend/Dockerfile` rodava
`npm install --legacy-peer-deps`, que **reresolve tudo e ignora o lock**. Por isso o defeito viveu 7
dias sem sintoma — a imagem buildava e só o CI quebrava. Trocado por `npm ci`, que falha quando o
lock divergir; é o que a Fase **10.4.1** já declarava ("`npm ci` + lockfile obrigatório nos
Dockerfiles/CI") e não valia para o frontend. Imagem rebuildada e validada.

### F7 — Rotas de administração sem guard de `is_tenant_admin` · ✅ corrigido 26/07/2026

Em [App.tsx](../frontend/src/App.tsx), `admin/papeis` e `admin/usuarios` têm o comentário
"guardado por `is_tenant_admin`", mas **não há guard na rota** — só a sidebar trava o link. URL
digitada direto entra na tela (a API barra depois, mas a UI já montou). O RH, na mesma página, usa
`<ModuleRoute module="rh">` corretamente.
**Corrigido:** [`AdminRoute`](../frontend/src/components/AdminRoute.tsx) — irmão do `ModuleRoute`,
mesmo formato (layout route com `<Outlet/>`, `AccessNotice` na negativa, estado de `loading` para não
piscar a tela de acesso negado antes de a sessão resolver). A diferença de critério é a que importa e
está no docstring: o `ModuleRoute` pergunta o **entitlement do tenant**, o `AdminRoute` pergunta o
**papel do usuário**. As duas rotas de `admin/` passaram a viver dentro dele.

### F8 — Item "Início" travado na sidebar · ✅ corrigido 25/07/2026

`AppSidebar` marcava `implemented: false` no item Início, que virava `<span>` com cadeado — mas
`/app/dashboard` é a rota-índice e a página existia. O usuário aterrissava na home e não conseguia
voltar a ela depois de navegar. **Corrigido** junto da reconstrução do hub (F.1).

### F17 — Vender lote e emitir carnê andavam na permissão de editar cadastro · ✅ corrigido 26/07/2026

Relatado pelo usuário ("falta authorization em AquisicaoForm — qualquer um pode vender lote?").
`ClienteEmpreendimentoViewSet` declarava `required_resource = "cadastro.cliente"`: pelo contrato do
`RequirePermission`, escrita exigia `cadastro.cliente.edit` — **a mesma permissão de corrigir o
telefone de um comprador**. Quem podia editar cadastro podia registrar uma venda (tirando a unidade
da praça) e, como os `@action` não tinham `action_permission_map`, também **gerar o carnê**, criando
`ContaReceber` no ERP. Ato comercial e ato financeiro atrás de uma permissão de cadastro.
**Corrigido:** três permissões novas na IAM (`cadastro.venda.view`/`.edit`/`.gerar_carne`), o viewset
passou a `required_resource = "cadastro.venda"` com `action_permission_map` (`simular` → `.view`,
porque cotar é anterior a fechar; `gerar_parcelas` e `corrigir` → `.gerar_carne`), personas ajustadas
(**comercial** vende mas não emite; **financeiro** emite; tesouraria/diretoria só leem) e a ficha do
cliente passou a gatear os botões por `hasPermission`. `sync_authz --all-tenants` (aditivo) aplicado.
Testes `PermissaoDeVendaTests` (5).

### F18 — Carteira: "Agrupar por" e todos os filtros vazios (endpoint em 500) · ✅ corrigido 26/07/2026

Relatado pelo usuário. `views.py:521` (`CarteiraOpcoesView`) ainda lia
`aquisicoes.values_list('quadra')` — campo que o **F16** moveu de `ClienteEmpreendimento` para
`Unidade`. `FieldError` → `GET /api/clientes/carteira/opcoes/` respondia **500** → `opcoes` ficava
`undefined` no React e `dimensoes = opcoes?.dimensoes[visao] ?? []` esvaziava o painel. Não era só o
agrupamento: empreendimentos, quadras, cidades, UF e anos vinham vazios pela mesma resposta. Todo o
`carteira.py` já havia sido migrado para `unidade__quadra`; só esta linha ficou.
**Corrigido:** `unidade__quadra`. Verificado ao vivo pelo gateway — 200 com os 16 agrupamentos.

### F19 — Condição de pagamento era rótulo decorativo, e vinha depois do plano · ✅ corrigido 26/07/2026

Relatado pelo usuário. No `AquisicaoForm`, **Condições de pagamento** estava na linha 489 — depois de
entrada, parcelas, juros, balões e do painel de simulação inteiro — e **não gateava nada**: vender
"À Vista" ainda pedia sistema de amortização, juros ao mês e prazo. O campo só aparecia em filtro,
admin e display; nenhuma linha de backend o lia para calcular.
**Corrigido:** a condição virou a **primeira** pergunta depois da unidade e passou a reger o
formulário (`PLANO_DA_CONDICAO`: à vista e permuta sem plano; bancário e cartão só com sinal;
direto e outro com tudo), limpando o que a condição anterior deixou. A regra vive no **motor**
(`plano_pagamento.montar(a_vista=…)`), não na tela, para o simulado e o gravado não divergirem — à
vista vira parcela única na data da compra, sem juros nem prazo. Os balões ganharam o nome de
mercado (**parcelas anuais/intercaladas**). Testes `CondicaoDePagamentoTests` (4).

### F20 — "Gerar parcelas" parecia ter gerado a carteira inteira · ✅ sem defeito, apurado 26/07/2026

Relatado pelo usuário ("cliquei em gerar parcelas e parece que gerou de todos os 5000 clientes").
**Não havia defeito:** `gerar_parcelas` é `detail=True`, opera sobre uma aquisição e recusa a segunda
chamada com 409. A apuração nos carimbos de `parcelas_geradas_em` mostrou 2.182 aquisições marcadas
numa rajada de 3 s (10:19:40–42 — o `semear_carteira_demo`, que já gera os carnês da carteira
semeada) e **exatamente uma** às 10:41:14, que foi o clique. As 86.010 `ContaReceber` já existiam
antes. O que enganou foi a mensagem de sucesso mandando "veja na aba Financeiro" sem dizer de qual
venda, com o ERP mostrando 86 mil linhas.
**Ajustado:** a mensagem passou a nomear a unidade, o total daquela venda e a apontar para a aba
Financeiro **do cliente**, não para o financeiro geral.

### F16 — Unidade cadastrada duas vezes na venda, sem trava contra revenda · ✅ corrigido 26/07/2026

O formulário de aquisição pedia **`Unidade comprada`** (texto livre) **e** os cinco campos da
identificação estruturada, lado a lado e independentes: nada garantia que combinassem, e o mesmo
lote entrava como "Apto 101" numa venda e "apto 101" em outra. O `unique(empreendimento,
unidade_comprada)` que deveria impedir revenda não pegava essas duas — e a unidade não tinha preço,
então o valor da compra era digitado do zero a cada venda.
**Corrigido:** a unidade virou **cadastro do empreendimento** (`empreendimentos.Unidade`, com
identificação estruturada única, preço de tabela e situação) e a aquisição só **aponta** para ela
(`unique(tenant, unidade)`); o texto livre e os campos duplicados foram removidos. A venda ganhou
plano de pagamento (desconto → entrada → Price/SAC → balões) calculado no backend, com simulação
sem gravar e geração de carnê por ato explícito. Migration destrutiva, base de dev recriada com
CPF/CNPJ **válidos** (o Asaas sandbox recusa documento com dígito verificador errado, e a base
antiga não emitiria um boleto sequer). Suíte `clientes` 69/69 sobre PG + fumaça ao vivo pelo gateway.

### F15 — Carteira: a visão "Unidades" abria como a de clientes · ✅ corrigido 26/07/2026

O seletor `Clientes × Unidades` trocava o conjunto de colunas, mas não o que a
visão promete. As preferências eram **uma só para as duas** (`sgi_carteira_clientes_v1`):
a primeira coluna continuava `Cliente` em Unidades, a ordem continuava a de nomes, e as
larguras/agrupamento de uma visão vazavam para a outra. Só 5 das 13 colunas eram
ordenáveis (as demais nem existiam em `ORDENACOES`), e `quadra`/`lote` ordenavam como
texto — o lote 10 antes do 2.
**Corrigido:** cada visão é uma planilha própria, com **coluna-âncora** (Cliente / Unidade,
sempre a primeira e congelada), ordem padrão própria (alfabética / endereço) e preferências
por visão (`sgi_carteira_clientes_v2`); **toda coluna ordena**, por clique ou pelo menu
"Ordenar por" do cabeçalho; ordem natural da unidade (quadra › lote › bloco/torre › andar ›
apto, numérica, vazio por último) com bloco/andar/apto virando colunas; ordenar por
documento passou a exigir `cadastro.cliente_doc.view` (a ordem dos CPFs vaza o CPF) e a
resposta declara `podeDocumento`; toda ordenação ganhou desempate por chave primária, sem o
qual a rolagem infinita duplicava e omitia linhas. Testes `CarteiraOrdenacaoTests` (6);
`clientes` 31/31 sobre PG.

### D8 — Tasks Celery sem contexto de tenant no worker (cobrança Asaas não gerava boleto) · ✅ corrigido 17/07/2026

Relatado pelo usuário: "Gerar cobrança" respondia 202 mas **nenhum boleto** aparecia — nem no Asaas nem
no banco. Causa (confirmada no log do worker): a task `funcoescobrancas.tasks.criar_cobranca` lia
`ContaReceber.objects.get()` **sem armar `rls_bypass`/`tenant_context`**; no worker real (Postgres, RLS
fail-closed, role `erp_app`, sem `app.current_tenant`) a linha some → `DoesNotExist` → a task morre na DLQ
antes de chamar o Asaas ou gravar o `Boleto`. Latente desde que o worker real entrou (Fase 10.9) — em dev
com `CELERY_TASK_ALWAYS_EAGER=True` rodava no request (contexto armado). **Correção:** `criar_cobranca` passou
a resolver o tenant sob `rls_bypass()` e a rodar o trabalho sob `tenant_context(tenant_id)` (mesmo padrão das
tasks de NF e do webhook Asaas). **Varredura:** mesma classe em `modulocrm.tasks.notificar_tarefas_a_vencer`
(job global de lembrete) → envolto em `rls_bypass()` (só não quebrava por ser no-op sem e-mail). `drone_sync`
recebe o `tenant_id` por argumento — ok. Testes: `funcoescobrancas.tests.TaskCriarCobrancaSemContextoTests`
(a task cria o Boleto sem request). **E2E vivo:** gerar-cobranca → worker → **Boleto no banco + boleto no
Asaas sandbox** (com URL).

### D9 — Download de PDF/XML da NFS-e vazio · ✅ corrigido 17/07/2026

Duas causas encadeadas, ao validar a emissão real: (a) a NFE.io **não** devolve `urlPdf`/`urlXml` no corpo do
invoice — os arquivos vêm dos endpoints `/serviceinvoices/{id}/pdf|xml` (302 → blob assinado público);
`nfe_client.resolver_url_arquivo` passou a seguir o 302 (com auth) e `_aplicar_retorno` baixa o blob (idempotente:
só o que falta); `data_emissao` agora vem de `issuedOn`/`createdOn`. (b) o **worker** gravava o arquivo no seu
filesystem efêmero enquanto o **erp** serve `/media/` — sem volume comum → **404**; adicionado
`media_data:/app/media` em erp/worker/beat no `docker-compose.yml`. **E2E vivo:** emitir → EMITIDA → PDF/XML
baixam pelo gateway (200, `application/pdf`/`text/xml`). Nota: a emissão de NFS-e é **assíncrona** na NFE.io
(pode ficar `PROCESSANDO` até uma consulta atribuir o número) — o botão "Consultar" resolve; um poll agendado
das NFs em PROCESSANDO fica como melhoria.

### D10 — Defeitos de modo-produção na 1ª subida greenfield do staging (Fase 10.7) · ✅ corrigido 18/07/2026

Subir o staging pela 1ª vez (DEBUG=False/RS256/TLS/Celery async, banco novo) expôs 7 defeitos que o dev
(DEBUG=True + dados pré-existentes) escondia. Todos corrigidos → `validate.sh` **6/6 verde** + **phase10_8 7/7**.

- **`worker`/`beat` sem `ALLOWED_HOSTS`** ([docker-compose.yml](../docker-compose.yml)): `settings` roda a
  fail-fast de produção no import mesmo sem servir HTTP → **crash-loop** dos dois. Adicionado `ALLOWED_HOSTS`
  aos serviços (só o `erp` tinha).
- **UUID de tenant desalinhado entre os seeds (crítico p/ greenfield):** `iam/seed_demo.py` e
  `backend/seed_demo_data.py` criavam `demo` com UUIDs **independentes**; como
  [`nucleo.authentication._sync_tenant`](../backend/nucleo/authentication.py) espelha o tenant da IAM **por id**
  (JIT), o 1º login não achava o tenant → tentava criar `slug='demo'` → **UniqueViolation → 500 em todo `/api/*`**.
  Os dois seeds passaram a derivar o id por `uuid5` do mesmo nome (demo/acme alinhados IAM×backend). Em produção
  real não há seed (JIT alinha sozinho); dev só funcionava por alinhamento histórico.
- **Parse do gate (`validate.sh`/`up.sh`):** (a) o guard `grep 'TROQUE-'` batia no comentário do cabeçalho do
  `.env.staging`; (b) `cut -d= -f2` colava o comentário inline do `GATEWAY_HTTPS_PORT` no `SGI_GW` → o `#` virava
  fragmento e **todo request caía no SPA do React** (405/200, login "FALHOU"). Corrigidos (`=TROQUE-`; extrair só o número).
- **phaseC com container de dev fixo** (`ERP_CONTAINER="sgi-erp"`): as checagens no ORM liam o banco de **dev**
  enquanto o webhook escrevia no de **staging** → `Lead count=0`. Tornado configurável (`SGI_ERP_CONTAINER`,
  exportado pelo `validate.sh` a partir do `SGI_PREFIX`).
- **rate-limit do login** (`10r/m burst=5` no gateway) estourava ao rodar os 6 E2E em sequência → **429**;
  `validate.sh` passou a espaçar as corridas (mantém o limite de produção intacto — pausa só o harness).
- **`phase10_8` com `Origin` de dev fixo** (`http://localhost:8090`): o drone recusa o handshake com **403
  antes do upgrade** quando a origem não está em `APP_CORS_ALLOWED_ORIGINS` — no staging a origem é a do
  gateway HTTPS. Tornado configurável (`SGI_WS_ORIGIN`). Com isso o 10.8 fecha **7/7** no staging (WS rodado
  de dentro da rede contra `java-service:8080`, que é onde mora a checagem do CONNECT).
- **Cosmético:** `down.sh -v` imprime "volumes persistem" mesmo tendo removido; `POSTGRES_SUPbackendASSWORD`
  (nome corrompido por rename `erp`→`backend`) é consistente entre `.env`/compose, então funciona.

### D11 — Admin não consegue resetar senha esquecida (e não há recuperação) · ✅ corrigido 18/07/2026

`redefinir-senha` exigia a senha ATUAL do alvo — justamente o que o usuário não tem quando esquece —
e não existia "esqueci minha senha", então **quem esquecia a senha ficava travado sem saída**.

**Decisão de desenho (18/07):** descartada a opção "admin redefine sem conhecer senha alguma"
(padrão de mercado — Okta/Entra/Workspace — mas rejeitada aqui por dar takeover de qualquer conta a
um admin comprometido). Caminho adotado: **recuperação por token de e-mail**.

**Achado durante a implementação — a recuperação por e-mail sozinha só MOVE o buraco.** `email` era
campo gravável no `UsuarioSerializer` sob `IsTenantAdmin`: um admin socialmente engenheirado faria
`PATCH {"email": "atacante@evil.com"}` → "esqueci minha senha" → token na própria caixa. Takeover
idêntico ao que a decisão acima quis evitar, e **pior de detectar**, porque o rastro pareceria uma
recuperação legítima feita pelo próprio usuário. Por isso a entrega inclui as travas de troca de e-mail.

**Entregue — um caminho só:**

- **Recuperação** (`POST /auth/senha/esqueci/`, público, botão na tela de login): token de uso único
  (SHA-256 no banco, claro só no e-mail), TTL 30 min, emissão nova invalida a anterior, teto de 5/hora
  por conta. Resposta **sempre genérica** (conta inexistente/inativa/em cooldown/no teto devolvem o
  mesmo corpo e status) → sem oráculo de enumeração. Consumo em `POST /auth/senha/redefinir/` encerra
  todas as sessões (`revoke_all_sessions` + `bump_session_epoch`).
- **Admin recebe AVISO, nunca o link.** Os admins do tenant são notificados de que houve o pedido —
  enxergam o que acontece e podem reagir (conta de quem saiu da empresa, rajada de pedidos) — mas não
  recebem o token. *Copiar o link para o admin foi avaliado e recusado:* o endpoint é público e sem
  autenticação, então qualquer anônimo que soubesse um username faria cair um token de takeover na
  caixa do admin, e todo admin teria takeover silencioso de qualquer conta. Supervisão sim, poder não.
- **E-mail obrigatório e único** no `Usuario` (migration `0004`, com guarda que falha com mensagem
  legível se houver vazio/duplicata). Deixou de ser dado de contato e virou infraestrutura: conta sem
  e-mail é conta sem caminho de volta; e-mail repetido torna a recuperação ambígua. Único **global**
  (decisão 18/07: a mesma pessoa não tem conta em duas empresas).
- **Troca de e-mail endurecida e ASSIMÉTRICA:** `email` saiu do PATCH genérico; agora só por
  `POST /iam/usuarios/{id}/trocar-email/`, com regra que depende de **quem é o alvo** — porque neste
  produto o admin **é o dono da empresa** (quem paga), e as contas dos funcionários existem a partir
  dele:

  - **alvo funcionário** → troca vale **na hora**, sem confirmação e **sem cooldown**. Exigir
    confirmação no endereço antigo travaria justamente o caso que motivou o D11 (e-mail digitado
    errado no cadastro, ou caixa que a pessoa não acessa mais: a confirmação iria para um endereço
    morto e ninguém nunca corrigiria). O cooldown também fica de fora de propósito — senão o dono
    corrigiria o endereço e a pessoa ainda ficaria 24 h sem recuperar. Compensações: evento na trilha
    e **aviso nos dois endereços**;
  - **alvo admin** (inclusive o próprio) → **confirma no endereço ANTIGO** e, ao confirmar, arma
    `Usuario.email_alterado_em` → **cooldown de 24 h** sem emissão de token. A conta do dono é o ponto
    único de comprometimento da empresa inteira: quem sequestrar a sessão dele não pode redirecionar
    o e-mail e, com isso, herdar a recuperação de senha de tudo.

  *Histórico: a 1ª versão exigia confirmação para todo mundo. Corrigido em 18/07 ao perceber que isso
  reintroduzia o travamento pela porta dos fundos — proteger o funcionário contra o próprio dono não é
  papel do sistema, já que ele acessa os dados da empresa por direito.*
- **Escalada de privilégio auditada:** mudança de `perfis`/`is_tenant_admin` gera evento e avisa o
  dono da conta por e-mail.
- **Trilha própria da IAM:** `EventoSeguranca` append-only (bloqueio no modelo + **trigger PostgreSQL**
  contra UPDATE/DELETE, FKs congeladas `db_constraint=False`), porque o `AuditLog` da Fase 9.E vive no
  backend e **nenhum evento de identidade era auditado em lugar nenhum** até aqui. Só metadados; e-mails
  mascarados (`e••••n@dominio`).
- **Infra:** IAM ganhou SMTP próprio (`MAIL_HOST` **obrigatório** fora de `IAM_DEBUG` — sem ele a
  recuperação aceitaria a solicitação e nunca entregaria o token) + **Mailpit** no compose (perfil
  `mail`, UI em `:8025`) como caixa de captura de dev/staging, andaime a aposentar antes do go-live.
- **Mantido:** `redefinir-senha` (admin informa a senha ATUAL do alvo) segue existindo para o caso
  presencial — não é primitivo de takeover, quem não sabe a senha do alvo não passa dali.

**Validado 18/07/2026:** suíte da IAM **69/69** + **E2E 17/17 no dev E 17/17 no staging**
(TLS + `DEBUG=False` + Celery async; o roteiro é parametrizável por `SGI_GW`/`SGI_MP`/
`SGI_IAM_CONTAINER` justamente para valer nos dois) — antes só rodava contra o dev, ver achado (d).
Detalhe do que cada corrida cobre, pelo gateway
([d11_recuperacao_senha_test.sh](../testes/e2e/d11_recuperacao_senha_test.sh), com o Mailpit como
caixa): recuperação ponta a ponta, link só na caixa do usuário e **aviso do admin sem `token=`**, uso
único, senha antiga invalidada, resposta idêntica p/ conta inexistente, PATCH não troca e-mail,
confirmação no endereço antigo, criação sem e-mail e e-mail duplicado recusados com **400 (não 500)**.

**Achados durante a implementação:**

- (a) declarar `email` no serializer descartava o `UniqueValidator` que o `ModelSerializer` geraria do
  `unique=True` → duplicata escapava e estourava `IntegrityError` (**500**); validador explícito.
- (b) o teto por hora é silencioso por desenho, então o próprio E2E esgotava a cota do `demo` ao rodar
  repetido — o script zera a cota antes de começar, sem afrouxar o limite real (mesma disciplina do
  espaçamento no `validate.sh`, ver D10). O roteiro também **restaura o ambiente ao final** (trocava a
  senha do `demo` e deixava assim).
- (c) **link morto na tela de login** (relatado pelo usuário: "não faz nada"). O `LoginPage` já tinha
  um `<a href="#">Esqueci minha senha</a>` — placeholder da época sem recuperação — e a nova entrega
  acrescentou um segundo link, vivo, em outro ponto da tela. O usuário clicou no morto. Removido o
  placeholder; sobrou **um** link. *Lição: procurar o texto no código antes de adicionar um elemento
  de UI com o mesmo rótulo (parente do F5 — duas gerações de páginas convivendo).* O E2E via `curl`
  jamais pegaria isso: exercitava a API, não a tela.
- (d) **staging não subiria** (achado antes de quebrar): lá `IAM_DEBUG=False` e o `MAIL_HOST` estava
  **vazio** — com o fail-fast novo, a IAM recusaria o boot em crash-loop. `.env.staging`/`.example`
  passaram a apontar para o Mailpit do staging (portas próprias 8026/1026) e a definir
  `FRONTEND_BASE_URL=https://localhost:8443`; sem isso os links do e-mail apontariam para o **dev**
  (`localhost:8090`) e o usuário do staging cairia no ambiente errado. Mesma família do **D10**.

**UI ✅ 18/07/2026:** link "Esqueci minha senha" na [tela de login](../frontend/src/pages/LoginPage.tsx)

+ três telas públicas ([EsqueciSenhaPage](../frontend/src/pages/EsqueciSenhaPage.tsx),
  [RedefinirSenhaPage](../frontend/src/pages/RedefinirSenhaPage.tsx),
  [ConfirmarEmailPage](../frontend/src/pages/ConfirmarEmailPage.tsx)) sobre uma moldura comum
  ([AuthShell](../frontend/src/components/AuthShell.tsx)) e cliente "cru" sem os interceptors de refresh
  ([recuperacaoSenha.ts](../frontend/src/api/recuperacaoSenha.ts) — quem esqueceu a senha não tem sessão
  a renovar). A tela de sucesso é **idêntica** para conta existente e inexistente, para a UI não desfazer
  a proteção anti-enumeração do servidor. Na confirmação de troca, "Não fui eu — recusar" tem o mesmo
  peso visual do confirmar. Rotas batem com os links montados pela IAM (`FRONTEND_BASE_URL` + path).
  Validado: `tsc` limpo nos arquivos novos (o legado caiu de 26 → 25 erros), imagens `iam`/`react`
  rebuildadas, as 3 rotas servidas pelo gateway (200) e o link do e-mail apontando para a tela nova.

**Fica de fora (registrado, não implementado):** **cadastro de usuário pelo frontend**, que virá com o
paywall (decisão 18/07); e leitura unificada das duas trilhas (ver **D17**).

### D12 — Revogação de sessão só cobre a desativação feita pela API · ✅ corrigido 19/07/2026

Na desativação (`is_active` True→False) o serializer faz o certo: `revoke_all_sessions` (blacklista os
refresh) + `bump_session_epoch` (corta o access residual na hora). **Mas** isso só roda nesse caminho:

- desativar por **Django admin, shell ou UPDATE direto no banco** não carimba nada — o access residual
  segue válido por ≤ access TTL (só o `/auth/refresh/` barraria, por checar `is_active`);
- **excluir** um usuário (em vez de desativar) também não carimba; pior, o access residual ainda passa no
  backend, que faz JIT `get_or_create` do espelho local e **recria** o usuário excluído por até 5 min;
- mudança de **papel/permissão** não carimba — propaga no próximo refresh (≤5 min) por recálculo de claims.
  *(este é o desenho documentado, registrado aqui só para não parecer omissão)*

**Corrigido (19/07):** o gatilho migrou para signals do `Usuario`
([iam/identity/signals.py](../iam/identity/signals.py), registrados no `AppConfig.ready`) — `post_save`
revoga na transição ativo→inativo e `post_delete` carimba a época, cobrindo admin, shell e script. O
serializer deixou de revogar (havia dois donos da mesma regra) e ficou só com a auditoria, que precisa
saber QUEM desativou — informação que o signal não tem. No `delete` não se blacklista refresh de
propósito: as linhas de `OutstandingToken` caem em cascata com o usuário, então o que vale é o carimbo.
Do lado do backend, `IamJWTAuthentication.get_user` — que **substitui** o do SimpleJWT e havia perdido a
checagem original — voltou a recusar espelho local inativo. Testes
[test_d12_revogacao.py](../iam/identity/test_d12_revogacao.py) (5): desativar e excluir pelo ORM carimbam;
salvar sem mudar `is_active`, reativar e criar **não** carimbam (revogar a cada `save()` derrubaria a
sessão do usuário a cada edição banal).
**Completado em 19/07 — troca de senha fora da API.** Ao revisar a entrega, apareceu que o mesmo buraco
continuava aberto numa terceira porta: os três caminhos que carimbavam a época em troca de senha eram
todos de aplicação (troca pela API, reset por token, `redefinir-senha` do admin). Trocar a senha pelo
**Django admin ou shell** não encerrava nada — e aqui era pior que na desativação, porque o
`/auth/refresh/` confere `is_active`, **não a senha**: o refresh antigo seguiria renovando o acesso
indefinidamente. Trocar a senha de uma conta comprometida pelo admin parecia cortar o acesso sem cortar.
O `post_save` passou a comparar o **hash** da senha (é o que está no banco; o hash muda a cada
`set_password` mesmo para a mesma senha, o que só causa revogação a mais, nunca a menos) e revoga
blacklistando o refresh + carimbando a época. Os fluxos legítimos não são afetados: eles carimbam antes
de reemitir a sessão, então o token novo (com `iat` ≥ carimbo) sobrevive — a suíte da IAM cobre isso.
**Provado no stack vivo:** token válido → `/api/clientes/` **200**; senha trocada pelo `manage.py shell`
(sem tocar em endpoint algum); **o mesmo token → 401**; relogin → 200.

**Segue de fora, por construção:** `UPDATE`/`DELETE` em SQL cru e `queryset.update()`, que não disparam
signals; e a mudança de papel/permissão, que propaga no próximo refresh (≤5 min) por recálculo de claims.

### D14 — `DB_SSLMODE` é knob morto e não há caminho para TLS no banco · ✅ corrigido 19/07/2026

`.env.example` declara `DB_SSLMODE=prefer` e `.env.staging.example` `disable`, mas o
[docker-compose.yml](../docker-compose.yml) **crava `DB_SSLMODE: disable`** nos 4 serviços que falam com o
Postgres (iam, erp, worker, beat). Confirmado em runtime: `disable` **no dev e no staging**. Ou seja:
(a) o knob do `.env` não vale nada; (b) **não existe forma de ligar TLS no banco por configuração** — o
staging, que se propõe idêntico a produção, conversa com o Postgres **em claro**.
**Corrigido (19/07):** o literal virou `${DB_SSLMODE:-disable}` nos 4 serviços
([deploy/compose/base.yml](../deploy/compose/base.yml)) — o knob do `.env` passou a valer. Faltava ainda
o caminho para o modo forte: `verify-full` exige a CA do servidor, então backend e IAM ganharam
`DB_SSLROOTCERT` (repassado pelo compose e aplicado em `OPTIONS` só quando definido — sem ele o modo
falha na verificação, e não cai em conexão insegura silenciosa). `deploy/env/prod.env.example` já nasce
com `verify-full`. **Não validado contra Postgres com TLS real** (não há um disponível): o que se provou
é que o knob chega ao Django e que dev/staging seguem subindo com `disable`.

### D16 — Cookie de refresh emitido SEM `Secure` (staging, sob HTTPS) · ✅ corrigido 18/07/2026

Achado na auditoria 18/07 (doc × código × runtime). O cookie que **é** a sessão saía do staging como
`HttpOnly; Path=/auth/; SameSite=Strict` — **sem `Secure`** —, ou seja, podia trafegar em HTTP puro
(exposição a downgrade/MITM da credencial mais sensível do sistema). Causa: `REFRESH_COOKIE_SECURE` lia
`IAM_COOKIE_SECURE` com default `"0"`, e essa variável **não estava definida em lugar nenhum** (nem
compose, nem `.env`, nem documentada). O endurecimento do bloco de produção (S4) só alcança os cookies do
**Django** (`SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`); o refresh é setado à mão em
[cookies.py](../iam/identity/cookies.py) e ficava de fora. O comentário no próprio settings já afirmava
"Secure=1 sob HTTPS (produção)" — a intenção estava documentada, a implementação não seguia.
**Corrigido:** default passa a ser **ligado fora de `DEBUG`** (mesmo princípio do S4); `IAM_COOKIE_SECURE`
documentado no `.env.example`; regressão `test_cookie_de_refresh_leva_secure_quando_ligado`.
**Confirmado no ar 18/07/2026** (imagem da IAM rebuildada): o login do staging passou a emitir
`sgi_refresh=…; HttpOnly; Path=/auth/; SameSite=Strict; **Secure**`.

### D26 — O CI nunca rodou a suíte do backend: três jobs vermelhos há 7 dias · ✅ corrigido 26/07/2026

Achado ao analisar o estado do projeto. O job `backend-tests` rodava
`manage.py test identity funcoesemail` com `working-directory: backend` — mas **`identity` é app da
IAM**, não existe no backend. O rótulo e o comentário que o explica foram colados no job errado
(introduzidos em `a4c45be`, 19/07). Resultado reproduzido: `ModuleNotFoundError: No module named
'identity'`, **"Ran 1 test"** — o job falhava e **nenhum dos 677 testes do backend rodava**.

Agravante no mesmo comando: o rótulo **`funcoesemail`** (sem `.tests`) roda **0 testes** em silêncio.
Django resolve o rótulo como diretório quando ele existe no cwd, e como *nome de módulo* quando não —
nos dois caminhos cai num **pacote** que não declara testes. Só `funcoesemail.tests` roda os 9. Ou
seja, nem a parte que "funcionava" funcionava, e a mensagem final era `NO TESTS RAN`, não um erro.

E não era um job só. O **`frontend`** e o **`security-scan`** também estavam vermelhos, os dois pelo
mesmo `npm ci` do **F6** — no `security-scan` ele roda *antes* do `npm audit` e do trivy, então o gate
bloqueante de CVE e de segredos também não executava. Dos 4 jobs, **3 vermelhos**; o único verde era
o do IAM.

**Por que importa mais que a soma das partes.** Entre 19 e 26/07 entraram SIL v2, ORC.0–ORC.5b,
IE.0–IE.1 e o pacote clientes/F16–F20 — todos com "suíte X/X verde" registrado aqui e no roadmap,
todos medidos **à mão**, nenhum por um portão. A afirmação era verdadeira e não era verificável: é a
classe de defeito que não quebra nada hoje e remove a rede de proteção de tudo o que vem depois.

**Corrigido:** job do backend passou a `manage.py test . funcoesemail.tests` (`.` dispara a descoberta
a partir de `backend/`; o pacote da raiz entra pelo módulo de teste), o `identity` voltou para o job
do IAM e os comentários dos dois jobs foram corrigidos. **Linha de base medida na correção — 801
testes verdes:** backend **677**, `funcoesemail` **9** (= os 686 que os documentos citavam), IAM
**115**. Nenhuma regressão havia acumulado atrás do portão desligado; o que faltava era a prova.
**Não fechado:** os `continue-on-error` de lint/build do frontend — medidos em clone limpo, `npm run
lint` dá **51 erros** e `tsc -b` dá **45** em 19 arquivos, e o topo **não** é o shell legado que o
comentário do `ci.yml` culpava, é o **SIL v2** (`operacao.tsx` 13, `pessoas.tsx` 6), de 25/07. Ver
**D27**.

### D27 — 45 erros de tipo no frontend, e um import de dependência que não existe · ✅ corrigido 26/07/2026

> **Fechado 26/07/2026: `tsc -b` = ZERO e o type-check virou gate.** O `frontend/Dockerfile` passou a
> rodar `npm run build` (`tsc -b && vite build`) em vez de `npx vite build`, e o passo
> **Build + typecheck** do [ci.yml](../.github/workflows/ci.yml) perdeu o `continue-on-error`. Era o
> buraco central do achado: o esbuild do Vite transpila **sem** type-check, então, com o CI
> informativo, erro de tipo não aparecia em ponto nenhum da esteira — foi assim que o SIL v2 subiu com
> 10 erros de contrato. Imagem `react` rebuildada com o gate no caminho e app servindo pelo gateway.
>
> **O `lint` continua informativo**, e agora por uma decisão declarada em vez de dívida solta: dos 23
> erros restantes, **22 são `react-refresh/only-export-components`** — a regra reclama de arquivo que
> exporta componente *e* constante, que é como os quatro kits de UI foram escritos (`malha/`, kit do
> SCM, `sil/ui.tsx`, `orcamento/ui.tsx`). Fechar exige partir os kits em dois arquivos cada ou rebaixar
> a regra a `warn` — é a dívida do **F12**, não deste achado.
>
> **Como foi (o caminho, que vale mais que o número).**
> Medido numa imagem que reproduz o job do CI (`npm ci` a partir do lock + `tsc -b` + `eslint`, com o
> `node_modules` local fora pelo `.dockerignore`): **`tsc` 45 → 11** e **`eslint` 51 → 41 problemas
> (34 → 30 erros)**. Os **11 erros restantes estão todos na ilha de obras** inventariada no `F5` da
> tabela de Baixas — nenhum em código alcançável.
>
> Antes de mexer, a inalcançabilidade foi **provada** com um grafo de imports a partir de `main.tsx`
> (resolvendo o alias `@` → `src/` do [vite.config.ts](../frontend/vite.config.ts), sem o qual quase
> todo o código vivo aparece como morto): **50 dos 313 arquivos de `src/` não são alcançáveis**, e a
> lista confirma o inventário do `F5` item a item.
>
> **Corrigido no código vivo** — os de contrato primeiro, como a ordem recomendada pedia:
> - **SIL, apropriação por etapa:** `MovimentacaoEstoque` ganhou `etapa`/`obra_nome`/`etapa_nome` e
>   `Requisicao` ganhou `etapa`/`etapa_nome` em [types.ts](../frontend/src/modules/sil/types.ts). O
>   backend manda os cinco (conferido nos serializers), o tipo do front não acompanhou — eram **10**
>   dos 45 erros.
> - **`User.id` era `number` e a IAM manda UUID** ([types/index.ts](../frontend/src/types/index.ts)):
>   `identity.Usuario.id` é `UUIDField`, e `api/session.ts` já declarava `string`. Os dois pontos que
>   preenchem o usuário (login e `/auth/me/`) atribuíam string a number.
> - **`FornecedorFormData.cnpj` era `string`** mas o formulário manda `null` quando se marca "sem
>   documento" — e o model permite (`null=True`). Virou `string | null`.
> - **`cleanParams` de `notasFiscais.ts`** ficou genérico: servia dois tipos de filtro e
>   `Record<string, unknown>` não aceita interface sem index signature.
> - **`pessoas.tsx` do SIL:** o estado do seletor de ferramenta virou o tipo `EstadoAlteravel`
>   (`emprestada` não se escolhe à mão — quem empresta é o fluxo de empréstimo).
> - Ruído: imports/constantes não usados em `LeadsPage`, `OpportunitiesPage`, `PersonaForm`,
>   `FuncionarioForm` (o `FIELD_LABELS` de rótulos PT-BR estava declarado e **nunca consumido** —
>   `parseApiErrors` não aceita mapa de rótulos; saiu, e fica registrado aqui que a intenção existia),
>   `LogisticaPage`, `operacao.tsx` e o parâmetro de `th` em `ui.tsx`.
> - **Lint em código vivo:** três `cond ? set.delete(x) : set.add(x)` usados como statement viraram
>   `if/else` (`Grade.tsx`, `ClientesListPage.tsx`, `UsuariosPage.tsx` — não eram bug, os efeitos
>   aconteciam, mas a regra está certa: statement disfarçado de expressão) e o `any` de
>   `FinanceDataTable` ganhou `eslint-disable` com o motivo (é o idioma do TanStack para coluna
>   heterogênea; estreitar quebraria as telas).
>
> **Os 11 últimos morreram com a limpeza do código morto** (o `F5` da tabela de Baixas, feito no mesmo
> dia): 2 deles eram **dependências que sequer estão no `package.json`** (`leaflet`/`react-leaflet` no
> `InteractiveMap`, `react-hot-toast` no `ObraDetailPage` órfão) — corrigi-los seria instalar
> dependência para código que ninguém alcança. Apagar era a correção, não o atalho.

Medido ao tentar transformar lint/build em gate (D26): `tsc -b` acusa **45 erros** em 19 arquivos e
`npm run lint` **51**. Enquanto isso vale, o build do CI não pode bloquear merge — e o `vite build`
da imagem não substitui o gate, porque usa `npx vite build` **sem `tsc`**: o esbuild transpila sem
type-check, então erro de tipo nunca aparece em lugar nenhum.

Concentração (não é dívida uniforme de shell legado): `modules/sil/tabs/operacao.tsx` **13**,
`sil/tabs/pessoas.tsx` **6**, `crm/pages/LeadsPage.tsx` **4**, `obras/ObraDetailPage.tsx` **3**. A
maioria é ruído barato (`no-unused-vars`, TS6133), mas há erros de contrato reais: `obra_nome`/
`etapa_nome` lidos de `MovimentacaoEstoque` e `Requisicao` sem existir no tipo (o backend passou a
mandá-los na apropriação por etapa do SIL v2 e o tipo do front não acompanhou) e
`Property 'token' does not exist on type 'AuthContextType'` em `ObrasListPage`, resíduo da Fase 10.6
(access token saiu para a memória).

**Confirmação independente do `F5` da tabela de Médias** (o do código morto, não o do `.gitignore` —
colisão de IDs herdada dos laudos): 3 dos 45 erros vêm de `modules/obras/ObraDetailPage.tsx`, a
duplicata órfã já inventariada lá, e ela importa **`react-hot-toast`, que não está no
`package.json`** — o mesmo padrão de dependência fantasma que aquela entrada já registrou para o
`frappe-gantt` do `GanttChart.tsx`. Ou seja: **parte dos 45 erros morre com a limpeza do código
morto**, não precisa de correção própria. Fazer o `F5` da tabela antes de atacar o resto reduz o
número real.

**Resíduo à parte:** o `package.json` da **raiz** do repo é da era Node (versão `1.0.14`,
`description` com um cabeçalho markdown solto, deps duplicando o frontend) e está **fora da varredura
do CI**, que só olha `frontend/` — decidir se sai ou entra no escopo do `npm audit`.
**Correção:** limpar o código morto (`F5` da tabela) → zerar os erros de tipo que sobrarem, começando
pelos **contratos do SIL**, que são bug de verdade e não ruído → remover os dois `continue-on-error`
do job `frontend`.

### D25 — `worker`/`beat` ficam com a imagem velha quando só `erp`/`react` são rebuildados · ✅ corrigido 26/07/2026

Achado ao subir o **IE.0b**: a importação de arquivo grande respondia **202** e a tela ficava
progredindo para sempre. O lote ficava em `lendo` com 0 linhas, sem erro em lugar nenhum — nem na
DLQ, porque a task nunca chegou a existir. Causa: `docker compose build erp react` não reconstrói
`worker`/`beat`, que **usam a mesma imagem do backend**; o worker seguia com o código antigo e
descartava `funcoesimpexp.preparar_importacao` como task desconhecida.

É a mesma classe do **D8** (Celery que responde 202 e nunca faz o trabalho), por outro caminho: lá
faltava o contexto de tenant, aqui falta a imagem. E o sintoma é o pior possível — **sucesso
aparente**, porque o 202 é honesto e a falha acontece depois, fora da vista.

O comando certo **já estava** em [comandos.md](comandos.md) (`--build erp worker beat`); o que
faltava era o aviso de que rebuildar parcialmente falha em **silêncio**. Sem isso, a regra parece
zelo e é fácil de encurtar quando "só mexi numa view".

**Corrigido:** `worker`/`beat` recriados e o efeito colateral documentado no `comandos.md`, ao lado
do comando. Provado depois pelo E2E
[ie_impexp_test.py](../testes/e2e/ie_impexp_test.py) (16/16), que exercita justamente o caminho
de job que o bug escondia.

### D28 — Aprovar/revisar orçamento não está em nenhuma persona: só o admin do tenant aprova · ✅ corrigido 26/07/2026

Achado ao escrever o **ORC.6** (E2E vivo), e é achado que só aparece com o **token real da IAM** — a
suíte unitária concede permissão direto no teste, então nunca esbarra nisto.

`orcamento.orcamento.aprovar` e `orcamento.orcamento.revisar` existem no catálogo
([catalog.py](../iam/identity/catalog.py)) e são exigidas pelo `action_permission_map` do
`OrcamentoViewSet`, mas **nenhuma persona de fábrica as contém**:

- **`orcamentista` não tem, de propósito** — está escrito no catálogo: *"Aprovar orçamento fica FORA:
  congelar a régua de custo é decisão de quem responde pela obra"*. Correto.
- **mas nenhuma outra persona tem** — `diretoria` (a que representa quem responde pela empresa) só
  recebeu permissões `.view`; `engenharia` (que gere obra) não recebeu nada de `orcamento`.

Consequência medida no stack vivo: `demo` (orçamentista) → **403** em `aprovar`; `admin`
(`is_tenant_admin`, que **bypassa** o `RequirePermission`) → **200**. Ou seja, na prática **o único
caminho para aprovar um orçamento é ser o administrador do tenant** — e isso não está declarado em
lugar nenhum como o desenho pretendido. É a mesma classe do órfão `erp.lote_remessa.*` do **D5**:
permissão criada, verbo gateado, ninguém com a chave.

Impacto prático: numa construtora com orçamentista e engenheiro-gestor, o dono acaba tendo de aprovar
toda planilha, ou o admin de TI ganha alçada financeira que não deveria ter.

**Decisão do dono (26/07/2026): a alçada é do próprio `orcamentista`.** O template passou a
`orcamento.orcamento.*` (view+edit+aprovar+revisar) em [catalog.py](../iam/identity/catalog.py), e
tanto o comentário do template quanto a descrição legível da persona foram reescritos — antes diziam
o contrário ("Não aprova orçamento"), e documento que contradiz o código é pior que documento nenhum.

Aplicado sem passo manual: imagem `sgi-iam` rebuildada e o `sync_authz --all-tenants` do boot
propagou **aditivamente** (`Permissões: 0 criadas, 161 atualizadas; tenants demo e acme: 17 papéis
sincronizados`). Usuários pegam a permissão no próximo **refresh** do token.

**Provado ao vivo:** o [orc6_orcamento_test.py](../testes/e2e/orc6_orcamento_test.py) deixou de
precisar do `admin` — o `demo` (que não é `is_tenant_admin`) aprova e revisa com o próprio token, e a
suíte segue **55/55**. IAM **115/115**. Quem quiser separar de novo cria uma persona só de aprovação
e tira as duas ações de `orcamento.orcamento.*` aqui.

### D31 — O Maps nasceu inalcançável: nenhum tenant assinava `maps` no stack vivo · ✅ corrigido 27/07/2026

Achado no primeiro minuto do **MAP.6** (E2E vivo), e é da mesma família do **D28**: só aparece com o
**token real da IAM**. O backend estava inteiro — migrations `0001`/`0002` aplicadas no `erp_db`,
rotas registradas, gateway roteando —, a suíte unitária fechava **44/44**, e mesmo assim **nenhum
usuário conseguia abrir uma camada do módulo**. O token do `demo` trazia
`modules: [crm, drone, erp_financeiro, orcamento, rh, scm, sil]` — sem `maps` — e, de `mapa.*`,
só `mapa.local.view/edit`.

A causa é a mesma armadilha já registrada para o SIL e o Orçamento: **o catálogo da IAM está na
imagem, mas a assinatura do tenant está no seed**. A imagem `sgi-iam` havia sido rebuildada (o
`topografo` estava lá), e o `sync_authz --all-tenants` do boot propagou o catálogo — mas ele é
**aditivo sobre o que o tenant assina**, e o tenant `demo` nunca passou a assinar `maps`, porque isso
mora no `iam/seed_demo.py`, que não roda no boot. Resultado: a trava anti-escalada (permissão ⊆
módulos assinados) cortou corretamente todas as permissões do módulo `maps`, e sobraram só as de
`base` — que é exatamente por que `mapa.local.*` sobreviveu. O sintoma parecia defeito de gate; era
provisionamento.

Sinal correlato de que o módulo nunca havia sido exercido no stack: **zero linhas em `maps_local`**
— o `georreferenciar_cadastros` nunca rodou no dev, então o mapa da empresa abria vazio.

**Corrigido:** re-seed (`docker exec -i sgi-iam python manage.py shell < iam/seed_demo.py`) — o
tenant passou a assinar `maps` e o `demo` a ter o `topografo`. Sem rebuild: a imagem já estava certa.

**Segundo achado, dentro do primeiro:** o seed **não tinha ator capaz de provar a tese das duas
metades** (planta §2). O candidato natural, o `admin`, não serve — `is_tenant_admin` **herda todos os
módulos do tenant**, então assim que o `demo` passou a assinar `maps` ele passou a alcançar as
camadas também (medido: o tile saiu de 403 para 503). Sem um ator sem o entitlement, a afirmação
central do módulo — `Local` é fundação, camada é produto — ficaria só no comentário do código.
Corrigido dando ao usuário `acme` (tenant que assina **só `drone`**) a persona `engenharia`: o
`sync_authz` a compõe naquele tenant **sem nenhuma permissão de `maps`**, sobrando exatamente
`mapa.local.*`. É o ator que o E2E usa, e ele prova a régua nas duas direções. Blast radius medido:
21 permissões, todas de `base`/`drone`; [phase8_tenancy_test.py](../testes/e2e/phase8_tenancy_test.py)
revalidado **10/10** (o isolamento do drone não se mexeu).

**Lição para o próximo módulo:** entitlement novo exige **re-seed**, não só rebuild — e o E2E vivo é
o único lugar onde isso aparece. Os dois comandos estão em [comandos.md](comandos.md); o **D25**
registra a armadilha vizinha (rebuildar `erp`/`react` e esquecer `worker`/`beat`).

### D33 — O build stage do LibreDWG não compilava (GCC 14 × `-Werror`) · ✅ corrigido 31/07/2026

O estágio 1 do [backend/Dockerfile](../backend/Dockerfile), escrito na PRA.1, **nunca havia sido
buildado**. Na primeira execução ele quebra em `encode.lo`: `cc1: all warnings being treated as
errors`. A causa é a distância entre as duas pontas — o LibreDWG 0.13.3 é de 2023 e o
`python:3.12-slim` já vem com **GCC 14**, que estreou o `-Walloc-size`; ele acusa ~40 `malloc()` de
tamanho menor que o struct em `src/encode.c`, e o `-Werror` do projeto os promove a erro.

**Corrigido:** `--disable-werror` no `configure`, com o motivo no próprio Dockerfile. Não é
conveniência: (a) o padrão acusado é intencional lá em cima (o struct tem cauda de tamanho variável)
e (b) **`encode` é o escritor de DWG** — a metade que o próprio LibreDWG chama de fraca e que o
nosso caminho não toca, porque o `dwg2dxf` decodifica. Nenhum aviso caiu no decodificador. Manter o
`-Werror` deixaria o build do backend refém do aviso novo do GCC seguinte, em código de terceiro que
não vamos consertar. De quebra, `make install-strip` em vez de `make install`: o binário estático
caiu de **66 MB para 17 MB**.

**Lição:** Dockerfile que compila dependência de fonte não está pronto quando está escrito — só
quando **buildou**. É o mesmo gênero do **D31** (o módulo que existe mas não é alcançável) e do
**F6** (o `npm ci` que só quebrava no CI): artefato de deploy não escrito por teste unitário nenhum.

### D34 — DWG e IFC nunca converteram: dois defeitos que só arquivo real revela · ✅ corrigido 31/07/2026

Com o build do **D33** de pé, os quatro motores livres foram exercitados sobre arquivos reais pela
primeira vez (amostras em `backend/media/amostras_prancheta/`, geradas com as próprias bibliotecas da
imagem). PDF e DXF passaram; **DWG e IFC falhavam 100% das vezes**, cada um por um motivo que a suíte
não tinha como ver — ela cobre a taxonomia de erro com binário ausente e cabeçalho sintético, nunca
um arquivo que chega ao motor.

**DWG — o falso upsell.** `_para_dxf` reserva o destino com `tempfile.mkstemp()`, que **cria** o
arquivo; o `dwg2dxf` recusa sobrescrever arquivo existente (`ERROR: File not overwritten: …, use -y`)
e sai com código 1 e destino vazio. O teste seguinte do adaptador (`returncode != 0 or not
getsize()`) lê isso como "o motor livre não deu conta" e levanta `MotorInsuficiente` — ou seja, a
plataforma dizia a **todo** cliente que o DWG dele *"exige o motor de alta fidelidade"* e o mandava
comprar o plano premium **para resolver um bug nosso**. É exatamente a confusão que a planta §4.2
separa em dois motivos de erro, invertida da pior forma possível: o erro do servidor vestido de
limite de plano. **Corrigido** com `-y` na chamada (a alternativa — apagar o temporário antes —
devolveria a corrida de nome que o `mkstemp` existe para evitar).

**IFC — o modelo "sem geometria".** O serializador glTF do IfcOpenShell acumula a malha em dois
arquivos vizinhos (`.glb.vertices.tmp` e `.glb.indices.tmp`) e monta o binário final **no destrutor
C++**; o `finalize()`, apesar do nome, encerra a coleta e não escreve nada. `_para_gltf` lia o
arquivo com o serializador ainda vivo → sempre zero byte → `FalhaMotor("A tesselação terminou sem
produzir geometria")`, frase que descreve um modelo vazio e manda o cliente procurar defeito no
arquivo dele. **Corrigido** soltando a referência antes da leitura (e no caminho de erro também,
senão o serializador escreveria o `.glb` depois da faxina); os dois `.tmp` passaram a ser removidos,
que antes vazavam dois arquivos por conversão.

**Regressões que fecham o buraco:** `MotorDwgTests.test_conversor_que_recusa_sobrescrever_nao_pode_virar_upsell`
(um `dwg2dxf` falso reproduz a recusa sem `-y`, então o teste vale em máquina sem LibreDWG — que foi
por onde o defeito passou) e `MotoresReaisTests.test_ifc_de_verdade_vira_gltf` (monta um IFC mínimo,
exige a assinatura `glTF` no conteúdo e que nenhum `.tmp` sobre).

**Terceiro achado, menor:** a suíte da PRA.1 **não estava verde** — 1 dos 68 falhava
(`test_status_declara_o_que_o_plano_nao_abre_em_vez_de_esconder` exigia
`conversao_disponivel is False` no plano `free`, contradizendo a semântica que a própria view
documenta: o `free` contrata PDF/imagem e o Pillow está na imagem, logo há conversão — a miniatura é
o produto de conversão que esse plano compra). O que o `free` não tem é o **motor premium**, e é isso
que o teste passou a afirmar. Suíte `moduloprancheta` **68/68** depois das correções.

**Lição:** "arquivo real de cada formato vira derivada" é DoD de fatia porque **é o único teste que
pega esta classe de defeito** — contrato de processo externo e ciclo de vida de objeto compilado não
aparecem em mock. Vale para o `gdal` e o `pdal` quando entrarem.

### D38 — Resposta de verbo de alçada saía com a conversa desatualizada · ✅ corrigido 01/08/2026

Achado pela fumaça no stack vivo da PRA.3, e é achado que **só o teste que olha a resposta pega**: o
unitário consultava o banco e passava.

`POST /api/prancheta/marcacoes/<id>/situacao/` grava a mudança, cria o comentário automático do ato
(sem ele o tópico chega ao escritório mudando de status sem dizer quem mudou — o BCF só carrega
autoria dentro do comentário) e serializa a marcação. Só que o `get_object()` trouxe `comentarios`
por `prefetch_related`, e esse cache foi montado **antes** do comentário: a resposta devolvia a
conversa sem a linha que a própria ação acabou de escrever. Na tela, o encerramento aparecia sem o
registro dele até o próximo refetch.

**Corrigido:** `_prefetched_objects_cache = {}` antes de serializar — o idioma que o `UpdateModelMixin`
do DRF usa pela mesma razão. Regressão em `moduloprancheta/tests.py::…deixa_rastro_no_proprio_topico`,
que passou a conferir **a resposta** além do banco.

**Lição, e ela é geral:** ação que escreve em relação **prefetchada** e devolve o objeto serializado
mente sobre o que acabou de fazer. Vale para todo `@action` de verbo de domínio que crie linha filha —
há vários no ERP e no Orçamento.

### D40 — O seed não tinha ator para provar a segregação da PRA.3 · ✅ corrigido 01/08/2026

O mesmo achado do MAP.6, no módulo seguinte: a fatia mais valiosa da PRA.3 é que **quem aponta não
fecha** (`prancheta.marcacao.edit` sem `.resolver`), e nenhum usuário do seed conseguia demonstrá-la.
O `demo` tem a persona `projetista`, que traz `prancheta.marcacao.*`; o `admin` é `is_tenant_admin` e
herda o catálogo inteiro; o `acme` não assina o módulo e para no entitlement, um eixo antes. A
persona `campo` existia no catálogo desde a PRA.0 — sem ninguém vestindo.

**Corrigido:** `campo / campo123` no [seed da IAM](../iam/seed_demo.py), tenant `demo`, módulos
`drone`+`prancheta`, persona `campo` — e o seed agora **imprime** se ele resolve marcação, para a
regressão aparecer no próprio log do provisionamento. Como sempre, exigiu rebuild da imagem
`sgi-iam` + re-seed (**D31**).

**Lição:** verbo de alçada nasce com três coisas, não duas — a permissão, a persona que a tem (D28) e
**o ator do seed que não a tem**. Sem o terceiro, a segregação só é testável com permissão concedida
à mão, que é exatamente o cenário que o unitário já cobre e o stack vivo não.

### D42 — O motor livre entrega 55% no acervo real, e a maior parte da falha é nossa · ✅ corrigido 02/08/2026

A medição que o PRA.1 deixou pendente rodou em **01/08/2026** sobre **73 DWGs reais de construtora**
(`medir_cobertura_dwg`, planta [§4.1](modulos/moduloprancheta.md)): **40 convertidos, 33 falhados,
taxa de 54,8%** — muito abaixo dos ~99% que a documentação do LibreDWG sugere. Duas leituras, e a
segunda é o achado:

**1. O premium não se justifica por versão nova.** `acima_do_alcance = 0`: nenhum `AC1037` no acervo.
O DWG 2024 que motivava metade da §4.1 não apareceu. Os arquivos são `AC1032` (55 de 73) e anteriores
— todos dentro do que o motor livre **declara** ler.

**2. A maior parte da falha acontece depois do LibreDWG.** Só **5** vêm do `dwg2dxf` (CRC/checksum do
próprio DWG); **26** acontecem com o DWG já convertido em DXF, no `ezdxf` tentando desenhá-lo (as 2
restantes ficaram fora do top-10 de motivos que o comando imprime):

| Motivo | Falhas | Onde |
|---|---|---|
| `arquivo_corrompido` — "não é um DXF válido, nem depois do reparo" | 13 | ezdxf lendo o DXF do LibreDWG |
| `Required block definition for "*U" does not exist` | 10 | ezdxf desenhando (bloco anônimo referenciado e não definido) |
| divisão por zero · *bounding box* vazia | 3 | ezdxf desenhando |
| CRC/checksum mismatch | 5 | `dwg2dxf` (limite real do motor livre) |

**Por que é 🟠 e não 🟡:** a fronteira comercial entre os planos ia ser posicionada por este número, e
o número está medindo um **defeito nosso**, não o limite do LibreDWG. Pior, o cliente cujo arquivo cai
nos 13 primeiros lê *"O arquivo não é um DXF válido"* — uma frase sobre o **DWG dele**, quando o
inválido é o DXF que o nosso conversor produziu. É o inverso da regra da §4.2 (separar "seu plano não
abre" de "o servidor não deu conta"), com o agravante de culpar o arquivo do cliente.

**Para fechar, em ordem de custo:** (a) tratar bloco ausente no render — criar a definição vazia do
bloco referenciado antes de desenhar resolveria 10 das 33 de uma vez; (b) trocar a mensagem do
`arquivo_corrompido` quando a origem é DWG (o DXF é intermediário nosso, não é o arquivo do cliente);
(c) só então repetir a medição e decidir a fronteira do plano — e, aí sim, dimensionar a **PRA.4**
pelo que sobrar. A amostra também merece ampliação: são os 73 arquivos que estavam locais, de um
acervo de 2.658 (os demais são placeholders do OneDrive; lê-los baixaria ~10 GB).

**Corrigido 02/08/2026, nos três passos.**

**(a) Bloco órfão não derruba mais a prancha** — [`_sanear_blocos`](../backend/moduloprancheta/motores/dxf.py).
São **duas** avarias, e a segunda só apareceu na remedição: *nome conhecido e definição ausente*
(`*U3`, `*X7`) ganha **definição vazia** — aquela inserção desenha vazio em vez de a folha inteira
morrer, que é o que qualquer CAD faz com referência quebrada; *nome vazio* (`Required block
definition for "" does not exist`) tem a **entidade descartada**, porque não há o que definir e ela
já não desenhava nada. A varredura é sobre `documento.blocks`, não sobre o modelspace: no DXF o
modelspace e cada paperspace **são** block layouts, e é isso que pega o `INSERT` aninhado dentro de
outro bloco. As duas contagens (`blocos_ausentes`, `insercoes_descartadas`) sobem para a memória de
conversão — a prancha saiu **incompleta**, e isso fica declarado em vez de virar silêncio.

**(b) A falha do intermediário deixou de acusar o arquivo do cliente** — nova
[`FalhaDoIntermediario`](../backend/moduloprancheta/motores/base.py) e `MotorDxf(origem="dwg")`. O
`MotorDwg` passa a dizer ao `MotorDxf` que aquele DXF é intermediário **nosso**, e as frases de erro
mudam de dono: `motivo` vira `falha_motor` (a fila do que **nós** consertamos, não a do upsell) e
`retentavel` é **False**, porque mesmo DWG + mesmo binário = mesmo DXF quebrado, e retentar 3× só
encheria a DLQ. Na medição, **20 clientes liam "O arquivo não é um DXF válido" sobre um DXF que
nunca viram; agora são zero**.

**(c) Remedição — 150 DWGs, amostra 1 a cada 7 de um acervo local de 1.107**, o mesmo corpus medido
antes e depois ([planta §4.1](modulos/moduloprancheta.md)): **70,7% → 73,3%**, e as 40 falhas
restantes classificadas por causa real — 20 DXF intermediário ilegível (**nosso**, → **D43**), 8
prancha só no paperspace (**nosso**, → **D44**), 5 desenho vazio e 2 XREF não enviado (→ **D45**), e
**5 CRC no `dwg2dxf`** — o único balde que é limite real do motor livre.

**A conclusão que fecha o achado:** na amostra, o limite real do caminho livre é **3,3%** — não os
45% que a taxa crua sugeria. Era exatamente o risco que este achado existia para impedir: posicionar
a fronteira comercial em cima de uma lista de correção nossa.

**Ressalva medida no mesmo dia, e ela é grande:** a amostra é dominada por arquivo pequeno (121 dos
150 abaixo de 1 MB), e a taxa **desaba com o tamanho**. Varrendo os **102 DWGs acima de 5 MB** do
acervo local, o `dwg2dxf` entrega 93% até 20 MB, **64% entre 20 e 40 MB e 0% (0 de 10) acima de 40
MB**. Então o premium **se justifica sim por DWG** — só que na ponta pesada, que é justamente o
projeto executivo completo. Ver a §4.1 da planta e o **D47**.

Suíte `moduloprancheta` **158/158** (10 testes novos, entre eles um que prova que os arquivos
recuperados geram desenho **real** — 24 a 35.401 traços, até 3,5 MB de SVG —, e não folha em branco).

### D44 — Prancha montada no paperspace sai em branco · ✅ corrigido 06/08/2026

**8 de 150** (5,3%). O motor desenha `documento.modelspace()`, e boa parte da prancha de projeto é
composta na **aba de layout** (paperspace): moldura, carimbo, legendas e *viewports* apontando para o
modelo. Nesses arquivos o modelspace tem pouca ou nenhuma entidade, o `ezdxf` não acha extensão para
a folha e levanta `empty bounding box` — que hoje vira `falha_motor` genérico.

Medido no acervo: as folhas em questão renderizam **66 a 217 KB de SVG, com 75 a 289 traços** quando
se desenha o `Layout1` em vez do modelspace. Ou seja, há prancha para mostrar.

**A armadilha a não cair junto:** a escala do PRA.3b **não pode** ser derivada de um render de
paperspace. Lá a unidade é a da **folha** (milímetro de papel), não a do modelo — publicar aquela
largura como `escala_largura_m` faria a tela responder "0,9 m" para uma fachada de 30 m, e o pior é
que o valor cairia dentro da janela de plausibilidade sem disparar nada. Quem cair no paperspace
converte **sem régua**, e a calibração humana segue sendo o caminho.

**Corrigido na PRA.1b** ([planta §4.5](modulos/moduloprancheta.md)). Quando o modelspace não desenha
nada, o motor cai nas abas de layout e **cada aba vira uma folha** — a unidade que a PRA.1c inventou
já existia no arquivo. Sem separação por lacuna (um layout é uma folha física; partir moldura de
carimbo inventaria duas pranchas onde o projetista vê uma), em ordem de aba, e com **o nome da aba
virando o nome da folha** — a única vez em que este módulo recebe um nome escrito por gente sem pedir
a ninguém. A armadilha da escala foi honrada: `escala_indisponivel: paperspace` na memória de
conversão, nenhum `escala_largura_m` publicado, com teste que monta uma moldura A1 de 841 unidades
sobre `$INSUNITS = 4` e falha se a régua sair. **Limite declarado:** o caminho só existe quando o
modelspace produz **nada** — arquivo com três entidades soltas no modelspace e a folha no layout
continua sendo desenhado por elas, porque comparar os dois espaços para escolher "o melhor" é
heurística que erraria calada.

### D45 — Desenho vazio e XREF não enviado são relatados como falha do motor · ✅ corrigido 06/08/2026

Dois casos que a classificação do **D42** separou e que hoje caem no mesmo balde de erro, ambos **sem
defeito nosso e sem plano a vender**:

- **desenho genuinamente vazio** (5 de 150) — arquivos como `Desenho1_recover.dwg`, sem uma entidade
  sequer, nem no modelspace nem em layout nenhum. Dizer "falha interna do motor" é confessar um
  defeito que não existe. Existe até a frase certa em `_ilegivel` (*"O desenho está vazio"*), mas ela
  é **inalcançável**: o `ezdxf` levanta `empty bounding box` antes;
- **XREF não enviado** (2 de 150) — a geometria mora em arquivos externos referenciados por caminho
  absoluto da máquina do projetista (`C:\Users\…\DATA\28 08\…dwg`), que nunca subiram. **Nenhum
  motor, livre ou premium, desenha o que não está no arquivo** — e é por isso que este caso não pode
  virar upsell. O que ele pede é um estado próprio ("esta prancha referencia N arquivos que não foram
  enviados") e uma linha na fila de decisão, que é acionável: o cliente reenvia com as referências.

Os dois exigem um `MotivoErro` novo (portanto migration), e é por isso que ficaram fora do D42 em vez
de entrar de carona.

**Corrigido na PRA.1b** ([migration 0007](../backend/moduloprancheta/migrations/0007_pra1b_motivos_sem_dono.py)),
com **três** motivos e não dois — o `sem_preview` do [D49](historico-correcoes.md) é da mesma família e nasceu
junto. O que os une virou conceito nomeado no código (`DerivadaProjeto.MOTIVOS_DO_ARQUIVO`): **o
problema está no arquivo**, nem no motor nem no plano.

A classificação é por evidência, não por texto de erro:

- **XREF primeiro**, e só os que estão de fato **inseridos** — um arquivo que insere referências
  externas *tem* entidades (as inserções vazias) e cairia no balde "é nosso"; já uma definição de
  XREF que ninguém inseriu não põe nada na prancha, e chamá-la de "faltam anexos" mandaria o cliente
  procurar arquivo que ele não precisa enviar. A mensagem carrega os caminhos, porque é isso que a
  torna acionável;
- **depois "nenhuma entidade em lugar nenhum"** — modelspace **e** abas de layout, senão o arquivo do
  D44 seria declarado vazio;
- **o resto continua nosso**, caindo no `_ilegivel` que o D42 criou.

**Nenhum backfill**, e a migration diz por quê: reclassificar as derivadas já em `falha_motor`
exigiria reabrir cada arquivo — a conversão é justamente o que não temos —, e adivinhar pelo texto do
erro carimbaria motivo errado em linha que ninguém conferiria. Elas se reclassificam no próximo
`reprocessar/`, que a versão nova do motor já invalida por comparação.

**Do lado da tela, e é aqui que o achado paga:** a fila do cockpit passou a contar por **quem age**
(`conversoes_que_exigem_upgrade` · `conversoes_aguardando_anexo` · `conversoes_sem_desenho` · o resto
somos nós), o badge da aba subtrai o que ninguém resolve, e a aba Conversões ganhou duas seções —
"Resolve-se reenviando" e "Não há o que converter", esta **sem botão de reconverter**, porque
oferecer a ação sugeriria que há o que tentar.

### D46 — A prancha converte, abre a 60 fps e mostra uma tarja preta · ✅ corrigido 02/08/2026

> **Mecanismo substituído no mesmo dia pelo [D52](historico-correcoes.md).** O conserto aqui descrito —
> medir os aglomerados e publicar atalhos de zoom — atacava o sintoma certo por dentro de uma folha
> que não devia existir, e esbarrava no limite de rasterização do navegador antes de resolver o
> caso. O que ficou de pé é a parte que importava: o `Recorder` (que o D52 reusa para recortar), a
> recusa a apagar geometria e os limites de zoom relativos ao ajuste. O que saiu foram os atalhos:
> cada desenho tem folha própria, então trocar de desenho é abrir outra prancha, não voar 7.865×.

Achado no teste de carga de 02/08/2026, e é o mais grave da leva porque **o sistema declara sucesso**:
a derivada fica `pronto`, o visualizador abre em 0,19 s, o movimento roda a 60 fps — e o que o
canteiro vê é **uma faixa escura de 43 px**, com o zoom marcando 0%.

**Causa.** O `ezdxf` dimensiona a página pela **extensão do desenho**. Uma única entidade perdida a
centenas de quilômetros da origem (coordenada lixo, herança de import, ponto solto num layer
esquecido) estica a folha inteira. No `Nova Área Industrial MaxPlast` o SVG sai declarando
`width="470740mm" height="8.56664e+06mm"` — **470 m × 8.566 km**. Encaixada em 1440×900, a prancha
real vira uma fração de pixel.

**Frequência medida:** dos 110 arquivos que convertem na amostra de 150, **97 (88,2%) dão folha
normal** (≤ 3 m), 8 dão folha grande (3–20 m, legítimo em urbanismo), 3 são suspeitas (20–200 m) e
**2 (1,8%) são inutilizáveis** (> 200 m).

**O conserto é barato porque o sinal já existe.** Os **dois** casos inutilizáveis já carregam
`escala_recusada` na memória de conversão — a janela de plausibilidade de
[`escala_do_desenho`](../backend/moduloprancheta/motores/dxf.py) **já concluiu** que aquela extensão
não é de um desenho de obra. Hoje esse veredito só desliga a régua; devia também decidir a folha. Em
ordem de custo:

1. **usar o sinal que existe** — extensão implausível marca a derivada como suspeita, e a tela diz
   "esta prancha tem geometria muito fora do desenho; veja o original" em vez de exibir a tarja;
2. **recortar pelo grosso da geometria** — desenhar o quantil (ex.: 99%) das entidades em vez do
   extremo, que é o "zoom nos objetos" que todo CAD tem, e cair no extremo só quando não há outlier.

**A ferramenta do caminho 2 já está instalada** (apurado 02/08/2026): a imagem roda **`ezdxf` 1.4.4**,
não o `>=1.1` do pin, e essa versão traz o backend `Recorder`/`Player`, que grava o desenho em arrays
numpy e expõe **`bbox()`** e **`crop_rect()`**. Dá para medir a extensão real, descartar a entidade
perdida a quilômetros e recortar **antes** de emitir a folha, sem dependência nova.

**Por que 🔴 e não 🟠:** é a única falha desta leva em que a plataforma **mente por omissão**. Erro de
conversão vai para a fila de decisão e alguém age; tarja preta com selo de `pronto` faz o engenheiro
concluir que o sistema não presta — e ele tem razão pelo que está vendo.

**A primeira tentativa de conserto foi recusada, e o arquivo que a derrubou é o próprio do achado.**
Recortar o desenho pelo "grosso da geometria" (quantil de 0,5% por eixo + `crop_rect()`) resolvia o
caso da entidade solta e **fracassava no caso real**: medido no
`CONFRONTANTES POLIGONAL.dwg` — o arquivo por trás deste achado —, a folha de 470 m × 8,5 km não tem
entidade perdida nenhuma. Tem **duas poligonais de levantamento legítimas, de 1.089 × 861 unidades
cada, com 169 traços cada**, separadas por um vazio de 8,5 milhões de unidades. Nenhum quantil as
separa (cada uma tem metade dos traços), e um agressivo o bastante para separá-las **apagaria uma
delas**. Recortar também presumia saber o que no arquivo do cliente é lixo — e um traço solto pode ser
um marco topográfico, uma amarração, o ponto que ele foi a campo levantar.

**O mecanismo também estava mal lido.** A tarja não é o navegador falhando em rasterizar: é o
**aspecto 1:18,2** sob o ajuste à tela. `min(1440/1.774.042, 900/32.371.124) × 0,94` dá `z =
0,0000261`, que desenha **46 × 846 px** e o badge arredonda para **0%** — batendo com os "43 px" e o
"zoom marcando 0%" relatados aqui. Por isso um teto de folha **não resolveria**: 55 × 1.000 mm tem o
mesmo aspecto e dá a mesma faixa de 47 px.

**Corrigido (02/08/2026) — o motor mede, o zoom resolve, e nada é apagado.** O `Frontend` do `ezdxf`
passa a desenhar num **`Recorder`**, que dá acesso às coordenadas de cada traço antes de a folha sair.
Com elas, [`_enquadrar`](../backend/moduloprancheta/motores/dxf.py) **descreve** a prancha em vez de
editá-la:

- **aglomerados por lacuna** — divide os traços onde houver vazio maior que `LACUNA_SEPARADORA` (25%)
  da extensão do eixo. Não há zona cinzenta a calibrar: no arquivo real a maior lacuna vale 99,98% da
  altura e a seguinte 0,0005%;
- **só fala quando o problema existe** — se o maior desenho ocupa mais de `OCUPACAO_MINIMA` (10%) do
  lado da folha, ele aparece sozinho no ajuste inicial e a memória não leva atalho nenhum. Lista de
  atalho inútil treina o usuário a ignorar a que importa;
- **o mesmo mecanismo cobre a entidade solta**, e por isso não há um segundo caminho para ela: o traço
  perdido vira um aglomerado de **1 registro**, entra na lista com a contagem, e quem decide se é lixo
  é o dono do arquivo;
- as caixas saem **normalizadas pela largura da folha** (o contrato de `Ponto` no frontend), com o Y
  invertido — no desenho ele cresce para cima, na folha para baixo; sem a inversão o atalho levaria ao
  lugar espelhado, e o erro só apareceria em prancha de dois desenhos, que é a que ninguém confere.

**A resolução é o zoom, e ele estava travado** ([Vista2D.tsx](../frontend/src/modules/prancheta/visualizador/Vista2D.tsx)):
os limites eram `[0.02, 40]` **absolutos**. Partindo de `z = 0,0000261`, o primeiro clique do scroll
caía em `Math.max(0.02, …)` e **saltava 766× de uma vez** — não era zoom curto, era teletransporte, e
o desenho passava voando. Agora os limites são **relativos ao ajuste** (`0,2×` a `50.000×`), porque ler
uma das poligonais exige **~7.865×**. Junto vieram as alternativas, todas sem recortar nada:

| Gesto | O que faz |
|---|---|
| roda do mouse | aproxima **acelerando**: giro rápido (< 120 ms entre eventos) aumenta o expoente até 3 cliques num — o "gira rápido para atravessar" do CAD |
| **Shift + arrastar** | *zoom window*: enquadra a área do laço |
| duplo clique · Shift + duplo | aproxima/afasta onde se clicou |
| `+` · `−` · `0` | aproxima · afasta · volta ao ajuste |
| **atalhos "Desenho N"** | voam direto para cada aglomerado, com a contagem de traços no rótulo |

O badge passou a ser **relativo ao ajuste** (100% = prancha ajustada) e a mostrar `7.865×` em vez de
`786500%`. Absoluto, ele abria marcando 0% — um número que não informa nada e fazia a tela parecer
quebrada antes de o usuário tentar mover.

**Armadilha encontrada:** o pin `ezdxf>=1.1` estava mentindo — a imagem rodava 1.4.4 por acaso, e o
`Recorder`/`Player` é da 1.4. Um `pip install` que resolvesse a 1.1 traria a tarja de volta **sem
quebrar teste nenhum**. Pin subido para `>=1.4` com o motivo escrito.

**O terceiro degrau, e o único que o zoom não substitui — a geometria não estava sendo emitida.**
Achado ao o usuário testar: *"Desenho 1 só apareceu algumas palavras, linhas, hachuras e pontos não
tem; Desenho 2 não apareceu nada"*. O sintoma denunciava a causa — **texto aparece, linha não**,
porque glifo é preenchimento e linha é traço. O `SVGBackend` do ezdxf emite coordenadas **inteiras**
numa grade fixa (`output_coordinate_space`, 1.000.000) esticada sobre a folha inteira; com 861 mm de
desenho numa folha de 8,5 km, cada poligonal recebia **~100 unidades**:

| grade | `stroke-width` | segmentos zerados (`l -0 -0`) |
|---|---|---|
| 1.000.000 (padrão) | **0** | **7.268 / 21.634 (34%)** |
| 100.000.000 | 3 | 182 |
| 1.000.000.000 | 29 | 4 (0,02%) |

**Nenhum zoom recupera o que não foi emitido**, e por isso este degrau vem antes de todos. A grade
passou a ser dimensionada pelo **desenho** (`RESOLUCAO_ALVO / ocupacao`, entre 1e6 e 1e9): prancha que
já ocupa a folha não paga nada — e é a esmagadora maioria do acervo —, e o arquivo real subiu de 235
para 307 KB entregando **169 elementos e 10.817 segmentos em cada uma das duas poligonais**.

A mesma medição **derrubou a solução que o [D48](historico-correcoes.md) carregava**: `LineweightPolicy.RELATIVE`
dá traço de 142.233 unidades = **1,2 m de espessura** para um desenho de 0,86 m. Relativo à folha é
tão errado quanto absoluto quando a folha não é o desenho; o que conserta é a grade.

**Defeito anterior encontrado no caminho:** `escala_do_desenho` lia a largura com `[0-9.]+`, e o ezdxf
emite `width="4.00002e+06mm"` a partir de ~7 dígitos — **toda prancha com folha acima de ~1 km perdia
a régua em silêncio**, indistinguível de quem não declara unidade. Regex corrigida, com teste.

**Validação.** Suíte `moduloprancheta` **182/182**. O teste central prende que o desenho com traço
solto sai com **um path a mais**, não com a folha "consertada" e o traço no lixo; os da grade prendem
que não sobra `stroke-width: 0` nem enxurrada de segmento zerado, e que prancha normal não engorda.
No arquivo real, pelo gateway com token de `demo` e de `admin`: `conversao.aviso.codigo =
varios_desenhos`, 2 desenhos de 169 traços, **338 paths preservados**. Semeado como `TOP-POL-001` na
obra *Torre A — Fundações* do tenant `demo` para teste manual. **A entrega do conserto dependeu do
[D51](historico-correcoes.md)** — o cache `immutable` sem versão o manteve invisível na tela.

### D47 — Acima de 40 MB o motor livre não abre nada · ✅ decidido e declarado 06/08/2026

Medido sobre os **102 DWGs acima de 5 MB** do acervo local ([planta §4.1](modulos/moduloprancheta.md)):
93% até 20 MB, **64% entre 20 e 40 MB, 0% (0 de 10) acima de 40 MB**. Todos os dez falham com a mesma
assinatura — `checksum CRC mismatch` seguido de `Invalid section_array_size` —, que é o LibreDWG
esbarrando no próprio limite ao percorrer o mapa de seções de um DWG grande.

**Não é bug a corrigir, é fronteira a declarar.** Duas consequências, e as duas são de produto:

- **a PRA.4 volta a ter degrau em DWG** — e com um critério que o cliente entende e que a plataforma
  sabe **antes** de converter: o tamanho do arquivo. O projeto executivo completo (o de 138 MB do
  acervo) é exatamente o que o plano superior passa a abrir;
- **o upload devia avisar na hora.** Hoje o cliente sobe 138 MB, espera a fila e recebe
  `motor_insuficiente`. Com o teto medido, dá para dizer no ato — e a mensagem deixa de ser um
  diagnóstico tardio para virar uma escolha informada.

Faltava confirmar se o teto é do binário 0.13.3 ou do formato. **Respondido na PRA.1b: não há versão
estável mais nova para testar.** A 0.13.3 (26/02/2024) é a última do índice de `ftp.gnu.org/gnu/
libredwg/` — as 24 releases publicadas vão de 0.5 a 0.13.3 e param ali. O que existe acima são as
*nightlies* do GitHub, todas marcadas prerelease, e o Dockerfile já registra por que elas não servem:
o ponto fixo publicamente arquivado e assinado é o que torna a **oferta de código-fonte** da GPLv3
cumprível sem esforço. Trocá-lo por uma nightly encareceria a obrigação sem promessa de ganho.

**Logo o teto é o que está medido, e virou knob:**
[`payment/planos.py::DWG_MB_MOTOR_LIVRE`](../payment/planos.py) = 40, com o aviso saindo **no
upload** (`aviso_do_upload`) e o número viajando no catálogo de formatos (`motor_livre_max_mb`) para
a tela poder avisar antes mesmo de o arquivo subir. **Avisa e deixa passar**, deliberadamente:
recusar venderia como fronteira de plano um motor premium que ainda não existe (PRA.4) — o arquivo
fica no acervo, baixável na íntegra, e reconverte sozinho quando o motor melhor chegar. Duas frases,
porque são dois problemas: quem não contratou o premium tem o que comprar; quem contratou ouve que
ele ainda não está ligado neste servidor, a mesma distinção que `pipeline._traduzir` faz depois da
falha.

**Decisão de produto tomada em 02/08/2026** ([planta §6.1](modulos/moduloprancheta.md)): o degrau do
DWG é o **tamanho do arquivo**, avisado **no upload**; e o motor premium é a **APS/Model Derivative**
(cobra **por arquivo**), não a ODA (**milhares de USD/ano fixos**) — porque o plano básico não pode
custar nada ao dono e o premium é comprado e distribuído aos assinantes que o pagam.

### D48 — O render sai de fábrica: traço grosso e texto SHX perdido · ✅ corrigido 06/08/2026

Relatado pelo usuário em 02/08/2026 ("no plano grátis, redesenhando, as linhas ficam muito grandes e
pode perder algo") e **confirmado dentro da imagem que roda**. A causa dos dois sintomas é a mesma:
[`dxf.py`](../backend/moduloprancheta/motores/dxf.py) instancia
`Frontend(RenderContext(documento), backend)` **sem `config=`**, então todo o render é default.

Medido em `02sistema_gestao_integrada-erp` (**`ezdxf` 1.4.4**):

| Opção | Valor | Veredito |
|---|---|---|
| `lineweight_policy` | `ABSOLUTE` | **causa do traço grosso** |
| `support_dirs` | `[]` | **causa do texto perdido** |
| `min_lineweight` · `lineweight_scaling` | `None` · `1.0` | nunca calibrados |
| `load_proxy_graphics` | `True` | **não é causa** — já ligado nesta versão |
| `hatch_policy` | `NORMAL` | **não é causa** — hachura não é ignorada |

**O traço.** `ABSOLUTE` significa 0,25 mm de **papel**; mas a folha é auto-dimensionada
(`Page(0, 0)`, `scale=1.0`), então o tamanho físico dela depende de como o escritório modelou. A
mesma fachada de 30 m dá folha de **30 mm** se modelada em metros (a linha vale 1/120 da largura →
empastada) e de **30.000 mm** se modelada em milímetros (1/120.000 → normal). O módulo já sabe em
qual caso está: o PRA.3b extrai o `$INSUNITS`. A saída é espessura **relativa à folha**.

**O texto, e este não tem solução livre.** As fontes **SHX** (`txt`, `romans`, `isocp`) são o padrão
de carimbo, cota e legenda no CAD brasileiro, e são formato proprietário não documentado — os
backends do `ezdxf` não as leem, e sem fonte disponível sai *tofu* no lugar de cada caractere. A
imagem tem `fonts-liberation` (cobre TrueType), não SHX. **Nenhum caminho grátis resolve isso**, nem
trocando para render no cliente: é limite do formato. Por isso o texto virou o **diferencial mais
visível do motor premium** ([planta §6.1](modulos/moduloprancheta.md)).

**Corrigido na PRA.1b** — a metade do traço por completo, e a do texto **corrigida no diagnóstico**,
que estava errado.

**O traço.** `Configuration(lineweight_policy=RELATIVE)` amarra a espessura ao lado maior da página,
com o teto calibrado numa folha de referência A1: `ESPESSURA_RELATIVA = 2,11 mm / 841 mm`, onde 2,11
é a espessura máxima que o próprio DXF define. Não é número mágico — há teste que falha se a âncora
mudar. Medido na imagem, mesma geometria em duas unidades: **41× de diferença antes, ≤3,3% depois**,
e o resíduo é quantização inteira do `SVGBackend` no extremo fino (21 unidades de grade contra 212).
A faixa de cinco penas continua distinta e em ordem — `RELATIVE_FIXED` teria resolvido o D48 matando
a hierarquia que separa corte de hachura.

Duas coisas foram necessárias e não estavam no diagnóstico original:

- **foi a PRA.1c que tornou `RELATIVE` utilizável.** É por isso que o [D46](historico-correcoes.md) a
  registrou como inviável ("traço de 1,2 m num desenho de 0,86 m"): enquanto a folha era o arquivo
  inteiro, 0,1% dela — o padrão do ezdxf — dava metros. Com um desenho por folha, a fração voltou a
  significar o que diz;
- **a compensação por ocupação**, sem a qual o conserto ficava pela metade. `MARGEM_MM` é absoluta
  (10 mm): 1,2% de uma folha de 841 mm e 40% da folha de 30 mm do *mesmo* desenho modelado em metros.
  Como a política mede fração da **página**, sobrariam ~1,7× de diferença. Corrigir a margem seria o
  caminho direto e está proibido — a largura da página **é a régua** (`escala_do_desenho` a lê do SVG
  emitido), e mexer nela mudaria o valor de toda medida já anotada no canteiro.

**O texto: as duas afirmações desta seção estavam erradas, e medir foi o que mostrou.**

1. **Não sai tofu.** O `ezdxf` cai no *fallback* `LiberationSans-Regular.ttf`, que a imagem já traz
   por `fonts-liberation`, e desenha as letras — verificado glifo a glifo (`IIIII` rende 309 bytes de
   path, `WWWWW` rende 1.924: formas diferentes, não caixas). O que se perde não é o conteúdo, é a
   **forma**: sans-serif proporcional onde o desenho espera monoline de traço, com larguras
   diferentes — o que desalinha carimbo e faz cota vazar da caixa. É um defeito menos grave e de
   natureza diferente do que estava escrito aqui;
2. **existe caminho livre, e o `ezdxf` já o lê.** O pacote traz `fonts/lff.py` (LibreCAD Font Format),
   o mapa `LFF_FONTS` e a resolução `resolve_shx_font_name(nome, "lts")`. Falta só o **arquivo**:
   `font_manager.has_font("txt.lff")` responde `False` e `ezdxf.options.support_dirs` está vazio.

O que sobra é decisão de licença, não de engenharia → **[D55](modulos/moduloprancheta.md)**.

### D49 — O `dwgbmp` ficou no build stage: o preview que o CAD gravou nunca é usado · ✅ corrigido 06/08/2026

Apurado em 02/08/2026 ao responder "não dá para abrir sem redesenho?". **Não dá** — DWG guarda o
modelo, não a imagem —, **exceto** pelo *thumbnail* que o próprio CAD grava ao salvar. O LibreDWG
extrai esse raster com o **`dwgbmp`**, ferramenta separada da mesma tarball que o build stage já
compila. Só que a imagem instala **apenas o `dwg2dxf`** (verificado: `ls` do container devolve um
binário só).

Perde-se com isso a única figura do acervo que **não depende do nosso conversor** — e ela é mais
valiosa exatamente onde hoje não há nada: quando a conversão falha, o cartão fica sem prancha alguma,
embora o arquivo carregue a imagem que o AutoCAD mostrou. Limite honesto: é raster de baixa
resolução, serve de miniatura e de "é esta prancha mesmo?", **nunca** de prancha para zoom ou
medição.

**Corrigido na PRA.1b** ([planta §4.4](modulos/moduloprancheta.md)): `dwgbmp` copiado do build stage
(+13 MB, do mesmo estágio já pago) e `MotorDwg.tipos = ("vetor_2d", "miniatura")` — **duas linhas no
banco**, que é o que faz uma sobreviver à falha da outra. O gate de versão não se aplica à miniatura:
o R2024 é justamente onde a prancha não sai.

**Três achados ao ligar o binário de verdade:**

- **o código de saída não denuncia a ausência.** Sem thumbnail o `dwgbmp` imprime *"No thumbnail
  image"*, **sai com 0** e não escreve arquivo nenhum — a mesma armadilha do `-y` que o
  [D34](historico-correcoes.md) cobrou caro. Quem responde é o destino existir e ter tamanho;
- **a ausência precisou de motivo próprio** (`sem_preview`, na migration do [D45](historico-correcoes.md)):
  depende de o escritório salvar com `RASTERPREVIEW` ligado, e arquivo gerado por script sai sem —
  uma linha vermelha por isso poria em dúvida uma prancha que abre;
- **a falha da miniatura quase apagou o upsell.** `miniatura` vem antes de `vetor_2d` em ordem
  alfabética, e o serializer pegava a *primeira* derivada em erro: um DWG que exige o motor premium
  passaria a anunciar "não traz miniatura embutida", e o botão de compra sumiria da tela. A revisão
  passou a escolher a falha por **quanto ela diz** (comercial → acionável → nossa → nenhuma), com
  regressão dedicada.

O `dwgbmp` entrega o que estava lá dentro (BMP, PNG ou WMF, sem converter entre eles). Pillow lê os
dois primeiros; **WMF é vetorial do Windows e não abre sem renderizador externo** — vira ausência
declarada com a assinatura na memória de conversão, para a estatística existir antes de alguém
decidir se vale um renderizador de WMF.

**O que ficou por provar:** o caminho feliz com binário real **e** arquivo real. As amostras do
repositório são sintéticas e nenhuma carrega thumbnail (o `dwgbmp` de verdade respondeu "No thumbnail
image" sobre elas, o que prova o caminho da ausência). O caminho da imagem está coberto por teste com
binário falso que reproduz a semântica medida — falta rodá-lo sobre um DWG do acervo, junto da
remedição.

### D51 — Reconverter uma derivada não chegava na tela (cache `immutable` por um ano) · ✅ corrigido 02/08/2026

Relatado pelo usuário ao testar o **D46**: *"se já fez o rebuild, ainda tá do mesmo jeito"*. Estava —
e o servidor estava certo. `GET /api/prancheta/derivadas/47/arquivo/` devolvia o SVG novo (307 KB,
`stroke-width` 5/12/23), mas o navegador dele nunca o pediu.

A derivada é única por `(revisão, tipo, motor)` e **a mesma linha é reescrita** a cada reconversão;
a URL, porém, era só o id, e [entrega.py](../backend/moduloprancheta/entrega.py) responde
`private, max-age=31536000, immutable` — **sem `ETag` e sem `Last-Modified`**. `immutable` diz ao
navegador para nem revalidar. Quem já tinha aberto a prancha ficava com a conversão velha por um ano.

**Isso não era um incômodo de teste, era um defeito de produto.** Atinge os três caminhos que a planta
promete: o verbo `reprocessar/` (que tem permissão própria, `prancheta.conversao.reprocessar`), a
invalidação por versão de motor do pipeline, e o **upgrade de plano para a APS** — a §4.1 promete que
"subir de plano reconverte com o motor melhor", e o cliente pagaria para não ver diferença. O sintoma
acusa o lado errado: o cliente jura que nada mudou, e está certo sobre o que vê.

**Corrigido:** `url_da_derivada` passou a carregar `?v=` com a identidade do **conteúdo**
(`versao_da_derivada` = sha256 curto de `hash_origem` + `motor_versao` + `concluido_em`). Conteúdo
novo → URL nova → busca nova; conteúdo intocado → mesma URL, e o `immutable` segue valendo (o cache
offline da §8 depende dele). `?v=` é **dica de cache, não credencial** — o gate do módulo continua
sendo o único, e há teste que prova que um `v` qualquer não abre porta a quem não tem acesso.
Testes `VersaoNaUrlDaDerivadaTests` (6) + a regressão do `EntregaDoArquivoTests`, que prendia a URL
sem versão e passou a exigi-la. Suíte `moduloprancheta` **182/182**.

**O arquivo da revisão fica como está:** ele é write-once de verdade (§9), então ali `immutable` sem
versão continua correto. A distinção é o ponto — não era o cache que estava errado, era supor que
derivada e revisão têm a mesma natureza.

### D52 — Numa prancha com duas áreas distantes, só uma delas aparecia · ✅ corrigido 02/08/2026

Relatado pelo usuário ao abrir o `confrontantes.dwg`: *"aparece só 1 dos desenhos, o outro ou não é
desenhado, ou o zoom não vai pro lugar certo"*. **Nenhuma das duas.** Contei dentro do SVG: 338
paths, 646 pontos em `y≈0` e 646 em `y≈7,87×10⁸` — as duas poligonais sempre estiveram lá, com a
geometria inteira.

O que não estava lá era um navegador capaz de mostrá-las. O `ezdxf` dimensiona a página pela extensão
do desenho, e o arquivo tem a mesma área na origem **e** em coordenada UTM: a folha saía com
`width="469382mm" height="8.56486e+06mm"`, o que dá um `<img>` de tamanho intrínseco **1,77 milhão ×
32,4 milhões de pixels CSS**. O desenho de baixo fica a 18,2 larguras-de-folha do topo, muito além do
que qualquer rasterizador entrega.

**Por que o D46 não tinha resolvido:** ele atacou o sintoma certo pelo lado errado. Mediu os
aglomerados, publicou as caixas e ofereceu atalhos — navegação *dentro* de uma página que não devia
ter existido. Funcionava até o limite do navegador, e o limite do navegador chegava antes.

**A correção é de desenho, não de tela** ([planta §4.5](modulos/moduloprancheta.md)): cada aglomerado
ganha a **própria folha**, com `crop_rect` sobre o `Recorder` que o D46 já tinha introduzido. Nada é
apagado — a recusa a recortar continua de pé, e é justamente por isso que a saída foi *dar uma folha a
cada um* em vez de escolher uma. O critério de separação passou a ser "a lacuna é maior que o próprio
desenho" (referência: o **maior** dos dois vizinhos — com o menor, um ponto solto estilhaçaria a folha
normal), e o teto subiu de 8 para 64, porque o acervo real traz o *sheet set* inteiro montado no
modelspace.

Medido: `confrontantes` passou de 1 folha de 469 m × 8,5 km para **2 folhas de 1.109 × 881 mm, 182 KB
cada**; `MaxPlast` idem; a prancha de folha única sai byte a byte igual, porque desenho sozinho não
passa pelo recorte.

**Dois achados de carona.** O `MaxPlast` traz **513 registros de extensão zero exatamente na origem**
que não desenham nada e ainda assim esticavam a folha de UTM até `(0,0)` — viraram descarte, com o
censo na `memoria` da derivada. **Rastreados em 06/08/2026** até a origem: são **51 arcos de
`radius = 0.0` do bloco `onibus`, repetidos nas 10 inserções dele** (10 × 51 = 510, mais 3 ARCs
soltos). As **39 linhas** de cada ônibus estão desenhadas, no lugar certo, dentro do Desenho 1 — nada
se perdeu. São esses arcos degenerados que fazem o próprio cabeçalho do arquivo declarar
`$EXTMIN = (0, 0, -508)` contra `$EXTMAX = (470720, 8566619, 1263)`: **é a causa da "extensão absurda"
deste caso**, e o agrupamento da PRA.1c a isola em vez de deixá-la esticar a página. O descarte deixou
de ser contado no aviso da tela (regra do dono: o que tem desenho se mostra, o que não tem se ignora)
— a linha alarmava sem informar. E a separação, sozinha, teria **piorado a
escala**: com a folha certa, o `$INSUNITS = 2` (pés) desse arquivo passaria a produzir 338 m para um
desenho de 1.109 m — errado por 3,28× e, agora sim, *dentro* da janela de plausibilidade. Por isso a
coordenada UTM passou a vencer o cabeçalho ([§13.2](modulos/moduloprancheta.md)).

### D56 — `documentos/` paginado ficou com N+1 de folha depois da PRA.1c · ✅ corrigido 06/08/2026

O comentário do `DocumentoProjetoViewSet` já dizia por que `revisoes` é prefetchado (o serializer
resolve a vigente em Python). A PRA.1c acrescentou **duas camadas** ao resumo da vigente — `derivadas`
(diz se dá para abrir) e `desenhos__derivadas` (quantas folhas, e a URL de cada uma) — e as ligou só
no `acervo/`. O viewset paginado ficou pagando uma query por revisão **e mais uma por folha**: um DWG
de 50 folhas na página vira 50 queries por documento.

Não aparecia como bug porque a tela do canteiro entra pelo `acervo/`, que estava certo. Corrigido com
o mesmo prefetch dos dois endpoints em [views.py](../backend/moduloprancheta/views.py).

### D58 — Hachura truncada saía pela metade, e ninguém ficava sabendo · ✅ corrigido 07/08/2026

Achado ao ler o `ezdxf 1.4.4` para o item 4 do [D57](historico-correcoes.md). O `hatching_timeout` (30 s de
fábrica) é **por hachura**, e ao batê-lo o `Frontend` **para no meio, desenha as linhas que já
acumulou** e avisa por `print()` no stdout do worker. O resultado é uma área hachurada até a metade
numa folha que se declara `pronto` — e `print` não é log, não vai para lugar nenhum e não chega à
tela.

É o caso mais provável do acervo pesado, e não o estouro: o teto por hachura costuma cortar antes de
o orçamento inteiro acabar, então a prancha **entrega** em vez de falhar, com o padrão pela metade.
Sem declaração, quem abre conclui que o desenho veio errado do projetista.

Corrigido no mesmo mecanismo do item 4: um `Frontend` próprio conta as hachuras desenhadas e mede o
relógio de cada uma — herdar é o ponto de extensão que o `ezdxf` oferece, não gancho torto. Passando
do teto, a folha sai declarada `hachura: "parcial"` com quantas áreas, e o aviso da prancha diz que o
preenchimento saiu só em parte e que o contorno e o resto do desenho estão inteiros.

**Correção — e a ordem importa, porque as duas primeiras são contenção e as outras são conserto:**

1. **Teto duro no worker** (`mem_limit`/`cpus` no serviço `worker` do compose, e o equivalente na
   VM): o processo que estourar morre sozinho em vez de derrubar o host. É a única linha que protege
   o servidor **antes** de qualquer diagnóstico, e vale mesmo depois de tudo o mais estar consertado.
2. **`soft_time_limit`/`time_limit` na task de conversão** — hoje não há nenhum
   `CELERY_TASK_TIME_LIMIT` no projeto (conferido: zero ocorrências no backend). O `soft` levanta
   exceção capturável, então a derivada vira `erro` com motivo próprio em vez de a task sumir.
3. **Teto de memória e de tempo por arquivo dentro da conversão** (`RLIMIT_AS` no processo que
   desenha, ou o desenho num subprocesso próprio) — para o motivo do erro ser *dado*, e não um
   worker morto sem rastro.
4. **Política de hachura no `Configuration`** — é o gerador do consumo. Conferir na versão instalada
   (`ezdxf 1.4.4`) o que existe além do `lineweight_policy` que a PRA.1b já usa; desenhar hachura
   pesada como contorno ou preenchimento sólido custa uma fração e é honesto na tela.
5. **Só então** o `medir_cobertura_dwg` volta a rodar — sob os mesmos tetos, um arquivo por
   subprocesso, para que uma medição nunca mais possa ocupar a máquina de quem a disparou.

**Duas decisões de produto saem daqui**, e são do dono:

- prancha que não converte dentro do teto é erro **de quem**? Não é upsell (nada garante que a APS
  aguente o mesmo arquivo), não é do arquivo (ele desenha, só é caro) — é nosso, e a saída honesta é
  a hachura simplificada, não a recusa;
- se o custo por conversão é ilimitado hoje, **a unidade de cobrança do módulo talvez não seja o
  formato nem o tamanho, e sim o cômputo** — o que mexe no desenho do paywall da §6.1 da
  [planta](modulos/moduloprancheta.md).

**Enquanto isto não fechar, a remedição da PRA.1b fica parada** (62 de 160 medidos, número parcial e
não registrável) — medir de novo antes dos tetos é repetir o incidente.

### D23 — Limite de entrada sem dimensão de TENANT (noisy neighbor) · ✅ corrigido 19/07/2026 · camada 1

Aberto ao concluir a **camada 2** (D22): com a saída protegida, a entrada ficou sendo a lacuna. Hoje o
throttle tem eixo por **IP** e por **usuário** — falta o eixo que define um SaaS, o **tenant**.

Consequência prática num produto vendido por empresa: uma empresa com 50 funcionários consome
legitimamente 50× o que uma de 3 consome, e **nada impede que degrade a experiência da outra**. É o
problema conhecido como *noisy neighbor*. A prática de mercado
([AWS](https://aws.amazon.com/builders-library/fairness-in-multi-tenant-systems/),
[AWS API Gateway](https://aws.amazon.com/blogs/architecture/throttling-a-tiered-multi-tenant-rest-api-at-scale-using-api-gateway-part-1/))
é limitar **por tenant** e fazer o teto de usuário ser uma **fração** do teto da empresa, não um valor
independente como está hoje.

**Corrigido (19/07)** — [nucleo/throttling.py](../backend/nucleo/throttling.py): `TenantRateThrottle`
chaveado pelo `tenant_id` do espelho local (`user.tenant_id`, sincronizado do claim pela
`IamJWTAuthentication` — o mesmo idioma de `tenancy.py`; um segundo caminho para o mesmo dado é um
segundo caminho para divergir dele). Sem tenant (anônimo, dono da plataforma) o eixo devolve `None` =
"não se aplica", e os eixos `anon`/`user` seguem valendo.

**O teto de usuário passou a DERIVAR do teto da empresa** (`THROTTLE_TENANT` ×
`THROTTLE_USER_FRACAO`, default 5%), que é o ponto do achado: solto, ele mentia nas duas pontas — 20
funcionários × 3000/h davam 60.000/h à empresa sem ninguém ter declarado esse número, e uma empresa de
3 pessoas ficava com teto efetivo 7× menor sem motivo. A fração default **preserva exatamente** o teto
de usuário vigente antes do D23: o eixo é somado, nenhum limite existente foi afrouxado.
`THROTTLE_USER` continua como escape hatch (definido, vence a derivação).

**Correção da 1ª versão, no mesmo dia — o teto do TENANT era constante e estrangulava o cliente
grande.** Apontado pelo usuário: com `60000/hour` fixo, uma empresa de 1000 funcionários recebia **60
requisições por hora por pessoa** — menos do que o polling do sino de notificações consome sem ninguém
trabalhar (~75/h só com o app aberto). O defeito não era o número e sim a **forma**: teto fixo não tem
valor que funcione — alto o bastante para o cliente de 1000 não protege contra o de 50 abusando; baixo
o bastante para proteger inutiliza o de 1000.

Pesquisa da prática (GitHub: base 5.000/h **+50/h por usuário** da organização, cap 12.500/h; Shopify:
teto por **tier do plano**, 50→100→500 pts/s; AWS SaaS Lens: balde por tenant + tier) mostrou
convergência em três pontos: **balde por tenant**, **teto derivado do plano/tamanho** e **teto duro no
topo**. Adotados os três. Por decisão do dono do produto, o teto passou a sair do **paywall**:

- **[`payment/`](../payment/README.md)** — pacote na raiz com os **valores comerciais** (planos,
  quotas, preços, add-ons e os parâmetros do teto). É o arquivo que o dono do software edita, sem
  revisão de código. Inclui o novo plano **`free`** (1 seat), que é o degrau de aquisição *e* o
  default de quem não tem assinatura — default seguro: tenant provisionado com erro cai no plano
  **menor**, nunca em "sem limite".
- **[`payment/regras.py`](../payment/regras.py)** — as **regras** (derivação, precedência, fallback).
  *(Ficava em `iam/identity/planos.py` até 19/07; movida para `payment/` no D24 para reunir todo o
  modelo comercial numa pasta só — ver a nota no D24.)*
- **Teto = `min(base + seats × por_seat, teto_de_infra)`**, com precedência
  `AssinaturaTenant.limites` → plano → `free`. Deriva de seats **contratados**, então comprar o add-on
  de usuário extra **aumenta o teto sozinho**: o limite acompanha a receita em vez de brigar com ela.
- **A IAM emite o teto como claim `rate_hora`** do access token, e não o backend calcula, porque só
  ela sabe quantos seats foram contratados — o `Usuario` do backend é **espelho JIT** (só existe quem
  já logou), então contar lá daria um teto menor que o contratado e **crescente durante a
  implantação** do cliente. Propaga no próximo refresh, como permissão.
- **`RATE_TETO_INFRA_HORA` fica acima de qualquer plano**, inclusive do *Sob Medida*: "ilimitado" no
  contrato não pode virar ilimitado no eixo de requisições, senão um tenant consome a capacidade dos
  outros. Contrato maior exige projeto de capacidade, não cláusula.

Desenho completo em [monetizacao.md §11](arquitetura/monetizacao.md).

**Também adotado da pesquisa: `X-RateLimit-Limit/Remaining/Reset`** na resposta (GitHub, Stripe e
Shopify retornam; o DRF só manda `Retry-After`, e só no 429). Sem eles o cliente só descobre o teto
**batendo nele** — o comportamento que o teto existe para evitar. Publicados pelo eixo do tenant, que
é o teto que o cliente compra e o único que ele administra. Armadilha encontrada: o `request` do DRF é
um **wrapper**, e `setattr` nele não alcança o `HttpRequest` que o middleware recebe na volta — sem
escrever em `request._request` o header sumia em silêncio.

**Modo de falha (pesquisado a pedido):** o consenso é **dividido por tipo de endpoint** — fail-open em
API de dados (fail-closed transforma queda de cache em queda total do produto) e **fail-closed em
autenticação**, onde liberar durante a queda é o que o atacante quer. É o que já vale aqui por
construção: o anti-brute-force do login mora no **nginx** e não depende do Redis, então a dimensão
crítica de segurança nunca foi fail-open. Mantido.

**Segundo furo fechado no gateway:** `limit_req_zone api` + `limit_req` na `location /api/`
(1200 r/m por IP, `burst=300 nodelay`) em [nginx.unified.conf](../infra/gateway/nginx.unified.conf) e
[nginx.staging.conf](../infra/gateway/nginx.staging.conf) — é o único lugar onde a inundação anônima de
`/api/*` é barrada, já que o DRF resolve permissão **antes** do throttle e o `401` não é contado por
eixo nenhum. Folgado de propósito: um escritório inteiro compartilha um IP via NAT, e o limite fino é o
da aplicação.

**Dois defeitos que a implementação expôs:**

- **Fail-open ausente na camada 1.** `django_redis` com `IGNORE_EXCEPTIONS=True` devolve **`None`**
  (não o default) quando o Redis cai, e o `SimpleRateThrottle` do DRF faz `history.insert(...)` logo
  depois → `AttributeError` → **500 em toda requisição**. O teto derrubaria justamente o que existe
  para proteger. Os **quatro** eixos passaram a ser subclasses locais com `FailOpenMixin` (libera e
  **loga em nível de erro** — protetor fail-open silencioso é indistinguível de protetor funcionando,
  a lição do D21). Inclusive o `ScopedRateThrottle`, que guarda os verbos caros (dashboard, NF, cobrança).
- **Os `THROTTLE_*` nunca chegavam ao container** — mesmo defeito do **D20** com `MAIL_*`: documentados
  no `.env.example` desde o S8 e ausentes do [compose](../deploy/compose/base.yml), então o operador
  ajustava o teto no `.env` e nada mudava, porque valia sempre o default do settings. Repassados ao
  `erp` (só ele serve HTTP), junto do `NUM_PROXIES` — que estava no mesmo estado e é o que define se o
  teto por IP é contornável por `X-Forwarded-For` falso.

Testes: [test_d23_tenant_throttle.py](../backend/nucleo/test_d23_tenant_throttle.py) (13) — o central é
**dois usuários da mesma empresa dividindo o balde**, com a contrapartida obrigatória (empresas
distintas não se afetam), o texto do 429 dizendo que o bloqueio é da *empresa* e não da *conta* (§2.4),
usuário sem tenant não quebrando, a queda do Redis liberando em vez de 500, e **dois tenants com planos
diferentes recebendo tetos diferentes no mesmo servidor**.
[identity/test_planos.py](../iam/identity/test_planos.py) (15) cobre o lado da IAM: teto monotônico por
plano, **empresa grande não estrangulada** (regressão do defeito original), add-on de seat aumentando o
teto, contrato vencendo o plano, nada passando do teto de infra, e plano desconhecido caindo no `free`
sem levantar. **Suítes: backend 239/239 e IAM 99/99**; `nginx -t` verde no unified.

**E2E validado no stack vivo 19/07/2026** (imagens `iam` e `erp` rebuildadas):
[d23_teto_por_plano_test.py](../testes/e2e/d23_teto_por_plano_test.py) **8/8 pelo gateway** — prova a
cadeia inteira que o teste de unidade não cobre: tenant sem assinatura cai em `free` (`rate_hora=6.900`)
→ upgrade para `empresarial` sobe o teto para **42.000** → o backend **usa** esse número
(`X-RateLimit-Limit: 42000`, `Remaining` coerente, `Reset` presente) → downgrade para `essencial`
reduz para **8.700** no token seguinte. O roteiro restaura o plano do tenant ao final.
Regressão dos E2E vizinhos: **phase6 verde** e **phase8 10/10**.

Armadilha registrada: o `manage.py shell -c` imprime um banner **antes** da saída do código, e a 1ª
execução gravou esse banner como nome do plano no restore. Corrigido com marcador (`PLANO=`) — vale
para qualquer roteiro que leia estado pelo shell do Django.

Desenho completo em [arquitetura/rate-limiting.md](arquitetura/rate-limiting.md) §2.

### D24 — Cota comercial por plano (camada 3) · 🟠 parcial · fundação 19/07 · **trava de objeto/seat ✅ 19/07/2026**

Quantas notas, boletos, análises de IA ou mensagens o plano contratado inclui por mês, por tenant.

**Já existia (entregue junto do D23):** o **catálogo de planos em código** — em
[`payment/`](../payment/README.md), com todas as quotas do [monetizacao.md §5](arquitetura/monetizacao.md)
**declaradas**, o plano `free` como default seguro e a precedência
`AssinaturaTenant.limites` → plano → `free`. Isso fechou o **item 1 do faseamento** do §10 daquele documento.

**Entregue 19/07/2026 — item 2 (trava dura de seats e objetos), sem depender do checkout:**

- **Quotas viajam como claim.** A IAM emite `quotas` no access token
  ([tokens.py](../iam/identity/tokens.py) + `quotas_efetivas`), pelo mesmo motivo do `rate_hora`: ela é
  quem sabe o que foi **contratado**, o backend é quem sabe quanto já foi **usado**. Evita um hop de
  rede no caminho de escrita, que cairia junto com a IAM. A claim leva **só o que é aplicado** —
  publicar quota inerte convidaria alguém a aplicá-la sem que o contador existisse do outro lado.
- **Objetos travam no backend** ([nucleo/quotas.py](../backend/nucleo/quotas.py)): `QuotaEnforcedMixin`
  com `quota_recurso` nos 4 viewsets da família de valor (empreendimentos, obras, clientes,
  fornecedores) → **402** com corpo estruturado (`quota`/`limite`/`uso`/`plano`).
- **Seats travam na IAM** ([identity/quotas.py](../iam/identity/quotas.py)), porque quem cria usuário é
  ela; o `Usuario` do backend é espelho JIT e contaria menos que a realidade durante a implantação.
  **Seat = usuário ativo**, então desativar libera — a saída sem checkout quando alguém sai da empresa.
- **Medidor antes da parede:** `GET /api/plano/` ([plano_views.py](../backend/nucleo/plano_views.py))
  serve plano, uso, limite, próximo degrau e o catálogo com preços. É o primeiro consumidor de
  `payment/` no backend (o `Dockerfile` passou a copiar o pacote, como o README de lá já previa).

Decisões que valem registro:

- **Só a família de VALOR trava.** A de CUSTO (IA, NF, boleto, drone, armazenamento) fica de fora por
  desenho — a regra de ouro do [monetizacao.md §4](arquitetura/monetizacao.md) manda medir e cobrar o
  excedente dela. Travar o cliente no meio de um fechamento fiscal para vender um pacote custa mais que
  o excedente evitado. Há teste que **falha** se alguém acrescentar um recurso de COGS ao registro.
- **Trava só a criação.** Editar e excluir passam mesmo acima do teto: um downgrade não pode deixar o
  cliente sem conseguir corrigir nem apagar os próprios dados.
- **Fail-open sem a claim** (token de serviço/legado), e **logado**. Não é brecha: forjar token exige a
  chave da plataforma. Fail-closed trocaria uma feature comercial por indisponibilidade de escrita.
- **Corrida aceita:** duas criações simultâneas podem terminar em `limite + 1`. Serializar exigiria
  travar a linha do tenant em toda escrita — gargalo por empresa — para evitar uma unidade num limite
  comercial. Diferente do L5, onde o que estava em jogo era o valor pago de um título.
- **Reativar consome seat.** Sem isso a trava era contornável: desativar, criar o novo, reativar o
  antigo — e terminar acima do contratado sem ver um 402.
- **Corpo do 402 sai com números, não strings.** O `APIException` do DRF converte todo o `detail` em
  `ErrorDetail` (subclasse de `str`), então `limite: 0` chegaria como `"0"`. Achado ao escrever o teste
  do contrato; corrigido nos **dois** serviços, que precisam falar a mesma língua com o frontend.
- **A lista de "quais quotas travam" é botão COMERCIAL e mora em `payment/planos.py` §4.** A 1ª versão
  a deixou junto das regras de engenharia — correção pedida pelo dono do software em 19/07, com o
  argumento que vale registrar: *o que influencia o valor final tem de estar onde ele enxerga; fora de
  `payment/` passa despercebido*. Tirar um nome da lista faz o limite deixar de morder — **vazamento de
  receita silencioso**, sem erro em log algum. Como o registro de contadores (`nucleo/quotas.py`)
  continua sendo engenharia, um teste garante que os dois **não divergem** em nenhum sentido (provado
  que pega: removendo um recurso da lista comercial, o teste falha).
- **Todo o modelo comercial foi reunido em `payment/` (19/07, a pedido do dono).** As **regras**
  (derivação do teto, precedência, fallback) saíram de `iam/identity/planos.py` — que **deixou de
  existir** — para [`payment/regras.py`](../payment/regras.py), ao lado dos valores. Motivo: quem faz
  manutenção do modelo comercial abre **uma pasta só**. Fronteira dentro dela: `planos.py`/`addons.py`
  = valores (o dono edita); `regras.py` = engenharia. Efeito colateral bom: **matou a duplicação** do
  `proximo_plano`, que o backend antes reescrevia por não alcançar o código da IAM.
  O **enforcement** (`iam/identity/quotas.py` = seats, `nucleo/quotas.py` = objetos) **não** foi para
  `payment/` e não pode ir: precisa do framework (exceção HTTP) e conta linhas **no banco de cada
  serviço** — dois bancos que o pacote compartilhado não alcança. A contagem roda onde o dado está,
  mas pede **todo limite** a `payment/regras.py`. Sem decisão comercial nesses dois arquivos.

**Armadilha exposta pela entrega — tenant sem `plano` fica no `free` (1 seat, 2 obras).** Os seeds não
gravavam plano nenhum, então ligar a trava capava a demo em 1 usuário. `iam/seed_demo.py` passou a
definir o plano **explicitamente** (`demo` → `profissional`; `acme` fica no `free` de propósito, para
existir sempre um tenant onde a parede é alcançável à mão). **Vale para o cutover:** todo tenant real
precisa de `plano` explícito antes de a trava valer para ele, senão será tratado como `free`.

**Falta:** os medidores mensais de consumo com excedente cobrado (**item 5**) e o **checkout** (item 3:
landing → Asaas → provisionamento). A UI é a **fase G** do [frontend.md §5.16](frontend.md) — enquanto
não houver checkout, o CTA de upgrade abre contato, não pagamento.

**Validado:** `nucleo/test_quotas.py` (16) e `identity/test_quotas.py` (16); suítes completas
**backend 255/255** e **IAM 115/115**. Falta E2E no stack vivo (validação sob demanda).

**Não é proteção técnica, é produto:** excedente vira bloqueio comercial ou upsell, não `429`. Por isso
depende do modelo de assinatura e **anda junto do paywall**, não antes dele — mesma decisão já registrada
para o cadastro de usuário pelo frontend (ver D11). O contador é por tenant e por período de faturamento,
e precisa ser **auditável**, porque vira fatura.

Desenho em [arquitetura/rate-limiting.md](arquitetura/rate-limiting.md) §4.

### D22 — Nenhum limite protegia a cota dos fornecedores (saída) · ✅ corrigido 19/07/2026 · camada 2

Auditoria de 19/07 contra a prática de mercado para SaaS multi-tenant. O S8 tinha construído limite de
**entrada** e nada de **saída** — e a saída é onde há dinheiro e cota de terceiro. Estado encontrado:

- **8 integrações**, não 2: NFE.io, Asaas, WhatsApp (Meta), ODM do drone, LLM de visão, geocoding,
  feriados e SMTP. `grep -rn "rate_limit" backend/` → **nada**.
- Toda task de integração com `max_retries=3` → cada ação vira **até 4 chamadas** ao fornecedor.
- O escopo `integracao_externa` (ligado no próprio S8) estava na **camada errada** e errava nos dois
  sentidos: por usuário, 20 funcionários × 300/h = **6.000 chamadas/hora** ao Asaas; e
  [`emitir_lote_nfse`](../backend/moduloerp/views.py) recebe uma **lista** e emite N notas numa
  requisição só — contada como **1**. Guarda que dava sensação de proteção sem proteger.

**Corrigido — camada 2** ([nucleo/rate_limit.py](../backend/nucleo/rate_limit.py), desenho em
[arquitetura/rate-limiting.md](arquitetura/rate-limiting.md)): token bucket no Redis (DB 4 dedicado),
**por fornecedor**, consumido **no cliente HTTP dentro do worker** — o único ponto que conhece o número
real de chamadas. Token bucket porque o trabalho chega em lote (remessa, fechamento) e janela fixa
quebraria o lote legítimo. Ligado em NFE.io, Asaas, WhatsApp, LLM e e-mail; taxa e burst calibráveis por
env, e fornecedor sem config passa (integração nova não trava por esquecimento).

Decisões que valem registro:

- **Sem token → `retry`, nunca bloqueio.** Centralizado no `DLQTask`, com orçamento próprio de
  retentativas (48): esperar a janela do fornecedor não é defeito e não pode consumir as tentativas
  reservadas a falha real. Bloquear o worker pararia a fila inteira, inclusive de outros tenants.
- **A exceção herda de `Throttled` (DRF).** Nem toda chamada vem de task: `gerar-cobranca` e
  `divergencias-asaas` consultam o Asaas **dentro da requisição** e capturam só `AsaasAPIError` — uma
  exceção comum viraria **500**. Sendo `Throttled`, vira **429 com `Retry-After`** em qualquer view,
  inclusive nas que ainda não existem.
- **Fail-open, mas RUIDOSO** (log de erro): travar pararia emissão de nota e boleto do sistema inteiro;
  passar gera, no pior caso, 429 do próprio fornecedor — que o retry trata. O silêncio é que foi o
  problema no D21.
- **`chave_extra` pronta para credencial por tenant** (previsto para o Asaas): aí a cota disputada passa
  a ser de cada empresa, e um balde global limitaria empresas sem relação entre si.

Testes: [test_rate_limit.py](../backend/nucleo/test_rate_limit.py) (11) — rajada passa, teto vira espera,
reposição com o tempo, baldes independentes, fail-open ruidoso, retry com `countdown`, e o caso central:
**lote de N notas consome N tokens** e a chamada não sai sem token. **Provado no stack vivo:** balde
compartilhado entre `erp` e `worker` (erp consome 2 → worker vê 1 → bloqueia na 4ª).

**Falta:** as outras duas camadas — **D23** (limite por tenant, camada 1) e **D24** (cota por plano,
camada 3).

### D21 — Throttle da IAM ficou inerte no Docker (cache morta em silêncio) · ✅ corrigido 19/07/2026

Encontrado em 19/07 ao responder uma pergunta sobre a UX do 429: 34 pedidos seguidos de recuperação de
senha passaram **todos com 200**, com o teto configurado em 30/hora. O throttle do S8 estava **inerte
desde que foi criado**.

Causa: a `IAM_CACHE_REDIS_URL` não foi repassada no compose, então dentro do container o default do
settings (`redis://localhost:6379/3`) apontava para o **próprio container**, onde não há Redis. E como a
cache foi configurada com `IGNORE_EXCEPTIONS: True` — de propósito, para uma queda de Redis não derrubar
o login —, a falha virou **no-op silencioso**: nenhum erro no log, nenhum sintoma, e a contagem do
throttle simplesmente não acontecia.

É a face ruim do fail-open, e vale como lição além deste caso: **um protetor fail-open que perde a
dependência fica indistinguível de um protetor funcionando**. O `/readyz` da IAM não pega isso porque
verifica o Redis da revogação (DB 2), que está configurado corretamente — são conexões diferentes.

**Corrigido:** `IAM_CACHE_REDIS_URL` repassada aos serviços no compose. **Provado no stack vivo:** cache
`VIVA`, e o 429 passa a disparar na requisição **#31**, exatamente no teto configurado.

**Varredura completa (19/07), pedida depois da primeira correção — achou mais dois defeitos:**

- **(a) Teto por IP era contornável por qualquer um.** O gateway usa
  `$proxy_add_x_forwarded_for`, que **acrescenta** o IP real ao `X-Forwarded-For` **enviado pelo cliente**;
  o DRF, sem `NUM_PROXIES`, usa a **cadeia inteira** como identidade. Bastava mandar um XFF falso e
  trocá-lo a cada requisição para ganhar um balde novo — provado no ar: 34 pedidos com XFF rotativo
  criaram 34 baldes e nenhum 429. **Corrigido** com `NUM_PROXIES=1` (env `NUM_PROXIES`) nos dois serviços:
  o DRF passa a usar o endereço acrescentado pelo proxy e ignora o que o cliente afirma. Reprovado no ar:
  os mesmos 34 pedidos caem num balde só e o 429 volta a disparar em #31. **Ajuste obrigatório no
  cutover:** com CDN/ALB na frente, o número tem de bater com a topologia real.
- **(b) A mesma confusão poluía a TRILHA DE AUDITORIA.** `_origem()` pegava `xff.split(",")[0]` — o
  primeiro elemento, 100% controlado pelo cliente — e o comentário afirmava que "a borda reescreve"
  (ela acrescenta). Dava para **gravar IP falso no `EventoSeguranca`**, o registro que existe justamente
  para reconstituir incidente: incriminar outro endereço ou esconder o próprio. Corrigido para usar o
  endereço do proxy confiável, com `NUM_PROXIES` como setting de topo — fonte única para o throttle e
  para a trilha, que não podem divergir. Testes [test_origem_ip.py](../iam/identity/test_origem_ip.py) (7).
- **(c) Dois escopos eram configuração morta.** `relatorio` e `integracao_externa` tinham taxa definida e
  **nenhuma view os declarava** — efeito zero. Ligados: `relatorio` no `ERPDashboardView` (a chamada mais
  cara da API) e `integracao_externa` nas ações que gastam cota de terceiro (gerar cobrança, emitir NFS-e/
  NF-e/lote), via `get_throttles()` por ação — repetir isso em laço não é só carga, é fatura de terceiro e
  documento fiscal indevido. Regressão em `nucleo/test_s8_jwt_throttle.py` garante que não voltem a ser
  letra morta, e que o teto apertado **não vaze** para o CRUD comum.

**Limite conhecido, registrado de propósito:** em endpoint que exige autenticação, o DRF resolve
permissão **antes** do throttle — requisição sem token leva 401 e **não é contada** (provado: 10 chamadas
sem token a `/api/clientes/` criaram zero chaves; as mesmas 10 no endpoint público contaram 10). Ou seja,
o teto `anon` protege as rotas `AllowAny` (webhooks, recuperação de senha), não a inundação anônima de
`/api/*` — para essa, o controle é o do nginx, que hoje cobre só o login. Fechar isso exigiria um
`limit_req` geral no gateway.

**UX do 429 (a pergunta que originou o achado):** o corpo que chegava à tela era o texto do DRF —
*"Pedido foi suprimido. Espera-se que esteja diponível em 3600 segundos."*, em segundos e com o erro de
digitação que vem da tradução do próprio framework. [mensagemDeErro](../frontend/src/api/recuperacaoSenha.ts)
passou a tratar 429 à parte, dizendo em minutos (via `Retry-After`) e deixando claro que o bloqueio é da
**conexão**, não da conta — sem isso a pessoa conclui "minha conta foi bloqueada" e liga para o suporte.
O texto não diz nada sobre a conta existir, pelo mesmo motivo que o teto por conta é silencioso.

### D20 — E-mail do backend nunca saiu: sem `MAIL_HOST` e com STARTTLS forçado · ✅ corrigido 19/07/2026

Encontrado em 19/07 ao migrar os últimos `send_mail` para o `funcoesemail`: ao tentar o primeiro envio
real pelo backend, ele falhou. **Dois defeitos empilhados**, e o de baixo escondia o de cima:

1. **O compose nunca passou `MAIL_*` ao backend.** Só o serviço `iam` recebia `MAIL_HOST`; `erp`, `worker`
   e `beat` subiam sem nenhuma variável de e-mail. Como as duas tasks começam com
   `if not settings.EMAIL_HOST: return`, elas viravam **no-op silencioso** — o lembrete de tarefa do CRM e
   o e-mail de lembrete do calendário **nunca dispararam em nenhum ambiente**. O aviso in-app do
   calendário funcionava e mascarava a ausência (a validação da Fatia C conferiu o sino, não a caixa).
2. **STARTTLS forçado.** `EMAIL_USE_TLS = not EMAIL_USE_SSL` ligava TLS em qualquer porta ≠ 465, e o
   Mailpit (1025) não oferece STARTTLS → `SMTPNotSupportedError` em todo envio. A IAM já excluía a 1025
   (`EMAIL_PORT not in (465, 1025)`); o backend não — as duas configurações haviam divergido.

**Corrigido:** `MAIL_HOST/PORT/USER/PASS/FROM` repassados a `erp`/`worker`/`beat` no compose, e a regra de
TLS do backend alinhada à da IAM (+ `EMAIL_TIMEOUT`, que também faltava: sem ele um SMTP pendurado segura
o worker). **Provado no stack vivo:** os dois e-mails chegam ao Mailpit com assunto e corpo corretos.

### D18 — Diário de obra datado em UTC: contribuição da noite ia para o dia seguinte · ✅ corrigido 19/07/2026

Encontrado **por acidente** em 19/07, ao rodar a suíte depois da meia-noite UTC durante outra entrega:
3 testes do `funcoeswhatsapp` falharam sem que nenhuma linha daquele módulo tivesse mudado.

`modulodiario.services.registrar_contribuicao` usava `timezone.now().date()` — a data em **UTC**. Como o
projeto roda em America/Sao_Paulo (UTC-3), toda contribuição feita entre **21h e meia-noite** era
arquivada no diário do **DIA SEGUINTE**. É exatamente o horário em que a equipe de campo fecha o dia pelo
WhatsApp, e o diário de obra é registro contratual — datar errado não é detalhe cosmético. Duas
contribuições da mesma noite (20h55 e 21h05) caíam em diários diferentes.

**Corrigido:** `timezone.localdate()` nas 4 ocorrências (`modulodiario/services.py`,
`modulodiario/views.py` ×2, `moduloerp/views.py`). Regressão em
[modulodiario/tests.py](../backend/modulodiario/tests.py) (2) com o instante **fixado** por mock — o app
não tinha `tests.py` até aqui, e um teste que dependesse do relógio de quem roda esconderia o bug de novo
(ele só se manifesta em 3 das 24 horas do dia). Provado que pega: revertendo a correção, o teste falha.

### D19 — A suíte dependia do `.env` da máquina de quem a roda · ✅ corrigido 19/07/2026

Também exposto em 19/07. Três acoplamentos faziam o resultado dos testes variar sem mudança de código:

- **Throttle (S8):** a contagem vive na cache, que era o Redis **real e compartilhado** — um teste
  consumia a cota do seguinte, e o teto por hora nem zerava entre execuções. Foi o que quebrou 12 testes
  da IAM na primeira tentativa do S8.
- **Celery:** `CELERY_TASK_ALWAYS_EAGER` tinha default `str(DEBUG)`; bastava alguém pôr `False` no `.env`
  local para 3 testes do diário quebrarem.

**Corrigido:** ambos os `settings.py` passaram a detectar `TESTING = "test" in sys.argv` e, sob teste,
usar **LocMemCache**, **throttle desligado** (quem o exercita reativa a taxa com `@override_settings` /
patch em `THROTTLE_RATES`, que é atributo de CLASSE lido no import — `override_settings` sozinho não o
alcança) e **Celery in-process**. Isso não substitui exercitar o worker real: o **D8** (cobrança sem
contexto de tenant) só apareceu no worker, e continua coberto por E2E no stack vivo.

### D15 — 23 knobs lidos pelo código e ausentes do `.env.example` · ✅ corrigido 19/07/2026

Auditoria 18/07/2026 (declarado × lido) achou 23 variáveis que o código lê mas nenhum `.env` documenta.
As de segurança: **`SESSION_REVOCATION_ENABLED` / `SESSION_REVOCATION_FAIL_OPEN`** (dá para **desligar a
revogação de sessão inteira** sem rastro em documentação), `IAM_COOKIE_SECURE`/`IAM_COOKIE_SAMESITE`/
`IAM_REFRESH_COOKIE`, `SECURE_SSL_REDIRECT`/`SECURE_HSTS_SECONDS`, `JWT_PRIVATE_KEY_PATH`/
`JWT_PUBLIC_KEY_PATH` (base do S3), `JWT_ISSUER` (o S8 vai precisar) e `SERVICE_TOKEN_TTL_SECONDS`.
As operacionais: `LOG_LEVEL`, `LOG_FORMAT`, `DB_CONN_MAX_AGE`, `PROMETHEUS_MULTIPROC_DIR`,
`OBSERVABILITY_SERVICE_NAME` e os timeouts de NFE.io/LLM/serviço.
**Corrigido (19/07):** os 23 estão documentados em
[deploy/env/dev.env.example](../deploy/env/dev.env.example), agrupados por assunto (Redis e a divisão de
DBs, observabilidade, timeouts de integração, tetos do S8). A verificação é mecânica e vale repetir a
cada auditoria — comparar o que o código lê com o que o exemplo declara:

```bash
grep -rhoE "os\.getenv\(\s*['\"]([A-Z0-9_]+)" --include="*.py" backend/ iam/ \
  | grep -oE "[A-Z0-9_]+$" | sort -u > /tmp/lidas.txt
grep -hoE "^#?\s*[A-Z0-9_]+=" deploy/env/dev.env.example | tr -d '#= ' | sort -u > /tmp/doc.txt
comm -23 /tmp/lidas.txt /tmp/doc.txt        # vazio = nenhum knob órfão
```

Hoje esse `comm` sai **vazio**. Foi esta auditoria que revelou o `JWT_REFRESH_DAYS` morto e o D14.

### F13 — Cliente do Orçamento contrariava o contrato do backend em 5 pontos · ✅ corrigido 25/07/2026

O hub do Orçamento quebrava a tela inteira no primeiro acesso
(`TypeError: x is not iterable`, em `montarFila`). Causa: `apiClient.get<T>` é **só um cast** — o
tipo declarado não valida nada em runtime, então uma divergência com o backend só aparece quando a
tela roda. Havia quatro, todas do mesmo feitio (envelope × lista, nome de campo):

| Endpoint | Backend devolve | Cliente esperava | Sintoma |
| --- | --- | --- | --- |
| `controle/` | `{obras, nota_realizado}` | `ControleLinha[]` | **crash** do hub (`for…of` sobre objeto) |
| `referencias/{id}/composicao/` | `{composicao, componentes}` | `ComponenteReferencia[]` | **crash** ao espiar a analítica (`.map`) |
| `referencias/adotar-lote/` | `{adotados: <contagem>, itens: [...]}` | `{adotados: number[], criados}` | **crash** ao inserir item adotado; recado "undefined item(ns)" |
| `bases-resumo/` | `insumos`/`composicoes`/`adotados_no_catalogo` | `total_insumos`/`total_composicoes`/`adotados` | cards de base com `undefined` |
| `obras/` e `etapas-obras/` | `obra_id` / `etapa_id` | `id` (em `ObraOpt`/`EtapaOpt`) | **todo seletor de obra do módulo quebrado** (ver abaixo) |

**Corrigido** no cliente ([orcamentoApi.ts](../frontend/src/modules/orcamento/api/orcamentoApi.ts) +
[types.ts](../frontend/src/modules/orcamento/types.ts)), não no backend: as respostas estão
testadas (`test_resumo_conta_itens_e_adotados`) e os nomes do resumo **não podem** virar
`total_insumos` — são anotações `Count(...)` e o model já tem campos com esse nome. O tipo do
cliente passou a descrever o que a API realmente devolve, com o desembrulho explícito em um lugar só.

O caso `ObraOpt` merece nota própria porque **não gera erro nenhum** — nem no console: com
`id` inexistente, `<option value={o.id}>` sai **sem atributo `value`** e o `<select>` passa a
devolver o *texto visível* da opção. A obra virava `NaN`→`null` no POST (400 "Este campo pode não ser
nulo") e, nos seletores que só filtram (Controlar, Cronograma, Incorporação), a tela simplesmente
não achava nada. Os seis pontos foram corrigidos; o SIL, que já usava `obra_id`, estava certo.

**Dívida que isto expõe (aberta):** nada garante o contrato entre backend e cliente. Enquanto o
`tsc -b` não roda no build da imagem (o Dockerfile do frontend usa `vite build` de propósito, por
causa de ~55 erros herdados do shell v01), o próximo desalinho volta a aparecer só na tela.
Caminho: schema gerado (`drf-spectacular` → tipos) ou validação em runtime no cliente.

### F14 — Só era possível criar **um** orçamento por obra (400 sem explicação) · ✅ corrigido 25/07/2026

`POST /api/orcamento/orcamentos/` respondia **400 "Os campos obra, versao devem criar um set
único"** em qualquer obra que já tivesse planilha. Causa: `versao` é `read_only` no serializer, então
o validador automático do DRF a checava pelo **default do modelo (1)** — e a constraint
`(obra, versao)` recusava. Os outros dois caminhos de criação já numeravam
(`revisar_orcamento`, `duplicar_orcamento`); o POST era o único que não, e nascia sempre v1.
Efeito prático: **reorçamento impossível pela tela** e a única saída era aprovar para poder revisar.

**Corrigido:** `planilha.proxima_versao(obra_id)` virou o numerador único dos três caminhos; o
serializer descarta o validador de `(obra, versao)` (o cliente não envia versão) e atribui o número
no `create`, com retry em `IntegrityError` para o POST simultâneo não virar 500. Testes
`PlanilhaAPITests.test_segundo_orcamento_da_mesma_obra_nasce_na_versao_seguinte` e
`…test_versao_do_post_continua_depois_da_revisao` (suíte do módulo: 202 ✅). Desenho registrado em
[modulos/moduloorcamento.md §4.2](modulos/moduloorcamento.md).

**Achado junto (mesmo sintoma para o usuário):** o modal "Novo orçamento" não tratava erro —
`onCriar` era chamado sem `await`/`catch`, então **qualquer** 400 virava só uma promise rejeitada no
console, com o modal aberto e nenhum recado. Agora mostra a mensagem da API e avisa, ao escolher a
obra, que a planilha nascerá como v*N*.

### D62 — A exportação entregava fórmula executável ao destinatário · ✅ corrigido 07/08/2026

Achado na análise de segurança do `funcoesimpexp` (07/08/2026). `_csv` e `_valor_para_celula` em
[formatos/escrita.py](../backend/funcoesimpexp/formatos/escrita.py) escreviam `str(valor)` cru. Um
fornecedor cadastra a razão social como `=cmd|'/c calc'!A1` — dado que entra pelo cadastro normal —
e quem abre o XLSX/CSV exportado no Excel executa a fórmula.

**O alvo é o cliente do nosso cliente, e o veículo somos nós.** É o oposto exato da R9: a peça sai
executável em vez de conferível. A OWASP trata *CSV Injection* como defeito de quem **gera** o
arquivo, não do Excel.

**Corrigido com remédio diferente por formato**, porque o risco é diferente: no **CSV** o Excel
reinterpreta cada célula ao abrir, então `=`, `+`, `-`, `@`, tab e CR ganham prefixo `'` (a
mitigação da OWASP — custa um apóstrofo visível, aceitável no formato que existe "para quem vai ler
com script"); no **XLSX** célula de string é string e o Excel não a reinterpreta — o que sobrava era
o **openpyxl** inferindo tipo no `append` e gravando um `<f>` de verdade, resolvido fixando
`data_type = "s"`, sem sujar o valor. Medido: `=cmd|"/c calc"!A1` sai `tipo=s` no XLSX e `'=cmd…` no
CSV; número tipado (R8) não passa pelo escape, então valor negativo continua intacto.

### D63 — O parse de planilha não tinha teto de recurso nenhum · ✅ corrigido 07/08/2026

**É o [D57](historico-correcoes.md) num segundo caminho, e o [D60](roadmap.md) previu.** `load_workbook`
com `read_only=True` é streaming, mas `[list(l) for l in iter_rows()]` materializa tudo, e o
`preparar` monta a lista inteira de `LinhaImportacao` antes do `bulk_create` — **duas cópias
completas**. Não havia teto de bytes descomprimidos, de linhas lidas nem de tempo; PDF idem
(`pdfplumber` sem limite de páginas). Um XLSX cabe em 10 MB e descomprime sem relação com isso.

**E quem ataca escolhia onde bater**, porque o corte é público: abaixo de 512 KB o parse roda no
**processo web**; acima, no **`worker` geral** — na época o único da frota sem `mem_limit`
(→ **D71**, fechado em 07/08/2026, abaixo).

**Corrigido:** o orçamento de recurso do D57 foi **promovido para a fundação**
([nucleo/orcamento.py](../backend/nucleo/orcamento.py)) e o `preparar` roda leitura **e**
classificação inteiras sob ele. `MemoryError` vira `RecursoExcedido` — a lição do E2E da PRA.1d, em
que o estouro embrulhado por `except Exception` acusava o arquivo do cliente por um limite nosso.
Guarda de thread principal nos dois tetos: `RLIMIT_AS` é do processo, e armá-lo sob pool de threads
estrangularia requisição vizinha. Os números vêm do plano (→ [D64](historico-correcoes.md)).

**Corrigido junto — o comentário que mentia:** `preparar` dizia "Tetos ANTES de materializar (R13)",
mas `_checar_teto_por_operacao` roda **depois** do parse: não há como contar linha sem ler. A R13
protege o que é **gravado**; o custo de ler é anterior a ela, e é do orçamento.

### D64 — Os limites do motor eram constantes de engenharia, invisíveis ao dono · ✅ corrigido 07/08/2026

O teto de tamanho vinha de `ConfiguracaoArquivos` do tenant (10 MB, num lugar que o dono do produto
não revisa), a lista de formato não existia e memória/relógio idem. Decisão do dono na mesma
conversa: **todo limite é knob comercial, por plano, "para ser mais fácil mudar"** — ampliação
explícita da regra do `payment/` ([README](../payment/README.md)).

**Método aplicado, não parâmetros** (pesquisa pedida): é o do **assinador gov.br** — capacidade é
atributo do **nível** (conta bronze não assina, prata e ouro sim), **allowlist publicada** de
formato, e o teto **dito antes** do envio, nunca descoberto no erro. E o da **Shopify** no eixo do
custo: ela não limita por contagem, limita por **custo calculado** — que aqui são `impexp_memoria_mb`
e `impexp_segundos`, o limite na unidade em que a conta chega.

**Corrigido:** `payment/planos.py` §5.2 ganhou `impexp_max_mb`, `impexp_formatos`,
`impexp_memoria_mb`, `impexp_segundos` e `impexp_exportar_apos_cancelar_dias` nos cinco planos, com
tetos **duros de infraestrutura** por cima (`None` de contrato ilimitado cai neles, não em
ilimitado — o mesmo papel do `RATE_TETO_INFRA_HORA`). `GET /api/impexp/recursos/` passou a publicar
`limites` junto do catálogo, que é a terceira parte do método.

### D65 — Upload aceitava qualquer coisa: só tamanho, e despacho pelo nome do arquivo · ✅ corrigido 07/08/2026

`_validar_upload` checava `arquivo.size` e **nada mais** — sem allowlist, sem MIME, sem magic bytes —
e `ler_bytes` despachava pelo **sufixo do nome que o cliente mandou**, que é dado do atacante.
`payload.exe` renomeado para `.xlsx` passava a porta, era **gravado em disco** no caminho de job e só
falhava ao ser parseado.

A recusa de reusar `validate_uploaded_file` continua certa e pelo motivo original (aquela lista de
MIMEs é de documento guardado e não tem `text/csv`); o que faltava era um validador **próprio**.

**Corrigido:** [limites.py](../backend/funcoesimpexp/limites.py) decide pela **assinatura de bytes**
(allowlist: `PK\x03\x04` → xlsx · `%PDF-` → pdf · texto sem byte nulo → csv), e o sufixo só desempata
entre formatos que compartilham assinatura (todo XLSX é um ZIP). A amostra de 4 KB é lida **antes** do
arquivo inteiro, senão o teto de tamanho protegeria depois de já ter pago o custo. O formato
reconhecido viaja com o lote, para o worker e o `remapear` não voltarem a decidir pelo nome. Provado:
`.exe` e ELF renomeados são recusados; PDF no plano `free` volta **402** nomeando o que o plano abre.

### D66 — O admin do tenant furava o entitlement pelo impexp · ✅ corrigido 07/08/2026

O gate deste app é o conjunto de permissões, e ele **já carregava o entitlement por
transitividade**: `permissoes_efetivas()` na IAM filtra as permissões pelos módulos efetivos, então
quem não assina o Orçamento não tem `orcamento.*` no token. Bom desenho — e `_privilegiado` passava
por cima dele, porque devolve conjunto vazio **antes** de olhar permissão nenhuma. Efeito concreto: o
tenant que cancelava o Orçamento levava 403 em `/api/orcamento/**` e seguia importando **e**
exportando por `/api/impexp/orcamento.planilha/`; `RecursosView` ainda listava para ele os recursos
de todo módulo, contratado ou não.

**Corrigido com assimetria deliberada, e ela é o método dos grandes:** importar passou a exigir o
módulo contratado; **exportar continua aberto ao admin**, porque é *portabilidade* — Salesforce
retém 180 dias e a HubSpot rebaixa para o free em vez de apagar, e prender o dado do cliente no dia
em que ele cancela gera processo, não receita. O que faltava para isso ser decisão em vez de
acidente era o rastro, e ele veio com o [D67](historico-correcoes.md). Recurso de **fundação** declara
`entitlement = None` (o `maps.local` é o caso: `Local` é a metade do Maps que abre para todo tenant).
A janela em dias está declarada e **inerte** — aplicá-la exige a IAM emitir a data de cancelamento,
porque hoje `modules` só diz o estado de agora e módulo cancelado é indistinguível de nunca contratado.

### D67 — A R12 era letra morta: nenhuma exportação chegava ao `AuditLog` · ✅ corrigido 07/08/2026

A régua promete "toda exportação é auditada no `AuditLog`" e o próprio model repetia a promessa —
**não havia uma única chamada no app inteiro**. Existia a linha `Exportacao`, que é rastro
*operacional* dentro da RLS do tenant; a trilha append-only da plataforma (o `save()` recusa update,
o `delete()` é bloqueado, a API é read-only) não recebia nada. Para o evento de LGPD por excelência —
o instante em que o dado deixa o perímetro — é a diferença que importa. Conecta com o [D17](pendencias.md).

**Corrigido:** ação própria `AuditLog.Acao.EXPORTAR_DADOS`
([migration 0021](../backend/nucleo/migrations/0021_auditlog_exportar_dados.py)), separada da
`EXPORTAR_LGPD` de propósito — aquela é o direito do titular, esta é levar um recorte para o Excel, e
misturá-las tornaria ilegível o relatório que a LGPD pede. `detalhes` sem PII: recurso, formato,
volume e **recorte** — que é o que responde "levou tudo ou levou uma obra". Auditado nos dois
caminhos, e no de job **na conclusão**, porque o que sai do sistema é o arquivo pronto, não o pedido.

### D68 — Arquivo de entrada preso em `aguarda_de_para` ficava para sempre · ✅ corrigido 07/08/2026

`limpar_exportacoes_expiradas` varria só a **saída**. Na entrada o arquivo é apagado assim que lido —
menos o lote que ficou esperando de-para, que o preserva de propósito (R4) e não tinha prazo nenhum.
Subir arquivos com cabeçalho que não casa era acervo permanente, de graça, fora de qualquer quota — e
arquivo de importação é o dado mais cru que existe (carteira de clientes, folha).

**Corrigido:** `limpar_entradas_orfas` no beat (24 h, corte de 7 dias). Como na saída, **a linha
permanece** e o arquivo some; o lote passa a dizer isso, para a tela não oferecer um "escolha as
colunas" que não tem mais o que reler.

### D69 — Saída de arquivo sem `nosniff` · ✅ corrigido 07/08/2026

`_arquivo()` mandava `attachment` e o `FileResponse` da exportação por job idem, mas nenhum dos dois
mandava `X-Content-Type-Options: nosniff` — o par que a PRA.2 fixou como padrão da casa na porta de
leitura da Prancheta. Risco baixo com xlsx/csv/pdf, e é justamente por isso que passa despercebido
até o dia em que um recurso exportar formato que o navegador saiba renderizar.

### D57 — A conversão não tinha teto de recurso nenhum: um DWG de cliente consumia a máquina · ✅ corrigido 07/08/2026

Achado em 06/08/2026 ao rodar a remedição da PRA.1b, **duas vezes**: a passada consumiu **62 GB de
RAM** na primeira e **30 GB** na segunda (interrompida antes de travar), numa estação de 64 GB. O
custo não era do volume de arquivos — era que **uma conversão sozinha não tinha limite superior de
nada**: nem tempo, nem memória.

**A leitura certa nunca foi "a medição pesou".** É que o mesmo caminho roda em produção, num worker
Celery, sobre arquivo que **qualquer cliente sobe**. Numa VM paga isso é dinheiro: um punhado de DWGs
assim num dia consome o orçamento de infraestrutura do mês — o oposto exato da régua de que **o plano
básico não pode custar nada ao dono**. Nenhuma das três camadas de limite existentes pegava isto: a
[D23](historico-correcoes.md) limita **entrada**, a [D22](historico-correcoes.md) limita **saída** e a
[D24](historico-correcoes.md) conta **objetos e seats**. O que ninguém limitava era o **cômputo**, que
é onde mora o COGS real deste módulo. O teto de peso do DWG (D47) tentou aproximá-lo pelo tamanho do
arquivo, e a medição mostrou que **tamanho não é proxy de custo**: os arquivos que estouraram a RAM
passam folgados no teto de MB.

**O mecanismo da memória** (o que custava caro, e não o tempo): o `Frontend` expande cada `HATCH` em
linhas de padrão, e cada linha vira registro no `Recorder` — objetos vivos até a folha ser emitida.
O teto de 30 s do próprio `ezdxf` é **por hachura** e **não devolve a memória já alocada**. Somando: a
PRA.1c mantém as folhas todas em `Saida.partes` até o pipeline gravar, então o pico é por **arquivo**.

**Corrigido em cinco itens (PRA.1d, 06–07/08/2026)** — desenho em [planta §4.6](modulos/moduloprancheta.md):

1. **Contenção (06/08).** Fila `conversao` + serviço `worker-conversao` com `mem_limit`/`cpus` e
   `--max-memory-per-child` ([base.yml](../deploy/compose/base.yml)), `-Q celery` explícito no worker
   geral (sem isso o isolamento seria só aparente), `soft_time_limit`/`time_limit` na task, e o
   `orcamento_de_conversao` ([limites.py](../backend/moduloprancheta/limites.py)) traduzindo estouro em
   **`recurso_excedido`** ([migration 0008](../backend/moduloprancheta/migrations/0008_d57_recurso_excedido.py)) —
   motivo próprio porque `tempo_excedido` é `retentavel` (repetir reproduz o estouro, 3× pela DLQ) e
   `falha_motor` acusaria defeito nosso onde houve **limite** nosso.
2. **A causa, não o estrago (07/08).** `hatch_policy` na `Configuration` + **escada de um degrau** no
   pipeline (`SHOW_OUTLINE`, medido: 119.991 B → 569 B). Quatro decisões que valem como precedente:
   nada degrada por palpite (só desce quem **provou** não caber); a escada mora no pipeline, não no
   motor (lá a 2ª passada herdaria o consumo da 1ª); sem hachura a 2ª passada nem começa
   (`teto="sem_economia"`); e a folha **diz o que é** pelo canal de aviso que já existia. Junto, a
   ferramenta da remedição passou a rodar pelo caminho de produção — ela chamava o motor **direto**,
   que é como a passada de 06/08 chegou aos 62 GB.
3. **O defeito que anulava a fatia**, pego pelo E2E vivo ([pra1d_hachura_test.py](../testes/e2e/pra1d_hachura_test.py)):
   o `MemoryError` do `RLIMIT_AS` era embrulhado pelos `except Exception` do motor e virava
   `falha_motor` (retentável, 3× na DLQ) ou `arquivo_corrompido` (culpando o arquivo do cliente), então
   **a escada nunca descia** — 7min06 sem desfecho → **36 s**. Subiu junto o `worker-conversao`, que
   nunca tinha subido: a fila `conversao` não tinha consumidor.
4. **A remedição sem ocupar a estação (07/08).** 160 DWGs em 16 lotes, um container por lote
   ([remedir_dwg.sh](../ferramentas/medicao/remedir_dwg.sh)), teto duro de 3 GB/2 CPUs por lote — o lote é
   sobre **memória**: o que o `ezdxf` e o LibreDWG alocam volta ao sistema quando o processo morre, não
   quando o Python libera o objeto. **116 de 160 (72,5%)**, premium estável em 3,1%, corpus versionado.
5. **O contrato promovido a todos os motores (07/08).** A correção do item 3 nasceu **dentro do
   `dxf.py`**, como se fosse detalhe daquele motor, e ficou lá: PDF, imagem, IFC e o preview embutido
   do DWG seguiram embrulhando `MemoryError`, cada um com a frase errada da sua família. Achado ao
   conferir o D57 antes de arquivá-lo — **o achado estava sendo dado por fechado com 1 dos 4 motores
   corrigidos**:

   | Motor | O teto virava | Por que dói |
   |---|---|---|
   | PDF (`render` da 1ª página) e imagem (`load()`) | `arquivo_corrompido` | manda o projetista reexportar um arquivo que está perfeito |
   | IFC — leitura (`ifcopenshell.open`) | `arquivo_corrompido` | idem, e o parser lê o arquivo inteiro **antes** de o `TETO_ELEMENTOS` ter o que contar |
   | **IFC — tesselação (OpenCascade)** | **`FalhaMotor`, retentável** | **a DLQ repetia 3× um estouro determinístico: três picos de memória pelo preço de um upload** |
   | preview embutido do DWG | `sem_preview` | família *"ninguém age"* (D45/D49) — o teto agindo **sem aparecer em fila nenhuma** |

   `NAO_EMBRULHAR` saiu do `dxf.py` para [motores/base.py](../backend/moduloprancheta/motores/base.py),
   e cada `except ArquivoCorrompido: raise` / `except FalhaMotor: raise` espalhado pelos motores — cada
   um relembrando só a subclasse que o autor tinha em mente — foi subsumido por ele. Regressão em
   `TetoTraduzidoEmTodosOsMotoresTests`: comportamento motor a motor **mais** uma varredura de AST
   sobre os adaptadores **registrados** (não sobre uma lista escrita no teste, para o motor da PRA.4
   entrar coberto no dia em que for registrado), cobrando a guarda de todo `except Exception` que troque
   a exceção por outra. **A varredura tem controle negativo**, e foi ele que derrubou a primeira versão
   dela: conferir uma lista de "falhas que culpam" passava limpa no `dxf.py` mesmo sem guarda nenhuma,
   porque lá a tradução passa por um helper (`raise self._ilegivel(…)`) cujo nome não está no `raise`.
   A regra virou o oposto — allowlist do que é inofensivo (`MotorIndisponivel`, que só nasce de
   `except` em volta de `import`).

**Fica declarado na planta, não aqui:** `RLIMIT_AS` não alcança o C++ do OpenCascade da mesma forma
(`std::bad_alloc` não é `MemoryError`), e o remédio — tesselar em subprocesso — é a mesma fatia do
§12.4. **Resíduo aberto, com ID próprio:** [D61](pendencias.md) — 11 arquivos estouram mesmo no
degrau. O outro, **D71** (o worker geral sem teto de container), foi fechado em 07/08/2026 e está
logo abaixo.

**Como foi verificado:** 14 asserções do contrato executadas contra as bibliotecas reais
(`pypdfium2`, `ifcopenshell 0.8.5`, `Pillow 12.3`) — incluindo que a falha comum do IFC **continua**
retentável, que é a metade do teste que prova não ter quebrado o comportamento certo —, mais o
controle negativo da varredura nos quatro motores. A suíte `moduloprancheta` sob Django roda no
container (o venv da estação não tem GDAL desde a MAP.0) e é a validação que fecha o item.

### D71 — O worker geral não tinha teto de container · ✅ corrigido 07/08/2026

Resíduo direto do **D57** acima, e a leitura que o torna incômodo: **isolar a conversão numa frota com
teto deixou a outra frota sem nenhum.** O `worker-conversao` ganhou `mem_limit`/`cpus`/
`--max-memory-per-child`; o `worker` geral — que roda a importação do `funcoesimpexp`, a cobrança, a
NF-e, o e-mail e os lembretes — seguia sem nada em
[base.yml](../deploy/compose/base.yml). O [D63](historico-correcoes.md) fechou o consumo do **parse**
por operação, que é o freio mais apertado e o único que sabe explicar; faltava a rede por baixo dele.

**O que ficava descoberto não era o impexp — eram as outras quatro.** A importação tem
`orcamento()` desde a IE.2, com memória e relógio vindos do plano. Cobrança, NF-e, e-mail e
reconciliação do drone **não têm teto de espécie alguma**, e para elas o `mem_limit` não é redundância:
é o único limite que existe.

**Por que o número da pendência (`2g`) estava errado — e é o erro que a regra do D57 previne.** A
ordem exigida é *freio que explica* → *freio que recicla* → *freio que mata*, e ela só vale se cada um
for maior que o anterior. O freio explicativo aqui é o `orcamento()` do impexp, cujo pior caso é
`IMPEXP_TETO_INFRA_MEMORIA_MB` = **2.048 MB** ([payment/planos.py](../payment/planos.py) — onde caem o
plano "Sob Medida" e o fail-open de token sem plano conhecido). O worker roda `--concurrency 2`, então
**dois** filhos podem segurar 2.048 MB ao mesmo tempo: 2 × 2.048 + o processo pai ≈ **4,25 GB de pico
legítimo**. `2g` fica abaixo do orçamento de **um só** filho — o cgroup mataria o container antes de o
`RLIMIT_AS` conseguir virar `MemoryError` → `RecursoExcedido`, reintroduzindo na frota geral exatamente
o defeito que o item 3 do D57 levou 7min06 para achar na frota de conversão. Um teto abaixo do
orçamento não é um teto apertado: é um teto que troca erro legível por processo morto.

**Aplicado:**

| Freio | Valor | Papel |
|---|---|---|
| `orcamento()` do impexp | ≤ 2.048 MB (do plano) | o único que vira frase para o cliente |
| `--max-memory-per-child` | `WORKER_MAX_MEM_KB` = 2.359.296 KiB (2,25 GiB) | recicla o filho que vazou; **acima** do orçamento, para operação legítima no teto não provocar reciclagem a cada task |
| `mem_limit` | `WORKER_MEM_LIMIT` = **5g** | protege a máquina e a fatura da VM. Invariante: 5 > 2 × 2,25 |
| `cpus` | `WORKER_CPUS` = 2 | casa com `--concurrency 2` |

**`mem_limit` é teto, não reserva:** 5g não ocupa 5 GB, limita a 5 GB — a estação e a VM só pagam o
que for usado. **Para apertar de verdade, o caminho é comercial e não de infraestrutura:** baixar
`IMPEXP_TETO_INFRA_MEMORIA_MB`, que é knob visível ao dono, e só então descer o `mem_limit` — nunca o
contrário, senão a ordem se inverte outra vez. Os três valores são env com default no compose, no
mesmo padrão dos `CONVERSAO_*`.

**Como foi verificado:** o compose parseia e os dois workers declaram a mesma forma de contenção. A
prova sob carga é a mesma do D57 e depende de subir a frota — fica para a próxima validação no stack
vivo, junto do PRA.5, que é o primeiro consumidor a mandar lote grande por esta fila.

### D76 — A importação síncrona estava quebrada: o objeto do formato ia onde se esperava o código · ✅ corrigido 08/08/2026

Achado em 08/08/2026 ao rodar a suíte do `funcoesimpexp` depois da **IE.3**. Quatro testes de
`ApiTests` falharam, e **não era regressão da fatia nova**: `git show HEAD` não tem sequer o parâmetro
`formato=` no `preparar`, então o defeito nasceu na **IE.2** (07/08, ainda não versionada), junto com a
detecção por assinatura de bytes do [D65](historico-correcoes.md).

`limites.validar_entrada` devolve um **`FormatoEntrada`**; `formatos.leitura.ler_bytes` despacha por
**string** (`if codigo == "csv"`). A `ImportarView` passava o objeto:

```python
formato = self._validar_upload(arquivo, teto)   # → FormatoEntrada
motor_importacao.preparar(..., formato=formato) # → ler_bytes(formato=FormatoEntrada)
```

Nenhum `==` casava, o fluxo caía no `raise LeituraInvalida("Formato não suportado…")` do fim do
`ler_bytes`, e o `preparar` o traduzia em lote com status **ERRO**. **Toda importação síncrona por
planilha nascia vazia** — a resposta era 201 com zero linhas.

**Por que passou:** o caminho de job (`_enfileirar`) e o `remapear` passam `formato.codigo`,
corretamente — só o síncrono passava o objeto. E o sintoma vestia a roupa de defeito do cliente: um
lote em ERRO dizendo "formato não suportado" sobre um `.csv` legítimo lê-se como arquivo estranho, não
como bug nosso.

**Corrigido em dois lugares, e o segundo é o que importa:** (a) a chamada passa `formato.codigo`;
(b) `ler_bytes` levanta **`TypeError`** — não `LeituraInvalida` — se receber algo que não seja `str`.
É a terceira reincidência da mesma lição ([D34](historico-correcoes.md), [D57](historico-correcoes.md)):
**quando um defeito nosso é reportado como defeito do arquivo do cliente, ninguém o acha.** Erro de
programação tem de falhar alto e no lugar errado, não virar mensagem plausível para o usuário.

**Como foi verificado:** suíte `funcoesimpexp` **111/111** no container (63 do IE.0/IE.2 + 48 da
IE.3); os 4 testes de `ApiTests` que denunciaram o defeito passam a exercitar o ciclo completo de
verdade — antes eles rodavam contra um lote em ERRO e mediam zero.

## 🟡 Médias — fechados

| ID  | Achado → correção                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | Status                                                             |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| S8  | backend não valida`iss`/`aud` do JWT e o DRF não tem throttling. **Corrigido 19/07:** a IAM já emitia `iss` e passou a emitir `aud`; o backend agora **exige** os dois (`ISSUER`/`AUDIENCE` no SIMPLE_JWT) — antes, qualquer token assinado com a mesma chave era aceito, viesse de onde viesse. Throttle do DRF (`anon`/`user` + `ScopedRateThrottle`) no backend e na IAM, com taxas por env; escopo `recuperacao` (30/h por origem) no endpoint público de senha, que complementa o teto de 5/h **por conta** — este não cobria rajada contra contas diferentes. A IAM ganhou cache Redis (DB 3) porque com o LocMem o teto valeria por worker do gunicorn. Testes `nucleo/test_s8_jwt_throttle.py` (6) + E2E phase5/6 no stack vivo.                                                                                                                                                                        | ✅ corrigido 19/07/2026                                            |
| S9  | PII em texto puro (CPF, endereço, dados bancários) sem mascaramento/criptografia/endpoints de titular → é a**Fase 9** (LGPD)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | ✅ mascaramento 05/07/2026 (Fase 9.C); endpoints de titular → 9.D |
| L8  | `AtualizarStatusNFView` grava status arbitrário; downloads de NF sem `timeout`. **Corrigido 16/07 (Fase 11.1):** status validado contra `StatusNFE.values` (400 se inválido); `_registrar_arquivos_nf` com `timeout=(5,30)` + nome via `urlparse().path`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | ✅ corrigido 16/07/2026                                            |
| L9  | Lote de remessa soma o**valor cheio** (usar `saldo_aberto`) e aceita título quitado/cancelado/duplicado (filtrar status + excluir já em lote ativo). **Corrigido 16/07:** `gerar-lote-remessa` soma o saldo em aberto, filtra `ABERTO/PARCIAL`, exclui título já em lote ativo (GERADO/ENVIADO/PROCESSADO) e devolve os `ignorados` (os elegíveis são materializados **antes** do `set()`, senão o próprio queryset — que exclui títulos em lote ativo — voltaria vazio depois de vincular). Testes `moduloerp.tests.L9LoteRemessaTests` (4), verdes sobre Postgres 17/07.                                                                                                                                                                                                                                                                                                                                            | ✅ corrigido 16/07/2026                                            |
| F4  | Rotas do ERP sem guard de módulo no front (403 cru) →`ModuleRoute`/`hasModule` com tela amigável. **Corrigido 13/07:** novo [`ModuleRoute`](../frontend/src/components/ModuleRoute.tsx) (layout guard por `hasModule`) envolve as rotas de ERP/CRM/RH; sem o entitlement, navegação direta por URL cai numa tela amigável ([`AccessNotice`](../frontend/src/components/AccessNotice.tsx)) em vez de 403 cru. Hub do ERP degrada o 403 de permissão (D3).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | ✅ corrigido 13/07/2026                                            |
| D7  | Recurso`erp.nf` não tinha `.edit` no catálogo → os 3 ViewSets de NF e `AtualizarStatusNFView` (POST→`.edit`) só passavam por admin; `ConsultarStatusNFView`, sendo **leitura**, exigia `.edit` indevidamente. Surgiu explícito ao remover o fallback de papel (fatia E). **Corrigido 12/07:** `erp.nf.edit` criado no catálogo (persona `fiscal` herda via `erp.nf.*`, `sync_authz` aditivo propaga no boot); `ConsultarStatusNFView` passou a exigir `erp.nf.view`. Testes `moduloerp.tests.D7NfApiViewPermissionTests` (4).                                                                                                                                                                                                                                                                                                                                                                                     | ✅ corrigido 12/07/2026                                            |

## 🟢 Baixas — fechados

| ID  | Achado → correção                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Status                  |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------- |
| A11 | Sem testes/CI — o L1 seria pego por um smoke test de 1 linha → pipeline mínima (Fase 10.5)*(v01-G2)*. **Corrigido 14/07:** GitHub Actions ([.github/workflows/ci.yml](../.github/workflows/ci.yml)) roda backend (Django+Postgres, RLS real), iam e frontend a cada push/PR.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | ✅ corrigido 14/07/2026 |
| F5  | Código morto/duplicado no frontend (duas gerações de páginas, dois`ObraDetailPage`) → remover a geração antiga *(v01-F4)*. **Inventário confirmado 25/07/2026** (nada disto é alcançável a partir de [App.tsx](../frontend/src/App.tsx)): (a) **ilha de obras** — `modules/obras/ObraDetailPage.tsx` e `ObrasListPage.tsx` na raiz do módulo (duplicatas das versões em `pages/`, que são as roteadas) + os `.module.css` de ambas; elas são as **únicas** consumidoras de todo `components/obra/**` (blueprint · documentslist · finances · ganttchart · interactivemap · kpidashboard · obratimeline · storage, com CSS) e de `hooks/useObraData.ts` — ~18 arquivos que só se referenciam entre si; (b) **avulsos** — `pages/AppStubPage.tsx`, `pages/Clientes.tsx`, `pages/Login.tsx` (a viva é `LoginPage.tsx`), `components/layout/MainLayout.tsx` + `Sidebar.tsx` (+CSS, substituídos pelo `AppShell`), `components/clientes/ClienteForm.tsx` (a viva é `modules/clientes/components/ClienteForm.tsx`), `modules/empreendimentos/pages/EmpreendimentosPage.tsx`, `modules/drone/pages/MapeamentoDronePage.tsx`. Sintoma de que a ilha está mesmo morta: `GanttChart.tsx` importa **`frappe-gantt`, que não consta do `package.json`** — só não quebra porque o `types/frappe-gantt.d.ts` satisfaz o `tsc` e o Vite nunca chega a resolver o módulo (nada o alcança). Esse `.d.ts` sai junto. *(Este `F5` é o da tabela — não confundir com o `### F5` da seção Altas, do `.gitignore`; colisão de IDs herdada dos dois laudos.)* **Corrigido 26/07/2026:** os 24 arquivos do inventário removidos (ilha de obras + avulsos + o `types/frappe-gantt.d.ts`). Antes de apagar, a inalcançabilidade foi **provada** por um grafo de imports a partir de `main.tsx` — resolvendo o alias `@`→`src/` do `vite.config.ts`, sem o qual quase todo o código vivo aparece como morto — que apontou **50 dos 313 arquivos** de `src/` fora do grafo e confirmou o inventário item a item. Efeito colateral que era o objetivo: **11 dos 45 erros de tipo do D27** morreram junto. `npm run build` (tsc+vite) limpo e imagem `react` rebuildada e servindo. **Sobraram fora do inventário** (inalcançáveis pelo grafo, NÃO removidos por não terem sido vetados no laudo): `App.css`, `assets/react.svg`, `components/common/{Button,Input,Modal,Table}`, `hooks/useFileUpload.ts`+`utils/fileUpload.ts`, `modules/clientes/hooks/useClientes.ts`, `modules/crm/{api/endpoints/interactions.ts,hooks/useInteractions.ts}` e — este merece decisão, não deleção — `modules/erp/{api/endpoints/lotesRemessa.ts,hooks/useLotesRemessa.ts}`, que é **feature pronta e nunca ligada na UI** (o backend do lote de remessa existe e foi corrigido no L9). | ✅ corrigido 26/07/2026 |
| C1  | **Calendário Fatia C (14/07):** lembretes de **série recorrente** só definidos na criação — editar "só esta"/"série" não os altera. **Corrigido 14/07/2026:** `update-recurrence` sincroniza `reminders` nos três escopos — `all` substitui os do mestre (valem p/ todas as ocorrências virtuais), `future` abastece o novo mestre e o truncado conserva os seus, `this` no override; ausência de `reminders` no payload **herda os do mestre** (novo `_reminders_for`), não perde aviso. Front parou de fazer `delete payload.reminders`. Testes `CalendarRecurrenceTests` (4 novos, suíte 25/25) + E2E vivo pelo gateway (all/this/future). Canal **WhatsApp** segue adiado (hoje in-app + e-mail).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | ✅ corrigido 14/07/2026 |
| C2  | **Calendário Fatia C (14/07):** suíte DB-backed + E2E/typecheck do sino pendentes na entrega (Postgres/Docker fora). **Validado 14/07/2026:** suíte **27/27** sobre Postgres (role `erp_app`, RLS real) — `modulocalendar` (reminders CRUD + `LembreteDispatchTests`) + `nucleo.test_notificacoes`; **typecheck** `tsc -b` limpo nos arquivos da Fatia C (os 33 erros restantes são do shell legado, fora da fatia); **E2E vivo pelo gateway** — evento com lembrete `[0]` → beat@60s + worker `despachar_lembretes` → `Notificacao` in-app (badge, texto, `marcar-todas-lidas`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | ✅ validado 14/07/2026  |
