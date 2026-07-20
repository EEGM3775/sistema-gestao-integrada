# backend/funcoeswhatsapp/identity.py
"""
Identidade telefone → pessoa, **dentro do tenant** já resolvido (Fase C, §4.2).

Porte do `services/api/authService.js` (Node), mas *in-process*: em vez de
chamar `/funcionarios/?telefone=` por HTTP, consulta o ORM sob o contexto de
tenant armado pela task. A comparação é por dígitos (ignora `+`, espaços e
pontuação) — o mesmo espírito da normalização do `rh.views.FuncionarioViewSet`,
mas tolerante ao `+` que a Meta não envia no `from`.

Papéis: 'funcionario' | 'cliente' | 'fornecedor' | 'unknown'. O papel decide
quais fluxos o remetente pode acionar; a autoria dos registros vem daqui.
"""
import re

ROLE_FUNCIONARIO = 'funcionario'
ROLE_CLIENTE = 'cliente'
ROLE_FORNECEDOR = 'fornecedor'
ROLE_UNKNOWN = 'unknown'


def so_digitos(telefone):
    return re.sub(r'\D', '', telefone or '')


def identificar(telefone):
    """Resolve `(pessoa, papel)` para o número (formato da Meta, sem `+`).

    Deve rodar sob `tenant_context(...)`: a RLS fail-closed garante que só as
    pessoas **do tenant** são consideradas. Não encontrado → `(None, 'unknown')`.
    """
    alvo = so_digitos(telefone)
    if not alvo:
        return None, ROLE_UNKNOWN

    funcionario = _achar_funcionario(alvo)
    if funcionario is not None:
        return funcionario, ROLE_FUNCIONARIO

    cliente = _achar_por_telefone_simples('clientes.models', 'Cliente', alvo)
    if cliente is not None:
        return cliente, ROLE_CLIENTE

    fornecedor = _achar_por_telefone_simples('fornecedores.models', 'Fornecedor', alvo)
    if fornecedor is not None:
        return fornecedor, ROLE_FORNECEDOR

    return None, ROLE_UNKNOWN


def _achar_funcionario(alvo):
    from rh.models import Funcionario
    # O conjunto por tenant é pequeno; compara os dois telefones por dígitos.
    for f in Funcionario.objects.exclude(telefone_celular='', telefone_pessoal='').only(
        'funcionario_id', 'nome_completo', 'telefone_celular', 'telefone_pessoal', 'usuario', 'tenant',
    ):
        if alvo in (so_digitos(f.telefone_celular), so_digitos(f.telefone_pessoal)):
            return f
    return None


def _achar_por_telefone_simples(modulo, classe, alvo):
    import importlib
    modelo = getattr(importlib.import_module(modulo), classe)
    for obj in modelo.objects.exclude(telefone='').only('pk', 'telefone', 'tenant'):
        if so_digitos(obj.telefone) == alvo:
            return obj
    return None
