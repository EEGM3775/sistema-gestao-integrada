# backend/funcoesimpexp/registro.py
"""IE.0 — o contrato: como um módulo declara o que sai e o que entra.

Este arquivo é o vocabulário inteiro do funcoesimpexp. **O motor não conhece
modelo nenhum**; ele só sabe percorrer `Coluna` e chamar os ganchos de um
`Recurso`. Quem sabe o que é um item orçado, um cliente ou uma conta a pagar é o
módulo dono, e ele conta isso aqui.

A escolha por declaração (e não por reflexão sobre o ORM, como fazia o v01) é o
que mantém a régua da planta §2 aplicável: `Model.objects.values()` devolve
`empreendimento_id = 47` e `cpf_cnpj` em claro — nomes de coluna de banco, sem
rótulo, sem tipo e sem gate de PII. Uma declaração custa ~15 linhas por recurso e
paga com as três saídas da §5 saindo de uma fonte só (R2).

`Recurso` é classe comum, não `dataclass`, de propósito: os ganchos são
**métodos** que a subclasse sobrescreve, e o `__init__` gerado por `@dataclass`
atribuiria os defaults por cima deles na instanciação — apagando em silêncio o
`queryset` que o módulo acabou de escrever.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal


class RecursoInvalido(Exception):
    """Declaração que não obedece à régua — erro de programação, não de uso."""


class RecursoDesconhecido(KeyError):
    """Pediram um recurso que ninguém registrou."""


class ContextoInvalido(Exception):
    """Destino ausente, de outro tenant ou fechado para escrita.

    Erro **de uso**, não de programação: quem chama traduz para 400/404/409
    conforme o caso. Existe separado de `RecursoInvalido` justamente por isso —
    declaração torta derruba o boot, destino errado devolve mensagem ao usuário.
    """


TIPOS_SUPORTADOS = (str, int, Decimal, bool)


@dataclass(frozen=True)
class Coluna:
    """Uma coluna do arquivo — e, por R2, também do modelo e do validador.

    `campo` é o nome interno (o que os ganchos recebem e devolvem); `rotulo` é o
    que aparece no cabeçalho do arquivo. Os dois são distintos de propósito:
    renomear o rótulo para o usuário não pode quebrar a gravação, e mudar o campo
    interno não pode mudar o arquivo que o cliente já usa como modelo.
    """

    campo: str
    rotulo: str
    tipo: type = str
    obrigatoria: bool = False
    exemplo: str = ""
    # Sinônimos aceitos no cabeçalho de um arquivo importado, além do rótulo.
    # Alimentam o de-para automático (R4); o que não casar vai para o operador
    # mapear à mão, nunca para adivinhação.
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.campo or not self.rotulo:
            raise RecursoInvalido("Coluna precisa de `campo` e `rotulo`.")
        if self.tipo not in TIPOS_SUPORTADOS:
            raise RecursoInvalido(
                f"Coluna '{self.campo}': tipo {self.tipo!r} não suportado. "
                "Use str, int, Decimal ou bool."
            )

    @property
    def numerica(self) -> bool:
        return self.tipo in (Decimal, int)


class Recurso:
    """O que um módulo declara. Subclasse, preencha e decore com `@registrar(id)`.

    Um recurso pode ser só de exportação (curva ABC, DRE), só de importação
    (contagem de inventário) ou os dois — o motor descobre pelo que foi
    sobrescrito: `queryset` habilita a saída, `aplicar_linha` habilita a entrada.

    **Contexto.** O registry guarda uma instância por processo, sem estado. Quando
    a operação tem um *destino* dentro do módulo — qual banco de preço recebe as
    linhas, qual orçamento é a planilha —, o motor não passa esse dado gancho a
    gancho: ele chama `com_contexto()`, que devolve uma **cópia rasa** com
    `self.contexto` preenchido, e é nela que os ganchos rodam. A instância do
    registry nunca é tocada, então duas importações simultâneas de bancos
    diferentes não se cruzam — que é o defeito que guardar o destino no singleton
    produziria, e produziria só sob concorrência, em produção.
    """

    # --- identidade -------------------------------------------------------
    id: str = ""
    rotulo: str = ""
    modulo: str = ""
    # Destino da operação (`{"banco": 12}`). Vazio na instância do registry;
    # preenchido nas cópias que `com_contexto` devolve.
    contexto: dict = {}

    # --- acesso (planta §3 / R11) ----------------------------------------
    # Conjunto INTEIRO exigido: meia permissão bloqueia. Inclui a permissão de
    # máscara de toda coluna sensível declarada — se a exportação traz CPF, o
    # `cadastro.cliente_doc.view` entra aqui. É a única obrigação que a regra
    # simplificada transfere para quem declara.
    permissoes_exigidas: tuple[str, ...] = ()

    # --- forma ------------------------------------------------------------
    colunas: tuple[Coluna, ...] = ()
    # Campo que decide criar × atualizar (R3). Sem ele não há importação
    # idempotente — e sem idempotência, reimportar duplica tudo.
    chave: str = ""
    formatos_saida: tuple[str, ...] = ("xlsx", "csv", "pdf")
    formatos_entrada: tuple[str, ...] = ("xlsx", "csv")
    # Chaves de contexto que a tela precisa perguntar antes do upload. Publicado
    # em `descrever()` para o wizard montar o passo de destino sem saber de
    # domínio — sem isso o frontend teria um `if recurso == "orcamento.banco"`
    # escrito à mão, que é exatamente o acoplamento que o registry evita.
    contexto_requerido: tuple[str, ...] = ()

    # ------------------------------------------------------------------
    # Ganchos — sobrescreva o que o recurso oferece
    # ------------------------------------------------------------------

    def queryset(self, request, recorte: dict):
        """Linhas a exportar, já escopadas por tenant e com o recorte da tela (R7).

        Devolve iterável de dicionários `campo -> valor` (ou de objetos, se
        `serializar_objeto` for sobrescrito).
        """
        raise NotImplementedError

    def serializar_objeto(self, obj) -> dict:
        """Objeto do ORM → `campo -> valor`. Só quando `queryset` devolve objetos."""
        return {c.campo: getattr(obj, c.campo, None) for c in self.colunas}

    def contar(self, request, recorte: dict) -> int | None:
        """Quantas linhas o recorte tem, sem materializá-las (R10).

        Num `QuerySet` sai um `COUNT` no banco; numa lista, o `len`. Gerador não
        tem como ser contado sem ser consumido, e aí a resposta honesta é `None`
        = "não sei" — o motor então trata como pequeno. Recurso que espera volume
        e devolve gerador deve sobrescrever isto, senão troca o job por um
        timeout.
        """
        try:
            alvo = self.queryset(request, recorte)
        except NotImplementedError:
            return None
        contador = getattr(alvo, "count", None)
        if callable(contador):
            try:
                return int(contador())
            except TypeError:  # list.count exige argumento — não é o do ORM
                pass
        try:
            return len(alvo)
        except TypeError:
            return None

    def validar_linha(self, dados: dict) -> str:
        """Regra de negócio do módulo. Devolve o motivo da recusa, ou "" se passa.

        Roda na conferência, antes de qualquer gravação — é aqui que "quantidade
        negativa" ou "obra de outro tenant" viram linha inválida em vez de erro
        no meio do lote.
        """
        return ""

    def localizar(self, dados: dict, tenant_id):
        """Objeto existente com esta chave, ou `None`. É o que decide criar × atualizar."""
        raise NotImplementedError

    def aplicar_linha(self, dados: dict, existente, tenant_id) -> dict | None:
        """Grava a linha. Devolve o que `desfazer_linha` precisa para reverter (R6).

        Convenção: `{"acao": "criou", "pk": ...}` ou
        `{"acao": "atualizou", "pk": ..., "antes": {...}}`. `None` = sem reversão.
        """
        raise NotImplementedError

    def desfazer_linha(self, estado_anterior: dict, tenant_id) -> None:
        """Reverte uma linha aplicada. Sem isto, o lote não é desfazível."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Contexto — o destino da operação dentro do módulo
    # ------------------------------------------------------------------

    def com_contexto(self, contexto: dict | None):
        """Cópia deste recurso amarrada a um destino. Ver a nota da classe."""
        instancia = copy.copy(self)
        instancia.contexto = dict(contexto or {})
        return instancia

    def validar_contexto(self, contexto: dict, user, tenant_id) -> dict:
        """Resolve e valida o destino **antes** de ler o arquivo.

        Devolve o contexto normalizado (o que será persistido no lote) ou levanta
        `ContextoInvalido`. Rodar antes da leitura é deliberado: descobrir que o
        banco está travado depois de classificar 40 mil linhas é fazer o usuário
        esperar para receber um "não".

        O padrão não exige nada — recurso sem destino (a carteira de clientes
        inteira, a curva ABC) não precisa declarar isto.
        """
        return dict(contexto or {})

    def checar_quota_objeto(self, novas: int, limites: dict | None, tenant_id) -> None:
        """Teto de **acervo** do módulo, se houver (planta §9).

        O motor cuida sozinho de `importacao_linhas`, que é quota de *operação* e
        vale para todo recurso. Teto de acervo é outra coisa e é sempre do
        módulo: `banco_preco_linhas` conta linhas de tabela de preço e não faria
        sentido aplicado a uma importação de clientes. Quem tem acervo declara o
        seu aqui e levanta `LimiteDoPlano`.
        """
        return None

    def rotulo_do_contexto(self) -> str:
        """Como o destino aparece no cabeçalho de procedência (R9). Ex.: "Banco: Prefeitura"."""
        return ""

    # ------------------------------------------------------------------
    # Introspecção usada pelo motor
    # ------------------------------------------------------------------

    @classmethod
    def _sobrescreveu(cls, nome: str) -> bool:
        return getattr(cls, nome, None) is not getattr(Recurso, nome, None)

    @property
    def exporta(self) -> bool:
        return type(self)._sobrescreveu("queryset")

    @property
    def importa(self) -> bool:
        return type(self)._sobrescreveu("aplicar_linha")

    @property
    def desfazivel(self) -> bool:
        return type(self)._sobrescreveu("desfazer_linha")

    @property
    def coluna_chave(self) -> Coluna | None:
        return self.coluna_por_campo(self.chave)

    def coluna_por_campo(self, campo: str) -> Coluna | None:
        return next((c for c in self.colunas if c.campo == campo), None)

    def obrigatorias(self) -> tuple[Coluna, ...]:
        return tuple(c for c in self.colunas if c.obrigatoria)

    # ------------------------------------------------------------------
    # A régua, verificada no registro
    # ------------------------------------------------------------------

    def validar(self) -> None:
        """Falha no import do módulo, não no clique do usuário.

        Declaração torta é erro de programação: descobrir no boot custa um
        traceback; descobrir no request custa um arquivo errado na mão de um
        cliente.
        """
        if not self.id or "." not in self.id:
            raise RecursoInvalido(f"id do recurso deve ser 'modulo.recurso' (veio {self.id!r}).")
        if not self.rotulo:
            raise RecursoInvalido(f"{self.id}: falta `rotulo`.")
        if not self.modulo:
            raise RecursoInvalido(f"{self.id}: falta `modulo`.")
        if not self.permissoes_exigidas:
            raise RecursoInvalido(
                f"{self.id}: `permissoes_exigidas` vazio. A planta §3 não admite recurso "
                "sem gate — conjunto vazio liberaria import/export para qualquer um."
            )
        if not self.colunas:
            raise RecursoInvalido(f"{self.id}: falta declarar `colunas`.")
        campos = [c.campo for c in self.colunas]
        repetidos = sorted({c for c in campos if campos.count(c) > 1})
        if repetidos:
            raise RecursoInvalido(f"{self.id}: colunas repetidas: {repetidos}.")
        if not (self.exporta or self.importa):
            raise RecursoInvalido(
                f"{self.id}: nem `queryset` nem `aplicar_linha` — recurso não faz nada."
            )
        # R3 vale só para quem importa: exportação não precisa de chave.
        if self.importa:
            if not self.chave:
                raise RecursoInvalido(
                    f"{self.id}: importação sem `chave`. Sem chave de identidade, reimportar "
                    "o mesmo arquivo duplica tudo (R3)."
                )
            if self.coluna_chave is None:
                raise RecursoInvalido(
                    f"{self.id}: `chave` aponta para '{self.chave}', que não está em `colunas`."
                )
            if not type(self)._sobrescreveu("localizar"):
                raise RecursoInvalido(
                    f"{self.id}: importação exige `localizar` — é como o motor decide se a "
                    "linha cria ou atualiza."
                )

    def descrever(self) -> dict:
        """O que a API publica para o frontend montar botão e wizard."""
        return {
            "id": self.id,
            "rotulo": self.rotulo,
            "modulo": self.modulo,
            "exporta": self.exporta,
            "importa": self.importa,
            "desfazivel": self.desfazivel,
            "chave": self.chave,
            "formatos_saida": list(self.formatos_saida),
            "formatos_entrada": list(self.formatos_entrada),
            "contexto_requerido": list(self.contexto_requerido),
            "colunas": [
                {
                    "campo": c.campo,
                    "rotulo": c.rotulo,
                    "tipo": c.tipo.__name__,
                    "obrigatoria": c.obrigatoria,
                    "exemplo": c.exemplo,
                }
                for c in self.colunas
            ],
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRO: dict[str, Recurso] = {}


def registrar(recurso_id: str):
    """Decorador de classe: `@registrar("orcamento.planilha")`.

    Registra uma **instância** — recurso não tem estado por request, então uma
    só serve o processo inteiro.
    """

    def decorador(cls):
        if not isinstance(cls, type) or not issubclass(cls, Recurso):
            raise RecursoInvalido("@registrar decora subclasse de Recurso.")
        cls.id = recurso_id
        instancia = cls()
        instancia.validar()
        anterior = _REGISTRO.get(recurso_id)
        if anterior is not None and type(anterior) is not cls:
            raise RecursoInvalido(
                f"Recurso '{recurso_id}' registrado duas vezes — o id é a chave do endpoint "
                "e colisão faria um módulo servir o dado do outro."
            )
        _REGISTRO[recurso_id] = instancia
        return cls

    return decorador


def obter(recurso_id: str) -> Recurso:
    try:
        return _REGISTRO[recurso_id]
    except KeyError:
        raise RecursoDesconhecido(recurso_id) from None


def listar() -> tuple[Recurso, ...]:
    return tuple(_REGISTRO[k] for k in sorted(_REGISTRO))
