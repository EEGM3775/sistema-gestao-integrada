"""O tratador de exceções da API — e a única coisa que ele resolve.

**O defeito que o motivou.** Uma FK `PROTECT` existe para impedir que se apague
o registro do qual outro depende: o calendário de trabalho que um cronograma
usa, por exemplo. A recusa é correta — o problema é *como* ela chegava a quem
pediu. O `ProtectedError` do Django não é uma `APIException`, então o DRF o
deixava subir: o cliente recebia **500**, o log guardava um rastro de renderizador
de template, e a página de depuração do Django ainda quebrava por cima disso ao
tentar imprimir os objetos protegidos (`DoesNotExist` num atributo diferido).
Três camadas de ruído para uma regra de negócio que caberia numa frase.

Achado escrevendo o E2E da PDCA.1 (excluir a obra do teste), mas **não é da
PDCA**: vale para toda `PROTECT` do sistema, e o sistema tem várias.

**Por que o texto não usa `str(obj)`.** Os objetos que vêm no `ProtectedError`
podem estar com campos diferidos, e imprimir um deles dispara uma ida ao banco
por uma linha que talvez já não exista — que é exatamente o que quebrou a página
de erro. O nome do modelo e a chave primária bastam para o suporte achar a
linha, e não custam consulta nenhuma.
"""
from django.db.models.deletion import ProtectedError, RestrictedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as tratador_padrao

#: Quantos dependentes são nomeados na mensagem. Acima disso a lista deixa de
#: informar e vira parede de texto; o número total continua na resposta.
MAXIMO_NOMEADOS = 5


def _identificar(objetos) -> list[str]:
    nomes = []
    for obj in list(objetos)[:MAXIMO_NOMEADOS]:
        nomes.append(f"{obj._meta.verbose_name} #{obj.pk}")
    return nomes


def tratador(exc, context):
    """Mantém o comportamento do DRF e só acrescenta as duas exceções de
    integridade referencial que ele não conhece."""
    resposta = tratador_padrao(exc, context)
    if resposta is not None:
        return resposta

    if isinstance(exc, (ProtectedError, RestrictedError)):
        dependentes = getattr(exc, "protected_objects", None)
        if dependentes is None:
            dependentes = getattr(exc, "restricted_objects", [])
        dependentes = list(dependentes)
        nomes = _identificar(dependentes)
        sobra = len(dependentes) - len(nomes)
        detalhe = (
            "Não é possível excluir: outro registro depende deste. "
            + ("Dependentes: " + ", ".join(nomes) if nomes else "")
            + (f" e mais {sobra}." if sobra > 0 else ".")
        )
        return Response(
            {
                "detail": detalhe.strip(),
                "dependentes": nomes,
                "total_dependentes": len(dependentes),
            },
            status=status.HTTP_409_CONFLICT,
        )

    return None
