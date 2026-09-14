# Sistema de Lixo — exclusão reversível com auditoria

> Prancha da exclusão reversível do SGI. Descreve o **desenho**, sem status nem datas — o status
> está no [roadmap.md](../roadmap.md).
>
> **Esta prancha foi reescrita quando a implementação aconteceu.** A versão anterior desenhava
> *hard-delete + snapshot JSON* e foi escrita antes de os módulos existirem; medida contra o código
> real, ela não satisfazia a decisão do dono. O que mudou e por quê está na [§10](#10-o-que-mudou-em-relação-ao-desenho-de-2026).

---

## 1. A decisão do dono

> *"Coloca como «Obra excluída por «usuário» na data xx/xx/xx». Deixa o plano para poder ser usado
> como modelo em outra obra."* — 23/08/2026
>
> *"O lixo é uma página à parte. Como é custo para o programa, terá uma paywall. O lixo é apagado
> depois de 15 dias. O lixo pode ser restaurado através da página de lixo."* — 13/09/2026

As duas frases, juntas, descrevem **duas etapas** — e é a separação delas que sustenta todo o resto:

| Etapa | O que acontece | Quando |
|---|---|---|
| **Lápide** | O registro é marcado (`excluído por fulano em dd/mm`), some de toda listagem e **continua inteiro no banco**. Nada cascateia. | No `DELETE` |
| **Purga** | O registro é apagado de verdade, e só aí o `CASCADE`/`PROTECT` de cada módulo entra em cena. | No fim do prazo do plano |

A lápide é a janela reversível; a purga é o que o nome "lixo" descreve.

---

## 2. Por que lápide, e não cópia em JSON

Três razões, todas medidas contra o código que existe:

1. **O `PROTECT` tornava a exclusão impossível.** `Orcamento.obra` é `PROTECT`: uma obra com
   orçamento não sai por `DELETE`, então um endpoint que *move* o objeto para outra tabela devolveria
   409 justamente nas obras que alguém quer tirar da frente. A lápide não consulta `PROTECT` nenhum —
   ela não apaga.
2. **O snapshot mataria o plano modelo.** `Cronograma.obra` é `CASCADE` e `eh_modelo` é uma marca no
   próprio cronograma. Apagar a obra fisicamente levaria junto a biblioteca de padrões da empresa —
   exatamente o que a decisão de 23/08 mandou preservar.
3. **Restaurar vira trivial.** Sem payload para desserializar, sem `INSERT` com id explícito, sem
   `setval()` em sequência, sem conflito de id. Restaurar é `UPDATE ... SET excluido_em = NULL`.

**E o medo que o desenho antigo tinha do soft-delete não se aplica aqui.** O receio era obrigar toda
consulta de todo módulo a lembrar do filtro. Não é o caso: o filtro entra no **gerente padrão**, que
é o caminho por onde os modelos já leem. Serializer, relação reversa (`obra.etapas`), agregação de
serviço e ViewSet herdam o corte sem escrever uma linha.

---

## 3. Modelo de dados

### 3.1 A lápide — `nucleo.tenancy.Excluivel`

Base abstrata. Herdar isto **muda o `DELETE` da API**: o `perform_destroy` do
`TenantScopedViewSetMixin` passa a marcar em vez de apagar.

| Campo | Papel |
|---|---|
| `excluido_em` | A lápide **e** o relógio da purga. Indexado. |
| `excluido_por` | `SET_NULL` — a lápide sobrevive ao desligamento de quem apagou. |
| `motivo_exclusao` | O que o usuário escreveu no modal. |

Dois gerentes, e **a ordem importa**:

- `objects` (padrão) — filtra a lápide. É o que a relação reversa e o serializer usam.
- `todos` — a porta explícita para o que está na lixeira. Só o `nucleo/lixo.py` e o `admin` precisam.

> **Detalhe de Django que torna o desenho seguro.** Com `base_manager_name` **não** declarado, o
> `_base_manager` que o ORM usa para travessia de FK e `refresh_from_db()` é um `Manager` simples,
> sem o filtro. `conta_pagar.obra` continua devolvendo a obra na lixeira — o título tem de saber de
> quem ele é —, enquanto `Obra.objects` não a lista.

### 3.2 O índice — `nucleo.Lixo`

Uma linha por objeto que foi para a lixeira. **Não guarda o dado** — guarda onde ele está e o que
aconteceu com ele. Existe por dois motivos que a lápide sozinha não resolve:

1. **a página é uma consulta só** — sem ela, listar "o que este tenant excluiu" varreria as 16
   tabelas que herdam `Excluivel`, ordenaria em Python e paginaria à mão;
2. **a auditoria sobrevive à purga** — apagado o objeto, esta linha fica, com `purgado_em`
   preenchido. É o que ainda responde "quem apagou o quê, quando e por quê".

Campos: `alvo_tipo` (`ContentType`) + `alvo_id`; `rotulo` (o `str()` do objeto no instante da
exclusão — depois da purga é a única coisa que ainda diz o que era); os três de auditoria
desnormalizados da lápide; `purgar_em`; e os pares `restaurado_em/por`, `purgado_em/por`, mais
`falha_na_purga`.

**`purgar_em` é gravado, não calculado.** O prazo é congelado no instante da exclusão a partir do
plano vigente. Calcular na varredura faria um downgrade encurtar retroativamente a janela de quem já
tinha apagado.

**Constraint:** um objeto está no máximo **uma vez** na lixeira — `UniqueConstraint` parcial sobre
(`tenant`, `alvo_tipo`, `alvo_id`) onde `restaurado_em` e `purgado_em` são nulos.

### 3.3 A unicidade solta a lápide

As `UniqueConstraint` dos modelos com lixeira ganharam `condition=Q(excluido_em__isnull=True)`: um
CPF na lixeira **não** segura o recadastro pelo prazo inteiro. Sem isso o usuário exclui, tenta
cadastrar de novo e leva "já existe" sobre um registro que não consegue ver em lugar nenhum.

O `TenantScopedUniqueSerializerMixin` reconhece essa condição específica e mantém o validador de
DRF — o queryset dele é o `_default_manager`, que **já** aplica o mesmo corte. Sem essa exceção, as
duplicatas cairiam de *400 com o campo apontado* para *500 com `IntegrityError`*.

---

## 4. Quem pode o quê

| Operação | Quem | Permissão |
|---|---|---|
| Excluir (marcar a lápide) | quem já podia excluir | a do próprio módulo — **nenhuma nova** |
| Ver a lixeira | `gestor_lixo` | `plataforma.lixo.view` |
| Restaurar | `gestor_lixo` | `plataforma.lixo.restaurar` |
| Purgar antes do prazo | `gestor_lixo` | `plataforma.lixo.purgar` |

Admin do tenant e superusuário passam, como em toda a casa.

**Excluir não ganhou verbo novo de propósito:** quem já podia apagar continua podendo, e o que mudou
é que agora dá para voltar atrás. Trancar a exclusão atrás de uma permissão nova tornaria a lixeira
um rebaixamento de permissão disfarçado de melhoria.

**Purgar saiu de dentro de restaurar:** restaurar devolve dado à circulação; purgar destrói, antes do
prazo, o que ainda dava para recuperar. Quem confere o que foi apagado por engano não é
necessariamente quem pode encurtar a janela que o plano vendeu.

---

## 5. A paywall é a JANELA, não um teto de itens

`lixo_retencao_dias` por plano ([`planos.py` §5.5g](../../payment/planos.py)). Um teto de
**quantidade** só teria dois modos de agir, e os dois são piores:

- **barrar a exclusão** com a lixeira cheia — quebra a regra que o `nucleo/quotas.py` já defende
  (*quota trava só a criação; editar e excluir seguem livres*), e na versão mais perversa dela:
  impedir alguém de apagar porque apagou demais;
- **purgar o mais antigo** para abrir espaço — destruir dado ainda dentro do prazo prometido, calado.

A janela regula o mesmo custo sem nenhum dos dois efeitos: o que entra sai sozinho, e quanto mais
barato o plano, mais rápido sai.

---

## 6. Fluxo

### 6.1 Excluir

```
DELETE /api/<modulo>/<recurso>/<id>/?motivo=...
  → TenantScopedViewSetMixin.perform_destroy
  → é Excluivel?  sim → nucleo.lixo.mover_para_lixo   (lápide + linha no Lixo, uma transação)
                  não → instance.delete()             (exclusão física, como sempre foi)
```

Não existe `POST /api/lixo/mover/`. O que põe um objeto na lixeira é o `DELETE` do próprio módulo,
onde o usuário está e onde a autorização dele já roda.

### 6.2 Restaurar · 6.3 Purgar

```
POST   /api/lixo/{id}/restaurar/   → tira a lápide
POST   /api/lixo/{id}/purgar/      → emite `antes_de_purgar`, apaga de verdade
DELETE /api/lixo/{id}/purgar/      → o mesmo (o verbo que descreve o ato)
```

### 6.4 A varredura

`nucleo.purgar_lixo_vencido`, de hora em hora no beat. Lê `purgar_em` e **não consulta plano nenhum**.
Lista sob `rls_bypass()` (task não tem tenant armado; sem isso enxergaria zero linhas para sempre) e
**apaga dentro do contexto do tenant de cada item**. Transação **por item**: uma obra que recusa não
desfaz a purga das outras.

---

## 7. O contrato com os módulos — `antes_de_purgar`

O `nucleo` é importado por todos e não pode importar nenhum de volta: ele não sabe o que está
apagando. Antes do `DELETE` definitivo ele emite `antes_de_purgar` (sender = classe do alvo), e o
módulo dono decide o que precisa sobreviver. Mesmo contrato do `aprovacao_concluida`.

**Levantar exceção no receptor aborta a purga** — e é legítimo: é como um módulo diz "este objeto não
pode morrer ainda". O motivo vai para `Lixo.falha_na_purga`, o item **fica** na lixeira, visível, e a
tela mostra a recusa ao lado dele. Purga que falha não mente.

Receptores hoje:

| Módulo | O que faz | Por quê |
|---|---|---|
| `modulopdca` | desliga da obra os cronogramas `eh_modelo` (e solta o calendário deles) | decisão do dono: o modelo sobrevive à obra |
| `modulopdca` | solta o calendário dos cronogramas **comuns** antes do `CASCADE` | desata o nó `CASCADE`/`PROTECT` que abriu o D116 |
| `moduloorcamento` | apaga os orçamentos da obra | `Orcamento.obra` é `PROTECT`; sem isso a obra nunca venceria o prazo |

> **O nó do D116, e onde ele foi desatado.** `CalendarioTrabalho.obra` é `CASCADE` e
> `Cronograma.calendario` é `PROTECT`. Os dois entram na mesma fila de exclusão, e o coletor do
> Django **não isenta o que já está na fila**: ele vê um `PROTECT` apontando para o calendário e
> recusa o `DELETE` inteiro. Soltar o calendário antes resolve porque o `PROTECT` deixa de existir no
> instante do `DELETE`. O lugar certo para isso é o módulo dono, não o `nucleo`.

---

## 8. A tela

A listagem é **paginada** (`PAGINA_PADRAO["lixo"]` = 25, teto 200, no [`planos.py`](../../payment/planos.py)) —
neste projeto não há paginação padrão do DRF, e ViewSet sem paginador devolve array puro em vez do
envelope `{count, results}`. Foi o que fez a tela dizer "1 na lixeira" e "nada na lixeira" ao mesmo
tempo no primeiro dia ([D122](../historico-correcoes.md)).

`/app/lixo`, na seção **Administração** da sidebar, trancada por `plataforma.lixo.view` (cadeado, não
omissão: é porta que existe para a pessoa — ela pode pedir o papel ao admin).

**O relógio é o assunto.** A coluna que mais importa não é o que foi apagado, é quanto tempo falta;
o que vence em 3 dias ou menos vem marcado, e "vencido" não vira zero. O modal de purga exige digitar
o nome do item, porque aquele botão apaga antes do prazo que o plano prometeu.

Três medidores no topo: o que está na lixeira, o que **venceu e ainda está aqui** (normalmente zero —
diferente de zero por muito tempo significa que a varredura parou) e o que tem falha de purga.

---

## 9. Escopo — os modelos com lixeira

| App | Modelos |
|---|---|
| `empreendimentos` | `Empreendimento` |
| `obras` | `Obra`, `EtapaObra`, `DocumentoObra` |
| `clientes` | `Cliente`, `ClienteEmpreendimento`, `ContratoCliente` |
| `fornecedores` | `Fornecedor` |
| `moduloerp` | `ContaPagar`, `ContaReceber`, `NotaFiscal` |
| `moduloorcamento` | `Orcamento` — com trava por status: aprovado não sai (ver [moduloorcamento.md](../modulos/moduloorcamento.md)) |
| `rh` | `Cargo`, `Funcionario` |
| `modulocrm` | `Lead`, `Account`, `Opportunity` |

O que **não** herda `Excluivel` continua com exclusão física, e isso é o certo para o acessório
(rateio, item de nota, exceção de calendário): lixeira de tudo viraria depósito de ruído. O que o
dono pediu para poder desfazer é o objeto de valor, não a linha filha dele.

Entrar com o 17º modelo é herdar a base e gerar a migration — a tela, a varredura, a permissão e a
paywall já valem para ele.

---

## 10. O que mudou em relação ao desenho de 2026

| Desenho anterior | O que ficou | Por quê |
|---|---|---|
| `Lixo.payload` com o objeto e os filhos em JSON | **removido** | o objeto nunca sai do lugar |
| Hard-delete na exclusão | **lápide**; o hard-delete foi para a purga | `PROTECT` impedia; e o plano modelo morria junto |
| §3 "Garantia de ID — sem reutilização", `setval()`, conflito 409 | **sem assunto** | restaurar não reinsere nada |
| `POST /api/lixo/mover/` | **removido** | o `DELETE` do módulo já autoriza e já sabe o alvo |
| Papel via `RequireRole('gestor_lixo')` | **permissões** `plataforma.lixo.*` | é o catálogo que a casa usa desde a Fase 9 |
| Purga hard-deleta a linha do `Lixo` | a linha **fica**, com `purgado_em` | apagar o log no momento em que ele vira a única prova |
| Retenção padrão 30 dias, configurável por tenant | **`lixo_retencao_dias` por plano**, 15 nos contratados | decisão do dono: é paywall, não configuração |
| `ConfiguracaoLixo` (auto-purge on/off, notificar antes) | **não existe** | a purga não é opcional — é ela que corta o custo |

---

## 11. LGPD

O payload em JSON era o problema de PII em repouso que a prancha anterior previa — ele não existe
mais. O que fica é o `rotulo` (o nome do objeto) e o nome de quem apagou.

A lápide **não** é anonimização: um titular que exerce o direito ao esquecimento precisa que o dado
saia de verdade, e para isso existe a purga manual do `gestor_lixo`, que não espera o prazo. O
tratamento completo do art. 18 continua endereçado ao fluxo de LGPD da Fase 9
([acesso-e-permissoes.md](../acesso-e-permissoes.md)), que é quem sabe *quais* colunas são do titular
— a lixeira sabe apenas que o registro saiu de circulação.
