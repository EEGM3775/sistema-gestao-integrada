# backend/funcoesimpexp/models.py
"""IE.0 — a área de conferência e o registro do que saiu.

Generalização do `ImportacaoPreco`/`LinhaImportacao` do ORC.5b: onde lá havia
campos de preço (`codigo`, `custo_unitario`, `grupo`), aqui há um `valores` JSON
governado pelas colunas que o recurso declarou. O resto da máquina — status,
veredito por linha, linha bruta preservada — é o mesmo, porque o mesmo é o que
resolve o problema.

**RLS fail-closed em todas.** Inclusive na área de conferência: ela guarda o
arquivo que a empresa subiu *antes* de qualquer decisão, e arquivo em conferência
é o dado mais cru que existe no sistema — carteira de clientes, tabela de custo,
folha. Vazar entre tenants ali é vazar tudo.
"""
from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from nucleo.tenancy import TenantScopedModel


class Importacao(TenantScopedModel):
    """Um lote de importação — e, depois de aplicado, a unidade que se desfaz (R6)."""

    class Status(models.TextChoices):
        # `LENDO` só existe no caminho assíncrono (R10): é o intervalo entre o
        # upload responder e o worker terminar de classificar. Sem um estado
        # próprio, a tela teria de escolher entre mentir ("em conferência", com
        # zero linhas) e mostrar erro — as duas coisas fazem o usuário reenviar.
        LENDO = "lendo", _("Lendo o arquivo")
        CONFERINDO = "conferindo", _("Em conferência")
        APLICADA = "aplicada", _("Aplicada")
        DESCARTADA = "descartada", _("Descartada")
        DESFEITA = "desfeita", _("Desfeita")
        ERRO = "erro", _("Erro na leitura")

    importacao_id = models.AutoField(primary_key=True)
    # Id do registry (`modulo.recurso`) e não FK: o recurso é declaração em
    # código, não linha de tabela. Guardar o id preserva o histórico mesmo se a
    # declaração for renomeada — e um lote velho apontando para recurso que não
    # existe mais é legível, enquanto uma FK quebrada não seria.
    recurso = models.CharField(max_length=100, db_index=True, verbose_name=_("Recurso"))
    arquivo_nome = models.CharField(max_length=255, blank=True, verbose_name=_("Arquivo"))
    parametros = models.JSONField(
        default=dict, blank=True, verbose_name=_("Parâmetros"),
        help_text=_("De-para manual de colunas e delimitador escolhido."),
    )
    # Para ONDE, dentro do módulo, este lote vai — o banco de preço escolhido, o
    # orçamento de destino. É do módulo, não do motor: o motor só o carrega do
    # pedido até os ganchos, e o recurso o valida (`validar_contexto`).
    #
    # Persistido, e não recalculado na hora de aplicar, porque a conferência é
    # assíncrona por natureza: entre subir o arquivo e clicar em "confirmar"
    # passa-se um café, e o destino escolhido no upload tem de ser o mesmo que
    # recebe as linhas — não o que estiver selecionado na tela depois.
    contexto = models.JSONField(default=dict, blank=True, verbose_name=_("Contexto"))
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.CONFERINDO,
        db_index=True, verbose_name=_("Status"),
    )
    mensagem = models.CharField(max_length=500, blank=True, verbose_name=_("Mensagem"))
    total_linhas = models.PositiveIntegerField(default=0, verbose_name=_("Linhas lidas"))
    total_aplicadas = models.PositiveIntegerField(default=0, verbose_name=_("Linhas aplicadas"))
    # Progresso do caminho assíncrono (R10). Guardado no banco e não no backend de
    # resultado do Celery porque a tela pergunta "como vai a MINHA importação",
    # não "como vai a task X" — e o id da task é detalhe de infraestrutura que o
    # frontend não deve precisar carregar.
    processadas = models.PositiveIntegerField(default=0, verbose_name=_("Linhas processadas"))
    assincrona = models.BooleanField(default=False, verbose_name=_("Processada em job"))
    # O arquivo só é guardado no caminho assíncrono: no síncrono ele é lido em
    # memória e descartado, e guardar por guardar seria acumular dado cru
    # (carteira de clientes, folha) sem ninguém pedir.
    arquivo = models.FileField(
        upload_to="impexp/entrada/%Y/%m/", blank=True, null=True, verbose_name=_("Arquivo"),
    )
    # Rótulo durável, no padrão do AuditLog: o usuário pode ser desativado ou ter
    # o login trocado, e o rastro de quem decidiu a importação não pode sumir com
    # isso.
    usuario_nome = models.CharField(max_length=150, blank=True, verbose_name=_("Decidido por"))
    criada_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criada em"))
    decidida_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Decidida em"))

    class Meta:
        verbose_name = _("Importação")
        verbose_name_plural = _("Importações")
        ordering = ("-criada_em",)

    def __str__(self) -> str:
        return f"{self.recurso} · {self.arquivo_nome} ({self.get_status_display()})"

    @property
    def pendente(self) -> bool:
        """Decidível. `LENDO` de fora: aplicar um lote a meio caminho de ser
        classificado gravaria só o pedaço que o worker já tinha materializado."""
        return self.status == self.Status.CONFERINDO

    @property
    def progresso_pct(self) -> int:
        if not self.total_linhas:
            return 100 if self.status != self.Status.LENDO else 0
        return min(100, round(self.processadas * 100 / self.total_linhas))


class LinhaImportacao(TenantScopedModel):
    """Uma linha do arquivo com seu veredito. Nada aqui foi gravado no destino ainda."""

    class Situacao(models.TextChoices):
        NOVA = "nova", _("Nova")
        DUPLICADA = "duplicada", _("Já existe")
        INVALIDA = "invalida", _("Inválida")

    linha_id = models.AutoField(primary_key=True)
    importacao = models.ForeignKey(
        Importacao, on_delete=models.CASCADE, related_name="linhas",
        verbose_name=_("Importação"),
    )
    numero = models.PositiveIntegerField(default=0, verbose_name=_("Linha no arquivo"))
    chave = models.CharField(max_length=200, blank=True, db_index=True, verbose_name=_("Chave"))
    valores = models.JSONField(
        default=dict, blank=True, verbose_name=_("Valores"),
        help_text=_("campo → valor já convertido; Decimal serializado como texto."),
    )
    situacao = models.CharField(
        max_length=10, choices=Situacao.choices, default=Situacao.NOVA,
        verbose_name=_("Situação"),
    )
    motivo = models.CharField(max_length=255, blank=True, verbose_name=_("Motivo"))
    aceita = models.BooleanField(default=True, verbose_name=_("Aceita na conferência"))
    aplicada = models.BooleanField(default=False, verbose_name=_("Aplicada"))
    # A linha como veio do arquivo. Serve à R5 (devolver o erro com o original) e
    # a auditar o próprio extrator — quando um PDF sai torto, é comparando isto
    # com `valores` que se descobre se o erro foi da fonte ou do leitor.
    bruto = models.JSONField(default=list, blank=True, verbose_name=_("Linha original"))
    # O que existia antes desta linha gravar por cima (R6). Vazio em linha nova:
    # desfazer uma criação é apagar.
    estado_anterior = models.JSONField(
        null=True, blank=True, verbose_name=_("Estado anterior"),
    )

    class Meta:
        verbose_name = _("Linha de importação")
        verbose_name_plural = _("Linhas de importação")
        ordering = ("numero", "linha_id")
        indexes = [models.Index(fields=["importacao", "situacao"])]

    def __str__(self) -> str:
        return f"linha {self.numero} · {self.get_situacao_display()}"


class Exportacao(TenantScopedModel):
    """Registro do que saiu do sistema.

    Existe mesmo quando a resposta é síncrona e nenhum arquivo fica guardado: o
    valor da linha é o **rastro**, não o arquivo. Exportação é o momento em que o
    dado deixa o sistema, e a pergunta "quem levou a carteira de clientes embora,
    quando e com que recorte" precisa ter resposta (R12 — o `AuditLog` recebe o
    mesmo evento; aqui fica o detalhe operacional).
    """

    class Status(models.TextChoices):
        # A síncrona nasce PRONTA: ela *é* a resposta do request, e o registro
        # existe só como rastro. Os outros dois estados são do caminho de job.
        PRONTA = "pronta", _("Pronta")
        GERANDO = "gerando", _("Gerando")
        ERRO = "erro", _("Erro na geração")

    exportacao_id = models.AutoField(primary_key=True)
    recurso = models.CharField(max_length=100, db_index=True, verbose_name=_("Recurso"))
    formato = models.CharField(max_length=10, verbose_name=_("Formato"))
    recorte = models.JSONField(default=dict, blank=True, verbose_name=_("Recorte"))
    # Destino, como na importação. Separado do `recorte` de propósito: recorte é
    # filtro da tela e entra no cabeçalho de procedência para o leitor conferir;
    # contexto é para onde a operação aponta dentro do módulo, e misturar os dois
    # faria "banco=12" aparecer como se fosse um filtro que a pessoa escolheu.
    contexto = models.JSONField(default=dict, blank=True, verbose_name=_("Contexto"))
    linhas = models.PositiveIntegerField(default=0, verbose_name=_("Linhas"))
    usuario_nome = models.CharField(max_length=150, blank=True, verbose_name=_("Emitido por"))
    criada_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Emitida em"))
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PRONTA,
        db_index=True, verbose_name=_("Status"),
    )
    mensagem = models.CharField(max_length=500, blank=True, verbose_name=_("Mensagem"))
    # Só o caminho assíncrono materializa arquivo: o síncrono devolve os bytes na
    # resposta e não deixa nada para trás.
    arquivo = models.FileField(
        upload_to="impexp/saida/%Y/%m/", blank=True, null=True, verbose_name=_("Arquivo"),
    )
    # R10 — "link de validade limitada". O arquivo gerado é uma fotografia do
    # recorte no instante em que saiu; mantê-lo para sempre transformaria a pasta
    # de mídia num acervo paralelo de dado sensível, fora da RLS e fora do
    # esquecimento da LGPD (9.D). Expirado, a linha continua (é o rastro da R12);
    # o arquivo é que some.
    expira_em = models.DateTimeField(null=True, blank=True, verbose_name=_("Expira em"))

    class Meta:
        verbose_name = _("Exportação")
        verbose_name_plural = _("Exportações")
        ordering = ("-criada_em",)

    def __str__(self) -> str:
        return f"{self.recurso} → {self.formato} ({self.linhas} linhas)"

    @property
    def expirada(self) -> bool:
        from django.utils import timezone

        return bool(self.expira_em and timezone.now() > self.expira_em)

    @property
    def baixavel(self) -> bool:
        return bool(self.arquivo) and self.status == self.Status.PRONTA and not self.expirada


class MapaColunas(TenantScopedModel):
    """De-para de colunas salvo para reusar (R4).

    Existe por causa da importação **recorrente**: a mesma prefeitura publica a
    mesma planilha torta todo mês, e refazer o de-para à mão a cada vez é onde a
    pessoa erra — não na primeira, quando está prestando atenção, mas na sexta.

    Guarda `campo -> índice da coluna`, não `campo -> nome da coluna`: o nome é
    justamente o que não casou (senão o automático teria resolvido), e a posição
    é o que se manteve estável entre as publicações que motivaram isto.
    """

    mapa_id = models.AutoField(primary_key=True)
    recurso = models.CharField(max_length=100, db_index=True, verbose_name=_("Recurso"))
    nome = models.CharField(max_length=120, verbose_name=_("Nome"))
    mapa = models.JSONField(default=dict, verbose_name=_("De-para"))
    delimitador = models.CharField(max_length=4, blank=True, verbose_name=_("Delimitador"))
    usuario_nome = models.CharField(max_length=150, blank=True, verbose_name=_("Criado por"))
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))

    class Meta:
        verbose_name = _("Mapa de colunas")
        verbose_name_plural = _("Mapas de colunas")
        ordering = ("recurso", "nome")
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "recurso", "nome"], name="impexp_mapa_unico_por_tenant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.recurso} · {self.nome}"
