from decimal import Decimal

from django.db.models import Sum
from nucleo.campos import NomeDoRelacionado
from rest_framework import serializers

from nucleo.tenant_validators import TenantScopedUniqueSerializerMixin

from .models import ConcessaoEmpreendimento, ConcessaoEntidade, Entidade, ParticipacaoEmpreendimento


def so_digitos(valor) -> str:
    return "".join(ch for ch in (valor or "") if ch.isdigit())


class EntidadeSerializer(TenantScopedUniqueSerializerMixin, serializers.ModelSerializer):
    papel_nome = serializers.CharField(source="get_papel_display", read_only=True)
    # Não `source="matriz.__str__"`: sem matriz a tela mostrava "Matriz de
    # <method-wrapper…>" (ver `nucleo.campos`).
    matriz_nome = NomeDoRelacionado(source="matriz")
    cliente_nome = serializers.CharField(source="cliente.nome_completo", read_only=True, default="")
    # Aceita com pontuação; grava só os dígitos.
    documento = serializers.CharField(max_length=18, required=False, allow_blank=True)
    empreendimentos = serializers.SerializerMethodField()

    class Meta:
        model = Entidade
        exclude = ["tenant"]
        read_only_fields = ["criado_em", "atualizado_em"]

    def get_empreendimentos(self, obj):
        """Os empreendimentos de que ela é dona ou sócia — a integração que a tela mostra."""
        proprios = [
            {"empreendimento": e.pk, "nome": e.empreendimento, "como": "propria", "cota": None, "administradora": False}
            for e in obj.empreendimentos_proprios.all()
        ]
        cotas = [
            {"empreendimento": p.empreendimento_id, "nome": p.empreendimento.empreendimento, "como": "participacao",
             "cota": str(p.cota.normalize()), "administradora": p.administradora}
            for p in obj.participacoes.select_related("empreendimento")
        ]
        return proprios + cotas

    def validate_documento(self, valor):
        digitos = so_digitos(valor)
        if digitos and len(digitos) not in (11, 14):
            raise serializers.ValidationError("Informe o CPF (11 dígitos) ou o CNPJ (14 dígitos).")
        return digitos

    def validate(self, attrs):
        papel = attrs.get("papel", getattr(self.instance, "papel", Entidade.Papel.MATRIZ))
        matriz = attrs.get("matriz", getattr(self.instance, "matriz", None))
        externa = attrs.get("externa", getattr(self.instance, "externa", False))
        tipo = attrs.get("tipo_pessoa", getattr(self.instance, "tipo_pessoa", Entidade.TipoPessoa.PJ))
        documento = attrs.get("documento", getattr(self.instance, "documento", ""))
        if papel == Entidade.Papel.FILIAL and matriz is None:
            raise serializers.ValidationError({"matriz": "A filial aponta a matriz dela."})
        if papel != Entidade.Papel.FILIAL and matriz is not None:
            raise serializers.ValidationError({"matriz": "Só a filial tem matriz."})
        if matriz is not None and (matriz.externa or matriz.pk == getattr(self.instance, "pk", None)):
            raise serializers.ValidationError({"matriz": "A matriz tem de ser outra entidade do grupo."})
        if externa and papel in (Entidade.Papel.MATRIZ, Entidade.Papel.FILIAL):
            raise serializers.ValidationError({"externa": "Matriz e filial são do grupo, nunca externas."})
        if documento:
            esperado = 11 if tipo == Entidade.TipoPessoa.PF else 14
            if len(documento) != esperado:
                raise serializers.ValidationError({
                    "documento": "Pessoa física tem CPF (11 dígitos)." if esperado == 11 else "Pessoa jurídica tem CNPJ (14 dígitos).",
                })
        # A última entidade do grupo não sai do grupo.
        if self.instance is not None and externa and not self.instance.externa:
            outras = Entidade.objects.filter(tenant_id=self.instance.tenant_id, externa=False).exclude(pk=self.instance.pk)
            if not outras.exists():
                raise serializers.ValidationError({"externa": "A conta precisa de ao menos uma entidade do grupo."})
        return attrs


class ParticipacaoSerializer(serializers.ModelSerializer):
    entidade_nome = NomeDoRelacionado(source="entidade")
    entidade_externa = serializers.BooleanField(source="entidade.externa", read_only=True)
    empreendimento_nome = serializers.CharField(source="empreendimento.empreendimento", read_only=True)

    class Meta:
        model = ParticipacaoEmpreendimento
        exclude = ["tenant"]

    def validate(self, attrs):
        empreendimento = attrs.get("empreendimento", getattr(self.instance, "empreendimento", None))
        cota = attrs.get("cota", getattr(self.instance, "cota", Decimal("0")))
        outras = ParticipacaoEmpreendimento.objects.filter(empreendimento=empreendimento)
        if self.instance is not None:
            outras = outras.exclude(pk=self.instance.pk)
        soma = (outras.aggregate(s=Sum("cota"))["s"] or Decimal("0")) + cota
        if soma > Decimal("100"):
            raise serializers.ValidationError({
                "cota": f"As cotas do empreendimento passariam de 100% (somariam {soma.normalize()}%).",
            })
        if attrs.get("administradora") and attrs.get("entidade", getattr(self.instance, "entidade", None)).externa:
            raise serializers.ValidationError({"administradora": "A administradora é uma entidade do grupo."})
        return attrs


class _ConcessaoBase(serializers.ModelSerializer):
    usuario_nome = serializers.SerializerMethodField()

    def get_usuario_nome(self, obj):
        return obj.usuario.get_full_name() or obj.usuario.username

    def validate_usuario(self, usuario):
        # A tabela de usuários não tem RLS: o tenant é conferido aqui.
        request = self.context.get("request")
        if request is None or usuario.tenant_id != request.user.tenant_id:
            raise serializers.ValidationError("Usuário não encontrado.")
        return usuario


class ConcessaoEntidadeSerializer(_ConcessaoBase):
    entidade_nome = NomeDoRelacionado(source="entidade")

    class Meta:
        model = ConcessaoEntidade
        exclude = ["tenant"]
        read_only_fields = ["concedido_por", "concedido_em"]

    def validate_entidade(self, entidade):
        if entidade.externa:
            raise serializers.ValidationError("Entidade externa não tem financeiro a conceder.")
        return entidade


class ConcessaoEmpreendimentoSerializer(_ConcessaoBase):
    empreendimento_nome = serializers.CharField(source="empreendimento.empreendimento", read_only=True)

    class Meta:
        model = ConcessaoEmpreendimento
        exclude = ["tenant"]
        read_only_fields = ["concedido_por", "concedido_em"]
