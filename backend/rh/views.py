# backend/rh/views.py
# Este arquivo define a lógica da API (endpoints) para o app 'rh'.
# Cada ViewSet agrupa as operações CRUD (Create, Retrieve, Update, Delete) para um modelo.
from rest_framework import viewsets
from django.db.models import Q
import re
from .models import (
    Cargo,
    Funcionario,
    DadoMedicoFuncionario,
    DocumentoFuncionario,
    DadoBancarioFuncionario,
    PagamentoFuncionario,
    FolhaPagamento
)
from .serializers import (
    CargoSerializer,
    FuncionarioSerializer,
    DadoMedicoFuncionarioSerializer,
    DocumentoFuncionarioSerializer,
    DadoBancarioFuncionarioSerializer,
    PagamentoFuncionarioSerializer,
    FolhaPagamentoSerializer
)

class CargoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar cargos.
    """
    queryset = Cargo.objects.all()
    serializer_class = CargoSerializer
    # permission_classes = [permissions.IsAuthenticated]

class FuncionarioViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar funcionários.
    Inclui lógica especial para busca por telefone que normaliza os números.
    """
    queryset = Funcionario.objects.all()
    serializer_class = FuncionarioSerializer
    # permission_classes = [permissions.IsAuthenticated]
    
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

class DadoMedicoFuncionarioViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar dados médicos de funcionários.
    """
    queryset = DadoMedicoFuncionario.objects.all()
    serializer_class = DadoMedicoFuncionarioSerializer
    # permission_classes = [permissions.IsAuthenticated]

class DocumentoFuncionarioViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar documentos de funcionários.
    """
    queryset = DocumentoFuncionario.objects.all()
    serializer_class = DocumentoFuncionarioSerializer
    # permission_classes = [permissions.IsAuthenticated]

class DadoBancarioFuncionarioViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar dados bancários de funcionários.
    """
    queryset = DadoBancarioFuncionario.objects.all()
    serializer_class = DadoBancarioFuncionarioSerializer
    # permission_classes = [permissions.IsAuthenticated]

class PagamentoFuncionarioViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar pagamentos de funcionários.
    """
    queryset = PagamentoFuncionario.objects.all()
    serializer_class = PagamentoFuncionarioSerializer
    # permission_classes = [permissions.IsAuthenticated]

class FolhaPagamentoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para visualizar e editar folhas de pagamento.
    """
    queryset = FolhaPagamento.objects.all()
    serializer_class = FolhaPagamentoSerializer
    # permission_classes = [permissions.IsAuthenticated]
