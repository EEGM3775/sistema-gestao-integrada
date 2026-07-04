# modulodiario/permissions.py
from rest_framework import permissions
from django.core.exceptions import ObjectDoesNotExist


def get_funcionario(user):
    """
    Retorna o Funcionario vinculado ao usuário (funcionario_profile), ou None.

    Acessar `user.funcionario_profile` quando não existe o vínculo levanta
    RelatedObjectDoesNotExist (subclasse de ObjectDoesNotExist, NÃO de
    AttributeError) — por isso getattr/hasattr não bastam e seria um 500.
    """
    try:
        return user.funcionario_profile
    except ObjectDoesNotExist:
        return None


def pode_contribuir(funcionario, obra):
    """Equipe ∪ responsáveis técnicos da obra podem adicionar conteúdo."""
    if funcionario is None:
        return False
    return (
        obra.equipe.filter(pk=funcionario.pk).exists()
        or obra.responsaveis_tecnicos.filter(pk=funcionario.pk).exists()
    )


def pode_moderar(funcionario, obra):
    """Apenas responsáveis técnicos editam/excluem qualquer contribuição."""
    if funcionario is None:
        return False
    return obra.responsaveis_tecnicos.filter(pk=funcionario.pk).exists()


class PodeModerarDiario(permissions.BasePermission):
    """
    Leitura livre (escopada por tenant). Escrita por objeto (PUT/PATCH/DELETE
    de uma entrada ou documento) exige ser responsável técnico da obra.
    O objeto pode ser EntradaDiario, DocumentoDiario ou DiarioObra.
    """
    message = "Apenas responsáveis técnicos da obra podem editar ou excluir contribuições do diário."

    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        obra = getattr(obj, 'obra', None) or getattr(getattr(obj, 'diario_obra', None), 'obra', None)
        if obra is None:
            return False
        return pode_moderar(get_funcionario(request.user), obra)


# Compat: nome antigo ainda referenciado em pontos do código/migrações antigas.
class IsResponsavelTecnicoDaObra(PodeModerarDiario):
    pass
