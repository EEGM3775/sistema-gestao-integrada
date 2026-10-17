# Pendências — achados de revisão em aberto

> **Natureza: status.** Este documento lista **só o que está quebrado ou em risco** — nada mais.
> Achado corrigido **sai daqui** e vai inteiro para [historico-correcoes.md](historico-correcoes.md);
> limite consciente e decisão de desenho vão para a **planta** do módulo; trabalho planejado vai para
> o [roadmap.md](roadmap.md). Guardar as três coisas aqui foi o que fez este arquivo chegar a 251 KB.
>
> IDs: `S*` segurança · `L*` bugs de lógica · `A*` backend/arquitetura · `F*` frontend ·
> `D*` achados de auditoria posteriores. Herdados dos dois laudos de 02/07/2026 (v01 segurança,
> v02 bugs/arquitetura/frontend), já absorvidos.

**Onde foi parar o que saiu daqui:**

| O que                                | Para onde                                                  | Por quê                                                                  |
| ------------------------------------ | ---------------------------------------------------------- | ------------------------------------------------------------------------- |
| 148 achados corrigidos               | [historico-correcoes.md](historico-correcoes.md)            | Corrigido não é pendência — é histórico                             |
| D29 · D30 · D32 (Maps)             | [modulos/modulomaps.md](modulos/modulomaps.md)              | Desvio consciente da planta, com gatilho de reabertura                    |
| D35 · D36 · D37 · D55 (Prancheta) | [modulos/moduloprancheta.md](modulos/moduloprancheta.md)    | Limite declarado do desenho, não defeito                                 |
| D74 (antivírus)                     | [modulos/funcoesimpexp.md](modulos/funcoesimpexp.md)        | Decisão do dono, adiada com método definido                             |
| D6 · D13 · D60 + backlog de ideias | [roadmap.md](roadmap.md)                                    | Trabalho planejado, não achado                                           |
| Decisões do Orçamento              | [modulos/moduloorcamento.md](modulos/moduloorcamento.md)    | Decisão de módulo                                                       |
| D185 (base referencial fora do dev)  | [modulos/funcoesimpexp.md](modulos/funcoesimpexp.md) §13.1 | Resolvido: pacote da base (DMS.1); a base entrou no staging em 03/10/2026 |

---

## ⏸ Adiados para o final do desenvolvimento

**Não trabalhar agora** — são pré-produção ou decisão comercial, e o projeto está em dev. Os relatos
continuam abaixo, onde estão; a ordem do que fazer agora está em [roadmap.md](roadmap.md#foco-atual--desenvolvimento).

| Achado                                                                               | Natureza                                          |
| ------------------------------------------------------------------------------------ | ------------------------------------------------- |
| D258 (contêiner como root) · D113 (manual de produção) · D230 (HarfBuzz-Subset) | Endurecimento e operação                        |
| D239 · D245 (CNAB homologado em banco; instrução 06)                              | Homologação bancária                           |
| D86 · D103 · D104 · D105 · D114 · D124                                          | Número de plano, preço e capacidade do servidor |
| D39 (formatos geo vendidos sem motor)                                                | Decisão do dono: manter                          |

---

## 🔴 Críticos

Nenhum em aberto. O **D76** — o orçamento de memória que media o processo e matava toda importação em
todo plano — foi achado e fechado em 08/08/2026, no mesmo dia; relato em
[historico-correcoes.md](historico-correcoes.md).

O crítico anterior foi o **D57** — a conversão sem teto de recurso, que levou uma passada
de medição a 62 GB de RAM —, fechado em 07/08/2026 pela PRA.1d; relato inteiro em
[historico-correcoes.md](historico-correcoes.md). O resíduo que ele deixou — **D61**, os 11 arquivos
que estouravam o orçamento mesmo no degrau — **fechou em 08/08/2026 pela remedição**, e não por
decisão de produto: eram consequência do teto que o D76 consertou. O outro — **D71**, o teto de
contêiner que faltava na frota geral — foi fechado em 07/08/2026, também no histórico.

## 🟠 Altas

A1 - Verificação sobre uso de hardware
Uma observação: o ERP no servidor roda com o comando padrão da imagem, `gunicorn` com  **1 processo síncrono** , e não com os 2 processos × 4 threads do `base.yml`. Com mais gente usando ao mesmo tempo, isso pode voltar a deixar o sistema lento.

### D294 — conceder acesso a uma entidade "muda quem pode", mas ficou na classe B · 🟡 aberto 14/10/2026

`cadastro.entidade.conceder` dá a alguém o financeiro de outro CNPJ — é da família de `plataforma.papel.gerir`,
que está nos atos críticos (classe C: sem cache, nega com o PDP fora). A lista da classe C foi fixada pelo dono
(`funcoesautorizacao/classes.py`) e não se estende sem mudar a planta antes; por isso ficou em B. Nenhum papel
padrão recebe a permissão — só o administrador concede.

**Caminho:** decisão do dono — pôr `cadastro.entidade.conceder` na classe C (planta §10.8 e `CRITICOS`).

### D289 — o cookie `__Host-sgi_sessao` não é preso ao dispositivo, e não há tela de sessões ativas · 🟠 aberto 13/10/2026

Revisão da sessão do BFF (`iam/identity/sessoes.py`, `models.Sessao`, `iam_project/settings.py`).
**O que está certo:** cookie `HttpOnly` + `Secure` + `SameSite=Strict` + `__Host-`; credencial de 256 bits
guardada só como hash; o nginx tira o cookie antes dos serviços; logout, troca de senha, desativação e
"encerrar todas" revogam no servidor e no Redis; janela de 2 h/12 h (7 d/30 d com "manter conectado"); CSRF
por `X-SGI-CSRF`; step-up por `auth_time`/`amr`.

**O que falta:**

1. A `Sessao` não guarda user-agent nem IP. Quem copiar o valor do cookie (tela compartilhada, DevTools colado
   em chat, malware) usa a sessão de outro computador, sem alerta, até ela expirar ou ser revogada. A detecção
   de reuso só pega o ladrão se a pessoa legítima também estiver usando (comentário em `settings.py:245`).
2. Sem tela "Meus dispositivos" (listar e encerrar sessões) — só o backend foi lido; conferir o frontend.
3. Cabeçalhos de resposta duplicados (`X-Frame-Options` DENY e SAMEORIGIN, `Strict-Transport-Security`,
   `X-Content-Type-Options`, `Referrer-Policy`): duas camadas (nginx e Django) emitem o mesmo. Sem risco, mas
   deixar uma só responsável.

**Caminho:** guardar hash do user-agent (e IP de criação) na `Sessao` — migration no IAM — e derrubar a sessão
quando o user-agent mudar; tela de sessões ativas; unificar os cabeçalhos.

### D39 — Os planos vendem 6 formatos geo, e o motor `gdal` não tem adaptador · 🟠 aberto

Achado ao escrever o PRA.8, e ele importa porque é o único desta leva com consequência para **quem
já paga**.

[`payment/planos.py`](../payment/planos.py) inclui `kmz` e `geojson` no plano **`basico`** — com o
comentário dizendo, nas próprias palavras, *"já cobrem o construtor pequeno, que recebe DXF do
projetista **e KMZ do topógrafo**"* — e o `profissional` acrescenta `shp`, `gpkg`, `qgis` e
`geotiff`. Mas [`motores/`](../backend/moduloprancheta/motores/__init__.py) tem quatro adaptadores
(`documento`, `dxf`, `dwg`, `ifc`) e **nenhum `gdal`**: o arquivo passa o paywall, sobe, consome
`storage_projeto_gb` e gera **zero derivadas**.

**Não é desonestidade do código** — e é por isso que é 🟠 e não 🔴. `planejar()` devolver lista vazia
é caminho previsto e documentado ali mesmo; `estado_dos_motores()` declara `implementado: false`; o
`conversao` do acervo responde `outro_modulo`, que é estado diferente de `sem_motor` justamente para
não dizer "tudo certo". O teste [pra8_prancheta_test.py](../testes/e2e/pra8_prancheta_test.py)
passou a **cobrar** essa declaração (§1), para a lacuna não virar silêncio. O problema é comercial: o
plano de entrada vende metade do caso de uso que o próprio comentário descreve.

**Duas saídas, e a escolha é de produto, não de engenharia:**

- **fechar o seam** (é a **PRA.7**): KMZ/SHP na Prancheta vira `Camada` no [Maps](modulos/modulomaps.md),
  que é o dono do dado geo (planta §3 — "a Prancheta abre, o Maps guarda"). Esbarra num nó: o Maps
  tem entitlement próprio, e o cliente `basico` provavelmente não o assina;
- **recuar no plano**: tirar os formatos geo de `formatos_prancheta` até o seam existir. Barato,
  reversível, e alinhado com a régua — melhor não vender do que vender travado.

Enquanto nenhuma das duas acontece, o teste que casa registry × planos
(`RegistryEPlanosTests`) **não pega isto**: ele confere que o formato existe e que o *tier* de motor
bate, e `gdal` é `livre`, que o plano habilita. Falta a terceira pergunta — *o motor tem adaptador?*

### D53 — A folha do projeto executivo pesa 13,6 MB e converte em 26 s · 🟠 aberto

Consequência direta do **D52**, e ela é honesta: enquanto o desenho era destruído na emissão
(coordenadas arredondadas a zero na grade esticada), o SVG era pequeno **porque estava perdendo
traço**. Com a folha certa a geometria é emitida inteira e pesa o que pesa.

Medido no `MaxPlast.dwg` (62.433 entidades no modelspace): folha #1 sai com **13,6 MB** e a conversão
leva **26 s**. A conversão é assíncrona e não faz ninguém esperar — o problema é o **download**: 13,6
MB no 4G do canteiro é justamente o cenário para o qual o módulo existe.

**Não é bug do recorte, é o teto do formato de entrega.** Um SVG descreve cada segmento em XML, com
coordenadas em texto; o mesmo desenho num buffer binário de coordenadas é uma fração disso, carrega
direto em GPU e dispensa parsear. É a fatia do render vetorial
([planta §12.6](modulos/moduloprancheta.md)), que já estava decidida por outros dois motivos (zoom sem
teto e snap) — este é o terceiro, e é o que mais aperta.

Enquanto isso não chega, o número está declarado e o acervo típico não sofre: a prancha de disciplina
comum (`UFRB…-IE`, 35.401 traços) sai com 3,4 MB.

## 🟠 Altas

### D189 — a ocorrência de segurança não entra na trilha de LGPD, e entrar do jeito de hoje apagaria prova legal · 🟠 aberto 20/09/2026

Achado ao fechar a PDCA.8, que trouxe a **primeira PII do grupo `pdca`**: `Ocorrencia` guarda nome de
acidentado, parte do corpo, natureza da lesão, CID-10 e dias de afastamento — art. 11 da LGPD, vizinho
de porta do ASO.

`nucleo/lgpd.py` enumera os titulares e os modelos relacionados em `TITULARES`. **A `Ocorrencia` não
está lá**, então ela não sai na portabilidade nem no relatório de titular. O lugar natural seria
`relacionados_pii` do `funcionario`, pelo FK `acidentado` — e é aí que a coisa trava.

**Entradas de `relacionados_pii` são APAGADAS, não anonimizadas.** O
`anonimizar` faz `.delete()` sobre cada modelo relacionado (`lgpd.py`, a segunda varredura da lista).
Registrar a ocorrência ali faria um pedido de esquecimento **destruir o registro de um acidente de
trabalho** — que é exatamente o que a lei manda guardar: a CAT tem retenção previdenciária, e o próprio
art. 16, I da LGPD ressalva a guarda para cumprimento de obrigação legal. O pedido de um titular
apagaria a prova de que a empresa comunicou o acidente dele.

**Não foi resolvido dentro da fatia de propósito**: o conserto não é uma linha no dicionário, é dar ao
`lgpd.py` uma terceira categoria — o relacionado que **anonimiza em vez de apagar** —, e isso muda o
comportamento de todos os titulares, não só deste. É mudança de fundação, e a decisão de como tratar
dado sensível com retenção legal obrigatória é do dono.

**Enquanto isso, o que vale:** a ocorrência **não** é exportada nem esquecida, e este parágrafo é o
registro de que a ausência é conhecida. O mascaramento por permissão (`pdca.ocorrencia.dado_medico`)
funciona e está testado — o que falta é o outro lado, o do titular.

---

### D183 — a carga real herda o rótulo da publicação que substituiu · 🟠 aberto 16/09/2026

Causa em código do [D181](historico-correcoes.md), cujos **dados** já foram limpos. Em
[`carga.py:730`](../backend/moduloorcamento/carga.py) e no gêmeo de
[`importar_base_referencial.py`](../backend/moduloorcamento/management/commands/importar_base_referencial.py):

```python
if not base.rotulo:
    base.rotulo = base.rotulo_automatico()
```

A publicação é encontrada por `get_or_create` na chave `fonte+uf+mês+regime`. Quando uma carga real
cai sobre uma publicação que **já existe** nessa chave, o conteúdo é trocado inteiro e o rótulo
**não**. Foi assim que "SINAPI SP 08/2026 desonerado — DEMONSTRAÇÃO" passou a descrever 4.886 insumos
de SINAPI verdadeira, e ninguém tinha como saber olhando a tela.

A guarda não é ingênua: ela protege o `--rotulo` que alguém escolheu à mão, e sobrescrever cegamente
destruiria essa escolha. O problema é que **não existe como distinguir** "o usuário nomeou esta
publicação" de "uma semente de demonstração escreveu este texto" — é um campo só, sem procedência.

→ Decidir entre: (a) reescrever o rótulo sempre que a carga substituir o conteúdo, e aposentar o
`--rotulo` (o nome automático já é completo e nunca envelhece); (b) um campo de procedência
(`rotulo_manual`) que diga quem escreveu, e só preservar o que veio de gente; (c) deixar como está e
tratar rótulo herdado como responsabilidade de quem carrega. **(a) é o menor**, e o
`rotulo_automatico()` já é a fonte de verdade que a tela usa quando o campo está vazio.

### D184 — SINAPI de 01/2026 e 02/2026 não entrou: a URL da Caixa devolve HTML, não o ZIP · 🟠 aberto 16/09/2026

Das 20 competências carregadas em 15/09/2026 (01/2025 a 08/2026, 27 UFs × 3 regimes = 81 publicações
por mês), **duas faltam**. As cargas 30 e 31 registraram:

```
url  = https://www.caixa.gov.br/Downloads/sinapi-relatorios-mensais/SINAPI-2026-01-formato-xlsx.zip
lido = 295.035 bytes
erro = O arquivo não é um ZIP nem uma planilha .xlsx.
```

Baixou ~295 KB de **alguma coisa** que não é o pacote — quase certamente a página que o anuncia, ou
um aviso do WAF. O padrão de URL vale para os outros 18 meses, então não é o template: é aquele
artefato específico que não está onde os demais estão. É exatamente a distinção que o histórico de
cargas existe para registrar ("o WAF cortou" × "o mês não saiu" × "o layout mudou"), e aqui ela ainda
não foi feita.

**Consequência prática:** quem orçar com data-base de janeiro ou fevereiro de 2026 — data de edital é
quase sempre passada — não acha a publicação e cai em outro mês, mudando o custo sem perceber.

→ Conferir a URL real na página da Caixa e, se o pacote existir, rodar o plano B do comando, que não
depende do download:

```
manage.py carregar_base_oficial --fonte sinapi --mes 2026-01 --arquivo /tmp/SINAPI-2026-01.zip
```

### D179 — o ajuste de vencimento só conhece feriado onde a base foi sincronizada e o lote foi geocodificado · 🟠 aberto 16/09/2026

O dia útil bancário entrou em 16/09/2026 ([D169](historico-correcoes.md)), e ele **depende de duas
coisas que não são código** — as duas têm degradação declarada na tela, nenhuma tem ação tomada:

1. **A tabela `Feriado` é global e nasce vazia.** Quem a enche é `manage.py sincronizar_feriados`.
   Sem ela, o vencimento desvia de sábado e domingo e **não** de feriado. As respostas de
   `simular/`, `previa-parcelas/` e `gerar-parcelas/` trazem `calendario.feriadosCarregados`, e a
   tela escreve a ressalva — mas o carnê emitido nesse estado tem parcelas vencendo em 25/12.
   **Ação:** rodar o comando nos ambientes vivos e confirmar que o beat
   `calendar-sincronizar-feriados` está de pé em produção.
2. **O feriado municipal exige o código IBGE, e ele vem do Maps.** `Empreendimento` guarda cidade e
   UF em texto, e nome de cidade não é chave (existem quatro "Bom Jesus"). O código sai do `Local` do
   empreendimento, preenchido pela cascata de geocodificação. Empreendimento sem `Local` — ou com
   `Local` que ainda não resolveu o município — cai em nacional + estadual, e a resposta **diz**
   (`calendario.municipio: false`). **Ação:** rodar o backfill de `Local` dos empreendimentos, ou
   decidir por um campo `ibge` em `Empreendimento` (troca a dependência do Maps por um dado
   digitado — decisão do dono).

Não é defeito do cálculo: é alcance dele. Fica aqui porque a diferença entre "ajustado para o
próximo dia útil" e "ajustado, menos pelos feriados" é dinheiro entrando no dia errado.

---

### D160 — a folha separada costuma ser um traço perdido, não outro desenho · 🟠 aberto 16/09/2026

Achado ao medir o acervo a pedido do dono (item 24), e ele é a **causa** do item 31 — *"arquivos com
distâncias muito grandes entre desenhos, onde o desenho é separado. Quero desfazer essa separação."*

O `_agrupar` corta onde o vazio supera o desenho e **emite toda ilha como folha**, sem piso de
substância. Nos três arquivos do acervo que se separam em duas folhas, a segunda é resíduo:

| Arquivo                          | folha 1                                | folha 2                                                   | `viewBox` declarado |
| -------------------------------- | -------------------------------------- | --------------------------------------------------------- | --------------------- |
| `Sensor de Incendio.dwg`       | 129 traços, em (−559.725, 8.568.639) | **1 traço**, em (731, 200)                         | 371 × 226            |
| `Loteamento Park Ville R8.dwg` | 5.955 traços                          | **1 traço** de 9,5 × 7,3 a 18.431 de distância   | 7.006 × 3.392        |
| `ESGOTO 2023.dwg`              | 25.247 traços                         | **39 traços** de 99 × 330, a 42.815.267 no eixo Y | 467.288 × 8.557.859  |

Repare no `Sensor de Incendio`: o desenho **real** (129 traços) é o que está a 8,5 milhões de unidades
da página declarada, e o traço solto é o único que cai dentro dela. Não são dois desenhos distantes —
é um desenho e um resto que o conversor largou longe (ver o **D159**).

**Por que não foi consertado junto.** As duas saídas óbvias são ruins e a escolha é do dono:

1. **Absorver o resíduo na folha maior** parece o "desfazer a separação" literal, e é o pior dos dois:
   a envolvente da folha passaria a incluir um ponto a 42 milhões de unidades, e a página volta a ser
   quilométrica — exatamente o que a PRA.1c existe para impedir.
2. **Não promover o resíduo a folha** (piso de substância: uma ilha com menos de X% dos traços da
   maior não é desenho) resolve os três casos e preserva o caso legítimo do `confrontantes.dwg`, que
   tem 169 traços de cada lado. Mas implica **descartar geometria do cliente**, e o descarte precisa
   ser declarado como o `_tem_traco` e o `desenhos_truncados` já fazem.

O que foi entregue enquanto isso é a vista de conjunto do **D158**, que resolve o sintoma sem tocar
em geometria: as folhas voltam a aparecer juntas, no lugar em que estão.

Bancada: `ferramentas/medicao/` (o aferidor do D159 imprime as caixas por folha).

---

### D159 — o critério que escolhe o deslocamento do símbolo não decide em 80% do acervo · 🟠 aberto 16/09/2026

Pedido do dono (15/09/2026): *"Pranchetas tem uma função de deslocamento, testar vários dwg para
saber se esse deslocamento tá certo."* Medido sobre **159 DWGs** do acervo real + os 6 difíceis.

**O que passou.** A derivação está certa e é robusta: o `viewBox` foi legível em **159/159** arquivos,
e onde a correção se aplica ela acerta **exatamente** — nos símbolos afetados o centro vai de 4.541,5
para **0,0**, não "para perto de zero". A correção piorou o enquadramento em **2 de 148** arquivos com
símbolo, e marginalmente (0,6% → 0,0% e 1,7% → 1,1%, os dois já quase nulos).

**O que reprovou.** O docstring do `deslocamento_dos_simbolos` justifica a escolha por símbolo assim:
*"a diferença é de seis ordens de grandeza — não há empate a arbitrar"*. Isso vale para o arquivo de
referência de 10/08/2026 e **não vale para o acervo**: em **118 dos 148** arquivos (80%) existe ao
menos um símbolo em que as duas leituras ficam a menos de 10× uma da outra, com a vencedora ainda
acima de 1% da folha. Exemplo medido em `JAMYLLE E PAULO_plantas executivas_R03.dwg`, cujo `viewBox`
tem 4.794 unidades de largura e o deslocamento derivado é de 2.193:

| Símbolo     | \|centro\| cru | \|centro\| deslocado | razão         |
| ------------ | -------------- | -------------------- | -------------- |
| `…1933CC` | 36.047.303,5   | 36.047.458,7         | **1,00** |
| `…247DC7` | 9.139.564,9    | 9.139.720,2          | **1,00** |
| `…80207`  | 4.541,5        | **0,0**        | ∞             |

Os dois primeiros estão a dezenas de milhões de unidades de uma folha de 4,8 mil: o deslocamento de
2,2 mil não muda nada, e o critério "fica com o mais perto de zero" está sorteando entre duas
respostas igualmente erradas. Não é que a correção erre — **ela não alcança esses símbolos**, e o
docstring afirma uma garantia que o acervo não sustenta.

**O que fazer:** (a) corrigir a afirmação do docstring, que hoje autoriza confiança indevida;
(b) decidir o que fazer com símbolo que fica longe **nas duas** leituras — provavelmente declarar na
memória de conversão, como `blocos_ausentes` e `xrefs_ausentes` já fazem, porque hoje eles somem
dentro da envolvente e produzem o **D160**.

Bancada: `aferir_deslocamento.py` (roda em container com `dwg2SVG`; imprime símbolos, deslocados,
empates graves e a fração de geometria dentro do `viewBox` antes/depois).

---

### D161 — o de-para do D111 congelou uma resposta que a fonte já passou a dar, e discorda dela · 🟠 aberto 16/09/2026

Auditoria pedida pelo dono (item 34), feita no banco vivo em 16/09/2026.

**O que está certo.** O de-para de 14 linhas continua aplicado e íntegro (10 `encargos_complementares`

+ 4 `equipamento`). Varrendo os **90** itens SINAPI do catálogo contra a classificação da publicação
  01/2025, a **única** divergência são esses 10 — nenhum item nasceu torto depois de 21/08.

**O que mudou por baixo.** O próprio arquivo declara: *"Some quando uma publicação 2025+ da mesma
fonte for importada"*. Esse gatilho **já foi atingido** — as três publicações `SINAPI BA 01/2025`
(onerado, desonerado, sem encargos) estão carregadas e classificam **4.220/4.220** insumos, contra
**0/4.811** da BA 10/2024. O caminho 1 do D111 deixou de estar aberto; ele foi percorrido pela ORC.8 e
o registro não acompanhou.

**E a fonte discorda do de-para em 10 das 14 linhas.** A SINAPI 01/2025 classifica EPI, ferramenta,
alimentação, transporte, exame e seguro como **MATERIAL**; o de-para os declara **ENCARGOS
COMPLEMENTARES**. Como declaração da empresa vence a fonte, o CSV hoje **sobrepõe** a resposta da
SINAPI — e sobrepõe em silêncio, porque foi escrito quando a fonte não respondia nada. Para o encargo
social não muda (nem material nem encargos complementares recebem os 84,70%); muda a leitura material
× mão de obra × equipamento na composição por natureza, na curva ABC de insumos e no Controlar.

**Dois achados menores, da mesma varredura:**

- **O código `13458` (COMPACTADOR DE SOLOS DE PERCUSSÃO) não existe na BA 01/2025.** É item em uso,
  classificado por um de-para que aponta para uma publicação que já não o traz — a família do "item
  descontinuado" que a ORC.7b passou a avisar na reprecificação, aqui sem aviso nenhum.
- **39 dos 90 itens SINAPI estão sem procedência** (`publicacao_referencia` vazio) e 33 apontam para
  10/2024; **zero** aponta para 2025. Entre os órfãos estão 3 dos 4 equipamentos do de-para (14525,
  37734, 37758). O campo nasceu no D110 e só é preenchido na adoção, então o que foi adotado antes
  ficou sem ele — e é por procedência que se decide se um item precisa ser reclassificado.

**O que fazer:** decidir se a empresa mantém a classificação própria (e então o de-para deixa de ser
remendo e vira política declarada, com a discordância **reportada** em vez de silenciosa) ou se adota
a resposta da fonte; reapontar os itens para a publicação 2025; e dar procedência aos 39 órfãos.

---

### D124 — a paywall não decidiu se orçamento tem quantidade · 🟠 aberto 13/09/2026

**Decisão do dono, 13/09/2026, ao definir a trava de exclusão do orçamento:**

> *"A paywall ainda não está completamente definida, então apesar do seu entendimento, isso também
> pode mudar sobre a quantidade de orçamento, mas não vamos mexer agora."*

**O estado de hoje, conferido:** orçamento **não consome quota nenhuma**. Não está em
`QUOTAS_DE_OBJETO` nem em `RECURSOS_CONTADOS`. Os números `orcamento: 25 / 100` do
[`planos.py`](../payment/planos.py) são **tamanho de página**, não teto de quantidade — o que o
módulo conta é `banco_preco_linhas`, que é a tabela de preço própria, não a planilha. Logo, um
orçamento parado não impede ninguém de criar outro; o que ele custa hoje é poluição de listagem.

**A regra que o dono fixou e que fica valendo independentemente disto** (já implementada — ver
[modulos/moduloorcamento.md](modulos/moduloorcamento.md)): a trava protege a empresa, **não tutela o
usuário**. Rascunho, cancelado e superado saem; aprovado não sai, mas cancelar abre o caminho —
**nunca há estado do qual não se saia**.

**O que fica em aberto:** se um dia orçamento virar quota, a decisão precisa carregar junto três
coisas que hoje não existem, e esquecer qualquer uma recria a armadilha que esta regra evitou:

1. **o contador** em `RECURSOS_CONTADOS` — e ele lê pelo gerente padrão, que já filtra a lápide, de
   modo que orçamento na lixeira **não** ocuparia quota (isso já está certo por construção);
2. **o que fazer com o aprovado** — se ele conta e não sai, um cliente no teto com todas as obras
   aprovadas fica sem conseguir criar a próxima planilha sem cancelar uma que está em vigor. É a
   forma que a armadilha tomaria aqui;
3. **o degrau por plano**, nos cinco níveis, como todo o resto do §4 do `planos.py`.

Não trava nada hoje. É decisão comercial, e o dono pediu para registrar em vez de decidir agora.

### D114 — no `profissional`, o teto de clientes não conversa com o de empreendimentos · 🟠 aberto 22/08/2026

Levantado junto do D115, e é a metade **comercial** dele — a de engenharia é
aquela; esta é decisão do dono.

O `profissional` (R$ 449) vende **10 empreendimentos** e **1000 clientes**. O
seeder modelou uma incorporadora realista e chegou a 6 empreendimentos, 2.706
unidades e 2.186 vendas: estourou o teto de clientes sem chegar perto do de
empreendimentos.

A conta que expõe a inconsistência: dez empreendimentos de porte médio — 200
unidades cada — dão 2.000 compradores, o dobro do teto. **Quem vende unidade
cadastra um cliente por unidade vendida**, então o limite que morde primeiro não é
o do portfólio que ele contratou: é o de clientes, e ele chega no meio de uma
venda.

Duas leituras possíveis, e a escolha é de posicionamento:

- **o portfólio é o limite de valor** → `clientes` sobe para acompanhar 10
  empreendimentos de porte real (2.000–3.000);
- **o `profissional` é para construtora que executa obra**, não para incorporadora
  que vende unidade → o teto está certo e vender 2.000 unidades é caso de
  `empresarial`. Aí é upsell legítimo, não fricção.

Não trava nada em produção hoje (nenhum cliente real). Fica aberto porque o
módulo de venda de unidade e carnê **existe** no produto, e é ele que faz o número
de clientes crescer rápido.

### D105 — as 200 conversões premium do `empresarial` podem custar mais que o plano · 🟠 aberto 16/08/2026

O `empresarial` (R$ 1.199/mês) vende **200 conversões pagas/mês** com `motores_prancheta` incluindo
`premium` — que é a Autodesk, custo dela e não nosso. O estudo de
[viabilidade](medicoes/viabilidade-economica.md) mostra que o desfecho depende inteiramente de qual
formato essas 200 são:

| As 200 conversões são… |         Custo/mês | Contra R$ 1.199                           |
| ------------------------- | -----------------: | ----------------------------------------- |
| DWG (0,2 crédito)        |             R$ 206 | 17% da receita — sadio                   |
| Revit (1,5 crédito)      | **R$ 1.548** | **negativo antes do armazenamento** |

É a **única linha da plataforma capaz de inverter a margem** — todo o resto do COGS medido é nosso e
é desprezível (converter um acervo inteiro custa centavos). E o risco cresce: o Model Derivative
subiu de preço em 2026 e atividades antes gratuitas passaram a ser cobradas.

→ **decisão comercial, antes da PRA.4 existir**: ou a quota passa a ser por formato ("200 conversões
*de DWG*"), ou vira cobrança por uso, ou o preço do plano absorve o pior caso. Enquanto o motor
premium não existe, nada quebra — mas o número já está publicado no catálogo.

### D103 — o degrau de RAM do plano caro não cabe na máquina · 🟠 aberto 16/08/2026

O [D101](historico-correcoes.md) transformou a memória da conversão em degrau de plano, e a medição
que o motivou mostrou que **servir o arquivo grande é questão de máquina, não de código**: o DWG de
64,9 MB converte no `dwg2dxf` (sai `0`, produz 531,8 MB de DXF) e morre só no nosso orçamento; o
`dwg2SVG` pede **2.410–3.069 MB** nos 7 pesados do acervo (roadmap PRA.1f).

A escada de hoje é `1.536 MB (nosso teto, explica) < 2.048 (Celery recicla o filho) < 3.072 (`mem_limit` do contêiner)`. O limite não é teórico — foi **medido no arquivo de 64,9 MB**: com
2.048 MB no subprocesso ele devolve `recurso_excedido` em 8,9 s; com 2.800 MB o processo morre com
**exit 137 (SIGKILL), sem exceção e sem rastro**, porque os 3.072 MB são do contêiner inteiro e o
Python pai já reserva ~1.150 MB de VA. Por isso o mapa do subprocesso está **achatado no topo**
(2.048 do `essencial` para cima) e o da conversão para em 1.900.

→ **decisão de dimensionamento**: subir `mem_limit` e `CELERY_WORKER_MAX_MEMORY_PER_CHILD` no deploy
e, **no mesmo commit**, os degraus de cima. `EscadaDeMemoriaPorPlanoTests` (4 testes) falha se a ordem
for invertida — foi ele que pegou a primeira versão deste mapa prometendo 2.800.

### D104 — o disco por tarefa suspensa é uma variável sem número · 🟠 aberto 16/08/2026

`FROTA_DISCO_POR_TAREFA_SUSPENSA_MB = 0` (`planos.py` §5.4e) existe desligado por decisão do dono
(16/08/2026: *"o disco será determinado por medição quando o software estiver próximo do
lançamento"*). Enquanto valer 0, a retomada **recomputa** o estado a cada volta — 56% do relógio,
medido — em vez de guardá-lo.

Quem for medir precisa de três grandezas que ninguém tem: quantas tarefas ficam suspensas ao mesmo
tempo em carga real, o tamanho mediano e de cauda do estado por tarefa (~85 MB só do DXF no arquivo
comum, **531,8 MB** no de 64,9 MB) e **o custo em segundos de serializar e reler** — que pode comer a
economia que o número existe para gerar. Referência de indústria e o porquê de este ser o caminho
mais caro dos quatro: [laudo §10](medicoes/fila-da-frota.md).

### D99 — o acervo já convertido não recebeu os consertos de 16/08 · 🟠 aberto 16/08/2026

Os consertos do [D92](historico-correcoes.md) (fundo da folha) e do
[D93](historico-correcoes.md) (origem dos símbolos no degrau `dwg2SVG`) agem **na emissão**. As
**758 derivadas** que já estão no storage foram gravadas antes e continuam como saíram: fundo
cobrindo um terço da folha, e prancha que caiu no degrau `dwg2SVG` sem a correção de origem.

O verbo existe e está pronto — `reprocessar` no `DocumentoProjetoViewSet`, com permissão própria
(`prancheta.conversao.reprocessar`) e botão na tela. **Falta rodá-lo**, e é decisão de quando: é CPU
do `worker-conversao` sobre o acervo inteiro, e enquanto a fila não tiver porteiro ([D98](#d98--o-trabalho-pesado-tem-freio-mas-não-tem-porteiro))
isso concorre com a conversão de quem estiver usando o sistema.

É a mesma classe de pendência que a §14.13 da planta já declara para a quinta casa decimal — e agora
são três motivos para a mesma passada, o que torna vantajoso fazer uma só.

### D91 — o dono ainda vê a mira fora do traço, e a bancada não reproduz · 🟠 aberto 15/08/2026

Depois dos quatro defeitos do [D90](historico-correcoes.md) fechados, o relato continua: **o desvio
cresce com o zoom e diminui perto do topo da planta** ("a 5.000× para eu conseguir ver o erro" perto
do topo; ~10 quadrados de snap até o vértice a 4.000× mais abaixo). Isso é a assinatura de um erro
**relativo** de escala em Y, ancorado no topo da folha.

Dois defeitos dessa família foram achados por leitura e corrigidos em 15/08/2026 (§14.1b da planta):
`prepararSvg` devolvia `null` quando não havia espessura reescrevível, derrubando junto o aspecto
exato; e o papel em mm nunca era lido, porque o recorte do cabeçalho parava no `?>` do prólogo XML.
Os dois valem para 15 dos 528 SVGs do acervo — **não explicam "em todos os arquivos"**.

**A bancada não reproduz.** Na `001`, no app de verdade, ampliando primeiro e medindo depois, em
Chromium com tela a 100% e a 150%: caixa pedida = caixa real e **mira a 0,00 px da tinta a 83×,
1.005× e 5.503×** (§14.11). Ou seja, o caminho medido está correto e o caso do dono tem alguma coisa
que a bancada não tem — prancha, navegador ou ambiente.

**Próximo passo é captura, não conjectura:** o leitor de coordenadas (§14.11) foi instalado para isso.
No caso que erra, a linha `caixa` × `real` decide entre "o navegador não deu a caixa pedida" (aí é
teto de rasterização de outro motor — o `LARGURA_MAXIMA_DE_CAIXA` foi medido **só no Chromium**) e
"a caixa confere e a tinta ainda assim discorda" (aí é o índice, não a pintura). Com a **coordenada
de desenho** (§14.12) o leitor passou a dar o número que fecha o cerco por fora: o vértice lido aqui
e o mesmo vértice lido no AutoCAD têm de bater — se baterem, o índice está certo e sobra a pintura;
se não baterem, o erro nasceu antes da tela. **Folha convertida antes de 15/08/2026 precisa ser
reprocessada** para trazer a coordenada.

**Uma causa concreta foi achada e fechada em 15/08/2026, e ela tem a forma certa do sintoma**
(§14.13): as coordenadas do SVG são **inteiras**, e com a grade de 10⁶ numa folha A1 a tinta só podia
existir em múltiplos de 0,000861 unidade de desenho, enquanto o índice guardava o valor exato. Meia
unidade de grade é invisível no enquadramento e **cresce proporcional ao zoom** — ~3 px a 5.000×,
metade do glifo da mira. O dono descreveu isso como "trava na casa decimal mais próxima" e decidiu a
régua: **precisão na quinta casa, sem arredondar**. Grade, sidecar e tolerância de fusão foram
redimensionados. Falta confirmar, com o acervo do dono reprocessado, se era **a** causa ou **uma
delas** — a `001` media 0,00 px de mira à tinta antes e depois, então este defeito não aparecia na
bancada de tinta (ela é cega a deslocamento **ao longo** do traço).

### D88 — o teto do snap é conferido entre registros, e um registro pode ser gigante · 🟠 aberto 15/08/2026

`indice_de_snap` confere o teto do plano **entre registros**, não entre pontos. No acervo normal isso
custa um excesso de 98 a 13.186 pontos sobre 600.000 (2,2%, ~143 KB) e é generosidade barata — erra
para o lado do cliente.

**A cauda muda a conta.** A remedição de 15/08/2026 achou `HS-UFBACALMAS_Cob.dwg` (0,77 MB em disco)
rendendo **9,1 milhões de pontos, 1,36 GB de RAM e 175 s**. Se uma parte grande disso vier de poucos
registros densos, um único deles pode somar milhões de pontos antes da próxima conferência — e aí o
teto não protege nem a memória nem o relógio, que é a família do D57 e do D76.

**Não está medido quantos pontos o maior registro do acervo rende** — é isso que decide se o risco é
teórico ou presente. Antes de mexer, medir; o conserto provável é conferir o teto dentro de
`_colher_polilinha` a cada N vértices, com N grande o bastante para não pesar no laço quente.

Enquanto isso, o orçamento de conversão (`limites.orcamento_de_conversao`) segue como rede: o estouro
vira `RecursoExcedido` com motivo, não morte do worker.

### D89 — os tetos de `snap_pontos` foram fixados sobre medição contaminada · 🟠 aberto 15/08/2026

`payment/planos.py §5.7` traz 150k (Essencial), 600k (Profissional) e 2M (Empresarial). Os três saíram
da **primeira** passada de 15/08/2026, que media 11 de 15 arquivos e contava geometria fora da folha —
publicou mediana 65 mil e cauda 473 mil.

A passada corrigida ([custo-snap.md](medicoes/custo-snap.md)) mede 13 de 15 e dá **mediana 98 mil e
cauda 9,4 milhões**. Ou seja: a mediana subiu 50% e a cauda, vinte vezes. Os degraus continuam
funcionando — o teto corta e a tela declara "snap parcial" —, mas a fronteira comercial foi desenhada
sobre um acervo que não é o real, e o Essencial em 150 mil agora fica **abaixo** da prancha mediana.

Decisão do dono, com o número novo na mão. Não trava nada hoje.

## 🟡 Médias

### D300 — itens da EMBASA "incompletos" no Orçamento (M080401525 e outros) · 🟡 aberto 16/10/2026

Item 79 do dono: *"CONEXAO TIPO TE C/ DERIVACAO C/ PERFURADOR (COLAR DE TOMADA) PEAD"* e outros ficaram
incompletos. **Apurado:** no PDF de insumos carregado (`1-tabela-de-precos-2026-insumos-junho-r2`, pág. 394)
a descrição **termina em "PEAD"** — renderizada e extraída caractere a caractere, sem texto oculto, anotação
ou segunda linha; 29 códigos (M080401501…613) têm a mesma descrição e preços diferentes, e ~365 de 6.992 por
tabela de serviços repetem descrição (cortes como "…ELEVADO COM", "…CARTÃO DE", "APACITOR"). A EMBASA só
publica PDF nessa página. **Em aberto:** o dono viu a lista completa — falta saber qual documento (link) e
se "incompleto" é a descrição ou a linha sem unidade/preço no orçamento. A consulta ao gmaxis (onde está o
orçamento) não foi feita: leitura de produção depende de autorização.

### D258 — os contêineres de aplicação rodam como root · 🟡 aberto 03/10/2026

Visto ao montar o cofre de produção (10.3): `sgi-erp` e `sgi-iam` respondem `uid=0(root)` — os
Dockerfiles do backend e da IAM não têm `USER`. É o que hoje deixa o segredo `0400` de root ser lido
pelo app, e é também o que faz qualquer RCE no Django virar root no contêiner (escrita em `/app`,
leitura de todo `/run/secrets`). O pentest vai apontar. **Caminho:** usuário sem privilégio no
Dockerfile (`USER app`, uid fixo), `/app` só leitura, e os segredos montados com `uid`/`mode` do
compose (`secrets: - source: … uid: "1000" mode: 0400`) em vez de depender de root; conferir os
volumes de mídia (dono) e o `worker-conversao` (LibreDWG/ODA gravam em `/tmp`).

### D245 — a conta com boleto CNAB vivo não muda valor nem vencimento pelo SGI · 🟡 parcial 03/10/2026

Visto na revisão do item 57. **A metade grave fechou em 03/10/2026:** a segunda via já pede a baixa
(movimento 02) do boleto antigo na mesma remessa — relato em [historico-correcoes.md](historico-correcoes.md).
**Falta a outra metade:** a instrução de **alteração de vencimento/valor** (06) ao editar a conta. Sem
ela, conta com boleto CNAB vivo segue com valor, vencimento e cliente travados ([D248](historico-correcoes.md)),
e o caminho é a baixa pelo internet banking. **Caminho:** `Titulo.movimento = "06"` já é aceito pelos
geradores 240/400; falta a remessa avulsa de instrução (sem entrada), destravar o vencimento na
edição e a confirmação do retorno (14 no 240). Homologar junto com o D239 (abaixo).

### D239 — nenhuma carteira CNAB foi homologada em banco · 🟡 aberto 30/09/2026

O CNAB entrou em 30/09/2026 (item 52) para sete bancos: remessa 240 FEBRABAN e 400 de Bradesco e Itaú,
retorno, nosso número, código de barras e boleto em PDF. O que é padrão (código de barras, linha
digitável, fator de vencimento de 2025, larguras do 240/400) está provado em teste; o que é **de cada
banco** — campo livre, dígito do nosso número, versão do layout, campos "uso do banco" — segue os
manuais públicos e só se confirma no teste de remessa que o banco faz ao liberar a carteira. Até a
primeira homologação, tratar a carteira nova como teste (um lote pequeno), e ajustar a classe do banco
em [`cnab/bancos.py`](../backend/moduloerp/cnab/bancos.py) com o que o banco apontar.

**01/10/2026:** primeiro laudo de validador de banco (Sicoob) aplicado — ver
[D244](historico-correcoes.md). O Sicoob fica pronto para nova rodada no validador; os outros seis
bancos seguem sem laudo.

### D224 — na Prancheta, recalibrar a escala muda o valor de uma medida já anotada · 🟡 aberto 29/09/2026

Visto na volta inteira das E2E da fase 5 (`pra8_prancheta_test.py`, seção 10 — "Recalibrar não
reescreve o que alguém já anotou"): depois de trocar a régua de 20 para 40, a medida antiga responde
`20.0 m` onde o roteiro espera o valor original, e não se declara desatualizada (`False`). Nada de
autenticação no caminho — é a regra do módulo, e ainda não se sabe se a regra ou o roteiro está
certo. **A investigar** contra a planta ([modulos/moduloprancheta.md](modulos/moduloprancheta.md)).

### D155 — a foto da verificação não carimba data nem coordenada · 🟡 aberto 16/09/2026

Achado ao fechar a PDCA.7, conferindo a entrega contra a própria planta. A §5.2
descreve o instrumento do campo com a foto como *"cidadão de primeira classe
(**com data e coordenada carimbadas sozinhas**, sem o inspetor anotar nada)"*.
A fatia entregou a foto — sobe pela porta única, na mesma requisição da
resposta, com `capture="environment"` para abrir a câmera direto. O **carimbo**
não veio.

**O que existe hoje e o que falta:**

- **data** — existe de forma indireta: `ItemVerificacao.respondido_em` é gravado
  no servidor no momento da resposta, e a foto sobe nessa mesma requisição. O
  que não existe é o carimbo **na imagem**, que é o que sobrevive quando a foto
  sai do sistema (anexada a um e-mail, impressa num relatório de auditoria);
- **coordenada** — não existe em lugar nenhum. Nem o navegador é consultado
  (`geolocation`), nem há campo para guardá-la, nem ela é lida do EXIF do
  arquivo. A NC exportada para o projetista diz *em que local da obra* está o
  defeito só pelo `LocalObra`, que é o endereço construtivo — não o geográfico.

**Por que isso importa mais aqui do que no apontamento de avanço** (que também
não carimba): a foto da PDCA.2 documenta *quanto andou*, e quem confere tem o
avanço ao lado. A foto da PDCA.7 é **prova de inspeção**, e é ela que o
organismo certificador do PBQP-H olha quando quer saber se o técnico esteve
onde disse que esteve. Sem carimbo, ela prova que o defeito existe — não que
ele foi visto naquele lugar naquele dia.

**Não foi decidido como fazer, e as três saídas têm custos diferentes:** ler o
EXIF do arquivo enviado (barato, mas o celular pode ter a geolocalização
desligada e muitos navegadores removem o EXIF no upload); pedir
`navigator.geolocation` na tela e mandar junto (preciso, mas exige permissão do
usuário e um campo novo no modelo); ou gravar o carimbo **na imagem**, que é o
que o mercado de vistoria faz e o que sobrevive à foto sair do sistema — e é o
mais caro dos três.

Enquanto nada disso acontece, o que a fatia entrega é honesto: ela não afirma
em lugar nenhum que a foto está carimbada.

### D119 — o calendário de trabalho não modela turnos nem horários · 🟡 aberto 13/09/2026

Levantado ao resumir a PDCA.2. O modelo `CalendarioTrabalho` tem campos para
quantidade de horas por dia (`horas_por_dia`) e exceções de recesso/feriados,
mas **não tem estrutura para representar turnos nem horários específicos**.

Isto torna impossível representar:

- **Múltiplos turnos no mesmo dia** — manhã 06h-14h, tarde 14h-22h, noite 22h-06h
- **Horários específicos** — começar às 7:30, terminar às 17:15 em vez de "o dia inteiro"
- **Turnos parciais** — segunda obra que bate sábado apenas pela manhã
- **Paradas técnicas** — de 12h a 13h é parada, fora do expediente

A demo funciona com a simplificação "8,8 horas corridas, segunda a sexta" — que o
mundo real não permite. Uma obra com **dois turnos fica travada ou fake**.

**O impacto:** quando o sistema rodar de verdade, a curva S (que distribui o
previsto nos dias úteis do calendário) só conseguirá agregar horas por dia, não
por turno — e o apontamento de avanço fica sem granularidade para dizer "andou
15% no turno da manhã".

**Não bloqueia PDCA.2:** a fatia funciona com o calendário que existe. É uma
lacuna de desenho que só aparece em uso real, exatamente como a D118
(calendário vazio na tela) antes de existir calendário de verdade.

**Escopo:** fica para depois (Calendário.2 ou PDCA.3), porque altera o contrato
da API — um plano rascunho salvo com calendário A teria que saber o que fazer se
o calendário virar multi-turno depois, e essa migração de dado não é trivial.

### D113 — a plataforma não tem documentação de produção · 🟡 aberto 21/08/2026

Decisão do dono (21/08/2026): **tem que ter documentação de produção**. Hoje não há — e a lacuna não
é de conteúdo espalhado, é de destinatário: **nenhum documento fala com quem vai operar o sistema no
ar**. O que existe cobre outros públicos e nenhum deles é esse:

| Documento                                | Para quem                    | Por que não serve                                                                                                                    |
| ---------------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `comandos.md`                          | o dono, na própria máquina | guia de bancada — Docker Desktop, dev × staging, e o caminho da pasta pessoal escrito dentro; não é indexado no`docs/README.md` |
| `desenvolvimento.md`                   | quem vai desenvolver         | subir a infra local e rodar a suíte                                                                                                  |
| plantas (`modulos/`, `arquitetura*`) | quem vai mexer no código    | descrevem**desenho**, sem passo a passo e sem status, por regra                                                                 |
| `deploy/README.md`                     | quem opera a máquina        | compose, imagem, variável de ambiente — não o*uso* da plataforma                                                                 |

**O caso que expôs isso** foi a importação da base-mãe (ORC.9c). O procedimento só existe em dois
lugares: a mensagem que o comando devolve quando recusa, e o
[README ao lado do arquivo](../backend/moduloorcamento/dados/classes/README.md) que o superuser
edita. Instrução no ponto de uso é bom desenho e deve continuar — mas ela só aparece **depois** de a
pessoa já ter tentado, e não cobre o que não tem comando associado.

**Por que importa mais aqui do que na média dos produtos:** a base-mãe é global e read-only, só o
superuser a importa, e o que ele importa **todos os tenants enxergam**. Classe traduzida errado é
preço errado para a plataforma inteira de uma vez — e essa é exatamente a operação sem documentação
prévia. O mesmo vale para o que é decisão do dono e não tem tela: teto e preço em
[`payment/planos.py`](../payment/planos.py), quota, publicação de plano.

**Não trava nada hoje** — o sistema não está no ar. Fica aberto porque **vira bloqueio na virada**:
no dia em que a primeira SINAPI de verdade for carregada, quem a carrega precisa saber o que fazer
antes de rodar, não ao ler o erro. Escopo, formato e destinatário (o dono opera? um cliente opera?
há suporte no meio?) são decisão do dono, e é ela que falta para começar.

### D86 — os preços dos pacotes de snap são chute de engenharia · 🟡 aberto 15/08/2026

`pacote_snap_200k`, `_500k` e `_1m` entraram em [payment/addons.py](../payment/addons.py) com R$ 39,
79 e 139. Os **tetos** são medidos ([custo-snap.md](medicoes/custo-snap.md)); os **preços** não —
foram postos para o mecanismo ficar completo e testável de ponta a ponta.

Pela regra de 08/08/2026 o valor comercial é do dono, e este ficou pendente. Não trava nada: o teto
por plano já funciona e o add-on só entra quando alguém o contrata no IAM. Fica aberto porque um
preço inventado que ninguém revisou é exatamente o tipo de número que vira tabela de preços por
inércia.

### D80 — `remedir_dwg.sh` morre no fim quando o acervo perdeu um arquivo do corpus · 🟡 aberto

Achado ao rodar a passada de custo de 12/08/2026. O laço usa `TOTAL="$(wc -l < "$LISTA")"` — 160 —,
mas o comando **descarta** o arquivo da lista que não está mais na pasta e mede 159. A última janela
(`--pular 159 --limite 1`) fica vazia, o comando sai com `CommandError: Nenhum arquivo .dwg encontrado.` e o `set -e` mata o script **antes do `--consolidar`**. Os parciais estão todos gravados,
então nada se perde — mas a passada termina sem relatório, e a consolidação tem de ser refeita à mão.

**Correção:** contar o corpus **efetivo** (o que o comando mediu) em vez das linhas da lista, ou
tolerar janela vazia como fim normal. É decisão de instrumento, não de engenharia de produto: mexer no
que conta a cobertura é o que o `--consolidar` existe para conferir.

### D41 — As amostras que provaram os 4 motores estão fora do repositório · 🟡 aberto

`backend/media/amostras_prancheta/` está sob `media/`, que o [.gitignore](../.gitignore) exclui
inteiro (linha 115). Foram elas que provaram os quatro motores em 31/07 — e junto com elas está
ignorado o `gerar_amostras.py`, o script que as produz. Em clone limpo, nada disso existe: o
instrumento da prova não é versionado.

**Contornado no PRA.8**, não resolvido: o E2E carrega as próprias amostras em
[amostras_pra8.py](../testes/e2e/amostras_pra8.py) — PDF, DXF e IFC escritos à mão em texto (que
de quebra documentam o que cada motor precisa receber) e o DWG comprimido em base64, porque é binário
e o `dxf2dwg` que o escreveria vive só no *build stage*.

**Para fechar:** mover `gerar_amostras.py` para um caminho versionado (o candidato natural é um
management command, ao lado do `medir_cobertura_dwg`), de modo que a origem das amostras volte a ser
código revisável em vez de um arquivo que existe na máquina de quem o rodou.

### D54 — Marcação e medição anteriores à PRA.1c ficam sem folha · 🟡 aberto

A âncora de uma marcação é normalizada pela largura da folha em que foi fincada. Quando uma revisão
que era **uma** folha vira **várias**, o espaço de coordenadas da folha antiga deixa de existir, e a
`Marcacao.desenho` daquelas linhas fica nula (`SET_NULL` de propósito — a marcação sobrevive, é o
apontamento do canteiro).

O efeito é limitado e conhecido: elas continuam na conversa, exportam em BCF e podem ser resolvidas;
o que não têm é **pino sobre o desenho**. A tela diz isso em vez de fingir um lugar.

**Não foi remapeado automaticamente, e é decisão.** Dava para converter a coordenada antiga em
coordenada de desenho, achar o aglomerado que a contém e reprojetá-la — mas isso é a plataforma
movendo o dedo de quem apontou, com base numa aritmética que ninguém conferiu, num campo cujo produto
é dizer *onde*. Errar por alguns centímetros é pior que não ter pino, porque o pino errado é
acreditado.

**O alcance real é pequeno:** só atinge revisão que (a) já tinha marcação com âncora e (b) foi
reconvertida em mais de uma folha. Revisão de folha única não é tocada — o backfill da
[migration 0006](../backend/moduloprancheta/migrations/0006_pra1c_desenho_por_folha.py) pendura tudo
no desenho #1 e nada se move.

**Se virar incômodo**, o caminho é oferecer o remapeamento como **ação de quem governa o acervo**
(`documento.edit`), mostrando antes e depois — decisão de gente, não migração silenciosa.

## 🟡 Médias — herdadas dos laudos v01/v02

| ID                                                                                                                | Achado → correção                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | Status                |
| ----------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| A5                                                                                                                | `CobrancaCliente` duplica `ContaReceber`+`Boleto` → consolidar repetindo o playbook da `Fatura`. **Levantado 25/07/2026:** confirmado que **nada escreve** em `CobrancaCliente` (nenhum service, task, seed ou signal — só o CRUD exposto em `/api/erp/cobrancas-cliente/`): a tabela está vazia e a cadeia viva é `ContaReceber`→`Boleto`. A única capacidade que ela tinha a mais — amarrar a parcela ao **contrato/unidade** — passou a existir na `ContaReceber` (FKs `cliente_empreendimento`/`contrato`, migration `moduloerp/0013`), então a consolidação virou basicamente **remover** o modelo e a rota.                                                                                                                                                                                                                                                                                  | 🔴 aberto             |
| A7                                                                                                                | N+1 na galeria de IA e no CRM; busca de telefone O(N) em Python →`select_related`/`prefetch_related` + paginação + query no banco *(v01-B9)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | 🔴 aberto             |
| A8                                                                                                                | Acoplamento duro ao Redis (`delete_pattern` do django-redis; sem `IGNORE_EXCEPTIONS`) → cache tolerante a queda. **Parcial 19/07:** `IGNORE_EXCEPTIONS: True` no backend e na IAM — virou obrigatório com o S8, que faz o throttle consultar a cache em TODA requisição (sem isso, Redis fora deixaria de ser lentidão e passaria a ser API inteira fora do ar). **Falta** o `delete_pattern`, que segue amarrando o código ao django-redis.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | 🟠 parcial 19/07/2026 |
| A14                                                                                                               | **Bases sem leitor: ORSE, SICRO, SEINFRA e SEDOP** *(reescrito na ORC.8, 21/08/2026; estreitado na ORC.8b, 22/09/2026)* — a ORC.8 fechou o A13 e trocou o que falta aqui. `Fonte` aceita sete desde o ORC.0 e o importador manual é genérico, mas o motor de carga automática lê **dois** formatos: o arquivo largo da Caixa (27 UFs em colunas) e o PDF da EMBASA. `carga.fontes_conhecidas()` declara isso, a tela diz na cara (*"o motor ainda não lê o formato desta fonte"*) e o agendamento se recusa a tentar — nada finge funcionar. Para cada base nova é preciso um leitor do formato dela, e aí ela entra no botão; enquanto não houver, o caminho continua sendo o comando por publicação.                                                                                                                                                                                                                       | 🟠 aberto             |
| F13                                                                                                               | **O `Modal` do Orçamento reimplementa o modo `alto` em vez de usar o do `malha`** *(17/08/2026)* — [frontend.md §2.2](frontend.md) descreve o modo `alto` do `Modal` compartilhado para "diálogo cujo miolo é uma lista": cartão em coluna flex, cabeçalho e rodapé presos, miolo com `flex: 1`. O kit local do Orçamento (`modules/orcamento/ui.tsx`) **não tem esse modo**, então o modal de inserir item chegou à mesma altura por conta própria (`height: min(62vh, 660px)` na linha da lista) — funciona e respeita a regra de não usar pixel fixo, mas é a terceira implementação do mesmo comportamento. É um caso concreto do **F12** (quatro kits de UI paralelos), e o remédio é o mesmo: migrar para `components/malha/`. Enquanto não migrar, mexer no modo `alto` compartilhado não conserta este modal.                                                                            | 🔴 aberto             |
| A16                                                                                                               | **A adoção nunca remove componente que a fonte aposentou** *(17/08/2026)* — `services._adotar_componentes` e `bancos._adotar_componentes` usam só `update_or_create`: quando a SINAPI tira um insumo de uma composição, o `ComponenteComposicao` correspondente **fica para sempre** no catálogo do tenant, e a composição adotada passa a ter um item a mais que a oficial. É o irmão do D99 — lá o defeito era no preço da planilha, aqui é na receita do catálogo. **Não corrigido de propósito:** apagar componente é mexer em dado do cliente, e o tenant pode ter ajustado o coeficiente à mão; sem procedência por componente não dá para distinguir "veio da SINAPI e sumiu" de "o cliente acrescentou". → decidir com o dono entre (a) remover na re-adoção e relatar quantos, ou (b) marcar como órfão e deixar a decisão na tela; (b) exige campo novo, (a) não.                         | 🔴 aberto             |
| A15                                                                                                               | **`--dry-run` do importador grava a publicação** *(17/08/2026)* — `importar_base_referencial` diz "nada foi gravado", mas o `BaseReferencial.objects.get_or_create` roda **antes** do desvio do `--dry-run`, sem transação em volta. Quem só quer conferir um arquivo (o uso que o próprio `help` do comando sugere) deixa para trás uma publicação **vazia**, que já aparece no seletor de base pela `bases-resumo` com 0 insumos e 0 composições — dado falso numa tela de escolha de data-base. Achado ao carregar a SINAPI BA 10/2024, cuja publicação nasceu de um `--dry-run` que falhou no sintético (D98). → criar a publicação só depois do desvio, ou envolver o `handle` em `transaction.atomic` com rollback quando `seco`.                                                                                                                                                           | 🔴 aberto             |
| A9                                                                                                                | `except Exception → str(e)` no corpo do 500 vaza detalhes internos → mensagem genérica + traceback só no log *(v01-B7)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | 🔴 aberto             |
| F3                                                                                                                | Acessibilidade: ordenação/linhas de tabela sem teclado,`Sheet` sem focus trap, hover via JS → handlers de teclado + focus trap + CSS *(v01-F3)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | 🔴 aberto             |
| F9                                                                                                                | **Breadcrumb da topbar não conhece os módulos novos** — `SEGMENT_LABELS` em [AppTopbar.tsx](../frontend/src/components/layout/AppTopbar.tsx) não tem `sil`, `orcamento`, `orcar`, `encargos`, `controlar`, `cronograma`, `bases`, `incorporacao` nem `notas-fiscais`: nessas telas a trilha mostra o **slug cru** (`orcamento › orcar`), quebrando a promessa de "toda tela declara seu endereço" ([frontend.md §3.3](frontend.md)). O mapa é uma lista manual que ninguém atualiza ao criar rota. → completar os rótulos e, de preferência, derivá-los do catálogo de páginas de cada módulo (o Orçamento já tem o seu em `modules/orcamento/paginas.ts`) em vez de manter uma segunda lista. **Piorou na ORC.9 (21/08/2026):** o Orçar passou a ter três níveis                                                                                                                                 |                       |
| de rota (`orcar` › `obra/{id}` › `orcamento/{id}`), então a trilha da topbar agora mostra também        |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |                       |
| `obra` e o **id cru** no meio do caminho. A página desenha a própria trilha (obra e versão pelo nome), |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |                       |
| o que resolve na tela — mas deixa as duas trilhas contando histórias diferentes na mesma janela.                | 🔴 aberto                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |                       |
| F10                                                                                                               | **`--topbar-h` não existe** — [PaginaShell.tsx](../frontend/src/modules/orcamento/components/PaginaShell.tsx) dimensiona as páginas do Orçamento com `calc(100vh - var(--topbar-h, 56px))`, mas **nenhum arquivo declara** essa variável (nem `index.css`, nem o `AppTopbar`, cuja altura real vem de `padding: 12px` + conteúdo). Sempre cai no fallback, então a grade com `semRolagem` (Orçar) fica com altura errada por alguns pixels — rolagem dupla ou faixa cortada. → declarar `--topbar-h` no `AppShell`/`index.css` a partir da altura real da topbar (ou medir por `ResizeObserver`), já que outros módulos vão precisar do mesmo cálculo.                                                                                                                                                                                                                                                            | 🔴 aberto             |
| F11                                                                                                               | **Duas listas de módulos que divergem** — o farol da sidebar (`NAV_SECTIONS` em [AppSidebar.tsx](../frontend/src/components/layout/AppSidebar.tsx)) e o catálogo do hub (`CATALOGO` em [pages/app/home/catalogo.ts](../frontend/src/pages/app/home/catalogo.ts)) descrevem o mesmo conjunto com vocabulários diferentes (`implemented: boolean` × `situacao: pronto/backend/planejado`) e **já discordam**: Drone é `implemented: false` num e `situacao: 'backend'` no outro; Maps/DMS/Prancheta/PDCA/terrenos/viabilidade estão no hub e não na sidebar. Como os dois são "o farol da edição" ([frontend.md §3.2](frontend.md)), o usuário vê dois inventários da mesma casa. → uma fonte só (o `CATALOGO`, que é mais rico), com a sidebar derivando dela o seu recorte — mesmo remédio do `paginas.ts` do Orçamento, que já resolveu isso dentro do módulo.                                               | 🔴 aberto             |
| F12                                                                                                               | **A convenção de estilo escrita não é a praticada** — [frontend-convencoes.md](frontend-convencoes.md) manda "Tailwind classes inline; `cn()` para condicionais; sem arquivos `.css` por componente", mas **todo** o código nascido na Malha (sidebar, topbar, hub da home, SCM, SIL, Orçamento) é escrito com objetos `style={{}}` inline, sem Tailwind e sem `cn()`. Some-se a isso **quatro kits de UI paralelos** (`components/malha/` + kit local do SCM + `sil/ui.tsx` + `orcamento/ui.tsx`, cada um com seu `Card`/`Pill`/`Btn`/`Modal`) — a dívida dos kits já está declarada em [frontend.md §2](frontend.md), a da convenção não. Quem ler o documento antes de escrever a próxima tela vai escrever no padrão errado. → decidir o padrão de fato (inline `style` + tokens parece ser o vencedor) e reescrever a regra; e datar a migração dos kits locais para `components/malha/`. | 🔴 aberto             |

## 🟢 Baixas

### D270 — devolução ao fornecedor com obra preenchida reduz o "aplicado" da etapa · 🟢 aberto 09/10/2026

Visto ao montar o custo no plano e o consumo a baixar (`modulopdca/suprimentos.py`). O ledger do SIL
usa o mesmo `tipo=devolucao` para a volta ao estoque (estorno de requisição, entrada) e para a devolução
ao fornecedor (saída). As duas leituras tratam toda `devolucao` com obra como **volta da obra** e a
subtraem do aplicado; uma devolução ao fornecedor que leve obra/etapa faria o aplicado da etapa cair e o
"a baixar" subir. Hoje a devolução ao fornecedor não apropria obra, então o caso não aparece.
**Caminho:** distinguir pela origem (`Devolucao.tipo`) ou por sinal da movimentação ao ler o ledger.

### D230 — a imagem do backend não tem HarfBuzz-Subset, que o WeasyPrint vai passar a exigir · 🟢 aberto 30/09/2026

A 70 avisa a cada PDF: *"Using fontTools instead of HarfBuzz-Subset … will be unsupported in future
versions"*. Hoje funciona (o `fontTools` cobre), mas a próxima subida do `weasyprint` pode quebrar a
exportação em PDF se a biblioteca de sistema não estiver na imagem. **Correção:** instalar a
HarfBuzz-Subset ≥ 4.1 no `backend/Dockerfile` (pacote do sistema, ao lado do Pango) e conferir que o
aviso some — antes de subir o `weasyprint` de novo.

---

Fora o D230, nenhum em aberto (D206, D222 e D223 fechados em 30/09/2026 — [histórico](historico-correcoes.md)). O **D147** (seis erros de `eslint` em três telas da PDCA.3/4, que desligavam o
fast refresh justamente na tela em que se passa o dia digitando) e o **D148** (o traceback `CRÍTICO`
impresso a cada execução da suíte) foram corrigidos em 15/09/2026, junto do fechamento da PDCA.5;
relatos em [historico-correcoes.md](historico-correcoes.md).

| ID  | Achado → correção                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Status                |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| A10 | Higiene do repo:`nul`, `terminal*.txt`, scripts soltos na raiz → remover + `.gitignore` *(v01-G1)*. **Parcial 19/07:** o que tinha valor foi movido em vez de apagado — `terminal.txt` (guia de comandos atualizado) → [docs/comandos.md](comandos.md), `test_browser.py` → `testes/e2e/browser_smoke_test.py`, `serve_spa.py` → `infra/`. Docker e env saíram da raiz para [deploy/](../deploy/README.md). `.gitignore` ganhou `_verify_*.txt` e — achado no caminho — teve os padrões de virtualenv **ancorados** (`/env/` em vez de `env/`): sem a âncora, `env/` casava qualquer diretório com esse nome e escondia o `deploy/env/` inteiro, incluindo os modelos que precisam ser versionados. **Falta (exige decisão/ação do dono do repo):** (a) apagar 4 arquivos mortos na raiz — `nul` (um 502 do nginx capturado por engano), `_verify_testes.txt` (resíduo do bridge PHP removido) e `package.json`/`package-lock.json` (vestígio do monorepo Node; **nada os referencia** — o CI usa `frontend/package-lock.json`); (b) decidir o `requirements.txt` da RAIZ — não é usado por CI nem por Dockerfile algum (esses usam `backend/` e `iam/`), mas é plausível que seja o manifesto do `.venv` que roda as duas suítes localmente, e por isso **não foi tocado**. Se for isso, vale torná-lo explícito (`requirements-dev.txt`, somando backend+iam, hoje desatualizado: falta `django-redis`); se não, pode sair. **(c) 16/09/2026 — `infra/serve_spa.py` está morto E quebrado:** ao ser movido para `infra/` nesta mesma limpeza ele passou a resolver `infra/frontend/dist`, que não existe; e a SPA é servida pelo container `react` (nginx) e pelo Vite em dev. Ninguém notou em dois meses, o que é a prova de que ninguém o usa. A regra de entrada da pasta ficou escrita em [infra/README.md](../infra/README.md). | 🟠 parcial 19/07/2026 |
| A12 | Modelagem: validador CPF/CNPJ sem dígito verificador no backend;`Boleto.VENCIDO` nunca setado; rota duplicada `/api/api/`; duplicata no fallback de tipos de IA *(v01-B8)*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | 🔴 aberto             |
| F6  | Sem`ErrorBoundary` nem padrão de loading/erro/vazio; i18n ausente → padronizar componentes de estado                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | 🔴 aberto             |
| D77 | **`X-Content-Type-Options` sai duplicado em toda resposta do gateway** — o nginx o adiciona (`add_header … always`, Fase 5) e o Django também (`SecurityMiddleware`), então o cliente recebe `nosniff, nosniff`. Inofensivo hoje (mesmo valor, e o browser honra), mas é um header de segurança que ninguém sabe de onde vem: se um dia as duas fontes divergirem, uma delas fica invisível. Achado ao escrever o E2E do D70 em 09/08/2026, e ele explica por que nenhum E2E anterior o viu — todos leem headers com `dict(resp.headers)`, que descarta a duplicata em silêncio. → `proxy_hide_header` no gateway **ou** deixar o header por conta de uma fonte só, e ajustar as asserções que hoje comparam por igualdade.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | 🔴 aberto             |
