# A fila da frota sob carga — o laudo da bancada

> Passada de **16/08/2026**, pelo [`manage.py simular_fila`](../../backend/nucleo/management/commands/simular_fila.py),
> contra o banco de dev, dentro de uma transação desfeita no fim. Exercita a política de admissão do
> [D98](../historico-correcoes.md) e a recolocação da PRA.11 com **261 arquivos** em cinco cenários.
> Versão navegável do mesmo conteúdo: [Laudo da Frota](https://claude.ai/code/artifact/86e79c76-8df6-492b-8834-1df802e15707).

## 1. Por que existe uma bancada além dos testes

Os 24 testes automatizados (`testes/backend/nucleo/test_frota.py` e `RetomadaDaConversaoTests`) provam a máquina de
estados **caso a caso** e ficam no repositório para falhar quando alguém quebrar a política sem
perceber. Eles não respondem à pergunta que a fila realmente levanta, que é **agregada**: com
duzentos arquivos de quatro empresas disputando oito vagas, a repartição sai como projetada ou o
comportamento emergente é outro?

Comportamento agregado se mede. É o mesmo motivo pelo qual o custo de conversão tem bancada própria
([custo-acervo-160.md](custo-acervo-160.md)) em vez de ser inferido de um teste unitário.

**Tudo é desfeito.** A bancada escreve centenas de linhas na fila e termina levantando `Rollback`
dentro do `transaction.atomic`. Resíduo aqui não seria sujeira de banco: seria trabalho que o próximo
boot do despachante tentaria enviar ao worker.

## 2. O resultado

| Camada | Onde | Itens | Resultado |
| --- | --- | ---: | --- |
| Testes da fila | `testes/backend/nucleo/test_frota.py` | 18 | OK |
| Testes da retomada | `moduloprancheta.tests.RetomadaDaConversaoTests` | 6 | OK |
| Bancada com carga | `manage.py simular_fila` | 5 cenários · 261 arquivos | OK |
| Suíte inteira do backend | `manage.py test` | 1.283 | OK exceto os 4 do [D50](../pendencias.md) |

## 3. Cenário A — 12 arquivos, 3 empresas, uma vaga

A frota de hoje (`--concurrency 1`). Doze arquivos chegam intercalados entre free, profissional e
empresarial.

```
Chegada:  A01-beta(prof) · A02-gama(empr) · A03-acme(free) · A04-beta(prof) · …

Fila resultante:
   [RODANDO]  A01-beta        profissional  prio=200
    1º        A02-gama        empresarial   prio=100
    2º        A05-gama        empresarial   prio=100
    3º        A08-gama        empresarial   prio=100
    4º        A11-gama        empresarial   prio=100
    5º        A04-beta        profissional  prio=200
    …
    8º        A03-acme        free          prio=300
   11º        A12-acme        free          prio=300
```

O empresarial que chegou em **11º** sai antes do free que chegou em **3º**, e dentro de cada classe
vale a ordem de chegada. **Com uma vaga só a fração degenera em ordem de prioridade**, e isso é o
comportamento correto numa frota mínima — não um limite do mecanismo.

## 4. Cenário B — a reserva existe, e é o que prioridade pura não faz

Trinta arquivos empresariais afogam uma frota de 10 vagas; quatro free chegam **por último**.

| Classe | Reserva | Em voo | Confere |
| --- | ---: | ---: | --- |
| premium | 5 (+3 livres) | 8 | ✅ não invadiu a reserva alheia |
| free | 2 | 2 | ✅ sentou chegando por último, atrás de 30 |

É o caso que separa **cadeira marcada** de **prioridade**. Com prioridade pura o free nunca sentaria:
haveria sempre um premium na frente. A reserva nos dois sentidos é o que faz "o free espera mais"
deixar de ser "o free espera para sempre".

## 5. Cenário C — o arquivo de 40 MB converge

Um arquivo pesado estoura o turno e volta à fila quinze vezes, com um arquivo leve novo chegando a
cada volta. As duas metades da decisão do dono precisam ser verdade **ao mesmo tempo**.

| Volta | Prioridade | Onde o pesado ficou |
| ---: | ---: | --- |
| 1 | 209 | retomou na hora (fila vazia) |
| 2 | 208 | 2º — 1 leve na frente |
| 5 | 205 | 5º — 4 leves na frente |
| 9 | 201 | 9º — 8 leves na frente |
| 10 | 200 | 9º — 8 leves na frente |
| **11** | **199** | **1º — ultrapassa** |
| 15 | 195 | 1º |

Da 2ª à 10ª volta a posição **cresce**: é o *"volta pro fim"*. Na 11ª a penalidade acumulada se
esgota e ele passa a ultrapassar os recém-chegados: é a *"prioridade crescente"*. Sem a primeira
metade ele furaria a fila já na volta 1 (o defeito da primeira implementação, que só tinha o degrau);
sem a segunda, ficaria atrás do fluxo de leves indefinidamente.

## 6. Cenário D — passar na frente não move ninguém de fora

O administrador da ACME sobe o último arquivo dela numa fila de 9, de três empresas.

| Arquivo | Empresa | Antes | Depois |
| --- | --- | ---: | ---: |
| D01-beta | beta | 1 | 1 |
| D02-gama | gama | 2 | 2 |
| D03-acme | **acme** | 3 | 6 |
| D04-beta | beta | 4 | 4 |
| D05-gama | gama | 5 | 5 |
| D06-acme | **acme** | 6 | 9 |
| D07-beta | beta | 7 | 7 |
| D08-gama | gama | 8 | 8 |
| D09-acme | **acme** | 9 | **3** |

**Arquivos de outras empresas que mudaram de posição: 0.** As posições 3, 6 e 9 continuam sendo as da
ACME; mudou quem está em cada uma. É permutação de lugares, e é o que torna o botão honesto — a
primeira implementação usava `criada_em − 1µs` e empurrava para trás qualquer tenant *entremeado*.

## 7. Cenário E — carga

Duzentos arquivos de quatro empresas, frota de 8 vagas.

```
Política para 8 vagas: 4 premium · 1 free · 3 livres
   em voo: premium=4 comum=2 free=2 (total 8 / 8)
   esperando: 192
```

Nenhuma vaga ociosa com 192 arquivos esperando — que é o que separa um porteiro de um gargalo —, as
três classes representadas, e **200 arquivos → 200 linhas**: a chave de idempotência segurou sob
volume.

## 8. A retomada sobre o acervo real — o que ela custa

> Passada de **16/08/2026** pelo [`medir_retomada.py`](../../ferramentas/medicao/medir_retomada.py) e
> [`medir_retomada_multi.py`](../../ferramentas/medicao/medir_retomada_multi.py), dentro do
> `worker-conversao` (a máquina dimensionada para converter), sobre **170 DWGs distintos** do acervo
> de medição — dedupe por tamanho, porque o mesmo desenho está copiado em várias obras.

### 8.1 A aferição direta

`01_LOTEAMENTO_PORTAL_RESIDENCE` (16,0 MB, 4 folhas), convertido de verdade com prazo curto para
forçar uma folha por passada:

```
--- baseline: uma passada, sem prazo ---
  4 folhas em 35.9s

--- com retomada ---
  passada 1: folhas [1] · 26.0s · faltam 3
  passada 2: folhas [2] · 32.6s · faltam 2
  passada 3: folhas [3] · 27.9s · faltam 1
  passada 4: folhas [4] · 28.6s · faltam 0

  relógio: 115.1s com retomada  ×  35.9s numa passada  →  3.20×
  numeração [1, 2, 3, 4], sem repetição nem perda:  True
```

**O mecanismo funciona com arquivo real** — a numeração atravessa as passadas, nada se repete e nada
se perde. E ele **custa 3,2×**.

**O que esse 3,2× é, exatamente: tempo de CÁLCULO — e cálculo é espera.** O cronômetro abre
imediatamente antes de `converter()` e fecha quando ela retorna; entre uma passada e outra o laço
chama o motor de novo na hora, sem fila, sem broker e sem despachante no meio. Então o que está
medido é CPU pura: 115,1 s contra 36,0 s. Isso **não** quer dizer que o cliente não paga — a prancha
não abre antes de a CPU terminar. Quer dizer que o 3,2× é o **piso** do que ele espera a mais, e a
espera real é maior:

| | CPU | espera do cliente |
| --- | ---: | --- |
| Uma passada | 36,0 s | 36,0 s + uma entrada na fila |
| Com retomada | 115,1 s | 115,1 s + **quatro** entradas na fila |

E há o efeito de segunda ordem, que é o pior: a cadeira fica ocupada 115 s em vez de 36 s, então
**quem está atrás na fila também espera 3,2× mais** por causa daquele arquivo. O custo não fica com
quem o causou.

A mesma janela alimenta o teto acumulado (`_recolocar` soma o `custo["segundos"]` do `medir()`, que
envolve só o `_rodar_a_escada`). Isso é coerente com a decisão — *o que a máquina paga é segundo de
CPU* —, e tem uma consequência que precisa estar escrita: **o teto limita o gasto, não a espera**. Um
arquivo pode ficar horas na fila sem chegar perto de `PRANCHETA_CONVERSAO_TOTAL_SEGUNDOS`.

**E o 3,2× é o pior caso forçado, não o que produção faz.** Cada passada recebeu um prazo já vencido,
para o motor emitir exatamente uma folha por vez — é assim que se mede o mecanismo. Sob o turno real,
este arquivo converte inteiro na primeira passada e nunca retoma (§8.5).

### 8.2 A conta, sobre 166 arquivos

| Grandeza | Mediana | Faixa |
| --- | ---: | --- |
| Folhas por arquivo | **1** | máx. 5 |
| Arquivos com mais de uma folha | **11%** | 19 de 166 |
| Custo **fixo** (repete a cada volta) | **56%** do relógio | 45% – 71% |
| Emissão de folha (o que a retomada pula) | 44% do relógio | — |
| Sobrecusto de uma folha por passada | **1,86×** | 1,55× – 3,06× |

Por número de folhas: 2 folhas → 1,56× · 3 → 2,06× · 4 → 2,55× · 5 → 2,92×.

**O custo fixo é o `dwg2dxf` + a leitura do DXF + a gravação da geometria**, e ele roda inteiro em
toda passada. O único trabalho que a retomada pula é a emissão das folhas — que é a **menor** metade
do relógio.

### 8.3 Erro de método, corrigido

A primeira passada de medição cronometrou só a *gravação* e tratou o resto do relógio como emissão,
derivando **1,35×** para um arquivo de 4 folhas. A aferição direta do §8.1 deu **3,20×**. A conta
estava errada porque o `dwg2dxf` e a leitura do DXF também repetem, e não estavam no custo fixo. A
segunda passada mede a **emissão** diretamente (`MotorDxf._folha`) e obtém o fixo por subtração — daí
os 56% da tabela. O número publicado é o da medição direta, não o da derivação.

### 8.4 O que isso significa para o produto

- **A retomada não economiza — ela troca "nunca terminar" por "terminar mais caro".** Isso continua
  sendo a decisão certa: a alternativa medida era o arquivo não sair. Mas o preço tem de ser dito.
- **Ela alcança 11% do acervo.** Oitenta e nove por cento dos arquivos reais rendem **uma folha só**,
  e num arquivo de folha única não há onde parar: o pipeline nem oferece prazo, e o comportamento
  segue o de sempre — estoura o teto, para tudo e explica.
- **O próximo ganho não é picar mais fino, é baratear o custo fixo.** Com 56% do relógio irredutível,
  nenhuma granularidade de checkpoint resolve o arquivo pesado. Quem resolve é a
  [PRA.1e](../roadmap.md) — trocar o renderizador pelo `dwg2SVG`, que emite cada bloco uma vez em vez
  de expandir a repetição (medido: 1.520 MB e 17,2 s contra 416 MB e 1,7 s).
- **O maior arquivo do acervo não chega à retomada.** O de 64,9 MB falha no `dwg2dxf`, antes de
  existir folha para gravar.

### 8.5 Sob o turno real, a retomada não dispara em nenhum arquivo do acervo

O prazo de uma passada é 80% de `PRANCHETA_CONVERSAO_SEGUNDOS` (300 s) — **240 s**. Nos 166 arquivos
que converteram, o mais lento levou **78,9 s**. Nenhum chega perto:

| Arquivo mais lento do acervo | 78,9 s | 33% do prazo |
| --- | ---: | ---: |
| Segundo mais lento | 57,5 s | 24% do prazo |
| Mediana | 6,6 s | 3% do prazo |

Isso não invalida o mecanismo — invalida a leitura de que ele já está pagando 1,86× em produção. Hoje
ele **custa zero**: é um seguro armado que ainda não foi acionado. Os 3,20× do §8.1 e os 1,86× do
§8.2 são o preço *quando* acionar, medido com prazo forçado. O arquivo que acionaria de verdade é o
de 64,9 MB, que morre antes no `dwg2dxf`.

Consequência prática: o número que precisa de estudo não é o sobrecusto — é o **turno**. 240 s contra
79 s de pior caso é folga de 3×; se o acervo do cliente tiver desenho maior que o nosso, é o turno que
decide se ele retoma ou se ele simplesmente demora.

### 8.6 Onde o tempo vai — decomposição por estágio

> Passada de **16/08/2026**, `worker-conversao`, quatro DWGs representativos, cronômetro em cada
> estágio do caminho (`MotorDwg._para_dxf`, `MotorDxf._ler`, `MotorDxf._gravar`, `MotorDxf._folha`).

| Arquivo | `dwg2dxf` | ler DXF | gravar | emitir folhas | total |
| --- | ---: | ---: | ---: | ---: | ---: |
| `01_LOTEAMENTO_PORTAL_RESIDENCE` | 5,5 s (15%) | 11,1 s (31%) | 3,6 s (10%) | 14,5 s (40%) | 36,0 s |
| `ESGOTO_2023` | 5,2 s (9%) | 14,9 s (26%) | 5,7 s (10%) | 29,6 s (52%) | 56,8 s |
| `04-Nova_Area_Industrial_MaxPlast` | 8,7 s (15%) | 14,6 s (25%) | 8,3 s (14%) | 25,2 s (44%) | 57,5 s |
| `02_PROJETO_TERRAPLANAGEM_JRL` | 5,9 s (20%) | 9,5 s (32%) | 5,7 s (19%) | 8,4 s (28%) | 29,8 s |

Os quatro estágios somam 96%–99% do relógio; o resto é abrir arquivo e sanear.

**Não há um culpado único.** Nenhum estágio passa de metade. Mas dois deles concentram 60%–78%: a
**leitura do DXF intermediário** e a **emissão das folhas**. E cada um tem uma causa medida:

- **Ler o DXF custa caro porque o DXF é enorme.** O caminho é `DWG binário → DXF ASCII → objetos
  Python`, e a conversão infla o arquivo:

  | DWG | DXF intermediário | |
  | --- | ---: | ---: |
  | `01_LOTEAMENTO_PORTAL_RESIDENCE` 16,0 MB | **81,9 MB** | 5,1× |
  | `ESGOTO_2023` 16,2 MB | **88,2 MB** | 5,4× |

  São ~85 MB de texto que o `ezdxf` — Python puro — lê linha a linha e transforma em um objeto por
  entidade. Os 25%–32% do relógio são isso.

- **Emitir as folhas custa caro pelo motivo já registrado na [PRA.1e](../roadmap.md):** o nosso
  caminho expande cada inserção de bloco em geometria própria, enquanto o `dwg2SVG` emite o bloco uma
  vez e o referencia com `<use>`. É a mesma causa que produz 1.520 MB e 17,2 s contra 416 MB e 1,7 s
  na comparação daquele item.

**A conclusão converge com a do §8.4, agora com o porquê.** A PRA.1e não corta um estágio: ela corta
**três**. Indo do DWG direto ao SVG, não existe DXF intermediário para escrever (`dwg2dxf`, 9%–20%),
não existe DXF para o Python ler (25%–32%), não existe gravação em `Recorder` (10%–19%) — e a emissão
que sobra é a barata, a que referencia o bloco em vez de repeti-lo. Os 56% de custo fixo do §8.2 não
são irredutíveis por natureza: são irredutíveis *neste caminho*.

**O que esta decomposição não faz:** ela para na fronteira de cada estágio. Não abre o `ezdxf` por
dentro, nem separa, dentro da emissão, quanto é expansão de bloco e quanto é escrita de SVG.

## 8.7 O maior arquivo do acervo: o teto era nosso

Rodando o `dwg2dxf` **sem o nosso orçamento de memória** sobre o DWG de 64,9 MB:

```
dwg2dxf: saída 0  →  DXF de 531,8 MB   (8,2× o DWG)
```

O LibreDWG converte. Quem o mata é o `PRANCHETA_SUBPROCESSO_MEMORIA_MB` (2.048 MB), em 9,7 s. Isso
**corrige** o que o §8.4 desta mesma página dizia — *"falha no `dwg2dxf`"*, lido como limite do
decodificador. É teto nosso, virou degrau de plano ([D101](../historico-correcoes.md)), e o degrau de
cima depende de crescer a máquina ([D103](../pendencias.md)).

## 9. O que esta medição NÃO diz

Três limites, e nenhum é defeito — é o contorno do que foi medido.

- **As frações são arbitradas, não medidas.** 50/20/30 faz o mecanismo funcionar como projetado (§4 e
  §7); não diz se é a repartição certa para o negócio. O estudo que responde isso está especificado
  em [`payment/planos.py`](../../payment/planos.py) §5.4c: distribuição de plano na base, tempo
  mediano e de cauda por plano — que é o que converte "cadeira" em minutos de espera, a única unidade
  que o cliente sente — e o tamanho real da frota.
- **A frota em produção tem uma vaga.** Os cenários B e E rodaram com 10 e 8 para provar que o
  mecanismo escala; essa frota ainda não existe. Abaixo de ~5 vagas toda fração arredonda para zero.
- **Quantas voltas um arquivo de 40 MB pede, ninguém ainda sabe.** O §8 mediu o *sobrecusto por
  volta* sobre o acervo, mas o acervo de medição não tem um arquivo que exija muitas passadas sob o
  turno real de 300 s: o mais lento converte inteiro em 79 s. O
  `PRANCHETA_CONVERSAO_TOTAL_SEGUNDOS` continua sendo um número escolhido (6 turnos), não medido — e
  o arquivo que o testaria é justamente o de 64,9 MB, que morre antes, no `dwg2dxf`.

## 10. Como a indústria resolve isto — pesquisa de 16/08/2026

> Pedido do dono: *"faça uma pesquisa para ver se realmente isso é o modo como os softwares
> trabalham"*, sobre o desenho que ele descreveu — arquivo pesado em standby, sem gastar CPU nem RAM,
> só armazenamento, enquanto os leves passam na frente.

| Padrão | Quem faz | Mecanismo |
| --- | --- | --- |
| **Faixas separadas por tamanho** | [SPLIT (arXiv)](https://arxiv.org/pdf/2605.13749) e prática corrente | servidores dedicados a jobs grandes; nos pequenos, ordem por menor tempo restante — porque FCFS deixa o grande bloquear quem chega |
| **Fatiar em unidades independentes** | transcodificação de vídeo ([Wikimedia T158716](https://phabricator.wikimedia.org/T158716), [US2013/0114744](https://patents.google.com/patent/US20130114744)) | 2 h viram 12 pedaços de 10 min, cada um uma tarefa curta, remontados no fim |
| **Preemptar e recomeçar do zero** | [SLURM `PreemptMode=REQUEUE`](https://hpcf.umbc.edu/ada/slurm/preemption/) | volta para a fila e **recomeça** |
| **Preemptar salvando estado em disco** | [SLURM + DMTCP](https://arxiv.org/html/2407.19117), [CRIU](https://criu.org/Main_Page), [Abaqus restart](https://hpckp.org/articles/enabling-abaqus-checkpointing-and-restart-slurm-workload-manager/) | continua de onde parou |
| **Não prometer justiça** | [Autodesk Model Derivative](https://aps.autodesk.com/en/docs/model-derivative/v2/developers_guide/basics/translation) | assíncrono, faça polling; "modelos grandes levam 5–10 min" |

**O desenho do dono é real e tem nome** — preempção com checkpoint/restart. Não é invenção.

**Mas é o mais raro e o mais caro dos cinco.** A documentação do SLURM descreve exatamente a nossa
situação: o job requeued *"começa do início, a menos que o cálculo seja capaz de fazer checkpoint"*, e
o SLURM *"não faz checkpoint automaticamente; tem de ser implementado pelo usuário no próprio
código"*. Nós somos esse usuário — a PRA.11 implementou a metade barata (retomar entre folhas) e não
a cara (guardar o estado). Daí os 56% de custo fixo.

**E salvar estado não é de graça:** o tempo de checkpoint do CRIU é **linear no tamanho da memória**.
É o número que falta, e é o [D104](../pendencias.md).

**A resposta dominante da indústria para o nosso problema é fatiar, não suspender — e aqui está por
que ainda não serve para nós.** Um segmento de vídeo é decodificável sozinho; a nossa folha **não**
é: ela depende de um documento inteiro carregado, e esse carregamento *é* os 56%. Enquanto isso for
verdade, fatiar mais fino só multiplica o custo fixo. É a mesma conclusão da PRA.1e chegando por um
terceiro caminho — depois do §8.4 (custo fixo) e do §8.6 (decomposição por estágio).

## 11. O que mudou depois desta medição

| Achado desta página | O que foi feito |
| --- | --- |
| Ceder a vez com a fila vazia custa 56% do relógio à toa (§8.2) | [D102](../historico-correcoes.md) — o motor só cede se `frota.ha_espera`; o teto duro da passada passou a ser o que resta do acumulado |
| O 64,9 MB morre no nosso orçamento, não no LibreDWG (§8.7) | [D101](../historico-correcoes.md) — memória virou degrau de plano; [D103](../pendencias.md) — o degrau de cima espera a máquina crescer |
| Guardar estado em disco é o caminho caro, e sem número (§10) | [D104](../pendencias.md) — variável desligada em `planos.py` §5.4e, a medir perto do lançamento |
| Três dos quatro estágios somem com o `dwg2SVG` (§8.6) | PRA.1e promovida a prioridade pelo dono (16/08/2026) |
