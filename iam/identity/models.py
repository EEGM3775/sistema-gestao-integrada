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
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="usuarios", null=True, blank=True
    )
    # Admin do próprio tenant (gerencia usuários/perfis/acessos do tenant).
    is_tenant_admin = models.BooleanField(default=False)
    perfis = models.ManyToManyField(Perfil, related_name="usuarios", blank=True)

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
