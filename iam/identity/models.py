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
        Códigos dos módulos que este usuário pode efetivamente acessar:
        interseção entre as assinaturas ativas do tenant e o acesso concedido
        ao usuário. Admins de tenant (e admins de plataforma) recebem todos os
        módulos ativos do tenant.
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
        if self.is_tenant_admin or self.is_superuser:
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
        Admin de tenant/plataforma recebe todo o catálogo (limitado aos módulos).
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
