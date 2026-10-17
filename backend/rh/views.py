# backend/rh/views.py
# Este arquivo define a lógica da API (endpoints) para o app 'rh'.
# Cada ViewSet agrupa as operações CRUD (Create, Retrieve, Update, Delete) para um modelo.
from nucleo.busca import BuscaSemAcento
from nucleo.paginacao import PaginaSobPedido
from rest_framework.filters import OrderingFilter
from rest_framework import viewsets, permissions, filters
from django.db.models import Q
import re
from django_filters.rest_framework import DjangoFilterBackend
from nucleo.tenancy import TenantScopedViewSetMixin
from nucleo.auditoria import AuditedModelViewSetMixin, PiiReadAuditMixin
from nucleo.permissions import RequireModule, RequirePermission
from .models import (
    Cargo,
    Funcionario,
    DadoMedicoFuncionario,
    ASOFuncionario,
    DocumentoFuncionario,
    DadoBancarioFuncionario,
    PagamentoFuncionario,
    FolhaPagamento
)
from .serializers import (
    CargoSerializer,
    FuncionarioSerializer,
    DadoMedicoFuncionarioSerializer,
    ASOFuncionarioSerializer,
    DocumentoFuncionarioSerializer,
    DadoBancarioFuncionarioSerializer,
    PagamentoFuncionarioSerializer,
    FolhaPagamentoSerializer
)

class CargoViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Cargo.objects.all().order_by('nome_cargo')
    serializer_class = CargoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "rh"
    filter_backends = [DjangoFilterBackend, BuscaSemAcento]
    search_fields = ['nome_cargo', 'departamento']

class FuncionarioViewSet(AuditedModelViewSetMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = Funcionario.objects.all().order_by('nome_completo')
    serializer_class = FuncionarioSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "rh"
    filter_backends = [DjangoFilterBackend, BuscaSemAcento, OrderingFilter]
    filterset_fields = ['status_contrato', 'cargo']
    search_fields = ['nome_completo', 'cpf', 'email_pessoal']
    ordering_fields = ['nome_completo', 'funcionario_id']
    pagination_class = PaginaSobPedido
    
    def get_queryset(self):
        """
        Sobrescreve o método get_queryset para adicionar lógica de busca por telefone.
        """
        queryset = super().get_queryset()
        
        # Verifica se há um parâmetro de telefone na query
        telefone = self.request.query_params.get('telefone', None)
        if telefone:
            # Normaliza o número de telefone removendo tudo exceto dígitos
            # Mantém o + no início se existir
            if telefone.startswith('+'):
                telefone_limpo = '+' + re.sub(r'[^\d]', '', telefone[1:])
            else:
                telefone_limpo = re.sub(r'[^\d]', '', telefone)
            
            # Busca por números que, quando normalizados, correspondam ao número pesquisado
            funcionarios_encontrados = []
            for funcionario in queryset:
                # Verifica telefone_celular
                if funcionario.telefone_celular:
                    tel_cel_normalizado = funcionario.telefone_celular
                    if tel_cel_normalizado.startswith('+'):
                        tel_cel_normalizado = '+' + re.sub(r'[^\d]', '', tel_cel_normalizado[1:])
                    else:
                        tel_cel_normalizado = re.sub(r'[^\d]', '', tel_cel_normalizado)
                    
                    if tel_cel_normalizado == telefone_limpo:
                        funcionarios_encontrados.append(funcionario.funcionario_id)
                        continue
                
                # Verifica telefone_pessoal
                if funcionario.telefone_pessoal:
                    tel_pes_normalizado = funcionario.telefone_pessoal
                    if tel_pes_normalizado.startswith('+'):
                        tel_pes_normalizado = '+' + re.sub(r'[^\d]', '', tel_pes_normalizado[1:])
                    else:
                        tel_pes_normalizado = re.sub(r'[^\d]', '', tel_pes_normalizado)
                    
                    if tel_pes_normalizado == telefone_limpo:
                        funcionarios_encontrados.append(funcionario.funcionario_id)
            
            # Filtra o queryset pelos IDs encontrados
            queryset = queryset.filter(funcionario_id__in=funcionarios_encontrados)
        
        return queryset

class DadoMedicoFuncionarioViewSet(PiiReadAuditMixin, AuditedModelViewSetMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = DadoMedicoFuncionario.objects.all()
    serializer_class = DadoMedicoFuncionarioSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "rh"
    required_resource = "rh.dado_medico"   # GET→.view · escrita→.edit
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['funcionario']

class ASOFuncionarioViewSet(PiiReadAuditMixin, AuditedModelViewSetMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = ASOFuncionario.objects.all().order_by('-data_exame')
    serializer_class = ASOFuncionarioSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "rh"
    required_resource = "rh.dado_medico"   # ASO é PII médica
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['funcionario']

class DocumentoFuncionarioViewSet(TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = DocumentoFuncionario.objects.all().order_by('-data_upload')
    serializer_class = DocumentoFuncionarioSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule]
    required_module = "rh"
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['funcionario']

class DadoBancarioFuncionarioViewSet(PiiReadAuditMixin, AuditedModelViewSetMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = DadoBancarioFuncionario.objects.all()
    serializer_class = DadoBancarioFuncionarioSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "rh"
    required_resource = "rh.dado_bancario"
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['funcionario']

class PagamentoFuncionarioViewSet(AuditedModelViewSetMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = PagamentoFuncionario.objects.all().order_by('-data_pagamento')
    serializer_class = PagamentoFuncionarioSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "rh"
    required_resource = "rh.folha"
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['funcionario']

class FolhaPagamentoViewSet(AuditedModelViewSetMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    queryset = FolhaPagamento.objects.all().order_by('-mes_referencia')
    serializer_class = FolhaPagamentoSerializer
    permission_classes = [permissions.IsAuthenticated, RequireModule, RequirePermission]
    required_module = "rh"
    required_resource = "rh.folha"
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['funcionario']
