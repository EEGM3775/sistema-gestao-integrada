from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    AcessoUsuarioModulo,
    AssinaturaTenant,
    Modulo,
    Perfil,
    Permissao,
    Tenant,
    Usuario,
)
from .tokens import build_claims


class IamTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login: injeta as claims da plataforma no token e enriquece a resposta."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        for chave, valor in build_claims(user).items():
            token[chave] = valor
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        tenant = user.tenant
        data["user"] = {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "is_tenant_admin": user.is_tenant_admin,
            "is_platform_admin": user.is_superuser,
        }
        data["tenant"] = (
            {"id": str(tenant.id), "slug": tenant.slug, "nome": tenant.nome}
            if tenant
            else None
        )
        data["modules"] = user.modulos_efetivos()
        return data


class PermissaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permissao
        fields = ["id", "codename", "nome"]


class ModuloSerializer(serializers.ModelSerializer):
    class Meta:
        model = Modulo
        fields = ["id", "codigo", "nome", "descricao"]


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ["id", "nome", "slug", "cnpj", "status", "plano", "data_criacao"]
        read_only_fields = ["id", "data_criacao"]


class PerfilSerializer(serializers.ModelSerializer):
    class Meta:
        model = Perfil
        fields = ["id", "tenant", "nome", "descricao", "permissoes"]
        # `tenant` é injetado pelo perform_create (tenant do próprio admin); superuser
        # o informa explicitamente. Opcional na entrada p/ não barrar o admin do tenant.
        # validators=[] remove o UniqueTogether automático (exigiria `tenant` no
        # payload); a unicidade (tenant, nome) é checada à mão em validate().
        extra_kwargs = {"tenant": {"required": False}}
        validators = []

    def _tenant_efetivo(self, attrs):
        if attrs.get("tenant"):
            return attrs["tenant"]
        if self.instance:
            return self.instance.tenant
        request = self.context.get("request")
        return getattr(getattr(request, "user", None), "tenant", None)

    def validate(self, attrs):
        tenant = self._tenant_efetivo(attrs)
        nome = attrs.get("nome", getattr(self.instance, "nome", None))
        if tenant and nome:
            dup = Perfil.objects.filter(tenant=tenant, nome=nome)
            if self.instance:
                dup = dup.exclude(pk=self.instance.pk)
            if dup.exists():
                raise serializers.ValidationError(
                    {"nome": f"Já existe um papel '{nome}' neste tenant."}
                )
        return attrs

    def validate_permissoes(self, value):
        """Anti-escalada: um papel só recebe permissões (a) do catálogo e (b) de
        módulos `base`/`plataforma` ou de módulos que o tenant assina. Assim um
        admin de tenant compõe personas à vontade, mas nunca além do próprio plano.
        Plataforma-admin (superuser) é isento."""
        from .catalog import POR_CODIGO

        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and user.is_superuser:
            return value

        tenant = self.instance.tenant if self.instance else getattr(user, "tenant", None)
        modulos = set(tenant.modulos_ativos()) if tenant else set()
        for perm in value:
            p = POR_CODIGO.get(perm.codename)
            if p is None:
                raise serializers.ValidationError(
                    f"Permissão fora do catálogo: {perm.codename}."
                )
            if p.modulo not in ("base", "plataforma") and p.modulo not in modulos:
                raise serializers.ValidationError(
                    f"'{perm.codename}' exige o módulo '{p.modulo}', não assinado por este tenant."
                )
        return value


class AssinaturaTenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssinaturaTenant
        fields = ["id", "tenant", "modulo", "status", "inicio", "fim", "limites"]


class AcessoUsuarioModuloSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcessoUsuarioModulo
        fields = ["id", "usuario", "modulo"]


class UsuarioSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    modules = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Usuario
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_tenant_admin",
            "tenant",
            "perfis",
            "password",
            "modules",
        ]
        read_only_fields = ["id"]

    def get_modules(self, obj):
        return obj.modulos_efetivos()

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        perfis = validated_data.pop("perfis", [])
        user = Usuario(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        if perfis:
            user.perfis.set(perfis)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        perfis = validated_data.pop("perfis", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        if perfis is not None:
            instance.perfis.set(perfis)
        return instance
