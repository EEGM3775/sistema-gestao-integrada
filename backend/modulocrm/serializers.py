# backend/modulocrm/serializers.py
from rest_framework import serializers
from .models import Lead, Account, Contact, Opportunity, Interaction, OpportunityProduct
from nucleo.serializers import UsuarioSerializer

from rest_framework import serializers
from .models import Lead, Account, Contact, Opportunity, Interaction, OpportunityProduct
from nucleo.serializers import UsuarioSerializer
from fornecedores.serializers import FornecedorSerializer, ProdutoServicoFornecedorSerializer
from rh.serializers import FuncionarioSerializer
from nucleo.models import Usuario
from fornecedores.models import Fornecedor, ProdutoServicoFornecedor
from rh.models import Funcionario

class GenericObjectRelatedField(serializers.RelatedField):
    def to_representation(self, value):
        if isinstance(value, Usuario):
            serializer = UsuarioSerializer(value)
            data = serializer.data
            data['type'] = 'usuario'
        elif isinstance(value, Funcionario):
            serializer = FuncionarioSerializer(value)
            data = serializer.data
            data['type'] = 'funcionario'
        elif isinstance(value, Fornecedor):
            serializer = FornecedorSerializer(value)
            data = serializer.data
            data['type'] = 'fornecedor'
        else:
            raise Exception('Unexpected type of tagged object')
        return data

# Serializer para Interações
class InteractionSerializer(serializers.ModelSerializer):
    assigned_to = GenericObjectRelatedField(read_only=True)

    class Meta:
        model = Interaction
        fields = '__all__'


# Serializer for OpportunityProduct
class OpportunityProductSerializer(serializers.ModelSerializer):
    product = ProdutoServicoFornecedorSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=ProdutoServicoFornecedor.objects.all(),
        write_only=True,
        source='product'
    )

    class Meta:
        model = OpportunityProduct
        fields = '__all__'


# Serializer para Oportunidades
class OpportunitySerializer(serializers.ModelSerializer):
    assigned_to = UsuarioSerializer(read_only=True)
    assigned_to_id = serializers.PrimaryKeyRelatedField(
        queryset=UsuarioSerializer.Meta.model.objects.all(),
        write_only=True,
        source='assigned_to',
        allow_null=True
    )
    account = serializers.StringRelatedField(read_only=True)
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(),
        write_only=True,
        source='account'
    )
    contact = serializers.StringRelatedField(read_only=True)
    contact_id = serializers.PrimaryKeyRelatedField(
        queryset=Contact.objects.all(),
        write_only=True,
        source='contact',
        allow_null=True
    )
    interactions = InteractionSerializer(many=True, read_only=True)
    products = OpportunityProductSerializer(many=True, read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Opportunity
        fields = '__all__'

# Serializer para Contatos
class ContactSerializer(serializers.ModelSerializer):
    account = serializers.StringRelatedField(read_only=True)
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(),
        write_only=True,
        source='account'
    )
    opportunities = OpportunitySerializer(many=True, read_only=True)
    interactions = InteractionSerializer(many=True, read_only=True)

    class Meta:
        model = Contact
        fields = '__all__'

# Serializer para Contas
class AccountSerializer(serializers.ModelSerializer):
    assigned_to = UsuarioSerializer(read_only=True)
    assigned_to_id = serializers.PrimaryKeyRelatedField(
        queryset=UsuarioSerializer.Meta.model.objects.all(),
        write_only=True,
        source='assigned_to',
        allow_null=True
    )
    contacts = ContactSerializer(many=True, read_only=True)
    opportunities = OpportunitySerializer(many=True, read_only=True)

    class Meta:
        model = Account
        fields = '__all__'

# Serializer para Leads
class LeadSerializer(serializers.ModelSerializer):
    assigned_to = UsuarioSerializer(read_only=True)
    assigned_to_id = serializers.PrimaryKeyRelatedField(
        queryset=UsuarioSerializer.Meta.model.objects.all(),
        write_only=True,
        source='assigned_to',
        allow_null=True
    )
    interactions = InteractionSerializer(many=True, read_only=True)

    class Meta:
        model = Lead
        fields = '__all__'
