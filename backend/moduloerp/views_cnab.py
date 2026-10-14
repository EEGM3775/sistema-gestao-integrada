"""Carteiras de cobrança, remessas, retornos e lotes de boletos (item 52)."""
from django.http import HttpResponse
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from nucleo.permissions import RequireModule, RequirePermission
from entidades.escopo import EscopoDeEntidadeMixin
from nucleo.tenancy import TenantScopedViewSetMixin
from payment.planos import ERP_CNAB_RETORNO_TETO_MB

from . import cobranca_lote
from .cnab.bancos import AJUDA_CAMPOS, BANCOS, banco_de
from .models import ContaCobrancaBancaria, LoteCobranca, RemessaCnab, RetornoCnab


class ContaCobrancaSerializer(serializers.ModelSerializer):
    banco_nome = serializers.SerializerMethodField()
    problemas = serializers.SerializerMethodField()
    entidade_nome = serializers.CharField(source='entidade.__str__', read_only=True, default='')
    # Aceita com pontuação ("66.774.885/0001-90" tem 18 caracteres); o
    # `validate_beneficiario_documento` devolve só os 14 dígitos que se gravam.
    beneficiario_documento = serializers.CharField(max_length=18)

    class Meta:
        model = ContaCobrancaBancaria
        exclude = ['tenant']
        read_only_fields = ['criado_em']
        # Sem entidade, a matriz (docs/modulos/entidades.md §5).
        extra_kwargs = {'entidade': {'required': False}}

    def get_banco_nome(self, obj):
        banco = BANCOS.get(obj.banco)
        return banco.nome if banco else obj.banco

    def get_problemas(self, obj):
        banco = BANCOS.get(obj.banco)
        return banco.problemas(obj) if banco else ["banco sem cobrança CNAB no SGI"]

    def validate_beneficiario_documento(self, valor):
        """Grava só os dígitos — a pontuação é da tela (máscara), não do dado."""
        digitos = ''.join(ch for ch in (valor or '') if ch.isdigit())
        if len(digitos) not in (11, 14):
            raise serializers.ValidationError("Informe o CNPJ (14 dígitos) ou CPF (11 dígitos) do beneficiário.")
        return digitos

    def validate_banco(self, valor):
        if valor not in BANCOS:
            raise serializers.ValidationError("Este banco ainda não tem cobrança CNAB no SGI.")
        return valor

    def validate(self, attrs):
        from .serializers import _validar_entidade_do_grupo
        _validar_entidade_do_grupo(attrs.get('entidade'))
        banco = attrs.get('banco', getattr(self.instance, 'banco', None))
        layout = attrs.get('layout', getattr(self.instance, 'layout', '240'))
        if banco in BANCOS and layout not in BANCOS[banco].layouts:
            raise serializers.ValidationError({'layout': f"O {BANCOS[banco].nome} usa CNAB {', '.join(BANCOS[banco].layouts)}."})
        return attrs


class ContaCobrancaViewSet(EscopoDeEntidadeMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    """As carteiras de cobrança da empresa — de onde sai o CNAB."""
    queryset = ContaCobrancaBancaria.objects.all()
    campo_empreendimento_escopo = None
    serializer_class = ContaCobrancaSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    permission_map = {"view": "erp.cobranca.view", "write": "erp.cobranca.emitir"}

    @action(detail=False, methods=['get'], url_path='bancos')
    def bancos(self, request):
        """Os bancos disponíveis e o que cada campo genérico significa em cada um."""
        return Response([
            {'codigo': b.codigo, 'nome': b.nome, 'layouts': list(b.layouts), 'ajuda': AJUDA_CAMPOS.get(b.codigo, {})}
            for b in BANCOS.values()
        ])

    def destroy(self, request, *args, **kwargs):
        carteira = self.get_object()
        if carteira.boletos.exists():
            return Response(
                {'detail': 'Esta carteira já emitiu boletos. Desative-a em vez de excluir.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


class RemessaSerializer(serializers.ModelSerializer):
    carteira_nome = serializers.CharField(source='conta_cobranca.nome', read_only=True)

    class Meta:
        model = RemessaCnab
        fields = ['remessa_id', 'conta_cobranca', 'carteira_nome', 'sequencial', 'nome_arquivo',
                  'quantidade', 'valor_total', 'criado_em']


class RemessaViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = RemessaCnab.objects.select_related('conta_cobranca')
    serializer_class = RemessaSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    permission_map = {"view": "erp.cobranca.view", "write": "erp.cobranca.emitir"}

    @action(detail=True, methods=['get'], url_path='arquivo')
    def arquivo(self, request, pk=None):
        remessa = self.get_object()
        resposta = HttpResponse(remessa.conteudo.encode('latin-1', 'replace'), content_type='text/plain; charset=latin-1')
        resposta['Content-Disposition'] = f'attachment; filename="{remessa.nome_arquivo}"'
        return resposta


class RetornoSerializer(serializers.ModelSerializer):
    carteira_nome = serializers.CharField(source='conta_cobranca.nome', read_only=True)

    class Meta:
        model = RetornoCnab
        fields = ['retorno_id', 'conta_cobranca', 'carteira_nome', 'nome_arquivo', 'resumo', 'recebido_em']


class RetornoViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """O arquivo de retorno do banco: confirma registros e dá baixa no que foi pago."""
    queryset = RetornoCnab.objects.select_related('conta_cobranca')
    serializer_class = RetornoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    permission_map = {"view": "erp.cobranca.view", "write": "erp.cobranca.conciliar"}
    action_permission_map = {"enviar": "erp.cobranca.conciliar"}

    @action(detail=False, methods=['post'], url_path='enviar')
    def enviar(self, request):
        from django.db import transaction

        from .cnab.retorno import aplicar
        arquivo = request.FILES.get('arquivo')
        carteira = ContaCobrancaBancaria.objects.filter(pk=request.data.get('conta_cobranca')).first()
        if carteira is None:
            return Response({'detail': 'Escolha a carteira de cobrança deste retorno.'}, status=status.HTTP_400_BAD_REQUEST)
        if arquivo is None:
            return Response({'detail': 'Escolha o arquivo de retorno que o banco enviou.'}, status=status.HTTP_400_BAD_REQUEST)
        if arquivo.size > ERP_CNAB_RETORNO_TETO_MB * 1024 * 1024:
            return Response({'detail': f'O arquivo passa de {ERP_CNAB_RETORNO_TETO_MB} MB. Confira se é o retorno certo.'},
                            status=status.HTTP_400_BAD_REQUEST)
        conteudo = arquivo.read().decode('latin-1')
        try:
            with transaction.atomic():
                resumo = aplicar(carteira, conteudo, usuario=request.user)
                retorno = RetornoCnab.objects.create(
                    tenant=carteira.tenant, conta_cobranca=carteira, nome_arquivo=arquivo.name[:120],
                    conteudo=conteudo, resumo=resumo, recebido_por=request.user,
                )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        from nucleo.auditoria import registrar_auditoria
        registrar_auditoria(
            acao="processar_retorno_cnab", instance=retorno, usuario=request.user,
            detalhes={k: resumo[k] for k in ('lidos', 'pagos', 'rejeitados', 'valor_recebido')},
        )
        return Response(RetornoSerializer(retorno).data, status=status.HTTP_201_CREATED)


class LoteCobrancaViewSet(TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """O andamento de um lote de boletos — a tela consulta até todos saírem."""
    queryset = LoteCobranca.objects.all()
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "erp_financeiro"
    permission_map = {"view": "erp.cobranca.view", "write": "erp.cobranca.emitir"}

    def list(self, request, *args, **kwargs):
        lotes = self.get_queryset()[:20]
        return Response([cobranca_lote.andamento(l) for l in lotes])

    def retrieve(self, request, *args, **kwargs):
        return Response(cobranca_lote.andamento(self.get_object()))


__all__ = [
    'ContaCobrancaViewSet', 'RemessaViewSet', 'RetornoViewSet', 'LoteCobrancaViewSet', 'banco_de',
]
