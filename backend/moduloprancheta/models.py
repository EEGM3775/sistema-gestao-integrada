# backend/moduloprancheta/models.py
"""Prancheta — o projeto da obra, aberto em campo.

Planta: docs/modulos/moduloprancheta.md. Três tabelas sustentam o módulo, e a
separação entre elas é a resposta à pergunta do canteiro — *"esta é a última?"*:

- `DocumentoProjeto` é o documento **lógico** ("Planta baixa pavimento tipo").
  Não guarda arquivo nenhum.
- `RevisaoDocumento` é cada entrega (R00, R01…), com o arquivo como o cliente o
  mandou. **Revisão nova é linha nova, nunca UPDATE** — é isso que permite ao
  campo comparar R01 com R02 em vez de descobrir que o desenho mudou embaixo
  dele, e é o que torna a derivada imutável (planta §8).
- `DerivadaProjeto` é o produto da conversão, carimbado com o motor e a versão
  do motor. Nasce aqui vazia: o pipeline é o PRA.1. A tabela existe desde já
  porque a chave `(revisão, tipo, motor)` é o que faz as duas derivadas do mesmo
  DWG coexistirem — subir de plano reconverte com o motor melhor sem invalidar
  nada, descer não apaga o que já foi convertido (planta §4.1).

O app não é um segundo DMS: a Prancheta **abre**, e o DMS (o `funcoesimpexp`) governará
versão formal, aprovação e assinatura (planta §7).
"""
import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from nucleo.tenancy import TenantScopedModel

from .formatos import FORMATO_CHOICES, MOTOR_CHOICES


class Disciplina(models.TextChoices):
    """O eixo pelo qual o canteiro procura prancha. Não é taxonomia acadêmica:
    é o que está escrito no carimbo do desenho e na boca do mestre de obras."""

    ARQUITETURA = "arquitetura", _("Arquitetura")
    ESTRUTURAL = "estrutural", _("Estrutural")
    FUNDACAO = "fundacao", _("Fundações")
    HIDROSSANITARIO = "hidrossanitario", _("Hidrossanitário")
    ELETRICA = "eletrica", _("Elétrica")
    INCENDIO = "incendio", _("Combate a incêndio")
    CLIMATIZACAO = "climatizacao", _("Climatização")
    TERRAPLANAGEM = "terraplanagem", _("Terraplanagem")
    PAVIMENTACAO = "pavimentacao", _("Pavimentação")
    TOPOGRAFIA = "topografia", _("Topografia")
    IMPLANTACAO = "implantacao", _("Implantação / urbanismo")
    LEGAL = "legal", _("Projeto legal / aprovação")
    OUTRA = "outra", _("Outra")


class DisciplinaProjeto(TenantScopedModel):
    """A disciplina que **esta empresa** usa — o vocabulário dela, não o nosso.

    As 13 de `Disciplina` acima continuam existindo como **piso**: são o que o
    canteiro brasileiro escreve no carimbo, e é delas que a taxonomia do lote
    adivinha a pasta. O que faltava era o andar de cima — construtora que separa
    "Fachada" de "Arquitetura", ou que trabalha com "Impermeabilização" e
    "Paisagismo", não tinha onde pôr, e todo arquivo caía em *Outra*.

    **É tag, não FK.** O documento continua guardando o `codigo` como texto, e
    esta tabela só resolve rótulo, cor e ordem. Duas consequências que valem o
    desenho: o acervo que já existe não precisa de migração de dados (os slugs
    das 13 continuam valendo sem linha nenhuma aqui), e apagar uma disciplina não
    apaga prancha — ela volta a se chamar pelo próprio slug, que é feio e honesto,
    em vez de levar junto o documento por `CASCADE`.

    A **cor** é escolhida por quem cria porque a grade filtra por cor antes de
    filtrar por palavra (§9.1): quem trabalha na obra reconhece a sua sem
    soletrar, e um sorteio automático poria duas disciplinas vizinhas no mesmo
    matiz justamente onde a tela é lida sob sol.
    """

    disciplina_id = models.AutoField(primary_key=True)
    codigo = models.SlugField(max_length=40, verbose_name=_("Código"))
    nome = models.CharField(max_length=60, verbose_name=_("Nome"))
    cor = models.CharField(
        max_length=7, blank=True, verbose_name=_("Cor"),
        help_text=_("Hex (#RRGGBB). Em branco, a tela deriva uma estável do código."),
    )
    # Ordem manual antes do alfabeto: a construtora sabe que Arquitetura e
    # Estrutural são consultadas dez vezes mais que Paisagismo, e a fileira da
    # grade é justamente onde isso paga.
    ordem = models.PositiveIntegerField(default=100, verbose_name=_("Ordem"))
    ativa = models.BooleanField(default=True, verbose_name=_("Ativa"))
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Disciplina de projeto")
        verbose_name_plural = _("Disciplinas de projeto")
        ordering = ["ordem", "nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "codigo"], name="prancheta_disciplina_codigo_por_tenant"
            ),
        ]

    def __str__(self):
        return self.nome


class DocumentoProjeto(TenantScopedModel):
    """O documento lógico. É ele que tem nome, disciplina e lugar na obra.

    `codigo` é o do projetista ("ARQ-PLB-001"), não um id nosso: é por ele que o
    escritório e o canteiro se referem à prancha, e é o que faz a revisão nova
    encontrar o documento certo na hora de subir.
    """

    documento_id = models.AutoField(primary_key=True)
    obra = models.ForeignKey(
        "obras.Obra", on_delete=models.CASCADE, related_name="documentos_projeto",
        verbose_name=_("Obra"),
    )
    # A etapa é o mesmo eixo que o SIL usa para apropriar consumo e o Orçamento
    # para o cronograma — amarrar a prancha nela é o que deixa "o que executar
    # agora" e "com que desenho" na mesma pergunta.
    etapa = models.ForeignKey(
        "obras.EtapaObra", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="documentos_projeto", verbose_name=_("Etapa"),
    )
    codigo = models.CharField(max_length=60, verbose_name=_("Código do documento"))
    titulo = models.CharField(max_length=180, verbose_name=_("Título"))
    # **Sem `choices`, e é decisão de desenho** (PRA.9b): o valor é um slug, e o
    # vocabulário passou a ser do tenant (`DisciplinaProjeto`). Manter `choices`
    # aqui faria o `full_clean` recusar a disciplina que o próprio cliente
    # cadastrou, e o `get_disciplina_display` responder o slug cru para ela — o
    # rótulo agora sai da tabela, com as 13 embutidas como piso.
    disciplina = models.CharField(
        max_length=40, default=Disciplina.OUTRA, verbose_name=_("Disciplina"),
    )
    descricao = models.TextField(blank=True, verbose_name=_("Descrição"))
    # Autoria do desenho é TEXTO, não FK de usuário: o projetista costuma ser
    # escritório terceirizado, que não tem (nem deve ter) login no sistema. Quem
    # subiu o arquivo é outra pergunta, e ela é respondida na revisão.
    projetista = models.CharField(max_length=180, blank=True, verbose_name=_("Projetista/escritório"))
    ativo = models.BooleanField(default=True, verbose_name=_("Ativo"))
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Documento de projeto")
        verbose_name_plural = _("Documentos de projeto")
        ordering = ["obra", "disciplina", "codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "obra", "codigo"], name="prancheta_documento_codigo_por_obra"
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "obra", "disciplina"], name="prancheta_doc_obra_disc_idx"),
        ]

    def __str__(self):
        return f"{self.codigo} — {self.titulo}"

    @property
    def revisao_vigente(self):
        """A revisão que o campo deve executar, ou `None` se ainda não há uma.

        Documento sem vigente é item da fila de decisão do cockpit (planta §11),
        não um erro: acervo carregado em lote nasce assim.

        Filtra em Python, não no banco, de propósito: o acervo de uma obra lista
        dezenas de documentos e faz `prefetch_related("revisoes")`. Um
        `.filter()` aqui ignoraria o cache do prefetch e voltaria a fazer uma
        query por documento — o N+1 clássico, no endpoint que é justamente o do
        celular no canteiro. Sem prefetch, o custo é o mesmo de antes.
        """
        for revisao in self.revisoes.all():
            if revisao.situacao == RevisaoDocumento.Situacao.VIGENTE:
                return revisao
        return None

    @property
    def codigos_de_disciplina(self) -> list[str]:
        """As disciplinas desta prancha, a principal primeiro.

        Lê do vínculo quando ele existe e cai no campo denormalizado quando não —
        que é o estado de todo documento anterior à PRA.9c e o que faz a migração
        de dados ser desnecessária.
        """
        vinculos = list(self.vinculos_disciplina.all())
        if vinculos:
            return [v.codigo for v in sorted(vinculos, key=lambda v: (v.ordem, v.codigo))]
        return [self.disciplina] if self.disciplina else []

    def definir_disciplinas(self, codigos) -> list[str]:
        """**A única porta** por onde o conjunto de disciplinas muda.

        Grava os vínculos e sincroniza `disciplina` com o primeiro da lista. A
        denormalização existe porque três coisas dependem de haver **uma**
        disciplina: a ordenação do acervo, a coluna do lote e a cor do cartão —
        e ela só é segura enquanto ninguém escrever no campo por fora. Por isso
        este método, e por isso o `views`/`impexp` o chamam em vez de atribuir.

        Preserva a ordem recebida (a primeira é a principal) e ignora repetição,
        que é o que a tela manda quando alguém toca duas vezes no mesmo chip.
        """
        vistos: list[str] = []
        for codigo in codigos or []:
            limpo = (codigo or "").strip()
            if limpo and limpo not in vistos:
                vistos.append(limpo)

        self.vinculos_disciplina.all().delete()
        if not vistos:
            # Sem nenhuma, volta ao default do modelo — nunca fica sem
            # classificação, porque a grade agrupa por ela.
            self.disciplina = Disciplina.OUTRA
            self.save(update_fields=["disciplina"])
            return []

        DocumentoDisciplina.objects.bulk_create([
            DocumentoDisciplina(
                tenant_id=self.tenant_id, documento=self, codigo=codigo, ordem=i,
            )
            for i, codigo in enumerate(vistos)
        ])
        if self.disciplina != vistos[0]:
            self.disciplina = vistos[0]
            self.save(update_fields=["disciplina"])
        return vistos


class DocumentoDisciplina(TenantScopedModel):
    """Uma disciplina **desta** prancha. Uma prancha pode ter várias.

    Existe porque o desenho real não obedece a uma classificação só: a planta de
    forro é arquitetura e elétrica ao mesmo tempo, o corte de shaft é hidro e
    incêndio, e obrigar a escolher uma fazia a pessoa escolher errado ou não
    escolher — que era o caminho para tudo cair em *Outra*.

    **Guarda o código, não uma FK**, pelo mesmo motivo do documento (§9.1): o
    vocabulário embutido não tem linha em `DisciplinaProjeto`, e apagar uma
    disciplina criada não pode levar prancha junto. `ordem = 0` é a principal — é
    dela que saem a cor do cartão e a ordenação do acervo.
    """

    documento = models.ForeignKey(
        DocumentoProjeto, on_delete=models.CASCADE, related_name="vinculos_disciplina",
    )
    codigo = models.SlugField(max_length=40, verbose_name=_("Disciplina"))
    ordem = models.PositiveSmallIntegerField(default=0, verbose_name=_("Ordem"))

    class Meta:
        verbose_name = _("Disciplina do documento")
        verbose_name_plural = _("Disciplinas do documento")
        ordering = ["ordem", "codigo"]
        constraints = [
            models.UniqueConstraint(
                fields=["documento", "codigo"], name="prancheta_documento_disciplina_unica"
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "codigo"], name="prancheta_docdisc_codigo_idx"),
        ]

    def __str__(self):
        return f"{self.documento_id} · {self.codigo}"


def caminho_revisao(instance, filename):
    """Arquivo por tenant e obra. O tenant no caminho não é a proteção (essa é a
    RLS + o escopo do queryset) — é o que torna auditoria, cota de storage e
    expurgo por cliente uma operação de diretório em vez de uma varredura."""
    return f"prancheta/{instance.tenant_id}/obra-{instance.documento.obra_id}/{filename}"


class RevisaoDocumento(TenantScopedModel):
    """Uma entrega do projetista: o arquivo como ele veio, e em que estado está.

    **`vigente` é ato, não campo editável.** Publicar muda o que o campo vai
    executar, então é verbo com permissão própria (`prancheta.revisao.publicar`)
    — a mesma classe do `aprovar` do Orçamento, e a lição do D28 é que o verbo
    precisa também de uma persona que o tenha, senão só o admin do tenant
    consegue.
    """

    class Situacao(models.TextChoices):
        RASCUNHO = "rascunho", _("Rascunho (recebida, não publicada)")
        VIGENTE = "vigente", _("Vigente — é esta que se executa")
        SUPERADA = "superada", _("Superada por revisão posterior")

    revisao_id = models.AutoField(primary_key=True)
    documento = models.ForeignKey(
        DocumentoProjeto, on_delete=models.CASCADE, related_name="revisoes",
        verbose_name=_("Documento"),
    )
    revisao = models.CharField(max_length=10, verbose_name=_("Revisão"))  # R00, R01…
    arquivo = models.FileField(upload_to=caminho_revisao, verbose_name=_("Arquivo"))
    nome_original = models.CharField(max_length=255, verbose_name=_("Nome do arquivo enviado"))
    # **De qual pasta do escritório esta prancha veio.** O lote da R18 já lê o
    # caminho relativo para adivinhar disciplina, código e revisão, e até
    # 13/08/2026 o descartava logo depois: só o `nome_original` sobrevivia. Num
    # acervo histórico o nome não identifica nada — o corpus real tem `006.dwg` e
    # `AEGS06.DWG` repetidos entre subpastas —, e a tabela de custo por arquivo
    # teve de reconstruir esta coluna por SHA-256 contra a pasta de origem, que é
    # uma resposta que só existe enquanto alguém ainda tiver a pasta.
    #
    # **É texto de quem enviou, e não decide nada** — a mesma regra do
    # `nome_original`: não escolhe motor, não vira caminho de gravação (quem faz
    # isso é `caminho_revisao`, a partir de tenant e obra) e não é lido de volta
    # como estrutura. Serve para *responder* de onde veio, que é rastreabilidade,
    # e por isso pode ser vazio sem que nada quebre — todo acervo carregado antes
    # desta fatia está assim.
    caminho_origem = models.CharField(
        max_length=1024, blank=True, default="",
        verbose_name=_("Caminho de origem no acervo"),
    )
    formato = models.CharField(max_length=10, choices=FORMATO_CHOICES, verbose_name=_("Formato"))
    tamanho_bytes = models.PositiveBigIntegerField(default=0, verbose_name=_("Tamanho (bytes)"))
    # SHA-256 do conteúdo. Calculado na entrada porque é o que dá idempotência ao
    # pipeline do PRA.1 (`hash` + versão do motor decidem se reconverte) — gravar
    # depois exigiria reler todo o acervo já carregado.
    hash_sha256 = models.CharField(max_length=64, blank=True, verbose_name=_("SHA-256"))

    situacao = models.CharField(
        max_length=10, choices=Situacao.choices, default=Situacao.RASCUNHO,
        verbose_name=_("Situação"),
    )
    data_emissao = models.DateField(null=True, blank=True, verbose_name=_("Data de emissão pelo projetista"))
    observacao = models.TextField(blank=True, verbose_name=_("Observação"))

    enviado_por = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="revisoes_projeto_enviadas", verbose_name=_("Enviado por"),
    )
    enviado_em = models.DateTimeField(auto_now_add=True)
    publicado_por = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="revisoes_projeto_publicadas", verbose_name=_("Publicado por"),
    )
    publicado_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Publicado em"))

    # -- escala (PRA.3 · procedência na PRA.3b · mudou de casa nesta fatia) ----
    # **Medir exige escala declarada, e o desenho pode ou não trazê-la.**
    #
    # Um DXF/DWG **traz**: as coordenadas estão em unidades de desenho e o
    # cabeçalho declara a unidade (`$INSUNITS`). É daí que o AutoCAD tira o
    # "3,50 m" sem ninguém calibrar nada, e o motor a extrai na conversão
    # (`motores/dxf.py::escala_do_desenho`). Um PDF, uma foto de prancha e um DXF
    # sem `$INSUNITS` **não trazem**, e aí alguém calibra sobre uma cota conhecida.
    #
    # **Os campos moram em `DesenhoProjeto`, não aqui**, e a razão é que uma
    # revisão pode trazer várias folhas de tamanhos diferentes: a grandeza é
    # "unidades reais na largura do desenho", e um número só descreveria no máximo
    # uma delas — em silêncio, para as outras. É o tipo de erro que a §13.2 chama
    # de pior, o que vira parede no lugar errado.

    class OrigemEscala(models.TextChoices):
        DESENHO = "desenho", _("Declarada pelo desenho")
        CALIBRADA = "calibrada", _("Calibrada por uma pessoa")

    class Meta:
        verbose_name = _("Revisão de documento")
        verbose_name_plural = _("Revisões de documento")
        ordering = ["documento", "-revisao"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "documento", "revisao"], name="prancheta_revisao_unica_por_documento"
            ),
            # Só UMA vigente por documento. É a trava que sustenta a pergunta do
            # canteiro: se duas pudessem estar vigentes ao mesmo tempo, "esta é a
            # última?" deixaria de ter resposta e a tela teria de escolher uma —
            # ou seja, adivinhar qual desenho executar.
            models.UniqueConstraint(
                fields=["tenant", "documento"], condition=Q(situacao="vigente"),
                name="prancheta_uma_revisao_vigente",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "situacao"], name="prancheta_rev_situacao_idx"),
        ]

    def __str__(self):
        return f"{self.documento.codigo} {self.revisao}"


class DesenhoProjeto(TenantScopedModel):
    """Um **desenho** dentro da revisão — a folha que se abre, mede e marca.

    Nasceu de medir o acervo real, e corrige uma premissa que estava errada desde
    a PRA.0: *uma revisão não é uma prancha*. O DWG de construtora traz a mesma
    área desenhada na origem e em coordenada UTM (é o `confrontantes.dwg`, com
    duas poligonais a 8,5 milhões de unidades uma da outra), ou traz o *sheet set*
    inteiro montado no modelspace — dezenas de plantas em grade. Emitir tudo numa
    folha só produzia uma página de 469 m × 8,5 km, que nenhum navegador
    rasteriza e onde cada desenho ocupava 0,2% da largura.

    **A escala mora aqui, e não na revisão, porque é aqui que ela é verdade.**
    `escala_valor` é "quantas unidades reais cabem na largura inteira do desenho",
    e as coordenadas de marcação e medição são normalizadas por essa mesma
    largura. Com duas folhas de tamanhos diferentes na mesma revisão, um número
    só serviria para uma delas — e serviria de forma silenciosa, que é como o erro
    de escala vira parede no lugar errado.

    **`caixa` viaja em unidade de DESENHO, não normalizada**, e é isso que
    permite reencontrar o mesmo desenho na revisão seguinte para herdar o nome que
    alguém deu: a folha muda entre revisões (o projetista mexeu no desenho), o
    lugar no terreno não.
    """

    desenho_id = models.AutoField(primary_key=True)
    revisao = models.ForeignKey(
        RevisaoDocumento, on_delete=models.CASCADE, related_name="desenhos",
        verbose_name=_("Revisão"),
    )
    #: 1..N, do maior para o menor. É o `Desenho N` que a tela mostra enquanto
    #: ninguém deu nome — e é estável entre conversões, senão o nome dado ao
    #: "Desenho 2" passaria a apontar para outro desenho no reprocessamento.
    ordem = models.PositiveSmallIntegerField(verbose_name=_("Ordem"))
    #: **O nome é do usuário, e vazio é o estado normal.** Guardar "Desenho 1"
    #: como valor de fábrica tornaria impossível distinguir o rótulo automático de
    #: um nome que alguém escolheu — e a herança entre revisões passaria a
    #: propagar um rótulo que ninguém pediu.
    nome = models.CharField(max_length=120, blank=True, verbose_name=_("Nome dado ao desenho"))
    caixa = models.JSONField(default=dict, blank=True, verbose_name=_("Envolvente (unidades de desenho)"))
    #: A ponte de volta à coordenada do CAD — `{"origem_x","origem_y","por_folha"}`.
    #:
    #: A `caixa` diz onde o desenho está; **isto diz como converter qualquer
    #: ponto da folha na coordenada que o AutoCAD mostraria**, que é o único
    #: número comparável com o arquivo de origem. Vazio para folha antiga (a
    #: medida nasceu depois) e para motor que não é de vetor — e vazio é resposta:
    #: a tela mostra as réguas dela e não finge coordenada de desenho.
    mundo = models.JSONField(default=dict, blank=True, verbose_name=_("Coordenada de desenho"))
    tracos = models.PositiveIntegerField(default=0, verbose_name=_("Traços"))

    # -- escala (o bloco que era da revisão, agora onde ele é verdade) ---------
    # A semântica é a da PRA.3/3b, sem mudança: um DXF/DWG declara a unidade no
    # cabeçalho (`$INSUNITS`) e o motor a extrai; PDF e foto não declaram nada e
    # aí alguém calibra sobre uma cota conhecida. `escala_origem` diz qual dos
    # dois caminhos produziu o número, e define a precedência.
    escala_valor = models.FloatField(
        null=True, blank=True, verbose_name=_("Unidades reais na largura do desenho"),
    )
    escala_unidade = models.CharField(max_length=4, default="m", blank=True, verbose_name=_("Unidade"))
    escala_referencia = models.JSONField(default=dict, blank=True, verbose_name=_("Referência da calibração"))
    escala_origem = models.CharField(
        max_length=10, choices=RevisaoDocumento.OrigemEscala.choices, blank=True, default="",
        verbose_name=_("Procedência da escala"),
    )
    escala_calibrada_por = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="desenhos_projeto_calibrados", verbose_name=_("Calibrada por"),
    )
    escala_calibrada_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Calibrada em"))

    # De qual desenho da revisão anterior este herdou o nome. Guardado para a
    # herança ser **auditável**: nome que aparece sozinho numa revisão nova, sem
    # dizer de onde veio, é indistinguível de nome que alguém digitou ali.
    herdado_de = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="herdeiros", verbose_name=_("Herdou o nome de"),
    )
    renomeado_por = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="desenhos_projeto_renomeados", verbose_name=_("Renomeado por"),
    )
    renomeado_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Renomeado em"))
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Desenho de projeto")
        verbose_name_plural = _("Desenhos de projeto")
        ordering = ["revisao", "ordem"]
        constraints = [
            models.UniqueConstraint(
                fields=["revisao", "ordem"], name="prancheta_desenho_ordem_por_revisao"
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "revisao"], name="prancheta_desenho_revisao_idx"),
        ]

    def __str__(self):
        return f"{self.revisao_id} · {self.rotulo}"

    @property
    def rotulo(self) -> str:
        """O que a tela escreve: o nome de quem nomeou, ou o rótulo automático.

        `Traço solto` para o aglomerado de um registro só — a distinção que
        separa "o outro desenho" de "o que ficou para trás" sem obrigar ninguém a
        abrir os dois para descobrir.
        """
        if self.nome:
            return self.nome
        return "Traço solto" if self.tracos == 1 else f"Desenho {self.ordem}"

    @property
    def tem_escala(self) -> bool:
        """Se dá para converter medida em metro nesta folha.

        Falso é estado normal e visível: a tela mede assim mesmo e mostra o
        resultado **em fração da largura**, dizendo que não há escala.
        """
        return bool(self.escala_valor and self.escala_valor > 0)

    @property
    def pode_derivar_escala(self) -> bool:
        """Se o motor pode publicar aqui a escala que leu do desenho.

        **A calibração humana é soberana** — a mesma regra do pin `exata` do
        MAP.6. Quem foi conferir uma cota sabe o que o cabeçalho não sabe, e uma
        reconversão que sobrescrevesse esse trabalho mudaria em silêncio o valor
        de toda medida já anotada no canteiro.
        """
        return self.escala_origem != RevisaoDocumento.OrigemEscala.CALIBRADA


class DerivadaProjeto(TenantScopedModel):
    """O produto da conversão — vazia até o PRA.1.

    Três consequências de desenho moram nesta tabela:

    - **a chave inclui o motor**, então as duas derivadas do mesmo DWG (livre e
      premium) coexistem — é o que faz o upgrade de plano melhorar a derivada
      sem invalidar a antiga, e o downgrade não apagar nada (planta §4.1);
    - **a versão do motor é carimbada**, então motor novo invalida por
      comparação, sem flag manual;
    - **a falha é dado**: estado e motivo ficam aqui e aparecem na tela. Em
      especial, DWG que o motor livre não abre precisa dizer *"exige o motor de
      alta fidelidade"* — a régua de dados honestos vale para o erro também, e
      um upsell honesto não é "falha na conversão".
    """

    class Tipo(models.TextChoices):
        VETOR_2D = "vetor_2d", _("Vetor 2D (SVG/tiles)")
        MODELO_3D = "modelo_3d", _("Modelo 3D (Fragments/glTF)")
        MINIATURA = "miniatura", _("Miniatura")

    class Estado(models.TextChoices):
        PENDENTE = "pendente", _("Aguardando conversão")
        LENDO = "lendo", _("Lendo o arquivo")
        CONVERTENDO = "convertendo", _("Convertendo")
        #: PRA.11 — passou do turno, gravou o que ficou pronto e **voltou para o
        #: fim da fila**. Estado próprio e não `convertendo` porque as duas
        #: frases são diferentes na tela: "convertendo" promete movimento agora,
        #: e aqui o arquivo está parado esperando a vez de novo. Sem a distinção,
        #: quem olha uma prancha de 40 MB veria "convertendo" por meia hora sem
        #: saber que ela já tem 12 folhas prontas para abrir.
        RETOMANDO = "retomando", _("Na fila para continuar")
        PRONTO = "pronto", _("Pronto")
        ERRO = "erro", _("Erro")

    class MotivoErro(models.TextChoices):
        """Por que falhou — e a distinção que importa são as duas primeiras, que
        é fácil confundir e caro trocar:

        - `motor_insuficiente` não é defeito, é **limite de plano**: o arquivo do
          cliente exige o motor de alta fidelidade, e a tela tem de oferecer o
          upgrade em vez de um "tente novamente" que nunca vai funcionar;
        - `motor_indisponivel` é problema **nosso**: o motor não está nesta
          imagem (o `dwg2dxf` do LibreDWG não é empacotado pelo Debian e entra
          por build stage — ver `motores/dwg.py`). Mandar comprar um plano melhor
          por causa de um binário que esquecemos de instalar venderia ao cliente
          uma solução que não resolve o problema dele.

        **Os três últimos não são de ninguém** (PRA.1b), e nasceram da remedição
        do D42: o arquivo não tem desenho, a geometria mora em XREF que não subiu
        ou o DWG não traz miniatura embutida. Antes os três liam "falha interna do
        motor" — confissão de um defeito que não existe, e linha na fila do que
        *nós* consertamos que ninguém jamais consertaria. Só `referencia_ausente`
        é acionável, e por quem enviou: reenviar com as referências.
        """

        MOTOR_INSUFICIENTE = "motor_insuficiente", _("Exige o motor de alta fidelidade")
        MOTOR_INDISPONIVEL = "motor_indisponivel", _("Motor não instalado neste servidor")
        ARQUIVO_CORROMPIDO = "arquivo_corrompido", _("Arquivo ilegível ou corrompido")
        VERSAO_NAO_SUPORTADA = "versao_nao_suportada", _("Versão do formato não suportada")
        TEMPO_EXCEDIDO = "tempo_excedido", _("Tempo de conversão excedido")
        FALHA_MOTOR = "falha_motor", _("Falha interna do motor")
        DESENHO_VAZIO = "desenho_vazio", _("O arquivo não tem desenho dentro")
        REFERENCIA_AUSENTE = "referencia_ausente", _("Referências externas não enviadas")
        SEM_PREVIEW = "sem_preview", _("O arquivo não traz miniatura embutida")
        RECURSO_EXCEDIDO = "recurso_excedido", _("Passou do limite de processamento")

    #: Motivos em que **o problema está no arquivo** — nem defeito do motor, nem
    #: limite de plano. A fila de decisão os tira do balde "a consertar", senão
    #: ele cresce com linha que nenhum conserto nosso resolve (ver `MotivoErro`).
    #:
    #: Ter o problema no arquivo não quer dizer que ninguém aja: o
    #: `referencia_ausente` é resolvido por **quem enviou**, reenviando com os
    #: XREF. Os outros dois não pedem ação de ninguém. Quem separa esses dois
    #: graus é a fila (`views.acervo`), não este conjunto.
    MOTIVOS_DO_ARQUIVO = frozenset({"desenho_vazio", "referencia_ausente", "sem_preview"})

    derivada_id = models.AutoField(primary_key=True)
    revisao = models.ForeignKey(
        RevisaoDocumento, on_delete=models.CASCADE, related_name="derivadas",
        verbose_name=_("Revisão"),
    )
    # Qual desenho da revisão esta derivada mostra. **Nulo é o caso legítimo e
    # comum**: miniatura de PDF e modelo 3D não têm folha separável, e a derivada
    # é do arquivo inteiro. Preenchido, cada desenho tem a sua — é o que faz o
    # `confrontantes` abrir como duas pranchas de 1,1 m em vez de uma de 8,5 km.
    desenho = models.ForeignKey(
        DesenhoProjeto, null=True, blank=True, on_delete=models.CASCADE,
        related_name="derivadas", verbose_name=_("Desenho"),
    )
    tipo = models.CharField(max_length=10, choices=Tipo.choices, verbose_name=_("Tipo de derivada"))
    motor = models.CharField(max_length=14, choices=MOTOR_CHOICES, verbose_name=_("Motor"))
    motor_versao = models.CharField(max_length=40, blank=True, verbose_name=_("Versão do motor"))

    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.PENDENTE, verbose_name=_("Estado"),
    )
    arquivo = models.FileField(upload_to="prancheta/derivadas/%Y/%m/", null=True, blank=True, verbose_name=_("Arquivo derivado"))
    tamanho_bytes = models.PositiveBigIntegerField(default=0, verbose_name=_("Tamanho (bytes)"))

    # -- snap de medição (PRA.10) ---------------------------------------------
    # **Arquivo separado, e não uma coluna binária.** O sidecar mediano tem 605
    # KB e a cauda medida chega a 5 MB (`docs/medicoes/custo-snap.md`); dentro da
    # tabela isso entraria em TOAST e viria junto em toda listagem de derivada
    # que esquecesse um `defer()`. Como arquivo, ele é servido direto pelo mesmo
    # storage do SVG e o navegador o cacheia sozinho.
    snap = models.FileField(
        upload_to="prancheta/snap/%Y/%m/", null=True, blank=True,
        verbose_name=_("Índice de snap"),
    )
    #: Quantos pontos o índice tem. Zero = esta folha não tem snap, seja porque o
    #: plano não paga, porque o formato não rende geometria (PDF, imagem) ou
    #: porque a extração falhou — a memória de conversão distingue os três.
    snap_pontos = models.PositiveIntegerField(default=0, verbose_name=_("Pontos de snap"))
    #: O teto do plano cortou o índice. A tela precisa disto para dizer "snap
    #: parcial" e oferecer o pacote: sem a bandeira, a mira que não gruda num
    #: canto da prancha se lê como defeito, e não como limite contratado.
    snap_truncado = models.BooleanField(default=False, verbose_name=_("Snap parcial"))
    erro_motivo = models.CharField(
        max_length=22, choices=MotivoErro.choices, blank=True, verbose_name=_("Motivo do erro"),
    )
    erro_detalhe = models.TextField(blank=True, verbose_name=_("Detalhe do erro"))

    # SHA-256 do arquivo de ORIGEM no momento em que esta derivada foi gerada.
    # Junto de `motor_versao` é a chave de idempotência do pipeline (PRA.1): a
    # dupla que ainda bate é pulada, qualquer outra reconverte. O hash da revisão
    # é imutável (arquivo write-once, §9), então na prática quem invalida é o
    # motor — subir o `ezdxf` desatualiza o acervo convertido por comparação, sem
    # flag manual e sem migration de dados.
    hash_origem = models.CharField(max_length=64, blank=True, verbose_name=_("SHA-256 da origem"))
    # Memória de conversão (planta §5): o que o motor conseguiu ler — versão do
    # DWG, schema do IFC, se o DXF precisou de reparo. É o insumo do
    # `medir_cobertura_dwg` (§4.1) e o que dá ao projetista uma resposta melhor
    # que "deu erro".
    memoria = models.JSONField(default=dict, blank=True, verbose_name=_("Memória de conversão"))

    # -- retomada entre voltas à fila (PRA.11) --------------------------------
    # **Moram na linha que a FILA carrega**, que é a mesma em toda passada: o
    # `converter_derivada` recebe um `derivada_id` e o reenfileira com ele. Essa
    # linha vira a folha 1 na primeira passada e mantém o pk, então o progresso
    # não precisa de tabela própria nem de uma segunda chave para se reencontrar.
    #
    # Ficam como colunas e não dentro de `memoria` porque não são memória de
    # conversão: `memoria` responde "o que o motor conseguiu ler deste arquivo" e
    # é lida pelo `medir_cobertura_dwg`; isto é estado de agendamento, e misturar
    # os dois faria a telemetria de cobertura somar campos que não descrevem o
    # arquivo.
    retomada_grupos = models.PositiveIntegerField(
        default=0, verbose_name=_("Aglomerados já processados"),
    )
    retomada_desenhos = models.PositiveIntegerField(
        default=0, verbose_name=_("Folhas já emitidas"),
    )
    #: Quantos aglomerados ainda faltam, como a última passada os viu. É o que a
    #: tela mostra ("12 de 40 folhas") e o que distingue "parou porque acabou" de
    #: "parou porque o turno acabou".
    retomada_restam = models.PositiveIntegerField(
        default=0, verbose_name=_("Aglomerados restantes"),
    )
    retomada_vazios = models.PositiveIntegerField(
        default=0, verbose_name=_("Aglomerados sem traço já descartados"),
    )
    retomada_registros_vazios = models.PositiveIntegerField(
        default=0, verbose_name=_("Registros nos aglomerados sem traço"),
    )
    #: Segundos somados de TODAS as passadas deste arquivo. É o teto que faz a
    #: plataforma desistir (`PRANCHETA_CONVERSAO_TOTAL_SEGUNDOS`), e é de tempo e
    #: não de número de voltas porque o que a máquina paga é segundo de CPU —
    #: contar voltas mediria a nossa política, não o custo.
    retomada_segundos = models.FloatField(
        default=0.0, verbose_name=_("Segundos acumulados de conversão"),
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    concluido_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Concluído em"))

    class Meta:
        verbose_name = _("Derivada de projeto")
        verbose_name_plural = _("Derivadas de projeto")
        ordering = ["revisao", "tipo"]
        constraints = [
            # Sem `tenant` na chave de propósito: `revisao` já é tenant-scoped e a
            # FK-pai amarra o tenant. É o mesmo caso dos `unique_together` sobre
            # FKs que a Fase 8.3 manteve (ex.: `(obra, nome_etapa)`).
            #
            # **São duas porque o Postgres trata NULL como distinto de NULL.** Uma
            # chave única de quatro colunas com `desenho` nulo não travaria nada
            # justamente no caso da miniatura e do 3D, e a idempotência do
            # pipeline (que é `get_or_create` sobre esta chave) passaria a criar
            # uma derivada nova a cada reconversão — vazando arquivo no storage do
            # cliente a cada rodada.
            models.UniqueConstraint(
                fields=["revisao", "tipo", "motor"], condition=Q(desenho__isnull=True),
                name="prancheta_derivada_unica_por_motor",
            ),
            models.UniqueConstraint(
                fields=["revisao", "tipo", "motor", "desenho"], condition=Q(desenho__isnull=False),
                name="prancheta_derivada_unica_por_desenho",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "estado"], name="prancheta_deriv_estado_idx"),
        ]

    def __str__(self):
        return f"{self.revisao_id} · {self.tipo} ({self.motor})"


# ===========================================================================
# PRA.3 — marcar e medir
# ===========================================================================
# Aqui o módulo deixa de mostrar e passa a **resolver**: até a PRA.2 a Prancheta
# respondia "qual desenho vale"; daqui em diante ela carrega a pergunta de volta
# — *"esta viga não bate com a alvenaria, e agora?"*.
#
# **O vocabulário é o do BCF (BuildingSMART), não um nosso**, e isso é a decisão
# central da fatia. Tópico, comentário e ponto de vista têm os campos que o
# formato define, com os mesmos nomes e o mesmo GUID, porque o valor da marcação
# está em ela abrir no Revit, no Navisworks, no Solibri e no BIMcollab do
# projetista. Um modelo "mais limpo" e nosso obrigaria a um de-para na
# exportação, e todo de-para perde o que não coube.
#
# **O que o BCF não cobre, e por isso é nosso e está declarado assim:** o BCF é
# centrado em modelo 3D — tópico aponta para componente IFC e câmera no espaço.
# A marcação feita sobre uma prancha 2D não tem nem um nem outro. O que ela tem
# é uma âncora na folha, que guardamos em `Marcacao.ancora` e exportamos como
# **snapshot** (a imagem do trecho) + `ReferenceLink` de volta para cá. Ou seja:
# título, descrição, situação, prioridade, responsável, prazo, comentários e
# imagem atravessam para o escritório; a coordenada na folha, não. Está escrito
# em `bcf.py` e na planta §13 para ninguém descobrir isso na primeira exportação.


class Marcacao(TenantScopedModel):
    """Um tópico BCF: o que precisa ser resolvido neste desenho.

    Pendura-se na **revisão**, não no documento, de propósito. A marcação é
    sobre um desenho específico — quando a R02 chega, o que se apontou na R01
    não migra sozinho, porque pode já não existir. O que o sistema faz é
    **avisar**: marcação aberta em revisão superada é linha da fila de decisão
    do cockpit, não um registro que desaparece nem um que finge continuar
    válido.
    """

    class Tipo(models.TextChoices):
        """`TopicType` do BCF. Vocabulário aberto no padrão; estes são os que o
        canteiro usa e que os visualizadores de mercado reconhecem."""

        PROBLEMA = "Issue", _("Problema")
        SOLICITACAO = "Request", _("Solicitação")
        OBSERVACAO = "Comment", _("Observação")
        INTERFERENCIA = "Clash", _("Interferência")
        DUVIDA = "Inquiry", _("Dúvida")

    class Situacao(models.TextChoices):
        """`TopicStatus` do BCF, nos valores que o padrão usa em inglês.

        O valor guardado é o do BCF e o rótulo é em português: gravar "Aberta" e
        traduzir na exportação criaria um de-para que a primeira marcação
        importada de fora quebraria — o arquivo do projetista vem com `Open`.
        """

        ABERTA = "Open", _("Aberta")
        EM_ANDAMENTO = "In Progress", _("Em andamento")
        RESOLVIDA = "Resolved", _("Resolvida")
        FECHADA = "Closed", _("Fechada")

    # As duas que tiram a marcação da fila. Fechada é o fim; resolvida é "o
    # projetista respondeu" — quem apontou ainda confere. Separar as duas é o
    # que impede a fila de esvaziar sozinha do lado errado.
    SITUACOES_ABERTAS = ("Open", "In Progress")

    class Prioridade(models.TextChoices):
        BAIXA = "Low", _("Baixa")
        NORMAL = "Normal", _("Normal")
        ALTA = "High", _("Alta")
        CRITICA = "Critical", _("Crítica")

    class Origem(models.TextChoices):
        SISTEMA = "sistema", _("Criada aqui")
        BCF = "bcf", _("Importada de BCF")

    marcacao_id = models.AutoField(primary_key=True)
    # **O GUID é a identidade fora daqui.** É por ele que a marcação exportada,
    # respondida no Solibri e reimportada volta a ser a MESMA linha em vez de
    # virar uma segunda cópia a cada ida e volta. Por isso é gerado na criação e
    # **preservado** na importação — nunca regerado.
    guid = models.UUIDField(default=uuid.uuid4, editable=False, verbose_name=_("GUID (BCF)"))
    revisao = models.ForeignKey(
        RevisaoDocumento, on_delete=models.CASCADE, related_name="marcacoes",
        verbose_name=_("Revisão"),
    )
    # Em **qual desenho** da revisão o pino foi fincado. Nulo quando não há folha
    # onde ancorar (BCF de modelo 3D, PDF) e nas marcações anteriores a esta
    # fatia: a âncora delas está no espaço da folha única de antes, que deixou de
    # existir. A tela as mostra na conversa **sem pino**, dizendo por quê —
    # reposicioná-las por conta própria seria mover o dedo de quem apontou.
    desenho = models.ForeignKey(
        DesenhoProjeto, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="marcacoes", verbose_name=_("Desenho"),
    )

    titulo = models.CharField(max_length=200, verbose_name=_("Título"))
    descricao = models.TextField(blank=True, verbose_name=_("Descrição"))
    tipo = models.CharField(
        max_length=12, choices=Tipo.choices, default=Tipo.PROBLEMA, verbose_name=_("Tipo"),
    )
    situacao = models.CharField(
        max_length=12, choices=Situacao.choices, default=Situacao.ABERTA, verbose_name=_("Situação"),
    )
    prioridade = models.CharField(
        max_length=8, choices=Prioridade.choices, default=Prioridade.NORMAL,
        verbose_name=_("Prioridade"),
    )
    rotulos = models.JSONField(default=list, blank=True, verbose_name=_("Rótulos (BCF Labels)"))
    prazo = models.DateField(null=True, blank=True, verbose_name=_("Prazo"))

    # **Responsável tem duas formas, e as duas existem porque o mundo é assim.**
    # O `AssignedTo` do BCF é um e-mail solto — o projetista costuma ser
    # escritório terceirizado sem login aqui (mesma razão de `projetista` ser
    # texto em `DocumentoProjeto`). Quando a pessoa TEM login, a FK é o que faz
    # "atribuídas a mim" funcionar na fila de decisão; quando não tem, o e-mail
    # ainda atravessa para o BCF e a marcação chega a quem precisa.
    responsavel = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="marcacoes_prancheta", verbose_name=_("Responsável (com login)"),
    )
    responsavel_email = models.EmailField(blank=True, verbose_name=_("Responsável (e-mail)"))

    criado_por = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="marcacoes_prancheta_criadas", verbose_name=_("Criada por"),
    )
    # `CreationAuthor` do BCF quando a marcação veio de fora: a pessoa que a
    # escreveu não tem usuário aqui, e apagar o nome dela na importação faria o
    # histórico atribuir a autoria a quem apenas subiu o arquivo.
    autor_nome = models.CharField(max_length=180, blank=True, verbose_name=_("Autor (externo)"))

    # `default=timezone.now` e NÃO `auto_now_add`: na importação esta data é a do
    # BCF — quando o projetista de fato apontou o problema. É a lição do **L7**
    # (`Transacao.data_transacao` era `auto_now_add` e o pagamento caía no mês
    # errado): carimbo de chegada e data do fato são coisas diferentes, e quem
    # tem `auto_now_add` só consegue guardar a primeira.
    criado_em = models.DateTimeField(default=timezone.now, verbose_name=_("Criada em"))
    atualizado_em = models.DateTimeField(auto_now=True)
    resolvido_por = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="marcacoes_prancheta_resolvidas", verbose_name=_("Resolvida por"),
    )
    resolvido_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Resolvida em"))

    origem = models.CharField(
        max_length=8, choices=Origem.choices, default=Origem.SISTEMA, verbose_name=_("Origem"),
    )
    # Onde na folha. Normalizada pela LARGURA do desenho ({"x": 0.42, "y": 0.31})
    # — ver `Medicao.pontos`. Vazia quando a marcação veio de um BCF de modelo
    # 3D, onde o lugar é a câmera do ponto de vista e não um ponto na folha.
    ancora = models.JSONField(default=dict, blank=True, verbose_name=_("Âncora na folha"))

    class Meta:
        verbose_name = _("Marcação")
        verbose_name_plural = _("Marcações")
        ordering = ["-criado_em"]
        constraints = [
            # `tenant` na chave porque o GUID vem de FORA: dois clientes podem
            # importar o mesmo BCF de um projetista que trabalha para os dois, e
            # um unique global transformaria isso em erro de gravação para o
            # segundo — ou, pior, em colisão entre acervos.
            models.UniqueConstraint(fields=["tenant", "guid"], name="prancheta_marcacao_guid_unico"),
        ]
        indexes = [
            models.Index(fields=["tenant", "situacao"], name="prancheta_marc_situacao_idx"),
            models.Index(fields=["tenant", "responsavel"], name="prancheta_marc_resp_idx"),
        ]

    def __str__(self):
        return f"{self.titulo} ({self.get_situacao_display()})"

    @property
    def aberta(self) -> bool:
        return self.situacao in self.SITUACOES_ABERTAS


def caminho_snapshot(instance, filename):
    """Mesma lógica do arquivo da revisão: tenant no caminho para expurgo e cota
    por cliente serem operação de diretório, não varredura."""
    return f"prancheta/{instance.tenant_id}/marcacoes/{filename}"


class PontoDeVista(TenantScopedModel):
    """O `Viewpoint` do BCF — como estava a tela quando alguém apontou o problema.

    Existe como tabela e não como campo da marcação porque o BCF permite vários
    por tópico, e o comentário pode referenciar **um deles**. Guardar só o
    primeiro faria toda ida e volta com o escritório perder ponto de vista — e
    quem exporta um BCF que perde dado a cada ciclo desiste de exportar.

    Duas metades, e nenhuma das duas serve para as duas dimensões:

    - `camera` é o bloco 3D do padrão (`OrthogonalCamera`/`PerspectiveCamera`),
      preservado como veio para o round-trip ser fiel mesmo no que não sabemos
      desenhar aqui;
    - `snapshot` é a imagem — e é ela que carrega a marcação 2D para fora,
      porque o padrão não tem onde guardar um ponto numa folha.
    """

    ponto_de_vista_id = models.AutoField(primary_key=True)
    guid = models.UUIDField(default=uuid.uuid4, editable=False, verbose_name=_("GUID (BCF)"))
    marcacao = models.ForeignKey(
        Marcacao, on_delete=models.CASCADE, related_name="pontos_de_vista",
        verbose_name=_("Marcação"),
    )
    camera = models.JSONField(default=dict, blank=True, verbose_name=_("Câmera (BCF)"))
    snapshot = models.ImageField(
        upload_to=caminho_snapshot, null=True, blank=True, verbose_name=_("Snapshot"),
    )
    criado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = _("Ponto de vista")
        verbose_name_plural = _("Pontos de vista")
        ordering = ["ponto_de_vista_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "guid"], name="prancheta_ponto_vista_guid_unico"
            ),
        ]

    def __str__(self):
        return f"ponto de vista {self.guid}"


class ComentarioMarcacao(TenantScopedModel):
    """O `Comment` do BCF — a conversa sobre o tópico.

    É o que faz a marcação ser um laço e não um recado: o campo aponta, o
    projetista responde, o campo confere. Sem isto o BCF exportado sairia com um
    título e voltaria com um título.
    """

    comentario_id = models.AutoField(primary_key=True)
    guid = models.UUIDField(default=uuid.uuid4, editable=False, verbose_name=_("GUID (BCF)"))
    marcacao = models.ForeignKey(
        Marcacao, on_delete=models.CASCADE, related_name="comentarios", verbose_name=_("Marcação"),
    )
    texto = models.TextField(verbose_name=_("Comentário"))
    autor = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="comentarios_marcacao", verbose_name=_("Autor (com login)"),
    )
    autor_nome = models.CharField(max_length=180, blank=True, verbose_name=_("Autor (externo)"))
    ponto_de_vista = models.ForeignKey(
        PontoDeVista, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="comentarios", verbose_name=_("Ponto de vista"),
    )
    # Data do BCF na importação — mesma razão de `Marcacao.criado_em` (o L7).
    criado_em = models.DateTimeField(default=timezone.now, verbose_name=_("Criado em"))

    class Meta:
        verbose_name = _("Comentário de marcação")
        verbose_name_plural = _("Comentários de marcação")
        ordering = ["criado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "guid"], name="prancheta_comentario_guid_unico"
            ),
        ]

    def __str__(self):
        return self.texto[:60]


class Medicao(TenantScopedModel):
    """Uma medida tirada sobre a prancha.

    **O valor é carimbado com a escala do momento** (`escala_aplicada`), como a
    linha do orçamento guarda o snapshot do item (ORC.1). Recalibrar a prancha
    depois não pode reescrever silenciosamente uma medida que alguém já anotou e
    levou para o canteiro — o que a tela faz é mostrar que aquela medida foi
    tirada com outra escala, e oferecer refazê-la.

    Sem escala calibrada a medição continua existindo, com `escala_aplicada`
    nula: o valor sai em **fração da largura da prancha**, e a tela diz isso.
    Guardar zero, ou converter para metro com um chute, seria pior que não medir.
    """

    class Tipo(models.TextChoices):
        DISTANCIA = "distancia", _("Distância")
        AREA = "area", _("Área")

    medicao_id = models.AutoField(primary_key=True)
    revisao = models.ForeignKey(
        RevisaoDocumento, on_delete=models.CASCADE, related_name="medicoes",
        verbose_name=_("Revisão"),
    )
    # Sobre qual desenho a medida foi tirada — e, com ele, com que régua. Nulo só
    # nas medições anteriores a esta fatia, que ficam com o valor que tinham:
    # recalcular seria reescrever um número que alguém já anotou e levou para o
    # canteiro, exatamente o que `escala_aplicada` existe para impedir.
    desenho = models.ForeignKey(
        DesenhoProjeto, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="medicoes", verbose_name=_("Desenho"),
    )
    # Medida que virou apontamento: "esta parede está 12 cm fora do projeto".
    marcacao = models.ForeignKey(
        Marcacao, null=True, blank=True, on_delete=models.SET_NULL, related_name="medicoes",
        verbose_name=_("Marcação"),
    )
    tipo = models.CharField(
        max_length=9, choices=Tipo.choices, default=Tipo.DISTANCIA, verbose_name=_("Tipo"),
    )
    # Vértices em coordenada **normalizada pela largura** do desenho: x ∈ [0,1] e
    # y ∈ [0, altura/largura]. Normalizar os dois eixos por eixos diferentes
    # (o óbvio) distorceria o aspecto e faria a mesma diagonal medir diferente
    # conforme a folha — dividir os dois pela largura preserva a proporção.
    pontos = models.JSONField(default=list, verbose_name=_("Vértices (normalizados)"))
    # O resultado JÁ na unidade real quando há escala; em fração da largura
    # quando não há. `escala_aplicada` é o que distingue os dois casos.
    valor = models.FloatField(verbose_name=_("Valor"))
    unidade = models.CharField(max_length=4, blank=True, verbose_name=_("Unidade"))
    escala_aplicada = models.FloatField(
        null=True, blank=True, verbose_name=_("Escala usada (unidades na largura)"),
    )
    rotulo = models.CharField(max_length=120, blank=True, verbose_name=_("Rótulo"))
    # **O que a medida dizia antes da recalibração** (decisão do dono, 15/08/2026).
    #
    # Até aqui, recalibrar deixava a medida antiga como estava e a marcava
    # `desatualizada` — tracejada na tela —, para não reescrever um número que
    # alguém pudesse ter anotado e levado para o canteiro. O uso mostrou o
    # contrário: quem recalibra faz isso PORQUE o número estava errado, e deixá-lo
    # na tela com outra régua entrega o erro com aparência de medida conferida.
    #
    # Agora a medida é recalculada a partir dos `pontos`, que são normalizados e
    # portanto independentes de régua — mas o valor anterior fica AQUI. Não é
    # reescrita silenciosa: é conversão com recibo, e quem conferir a caderneta
    # do canteiro consegue reencontrar de onde veio o número velho.
    valor_anterior = models.JSONField(
        default=list, blank=True, verbose_name=_("Valores antes de recalibrar"),
    )

    criado_por = models.ForeignKey(
        "nucleo.Usuario", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="medicoes_prancheta", verbose_name=_("Medida por"),
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Medição")
        verbose_name_plural = _("Medições")
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["tenant", "revisao"], name="prancheta_medicao_revisao_idx"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.valor} {self.unidade}".strip()

    @property
    def desatualizada(self) -> bool:
        """A folha foi recalibrada depois desta medida.

        Não é erro: é a informação que impede alguém de comparar duas medidas
        tiradas com réguas diferentes achando que são a mesma régua.

        Compara contra o **desenho**, que é onde a régua mora desde que uma
        revisão passou a poder trazer várias folhas. Medida sem desenho é
        anterior a essa mudança e não tem com que se comparar — dizê-la
        desatualizada seria inventar um veredito.
        """
        return (
            self.escala_aplicada is not None
            and self.desenho_id is not None
            and self.desenho.escala_valor is not None
            and abs(self.escala_aplicada - self.desenho.escala_valor) > 1e-9
        )
