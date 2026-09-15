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
import logging

from django.db.models.deletion import ProtectedError, RestrictedError
from django.db.utils import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as tratador_padrao

logger = logging.getLogger(__name__)

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

    if isinstance(exc, IntegrityError):
        return _integridade(exc, context)

    return None


def _nome_da_constraint(mensagem: str) -> str:
    """O nome da **regra** na mensagem do Postgres, não o da tabela.

    A mensagem completa é:

        new row for relation "modulopdca_itemcontrato" violates check
        constraint "pdca_item_contrato_quantidade_positiva"

    e há **dois** pares de aspas. Pegar o primeiro devolve a relação — que o
    suporte já sabe pela rota — em vez da regra, que é a informação que falta.
    Por isso a busca é pelo texto `constraint "…"`, e não pela primeira aspa.
    """
    marca = 'constraint "'
    inicio = mensagem.find(marca)
    if inicio == -1:
        return ""
    inicio += len(marca)
    fim = mensagem.find('"', inicio)
    return mensagem[inicio:fim] if fim != -1 else ""


def _integridade(exc, context):
    """Uma regra do **banco** recusou a escrita — e isso é 4xx, não 500.

    **É o mesmo defeito do `ProtectedError` que motivou este arquivo**, com
    outro nome. A regra está certa (uma `CheckConstraint` existe justamente para
    que nenhum caminho de escrita a contorne); o errado era como a recusa
    chegava: página de depuração do Django, rastro de renderizador no log, e
    nada que o cliente pudesse mostrar a quem preencheu o formulário.

    **Isto NÃO substitui a validação do serializer**, e a diferença importa: o
    serializer sabe *qual campo* e fala a língua de quem preenche ("a quantidade
    contratada precisa ser maior que zero"); este tratador é a **rede de baixo**,
    para o caminho que ninguém previu — comando de bancada, importação, uma
    constraint nova que o serializer ainda não espelha. Ele nomeia a regra em vez
    de inventar uma explicação que talvez esteja errada.

    O log continua com o traceback inteiro: 400 para o cliente **não** quer dizer
    que ninguém precisa olhar. Serializer que deixa passar o que o banco recusa é
    defeito nosso, e este log é como ele aparece.
    """
    mensagem = str(exc)
    constraint = _nome_da_constraint(mensagem)
    view = type(context.get("view")).__name__ if context.get("view") else "?"
    logger.warning(
        "integridade_recusou_escrita view=%s constraint=%s", view, constraint,
        exc_info=exc,
    )

    if "check constraint" in mensagem:
        return Response(
            {
                "detail": (
                    "O registro viola uma regra de integridade deste cadastro e "
                    "não pôde ser gravado. Confira os valores — em especial os "
                    "que não podem ser zero, negativos ou fora de uma faixa."
                ),
                "regra": constraint,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if "duplicate key" in mensagem or "unique constraint" in mensagem:
        return Response(
            {
                "detail": (
                    "Já existe um registro com este valor — ele precisa ser "
                    "único neste cadastro."
                ),
                "regra": constraint,
            },
            status=status.HTTP_409_CONFLICT,
        )

    # FK inexistente, `NOT NULL` sem valor e afins continuam **500**: não são
    # dado do usuário fora de faixa, são bug de quem escreveu o caminho — e
    # devolver 400 esconderia isso atrás de uma mensagem de formulário.
    return None
