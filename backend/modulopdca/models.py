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

Planta: docs/modulos/modulopdca.md §4.1, §4.2 e §4.3.
"""
from __future__ import annotations

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.utils.translation import gettext_lazy as _

from nucleo.tenancy import TenantScopedModel


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
