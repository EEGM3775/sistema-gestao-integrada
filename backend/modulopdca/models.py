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

**Fatia PDCA.5: o Last Planner.** O módulo passa a responder **por que não
aconteceu**. `Restricao` é o *make-ready* — atividade com restrição aberta não
entra na programação, que é a regra que separa o LPS de uma lista de tarefas;
`ProgramacaoSemanal`/`ItemProgramacao` são o **compromisso** da equipe, que é
coisa diferente do que o plano mandava; e `CausaNaoCumprimento` é o catálogo de
onde sai o ranking que alimenta o *Act*. O **PPC** é derivado dos itens, nunca
gravado (§4.9).

**Fatia PDCA.7: a verificação.** O módulo passa a perguntar se o serviço saiu
**certo**, e não só se saiu. `ModeloVerificacao`/`ItemModeloVerificacao` são a
ficha em branco da empresa; `Verificacao`/`ItemVerificacao` são a ficha aplicada,
com a pergunta **congelada** dentro da resposta; `NaoConformidade` é o defeito,
que nasce de um item reprovado ou avulsa; `PlanoAcao` é o 5W2H que a trata; e
`VerificacaoEficacia` é o que impede a NC de encerrar por carimbo — ela só fecha
quando alguém volta à frente e registra que o conserto pegou. Uma máquina, quatro
domínios (§4.5): FVS, segurança, ambiental e entrega.

Planta: docs/modulos/modulopdca.md §4.1, §4.2, §4.3, §4.4 e §4.5.
"""
from __future__ import annotations

from django.contrib.contenttypes.fields import GenericRelation
from django.core.validators import MaxValueValidator, MinValueValidator
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
    #: De qual versão do orçamento as etapas deste plano vieram, e o carimbo do
    #: cronograma dela naquele momento. Versão nova ou carimbo mais novo lá =
    #: "o cronograma do orçamento mudou" (decisão do dono: copia e avisa).
    orcamento_origem = models.ForeignKey(
        "moduloorcamento.Orcamento", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="planos_pdca", verbose_name=_("Orçamento de origem"),
    )
    cronograma_orcamento_em = models.DateTimeField(
        null=True, blank=True, editable=False,
        verbose_name=_("Carimbo do cronograma do orçamento"),
    )
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
    #: A atividade **é a etapa do orçamento** (decisão do dono, 10/10/2026: do
    #: orçamento vêm só etapas). O `peso_informado` dela é o valor da etapa no
    #: cronograma do orçamento, em reais — e por isso conta no avanço financeiro
    #: como orçado, e não como peso digitado. `atualizar_do_orcamento` o refaz.
    peso_do_orcamento = models.BooleanField(
        default=False, verbose_name=_("Peso vem do orçamento"),
    )

    responsavel = models.ForeignKey(
        "rh.Funcionario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="atividades_pdca", verbose_name=_("Responsável"),
    )

    #: Quantos dias antes do início **todo o material desta atividade** tem de
    #: estar na obra — a exceção do planejador que vence o padrão da obra e o do
    #: insumo (`AntecedenciaDeCompra`). Nulo = segue o cadastro.
    antecedencia_compra_dias = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_("Antecedência de compra (dias)"),
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


class AntecedenciaDeCompra(TenantScopedModel):
    """Quantos dias antes da atividade o material tem de **chegar** à obra.

    *(Decisão do dono, 09/10/2026: "quem define é o planejador, com padrão e
    alteração por item".)* Uma linha com `item` nulo é o **padrão da obra**; uma
    linha com `item` é a exceção daquele insumo (aço 20 d, areia 3 d). Acima das
    duas, a atividade pode sobrepor (`Atividade.antecedencia_compra_dias`).

    **Pende da obra, e não do cronograma**: replanejar gera ids novos de plano,
    e o prazo de reposição do aço não muda porque o plano mudou de versão. Sem
    cadastro nenhum, vale zero — o material chega no dia do início — e a tela
    pede o padrão em vez de inventar um.
    """

    antecedencia_id = models.AutoField(primary_key=True)
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE, related_name="antecedencias_compra",
        verbose_name=_("Obra"),
    )
    item = models.ForeignKey(
        "catalogo.Item", null=True, blank=True, on_delete=models.CASCADE,
        related_name="+", verbose_name=_("Insumo (vazio = padrão da obra)"),
    )
    dias = models.PositiveSmallIntegerField(verbose_name=_("Dias de antecedência"))
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Antecedência de compra")
        verbose_name_plural = _("Antecedências de compra")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "obra", "item"], condition=models.Q(item__isnull=False),
                name="pdca_antecedencia_unica_por_insumo",
            ),
            models.UniqueConstraint(
                fields=["tenant", "obra"], condition=models.Q(item__isnull=True),
                name="pdca_antecedencia_padrao_unico",
            ),
        ]

    def __str__(self):
        return f"{self.dias} d · obra {self.obra_id} · {'padrão' if self.item_id is None else self.item_id}"


class MaterialDaAtividade(TenantScopedModel):
    """O material que a atividade consome, **informado no plano** — sem orçamento.

    *Pergunta do dono, 10/10/2026:* "se eu um dia não tiver orçamento, quer dizer
    que não posso fazer pedido?". O cronograma puxava a compra só pelas
    composições do orçamento; obra sem orçamento (ou serviço que ficou fora dele)
    não gerava necessidade nenhuma. Aqui o planejador diz "esta atividade gasta
    120 sacos de cimento", e a necessidade de compra (`suprimentos.py`) trata a
    linha como trata a do orçamento: data pelo início, abatida pelo avanço, pelo
    estoque e pelo que já foi pedido.

    O item do catálogo é opcional (o texto basta para pedir), mas só com ele o
    estoque e os pedidos abatem a quantidade.
    """

    class Categoria(models.TextChoices):
        MATERIAL = "material", _("Material")
        EQUIPAMENTO = "equipamento", _("Equipamento")

    material_id = models.AutoField(primary_key=True)
    atividade = models.ForeignKey(
        "Atividade", on_delete=models.CASCADE, related_name="materiais",
        verbose_name=_("Atividade"),
    )
    item = models.ForeignKey(
        "catalogo.Item", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", verbose_name=_("Item do catálogo"),
    )
    descricao = models.CharField(max_length=255, verbose_name=_("Descrição"))
    unidade = models.CharField(max_length=20, verbose_name=_("Unidade"))
    categoria = models.CharField(
        max_length=12, choices=Categoria.choices, default=Categoria.MATERIAL,
        verbose_name=_("Categoria"),
    )
    #: O total da atividade inteira; o que já foi executado sai da conta.
    quantidade = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Quantidade"))
    custo_unitario = models.DecimalField(
        max_digits=15, decimal_places=4, null=True, blank=True, verbose_name=_("Custo unitário"),
    )

    class Meta:
        verbose_name = _("Material da atividade")
        verbose_name_plural = _("Materiais das atividades")
        ordering = ["atividade_id", "descricao"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantidade__gt=0), name="pdca_material_atividade_qtd_positiva",
            ),
        ]

    def __str__(self):
        return f"{self.descricao} · {self.quantidade} {self.unidade}"


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


class LadoContrato(models.TextChoices):
    """De que lado da obra o contrato está (decisão do dono, 10/10/2026).

    - **custo** — com o **empreiteiro**: a medição gera conta a pagar;
    - **receita** — com o **contratante** (cliente público ou privado que
      encomendou a obra): a medição gera conta a receber.

    É o mesmo documento — itens, aditivos, medição, retenção, reajuste —, e por
    isso é o mesmo modelo: duplicar a máquina de medição para o lado da receita
    criaria duas regras para a mesma conta, que divergiriam no primeiro ajuste.
    """

    CUSTO = "custo", _("Empreiteiro (custo)")
    RECEITA = "receita", _("Contratante (receita)")


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
    lado = models.CharField(
        max_length=8, choices=LadoContrato.choices, default=LadoContrato.CUSTO,
        verbose_name=_("Lado"),
    )
    #: Do lado do **custo**, o empreiteiro; do lado da **receita**, vazio — a
    #: parte é o `cliente`. A constraint `pdca_contrato_parte_conforme_lado`
    #: cobra que exista exatamente uma das duas.
    fornecedor = models.ForeignKey(
        "fornecedores.Fornecedor", on_delete=models.PROTECT, related_name="contratos_pdca",
        null=True, blank=True, verbose_name=_("Empreiteiro"),
    )
    cliente = models.ForeignKey(
        "clientes.Cliente", on_delete=models.PROTECT, related_name="contratos_pdca",
        null=True, blank=True, verbose_name=_("Contratante"),
    )

    #: **Medição × compra de serviço** *(decisão do dono, 09/10/2026)*: a
    #: empreitada ou locação que o Suprimentos contratou (o pedido de serviço)
    #: conversa com o que a medição paga — pedido × medido × saldo, nos dois
    #: módulos. `SET_NULL` porque o pedido é documento do Suprimentos.
    pedido_scm = models.ForeignKey(
        "moduloscm.PedidoCompra", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="contratos_pdca", verbose_name=_("Pedido de serviço (Suprimentos)"),
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

    # --- Reajuste por fórmula paramétrica (decisão do dono, 10/10/2026) ------
    #
    # Saiu do Orçamento: reajuste é cláusula de contrato. Sem parcelas
    # (`ParcelaReajusteContrato`) o contrato é a preço fixo e nada se reajusta.
    # O motor é `nucleo/reajuste.py`, sobre a série única de índices.
    reajuste_data_base = models.DateField(
        null=True, blank=True, verbose_name=_("Data-base do reajuste"),
        help_text=_("Em regra a data da proposta. O primeiro aniversário conta daqui."),
    )
    reajuste_periodicidade_meses = models.PositiveSmallIntegerField(
        default=12, verbose_name=_("Periodicidade do reajuste (meses)"),
    )
    reajuste_parcela_fixa = models.DecimalField(
        max_digits=7, decimal_places=6, default=0,
        verbose_name=_("Parcela não reajustável (a)"),
    )
    reajuste_casas = models.PositiveSmallIntegerField(
        default=4, verbose_name=_("Casas do fator (truncado)"),
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
                    models.Q(lado=LadoContrato.CUSTO, fornecedor__isnull=False, cliente__isnull=True)
                    | models.Q(lado=LadoContrato.RECEITA, cliente__isnull=False, fornecedor__isnull=True)
                ),
                name="pdca_contrato_parte_conforme_lado",
            ),
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

    @property
    def parte(self):
        """Com quem é o contrato: o empreiteiro ou o contratante."""
        return self.cliente if self.lado == LadoContrato.RECEITA else self.fornecedor

    @property
    def parte_nome(self) -> str:
        parte = self.parte
        if parte is None:
            return ""
        return (getattr(parte, "razao_social", "") or getattr(parte, "nome", "")
                or getattr(parte, "nome_completo", "") or str(parte))


class ParcelaReajusteContrato(TenantScopedModel):
    """Uma parcela `pᵢ × Iᵢ` da fórmula de reajuste do contrato.

    O índice é o da série **única** (`nucleo.IndiceEconomico`) — o mesmo INCC
    que corrige o saldo do comprador corrige a medição do empreiteiro.
    """

    parcela_id = models.AutoField(primary_key=True)
    contrato = models.ForeignKey(
        ContratoObra, on_delete=models.CASCADE, related_name="parcelas_reajuste",
        verbose_name=_("Contrato"),
    )
    indice = models.ForeignKey(
        "nucleo.IndiceEconomico", on_delete=models.PROTECT, related_name="+",
        verbose_name=_("Índice"),
    )
    peso = models.DecimalField(max_digits=7, decimal_places=6, verbose_name=_("Peso (p)"))
    rotulo = models.CharField(max_length=80, blank=True, verbose_name=_("Rótulo"),
                              help_text=_("Mão de obra, materiais, equipamentos…"))

    class Meta:
        verbose_name = _("Parcela de reajuste")
        verbose_name_plural = _("Parcelas de reajuste")
        ordering = ["contrato", "parcela_id"]
        constraints = [
            models.UniqueConstraint(fields=["contrato", "indice"], name="pdca_reajuste_indice_unico"),
            models.CheckConstraint(condition=models.Q(peso__gt=0) & models.Q(peso__lte=1),
                                   name="pdca_reajuste_peso_entre_zero_e_um"),
        ]

    def __str__(self):
        return f"{self.rotulo or self.indice_id}: {self.peso}"


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
    #: **Retenção própria do item** *(decisão do dono, 11/10/2026)* — o aditivo
    #: pode trazer item com regra de caução diferente da do contrato. Nula =
    #: vale a do contrato. A medição copia o número para a linha no dia em que
    #: nasce (`ItemMedicao.retencao_percentual`), pelo mesmo motivo do
    #: percentual geral: mudar a regra depois não reescreve medição paga.
    retencao_percentual = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Retenção própria (%)"),
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
    #: **Nova retenção do contrato** *(decisão do dono, 11/10/2026)*. Aprovado o
    #: aditivo, ela passa a ser a cláusula — e vale para as medições que nascem
    #: depois. Nula = o aditivo não mexe na retenção.
    retencao_percentual_nova = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Nova retenção do contrato (%)"),
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
    #: A retenção própria que esta linha dá ao item (`ItemContrato.retencao_percentual`),
    #: escrita quando o aditivo é aprovado. Nula = não mexe.
    retencao_percentual = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Retenção própria do item (%)"),
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
        #: A aprovada que uma retificadora **substituiu** *(decisão do dono,
        #: 11/10/2026)*. Fica legível, fora de toda soma; a que vale é a
        #: retificadora, que guarda a medição corrigida inteira.
        RETIFICADA = "retificada", _("Retificada")

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
    #: Do lado da receita, o título é a receber (`moduloerp.ContaReceber`).
    conta_receber_ref = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("Ref. da conta a receber (ERP)"),
    )
    #: O acréscimo do reajuste sobre o bruto do período — **guardado**, ao
    #: contrário do bruto, porque depende do índice publicado no dia: a medição
    #: aprovada não pode mudar de valor quando o IBGE revisa a série.
    valor_reajuste = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, verbose_name=_("Reajuste do período"),
    )
    reajuste_memoria = models.JSONField(default=dict, blank=True, verbose_name=_("Memória do reajuste"))
    reajuste_provisorio = models.BooleanField(
        default=False, verbose_name=_("Reajuste com índice provisório"),
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
            self.Status.RETIFICADA,
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
    #: A retenção própria do item **no dia em que a linha nasceu** — nula = a
    #: da medição (`Medicao.retencao_percentual_aplicado`).
    retencao_percentual = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name=_("Retenção própria (%)"),
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
            # A quantidade negativa é recusada no serviço (`reescrever_linhas`):
            # desde 11/10/2026 a retificadora guarda a medição corrigida
            # inteira, e medir para menos é escrever o número certo.
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
    #: Do lado da receita, a caução que o contratante devolve vira conta a receber.
    conta_receber_ref = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("Ref. da conta a receber (ERP)"),
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


# ---------------------------------------------------------------------------
# PDCA.5 — o Last Planner: restrição, compromisso da semana e causa
# ---------------------------------------------------------------------------
# É a fatia que fecha o **Check** e o **Act** do módulo que se chama PDCA. Até
# aqui ele planejava (`Cronograma`), executava (`ApontamentoAvanco`) e pagava
# (`Medicao`) — e as três respondiam *o que era para acontecer* e *o que
# aconteceu*. Nenhuma respondia **por que não aconteceu**, que é a pergunta de
# onde sai a melhoria.
#
# O Last Planner faz isso com três gestos que não existem no cronograma:
#
#   1. **make-ready** — antes de comprometer, remover o que impede (`Restricao`);
#   2. **compromisso** — a equipe diz o que VAI fazer na semana, e isso é
#      diferente do que o plano DIZ que ela faria (`ProgramacaoSemanal`);
#   3. **aprendizado** — o que não saiu exige causa, e o ranking das causas é o
#      que muda o sistema (`CausaNaoCumprimento`).
#
# O **PPC** é a razão entre o comprometido e o cumprido, e ele é derivado —
# nunca gravado (§4.9): guardá-lo em coluna criaria a segunda verdade que a §4.9
# proíbe, e ela envelheceria no instante em que um item mudasse de cumprido para
# não-cumprido.


class TipoRestricao(models.TextChoices):
    """As oito famílias de impedimento do *make-ready*.

    Lista fechada, e não texto livre, pelo mesmo motivo do `NivelLocal`: o
    ranking de restrição por tipo é uma das duas leituras que fazem o make-ready
    valer a pena (a outra é o vencimento). Com texto livre, "material" e
    "materiais" viram duas famílias e o ranking deixa de somar.

    As oito saem da prática do LPS e cobrem o que trava obra: **projeto** (falta
    detalhe, RFI sem resposta), **material**, **mão de obra**, **equipamento**,
    **área** (a frente anterior não liberou o local), **licença** (alvará,
    liberação de órgão), **decisão** (o cliente não escolheu) e **clima**.
    """

    PROJETO = "projeto", _("Projeto")
    MATERIAL = "material", _("Material")
    MAO_DE_OBRA = "mao_de_obra", _("Mão de obra")
    EQUIPAMENTO = "equipamento", _("Equipamento")
    AREA = "area", _("Área / frente anterior")
    LICENCA = "licenca", _("Licença / liberação")
    DECISAO = "decisao", _("Decisão do cliente")
    CLIMA = "clima", _("Clima")


class Restricao(TenantScopedModel, Excluivel):
    """O *make-ready* do Last Planner — **o que impede a atividade de começar**.

    **É a regra que separa o LPS de uma lista de tarefas** (planta §4.3):
    atividade com restrição aberta **não entra na programação**. Sem essa trava,
    o quadro da semana vira uma lista de desejos — o time se compromete com o que
    sabe estar travado, o PPC despenca, e a causa registrada toda semana é a
    mesma restrição que ninguém removeu.

    **Ela pende de uma atividade, e não de uma obra solta.** Restrição sem alvo
    não bloqueia nada e não se fecha: é um recado. O que dá poder a este modelo é
    poder responder *quais compromissos esta pendência está segurando* — e isso
    exige a FK.

    **`responsavel` é rótulo durável, não FK de usuário** — o padrão do módulo.
    Quem responde por destravar é com frequência alguém de fora do sistema (o
    projetista, o fornecedor, o fiscal da prefeitura), e uma FK obrigaria a
    cadastrar a prefeitura como usuário para poder escrever "aguardando alvará".

    **Removida não é apagada.** A restrição removida é a prova de que o
    make-ready aconteceu, e o tempo entre `criada_em` e `removida_em` é a única
    medida honesta de quanto a obra demora para destravar a si mesma. Apagar
    apagaria a metade boa da história.
    """

    class Status(models.TextChoices):
        ABERTA = "aberta", _("Aberta")
        REMOVIDA = "removida", _("Removida")
        #: Descartada sem ter sido resolvida — "não era restrição", "o serviço
        #: saiu do escopo". Separada de `REMOVIDA` de propósito: contar as duas
        #: juntas inflaria a leitura de quanto a obra destrava de fato.
        CANCELADA = "cancelada", _("Cancelada")

    restricao_id = models.AutoField(primary_key=True)

    #: `CASCADE`, e não o `PROTECT` que a PDCA.3 dá à medição: a restrição não é
    #: prova de dinheiro, é insumo de planejamento. Atividade que deixa de
    #: existir num replanejamento leva junto as travas que só faziam sentido para
    #: ela — mantê-las produziria pendência órfã, que é o entulho que o teto da
    #: §5.5j existe para evitar.
    atividade = models.ForeignKey(
        Atividade, on_delete=models.CASCADE, related_name="restricoes",
        verbose_name=_("Atividade"),
    )

    #: Opcional, e é o endereço fino: a mesma atividade pode estar liberada na
    #: torre A e travada na torre B. Sem ele, destravar a torre A obrigaria a
    #: fechar uma restrição que ainda vale para a B.
    local = models.ForeignKey(
        LocalObra, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="restricoes", verbose_name=_("Local"),
    )

    tipo = models.CharField(
        max_length=12, choices=TipoRestricao.choices, verbose_name=_("Tipo"),
    )
    descricao = models.TextField(verbose_name=_("Descrição"))

    responsavel = models.CharField(
        max_length=150, blank=True, verbose_name=_("Responsável por remover"),
    )
    #: Quando a restrição **precisa** estar removida para não atrasar o serviço.
    #: Nula é permitido e honesto: existe restrição cujo prazo ninguém sabe ainda
    #: ("aguardando resposta do projetista"). O que a tela faz com nula é
    #: mostrá-la como *sem prazo* — nunca como vencida.
    prazo = models.DateField(null=True, blank=True, verbose_name=_("Prazo"))

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ABERTA,
        verbose_name=_("Status"),
    )

    #: O seam do SCM, e ele é **vivo**, não inerte: restrição de material é a
    #: origem natural de uma demanda de compra (planta §6 e §7 — "não compra nem
    #: cota; restrição vira demanda"). `SET_NULL` porque a demanda é documento do
    #: outro módulo e pode ser cancelada lá sem levar a restrição junto.
    demanda_scm = models.ForeignKey(
        "moduloscm.Demanda", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="restricoes_pdca", verbose_name=_("Demanda no SCM"),
    )

    criada_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Criada por"),
    )
    criada_em = models.DateTimeField(auto_now_add=True)
    removida_em = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Removida em"),
    )
    removida_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Removida por"),
    )
    #: Como foi destravada. É o campo que a reunião lê na semana seguinte, e o
    #: que transforma o log de restrição em memória da obra.
    nota_remocao = models.TextField(
        blank=True, verbose_name=_("Como foi removida"),
    )

    #: --- A volta atrás: a trava que voltou ---------------------------------
    #:
    #: O material "chegou" e era o errado; o clique em *Resolvida* foi na linha
    #: de baixo. A restrição removida volta a ser aberta — **registrada, não
    #: apagada**, a mesma régua da semana reaberta: quem lê o log vê que ela
    #: voltou e quantas vezes. A nota da última remoção fica (é a história),
    #: e o tempo de destravar passa a contar de novo a partir da reabertura.
    reaberta_em = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Reaberta em"),
    )
    reaberta_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Reaberta por"),
    )
    vezes_reaberta = models.PositiveSmallIntegerField(
        default=0, verbose_name=_("Vezes reaberta"),
    )

    class Meta:
        verbose_name = _("Restrição")
        verbose_name_plural = _("Restrições")
        ordering = ["prazo", "-restricao_id"]
        indexes = [
            #: O gesto que a tela faz o tempo todo: *o que ainda trava esta
            #: atividade?* — conferido antes de cada compromisso.
            models.Index(
                fields=["tenant", "atividade", "status"],
                name="pdca_restricao_ativ_idx",
            ),
            #: E o do painel: a fila de make-ready da obra, ordenada por prazo.
            models.Index(
                fields=["tenant", "status", "prazo"],
                name="pdca_restricao_fila_idx",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} · atividade {self.atividade_id}"

    @property
    def esta_aberta(self) -> bool:
        return self.status == self.Status.ABERTA


class CausaNaoCumprimento(TenantScopedModel):
    """Por que o compromisso não saiu — **de um catálogo, nunca de texto livre**.

    É o modelo mais simples desta fatia e o que decide se ela serve para alguma
    coisa. O PPC diz *quanto* falhou; só a causa diz *o quê* mudar. E ela só
    responde isso se for **a mesma lista toda semana**: com campo livre, "chuva",
    "choveu" e "clima" viram três linhas no ranking, cada uma com um terço do
    peso, e a causa que estava em primeiro lugar não aparece.

    **De fábrica e extensível.** As causas de fábrica (`de_fabrica=True`) nascem
    com o tenant e cobrem o que a literatura do LPS registra como recorrente; o
    tenant acrescenta as dele. O que ele **não** pode é apagar uma de fábrica que
    já foi usada — o histórico de PPC de dois anos atrás perderia o rótulo. Por
    isso `ativo`: causa que não se usa mais sai da lista de escolha e continua
    legível no passado.

    **Não herda `Excluivel` de propósito.** A lixeira existe para o objeto de
    valor que alguém apaga por engano; um item de catálogo desativado já é
    reversível por um clique, e mandá-lo para a lixeira criaria dois mecanismos
    de desfazer para o mesmo gesto.
    """

    class Categoria(models.TextChoices):
        """A quem a causa aponta — e é isto que transforma o ranking em ação.

        Saber que "falta de material" lidera é meia informação; saber que 60% das
        falhas apontam para **fora da equipe** (projeto, fornecedor, cliente) e
        40% para dentro é o que decide se a conversa da semana é com o time ou
        com a contratante.
        """

        PLANEJAMENTO = "planejamento", _("Planejamento")
        MAO_DE_OBRA = "mao_de_obra", _("Mão de obra")
        MATERIAL = "material", _("Material")
        EQUIPAMENTO = "equipamento", _("Equipamento")
        PROJETO = "projeto", _("Projeto")
        EXTERNO = "externo", _("Externo (clima, cliente, órgão)")
        QUALIDADE = "qualidade", _("Retrabalho / qualidade")

    causa_id = models.AutoField(primary_key=True)

    #: Curto e estável — é o que aparece no cartão e no eixo do gráfico, onde
    #: não cabe a frase inteira.
    codigo = models.CharField(max_length=30, verbose_name=_("Código"))
    nome = models.CharField(max_length=120, verbose_name=_("Nome"))
    categoria = models.CharField(
        max_length=14, choices=Categoria.choices, verbose_name=_("Categoria"),
    )
    #: Marca a linha que veio com o tenant. Serve para uma coisa só, e ela
    #: importa: impedir que o catálogo de fábrica seja renomeado a ponto de a
    #: comparação entre obras deixar de existir.
    de_fabrica = models.BooleanField(
        default=False, verbose_name=_("De fábrica"),
    )
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))

    class Meta:
        verbose_name = _("Causa de não-cumprimento")
        verbose_name_plural = _("Causas de não-cumprimento")
        ordering = ["categoria", "codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "codigo"],
                name="pdca_causa_codigo_unico_por_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.codigo} · {self.nome}"


class ProgramacaoSemanal(TenantScopedModel, Excluivel):
    """**O que a equipe se comprometeu a fazer nesta semana** — não o que o plano
    mandava.

    A distinção é a razão de este modelo existir ao lado do `Cronograma`. O
    cronograma diz o que *deveria* acontecer, calculado pelo CPM meses antes; a
    programação é o que o time, olhando a obra de hoje, **assume** perante os
    colegas. Guardar o compromisso na própria atividade destruiria a comparação:
    o plano seria reescrito toda semana para bater com a realidade e o PPC daria
    100% para sempre.

    **Três estados, e a transição normal é de mão única.** `RASCUNHO` é a parede
    sendo montada; `COMPROMETIDA` é o time tendo assumido (e a partir daí a
    lista de compromissos não recebe item novo — acrescentar depois de assumir é
    como escrever a aposta depois do resultado); `ENCERRADA` é o ciclo fechado,
    cada item julgado e o PPC calculável.

    **Mas existe volta, e ela é registrada.** `reabrir/` desce **um** degrau, com
    motivo obrigatório, e carimba quem, quando e por quê (ver os campos de
    reabertura abaixo). Sem ela a semana encerrada era um beco: julgamento errado
    ficava para sempre, e o ranking de causas — que é o que decide o que a
    empresa muda — passava a apontar para o problema errado.

    **O PPC não mora aqui.** Ele é derivado dos itens (§4.9), e a razão é a
    mesma que impediu o `percentual_conclusao` acumulado de virar coluna na
    PDCA.2: guardá-lo obrigaria a reescrevê-lo a cada item julgado, e a primeira
    vez que alguém gravasse fora desse caminho o número passaria a mentir.
    """

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        COMPROMETIDA = "comprometida", _("Comprometida")
        ENCERRADA = "encerrada", _("Encerrada")

    programacao_id = models.AutoField(primary_key=True)

    #: A obra, e não o cronograma. Uma programação atravessa o replanejamento:
    #: a semana que o time assumiu continua tendo acontecido depois de a v2 do
    #: cronograma ser publicada, e amarrá-la à versão faria o histórico de PPC
    #: zerar a cada replanejamento — exatamente o que a PDCA.2 evitou no avanço.
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE, related_name="programacoes_pdca",
        verbose_name=_("Obra"),
    )

    #: Segunda-feira da semana. É a chave natural do documento, e o `UniqueConstraint`
    #: abaixo a torna única por obra: duas programações da mesma semana seriam
    #: dois compromissos concorrentes sobre o mesmo período, e o PPC não saberia
    #: qual contar.
    semana_inicio = models.DateField(verbose_name=_("Início da semana"))
    semana_fim = models.DateField(verbose_name=_("Fim da semana"))

    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.RASCUNHO,
        verbose_name=_("Status"),
    )

    #: O que a reunião decidiu e não cabe em nenhum item — o clima da semana, a
    #: decisão que vale para todos os compromissos.
    nota = models.TextField(blank=True, verbose_name=_("Nota da reunião"))

    criada_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Criada por"),
    )
    criada_em = models.DateTimeField(auto_now_add=True)
    comprometida_em = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Comprometida em"),
    )
    comprometida_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Comprometida por"),
    )
    encerrada_em = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Encerrada em"),
    )
    encerrada_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Encerrada por"),
    )

    #: --- A volta atrás, e por que ela é REGISTRADA e não impedida ------------
    #:
    #: A semana encerrada era um beco: `julgar/` só aceita programação
    #: comprometida, então um julgamento errado — "saiu" no que não saiu, a causa
    #: trocada — ficava para sempre. E o estrago não é do índice: é do
    #: **ranking**, que é o que decide o que a empresa muda na semana seguinte.
    #: Uma causa errada contada durante um ano manda a obra consertar o problema
    #: que ela não tem.
    #:
    #: **Por que reabrir em vez de retificar.** A medição da PDCA.3 congela e se
    #: corrige por um documento novo, porque ela virou dinheiro: existe um título
    #: no ERP que não pode ser reescrito. Aqui não há documento nenhum a
    #: reconciliar — o PPC é **derivado, nunca gravado** (§4.9), então reabrir e
    #: rejulgar simplesmente recalcula. A régua aplicável é a do
    #: `ApontamentoAvanco` da PDCA.2: o erro se corrige **com motivo declarado**,
    #: não se apaga.
    #:
    #: **E por que sem prazo.** A tentação seria só deixar reabrir a semana
    #: recente. Mas erro achado tarde é o mais caro de não poder consertar — e a
    #: retificadora da medição, que mexe em dinheiro, também não tem prazo. O que
    #: protege o histórico não é a porta trancada, é **a correção aparecer**:
    #: quem lê a série vê quais semanas foram reabertas, e a reunião que discutiu
    #: o número antigo não é contrariada em silêncio.
    reaberta_em = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Reaberta em"),
    )
    reaberta_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Reaberta por"),
    )
    #: Obrigatório ao reabrir. É a frase que a reunião seguinte lê para saber
    #: por que o número mudou depois de ela ter olhado para ele.
    motivo_reabertura = models.TextField(
        blank=True, verbose_name=_("Motivo da reabertura"),
    )
    #: Contador, e não booleano: uma semana reaberta cinco vezes não é a mesma
    #: coisa que uma reaberta uma vez, e é o tipo de padrão que só aparece se
    #: alguém contar.
    vezes_reaberta = models.PositiveSmallIntegerField(
        default=0, verbose_name=_("Vezes reaberta"),
    )

    #: --- O encerramento ANTES de a semana acabar -----------------------------
    #:
    #: **Dava para fechar a semana que ainda não aconteceu.** `encerrar/` só
    #: olhava o status e os julgamentos pendentes, nunca o calendário: na
    #: segunda-feira de manhã a equipe podia julgar os cinco compromissos como
    #: "não saiu" e encerrar — e a semana inteira estava pela frente. O PPC que
    #: sai daí não mede confiabilidade de plano nenhum; mede quem apertou o botão
    #: cedo, e ele entra na série histórica indistinguível dos outros.
    #:
    #: **Não é proibido, é excepcional e carimbado** *(decisão do dono,
    #: 15/09/2026)*. Existe o caso real — a obra que para na sexta de um feriado
    #: prolongado e faz a retrospectiva na quinta —, e trancar de todo faria o
    #: time julgar de memória na semana seguinte, que é pior. Então a porta pede
    #: **permissão própria** (`pdca.programacao.encerrar_antecipado`) e **motivo
    #: por escrito**, e a semana fica marcada: quem lê a série vê que aquele
    #: ponto foi apurado antes do fim, do mesmo jeito que vê a semana reaberta.
    encerrada_antes_do_fim = models.BooleanField(
        default=False, verbose_name=_("Encerrada antes do fim da semana"),
    )
    motivo_encerramento_antecipado = models.TextField(
        blank=True, verbose_name=_("Motivo do encerramento antecipado"),
    )

    class Meta:
        verbose_name = _("Programação semanal")
        verbose_name_plural = _("Programações semanais")
        ordering = ["-semana_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["obra", "semana_inicio"],
                condition=models.Q(excluido_em__isnull=True),
                name="pdca_programacao_semana_unica_por_obra",
            ),
            models.CheckConstraint(
                condition=models.Q(semana_fim__gte=models.F("semana_inicio")),
                name="pdca_programacao_semana_coerente",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "obra", "semana_inicio"],
                name="pdca_prog_obra_semana_idx",
            ),
        ]

    def __str__(self):
        return f"Semana de {self.semana_inicio} · obra {self.obra_id}"

    @property
    def esta_aberta_para_montagem(self) -> bool:
        """Só o rascunho recebe item novo. Ver a docstring da classe."""
        return self.status == self.Status.RASCUNHO


class EquipeObra(TenantScopedModel):
    """A equipe que assume compromissos no quadro da semana — **uma composição**.

    *Decisão do dono, 09/10/2026:* "a equipe na semana deveria ser uma
    composição (fornecedores e funcionários), não uma escrita". Até aqui a
    coluna do quadro era o texto que alguém digitou: "Equipe do Zé" não dizia
    quem é o Zé, nem que empreiteira estava junto — e o mesmo time virava duas
    colunas na semana em que alguém escreveu "Eq. Zé".

    É da **obra**, não da semana: a composição atravessa as semanas, e o quadro
    novo já nasce com as colunas de quem trabalha ali. Funcionário é do RH;
    fornecedor é a empreiteira (o mesmo cadastro do contrato de medição).

    O **nome** continua existindo e é o rótulo que viaja no cartão
    (`ItemProgramacao.responsavel`): é ele que o encarregado procura no celular.
    Vazio, nasce dos membros ("Zé Silva + Construtora X").
    """

    equipe_id = models.AutoField(primary_key=True)
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE, related_name="equipes_pdca",
        verbose_name=_("Obra"),
    )
    #: `default=""` não é enfeite: `nome` está numa `UniqueConstraint`, e o DRF
    #: torna obrigatório todo campo de constraint sem default — e o nome vazio
    #: é o que pede ao serializer para compô-lo dos membros.
    nome = models.CharField(max_length=150, default="", verbose_name=_("Nome"))
    funcionarios = models.ManyToManyField(
        "rh.Funcionario", blank=True, related_name="equipes_pdca",
        verbose_name=_("Funcionários"),
    )
    fornecedores = models.ManyToManyField(
        "fornecedores.Fornecedor", blank=True, related_name="equipes_pdca",
        verbose_name=_("Fornecedores"),
    )
    ativa = models.BooleanField(default=True, verbose_name=_("Ativa"))
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Equipe da obra")
        verbose_name_plural = _("Equipes da obra")
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "obra", "nome"], name="pdca_equipe_nome_unico_por_obra",
            ),
        ]

    def __str__(self):
        return self.nome


class ItemProgramacao(TenantScopedModel):
    """Um **compromisso** da semana — uma atividade, num local, com um dono.

    **`cumprido` é tri-estado de propósito, e o `None` é o estado mais
    importante dos três.** Enquanto a semana não encerra, o item **não tem**
    julgamento — e um `BooleanField` com `default=False` diria que ele já
    falhou, jogando o PPC da semana em curso para zero e tornando o número
    inútil justamente enquanto ele poderia mudar alguma coisa. Nulo é "ainda não
    julgado", e é o que mantém o PPC honesto: ele só existe depois do encerramento.

    **Não cumprido exige causa**, e a trava é da aplicação (`services`) e do
    banco (a `CheckConstraint` abaixo). Sem ela o Last Planner degenera em
    marcar caixinhas: o time aprende a anotar "não saiu" e segue a semana, que é
    exatamente a prática que o LPS foi inventado para substituir.

    **Cumprido não pode ter causa.** É o outro lado da mesma regra, e sem ele a
    grade de causas contaria falhas que não houve.

    Não herda `Excluivel`: é linha filha de documento, na mesma régua do
    `ItemMedicao` e do `ItemAditivo` — a lixeira guarda o objeto de valor, não a
    linha dele.
    """

    item_programacao_id = models.AutoField(primary_key=True)

    programacao = models.ForeignKey(
        ProgramacaoSemanal, on_delete=models.CASCADE, related_name="itens",
        verbose_name=_("Programação"),
    )
    #: `PROTECT`: o compromisso é prova de que alguém assumiu aquele serviço
    #: naquela semana. Apagar a atividade e levá-lo junto apagaria o numerador e
    #: o denominador de um PPC já publicado.
    atividade = models.ForeignKey(
        Atividade, on_delete=models.PROTECT, related_name="itens_programacao",
        verbose_name=_("Atividade"),
    )
    local = models.ForeignKey(
        LocalObra, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="itens_programacao", verbose_name=_("Local"),
    )

    #: Quem assume — rótulo durável, como o `responsavel` da restrição e pelo
    #: mesmo motivo: o encarregado da empreiteira que assume a frente nem sempre
    #: tem login.
    responsavel = models.CharField(
        max_length=150, blank=True, verbose_name=_("Responsável"),
    )
    #: A composição que assume (funcionários e fornecedores). Com ela, o
    #: `responsavel` é o nome dela — o serializer mantém os dois juntos.
    #: `SET_NULL`: desfazer a equipe não apaga a aposta que ela fez.
    equipe = models.ForeignKey(
        EquipeObra, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="compromissos", verbose_name=_("Equipe"),
    )

    #: **Quanto** o time se compromete a avançar nesta semana, em pontos
    #: percentuais da atividade. É delta, não acumulado — a mesma régua do
    #: `ApontamentoAvanco` (planta §4.3), e pela mesma razão: "andou 15% esta
    #: semana" é o que alguém responde olhando o serviço.
    #:
    #: Nulo é permitido e comum: muito compromisso de LPS é binário ("concretar
    #: a laje do 4º"), e obrigar um número faria o time inventar um.
    percentual_previsto = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        verbose_name=_("Avanço previsto na semana (%)"),
    )

    #: A requisição de material que o compromisso pediu ao almoxarifado
    #: (`suprimentos.pedir_material_da_semana`) — uma por cartão. `SET_NULL`
    #: porque a requisição é documento do Estoque e pode ser apagada lá.
    requisicao_sil = models.ForeignKey(
        "modulosil.Requisicao", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="compromissos_pdca", verbose_name=_("Requisição de material"),
    )

    #: --- O peso do compromisso, e de onde ele veio ---------------------------
    #:
    #: **O PPC passa a ser ponderado** *(decisão do dono, 15/09/2026)*. Contar
    #: cartões iguais dizia que assumir a concretagem da laje e assumir a
    #: limpeza do canteiro valem o mesmo: a semana que entrega a laje e perde a
    #: limpeza marcava os mesmos 50% da que entrega a limpeza e perde a laje, e
    #: as duas semanas não são a mesma semana para ninguém que esteja na obra.
    #:
    #: **O número sai do planejamento, não de um campo novo para digitar.** É a
    #: mesma escada do `services.peso_de` que o avanço do cronograma já usa, com
    #: um degrau a mais no fim:
    #:
    #:   1. `orcado` — a atividade está vinculada ao `ItemOrcado`, e vale o que o
    #:      item vale. É o físico-financeiro do Orçamento entrando no Last
    #:      Planner sem ninguém redigitar nada;
    #:   2. `informado` — o peso que o planejador pôs na atividade;
    #:   3. `duracao` — os dias úteis da atividade. É o "por tempo": quem montou
    #:      o cronograma já disse quanto cada serviço dura, e essa é a régua de
    #:      esforço que toda obra tem mesmo sem orçamento vinculado.
    #:
    #: **Congelado quando o cartão entra no quadro**, como o
    #: `retencao_percentual_aplicado` da medição e pelo mesmo motivo: reprecificar
    #: o orçamento em dezembro não pode reescrever o PPC de uma semana que a
    #: reunião de agosto já leu.
    #:
    #: Nulo é resposta honesta e não zero: a atividade não tem como ponderar
    #: (sem vínculo, sem peso, sem duração — o marco, por exemplo). O item entra
    #: em `sem_peso` na leitura, e a tela mostra o denominador ao lado do índice
    #: — a mesma régua do `folhas_sem_peso` do avanço do cronograma.
    peso = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True,
        verbose_name=_("Peso do compromisso"),
    )
    #: Qual degrau da escada valeu. Viaja junto porque duas fontes silenciosas
    #: para o mesmo número é como se perde a confiança nas duas — a mesma razão
    #: do `peso_origem` do avanço (planta §11.2).
    peso_origem = models.CharField(
        max_length=12, blank=True, verbose_name=_("Origem do peso"),
    )

    #: --- O compromisso que não saiu e continua de pé -------------------------
    #:
    #: **Serviço que não saiu não deixa de ser preciso** *(decisão do dono,
    #: 15/09/2026)*. Até aqui a semana encerrada era um fim de linha: o cartão
    #: "não saiu" ficava no quadro de trás, e a semana seguinte nascia vazia —
    #: quem quisesse continuar a armação de pilares tinha de achá-la de novo na
    #: WBS e puxá-la à mão. O que se perdia não era o clique: era **o fato de
    #: aquele compromisso estar na segunda semana seguida**, que é exatamente o
    #: que o Last Planner existe para pôr na frente da reunião.
    #:
    #: `arrastado_de` aponta para o cartão da semana anterior, e `vezes_arrastado`
    #: conta. Um serviço arrastado quatro semanas não é o mesmo problema que um
    #: arrastado uma vez — é uma restrição que ninguém removeu, e o contador é o
    #: que faz esse padrão aparecer sem alguém ter de cruzar quadros à mão.
    arrastado_de = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="arrastos", verbose_name=_("Arrastado do compromisso"),
    )
    vezes_arrastado = models.PositiveSmallIntegerField(
        default=0, verbose_name=_("Semanas arrastado"),
    )

    #: **Quanto da atividade está concluído no fim da semana** — acumulado, em
    #: %, dito no julgamento. *Decisão do dono, 09/10/2026:* "em julgar semana
    #: era para colocar a porcentagem concluída, não se saiu ou não". O número
    #: faz duas coisas (`services.julgar_itens`): vira **apontamento de avanço**
    #: (a diferença para o que o campo já apontou — o físico da obra anda com o
    #: julgamento) e decide o `cumprido` do PPC, comparado à meta da semana. O
    #: PPC continua binário, que é a definição dele; só deixou de ser digitado.
    percentual_concluido = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        verbose_name=_("Concluído no fim da semana (%)"),
    )

    #: `None` até o encerramento — ver a docstring da classe.
    cumprido = models.BooleanField(
        null=True, blank=True, verbose_name=_("Cumprido"),
    )
    #: `PROTECT`: a causa é o rótulo de uma falha já contada num PPC publicado.
    causa = models.ForeignKey(
        CausaNaoCumprimento, on_delete=models.PROTECT, null=True, blank=True,
        related_name="itens", verbose_name=_("Causa do não-cumprimento"),
    )
    #: O detalhe da causa — *qual* material faltou, *que* projeto não chegou. A
    #: causa dá a família; esta linha dá o caso, e é dela que sai a ação.
    nota = models.TextField(blank=True, verbose_name=_("Nota"))

    ordem = models.PositiveIntegerField(default=0, verbose_name=_("Ordem"))

    class Meta:
        verbose_name = _("Item de programação")
        verbose_name_plural = _("Itens de programação")
        ordering = ["ordem", "item_programacao_id"]
        constraints = [
            #: A mesma atividade, no mesmo local, não se compromete duas vezes na
            #: mesma semana: seriam dois cartões disputando o mesmo serviço, e o
            #: PPC contaria a falha em dobro.
            models.UniqueConstraint(
                fields=["programacao", "atividade", "local"],
                name="pdca_item_prog_unico_por_atividade_local",
            ),
            #: A de cima **não cobre `local IS NULL`** — e esse é o caso comum
            #: aqui, não a exceção: muito compromisso de LPS é da frente inteira
            #: ("concretar a laje do 4º"), sem endereço fino. No Postgres
            #: NULL ≠ NULL, então dois cartões da mesma atividade sem local
            #: passavam, e o PPC contava a mesma falha duas vezes — exatamente o
            #: que a constraint acima existe para impedir. Achado pelo
            #: `pdca5_programacao_test.py`.
            #:
            #: Constraint parcial, e não `nulls_distinct=False`, pelo mesmo
            #: motivo já registrado na parcela do Orçamento: não depender de
            #: PG 15+.
            models.UniqueConstraint(
                fields=["programacao", "atividade"],
                condition=models.Q(local__isnull=True),
                name="pdca_item_prog_unico_sem_local",
            ),
            #: **Não cumprido exige causa; cumprido não a admite.** A regra vive
            #: também no `services`, para a mensagem ser legível — mas ela mora
            #: aqui porque o comando de bancada e a importação entram por outras
            #: portas (a mesma lição do append-only da PDCA.2).
            models.CheckConstraint(
                condition=(
                    models.Q(cumprido__isnull=True, causa__isnull=True)
                    | models.Q(cumprido=True, causa__isnull=True)
                    | models.Q(cumprido=False, causa__isnull=False)
                ),
                name="pdca_item_prog_causa_coerente",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "programacao", "cumprido"],
                name="pdca_item_prog_ppc_idx",
            ),
        ]

    def __str__(self):
        return f"Compromisso · atividade {self.atividade_id}"

    def save(self, *args, **kwargs):
        """Congela o peso **quando o cartão nasce**, e só então.

        Aqui, e não no serializer, pela mesma lição que pôs a `CheckConstraint`
        da causa no banco: o comando de bancada, a importação e o arrasto da
        semana seguinte entram por outras portas, e um peso que só o formulário
        preenchesse deixaria o PPC de metade dos quadros sem denominador.

        **Uma consulta, uma vez por cartão.** Não recalcula na atualização: o
        julgamento do fim da semana chama `save`/`bulk_update` sobre um cartão
        que já tem peso, e recalcular ali faria o orçamento reprecificado em
        dezembro reescrever o PPC de agosto.
        """
        if self._state.adding and self.peso is None and not self.peso_origem:
            from . import services

            atividade = self.atividade
            if atividade is not None:
                valor, origem = services.peso_do_compromisso(atividade)
                self.peso = valor
                self.peso_origem = origem
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# PDCA.7 — a máquina de verificação: FVS, não-conformidade e plano de ação
# ---------------------------------------------------------------------------
# **Uma máquina, quatro domínios** (planta §4.5 e §11.6). FVS, checklist de
# segurança, vistoria de entrega e inspeção ambiental são a mesma coisa: um
# modelo de verificação aplicado a um objeto, item a item, com resultado e
# evidência. Três cópias divergiriam na primeira mudança de requisito — e a
# quarta, a vistoria de entrega da PDCA.11, nasceria fora do laço de tratamento
# que as outras três já teriam.
#
# O que esta fatia acrescenta ao módulo não é mais um cadastro: é o **laço**. O
# PPC da PDCA.5 responde se a semana saiu; a medição da PDCA.3 responde quanto
# se paga por ela. Nenhum dos dois pergunta se o serviço saiu **certo** — e o
# retrabalho que essa pergunta evita é o que a causa `QUA-RETRAB` do catálogo da
# PDCA.5 já contava sem ter de onde vir.


class DominioVerificacao(models.TextChoices):
    """Os quatro domínios da mesma máquina.

    Lista fechada, e não texto livre, pelo mesmo motivo do `NivelLocal` e do
    `TipoRestricao`: é por ela que a biblioteca de modelos se organiza e que a
    leitura de conformidade se separa — o índice de qualidade de uma obra não se
    soma com o de segurança dela, ainda que os dois saiam da mesma tabela.

    **`entrega` não é redundante com `qualidade`.** A FVS confere o serviço no
    momento em que ele é executado, com a frente ainda aberta; a vistoria de
    entrega confere a unidade pronta, na frente do cliente, e o que ela gera é
    *punch list*. Mesma mecânica, momentos e públicos diferentes — e é por isso
    que a PDCA.11 reaproveita esta máquina em vez de ganhar a dela.
    """

    QUALIDADE = "qualidade", _("Qualidade (FVS)")
    SEGURANCA = "seguranca", _("Segurança")
    AMBIENTAL = "ambiental", _("Ambiental")
    ENTREGA = "entrega", _("Entrega / vistoria")


class ModeloVerificacao(TenantScopedModel, Excluivel):
    """O **modelo** de verificação — a ficha em branco da empresa.

    É a biblioteca de padrões da qualidade, irmã do plano modelo da PDCA.1b: o
    que faz a conformidade de duas obras ser comparável é elas terem respondido
    **à mesma ficha**. Modelo por obra, montado na hora, produziria um número de
    conformidade por engenheiro — que é o mesmo que nenhum.

    **`ativo` e a lixeira convivem, e não são o mesmo gesto.** O
    `CausaNaoCumprimento` recusou herdar `Excluivel` porque um item de catálogo
    desativado já é reversível por um clique, e dois mecanismos de desfazer para
    o mesmo gesto confundem. Aqui os gestos são dois de verdade: `ativo=False` é
    *"pare de oferecer esta ficha"* — ela sai da lista de escolha e continua
    legível em tudo que já foi verificado com ela —, e a lixeira é *"isto foi um
    engano"*, para o modelo de 150 itens que alguém montou no lugar errado. O
    que **não** existe é apagar modelo já aplicado: as fichas perderiam o nome
    do que responderam.
    """

    modelo_id = models.AutoField(primary_key=True)

    #: Curto e estável — é o que aparece no cabeçalho da ficha impressa e no
    #: eixo da leitura por modelo. Mesma régua do código da causa: o nome é do
    #: tenant, o código é a âncora da comparação.
    codigo = models.CharField(max_length=30, verbose_name=_("Código"))
    nome = models.CharField(max_length=150, verbose_name=_("Nome"))
    dominio = models.CharField(
        max_length=10, choices=DominioVerificacao.choices,
        default=DominioVerificacao.QUALIDADE, verbose_name=_("Domínio"),
    )
    #: Quando aplicar esta ficha — a instrução que o técnico lê antes de ir a
    #: campo ("após a cura, antes do revestimento"). É o que impede a FVS certa
    #: de ser aplicada na hora errada, que é o modo mais comum de ela não valer
    #: nada.
    descricao = models.TextField(blank=True, verbose_name=_("Quando aplicar"))

    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))

    criado_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Criado por"),
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Modelo de verificação")
        verbose_name_plural = _("Modelos de verificação")
        ordering = ["dominio", "codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "codigo"],
                condition=models.Q(excluido_em__isnull=True),
                name="pdca_modelo_verif_codigo_unico_por_tenant",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "dominio", "ativo"],
                name="pdca_modelo_verif_dominio_idx",
            ),
        ]

    def __str__(self):
        return f"{self.codigo} · {self.nome}"


class ItemModeloVerificacao(TenantScopedModel):
    """Uma pergunta da ficha em branco — **e o critério que a torna verificável**.

    **`criterio` é o campo que separa a FVS de uma opinião.** "A alvenaria está
    boa?" produz respostas diferentes de dois técnicos no mesmo dia; "prumo com
    desvio menor ou igual a 3 mm em 2 m, conferido com régua" produz a mesma. A
    NBR e o PBQP-H pedem critério objetivo exatamente por isso, e sem ele o
    índice de conformidade mede quem inspecionou, não como a obra está.

    **`exige_foto` é do item, não da ficha.** Obrigar foto em todos os itens faz
    a vistoria de 150 perguntas virar 150 fotos que ninguém olha; não permitir
    nenhuma deixa a NC sem prova. Quem monta o modelo marca os poucos itens em
    que a foto é a evidência — e é neles que a tela do campo insiste.
    """

    item_modelo_id = models.AutoField(primary_key=True)

    modelo = models.ForeignKey(
        ModeloVerificacao, on_delete=models.CASCADE, related_name="itens",
        verbose_name=_("Modelo"),
    )
    ordem = models.PositiveIntegerField(default=0, verbose_name=_("Ordem"))
    texto = models.TextField(verbose_name=_("O que se verifica"))
    criterio = models.TextField(
        blank=True, verbose_name=_("Critério de aceitação"),
    )
    #: Item obrigatório não aceita ficha concluída com ele pendente. Os demais
    #: aceitam — e isso é o que permite a ficha longa ser respondida no que
    #: importa sem travar a conclusão por causa de uma pergunta acessória.
    obrigatorio = models.BooleanField(
        default=True, verbose_name=_("Obrigatório"),
    )
    exige_foto = models.BooleanField(
        default=False, verbose_name=_("Exige foto"),
    )

    class Meta:
        verbose_name = _("Item do modelo de verificação")
        verbose_name_plural = _("Itens do modelo de verificação")
        ordering = ["ordem", "item_modelo_id"]
        indexes = [
            models.Index(
                fields=["tenant", "modelo", "ordem"],
                name="pdca_item_modelo_ordem_idx",
            ),
        ]

    def __str__(self):
        return f"{self.ordem}. {self.texto[:60]}"


class Verificacao(TenantScopedModel, Excluivel):
    """A **ficha aplicada** — o modelo, uma obra, um lugar, uma data, um inspetor.

    **Reprovação parcial é o caso normal, não a exceção** (planta §4.5). Uma FVS
    de alvenaria com 18 itens em que 2 reprovam é o dia comum do canteiro; um
    modelo que só soubesse dizer "aprovada" ou "reprovada" jogaria fora a
    informação inteira, que é *qual* item reprovou. Por isso não existe um campo
    `aprovada` aqui: o resultado é **derivado** dos itens (§4.9), e vem em quatro
    contagens mais a conformidade, nunca gravado.

    **`local` e `atividade` são os dois endereços, e os dois são opcionais.** A
    FVS de um serviço aponta para a `Atividade`; a vistoria de entrega de um
    apartamento aponta para o `LocalObra`; a inspeção de segurança do canteiro
    não aponta para nenhum dos dois. Obrigar qualquer um deles excluiria um dos
    quatro domínios da máquina.

    **`inspetor` é rótulo durável, não FK de usuário** — o padrão do módulo,
    pela mesma razão do `responsavel` da restrição: quem inspeciona é com
    frequência alguém de fora do sistema (o laboratório, o consultor do PBQP-H,
    o técnico da seguradora).
    """

    class Status(models.TextChoices):
        #: A ficha aberta, sendo respondida. É o estado em que o campo escreve.
        EM_ANDAMENTO = "em_andamento", _("Em andamento")
        #: Respondida e assinada. A partir daqui ela é leitura — corrigir uma
        #: ficha concluída é aplicar o modelo de novo, que é o que o mundo
        #: físico também exige: reinspecionar.
        CONCLUIDA = "concluida", _("Concluída")

    verificacao_id = models.AutoField(primary_key=True)

    #: `PROTECT`: a ficha respondida é prova de que alguém inspecionou aquele
    #: serviço naquele dia. Apagar o modelo e levá-la junto apagaria a evidência
    #: que o organismo certificador vem auditar.
    modelo = models.ForeignKey(
        ModeloVerificacao, on_delete=models.PROTECT, related_name="verificacoes",
        verbose_name=_("Modelo"),
    )
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE, related_name="verificacoes_pdca",
        verbose_name=_("Obra"),
    )
    local = models.ForeignKey(
        LocalObra, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="verificacoes", verbose_name=_("Local"),
    )
    atividade = models.ForeignKey(
        Atividade, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="verificacoes", verbose_name=_("Atividade"),
    )

    inspetor = models.CharField(
        max_length=150, blank=True, verbose_name=_("Inspetor"),
    )
    data = models.DateField(verbose_name=_("Data da inspeção"))

    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.EM_ANDAMENTO,
        verbose_name=_("Status"),
    )
    nota = models.TextField(blank=True, verbose_name=_("Nota da inspeção"))

    criada_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Criada por"),
    )
    criada_em = models.DateTimeField(auto_now_add=True)
    concluida_em = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Concluída em"),
    )
    concluida_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Concluída por"),
    )

    class Meta:
        verbose_name = _("Verificação")
        verbose_name_plural = _("Verificações")
        ordering = ["-data", "-verificacao_id"]
        indexes = [
            #: A leitura do cockpit: as fichas desta obra, da mais recente para
            #: a mais antiga.
            models.Index(
                fields=["tenant", "obra", "-data"],
                name="pdca_verificacao_obra_idx",
            ),
            #: E a fila do campo: o que ainda está aberto para responder.
            models.Index(
                fields=["tenant", "status"],
                name="pdca_verificacao_status_idx",
            ),
        ]

    def __str__(self):
        return f"{self.modelo_id} · obra {self.obra_id} · {self.data}"

    @property
    def esta_aberta(self) -> bool:
        """Só a ficha em andamento recebe resposta. Ver a docstring da classe."""
        return self.status == self.Status.EM_ANDAMENTO




class GravidadeNC(models.TextChoices):
    """Quanto a não-conformidade pesa — e o que cada degrau **autoriza**.

    Não é rótulo decorativo: é o que decide se a frente segue. O vocabulário é o
    do PBQP-H e o da ISO 9001 (maior x menor), com o terceiro degrau que o
    canteiro precisa e as normas de gestão não nomeiam.
    """

    MENOR = "menor", _("Menor — corrige-se na frente")
    MAIOR = "maior", _("Maior — o serviço não é aceito assim")
    CRITICA = "critica", _("Crítica — para o serviço")


class ResultadoItem(models.TextChoices):
    """As quatro respostas possíveis — e o `PENDENTE` é uma delas de propósito.

    É a mesma lição do `cumprido` tri-estado da PDCA.5: um item ainda não
    respondido **não é** um item reprovado. Sem o `PENDENTE`, a ficha
    recém-aberta nasceria com 18 reprovações e a conformidade dela seria 0%
    enquanto o técnico caminha até a frente de serviço — um número falso
    justamente no momento em que alguém poderia agir sobre ele.
    """

    PENDENTE = "pendente", _("Pendente")
    CONFORME = "conforme", _("Conforme")
    NAO_CONFORME = "nao_conforme", _("Não conforme")
    NAO_APLICAVEL = "nao_aplicavel", _("Não aplicável")


class ItemVerificacao(TenantScopedModel):
    """Uma resposta da ficha — **com a pergunta congelada dentro dela**.

    **`texto` e `criterio` são cópia, não referência, e essa é a decisão que
    torna a ficha uma prova.** O modelo é vivo: a empresa aperta o critério de
    prumo de 3 mm para 2 mm no ano seguinte, e faz bem. Se a ficha lesse o texto
    pelo FK, toda inspeção do ano anterior passaria a afirmar que conferiu 2 mm —
    e a auditoria do PBQP-H encontraria um sistema que reescreve o passado
    sozinho. É a mesma razão que congela preço no `ItemMedicao`: o documento
    guarda o que foi respondido, não o que se pergunta hoje.

    **Não conforme e não aplicável exigem observação**, e a trava é da aplicação
    e do banco. Sem ela a ficha degenera nos dois sentidos: o "não conforme" sem
    dizer o quê não vira ação nenhuma, e o "não aplicável" sem dizer por quê é a
    porta pela qual uma ficha inteira passa sem ninguém verificar nada — marcar
    N/A em tudo aprova o serviço sem mentir em nenhum campo.

    Não herda `Excluivel`: é linha filha de documento, na régua do `ItemMedicao`
    e do `ItemProgramacao`.
    """

    item_verificacao_id = models.AutoField(primary_key=True)

    verificacao = models.ForeignKey(
        Verificacao, on_delete=models.CASCADE, related_name="itens",
        verbose_name=_("Verificação"),
    )
    #: `PROTECT` e **opcional**: a linha aponta de volta para a pergunta do
    #: modelo enquanto ela existir, mas a ficha não depende disso para ser
    #: legível — o texto está congelado aqui. Nulo é o caso do item
    #: acrescentado à ficha em campo, que não veio de modelo nenhum.
    item_modelo = models.ForeignKey(
        ItemModeloVerificacao, on_delete=models.PROTECT, null=True, blank=True,
        related_name="respostas", verbose_name=_("Item do modelo"),
    )

    ordem = models.PositiveIntegerField(default=0, verbose_name=_("Ordem"))
    #: Congelados na aplicação do modelo — ver a docstring da classe.
    texto = models.TextField(verbose_name=_("O que se verifica"))
    criterio = models.TextField(
        blank=True, verbose_name=_("Critério de aceitação"),
    )
    obrigatorio = models.BooleanField(
        default=True, verbose_name=_("Obrigatório"),
    )
    exige_foto = models.BooleanField(
        default=False, verbose_name=_("Exige foto"),
    )

    resultado = models.CharField(
        max_length=14, choices=ResultadoItem.choices,
        default=ResultadoItem.PENDENTE, verbose_name=_("Resultado"),
    )
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))
    #: **Quanto ESTE defeito pesa** — e ele mora aqui, no item, porque a
    #: gravidade é propriedade do defeito e não da ficha.
    #:
    #: *(Decisão do dono, 16/09/2026, olhando o painel: "essa pergunta deveria
    #: ser feita em cada item e não no final, porque aí fica parecendo que um
    #: desalinhamento na porta é grave igual a falta de uma maçaneta".)*
    #:
    #: A primeira escrita desta fatia perguntava a gravidade **uma vez**, na
    #: conclusão da ficha, e carimbava o mesmo rótulo em todos os itens
    #: reprovados. O resultado era um painel dizendo "3 maiores" sobre três
    #: coisas de tamanhos diferentes — e um ranking de gravidade que não
    #: ranqueava nada, pelo mesmo mecanismo que faria o ranking de causas da
    #: PDCA.5 parar de funcionar se a causa fosse escolhida por semana em vez de
    #: por compromisso.
    #:
    #: **E é perguntada no item porque é lá que dá para responder.** Quem
    #: conclui a ficha pode não ser quem a respondeu (o `campo` responde,
    #: qualquer um com `aplicar` conclui) e pode nem ter estado na frente. Quem
    #: acabou de olhar o defeito sabe se ele se corrige na hora ou se para o
    #: serviço; quem lê uma lista depois, não.
    gravidade = models.CharField(
        max_length=8, choices=GravidadeNC.choices, null=True, blank=True,
        verbose_name=_("Gravidade do defeito"),
    )
    #: A evidência. Sobe pela **porta única** da plataforma
    #: (`nucleo.upload_validation`), que já impõe tipo e tamanho pelo teto do
    #: tenant — é por isso que a §5.5l do `planos.py` não declara um "bytes por
    #: item" próprio, que seria um segundo número para a mesma pergunta.
    foto = models.FileField(
        upload_to="pdca_verificacao/", null=True, blank=True,
        verbose_name=_("Foto"),
    )

    respondido_em = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Respondido em"),
    )
    respondido_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Respondido por"),
    )

    class Meta:
        verbose_name = _("Item de verificação")
        verbose_name_plural = _("Itens de verificação")
        ordering = ["ordem", "item_verificacao_id"]
        constraints = [
            #: **Desvio exige explicação.** A regra vive também no `services`,
            #: para a mensagem ser legível — mas mora aqui porque a importação e
            #: o comando de bancada entram por outras portas (a mesma lição do
            #: append-only da PDCA.2 e da causa da PDCA.5).
            models.CheckConstraint(
                condition=(
                    models.Q(resultado__in=["pendente", "conforme"])
                    | ~models.Q(observacao="")
                ),
                name="pdca_item_verif_desvio_explicado",
            ),
            #: **Exatamente o item reprovado carrega gravidade** — e os outros
            #: três resultados não carregam nenhuma.
            #:
            #: O primeiro lado impede a NC nascer sem peso, que é o que
            #: obrigaria alguém a inventar um depois. O segundo impede o
            #: contrário e é menos óbvio: um item que ficou *conforme* com
            #: gravidade `maior` pendurada (porque alguém marcou "não conforme",
            #: escolheu a gravidade e depois corrigiu para conforme) contaria no
            #: painel por gravidade um defeito que não existe.
            models.CheckConstraint(
                condition=(
                    models.Q(resultado="nao_conforme", gravidade__isnull=False)
                    | (
                        ~models.Q(resultado="nao_conforme")
                        & models.Q(gravidade__isnull=True)
                    )
                ),
                name="pdca_item_verif_gravidade_coerente",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "verificacao", "resultado"],
                name="pdca_item_verif_result_idx",
            ),
        ]

    def __str__(self):
        return f"{self.ordem}. {self.texto[:40]} — {self.get_resultado_display()}"



class NaoConformidade(TenantScopedModel, Excluivel):
    """O que saiu errado — **e o registro que não encerra sozinho**.

    **Nasce de um item reprovado ou avulsa** (planta §4.5), e as duas portas são
    necessárias. A primeira é a FVS: o item reprovou, e a NC leva junto o
    endereço, a foto e a pergunta que ele respondia. A segunda é o canteiro: o
    encarregado vê a trinca a caminho do almoxarifado, e obrigá-lo a abrir uma
    ficha de verificação inteira para registrá-la é o que faz a trinca não ser
    registrada.

    **`marcacao_prancheta` é o seam declarado com a Prancheta** (planta §6): a
    NC ancorada no pino sobre o desenho sai em **BCF** junto com o resto, e é
    assim que ela chega ao projetista dentro da ferramenta dele em vez de num
    e-mail. `SET_NULL` porque a marcação é documento do outro módulo e pode ser
    resolvida lá sem levar a NC junto.

    **`restricao` é o seam vivo com o Last Planner**, e é o que dá dente à
    gravidade: uma NC crítica *para o serviço*, e parar o serviço no vocabulário
    da PDCA.5 é exatamente uma `Restricao` aberta — a atividade deixa de poder
    entrar na programação da semana. Sem esse elo a gravidade seria adjetivo: o
    sistema diria "crítica" e o time se comprometeria com o serviço assim mesmo,
    na segunda-feira seguinte.

    **E ela não encerra enquanto a eficácia não for verificada** (§4.5). A regra
    é a que separa tratar de arquivar, e é o padrão do SAP QM: sem ela, "plano de
    ação concluído" vira o carimbo que fecha a NC, e ninguém volta à frente para
    ver se o conserto pegou. A trava mora no `services` e não numa
    `CheckConstraint` por uma razão física — ela olha **outra tabela**
    (`VerificacaoEficacia`), e check de banco não atravessa tabela.
    """

    class Status(models.TextChoices):
        ABERTA = "aberta", _("Aberta")
        #: Tem plano de ação. O degrau existe para a fila de decisão separar "o
        #: que ninguém pegou" de "o que está sendo consertado" — sem ele, o
        #: cockpit mostraria as duas como a mesma urgência.
        EM_TRATAMENTO = "em_tratamento", _("Em tratamento")
        ENCERRADA = "encerrada", _("Encerrada")
        #: Descartada sem tratamento — "não era NC", "o item saiu do escopo".
        #: Separada de `ENCERRADA` de propósito, pela mesma razão que separou
        #: `CANCELADA` de `REMOVIDA` na restrição: contar as duas juntas
        #: inflaria a leitura de quanto a obra conserta de fato.
        CANCELADA = "cancelada", _("Cancelada")

    nc_id = models.AutoField(primary_key=True)

    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE, related_name="ncs_pdca",
        verbose_name=_("Obra"),
    )
    local = models.ForeignKey(
        LocalObra, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="nao_conformidades", verbose_name=_("Local"),
    )
    atividade = models.ForeignKey(
        Atividade, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="nao_conformidades", verbose_name=_("Atividade"),
    )
    #: De onde ela nasceu, quando nasceu de uma ficha. `SET_NULL` e não
    #: `CASCADE`: a NC sobrevive à ficha porque o que ela registra não é a
    #: inspeção, é o defeito — e o defeito continua existindo.
    item_verificacao = models.ForeignKey(
        ItemVerificacao, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="nao_conformidades", verbose_name=_("Item que reprovou"),
    )

    gravidade = models.CharField(
        max_length=8, choices=GravidadeNC.choices, default=GravidadeNC.MENOR,
        verbose_name=_("Gravidade"),
    )
    descricao = models.TextField(verbose_name=_("Descrição"))
    foto = models.FileField(
        upload_to="pdca_nc/", null=True, blank=True, verbose_name=_("Foto"),
    )

    marcacao_prancheta = models.ForeignKey(
        "moduloprancheta.Marcacao", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="ncs_pdca",
        verbose_name=_("Marcação na Prancheta"),
    )
    restricao = models.ForeignKey(
        Restricao, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ncs", verbose_name=_("Restrição gerada"),
    )

    status = models.CharField(
        max_length=14, choices=Status.choices, default=Status.ABERTA,
        verbose_name=_("Status"),
    )

    aberta_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Aberta por"),
    )
    aberta_em = models.DateTimeField(auto_now_add=True)
    encerrada_em = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Encerrada em"),
    )
    encerrada_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Encerrada por"),
    )
    nota_encerramento = models.TextField(
        blank=True, verbose_name=_("Nota do encerramento"),
    )

    class Meta:
        verbose_name = _("Não-conformidade")
        verbose_name_plural = _("Não-conformidades")
        ordering = ["-aberta_em"]
        indexes = [
            #: A fila de decisão do cockpit: o que está aberto nesta obra.
            models.Index(
                fields=["tenant", "obra", "status"],
                name="pdca_nc_obra_status_idx",
            ),
            #: E a trava do quadro da semana: esta atividade tem NC aberta?
            models.Index(
                fields=["tenant", "atividade", "status"],
                name="pdca_nc_atividade_idx",
            ),
        ]

    def __str__(self):
        return f"NC {self.nc_id} · {self.get_gravidade_display()}"

    @property
    def esta_aberta(self) -> bool:
        return self.status in (self.Status.ABERTA, self.Status.EM_TRATAMENTO)


class PlanoAcao(TenantScopedModel):
    """O **5W2H** — o que se vai fazer a respeito, em sete perguntas.

    As sete existem porque cada uma sozinha é onde o tratamento falha na
    prática: plano sem `quem` não tem dono e ninguém executa; sem `quando` não
    vence e fica para sempre; sem `por_que` conserta o sintoma e a NC volta na
    semana seguinte. É o formato que o PBQP-H pede e que o canteiro brasileiro já
    escreve à mão — o software não está inventando um vocabulário novo.

    **Corretiva e preventiva são as duas que o PBQP-H exige**, e a diferença não
    é de grau: a corretiva conserta *esta* parede, a preventiva muda o processo
    para as próximas cem não saírem tortas. Um sistema que só registrasse a
    primeira produziria uma empresa que conserta a vida inteira sem nunca
    aprender — que é exatamente o que o "Act" do ciclo existe para evitar.

    Não herda `Excluivel`: é linha filha da NC, na régua do `ItemProgramacao`.
    """

    class Tipo(models.TextChoices):
        CORRETIVA = "corretiva", _("Corretiva — conserta o que saiu errado")
        PREVENTIVA = "preventiva", _("Preventiva — evita que volte a acontecer")

    class Status(models.TextChoices):
        PLANEJADA = "planejada", _("Planejada")
        EM_EXECUCAO = "em_execucao", _("Em execução")
        CONCLUIDA = "concluida", _("Concluída")
        CANCELADA = "cancelada", _("Cancelada")

    plano_id = models.AutoField(primary_key=True)

    nao_conformidade = models.ForeignKey(
        NaoConformidade, on_delete=models.CASCADE, related_name="acoes",
        verbose_name=_("Não-conformidade"),
    )
    tipo = models.CharField(
        max_length=10, choices=Tipo.choices, default=Tipo.CORRETIVA,
        verbose_name=_("Tipo"),
    )

    #: --- As sete perguntas -------------------------------------------------
    o_que = models.TextField(verbose_name=_("O quê"))
    por_que = models.TextField(blank=True, verbose_name=_("Por quê"))
    onde = models.CharField(max_length=200, blank=True, verbose_name=_("Onde"))
    #: O prazo. É o único dos sete que o sistema **cobra**: plano vencido e não
    #: concluído é linha da fila de decisão do cockpit.
    quando = models.DateField(null=True, blank=True, verbose_name=_("Quando"))
    #: Rótulo durável, como o `responsavel` da restrição e o `inspetor` da
    #: ficha, e pelo mesmo motivo: quem conserta é com frequência a empreiteira.
    quem = models.CharField(max_length=150, blank=True, verbose_name=_("Quem"))
    como = models.TextField(blank=True, verbose_name=_("Como"))
    #: Quanto custa. **Não vira título no ERP** (fronteira do módulo, §7): o
    #: custo do retrabalho é registrado aqui para virar leitura — quanto a
    #: qualidade desta obra custou —, e quem paga continua sendo o ERP pelo
    #: caminho que já existe.
    quanto = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        verbose_name=_("Quanto custa"),
    )

    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PLANEJADA,
        verbose_name=_("Status"),
    )
    concluida_em = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Concluída em"),
    )
    concluida_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Concluída por"),
    )

    criada_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Criada por"),
    )
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Plano de ação")
        verbose_name_plural = _("Planos de ação")
        ordering = ["quando", "plano_id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(status="concluida")
                    | models.Q(concluida_em__isnull=False)
                ),
                name="pdca_plano_acao_concluida_tem_data",
            ),
        ]
        indexes = [
            #: A fila do vencido: planos com prazo, ainda não concluídos.
            models.Index(
                fields=["tenant", "status", "quando"],
                name="pdca_plano_acao_fila_idx",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} · NC {self.nao_conformidade_id}"


class VerificacaoEficacia(TenantScopedModel):
    """**Funcionou?** — o registro que fecha o laço, e que pode dizer que não.

    É o que separa tratar de arquivar (planta §4.5). Sem ela, "plano de ação
    concluído" seria o carimbo que encerra a NC, e ninguém voltaria à frente
    para ver se o conserto pegou — que é como a maior parte dos sistemas de
    qualidade, de papel e de software, perde o valor inteiro do ciclo.

    **`eficaz=False` é o resultado mais útil dos dois.** Ele não encerra nada:
    a NC volta para tratamento, e o que vem a seguir é um plano de ação novo —
    porque o anterior, comprovadamente, não resolveu. É por isso que este
    modelo é **append-only na prática**: a segunda verificação não sobrescreve a
    primeira, e a sequência delas é a história honesta de quantas tentativas o
    conserto levou. O mesmo raciocínio do estorno do `ApontamentoAvanco`.

    Pende da **NC**, e não do plano de ação, porque é a NC que encerra: uma NC
    com três ações não fecha três vezes, fecha uma — quando a frente, olhada de
    novo, está certa.
    """

    eficacia_id = models.AutoField(primary_key=True)

    nao_conformidade = models.ForeignKey(
        NaoConformidade, on_delete=models.CASCADE, related_name="eficacias",
        verbose_name=_("Não-conformidade"),
    )
    data = models.DateField(verbose_name=_("Data da verificação"))
    eficaz = models.BooleanField(verbose_name=_("Foi eficaz"))
    #: O que se olhou para concluir isso. É o campo que a auditoria lê, e o que
    #: impede a verificação de eficácia de ser um `True` sem história.
    evidencia = models.TextField(verbose_name=_("Evidência"))
    foto = models.FileField(
        upload_to="pdca_eficacia/", null=True, blank=True,
        verbose_name=_("Foto"),
    )

    verificada_por = models.CharField(
        max_length=150, blank=True, verbose_name=_("Verificada por"),
    )
    verificada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Verificação de eficácia")
        verbose_name_plural = _("Verificações de eficácia")
        ordering = ["-data", "-eficacia_id"]
        indexes = [
            models.Index(
                fields=["tenant", "nao_conformidade", "-data"],
                name="pdca_eficacia_nc_idx",
            ),
        ]

    def __str__(self):
        marca = "eficaz" if self.eficaz else "não eficaz"
        return f"NC {self.nao_conformidade_id} · {marca} em {self.data}"


# ---------------------------------------------------------------------------
# PDCA.8 — SSMA: o diálogo de segurança e a ocorrência
# ---------------------------------------------------------------------------
# As fatias anteriores mediram prazo (PPC), dinheiro (medição) e serviço
# (verificação). Esta mede **gente** — e é a primeira do módulo cujo registro é
# prova perante o Estado, com prazo em lei e multa por omissão.
#
# **O que esta fatia NÃO cria, e por quê.** A §4.6 da planta listava três
# objetos: DDS, ocorrência e `EntregaEPI`. O terceiro **já existe**, completo,
# em `modulosil.EntregaEPI` desde 25/07/2026 — item do catálogo, colaborador do
# RH, CA e validade, troca, devolução, baixa de estoque. Recriá-lo aqui produzia
# duas verdades sobre o mesmo capacete: o saldo podendo baixar sem a ficha
# existir, e a ficha existindo sem o saldo baixar. E contradizia a §7 da própria
# planta, que diz que o PDCA **não** movimenta estoque. *(Decisão do dono,
# 20/09/2026: o PDCA lê o EPI do SIL e a §4.6 é corrigida.)* O que a SSMA faz
# com o EPI é **ler** — pela permissão do outro módulo, com import tardio, e
# declarando em voz alta quando o tenant não contrata o SIL.
#
# A segunda ausência é maior: **não existe `Efetivo`** (planta §4.7, fatia
# PDCA.9). O sistema não sabe quem está em qual frente hoje. Por isso esta fatia
# não promete "EPI vencido barra a entrada do trabalhador na frente" — o grão
# honesto disponível é a **obra**, e prometer o resto seria fabricar.


class TipoOcorrencia(models.TextChoices):
    """A taxonomia do fato, e a ordem dela é a pirâmide de Bird.

    **O quase-acidente é o primeiro da lista de propósito.** Ele é o registro
    mais valioso da segurança — é o acidente que avisou antes — e o mais fácil
    de não fazer, porque ninguém se machucou e o turno continua. Pôr o acidente
    no topo da lista faria o formulário abrir na tragédia e ensinaria que só se
    registra o que sangra.

    `INCIDENTE` é o fato **sem lesão e com dano** (a fôrma que caiu de noite, o
    cabo que queimou). Separado do quase-acidente porque tem custo e tem causa
    apurável, e separado do acidente porque não tem vítima — contar os três
    juntos é o que faz a pirâmide virar um número só e deixar de apontar nada.
    """

    QUASE_ACIDENTE = "quase_acidente", _("Quase-acidente (sem lesão e sem dano)")
    INCIDENTE = "incidente", _("Incidente (dano material, sem lesão)")
    ACIDENTE_TIPICO = "acidente_tipico", _("Acidente típico (no trabalho)")
    ACIDENTE_TRAJETO = "acidente_trajeto", _("Acidente de trajeto")
    DOENCA_OCUPACIONAL = "doenca_ocupacional", _("Doença ocupacional")


class ClassificacaoOcorrencia(models.TextChoices):
    """O que a ocorrência custou em tempo de gente — e o estado `PENDENTE`.

    **`PENDENTE` é o default e é a metade do desenho.** Registrar tem de ser
    barato; classificar é que muda o indicador. Se o formulário exigisse a
    classificação no ato, quem registra às 7h no canteiro teria de decidir, ali,
    se houve afastamento — coisa que só se sabe depois do atendimento médico. O
    resultado seria o registro adiado "para quando eu souber", que é o mesmo que
    o registro não feito.

    É a mesma lição do `cumprido` tri-estado da PDCA.5: o nulo que diz "ainda
    não se julgou" é informação, e o zero no lugar dele é mentira.
    """

    PENDENTE = "pendente", _("Ainda não classificada")
    SEM_AFASTAMENTO = "sem_afastamento", _("Sem afastamento")
    COM_AFASTAMENTO = "com_afastamento", _("Com afastamento")
    OBITO = "obito", _("Óbito")


class Lateralidade(models.TextChoices):
    """Exigida pelo formulário da CAT, e não é preciosismo clínico.

    O Anexo da Portaria SEPRT/ME 4.334/2021 pede parte do corpo **e** lado. A
    razão é previdenciária: perder três dedos da mão direita e da esquerda são
    incapacidades diferentes, e é sobre essa diferença que o benefício se
    calcula.
    """

    NAO_SE_APLICA = "nao_se_aplica", _("Não se aplica")
    ESQUERDA = "esquerda", _("Esquerda")
    DIREITA = "direita", _("Direita")
    AMBAS = "ambas", _("Ambas")


class TipoCAT(models.TextChoices):
    """Os três tipos do formulário vigente (Portaria SEPRT/ME 4.334/2021)."""

    INICIAL = "inicial", _("Inicial")
    REABERTURA = "reabertura", _("Reabertura")
    OBITO = "obito", _("Comunicação de óbito")


class DialogoSeguranca(TenantScopedModel, Excluivel):
    """O **DDS** — a roda de conversa antes do turno, e quem esteve nela.

    **Não é obrigatório por nome em norma nenhuma, e a fatia diz isso.** Varrendo
    as NRs, "DDS" não aparece em nenhuma e "diálogo" aparece uma vez (NR-1, item
    1.4.4.1). É prática de mercado consolidada — e é o principal **indicador
    proativo** que uma construtora tem: contar diálogos feitos mede o que a obra
    faz *antes*, e não só o que ela contabiliza depois. Registrar aqui um campo
    "obrigatório por norma" seria afirmar o que a norma não diz, e o sistema
    seria auditado por isso.

    **Por que ele é modelo próprio e não uma `Verificacao` de domínio
    `seguranca`.** A tentação é real, e a máquina da PDCA.7 já roda para os
    quatro domínios. Mas a ficha de verificação responde *perguntas sobre um
    objeto*, e o DDS não tem perguntas nem objeto: ele tem **tema, fala e lista
    de presença**. Encaixá-lo na ficha obrigaria a inventar itens falsos ("o
    diálogo foi realizado? conforme") só para caber, e a lista de presença — que
    é a única coisa que a fiscalização olha — não teria onde morar.

    **E por que ele escreve no Diário** (§7 — "não substitui o Diário: escreve e
    lê nele"): o diálogo de segurança faz parte do que aconteceu na obra naquele
    dia, e o diário é o registro contratual do dia. O PDCA é o primeiro módulo de
    negócio a atravessar essa porta.
    """

    class Status(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho")
        #: Encerrado fecha a lista de presença. Sem este degrau, alguém
        #: acrescentaria um nome três dias depois e a lista deixaria de ser
        #: prova de quem estava lá — que é a única coisa que ela é.
        ENCERRADO = "encerrado", _("Encerrado")

    dds_id = models.AutoField(primary_key=True)

    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE, related_name="dds_pdca",
        verbose_name=_("Obra"),
    )
    #: Local e atividade opcionais, na régua escrita na `Verificacao`: o diálogo
    #: da manhã é da obra inteira e não aponta para nenhum dos dois; obrigar
    #: qualquer um excluiria o caso mais comum.
    local = models.ForeignKey(
        LocalObra, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="dialogos_seguranca", verbose_name=_("Local"),
    )
    atividade = models.ForeignKey(
        Atividade, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="dialogos_seguranca", verbose_name=_("Atividade"),
    )

    data = models.DateField(verbose_name=_("Data"))
    tema = models.CharField(max_length=160, verbose_name=_("Tema"))
    assunto = models.TextField(blank=True, verbose_name=_("O que foi falado"))
    duracao_min = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_("Duração (minutos)"),
    )

    #: O par FK + texto livre é o mesmo do `EntregaEPI` do SIL, e existe pela
    #: mesma razão: metade de quem está no canteiro é de terceiro, e não tem
    #: cadastro no RH da construtora. Recusar o nome em texto excluiria da lista
    #: de presença justamente quem mais se acidenta.
    responsavel = models.ForeignKey(
        "rh.Funcionario", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name=_("Responsável (RH)"),
    )
    responsavel_nome = models.CharField(
        max_length=150, blank=True, verbose_name=_("Responsável (nome)"),
    )

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.RASCUNHO,
        verbose_name=_("Situação"),
    )
    encerrado_em = models.DateTimeField(null=True, blank=True)
    encerrado_por = models.CharField(max_length=150, blank=True)

    #: O diário que recebeu este diálogo. `SET_NULL` porque o diário é documento
    #: de outro módulo — a régua escrita na `Restricao.demanda`.
    diario = models.ForeignKey(
        "modulodiario.DiarioObra", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="dds_pdca",
        verbose_name=_("Diário de obra"),
    )

    registrado_por = models.CharField(max_length=150, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Diálogo de segurança (DDS)")
        verbose_name_plural = _("Diálogos de segurança (DDS)")
        ordering = ["-data", "-dds_id"]
        indexes = [
            #: A série do indicador proativo: quantos diálogos esta obra fez no
            #: período. É a consulta que o painel faz sempre.
            models.Index(
                fields=["tenant", "obra", "-data"], name="pdca_dds_obra_data_idx",
            ),
        ]
        constraints = [
            #: Cabe numa linha, então é do banco: encerrado sem carimbo seria um
            #: DDS fechado sem se saber quando — e a importação e o comando de
            #: bancada entram por outras portas.
            models.CheckConstraint(
                name="pdca_dds_encerrado_tem_carimbo",
                condition=(
                    models.Q(status="encerrado", encerrado_em__isnull=False)
                    | ~models.Q(status="encerrado")
                ),
            ),
        ]

    def __str__(self):
        return f"DDS {self.data} · {self.tema}"

    @property
    def esta_aberto(self) -> bool:
        return self.status == self.Status.RASCUNHO


class ParticipanteDDS(TenantScopedModel):
    """Quem esteve na roda — **a lista de presença, que é a prova**.

    O DDS sem lista é um campo de texto dizendo que houve diálogo. O que a
    fiscalização e a perícia olham é esta tabela: nomes, e se assinaram.

    **`assinou` é booleano e não guarda o traço da assinatura**, e isso é
    declarado em vez de disfarçado. Assinatura digital com valor probatório é
    fatia de plataforma, não de módulo; o que existe hoje é a lista impressa e
    assinada, fotografada e anexada à ocorrência ou ao diário. O campo diz que a
    assinatura **existe em algum lugar**, não que o sistema a guarda.
    """

    participante_id = models.AutoField(primary_key=True)

    dds = models.ForeignKey(
        DialogoSeguranca, on_delete=models.CASCADE, related_name="participantes",
        verbose_name=_("Diálogo"),
    )
    funcionario = models.ForeignKey(
        "rh.Funcionario", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name=_("Funcionário (RH)"),
    )
    nome = models.CharField(
        max_length=150, blank=True, verbose_name=_("Nome (terceirizado)"),
    )
    presente = models.BooleanField(default=True, verbose_name=_("Presente"))
    assinou = models.BooleanField(
        default=False, verbose_name=_("Assinou a lista"),
    )

    class Meta:
        verbose_name = _("Participante do DDS")
        verbose_name_plural = _("Participantes do DDS")
        ordering = ["participante_id"]
        constraints = [
            #: Ou o cadastro do RH, ou um nome escrito. Participante sem os dois
            #: é uma linha em branco na lista de presença — e uma lista de
            #: presença com linha em branco não prova nada.
            models.CheckConstraint(
                name="pdca_participante_dds_identificado",
                condition=(
                    models.Q(funcionario__isnull=False) | ~models.Q(nome="")
                ),
            ),
            #: A mesma pessoa não assina duas vezes a mesma roda.
            models.UniqueConstraint(
                fields=["dds", "funcionario"],
                condition=models.Q(funcionario__isnull=False),
                name="pdca_participante_dds_unico",
            ),
        ]

    def __str__(self):
        return self.nome or f"Funcionário {self.funcionario_id}"


class Ocorrencia(TenantScopedModel, Excluivel):
    """O que aconteceu e ninguém queria — **do quase-acidente ao óbito**.

    **Registrar é barato; classificar é que pesa.** A ocorrência nasce com
    `classificacao = PENDENTE` e só o `tipo`, a hora e a descrição são exigidos.
    Quem registra está no canteiro e acabou de ver; quem classifica decide o
    número pelo qual a obra é cobrada. Fossem o mesmo ato, o encarregado cujo
    bônus depende da taxa de frequência classificaria o próprio acidente — e é
    por isso que `pdca.ocorrencia.registrar` e `pdca.ocorrencia.classificar` são
    verbos separados no catálogo.

    **Os campos da CAT moram aqui, e a transmissão não.** O formulário vigente é
    o Anexo da Portaria SEPRT/ME 4.334/2021 (que revogou a 5.817/1999), e dele a
    ocorrência guarda o que **só a obra sabe**: hora, local, agente causador,
    situação geradora, parte do corpo e lado, último dia trabalhado, horas
    trabalhadas antes, registro policial. O que a obra não sabe — vínculo,
    remuneração, CNPJ — é do RH, e o que o sistema **não faz** é transmitir: o
    evento eSocial S-2210 é obrigação da folha, e duplicar a porta de um ato com
    prazo legal e multa criaria duas verdades sobre se a CAT foi comunicada.
    O que esta fatia faz é **avisar o prazo** e **guardar o protocolo**.

    *(O formulário vigente não tem campo de testemunhas — a 4.334/2021 o
    retirou. A fatia não o inventa.)*

    **`restricao` é o dente**, e é a mesma corrente que a NC crítica já
    percorre: risco grave abre uma `Restricao` de tipo `AREA` e a atividade sai
    do quadro da semana. Sem ela, "acidente grave" seria adjetivo e a equipe se
    comprometeria com o mesmo serviço na segunda seguinte. Não há
    `TipoRestricao.SEGURANCA` novo: interditar frente por risco **é** "a área
    não está liberada", e um nono tipo partiria o ranking de restrição em dois
    vocabulários para o mesmo fato — o argumento que a PDCA.7 já escreveu ao
    recusar um tipo próprio para a qualidade.

    **`nao_conformidade` é o laço.** Investigar acidente com árvore de causas e
    5W2H é exatamente o que `NaoConformidade` + `PlanoAcao` +
    `VerificacaoEficacia` já fazem, e refazê-los aqui produziria uma segunda
    máquina de tratamento que divergiria da primeira na primeira mudança de
    requisito. A ocorrência é o **fato**; a NC é o **tratamento** dele.
    """

    class Status(models.TextChoices):
        ABERTA = "aberta", _("Aberta")
        EM_INVESTIGACAO = "em_investigacao", _("Em investigação")
        ENCERRADA = "encerrada", _("Encerrada")
        #: Separada de `ENCERRADA` pela razão de sempre nesta casa (a mesma que
        #: separou `CANCELADA` de `REMOVIDA` na restrição): contar as duas
        #: juntas inflaria a leitura de quanto a obra de fato trata.
        CANCELADA = "cancelada", _("Cancelada")

    ocorrencia_id = models.AutoField(primary_key=True)

    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE, related_name="ocorrencias_pdca",
        verbose_name=_("Obra"),
    )
    local = models.ForeignKey(
        LocalObra, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ocorrencias", verbose_name=_("Local"),
    )
    atividade = models.ForeignKey(
        Atividade, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ocorrencias", verbose_name=_("Atividade"),
    )

    #: **Data e hora**, não só data — a CAT pede a hora do acidente e as horas
    #: trabalhadas antes dele, e as duas juntas é que dizem se o acidente
    #: aconteceu na quarta hora ou na décima segunda.
    ocorrido_em = models.DateTimeField(verbose_name=_("Ocorrido em"))
    tipo = models.CharField(
        max_length=20, choices=TipoOcorrencia.choices,
        default=TipoOcorrencia.QUASE_ACIDENTE, verbose_name=_("Tipo"),
    )
    descricao = models.TextField(verbose_name=_("O que aconteceu"))

    # --- Bloco da CAT que a obra conhece (Portaria SEPRT/ME 4.334/2021) ---
    agente_causador = models.CharField(
        max_length=160, blank=True, verbose_name=_("Agente causador"),
    )
    situacao_geradora = models.CharField(
        max_length=160, blank=True, verbose_name=_("Situação geradora"),
    )
    houve_registro_policial = models.BooleanField(
        default=False, verbose_name=_("Houve registro policial"),
    )
    horas_trabalhadas_antes = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_("Horas trabalhadas antes"),
    )
    ultimo_dia_trabalhado = models.DateField(
        null=True, blank=True, verbose_name=_("Último dia trabalhado"),
    )

    # --- Quem se machucou ---
    acidentado = models.ForeignKey(
        "rh.Funcionario", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="+", verbose_name=_("Acidentado (RH)"),
    )
    acidentado_nome = models.CharField(
        max_length=150, blank=True, verbose_name=_("Acidentado (nome)"),
    )
    parte_do_corpo = models.CharField(
        max_length=120, blank=True, verbose_name=_("Parte do corpo atingida"),
    )
    lateralidade = models.CharField(
        max_length=14, choices=Lateralidade.choices,
        default=Lateralidade.NAO_SE_APLICA, verbose_name=_("Lateralidade"),
    )

    # --- Bloco clínico: PII do art. 11 da LGPD, atrás de verbo próprio ---
    #: **A primeira PII do grupo `pdca`.** Estes quatro campos só saem pelo
    #: serializer para quem tem `pdca.ocorrencia.dado_medico`; para todo o resto
    #: eles vêm mascarados. É a régua do `rh.dado_medico`, e a razão é a mesma:
    #: para classificar o acidente ninguém precisa do diagnóstico.
    natureza_lesao = models.CharField(
        max_length=160, blank=True, verbose_name=_("Natureza da lesão"),
    )
    cid10 = models.CharField(max_length=10, blank=True, verbose_name=_("CID-10"))
    houve_internacao = models.BooleanField(
        default=False, verbose_name=_("Houve internação"),
    )
    atestado_dias = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_("Dias de atestado"),
    )

    # --- Classificação: o verbo separado ---
    classificacao = models.CharField(
        max_length=16, choices=ClassificacaoOcorrencia.choices,
        default=ClassificacaoOcorrencia.PENDENTE,
        verbose_name=_("Classificação"),
    )
    #: `dias_perdidos` é o afastamento real; `dias_debitados` é a tabela da NBR
    #: 14280 para incapacidade permanente e morte (6.000 dias no óbito). São
    #: duas grandezas diferentes e a taxa de gravidade soma as duas — guardá-las
    #: no mesmo campo perderia a distinção que a norma faz.
    dias_perdidos = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_("Dias perdidos"),
    )
    dias_debitados = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name=_("Dias debitados (NBR 14280)"),
    )
    classificada_em = models.DateTimeField(null=True, blank=True)
    classificada_por = models.CharField(max_length=150, blank=True)

    # --- CAT: o registro do ato, não o ato ---
    cat_tipo = models.CharField(
        max_length=10, choices=TipoCAT.choices, blank=True,
        verbose_name=_("Tipo de CAT"),
    )
    cat_emitida_em = models.DateField(
        null=True, blank=True, verbose_name=_("CAT emitida em"),
    )
    cat_protocolo = models.CharField(
        max_length=60, blank=True, verbose_name=_("Protocolo da CAT"),
    )
    cat_registrada_por = models.CharField(max_length=150, blank=True)

    # --- Os dois seams ---
    restricao = models.ForeignKey(
        Restricao, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ocorrencias", verbose_name=_("Restrição gerada"),
    )
    nao_conformidade = models.ForeignKey(
        NaoConformidade, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ocorrencias", verbose_name=_("Tratamento (NC)"),
    )

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ABERTA,
        verbose_name=_("Situação"),
    )
    registrada_por = models.CharField(max_length=150, blank=True)
    registrada_em = models.DateTimeField(auto_now_add=True)
    encerrada_em = models.DateTimeField(null=True, blank=True)
    encerrada_por = models.CharField(max_length=150, blank=True)
    nota_encerramento = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Ocorrência de segurança")
        verbose_name_plural = _("Ocorrências de segurança")
        ordering = ["-ocorrido_em", "-ocorrencia_id"]
        indexes = [
            #: A fila do cockpit: o que está aberto nesta obra.
            models.Index(
                fields=["tenant", "obra", "status"],
                name="pdca_ocor_obra_status_idx",
            ),
            #: A série dos indicadores: o que aconteceu no período, por tipo.
            models.Index(
                fields=["tenant", "obra", "-ocorrido_em"],
                name="pdca_ocor_obra_data_idx",
            ),
            #: A trava do quadro da semana, no molde do `pdca_nc_atividade_idx`.
            models.Index(
                fields=["tenant", "atividade", "status"],
                name="pdca_ocor_atividade_idx",
            ),
        ]
        constraints = [
            #: Cabe numa linha: afastamento sem dias é a classificação pela
            #: metade, e é dela que a taxa de gravidade nasce.
            models.CheckConstraint(
                name="pdca_ocorrencia_afastamento_tem_dias",
                condition=(
                    models.Q(
                        classificacao="com_afastamento",
                        dias_perdidos__isnull=False,
                    )
                    | ~models.Q(classificacao="com_afastamento")
                ),
            ),
            #: Os dois sentidos: CAT emitida sem tipo, e tipo pendurado em quem
            #: não emitiu. É a forma do `pdca_item_verif_gravidade_coerente`.
            models.CheckConstraint(
                name="pdca_ocorrencia_cat_coerente",
                condition=(
                    models.Q(cat_emitida_em__isnull=True, cat_tipo="")
                    | models.Q(cat_emitida_em__isnull=False)
                    & ~models.Q(cat_tipo="")
                ),
            ),
        ]

    def __str__(self):
        return f"Ocorrência {self.ocorrencia_id} · {self.get_tipo_display()}"

    @property
    def esta_aberta(self) -> bool:
        return self.status in (self.Status.ABERTA, self.Status.EM_INVESTIGACAO)

    #: Os tipos que geram CAT, **como constante e não como literal dentro do
    #: `exige_cat`**. A regra precisa ser respondível de dois jeitos: objeto a
    #: objeto (a propriedade abaixo, que é como a tela e o serializer
    #: perguntam) e em SQL (`tipo__in=...`, que é como a carteira conta CATs
    #: devidas em quarenta obras sem carregar quarenta mil ocorrências).
    #: Repetir a tupla no `filter` criaria a segunda verdade que o D138 ensinou
    #: a não criar — e o dia em que a lista mudasse, um dos dois lados ficaria.
    TIPOS_QUE_EXIGEM_CAT = (
        TipoOcorrencia.ACIDENTE_TIPICO,
        TipoOcorrencia.ACIDENTE_TRAJETO,
        TipoOcorrencia.DOENCA_OCUPACIONAL,
    )

    @property
    def exige_cat(self) -> bool:
        """**A CAT é devida mesmo sem afastamento** (MOS do eSocial, S-2210 §7.2).

        É o erro mais comum do mercado — a empresa comunica só o que afasta —, e
        é por isso que a regra mora aqui em vez de na cabeça de quem preenche.
        Quase-acidente e incidente não têm vítima e não geram CAT; os três tipos
        restantes geram, e a classificação não muda isso.
        """
        return self.tipo in self.TIPOS_QUE_EXIGEM_CAT


class AnexoOcorrencia(TenantScopedModel):
    """Os arquivos da ocorrência — **e é a primeira coleção do módulo**.

    Toda foto do PDCA até aqui é um `FileField` único: uma no apontamento, uma
    no item da ficha, uma na NC. A ocorrência é diferente por uma razão física —
    a cena se fotografa de vários ângulos porque a perícia vai olhar de vários
    ângulos, e junto vêm o atestado e o boletim. Forçá-la no campo único faria
    quem registra escolher qual foto do acidente vale, no pior momento possível
    para escolher.

    A consequência é um teto novo (`PDCA_TETO_ANEXOS_POR_OCORRENCIA`): a porta
    única da plataforma controla **bytes por arquivo** e nunca quantidade de
    arquivos, então sem um número aqui o teto de bytes seria multiplicado por um
    fator que ninguém declarou.
    """

    class Especie(models.TextChoices):
        CENA = "cena", _("Cena / local do fato")
        ATESTADO = "atestado", _("Atestado médico")
        BOLETIM = "boletim", _("Boletim de ocorrência")
        LISTA_PRESENCA = "lista_presenca", _("Lista de presença assinada")
        OUTRO = "outro", _("Outro")

    anexo_id = models.AutoField(primary_key=True)

    ocorrencia = models.ForeignKey(
        Ocorrencia, on_delete=models.CASCADE, related_name="anexos",
        verbose_name=_("Ocorrência"),
    )
    arquivo = models.FileField(
        upload_to="pdca_ssma/", verbose_name=_("Arquivo"),
    )
    #: A espécie decide **quem pode abrir**: o atestado é dado de saúde e sai
    #: por `pdca.ocorrencia.dado_medico`; a foto da cena sai por
    #: `pdca.ocorrencia.view`. É o mesmo corte por espécie que o `pdca.nc_foto`
    #: já faz entre a foto do defeito e a da eficácia.
    especie = models.CharField(
        max_length=16, choices=Especie.choices, default=Especie.CENA,
        verbose_name=_("Espécie"),
    )
    descricao = models.CharField(max_length=160, blank=True)
    enviado_por = models.CharField(max_length=150, blank=True)
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Anexo da ocorrência")
        verbose_name_plural = _("Anexos da ocorrência")
        ordering = ["anexo_id"]
        indexes = [
            models.Index(
                fields=["tenant", "ocorrencia"], name="pdca_anexo_ocor_idx",
            ),
        ]

    def __str__(self):
        return f"{self.get_especie_display()} · ocorrência {self.ocorrencia_id}"
