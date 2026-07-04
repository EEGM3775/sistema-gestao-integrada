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
