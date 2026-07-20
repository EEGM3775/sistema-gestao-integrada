from rest_framework import serializers
from rest_framework.validators import UniqueValidator
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
    # D11 — e-mail obrigatório na CRIAÇÃO. Uma conta nasce hoje e o dono esquece
    # a senha daqui a três meses: sem endereço não há como devolvê-la a ele. Na
    # ATUALIZAÇÃO o campo é descartado no `update()` — trocar e-mail exige a ação
    # `trocar-email`, que confirma no endereço antigo.
    #
    # O `UniqueValidator` precisa ser explícito: declarar o campo aqui substitui
    # a versão que o ModelSerializer geraria a partir do `unique=True` do modelo,
    # e sem ele a duplicata escapava da validação e estourava como IntegrityError
    # — 500 em vez de 400.
    email = serializers.EmailField(
        required=True,
        validators=[
            UniqueValidator(
                queryset=Usuario.objects.all(),
                message="Já existe uma conta com este e-mail.",
                lookup="iexact",
            )
        ],
    )

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
        # Troca de senha de usuário existente NÃO passa por aqui: só pela ação
        # `redefinir-senha` (exige a senha atual do usuário). Ignoramos `password`
        # num PATCH comum para não haver caminho de troca sem a senha antiga.
        validated_data.pop("password", None)

        # D11 — `email` também não passa por aqui. Era o elo que tornava a
        # recuperação por e-mail insuficiente: um admin comprometido apontava a
        # conta da vítima para a própria caixa com um PATCH banal e em seguida
        # usava o "esqueci minha senha" público — takeover completo, sem step-up,
        # e com rastro parecendo uma recuperação feita pelo próprio usuário.
        # A troca agora só acontece pela ação `trocar-email`, que confirma no
        # endereço ANTIGO e arma o cooldown de recuperação.
        validated_data.pop("email", None)

        perfis = validated_data.pop("perfis", None)
        estava_ativo = instance.is_active
        era_admin = instance.is_tenant_admin
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Promoção a admin de tenant é a escalada de privilégio mais forte que
        # existe aqui: admin gerencia usuários, papéis e acessos do tenant inteiro.
        if era_admin != instance.is_tenant_admin:
            self._auditar_privilegio(
                instance,
                {"is_tenant_admin": {"antes": era_admin, "depois": instance.is_tenant_admin}},
            )

        # Escalada de privilégio é evento de segurança: quem ganhou/perdeu papel
        # ou virou admin de tenant fica registrado e o dono da conta é avisado.
        # Um admin comprometido que se promova (ou promova um cúmplice) não faz
        # isso em silêncio.
        if perfis is not None:
            antes = set(instance.perfis.values_list("nome", flat=True))
            instance.perfis.set(perfis)
            depois = set(instance.perfis.values_list("nome", flat=True))
            if antes != depois:
                self._auditar_privilegio(
                    instance,
                    {"perfis_antes": sorted(antes), "perfis_depois": sorted(depois)},
                )
        # Desativação (is_active True→False): a revogação em si (blacklist do
        # refresh + carimbo de época) migrou para o signal `post_save` em
        # identity/signals.py — D12: pelo serializer só passava a desativação
        # feita pela API, e desativar por admin/shell deixava o access residual
        # vivo. Aqui fica a AUDITORIA, que o signal não consegue produzir: só
        # este caminho sabe quem foi o autor da ação.
        if estava_ativo and not instance.is_active:
            self._evento(
                "usuario_desativado", instance, {"por": self._autor_username()}
            )
        return instance

    # --- D11: trilha e aviso das mudanças de privilégio ---------------------
    def _autor(self):
        request = self.context.get("request")
        return getattr(request, "user", None) if request else None

    def _autor_username(self):
        autor = self._autor()
        return getattr(autor, "username", "") or "sistema"

    def _evento(self, tipo, instance, detalhes):
        from . import recuperacao

        recuperacao.registrar_evento(
            tipo,
            alvo=instance,
            autor=self._autor(),
            request=self.context.get("request"),
            **detalhes,
        )

    def _auditar_privilegio(self, instance, mudanca):
        from . import emails
        from .models import EventoSeguranca

        self._evento(EventoSeguranca.Tipo.PRIVILEGIO_ALTERADO, instance, mudanca)
        autor = self._autor()
        if autor is not None and autor.id != instance.id:
            resumo = "\n".join(f"  {k}: {v}" for k, v in mudanca.items())
            emails.enviar_aviso_privilegio_alterado(instance, autor, resumo)
