# backend/modulopdca/models.py
"""PDCA — planejar, executar, verificar e agir sobre a obra.

**Fatia PDCA.0: a fundação.** O **esqueleto** que todas as fatias seguintes
endereçam:

- `LocalObra` é *onde*. A hierarquia construtiva (torre → pavimento → unidade →
  ambiente, ou frente → trecho → estaca na obra linear) é o eixo vertical da
  linha de balanço e o endereço da não-conformidade. Sem ela, a PDCA.6 não tem
  em que desenhar a reta e a PDCA.7 não tem onde fincar o pino.
- `CalendarioTrabalho` é *quando*. O calendário de **feriado** já existe no
  `modulocalendar` desde a Fatia F; o de **trabalho** — jornada, dias úteis,
  parada de obra — não existia, e sem ele toda duração em dias úteis da PDCA.1
  seria chute.

**Fatia PDCA.1: o plano de tempo.** Sobre o esqueleto entra o *quando de cada
coisa*: `Cronograma` (versionado, e a versão anterior é a linha de base),
`Atividade` (a WBS própria do PDCA) e `Precedencia` (o grafo sobre o qual o CPM
roda). É esta fatia que fecha a coluna **Plan** da tabela da §1 — o plano de
custo já existia no Orçamento; o de tempo não existia em lugar nenhum.

**Fatia PDCA.2: o avanço.** O plano passa a ser confrontado com a obra.
`ApontamentoAvanco` é o livro-razão do *quanto andou* — **append-only**,
porque é dele que a medição da PDCA.3 vai nascer, e histórico reescrito é
dinheiro sem rastro. O avanço da folha é a soma dos seus apontamentos; o do
pai é a média ponderada pelo peso dos filhos; e a curva S deixa de ter só a
linha prevista.

**Fatia PDCA.3: o dinheiro.** O avanço deixa de ser só leitura e passa a sair
do caixa. `ContratoObra` e `ItemContrato` são *o que foi combinado*; `Medicao`
e `ItemMedicao` são *o que se paga deste período*, **proposto a partir do
avanço** e conferido por gente (§11.4); e a escada de atesto do `nucleo`
congela o documento no último degrau, gerando o título no ERP (§11.5). A
`LiberacaoRetencao` fecha o ciclo do que ficou retido.

Planta: docs/modulos/modulopdca.md §4.1, §4.2, §4.3 e §4.4.
"""
from __future__ import annotations

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.utils.translation import gettext_lazy as _

from nucleo.tenancy import Excluivel, TenantScopedModel


class NivelLocal(models.TextChoices):
    """Os degraus da hierarquia construtiva.

    É uma lista fechada, e não texto livre, porque a linha de balanço ordena por
    ela: "3º pavimento" tem de ficar acima de "2º pavimento" no eixo Y sem que o
    software precise adivinhar o que a palavra significa. A obra vertical usa os
    quatro primeiros; a linear, os três seguintes; `AREA` é a saída para o que
    não é nem uma coisa nem outra (pátio, canteiro, área de vivência).
    """

    BLOCO = "bloco", _("Bloco / Torre")
    PAVIMENTO = "pavimento", _("Pavimento")
    UNIDADE = "unidade", _("Unidade")
    AMBIENTE = "ambiente", _("Ambiente")
    FRENTE = "frente", _("Frente de serviço")
    TRECHO = "trecho", _("Trecho")
    ESTACA = "estaca", _("Estaca")
    AREA = "area", _("Área")


class LocalObra(TenantScopedModel):
    """Um lugar dentro da obra, na árvore que a empresa desenhou.

    **Recursivo por `pai`**, no mesmo padrão sintético × analítico do `ItemOrcado`
    — que já provou aguentar árvore grande. A profundidade é guardada em coluna
    (`profundidade`) em vez de recalculada a cada leitura: o teto de
    `payment/planos.py` é conferido na escrita, e a tela ordena a árvore inteira
    sem N consultas.

    Dois vínculos **opcionais**, e a opcionalidade é o desenho:

    - `maps_local` — a torre tem coordenada, o ambiente não precisa;
    - `unidade` — o apartamento 101 **já existe** como `empreendimentos.Unidade`,
      que é a unidade *vendável*. Este é o mesmo apartamento visto pela obra.
      Ligar os dois é o que faz o avanço físico apurado chegar ao portal do
      cliente sem digitação (planta §6); não ligar é legítimo — obra linear,
      reforma e área comum não têm unidade vendável nenhuma.
    """

    local_id = models.AutoField(primary_key=True)
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE, related_name="locais_obra",
        verbose_name=_("Obra"),
    )
    pai = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE,
        related_name="filhos", verbose_name=_("Local pai"),
    )
    nivel = models.CharField(
        max_length=12, choices=NivelLocal.choices, verbose_name=_("Nível"),
    )
    #: Curto e estável — "T1", "P03", "101". É por ele que a importação de
    #: cronograma e a carga em lote reencontram o local sem depender do nome,
    #: que o cliente reescreve.
    codigo = models.CharField(max_length=40, verbose_name=_("Código"))
    nome = models.CharField(max_length=150, verbose_name=_("Nome"))
    #: Ordem entre irmãos. O 10º pavimento tem de vir depois do 9º, e ordenar por
    #: texto poria "P10" antes de "P9".
    ordem = models.PositiveIntegerField(default=0, verbose_name=_("Ordem"))
    profundidade = models.PositiveSmallIntegerField(
        default=1, editable=False, verbose_name=_("Profundidade"),
    )

    maps_local = models.ForeignKey(
        "modulomaps.Local", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="locais_obra", verbose_name=_("Ponto no mapa"),
    )
    unidade = models.ForeignKey(
        "empreendimentos.Unidade", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="locais_obra", verbose_name=_("Unidade vendável"),
    )

    #: Área do local. Alimenta o indicador de produtividade da PDCA.9 (m² por
    #: homem-hora) e o rateio de serviço por local. Nulo é honesto: ninguém tem
    #: a área de todo ambiente no dia em que cadastra a torre.
    area_m2 = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name=_("Área (m²)"),
    )
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    #: A escada de atesto (`nucleo`) morre junto com o objeto aprovado. Declarada
    #: aqui porque o `nucleo` não pode importar módulo nenhum de volta.
    aprovacoes = GenericRelation(
        "nucleo.PedidoAprovacao",
        content_type_field="alvo_tipo", object_id_field="alvo_id",
    )

    class Meta:
        verbose_name = _("Local da obra")
        verbose_name_plural = _("Locais da obra")
        ordering = ["obra", "profundidade", "ordem", "codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "obra", "pai", "codigo"],
                condition=models.Q(pai__isnull=False),
                name="pdca_local_codigo_unico_entre_irmaos",
            ),
            # A raiz precisa da própria constraint: no Postgres dois NULL são
            # **distintos**, então a de cima deixaria passar duas torres "T1" na
            # mesma obra — que é exatamente o caso em que o gerador em lote é
            # chamado duas vezes por engano.
            models.UniqueConstraint(
                fields=["tenant", "obra", "codigo"],
                condition=models.Q(pai__isnull=True),
                name="pdca_local_codigo_unico_na_raiz",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "obra", "nivel"], name="pdca_local_obra_nivel_idx"),
            models.Index(fields=["pai"], name="pdca_local_pai_idx"),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.nome}"


class CalendarioTrabalho(TenantScopedModel):
    """Jornada e dias trabalhados — o que transforma "12 dias de duração" em duas
    datas no eixo do Gantt.

    **Consome** os feriados que o `modulocalendar` já sincroniza (federais,
    estaduais e municipais, por localidade) em vez de manter uma segunda lista:
    duas listas de feriado divergem no primeiro ano em que um município cria um
    padroeiro, e aí o cronograma e a agenda contam dias diferentes para a mesma
    obra.

    Escopo em dois níveis: `obra` nula = calendário da **empresa** (o padrão que
    toda obra herda); `obra` preenchida = o dessa obra. A frente de serviço com
    jornada própria — turno da noite, obra de rodovia que para na chuva — ganha
    calendário próprio na PDCA.1, quando a atividade puder apontar para um.
    """

    calendario_id = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=120, verbose_name=_("Nome"))
    obra = models.ForeignKey(
        "obras.Obra", null=True, blank=True, on_delete=models.CASCADE,
        related_name="calendarios_trabalho", verbose_name=_("Obra"),
    )
    #: O calendário que vale para as obras sem um seu. Um por tenant.
    padrao = models.BooleanField(default=False, verbose_name=_("Padrão da empresa"))

    trabalha_segunda = models.BooleanField(default=True, verbose_name=_("Segunda"))
    trabalha_terca = models.BooleanField(default=True, verbose_name=_("Terça"))
    trabalha_quarta = models.BooleanField(default=True, verbose_name=_("Quarta"))
    trabalha_quinta = models.BooleanField(default=True, verbose_name=_("Quinta"))
    trabalha_sexta = models.BooleanField(default=True, verbose_name=_("Sexta"))
    #: Sábado nasce **desligado**. A jornada 44h da construção civil brasileira
    #: costuma compensar o sábado na semana; quem trabalha aos sábados liga, e
    #: assume o efeito no prazo por escrito.
    trabalha_sabado = models.BooleanField(default=False, verbose_name=_("Sábado"))
    trabalha_domingo = models.BooleanField(default=False, verbose_name=_("Domingo"))

    #: Quantas horas rende um dia trabalhado. É o conversor entre a duração em
    #: dias do cronograma e o homem-hora da apropriação (PDCA.9).
    horas_por_dia = models.DecimalField(
        max_digits=4, decimal_places=2, default=8.8,
        verbose_name=_("Horas por dia"),
    )

    #: Se os feriados entram na conta. Desligar é legítimo em obra de turno
    #: contínuo (usina, rodovia com prazo de interdição).
    considera_feriados = models.BooleanField(
        default=True, verbose_name=_("Considera feriados"),
    )
    #: Localidade para a busca de feriado no `modulocalendar`. Vazio = só os
    #: nacionais — e é o padrão honesto: sem UF, afirmar um feriado estadual
    #: seria inventar. A PDCA.1 preenche isto a partir do `Local` da obra.
    uf = models.CharField(max_length=2, blank=True, verbose_name=_("UF"))
    ibge = models.CharField(
        max_length=7, blank=True, verbose_name=_("Código IBGE do município"),
    )

    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Calendário de trabalho")
        verbose_name_plural = _("Calendários de trabalho")
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"], condition=models.Q(padrao=True),
                name="pdca_um_calendario_padrao_por_tenant",
            ),
        ]

    def __str__(self):
        return self.nome

    @property
    def dias_da_semana(self) -> tuple[bool, ...]:
        """Segunda a domingo, na ordem do `date.weekday()` (0 = segunda)."""
        return (
            self.trabalha_segunda, self.trabalha_terca, self.trabalha_quarta,
            self.trabalha_quinta, self.trabalha_sexta, self.trabalha_sabado,
            self.trabalha_domingo,
        )


class ExcecaoCalendario(TenantScopedModel):
    """O dia que foge da regra: recesso de fim de ano, parada por chuva, mutirão
    de sábado. Existe porque sem ela toda parada de obra vira edição do
    calendário inteiro — e o cronograma de janeiro passaria a recontar dezembro.
    """

    excecao_id = models.AutoField(primary_key=True)
    calendario = models.ForeignKey(
        CalendarioTrabalho, on_delete=models.CASCADE, related_name="excecoes",
        verbose_name=_("Calendário"),
    )
    data = models.DateField(verbose_name=_("Data"))
    #: `False` = não se trabalha (recesso, chuva); `True` = trabalha-se num dia
    #: que a regra semanal ou o feriado excluiriam (mutirão de sábado). A exceção
    #: vence os dois — é o registro mais específico que existe sobre aquele dia.
    trabalha = models.BooleanField(default=False, verbose_name=_("Trabalha"))
    motivo = models.CharField(max_length=150, blank=True, verbose_name=_("Motivo"))

    class Meta:
        verbose_name = _("Exceção de calendário")
        verbose_name_plural = _("Exceções de calendário")
        ordering = ["calendario", "data"]
        constraints = [
            models.UniqueConstraint(
                fields=["calendario", "data"], name="pdca_uma_excecao_por_dia",
            ),
        ]

    def __str__(self):
        return f"{self.data:%d/%m/%Y} — {'trabalha' if self.trabalha else 'parado'}"


# ---------------------------------------------------------------------------
# PDCA.1 — o plano de tempo
# ---------------------------------------------------------------------------


class Cronograma(TenantScopedModel):
    """O plano da obra, **versionado** — e é do versionamento que a linha de base
    cai de graça.

    O P6 vende "linhas de base ilimitadas" como diferencial sobre o MS Project
    (que guarda uma só). Aqui não é recurso: é consequência de o cronograma
    seguir o mesmo padrão do `Orcamento` — rascunho → vigente, e replanejar cria
    a **versão seguinte** com motivo obrigatório, rebaixando a anterior a
    `substituido`. Toda versão anterior continua legível, e comparar o vigente
    com qualquer uma delas responde a pergunta que o planejador realmente faz:
    *atrasou quanto desde que a gente combinou?*

    **Um vigente por obra**, garantido por constraint parcial. Duas versões
    vigentes ao mesmo tempo seriam duas verdades sobre o mesmo prazo — e é sobre
    o prazo vigente que a medição da PDCA.3 será calculada.
    """

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        VIGENTE = "vigente", _("Vigente")
        SUBSTITUIDO = "substituido", _("Substituído")

    cronograma_id = models.AutoField(primary_key=True)
    #: **Nulo só no plano modelo órfão** (D116). O vínculo é `CASCADE` — plano é
    #: da obra e morre com ela —, mas o dono mandou o modelo sobreviver:
    #: *"deixa o plano para poder ser usado como modelo em outra obra"*. Quando a
    #: purga da lixeira vai apagar a obra de verdade, o receptor de
    #: `antes_de_purgar` (`modulopdca/signals.py`) desliga daqui os cronogramas
    #: marcados `eh_modelo` — e eles viram o que já eram por definição: um padrão
    #: **da empresa**, não daquela obra. Que essa era a natureza do modelo já
    #: estava escrito na constraint de nome, que é única por `tenant`, e não por
    #: obra. A `CheckConstraint` abaixo impede o nulo de vazar para o plano comum.
    obra = models.ForeignKey(
        "obras.Obra", null=True, blank=True, on_delete=models.CASCADE,
        related_name="cronogramas", verbose_name=_("Obra"),
    )
    descricao = models.CharField(max_length=150, verbose_name=_("Descrição"))
    versao = models.PositiveIntegerField(default=1, verbose_name=_("Versão"))
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.RASCUNHO,
        verbose_name=_("Status"),
    )

    #: A âncora do CPM: nenhuma atividade começa antes desta data. É informada, e
    #: não derivada da obra, porque replanejar no meio da obra ancora o plano
    #: novo em hoje, não no dia em que a obra começou.
    data_inicio = models.DateField(verbose_name=_("Início do plano"))

    #: O calendário que as atividades herdam quando não declaram um seu. Nulo é
    #: honesto — a empresa ainda não disse quando trabalha —, e o CPM recusa
    #: rodar assim em vez de inventar segunda a sexta.
    calendario = models.ForeignKey(
        CalendarioTrabalho, null=True, blank=True, on_delete=models.PROTECT,
        related_name="cronogramas", verbose_name=_("Calendário padrão"),
    )

    #: De qual versão este cronograma nasceu. É o fio que liga a linha de base ao
    #: plano vigente; nulo só na primeira versão.
    origem = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="derivados", verbose_name=_("Versão de origem"),
    )
    #: **Obrigatório da versão 2 em diante** (cobrado no serviço de replanejar).
    #: Replanejamento sem motivo declarado é o que transforma linha de base em
    #: enfeite: se o plano pode mudar sem justificativa, comparar com ele não
    #: responde nada.
    motivo_replanejamento = models.TextField(
        blank=True, verbose_name=_("Motivo do replanejamento"),
    )

    publicado_em = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Publicado em"),
    )
    #: Rótulo durável de quem publicou — no molde do `AuditLog`, que congela o
    #: nome para o registro sobreviver ao desligamento da pessoa.
    publicado_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Publicado por"),
    )

    #: Quando o CPM rodou pela última vez sobre esta versão. Nulo = as datas das
    #: atividades ainda não são resultado de cálculo nenhum, e a tela precisa
    #: dizer isso em vez de desenhar barras que parecem calculadas.
    calculado_em = models.DateTimeField(
        null=True, blank=True, editable=False, verbose_name=_("Calculado em"),
    )
    #: Término do projeto pelo CPM — o maior término entre as atividades. Guardado
    #: para a carteira multi-obra não ter de recalcular o cronograma inteiro só
    #: para escrever uma data numa linha de lista.
    termino_calculado = models.DateField(
        null=True, blank=True, editable=False, verbose_name=_("Término calculado"),
    )

    # -- Plano modelo (PDCA.1b) ---------------------------------------------
    #
    # *Decisão do dono, 23/08/2026:* **"deixa o plano para poder ser usado como
    # modelo em outra obra — para não ter que criar 300 planos em um
    # empreendimento grande. É só ele colocar como plano modelo e usar esse plano
    # para outras obras."**
    #
    # Por que é uma marca no cronograma, e não uma tabela `PlanoModelo`: um modelo
    # É um cronograma — mesma WBS, mesmas durações, mesma rede. Uma tabela paralela
    # obrigaria a manter duas cópias da mesma estrutura e dois caminhos de código
    # para tudo que a percorre (CPM, cobertura, exportação), e no dia em que as
    # duas divergissem a biblioteca de padrões passaria a mentir sobre o que
    # produz. Marcar é o que preserva a garantia de que o modelo aplicado gera
    # exatamente o plano que se viu ao salvá-lo.
    eh_modelo = models.BooleanField(
        default=False, verbose_name=_("É plano modelo"),
    )
    #: O nome pelo qual o modelo é escolhido na hora de aplicar — "Torre
    #: residencial 20 pav." vale mais que "Plano da Obra 47 v3". Único por
    #: empresa **entre os modelos**, por decisão do dono ("plano modelo pode ter
    #: apenas 1 nome por plano modelo"): duas bibliotecas com o mesmo nome é a
    #: forma mais rápida de alguém aplicar o padrão errado numa obra inteira.
    #: `default=""` não é enfeite: `nome_modelo` participa de uma
    #: `UniqueConstraint`, e o DRF torna **obrigatório** todo campo de constraint
    #: que não tenha default — o efeito era pedir o nome do modelo ao cadastrar
    #: um cronograma comum, que não é modelo nenhum.
    nome_modelo = models.CharField(
        max_length=120, blank=True, default="", verbose_name=_("Nome do modelo"),
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    aprovacoes = GenericRelation(
        "nucleo.PedidoAprovacao",
        content_type_field="alvo_tipo", object_id_field="alvo_id",
    )

    class Meta:
        verbose_name = _("Cronograma")
        verbose_name_plural = _("Cronogramas")
        # `obra_id`, e não `obra`: ordenar pelo NOME do campo faz o Django seguir
        # o `Meta.ordering` da `Obra` (`nome_obra`) e montar um JOIN. Desde que
        # `obra` virou nulável (D116, o plano modelo órfão) esse JOIN é LEFT
        # OUTER, e o Postgres recusa `SELECT ... FOR UPDATE` sobre o lado nulável
        # de um outer join. A cadeia era indireta e por isso fácil de não ver:
        # `Atividade.Meta.ordering` começa por `cronograma`, que expandia para cá,
        # que expandia para a obra — e o lock do apontamento de avanço
        # (`services.apontar`) quebrava sem nunca mencionar cronograma nenhum.
        ordering = ["obra_id", "-versao"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "obra", "versao"],
                name="pdca_cronograma_versao_unica_por_obra",
            ),
            # A unicidade é **condicional**: vale entre os modelos e ignora os
            # planos comuns, que não têm nome de modelo nenhum. Sem a condição,
            # o vazio de todos eles colidiria entre si na primeira linha.
            models.UniqueConstraint(
                fields=["tenant", "nome_modelo"],
                condition=models.Q(eh_modelo=True),
                name="pdca_cronograma_nome_modelo_unico",
            ),
            models.UniqueConstraint(
                fields=["tenant", "obra"],
                condition=models.Q(status="vigente"),
                name="pdca_um_cronograma_vigente_por_obra",
            ),
            # O nulo de `obra` existe para UM caso só: o plano modelo que
            # sobreviveu à purga da obra de origem (D116). Sem esta trava, um
            # cronograma comum órfão passaria despercebido — e um plano sem obra
            # que não é modelo não é nada: não aparece em obra nenhuma, não é
            # aplicável, e ainda ocupa a quota do tenant.
            models.CheckConstraint(
                check=models.Q(obra__isnull=False) | models.Q(eh_modelo=True),
                name="pdca_cronograma_sem_obra_so_se_modelo",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "obra", "status"], name="pdca_crono_obra_status_idx"),
        ]

    def __str__(self):
        return f"{self.descricao} (v{self.versao})"

    @property
    def editavel(self) -> bool:
        """Só rascunho se edita. Vigente congela — e substituído é história.

        Sem isto, corrigir a duração de uma atividade no plano vigente mudaria
        em silêncio a régua contra a qual o atraso é medido, que é o mesmo
        defeito que a medição retificadora da PDCA.3 existe para evitar.
        """
        return self.status == self.Status.RASCUNHO


class Atividade(TenantScopedModel):
    """A WBS **própria do PDCA** — recursiva, sintética × analítica, no mesmo
    padrão do `ItemOrcado` que já provou aguentar árvore grande.

    **Por que não ampliar a `EtapaObra`** (planta §11.1): ela é cadastro de
    macro-fase, fundação de vários módulos, e não comporta a granularidade de um
    cronograma real. O vínculo com ela existe e é **opcional** — é o que traduz a
    WBS para a dimensão `(obra, etapa)` que Orçamento e SIL já compartilham.

    Os dois vínculos opcionais são o coração da integração:

    - `etapa` — o mapeamento com a macro-fase que a obra já cadastrou;
    - `item_orcado` — a régua de **custo**. Vinculada, a atividade sabe quanto
      vale o que executa, e o avanço da PDCA.2 vira dinheiro sem digitação.

    **Sintética não tem duração**: ela é o intervalo dos filhos. Quem tem duração,
    precedência e peso próprio é a folha — e é só a folha que entra no grafo do
    CPM (§ `services.calcular_cpm`).
    """

    atividade_id = models.AutoField(primary_key=True)
    cronograma = models.ForeignKey(
        Cronograma, on_delete=models.CASCADE, related_name="atividades",
        verbose_name=_("Cronograma"),
    )
    pai = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE,
        related_name="filhos", verbose_name=_("Atividade pai"),
    )
    #: O código da EAP — "1.2.3". Curto e estável, é por ele que a importação de
    #: MS Project/P6 (seam da §10) reencontra a atividade sem depender do nome.
    codigo = models.CharField(max_length=40, verbose_name=_("Código"))
    nome = models.CharField(max_length=200, verbose_name=_("Nome"))
    ordem = models.PositiveIntegerField(default=0, verbose_name=_("Ordem entre irmãos"))
    profundidade = models.PositiveSmallIntegerField(
        default=1, editable=False, verbose_name=_("Profundidade"),
    )

    #: Em dias **úteis** do calendário da atividade, e o dia de início conta como
    #: o primeiro — a convenção do MS Project e do P6, que é a que o planejador
    #: espera: duração 1 termina no mesmo dia. Nulo na sintética.
    duracao_dias = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("Duração (dias úteis)"),
    )
    #: O `Marco` da v01 é **atividade de duração zero**, não uma segunda tabela.
    #: Concretagem liberada, alvará emitido, entrega das chaves: instante, não
    #: intervalo — e no Gantt ele é o losango, não a barra.
    eh_marco = models.BooleanField(default=False, verbose_name=_("É marco"))

    #: Restrição de data no molde do "Não iniciar antes de" do MS Project. É o
    #: que ancora a atividade que depende do mundo (chegada de equipamento
    #: importado, licença com data marcada) e não de uma predecessora.
    nao_comecar_antes_de = models.DateField(
        null=True, blank=True, verbose_name=_("Não começar antes de"),
    )

    #: Calendário próprio. Nulo herda o do cronograma — e ter um seu é o que
    #: atende a frente de turno da noite ou a que para na chuva sem obrigar a
    #: obra inteira ao mesmo expediente.
    calendario = models.ForeignKey(
        CalendarioTrabalho, null=True, blank=True, on_delete=models.PROTECT,
        related_name="atividades", verbose_name=_("Calendário"),
    )
    local = models.ForeignKey(
        LocalObra, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="atividades", verbose_name=_("Local da obra"),
    )
    etapa = models.ForeignKey(
        "obras.EtapaObra", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="atividades_pdca", verbose_name=_("Etapa da obra"),
    )
    item_orcado = models.ForeignKey(
        "moduloorcamento.ItemOrcado", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="atividades_pdca", verbose_name=_("Item orçado"),
    )

    #: O peso com que a atividade pondera o avanço do pai, **quando não há
    #: vínculo com o orçamento**. Havendo vínculo, o peso é o valor orçado e este
    #: campo é ignorado — e a API diz qual das duas origens valeu, porque duas
    #: fontes silenciosas para o mesmo número é como se perde a confiança nas
    #: duas (planta §11.2).
    peso_informado = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        verbose_name=_("Peso informado"),
    )

    responsavel = models.ForeignKey(
        "rh.Funcionario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="atividades_pdca", verbose_name=_("Responsável"),
    )

    # --- Derivados do CPM (services.calcular_cpm) ---------------------------
    # Guardados em coluna, e não recalculados a cada leitura, pelo mesmo motivo
    # da `profundidade` do LocalObra: a tela lê a árvore inteira, e o CPM é fonte
    # de verdade para prazo — o valor que a tela mostra tem de ser o mesmo que o
    # servidor calculou, não uma segunda conta feita no navegador (§5.5).
    inicio_cedo = models.DateField(null=True, blank=True, editable=False)
    termino_cedo = models.DateField(null=True, blank=True, editable=False)
    inicio_tarde = models.DateField(null=True, blank=True, editable=False)
    termino_tarde = models.DateField(null=True, blank=True, editable=False)
    folga_total = models.IntegerField(null=True, blank=True, editable=False)
    folga_livre = models.IntegerField(null=True, blank=True, editable=False)
    critica = models.BooleanField(default=False, editable=False)

    observacao = models.TextField(blank=True, verbose_name=_("Observação"))
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Atividade")
        verbose_name_plural = _("Atividades")
        ordering = ["cronograma", "ordem", "codigo", "atividade_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "cronograma", "codigo"],
                name="pdca_atividade_codigo_unico_no_cronograma",
            ),
        ]
        indexes = [
            models.Index(fields=["cronograma", "pai"], name="pdca_atividade_arvore_idx"),
            models.Index(fields=["cronograma", "critica"], name="pdca_atividade_critica_idx"),
            models.Index(fields=["cronograma", "etapa"], name="pdca_atividade_etapa_idx"),
        ]

    def __str__(self):
        return f"{self.codigo} {self.nome}".strip()

    @property
    def eh_folha(self) -> bool:
        """Folha é quem tem duração e entra no grafo. A distinção não é guardada
        em coluna de propósito: ela é consequência de ter filhos, e uma coluna
        `tipo_linha` divergiria da árvore no dia em que alguém pendurasse um
        filho numa analítica."""
        return not self.filhos.exists()


class Precedencia(TenantScopedModel):
    """A ligação entre duas atividades — e o grafo sobre o qual o CPM roda.

    Os quatro tipos são os do PMBOK e os que P6 e MS Project implementam:

    - **FS** (término → início): a mais comum. Só se reboca depois de alvenaria.
    - **SS** (início → início): as duas andam juntas, com defasagem. A pintura
      começa três dias depois de o reboco começar, andando atrás dele.
    - **FF** (término → término): terminam juntas. A limpeza termina quando o
      serviço que a suja termina.
    - **SF** (início → término): rara, e existe para turno que se substitui.

    O **atraso** (*lag*) pode ser negativo — aí é *lead*, a antecipação: começar a
    pintura dois dias **antes** de o reboco terminar. Recusá-lo obrigaria o
    planejador a picar a atividade em duas só para expressar a sobreposição.
    """

    class Tipo(models.TextChoices):
        FS = "FS", _("Término → Início (FS)")
        SS = "SS", _("Início → Início (SS)")
        FF = "FF", _("Término → Término (FF)")
        SF = "SF", _("Início → Término (SF)")

    precedencia_id = models.AutoField(primary_key=True)
    #: A predecessora — de onde a seta sai.
    origem = models.ForeignKey(
        Atividade, on_delete=models.CASCADE, related_name="sucessoras",
        verbose_name=_("Atividade predecessora"),
    )
    #: A sucessora — onde a seta chega, e quem tem a data empurrada.
    destino = models.ForeignKey(
        Atividade, on_delete=models.CASCADE, related_name="predecessoras",
        verbose_name=_("Atividade sucessora"),
    )
    tipo = models.CharField(
        max_length=2, choices=Tipo.choices, default=Tipo.FS, verbose_name=_("Tipo"),
    )
    #: Em dias úteis. Negativo é antecipação (*lead*).
    atraso_dias = models.IntegerField(default=0, verbose_name=_("Atraso (dias úteis)"))

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Precedência")
        verbose_name_plural = _("Precedências")
        ordering = ["destino", "origem"]
        constraints = [
            models.UniqueConstraint(
                fields=["origem", "destino", "tipo"],
                name="pdca_precedencia_unica",
            ),
            # Uma atividade ligada a si mesma é um ciclo de comprimento 1, e o
            # detector de ciclo do CPM o acharia — mas o banco o barra antes,
            # porque é erro de digitação, não de planejamento.
            models.CheckConstraint(
                check=~models.Q(origem=models.F("destino")),
                name="pdca_precedencia_nao_aponta_para_si",
            ),
        ]
        indexes = [
            models.Index(fields=["origem"], name="pdca_precedencia_origem_idx"),
            models.Index(fields=["destino"], name="pdca_precedencia_destino_idx"),
        ]

    def __str__(self):
        return f"{self.origem_id} →({self.tipo}{self.atraso_dias:+d}) {self.destino_id}"


# ---------------------------------------------------------------------------
# PDCA.2 — o avanço apontado
# ---------------------------------------------------------------------------


class OrigemApontamento(models.TextChoices):
    """De onde veio o apontamento — no **mesmo idioma** que o diário de obra já
    usa (`modulodiario.ORIGEM_CHOICES`).

    Não é enfeite de auditoria: a planta §9 declara três caminhos para o campo, e
    o primeiro deles — o WhatsApp — já está em produção no diário. Quando a IA
    passar a ler *"concretei 60% da laje do 3º"* e gravar aqui, a origem é o que
    permite à tela separar o que uma pessoa digitou olhando a grade do que uma
    conversa produziu. Sem ela, a fatia do WhatsApp teria de inventar a coluna
    depois, com a tabela já cheia.
    """

    WEB = "web", _("Web")
    WHATSAPP = "whatsapp", _("WhatsApp")
    APP = "app", _("Aplicativo de campo")


class ApontamentoAvanco(TenantScopedModel):
    """*Quem, quando, onde, quanto* — o livro-razão do avanço físico.

    **Append-only, e isto é a decisão central da fatia** (planta §4.3). Um
    apontamento errado **não se edita e não se apaga**: corrige-se com outro, de
    sinal contrário, que aponta para ele (`estorna`). O motivo é que o avanço é a
    base do dinheiro que sai — a medição da PDCA.3 nasce dele —, e uma linha
    alterada depois do pagamento é exatamente o rastro que uma auditoria de obra
    pública procura e não encontra. É o mesmo raciocínio da `RevisaoBaixa` do
    ERP, que já vive na casa.

    **O percentual é um delta, não um acumulado.** Apontar 30% na segunda e 25%
    na quinta deixa a atividade em 55%, e não em 25% — a leitura acumulada é
    derivada (`services.avanco_do_cronograma`), nunca gravada. Guardar o
    acumulado em coluna obrigaria a reescrever a linha anterior a cada
    apontamento, que é precisamente o que o append-only proíbe.

    **Fica pendurado na atividade, e a atividade é de uma versão do cronograma.**
    Replanejar copia a árvore e gera ids novos — por isso a leitura do avanço
    percorre a cadeia de versões pareando pelo **código** da EAP, no mesmo
    contrato de `services.comparar_com_base`. O que sobrevive à versão é o
    código; o apontamento continua preso, para sempre, à linha em que foi feito.
    """

    apontamento_id = models.AutoField(primary_key=True)

    #: **`PROTECT`, e não `CASCADE`**: excluir a atividade apagaria em silêncio o
    #: histórico de execução dela. Quem tentar leva 409 com o motivo, pela
    #: tradução de `ProtectedError` que vale para a plataforma inteira
    #: (`nucleo/excecoes.py`). Na prática a trava quase não aparece — atividade
    #: só se exclui em rascunho, e rascunho não recebe apontamento.
    atividade = models.ForeignKey(
        Atividade, on_delete=models.PROTECT, related_name="apontamentos",
        verbose_name=_("Atividade"),
    )

    #: *Onde*, dentro da obra. Opcional porque nem toda atividade é localizável
    #: ("mobilização do canteiro" não é de um pavimento), e porque é o
    #: apontamento por local que a PDCA.6 vai ler para desenhar a linha de
    #: balanço. `SET_NULL`: o lugar pode ser reorganizado sem apagar o registro
    #: de que o serviço andou.
    local = models.ForeignKey(
        LocalObra, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="apontamentos", verbose_name=_("Local da obra"),
    )

    #: O dia em que o serviço **andou** — não o dia em que alguém digitou. É o
    #: que põe o ponto da curva S realizada no lugar certo quando a semana
    #: inteira é lançada na sexta-feira, que é como obra funciona.
    data = models.DateField(verbose_name=_("Data do avanço"))

    #: O **delta**, em pontos percentuais da atividade. Negativo é o estorno.
    #: `7,4` dá folga para o ajuste fino sem virar dízima: obra grande aponta
    #: 0,25% de uma frente sem susto.
    percentual = models.DecimalField(
        max_digits=7, decimal_places=4, verbose_name=_("Avanço (%)"),
    )

    origem = models.CharField(
        max_length=20, choices=OrigemApontamento.choices,
        default=OrigemApontamento.WEB, verbose_name=_("Origem"),
    )
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))

    #: A foto do campo. Sobe pela **porta única** da plataforma
    #: (`nucleo.upload_validation`), que já impõe tipo e tamanho pelo teto do
    #: tenant — é por isso que a §5.5f do `planos.py` não declara um "bytes por
    #: apontamento" próprio, que seria um segundo número para a mesma pergunta.
    foto = models.FileField(
        upload_to="pdca_apontamento/", null=True, blank=True,
        verbose_name=_("Foto"),
    )

    #: O apontamento que este corrige. É o que transforma "apagar" em "estornar":
    #: a linha errada continua legível, a correção aponta para ela, e a soma dá o
    #: número certo. Nulo no apontamento comum.
    estorna = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="estornos", verbose_name=_("Estorna o apontamento"),
    )

    #: Rótulo durável de quem apontou — no molde do `AuditLog` e do
    #: `Cronograma.publicado_por`: o registro sobrevive ao desligamento da
    #: pessoa, e um `SET_NULL` numa FK de usuário apagaria justamente o *quem*
    #: que a planta pede.
    apontado_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Apontado por"),
    )
    registrado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Apontamento de avanço")
        verbose_name_plural = _("Apontamentos de avanço")
        ordering = ["-data", "-apontamento_id"]
        constraints = [
            # Apontamento de zero não é avanço: é ruído no livro que vai virar
            # medição. Quem quer só escrever uma observação tem o diário de obra.
            models.CheckConstraint(
                condition=models.Q(percentual__lt=0) | models.Q(percentual__gt=0),
                name="pdca_apontamento_nao_e_zero",
            ),
            # Nenhum lançamento isolado passa de 100 pontos para cada lado. O
            # **acumulado** é conferido no serviço, que sabe a soma; esta é a
            # trava do banco contra o dedo escorregado e contra qualquer caminho
            # de escrita que não passe por lá.
            models.CheckConstraint(
                condition=models.Q(percentual__gte=-100) & models.Q(percentual__lte=100),
                name="pdca_apontamento_dentro_de_cem",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "atividade", "data"], name="pdca_apont_ativ_data_idx"),
            models.Index(fields=["tenant", "data"], name="pdca_apont_data_idx"),
        ]

    def __str__(self):
        return f"{self.atividade_id} · {self.data} · {self.percentual:+}%"

    def save(self, *args, **kwargs):
        """A trava do append-only mora **aqui**, e não só na API.

        A viewset não expõe `PUT`/`PATCH`/`DELETE`, mas uma viewset é *uma*
        porta: o comando de bancada, a importação e a fatia de WhatsApp que vem
        depois entram por outras. Pôr a regra no model é o que faz "o avanço não
        se reescreve" ser propriedade do dado, e não costume de quem chamou.
        """
        if self.pk is not None:
            raise ValueError(
                "Apontamento de avanço é append-only: corrija com um apontamento "
                "de sinal contrário (estorno), em vez de editar este."
            )
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# PDCA.3 — contrato, medição e o título que sai para o ERP
# ---------------------------------------------------------------------------
#
# Aqui o módulo atravessa a fronteira do dinheiro pela primeira vez, e é por
# isso que esta é a fatia com mais trava por linha de código da casa.
#
# Três decisões da planta governam tudo o que vem abaixo:
#
# 1. **Avanço e medição são duas coisas** (§11.4). O avanço é da *atividade* e
#    existe sempre — inclusive na equipe própria, que não tem contrato. A
#    medição é do *contrato* e nasce **proposta** a partir do avanço do período,
#    para o gestor conferir e ajustar. Unificar obrigaria toda atividade a ter
#    contrato; separar sem derivação produziria dois números divergindo sem
#    ninguém notar.
# 2. **Medição aprovada congela** (§11.5). Correção é medição **retificadora**,
#    nunca edição — o mesmo rigor do orçamento aprovado, pelo mesmo motivo: é
#    dinheiro saindo.
# 3. **Saldo de contrato é derivado** (§4.9). Não há coluna de acumulado
#    medido, de saldo nem de total: `services` soma os itens. Guardar o agregado
#    criaria a segunda verdade que diverge da primeira.
#
# **O que FICA gravado, e por que isso não contradiz a (3).** O `ItemMedicao`
# guarda a quantidade **e o preço unitário do dia**, do jeito que uma nota
# fiscal guarda. Não é agregado: é o *insumo* congelado. Sem ele, corrigir o
# preço de um item de contrato em 2027 reescreveria o valor de uma medição paga
# em 2026 — que é exatamente o rastro que uma auditoria de obra procura e não
# encontra. A soma continua sendo feita na leitura; o que não muda mais são as
# parcelas.


class RegimeContrato(models.TextChoices):
    """Como o contrato mede — e são três matemáticas diferentes, não três nomes.

    - **preço unitário**: mede-se `quantidade × preço` de cada item. É o regime
      da empreitada por item, e o único em que o avanço físico converte direto
      em quantidade a pagar.
    - **preço global**: mede-se o **percentual** do valor fechado. O item
      continua existindo (é a régua de quanto cada frente pesa), mas o que se
      paga é a fração do todo.
    - **administração**: mede-se o **custo reembolsável** do período mais a taxa
      de administração. O custo não sai do avanço — sai da folha, da nota do
      material e do aplicado —, e por isso ele é **declarado** na medição com a
      origem junto (`OrigemCusto`), em vez de fingir que foi apurado.
    """

    UNITARIO = "unitario", _("Preço unitário")
    GLOBAL = "global", _("Preço global")
    ADMINISTRACAO = "administracao", _("Administração (custo + taxa)")


class NaturezaRetencao(models.TextChoices):
    """O que aquele dinheiro retido **é** — e isto governa quando ele volta.

    Não é enfeite de relatório: caução contratual e retenção técnica liberam em
    momentos diferentes (a primeira no encerramento do contrato, a segunda na
    aceitação definitiva do serviço), e quem libera é pessoa diferente. Guardar
    só o percentual deixaria a `LiberacaoRetencao` sem conseguir dizer que
    condição estava sendo atendida.
    """

    NENHUMA = "nenhuma", _("Sem retenção")
    CAUCAO = "caucao", _("Caução contratual")
    GARANTIA = "garantia", _("Garantia de execução")
    TECNICA = "tecnica", _("Retenção técnica")


class ContratoObra(TenantScopedModel, Excluivel):
    """O que foi combinado com o empreiteiro — e a régua contra a qual toda
    medição desta obra é conferida.

    **Usa o `Fornecedor` que já existe, e não um cadastro próprio** (§7 — o
    módulo *não* cadastra fornecedor). O cadastro da casa já é neutro quanto a
    ser de material ou de serviço, que é a razão de ele servir aqui sem ganhar
    um "tipo empreiteiro" que a tela teria de manter em dia.

    **`PROTECT` na obra e no fornecedor.** Contrato é documento com valor
    jurídico; apagar a obra e levar junto o contrato que gerou pagamento é
    perder a prova de para onde o dinheiro foi. Quem tentar leva 409 com o
    motivo (`nucleo/excecoes.py`), e o caminho honesto é a lixeira — o contrato
    entra nela (herda `Excluivel`), o que dá o prazo do plano para desfazer sem
    que a linha suma do banco.

    **O regime público é opção, não regime do sistema** (§11.3). Nem toda obra
    com dinheiro público segue o mesmo estatuto, e software que impõe a regra
    pela origem do dinheiro erra na exceção. Por isso `regime_publico` é um
    interruptor do usuário, e o limite legal de acréscimo é um **número que ele
    digita** — não uma constante nossa. E ele não vai para `payment/planos.py`:
    é regra de domínio, não teto comercial (§5.6 do `planos.py`).
    """

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        VIGENTE = "vigente", _("Vigente")
        SUSPENSO = "suspenso", _("Suspenso")
        ENCERRADO = "encerrado", _("Encerrado")
        CANCELADO = "cancelado", _("Cancelado")

    contrato_id = models.AutoField(primary_key=True)

    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.PROTECT, related_name="contratos_pdca",
        verbose_name=_("Obra"),
    )
    fornecedor = models.ForeignKey(
        "fornecedores.Fornecedor", on_delete=models.PROTECT,
        related_name="contratos_pdca", verbose_name=_("Empreiteiro"),
    )

    #: O número do contrato **da empresa**, não o nosso id. É por ele que o
    #: gestor procura, e é ele que aparece no título do ERP — um `ContaPagar`
    #: dizendo "Medição 3 do contrato 42" não ajuda quem confere a fatura contra
    #: a pasta do contrato.
    numero = models.CharField(max_length=40, verbose_name=_("Número do contrato"))
    objeto = models.TextField(verbose_name=_("Objeto"))

    regime = models.CharField(
        max_length=16, choices=RegimeContrato.choices,
        default=RegimeContrato.UNITARIO, verbose_name=_("Regime"),
    )

    #: O valor fechado. **Obrigatório no global e na administração**, ausente no
    #: unitário — lá o valor é a soma dos itens, e guardar um total ao lado da
    #: soma é a segunda verdade do §4.9. A constraint abaixo cobra isso.
    valor_global = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        verbose_name=_("Valor global"),
    )

    #: A taxa do regime de administração, em %. Só ela é margem do empreiteiro;
    #: o resto é reembolso de custo.
    taxa_administracao = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True,
        verbose_name=_("Taxa de administração (%)"),
    )

    data_inicio = models.DateField(verbose_name=_("Início da vigência"))
    data_fim = models.DateField(
        null=True, blank=True, verbose_name=_("Fim da vigência"),
    )
    garantia_meses = models.PositiveSmallIntegerField(
        default=0, verbose_name=_("Garantia (meses)"),
    )

    # --- A cláusula de retenção (§4.4) ------------------------------------
    #: Os três campos andam juntos de propósito: o percentual diz *quanto*, a
    #: natureza diz *o que é* e a condição diz *quando volta*. Guardar só o
    #: percentual deixaria a liberação sem conseguir declarar o que foi
    #: cumprido, e o dinheiro retido viraria saldo sem dono.
    retencao_percentual = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        verbose_name=_("Retenção (%)"),
    )
    retencao_natureza = models.CharField(
        max_length=12, choices=NaturezaRetencao.choices,
        default=NaturezaRetencao.NENHUMA, verbose_name=_("Natureza da retenção"),
    )
    retencao_condicao_liberacao = models.TextField(
        blank=True, verbose_name=_("Condição de liberação da retenção"),
    )

    # --- Regime público (§11.3), ligado pelo usuário ----------------------
    regime_publico = models.BooleanField(
        default=False, verbose_name=_("Regime público"),
    )
    #: O teto legal de acréscimo, **digitado**. 25% é o caso comum da Lei
    #: 14.133, 50% o da reforma de edifício — e existe contrato que não segue
    #: nenhum dos dois. O sistema confere contra o número que o usuário
    #: declarou; escolher o número por ele seria errar na exceção.
    limite_acrescimo_percentual = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name=_("Limite legal de acréscimo (%)"),
    )

    #: Quantos dias o título leva para vencer, contados da aprovação da medição.
    #: Fica aqui, e não em `planos.py`, porque **não é teto**: é cláusula
    #: comercial do contrato, que varia de empreiteiro para empreiteiro (§5.6).
    prazo_pagamento_dias = models.PositiveSmallIntegerField(
        default=30, verbose_name=_("Prazo de pagamento (dias)"),
    )

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.RASCUNHO,
        verbose_name=_("Status"),
    )
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Contrato de obra")
        verbose_name_plural = _("Contratos de obra")
        ordering = ["-criado_em"]
        constraints = [
            # Número único por obra, e não por tenant: a mesma construtora usa
            # "001" em obras diferentes, e proibir isso obrigaria a inventar
            # prefixo. Condicionado à lápide, como todo unique da casa desde a
            # Fase 8 — contrato na lixeira não deve bloquear o número.
            models.UniqueConstraint(
                fields=["tenant", "obra", "numero"],
                condition=models.Q(excluido_em__isnull=True),
                name="pdca_contrato_numero_unico_por_obra",
            ),
            models.CheckConstraint(
                condition=models.Q(retencao_percentual__gte=0)
                & models.Q(retencao_percentual__lte=100),
                name="pdca_contrato_retencao_entre_zero_e_cem",
            ),
            # Vigência que termina antes de começar é erro de digitação que só
            # aparece meses depois, na medição que "não cabe no período".
            models.CheckConstraint(
                condition=models.Q(data_fim__isnull=True)
                | models.Q(data_fim__gte=models.F("data_inicio")),
                name="pdca_contrato_vigencia_coerente",
            ),
            # Global e administração precisam do valor fechado; o unitário não
            # deve tê-lo (é a soma dos itens — §4.9). A trava mora no banco
            # porque o valor global é o denominador da medição por percentual:
            # nulo ali é divisão por nada no meio de um cálculo de dinheiro.
            models.CheckConstraint(
                condition=(
                    models.Q(regime=RegimeContrato.UNITARIO, valor_global__isnull=True)
                    | models.Q(regime=RegimeContrato.GLOBAL, valor_global__isnull=False)
                    | models.Q(
                        regime=RegimeContrato.ADMINISTRACAO, valor_global__isnull=False
                    )
                ),
                name="pdca_contrato_valor_global_conforme_regime",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "obra"], name="pdca_contrato_obra_idx"),
            models.Index(fields=["tenant", "status"], name="pdca_contrato_status_idx"),
        ]

    def __str__(self):
        return f"{self.numero} · {self.objeto[:40]}"


class ItemContrato(TenantScopedModel):
    """A linha do contrato — *o que* foi contratado, *quanto* e por *qual preço*.

    **Dois vínculos opcionais, e eles não são redundantes.** `item_orcado` é a
    **régua de custo**: contratado contra o orçamento aprovado, é o que permite
    dizer se o preço fechado ficou acima ou abaixo do orçado. `atividade` é a
    **ponte do avanço**: é por ela que a medição sabe quanto a frente andou no
    período.

    Na obra que tem orçamento, os dois se encontram sozinhos — a `Atividade` já
    carrega `item_orcado` desde a PDCA.1, e a proposta acha as atividades pelo
    item orçado sem precisar do vínculo direto. O campo `atividade` existe para
    a obra que **não** tem orçamento: sem ele, o contrato dessa obra não teria
    como nascer do avanço e a medição voltaria a ser digitação. Preencher os
    dois é legítimo, e o direto ganha — é o mais específico.

    **Não herda `Excluivel`, e é de propósito.** Item é linha filha de um
    documento — a mesma classe do rateio e do item de nota, que o `Excluivel`
    declara fora da lixeira. O que vai para a lixeira é o contrato inteiro.
    """

    item_contrato_id = models.AutoField(primary_key=True)

    contrato = models.ForeignKey(
        ContratoObra, on_delete=models.CASCADE, related_name="itens",
        verbose_name=_("Contrato"),
    )

    #: A régua de custo. `SET_NULL`: reorganizar o orçamento não pode apagar a
    #: linha contratada — o contrato foi assinado, e ele continua valendo mesmo
    #: que a planilha que o originou seja substituída.
    item_orcado = models.ForeignKey(
        "moduloorcamento.ItemOrcado", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="itens_contratados",
        verbose_name=_("Item orçado"),
    )
    #: A ponte do avanço, quando não há orçamento no meio. `SET_NULL` pelo mesmo
    #: motivo, com uma consequência declarada: perdido o vínculo, a proposta
    #: automática para de funcionar **para esta linha** e a medição diz isso, em
    #: vez de propor zero.
    atividade = models.ForeignKey(
        Atividade, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="itens_contratados", verbose_name=_("Atividade"),
    )

    #: O aditivo que **trouxe esta linha ao contrato**, quando ela não nasceu
    #: com ele. É o que a grade de medição marca (§4.4: *"o item aditado fica
    #: marcado nas medições seguintes"*), e é também o que autoriza a única
    #: linha de contrato com quantidade original zero — a quantidade dela mora
    #: no `ItemAditivo`, para a regra *atual = original + Σ deltas* valer sem
    #: exceção em nenhuma linha.
    aditivo_origem = models.ForeignKey(
        "AditivoContrato", null=True, blank=True, on_delete=models.PROTECT,
        related_name="itens_criados", verbose_name=_("Criado pelo aditivo"),
    )

    codigo = models.CharField(max_length=40, verbose_name=_("Item"))
    descricao = models.CharField(max_length=255, verbose_name=_("Descrição"))
    unidade = models.CharField(max_length=20, blank=True, verbose_name=_("Unidade"))
    ordem = models.PositiveIntegerField(default=0, verbose_name=_("Ordem"))

    #: `14,4` e `15,4` acompanham o `ItemOrcado`, e não o dinheiro de duas casas
    #: do ERP: aqui ainda se multiplica. Arredondar o unitário para centavo
    #: antes de multiplicar por 1.200 m³ erra em dezenas de reais — o
    #: arredondamento é do **produto**, na fronteira com o ERP, e não da parcela.
    quantidade_contratada = models.DecimalField(
        max_digits=14, decimal_places=4, verbose_name=_("Quantidade contratada"),
    )
    preco_unitario = models.DecimalField(
        max_digits=15, decimal_places=4, verbose_name=_("Preço unitário"),
    )

    observacao = models.TextField(blank=True, verbose_name=_("Observação"))
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Item de contrato")
        verbose_name_plural = _("Itens de contrato")
        ordering = ["contrato_id", "ordem", "item_contrato_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["contrato", "codigo"],
                name="pdca_item_contrato_codigo_unico",
            ),
            # Quantidade zerada passaria pela medição inteira sem erro e
            # produziria um título de R$ 0,00 — documento que ninguém consegue
            # explicar depois. Negativo é supressão, e supressão é **aditivo**,
            # não linha de contrato.
            #
            # **A exceção é o item que nasceu de aditivo**, e ela é o que mantém
            # uma regra só para todo o contrato: `contratado_atual = original +
            # Σ deltas aprovados`. Item novo tem original zero e a quantidade
            # inteira no `ItemAditivo` — sem isso, a linha aditada seria a única
            # em que a soma contaria a mesma quantidade duas vezes.
            models.CheckConstraint(
                condition=models.Q(quantidade_contratada__gt=0)
                | models.Q(aditivo_origem__isnull=False),
                name="pdca_item_contrato_quantidade_positiva",
            ),
            models.CheckConstraint(
                condition=models.Q(preco_unitario__gte=0),
                name="pdca_item_contrato_preco_nao_negativo",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "contrato"], name="pdca_item_ctr_contrato_idx",
            ),
        ]

    def __str__(self):
        return f"{self.codigo} · {self.descricao[:40]}"

    @property
    def valor_contratado(self):
        return self.quantidade_contratada * self.preco_unitario


class AcaoAditivo(models.TextChoices):
    """O que **este aditivo faz com esta linha**.

    Quatro verbos, e não um campo livre, porque cada um tem uma trava diferente:
    acréscimo bate no limite legal do regime público, supressão bate no já
    medido, revisão de preço não pode reescrever medição paga e inclusão precisa
    de código, descrição e unidade que a linha ainda não tem.
    """

    ACRESCIMO = "acrescimo", _("Acréscimo de quantidade")
    SUPRESSAO = "supressao", _("Supressão de quantidade")
    PRECO = "preco", _("Revisão de preço")
    INCLUSAO = "inclusao", _("Inclusão de item novo")


class AditivoContrato(TenantScopedModel, Excluivel):
    """O contrato mudando **por escrito** — quantidade, preço, item ou prazo.

    **Por que não basta editar a planilha contratual.** Sem este documento, a
    correção de uma quantidade contratada é um `PATCH` no `ItemContrato`: o
    número muda, o saldo muda junto, e ninguém consegue mais dizer *o que foi
    combinado no dia da assinatura* nem *quem autorizou a diferença*. É o mesmo
    buraco que a medição retificadora fecha do lado do pagamento — e é o
    primeiro achado de qualquer auditoria de contrato de obra.

    **O contratado original nunca é reescrito.** O `quantidade_contratada` do
    `ItemContrato` continua sendo o do dia da assinatura, e o que vale hoje é
    derivado: `atual = original + Σ deltas de aditivos aprovados` (§4.9 —
    derivar, não guardar a segunda verdade). O **preço** é a exceção declarada:
    ele é reescrito na linha, porque o `ItemMedicao` congela o preço do dia e
    nenhuma medição passada é afetada — e o `ItemAditivo` guarda o anterior.

    **Tem escada de atesto própria** (`pdca.aditivo.aprovar`), e ela não é a da
    medição: quem confere serviço executado não é quem autoriza a empresa a
    gastar 25% a mais do que contratou. Enquanto o aditivo não é aprovado ele
    **não muda saldo nenhum** — é intenção, como o rascunho de medição.

    **As três travas que o mercado ensina** (§4.4), todas na aplicação:

    1. a quantidade final de um item **nunca** cai abaixo do que já foi medido;
    2. no regime público, o acréscimo acumulado respeita o limite **digitado**
       no contrato (o sistema não escolhe 25% nem 50% por ninguém);
    3. preço revisado não toca em medição congelada — só vale daqui para frente.
    """

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        EM_APROVACAO = "em_aprovacao", _("Em aprovação")
        APROVADO = "aprovado", _("Aprovado")
        REPROVADO = "reprovado", _("Reprovado")
        CANCELADO = "cancelado", _("Cancelado")

    aditivo_id = models.AutoField(primary_key=True)

    #: `PROTECT` pelo mesmo motivo da medição: o aditivo é a prova de que o
    #: contratado mudou. Apagar o contrato e levá-lo junto apagaria o porquê de
    #: o saldo ser o que é.
    contrato = models.ForeignKey(
        ContratoObra, on_delete=models.PROTECT, related_name="aditivos",
        verbose_name=_("Contrato"),
    )

    #: Sequencial **por contrato**, como a empresa numera ("2º aditivo").
    numero = models.PositiveIntegerField(verbose_name=_("Número"))

    objeto = models.TextField(verbose_name=_("Objeto do aditivo"))
    #: O *porquê*, separado do *o quê*. É o campo que a auditoria lê primeiro, e
    #: é obrigatório na entrada — a mesma régua do motivo da retificadora.
    justificativa = models.TextField(verbose_name=_("Justificativa"))

    data_assinatura = models.DateField(
        null=True, blank=True, verbose_name=_("Data da assinatura"),
    )
    #: Prorrogação de prazo. Nula quando o aditivo não mexe em vigência — e um
    #: aditivo **só** de prazo é caso comum, por isso ele não exige item nenhum.
    nova_data_fim = models.DateField(
        null=True, blank=True, verbose_name=_("Nova data de fim"),
    )

    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.RASCUNHO,
        verbose_name=_("Status"),
    )

    #: Rótulo durável, no molde do resto do módulo.
    criado_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Criado por"),
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    aplicado_em = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Aplicado em"),
    )

    aprovacoes = GenericRelation(
        "nucleo.PedidoAprovacao",
        content_type_field="alvo_tipo", object_id_field="alvo_id",
    )

    class Meta:
        verbose_name = _("Aditivo de contrato")
        verbose_name_plural = _("Aditivos de contrato")
        ordering = ["contrato_id", "-numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["contrato", "numero"],
                condition=models.Q(excluido_em__isnull=True),
                name="pdca_aditivo_numero_unico_por_contrato",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "contrato", "status"],
                name="pdca_aditivo_ctr_status_idx",
            ),
        ]

    def __str__(self):
        return f"Aditivo {self.numero} · contrato {self.contrato_id}"

    @property
    def esta_congelado(self) -> bool:
        return self.status in (
            self.Status.APROVADO, self.Status.REPROVADO, self.Status.CANCELADO,
        )


class ItemAditivo(TenantScopedModel):
    """A linha do aditivo — *o que muda nesta linha do contrato*.

    `item_contrato` é nulo **só até o aditivo ser aprovado**, e só na inclusão:
    o item novo nasce no momento da aplicação, e é então que a linha passa a
    apontar para ele. Antes disso, a descrição do item que virá mora aqui
    (`codigo_novo`, `descricao_nova`, `unidade_nova`) — é o que permite montar,
    conferir e aprovar um aditivo de inclusão sem sujar a planilha contratual
    com uma linha que ainda não foi autorizada.

    `quantidade_delta` é **assinado**: positivo acrescenta, negativo suprime. É
    a mesma escolha do `ApontamentoAvanco` e do `ItemMedicao` da retificadora, e
    pelo mesmo motivo — soma de deltas dá o acumulado sem que ninguém precise
    reescrever o número anterior.
    """

    item_aditivo_id = models.AutoField(primary_key=True)

    aditivo = models.ForeignKey(
        AditivoContrato, on_delete=models.CASCADE, related_name="itens",
        verbose_name=_("Aditivo"),
    )
    #: `PROTECT`: a linha do aditivo é a razão da quantidade atual do item.
    item_contrato = models.ForeignKey(
        ItemContrato, null=True, blank=True, on_delete=models.PROTECT,
        related_name="aditivos", verbose_name=_("Item do contrato"),
    )

    acao = models.CharField(
        max_length=10, choices=AcaoAditivo.choices, verbose_name=_("Ação"),
    )

    quantidade_delta = models.DecimalField(
        max_digits=14, decimal_places=4, default=0,
        verbose_name=_("Δ quantidade"),
    )
    #: O preço que passa a valer. Nulo mantém o que está na linha.
    preco_unitario = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True,
        verbose_name=_("Preço unitário novo"),
    )
    #: O preço de antes, copiado na **aplicação**. Sem ele, "revisou o preço"
    #: não diz de quanto para quanto, e a linha do aditivo vira número solto.
    preco_unitario_anterior = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True,
        verbose_name=_("Preço unitário anterior"),
    )

    # --- Só na inclusão: o item que ainda não existe ----------------------
    codigo_novo = models.CharField(
        max_length=40, blank=True, verbose_name=_("Código do item novo"),
    )
    descricao_nova = models.CharField(
        max_length=255, blank=True, verbose_name=_("Descrição do item novo"),
    )
    unidade_nova = models.CharField(
        max_length=20, blank=True, verbose_name=_("Unidade do item novo"),
    )

    observacao = models.TextField(blank=True, verbose_name=_("Observação"))

    class Meta:
        verbose_name = _("Item de aditivo")
        verbose_name_plural = _("Itens de aditivo")
        ordering = ["aditivo_id", "item_aditivo_id"]
        constraints = [
            # Uma linha por item em cada aditivo. Duas somariam em silêncio, e o
            # gestor conferiria um total que nenhuma linha da tela explica.
            models.UniqueConstraint(
                fields=["aditivo", "item_contrato"],
                condition=models.Q(item_contrato__isnull=False),
                name="pdca_item_aditivo_unico_por_aditivo",
            ),
            models.CheckConstraint(
                condition=models.Q(preco_unitario__isnull=True)
                | models.Q(preco_unitario__gte=0),
                name="pdca_item_aditivo_preco_nao_negativo",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "item_contrato"],
                name="pdca_item_adt_item_ctr_idx",
            ),
        ]

    def __str__(self):
        return f"{self.get_acao_display()} · {self.quantidade_delta}"


class OrigemCusto(models.TextChoices):
    """De onde veio o número do custo reembolsável (regime de administração).

    **Existe porque a régua do projeto proíbe dado fabricado.** O custo do
    regime de administração não nasce do avanço nem de nenhum lançamento que o
    sistema tenha hoje — quem o conhece é a folha de pagamento, a nota do
    material e o aplicado do SIL. Enquanto a apropriação de HH (PDCA.9) e o
    seam do SIL não estiverem ligados, ele é **digitado**; e um número digitado
    que se apresenta como apurado é exatamente o que a régua chama de dado
    fabricado.

    A saída não é recusar o regime — é **declarar a origem junto do número**, de
    modo que a tela e o relatório digam "informado pelo gestor" em vez de
    deixarem quem lê supor que o sistema apurou. No dia em que a PDCA.9 chegar,
    `APROPRIADO` entra sem migração de dado e sem reinterpretar o passado.
    """

    INFORMADO = "informado", _("Informado pelo gestor")
    APROPRIADO = "apropriado", _("Apropriado pelo sistema")


class Medicao(TenantScopedModel, Excluivel):
    """O boletim do período — *quanto se paga desta vez*.

    **Nasce do avanço, não ao lado dele** (§11.4): `services.propor_medicao` lê
    os apontamentos do período e propõe a quantidade de cada item; o gestor
    confere, ajusta e só então submete. O que ele ajustou fica visível, porque
    `ItemMedicao` guarda **as duas** quantidades — a proposta e a medida.

    **Aprovada, congela** (§11.5). O último degrau da escada de atesto fecha o
    documento: nada mais se edita, e a correção é uma medição **retificadora**,
    que aponta para a corrigida (`retifica`). É o mesmo rigor do orçamento
    aprovado, pelo mesmo motivo — deste documento sai um título a pagar.

    **`conta_pagar_ref` é seam frouxo, não FK** — um `PositiveIntegerField` com
    o id da `ContaPagar`, no mesmo padrão que o `PedidoCompra` do SCM já usa. O
    PDCA não depende do app financeiro (a §7 é explícita: *não paga*), e uma FK
    faria o módulo de planejamento parar de migrar numa instalação que não
    contrate o ERP.

    > **Primeiro título gerado de verdade na plataforma.** O `conta_pagar_ref`
    > do SCM existe desde 07/2026 e nunca foi preenchido por ninguém — era seam
    > inerte. A medição aprovada é a primeira escrita real nessa fronteira.
    """

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        EM_APROVACAO = "em_aprovacao", _("Em aprovação")
        APROVADA = "aprovada", _("Aprovada")
        REPROVADA = "reprovada", _("Reprovada")
        CANCELADA = "cancelada", _("Cancelada")

    medicao_id = models.AutoField(primary_key=True)

    #: `PROTECT`: a medição é a prova do pagamento. Apagar o contrato e levar as
    #: medições junto apagaria o porquê de cada título que saiu.
    contrato = models.ForeignKey(
        ContratoObra, on_delete=models.PROTECT, related_name="medicoes",
        verbose_name=_("Contrato"),
    )

    #: Sequencial **por contrato**, como o empreiteiro numera ("3ª medição").
    numero = models.PositiveIntegerField(verbose_name=_("Número"))

    periodo_inicio = models.DateField(verbose_name=_("Início do período"))
    periodo_fim = models.DateField(verbose_name=_("Fim do período"))

    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.RASCUNHO,
        verbose_name=_("Status"),
    )

    #: A medição que esta corrige. É o que substitui a edição do documento
    #: congelado: a errada continua legível, a correção aponta para ela, e a
    #: soma dá o número certo — o mesmo desenho do estorno do apontamento.
    retifica = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="retificacoes", verbose_name=_("Retifica a medição"),
    )

    #: O percentual de retenção **do dia em que a medição foi criada**. Copiado
    #: da cláusula do contrato de propósito: mudar a cláusula em 2027 não pode
    #: reescrever o líquido de uma medição paga em 2026.
    retencao_percentual_aplicado = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        verbose_name=_("Retenção aplicada (%)"),
    )

    # --- Regime de administração (e só ele) -------------------------------
    custo_reembolsavel = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        verbose_name=_("Custo reembolsável do período"),
    )
    #: A taxa do dia, congelada pelo mesmo motivo do percentual de retenção.
    taxa_administracao_aplicada = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True,
        verbose_name=_("Taxa de administração aplicada (%)"),
    )
    custo_origem = models.CharField(
        max_length=12, choices=OrigemCusto.choices, default=OrigemCusto.INFORMADO,
        verbose_name=_("Origem do custo"),
    )

    #: O seam frouxo para o ERP — id da `ContaPagar` gerada na aprovação.
    conta_pagar_ref = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("Ref. da conta a pagar (ERP)"),
    )

    #: Rótulos duráveis, no molde do `ApontamentoAvanco.apontado_por`: o
    #: registro sobrevive ao desligamento da pessoa.
    apurada_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Apurada por"),
    )
    apurada_em = models.DateTimeField(auto_now_add=True)
    congelada_em = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Congelada em"),
    )

    observacao = models.TextField(blank=True, verbose_name=_("Observação"))

    aprovacoes = GenericRelation(
        "nucleo.PedidoAprovacao",
        content_type_field="alvo_tipo", object_id_field="alvo_id",
    )

    class Meta:
        verbose_name = _("Medição")
        verbose_name_plural = _("Medições")
        ordering = ["contrato_id", "-numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["contrato", "numero"],
                condition=models.Q(excluido_em__isnull=True),
                name="pdca_medicao_numero_unico_por_contrato",
            ),
            models.CheckConstraint(
                condition=models.Q(periodo_fim__gte=models.F("periodo_inicio")),
                name="pdca_medicao_periodo_coerente",
            ),
            models.CheckConstraint(
                condition=models.Q(retencao_percentual_aplicado__gte=0)
                & models.Q(retencao_percentual_aplicado__lte=100),
                name="pdca_medicao_retencao_entre_zero_e_cem",
            ),
            # Custo reembolsável negativo viraria título negativo no ERP — que o
            # `ContaPagar` aceita e ninguém consegue baixar.
            models.CheckConstraint(
                condition=models.Q(custo_reembolsavel__isnull=True)
                | models.Q(custo_reembolsavel__gte=0),
                name="pdca_medicao_custo_nao_negativo",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "contrato", "status"],
                name="pdca_medicao_ctr_status_idx",
            ),
            models.Index(
                fields=["tenant", "periodo_fim"], name="pdca_medicao_periodo_idx",
            ),
        ]

    def __str__(self):
        return f"Medição {self.numero} · contrato {self.contrato_id}"

    @property
    def esta_congelada(self) -> bool:
        """Aprovada e reprovada não se editam mais. **Cancelada também não** —
        um documento retirado que voltasse a ser editável seria o caminho para
        reaproveitar número de medição, que é o que uma auditoria procura."""
        return self.status in (
            self.Status.APROVADA, self.Status.REPROVADA, self.Status.CANCELADA,
        )


class ItemMedicao(TenantScopedModel):
    """A linha do boletim — quanto **deste** item andou no período.

    **Guarda três números, e cada um responde a uma pergunta diferente:**

    - `quantidade` é o que se paga. É o que o gestor confirmou.
    - `quantidade_proposta` é o que o sistema calculou a partir do avanço. Fica
      guardado para a tela poder mostrar *"o gestor ajustou de 120 para 95"* —
      sem isso, o ajuste é invisível e a proposta automática vira uma caixa
      preta que ninguém audita.
    - `preco_unitario` é o preço **do dia**, copiado do item de contrato. É o
      que congela o documento de verdade (ver a nota do cabeçalho do bloco).

    `percentual_avanco_periodo` é o rastro de *como* a proposta foi feita: o
    avanço físico que a originou. Nulo quando a linha foi digitada — e a
    diferença entre nulo e zero importa, porque zero é "não andou" e nulo é
    "ninguém mediu isto pelo avanço".
    """

    class Origem(models.TextChoices):
        AVANCO = "avanco", _("Proposta pelo avanço")
        MANUAL = "manual", _("Digitada")

    item_medicao_id = models.AutoField(primary_key=True)

    medicao = models.ForeignKey(
        Medicao, on_delete=models.CASCADE, related_name="itens",
        verbose_name=_("Medição"),
    )
    #: `PROTECT`: apagar um item de contrato que já foi medido apagaria a razão
    #: de uma linha paga.
    item_contrato = models.ForeignKey(
        ItemContrato, on_delete=models.PROTECT, related_name="medicoes",
        verbose_name=_("Item do contrato"),
    )

    quantidade = models.DecimalField(
        max_digits=14, decimal_places=4, verbose_name=_("Quantidade medida"),
    )
    #: **Saldo** de material posto na obra e ainda não aplicado — não delta.
    #:
    #: É a coluna E da G703 (*materials presently stored*), e ela é a única
    #: quantidade do documento que **não** é do período: cada medição declara o
    #: estoque que existe **agora**, e o que se paga de material nesta é a
    #: diferença contra o que a medição anterior declarava. Fosse delta, um
    #: estoque parado dois meses apareceria como zero e o gestor não veria que
    #: ainda há material pago sem aplicar.
    #:
    #: A aplicação do material não devolve nada: ele sai daqui (o estoque cai) e
    #: entra em `quantidade` (o serviço executado). As duas diferenças se
    #: cancelam, e por isso **ninguém paga duas vezes** pela mesma unidade.
    quantidade_estocada = models.DecimalField(
        max_digits=14, decimal_places=4, default=0,
        verbose_name=_("Material estocado (saldo)"),
    )
    quantidade_proposta = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        verbose_name=_("Quantidade proposta"),
    )
    preco_unitario = models.DecimalField(
        max_digits=15, decimal_places=4, verbose_name=_("Preço unitário"),
    )
    percentual_avanco_periodo = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
        verbose_name=_("Avanço do período (%)"),
    )
    origem = models.CharField(
        max_length=8, choices=Origem.choices, default=Origem.AVANCO,
        verbose_name=_("Origem da linha"),
    )
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))

    class Meta:
        verbose_name = _("Item de medição")
        verbose_name_plural = _("Itens de medição")
        ordering = ["medicao_id", "item_medicao_id"]
        constraints = [
            # Um item por medição. Duas linhas do mesmo item na mesma medição
            # somariam em silêncio e estourariam o acumulado sem que a grade
            # mostrasse onde.
            models.UniqueConstraint(
                fields=["medicao", "item_contrato"],
                name="pdca_item_medicao_unico_por_medicao",
            ),
            # Quantidade negativa **é** permitida, e só aqui: é como a
            # retificadora devolve quantidade medida a mais. O piso de zero mora
            # no acumulado, que o serviço confere — não nesta linha isolada.
            models.CheckConstraint(
                condition=models.Q(preco_unitario__gte=0),
                name="pdca_item_medicao_preco_nao_negativo",
            ),
            # Estoque negativo não é devolução — é erro de digitação. A
            # devolução de material estocado é ele **cair**, e cair a zero já
            # devolve tudo. O teto (executado + estocado ≤ contratado) é do
            # acumulado e mora no serviço, como o da quantidade.
            models.CheckConstraint(
                condition=models.Q(quantidade_estocada__gte=0),
                name="pdca_item_medicao_estocado_nao_negativo",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "item_contrato"],
                name="pdca_item_med_item_ctr_idx",
            ),
        ]

    def __str__(self):
        return f"{self.item_contrato_id} · {self.quantidade}"

    @property
    def valor(self):
        return self.quantidade * self.preco_unitario


class TipoDeducao(models.TextChoices):
    """O que está sendo descontado da medição — **tipado, não texto livre**.

    O tipo não é decoração: é o que permite ao financeiro conciliar a guia de
    INSS com as medições que a originaram, e ao gestor responder *"por que o
    empreiteiro recebeu 82% do que mediu?"* sem abrir cinco documentos.

    `OUTROS` existe porque a lista nunca fecha, e ele **exige descrição** — a
    trava mora no serviço, pelo mesmo motivo que o motivo da retificadora é
    obrigatório.
    """

    INSS = "inss", _("Retenção de INSS")
    ISS = "iss", _("Retenção de ISS")
    IRRF = "irrf", _("Retenção de IRRF")
    ADIANTAMENTO = "adiantamento", _("Amortização de adiantamento")
    MATERIAL = "material", _("Material fornecido pela contratante")
    MULTA = "multa", _("Multa contratual")
    OUTROS = "outros", _("Outros")


class DeducaoMedicao(TenantScopedModel):
    """O que sai do bruto **além da retenção contratual**.

    **Por que não bastava a retenção.** O `retencao_percentual_aplicado` é uma
    cláusula do contrato: dinheiro que a construtora segura e **devolve** quando
    a condição é cumprida (`LiberacaoRetencao`). Imposto retido não volta — vai
    para a União —, adiantamento amortizado já foi pago antes, e multa é
    penalidade. Somar tudo num percentual só faria a `LiberacaoRetencao` oferecer
    de volta dinheiro que nunca foi da construtora.

    **Percentual ou valor, nunca os dois.** O percentual guarda a *regra* (11%
    sobre a mão de obra) e a base guarda sobre *o quê*; o valor guarda o número
    quando não há regra (uma multa de R$ 3.500). Gravar os dois deixaria a tela
    sem saber qual mostrar quando eles divergissem — e eles divergem no dia em
    que alguém corrige um e esquece o outro.

    **Congela com a medição**, sem campo novo: a linha pertence ao documento, e
    o documento não se edita depois de aprovado. O valor aplicado é derivado da
    base e do percentual gravados aqui (§4.9).
    """

    deducao_id = models.AutoField(primary_key=True)

    medicao = models.ForeignKey(
        Medicao, on_delete=models.CASCADE, related_name="deducoes",
        verbose_name=_("Medição"),
    )

    tipo = models.CharField(
        max_length=14, choices=TipoDeducao.choices, verbose_name=_("Tipo"),
    )
    descricao = models.CharField(
        max_length=255, blank=True, verbose_name=_("Descrição"),
    )

    #: A base sobre a qual o percentual incide. Nula significa **o bruto da
    #: medição** — o caso comum. Preenchida, é a parcela declarada (a mão de
    #: obra dentro do bruto, para o INSS), e guardá-la é o que torna a conta
    #: conferível dois anos depois, quando ninguém lembra qual era a base.
    base_calculo = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        verbose_name=_("Base de cálculo"),
    )
    percentual = models.DecimalField(
        max_digits=6, decimal_places=3, null=True, blank=True,
        verbose_name=_("Percentual (%)"),
    )
    valor = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        verbose_name=_("Valor"),
    )

    class Meta:
        verbose_name = _("Dedução da medição")
        verbose_name_plural = _("Deduções da medição")
        ordering = ["medicao_id", "deducao_id"]
        constraints = [
            # Exatamente um dos dois. A trava é do banco porque o líquido desta
            # medição vira título a pagar: uma linha com os dois campos daria
            # dois líquidos possíveis para o mesmo documento assinado.
            models.CheckConstraint(
                condition=(
                    models.Q(percentual__isnull=False, valor__isnull=True)
                    | models.Q(percentual__isnull=True, valor__isnull=False)
                ),
                name="pdca_deducao_percentual_ou_valor",
            ),
            models.CheckConstraint(
                condition=models.Q(percentual__isnull=True)
                | (models.Q(percentual__gte=0) & models.Q(percentual__lte=100)),
                name="pdca_deducao_percentual_entre_zero_e_cem",
            ),
            # Dedução negativa seria acréscimo disfarçado — e acréscimo de
            # medição é linha de item, que a grade mostra e a trava do acumulado
            # confere.
            models.CheckConstraint(
                condition=models.Q(valor__isnull=True) | models.Q(valor__gte=0),
                name="pdca_deducao_valor_nao_negativo",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "medicao"], name="pdca_deducao_medicao_idx",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} · medição {self.medicao_id}"


class LiberacaoRetencao(TenantScopedModel, Excluivel):
    """O dinheiro retido voltando ao empreiteiro.

    *(Decisão do dono, 14/09/2026: a liberação entra na PDCA.3, e não numa fatia
    posterior — reter sem poder liberar deixa o ciclo do dinheiro pela metade.)*

    **Tem escada própria, e não herda a da medição.** Quem ateste medição
    confere serviço executado; quem libera caução confere uma **condição
    contratual cumprida** (obra recebida, garantia vencida, aceitação
    definitiva). São perguntas diferentes, feitas em momentos diferentes e
    muitas vezes por pessoas diferentes — por isso a `LiberacaoRetencao` é alvo
    próprio da máquina do `nucleo`, e o tenant pode montar para ela uma escada
    que não é a da medição.

    **`condicao_atendida` não é campo decorativo.** A cláusula do contrato diz
    *quando* a retenção volta; este campo é onde quem solicita declara que
    aquilo aconteceu. Valor liberado sem a condição escrita é exatamente o
    achado que uma auditoria de contrato registra.

    **O teto é derivado** (§4.9): não há coluna de "saldo retido". O que se pode
    liberar é `retido nas medições aprovadas − já liberado`, somado na leitura
    por `services.retencao_disponivel`.
    """

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        EM_APROVACAO = "em_aprovacao", _("Em aprovação")
        APROVADA = "aprovada", _("Aprovada")
        REPROVADA = "reprovada", _("Reprovada")
        CANCELADA = "cancelada", _("Cancelada")

    liberacao_id = models.AutoField(primary_key=True)

    contrato = models.ForeignKey(
        ContratoObra, on_delete=models.PROTECT, related_name="liberacoes",
        verbose_name=_("Contrato"),
    )
    valor = models.DecimalField(
        max_digits=15, decimal_places=2, verbose_name=_("Valor a liberar"),
    )
    data = models.DateField(verbose_name=_("Data da liberação"))
    condicao_atendida = models.TextField(verbose_name=_("Condição atendida"))
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.RASCUNHO,
        verbose_name=_("Status"),
    )
    conta_pagar_ref = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("Ref. da conta a pagar (ERP)"),
    )
    solicitada_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Solicitada por"),
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    congelada_em = models.DateTimeField(null=True, blank=True)

    aprovacoes = GenericRelation(
        "nucleo.PedidoAprovacao",
        content_type_field="alvo_tipo", object_id_field="alvo_id",
    )

    class Meta:
        verbose_name = _("Liberação de retenção")
        verbose_name_plural = _("Liberações de retenção")
        ordering = ["-data", "-liberacao_id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valor__gt=0),
                name="pdca_liberacao_valor_positivo",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "contrato", "status"],
                name="pdca_liberacao_ctr_idx",
            ),
        ]

    def __str__(self):
        return f"Liberação de {self.valor} · contrato {self.contrato_id}"

    @property
    def esta_congelada(self) -> bool:
        return self.status in (
            self.Status.APROVADA, self.Status.REPROVADA, self.Status.CANCELADA,
        )
