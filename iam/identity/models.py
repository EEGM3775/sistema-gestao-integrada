"""
Modelo de dados do IAM.

Autoridade única de identidade da plataforma:
- Tenant: a empresa-cliente (fronteira de isolamento multi-tenant).
- Usuario: pertence a um tenant; username é único globalmente (o JWT usa
  `sub`=username e o funcoesODM busca/provisiona o usuário por ele).
- Perfil / Permissao: RBAC intra-tenant.
- Modulo / AssinaturaTenant / AcessoUsuarioModulo: entitlements à la carte.
"""
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from payment.planos import CONFIRMACAO_JANELA_PADRAO_MIN


class Tenant(models.Model):
    class Status(models.TextChoices):
        ATIVO = "ativo", _("Ativo")
        SUSPENSO = "suspenso", _("Suspenso")
        CANCELADO = "cancelado", _("Cancelado")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(_("Nome"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=100, unique=True)
    cnpj = models.CharField(_("CNPJ"), max_length=18, blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ATIVO)
    plano = models.CharField(_("Plano"), max_length=100, blank=True, null=True)
    data_criacao = models.DateTimeField(auto_now_add=True)
    # Remodelagem, fase 1 — o admin desta empresa só entra com segundo fator.
    # É a **volta atrás** da fase (acesso-e-permissoes.md §10.12): desligar aqui
    # devolve o login só com senha aos admins deste tenant, sem deploy. Não
    # alcança o supervisor da plataforma, que é obrigado sempre (ver
    # `segundo_fator.obrigatorio`).
    segundo_fator_obrigatorio = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Tenant")
        verbose_name_plural = _("Tenants")
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.slug})"

    def modulos_ativos(self):
        """Códigos dos módulos que o tenant tem assinatura ativa hoje. Usado para
        impedir que um papel receba permissão de módulo não contratado (escalada)."""
        hoje = timezone.now().date()
        return list(
            AssinaturaTenant.objects.filter(
                tenant_id=self.id, status=AssinaturaTenant.Status.ATIVA, inicio__lte=hoje
            )
            .filter(Q(fim__isnull=True) | Q(fim__gte=hoje))
            .values_list("modulo__codigo", flat=True)
            .distinct()
        )

    def limites_contratados(self) -> dict:
        """O que foi contratado DE FATO, somando as assinaturas ativas.

        `AssinaturaTenant.limites` é por módulo, mas alguns limites são do tenant
        inteiro (seats, teto de requisições). Enquanto o checkout não existe
        (D24), a regra é o **maior valor** entre as assinaturas ativas: nenhum
        cliente deve receber menos do que a mais generosa das linhas que ele
        assinou. Quando o provisionamento automático existir, estes valores serão
        gravados de uma vez e a fusão vira trivial.

        Tem precedência sobre o plano — é o que permite o "Sob Medida" existir
        sem estar declarado em código (ver payment/regras.py).
        """
        hoje = timezone.now().date()
        assinaturas = (
            AssinaturaTenant.objects.filter(
                tenant_id=self.id, status=AssinaturaTenant.Status.ATIVA, inicio__lte=hoje
            )
            .filter(Q(fim__isnull=True) | Q(fim__gte=hoje))
            .values_list("limites", flat=True)
        )
        fundido: dict = {}
        for limites in assinaturas:
            for chave, valor in (limites or {}).items():
                atual = fundido.get(chave)
                if isinstance(valor, int) and isinstance(atual, int):
                    fundido[chave] = max(atual, valor)
                else:
                    fundido.setdefault(chave, valor)
        return fundido


class Permissao(models.Model):
    """Permissão granular, referenciada por código (ex.: 'pode_ver_financeiro')."""

    id = models.AutoField(primary_key=True)
    codename = models.CharField(max_length=100, unique=True)
    nome = models.CharField(max_length=150)

    class Meta:
        verbose_name = _("Permissão")
        verbose_name_plural = _("Permissões")
        ordering = ["codename"]

    def __str__(self):
        return self.codename


class Perfil(models.Model):
    """Papel dentro de um tenant (agrupa permissões). RBAC intra-tenant."""

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="perfis")
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True, null=True)
    permissoes = models.ManyToManyField(Permissao, related_name="perfis", blank=True)

    class Meta:
        verbose_name = _("Perfil")
        verbose_name_plural = _("Perfis")
        ordering = ["nome"]
        unique_together = ("tenant", "nome")

    def __str__(self):
        return f"{self.nome} @ {self.tenant.slug}"


class Modulo(models.Model):
    """Produto/módulo vendável (ex.: 'erp_financeiro', 'crm', 'drone')."""

    id = models.AutoField(primary_key=True)
    codigo = models.SlugField(max_length=50, unique=True)
    nome = models.CharField(max_length=150)
    descricao = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = _("Módulo")
        verbose_name_plural = _("Módulos")
        ordering = ["codigo"]

    def __str__(self):
        return self.codigo


class Usuario(AbstractUser):
    """Usuário da plataforma. Fonte de verdade da identidade."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # D11 — e-mail OBRIGATÓRIO e ÚNICO na plataforma. O `AbstractUser` o traz
    # opcional e duplicável; aqui ele é infraestrutura de segurança, não contato:
    # é por ele que se recupera a senha. Obrigatório porque conta sem e-mail é
    # conta sem caminho de recuperação — o travamento que o D11 existe para
    # eliminar. Único porque "esqueci minha senha" precisa resolver para UMA
    # conta; com duplicata o fluxo fica ambíguo e vira vetor de confusão.
    # (Único GLOBAL, não por tenant: a mesma pessoa não tem conta em duas
    # empresas — decisão de 18/07/2026.)
    email = models.EmailField(_("E-mail"), unique=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="usuarios", null=True, blank=True
    )
    # Admin do próprio tenant (gerencia usuários/perfis/acessos do tenant).
    is_tenant_admin = models.BooleanField(default=False)
    perfis = models.ManyToManyField(Perfil, related_name="usuarios", blank=True)
    # D11 — quando o e-mail desta conta mudou pela última vez. É o que sustenta o
    # cooldown: recuperação de senha fica bloqueada por
    # PASSWORD_RESET_COOLDOWN_TROCA_EMAIL_HORAS após uma troca, para que o aviso
    # enviado ao endereço ANTIGO chegue antes de o endereço novo poder receber um
    # token. Sem essa carência, trocar o e-mail e pedir reset em seguida é
    # takeover em dois passos.
    email_alterado_em = models.DateTimeField(null=True, blank=True, editable=False)
    # Remodelagem, fase 1 — quanto tempo depois de provar quem é a pessoa pode
    # fazer um ato grave sem provar de novo (acesso-e-permissoes.md §10.5).
    # Escolha dela, na tela de perfil; o padrão e a faixa são do dono
    # (`payment/planos.py` §5.5o). Quem cobra a faixa é o endpoint, não o banco.
    janela_confirmacao_min = models.PositiveSmallIntegerField(
        default=CONFIRMACAO_JANELA_PADRAO_MIN
    )

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        verbose_name = _("Usuário")
        verbose_name_plural = _("Usuários")
        ordering = ["username"]

    def __str__(self):
        return self.username

    def modulos_efetivos(self):
        """
        Códigos dos módulos que este usuário pode efetivamente acessar.

        Três réguas diferentes, e a diferença entre elas é o desenho de acesso da
        plataforma inteira:

        - **usuário comum** — interseção entre as assinaturas ativas do tenant e
          o `AcessoUsuarioModulo` concedido a ele;
        - **admin do tenant** — todos os módulos que a **empresa dele** assina.
          Ele manda na própria casa, e não além dela: módulo não contratado
          continua fechado;
        - **supervisor da plataforma** (`is_superuser`) — **todos os módulos do
          catálogo, contratados ou não** *(decisão do dono, 22/08/2026:
          "ele não pode ter restrição a nenhum módulo")*. Ele é o teste supremo
          do sistema, e um teste supremo que só alcança o que alguém comprou não
          testa o produto — testa a assinatura. É por isso que a régua dele não
          passa pelo `AssinaturaTenant`: ela é a única das três que ignora o
          entitlement, porque o entitlement é **do cliente**, e supervisionar não
          é ser cliente.

        **O que isto NÃO é** — e a distinção é a mesma da decisão anterior do
        dono, no mesmo dia: alcançar todo módulo não é alcançar o dado de toda
        empresa. O que protege o cliente é a **fronteira de tenant**, que vale
        para o supervisor como para qualquer um (`nucleo/tenancy.py`), e o acesso
        a dado de um cliente segue dependendo de o cliente **dar acesso**.
        Detalhe em docs/acesso-e-permissoes.md.
        """
        if not self.tenant_id:
            return []
        hoje = timezone.now().date()
        assinaturas = (
            AssinaturaTenant.objects.filter(
                tenant_id=self.tenant_id,
                status=AssinaturaTenant.Status.ATIVA,
                inicio__lte=hoje,
            )
            .filter(Q(fim__isnull=True) | Q(fim__gte=hoje))
            .values_list("modulo_id", flat=True)
        )
        modulo_ids = list(assinaturas)
        if self.is_superuser:
            # Sem restrição: o catálogo inteiro, não o que o tenant assinou.
            qs = Modulo.objects.all()
        elif self.is_tenant_admin:
            qs = Modulo.objects.filter(id__in=modulo_ids)
        else:
            qs = Modulo.objects.filter(
                id__in=modulo_ids, acessos_usuario__usuario_id=self.id
            )
        return list(qs.values_list("codigo", flat=True).distinct())

    def nomes_perfis(self):
        return list(self.perfis.values_list("nome", flat=True))

    def permissoes_efetivas(self):
        """Conjunto de permissões que viaja no JWT (Fase 9, fatia A): união das
        permissões dos papéis do usuário, **filtrada pelos módulos efetivos** —
        uma permissão de módulo vendável só vale se o tenant o assina e o usuário
        o acessa. Permissões `base`/`plataforma` não dependem de entitlement.

        O **admin do tenant** recebe todo o catálogo, limitado aos módulos que a
        empresa dele assina. O **supervisor da plataforma** também recebe o
        catálogo — e, como os módulos dele são todos (ver `modulos_efetivos`),
        na prática ele recebe o catálogo inteiro. É o que "teste supremo do
        sistema" exige: um supervisor que enxerga a tela mas leva 403 em toda
        ação não testa nada, só confirma que a tela abre.
        """
        from identity.catalog import POR_CODIGO, CODIGOS

        if self.is_tenant_admin or self.is_superuser:
            codigos = set(CODIGOS)
        else:
            codigos = set(
                self.perfis.values_list("permissoes__codename", flat=True)
            )
            codigos.discard(None)

        modulos = set(self.modulos_efetivos())

        def liberado(code: str) -> bool:
            p = POR_CODIGO.get(code)
            if p is None:
                return False  # código fora do catálogo não viaja no token
            if p.modulo in ("base", "plataforma"):
                return True
            return p.modulo in modulos

        return sorted(c for c in codigos if liberado(c))


class AssinaturaTenant(models.Model):
    """Quais módulos um tenant contratou (entitlement no nível do tenant)."""

    class Status(models.TextChoices):
        ATIVA = "ativa", _("Ativa")
        SUSPENSA = "suspensa", _("Suspensa")
        CANCELADA = "cancelada", _("Cancelada")

    id = models.AutoField(primary_key=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="assinaturas")
    modulo = models.ForeignKey(Modulo, on_delete=models.CASCADE, related_name="assinaturas")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ATIVA)
    inicio = models.DateField(default=timezone.now)
    fim = models.DateField(null=True, blank=True)
    limites = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Assinatura do Tenant")
        verbose_name_plural = _("Assinaturas dos Tenants")
        unique_together = ("tenant", "modulo")

    def __str__(self):
        return f"{self.tenant.slug} → {self.modulo.codigo} ({self.status})"


class AcessoUsuarioModulo(models.Model):
    """Quais módulos um usuário pode usar (subconjunto dos do tenant)."""

    id = models.AutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="acessos_modulo"
    )
    modulo = models.ForeignKey(
        Modulo, on_delete=models.CASCADE, related_name="acessos_usuario"
    )

    class Meta:
        verbose_name = _("Acesso de Usuário a Módulo")
        verbose_name_plural = _("Acessos de Usuários a Módulos")
        unique_together = ("usuario", "modulo")

    def __str__(self):
        return f"{self.usuario.username} → {self.modulo.codigo}"


# ---------------------------------------------------------------------------
# D11 — recuperação de senha, troca de e-mail e trilha de eventos de identidade
# ---------------------------------------------------------------------------


class EventoSeguranca(models.Model):
    """Trilha **append-only** dos eventos de identidade (D11).

    Existe porque o `AuditLog` da Fase 9.E vive no backend (`nucleo`) e não
    enxerga nada do que acontece na IAM: até aqui, resetar senha, trocar e-mail
    ou promover alguém a admin de tenant não deixava rastro em lugar nenhum.

    O ponto do modelo não é prevenir — é **atribuir**. Contra um admin vítima de
    engenharia social, o controle que funciona é a ação ficar registrada com
    nome e hora, e o usuário ser avisado; um reset assistido nunca pode se
    disfarçar de recuperação feita pelo próprio dono da conta.

    Imutável pelo mesmo padrão do `AuditLog`: `save` só cria, `delete` recusa.
    """

    class Tipo(models.TextChoices):
        RESET_SOLICITADO = "reset_solicitado", _("Recuperação de senha solicitada")
        RESET_CONCLUIDO = "reset_concluido", _("Senha redefinida por token")
        SENHA_ALTERADA = "senha_alterada", _("Senha alterada")
        EMAIL_TROCA_SOLICITADA = "email_troca_solicitada", _("Troca de e-mail solicitada")
        EMAIL_TROCA_CONFIRMADA = "email_troca_confirmada", _("Troca de e-mail confirmada")
        EMAIL_TROCA_CANCELADA = "email_troca_cancelada", _("Troca de e-mail cancelada")
        PRIVILEGIO_ALTERADO = "privilegio_alterado", _("Papéis/privilégios alterados")
        USUARIO_DESATIVADO = "usuario_desativado", _("Usuário desativado")
        SEGUNDO_FATOR_ATIVADO = "segundo_fator_ativado", _("Segundo fator ativado")
        SEGUNDO_FATOR_DESATIVADO = "segundo_fator_desativado", _("Segundo fator desativado")
        SEGUNDO_FATOR_TROCADO = "segundo_fator_trocado", _("Segundo fator trocado de aparelho")
        SEGUNDO_FATOR_REDEFINIDO = "segundo_fator_redefinido", _("Segundo fator redefinido pelo admin")
        SEGUNDO_FATOR_CODIGOS = "segundo_fator_codigos", _("Códigos de recuperação trocados")
        SEGUNDO_FATOR_RECUPERACAO = "segundo_fator_recuperacao", _("Entrada com código de recuperação")
        SEGUNDO_FATOR_BLOQUEADO = "segundo_fator_bloqueado", _("Segundo fator bloqueado por tentativas")
        SUPORTE_CONSENTIDO = "suporte_consentido", _("Acesso do suporte da plataforma liberado")
        SUPORTE_ENCERRADO = "suporte_encerrado", _("Acesso do suporte da plataforma encerrado")

    id = models.BigAutoField(primary_key=True)
    tipo = models.CharField(max_length=40, choices=Tipo.choices)
    # FKs SEM constraint no banco e sem cascata: a linha é CONGELADA. Se fossem
    # SET_NULL, excluir um usuário emitiria UPDATE nesta tabela — que o trigger de
    # imutabilidade barra, tornando o usuário inexcluível. Quem agiu fica durável
    # nos campos `*_username`, exatamente como o AuditLog do backend faz.
    alvo = models.ForeignKey(
        Usuario, on_delete=models.DO_NOTHING, null=True, db_constraint=False,
        related_name="eventos_seguranca",
    )
    alvo_username = models.CharField(max_length=150, blank=True)
    # Quem executou. NULL = o próprio fluxo público (esqueci minha senha).
    autor = models.ForeignKey(
        Usuario, on_delete=models.DO_NOTHING, null=True, blank=True, db_constraint=False,
        related_name="eventos_seguranca_autorados",
    )
    autor_username = models.CharField(max_length=150, blank=True)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.DO_NOTHING, null=True, db_constraint=False,
        related_name="eventos_seguranca",
    )
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    # Só metadados não-sensíveis. NUNCA token, senha ou PII em texto puro — os
    # e-mails ficam mascarados por `mascarar_email` antes de entrar aqui.
    detalhes = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Evento de Segurança")
        verbose_name_plural = _("Eventos de Segurança")
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["-criado_em"]),
            models.Index(fields=["alvo", "-criado_em"]),
            models.Index(fields=["tenant", "-criado_em"]),
            models.Index(fields=["tipo", "-criado_em"]),
        ]

    def __str__(self):
        return f"{self.criado_em:%Y-%m-%d %H:%M} {self.tipo} → {self.alvo_username}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("EventoSeguranca é imutável: alteração não é permitida.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("EventoSeguranca é append-only: exclusão não é permitida.")


class TokenRecuperacaoSenha(models.Model):
    """Token de uso único para redefinir a senha sem conhecer a anterior.

    O valor em claro **nunca** é persistido: guardamos só o SHA-256. Um dump do
    banco (ou um SELECT de quem tem leitura) não permite assumir contas — mesma
    disciplina de uma tabela de senhas.
    """

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="tokens_recuperacao"
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    # Caixa que recebeu o token. Hoje é sempre o e-mail do próprio usuário — há um
    # caminho só —, mas o registro importa: o e-mail da conta pode mudar depois, e
    # numa investigação o que interessa é para onde o token foi NAQUELE momento.
    enviado_para = models.EmailField(blank=True)
    expira_em = models.DateTimeField()
    usado_em = models.DateTimeField(null=True, blank=True)
    # Invalidação em massa sem apagar histórico (ex.: outra emissão, troca de
    # senha por outro caminho, cancelamento pelo usuário via link do aviso).
    invalidado_em = models.DateTimeField(null=True, blank=True)
    ip_solicitacao = models.GenericIPAddressField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Token de Recuperação de Senha")
        verbose_name_plural = _("Tokens de Recuperação de Senha")
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["usuario", "-criado_em"])]

    def __str__(self):
        return f"reset({self.usuario_id}) exp={self.expira_em:%Y-%m-%d %H:%M}"

    @property
    def valido(self):
        return (
            self.usado_em is None
            and self.invalidado_em is None
            and self.expira_em > timezone.now()
        )


class TrocaEmailPendente(models.Model):
    """Troca de e-mail com confirmação no endereço **ANTIGO**.

    Sem isto, a recuperação por e-mail não fecha nada: um admin comprometido
    trocaria o e-mail da vítima para a própria caixa, pediria o "esqueci minha
    senha" e assumiria a conta — com a agravante de o rastro parecer uma
    recuperação legítima feita pelo próprio usuário.

    Confirmando no endereço antigo, o link cai numa caixa que o atacante não
    controla, e o e-mail novo só passa a valer depois disso.
    """

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="trocas_email"
    )
    email_antigo = models.EmailField()
    email_novo = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    # Quem pediu a troca: o próprio usuário ou um admin do tenant.
    solicitante = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="trocas_email_solicitadas",
    )
    expira_em = models.DateTimeField()
    confirmado_em = models.DateTimeField(null=True, blank=True)
    cancelado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Troca de E-mail Pendente")
        verbose_name_plural = _("Trocas de E-mail Pendentes")
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["usuario", "-criado_em"])]

    def __str__(self):
        return f"{self.usuario_id}: {self.email_antigo} → {self.email_novo}"

    @property
    def pendente(self):
        return (
            self.confirmado_em is None
            and self.cancelado_em is None
            and self.expira_em > timezone.now()
        )


# ---------------------------------------------------------------------------
# Remodelagem da segurança, fase 1 — segundo fator (acesso-e-permissoes.md §10.5)
# ---------------------------------------------------------------------------


class SegundoFator(models.Model):
    """O segundo fator de uma pessoa — hoje, TOTP (o código de 6 dígitos do app
    autenticador). Passkey entra como outro `metodo`, na mesma linha.

    **O segredo é cifrado, não resumido.** Diferente de senha e de token de
    recuperação, o servidor precisa do segredo em claro a cada login para
    calcular o código do instante — um hash não serve. Cifrado com uma chave que
    não mora no banco (`segundo_fator.cifra`), um dump da tabela não dá o
    segundo fator de ninguém.

    Existe sem `confirmado_em` enquanto o cadastro não terminou: a pessoa leu o
    QR mas ainda não digitou um código certo. Só a linha confirmada conta como
    segundo fator ativo — senão um cadastro abandonado no meio trancaria a conta.
    """

    class Metodo(models.TextChoices):
        TOTP = "totp", _("App autenticador (TOTP)")

    id = models.BigAutoField(primary_key=True)
    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, related_name="segundo_fator"
    )
    metodo = models.CharField(max_length=20, choices=Metodo.choices, default=Metodo.TOTP)
    segredo_cifrado = models.TextField()
    confirmado_em = models.DateTimeField(null=True, blank=True)
    # Anti-reuso: o último passo de 30 s aceito. Um código visto por cima do
    # ombro (ou capturado) não vale uma segunda vez, nem dentro do mesmo passo.
    ultimo_passo = models.BigIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Segundo fator")
        verbose_name_plural = _("Segundos fatores")

    def __str__(self):
        estado = "ativo" if self.confirmado_em else "em cadastro"
        return f"{self.usuario_id}: {self.metodo} ({estado})"

    @property
    def ativo(self) -> bool:
        return self.confirmado_em is not None


class CodigoRecuperacao(models.Model):
    """Código de uso único para entrar sem o celular. Guardado só o SHA-256,
    pela mesma disciplina do `TokenRecuperacaoSenha`: o código tem entropia
    alta, então o hash lento de senha não acrescentaria nada."""

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="codigos_recuperacao"
    )
    codigo_hash = models.CharField(max_length=64, db_index=True)
    usado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Código de recuperação")
        verbose_name_plural = _("Códigos de recuperação")
        indexes = [models.Index(fields=["usuario", "usado_em"])]

    def __str__(self):
        return f"{self.usuario_id}: {'usado' if self.usado_em else 'livre'}"


# ---------------------------------------------------------------------------
# Remodelagem da segurança, fase 4 — a sessão tem identidade própria (§10.5)
# ---------------------------------------------------------------------------


class Sessao(models.Model):
    """Uma sessão aberta por login — o `sid` que viaja no token.

    O refresh token rotaciona a cada renovação (um `jti` novo por vez); a
    sessão é o que fica igual do login ao logout. É ela que se revoga: logout,
    troca de senha, desativação, reset do segundo fator e "encerrar todas" marcam
    `revogada_em` e publicam o `sid` no Redis (`sessoes.publicar_revogacao`), e
    cada serviço (PEP) confere o `sid` a cada requisição — o access já emitido
    deixa de valer em segundos, e não quando expira.

    A IAM é a autoridade: quando o Redis falta, o PEP pergunta aqui
    (`/auth/interno/sessao/<sid>/`), e só nega se nem a IAM responder.

    **Fase 5 (BFF).** O navegador não recebe mais token: guarda só o cookie
    HttpOnly da sessão, cuja credencial aleatória fica aqui **como hash**
    (`credencial_hash`). O gateway troca o cookie por um access de 5 minutos
    para o serviço de destino (`/auth/interno/bff/<serviço>/`), e é desta linha
    que saem o `amr`, o `auth_time` e a validade (`expira_em`, que acompanha a
    janela deslizante do refresh). O `auth_time` só anda no login e na
    confirmação do ato grave (step-up, fase 6).
    """

    sid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="sessoes")
    criada_em = models.DateTimeField(auto_now_add=True)
    revogada_em = models.DateTimeField(null=True, blank=True)
    motivo = models.CharField(max_length=40, blank=True)
    credencial_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    lembrar = models.BooleanField(default=False)
    amr = models.JSONField(default=list, blank=True)
    auth_time = models.DateTimeField(null=True, blank=True)
    expira_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Sessão")
        verbose_name_plural = _("Sessões")
        indexes = [models.Index(fields=["usuario", "revogada_em"])]

    def __str__(self):
        return f"{self.sid} ({self.usuario_id}{', revogada' if self.revogada_em else ''})"

    @property
    def ativa(self) -> bool:
        return self.revogada_em is None


# ---------------------------------------------------------------------------
# Remodelagem da segurança, fase 6 — o suporte só entra com consentimento (§10.7)
# ---------------------------------------------------------------------------


class ConsentimentoSuporte(models.Model):
    """O admin da empresa deixa o supervisor da plataforma enxergar as pessoas,
    os papéis e os acessos dela — **com data de fim** (§10.7, §10.10: "suporte da
    plataforma lendo dado de cliente").

    Sem uma linha vigente, o supervisor não vê nem mexe em ninguém de outra
    empresa na IAM. A exceção é o resgate do próprio administrador (segundo
    fator perdido): sem ele não há quem consinta, e a redefinição continua
    registrada e avisada por e-mail (`identity.suporte`).

    Encerrar é marcar `encerrado_em`; a linha fica, como trilha de quem liberou,
    por quanto tempo e por quê.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="consentimentos_suporte")
    concedido_por = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, null=True, related_name="consentimentos_concedidos",
    )
    concedido_por_username = models.CharField(max_length=150, blank=True)
    motivo = models.CharField(max_length=200, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    ate = models.DateTimeField()
    encerrado_em = models.DateTimeField(null=True, blank=True)
    encerrado_por_username = models.CharField(max_length=150, blank=True)

    class Meta:
        verbose_name = _("Consentimento de suporte")
        verbose_name_plural = _("Consentimentos de suporte")
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["tenant", "encerrado_em", "ate"])]

    def __str__(self):
        return f"{self.tenant_id} até {self.ate:%d/%m %H:%M}"

    @property
    def vigente(self) -> bool:
        from django.utils import timezone

        return self.encerrado_em is None and self.ate > timezone.now()
