"""O listão dos títulos — busca, ordem e agrupamento no banco.

Contas a receber passaram de 86 mil linhas num tenant, e a tela antiga era uma
tabela paginada que pedia o nome de cada cliente a uma lista de 300 opções: o
cliente nº 301 aparecia como "Cliente #1234", a busca só olhava a descrição e
não havia como ordenar por cliente. A grade nova é a da carteira de clientes
(``clientes/carteira.py``): rolagem infinita, toda coluna ordena e o usuário
empilha **agrupamentos** cujos subtotais saem de um ``GROUP BY`` sobre o recorte
inteiro — nunca sobre a página carregada, que daria número errado com cara de
certo.

Um motor para as três listas (receber, pagar, boletos). Cada ``Fonte`` diz o
que anotar, por onde ordenar e por onde agrupar; o ViewSet só aponta para ela.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import (
    Case, CharField, Count, DecimalField, F, IntegerField, Q, QuerySet, Sum, Value, When,
)
from django.db.models.functions import Coalesce, Lower, NullIf, TruncMonth
from django.utils import timezone
from rest_framework import filters

from clientes.carteira import chave_natural
from nucleo.busca import BuscaSemAcento

from .models import StatusConta

DINHEIRO = DecimalField(max_digits=15, decimal_places=2)
ZERO = Value(Decimal("0"), output_field=DINHEIRO)
EM_ABERTO = (StatusConta.ABERTO, StatusConta.PARCIAL)

# Os cortes do aging do dashboard e da carteira: "31-60 dias" quer dizer a mesma
# coisa nas três telas. `a_vencer` e `encerrado` completam a partição — todo
# título cai em exatamente uma faixa, então os subtotais somam o total.
FAIXAS = {
    "a_vencer": "A vencer",
    "d1_30": "Vencido 1-30 dias",
    "d31_60": "Vencido 31-60 dias",
    "d61_90": "Vencido 61-90 dias",
    "d90_mais": "Vencido há mais de 90 dias",
    "encerrado": "Quitado ou cancelado",
}

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def hoje_local() -> date:
    return timezone.localdate()


def saldo_de(prefixo: str = ""):
    """Saldo em aberto como expressão — espelha a property `saldo_aberto`."""
    p = prefixo
    return (
        F(f"{p}valor") + F(f"{p}juros") + F(f"{p}multa")
        - F(f"{p}desconto") - F(f"{p}valor_pago")
    )


def faixa_do_titulo(hoje: date, status: str = "status", vencimento: str = "data_vencimento"):
    aberto = Q(**{f"{status}__in": EM_ABERTO})
    return Case(
        When(~aberto, then=Value("encerrado")),
        When(Q(**{f"{vencimento}__gte": hoje}), then=Value("a_vencer")),
        When(Q(**{f"{vencimento}__gte": hoje - timedelta(days=30)}), then=Value("d1_30")),
        When(Q(**{f"{vencimento}__gte": hoje - timedelta(days=60)}), then=Value("d31_60")),
        When(Q(**{f"{vencimento}__gte": hoje - timedelta(days=90)}), then=Value("d61_90")),
        default=Value("d90_mais"),
        output_field=CharField(),
    )


def filtro_de_faixa(faixa: str, hoje: date, status: str = "status", vencimento: str = "data_vencimento") -> Q:
    """O mesmo corte de `faixa_do_titulo`, como filtro — é o que abre o grupo."""
    aberto = Q(**{f"{status}__in": EM_ABERTO})
    v = vencimento
    cortes = {
        "encerrado": ~aberto,
        # Atalho da tela ("Vencidas"): as quatro faixas de atraso juntas.
        "vencido": aberto & Q(**{f"{v}__lt": hoje}),
        "a_vencer": aberto & Q(**{f"{v}__gte": hoje}),
        "d1_30": aberto & Q(**{f"{v}__lt": hoje, f"{v}__gte": hoje - timedelta(days=30)}),
        "d31_60": aberto & Q(**{f"{v}__lt": hoje - timedelta(days=30), f"{v}__gte": hoje - timedelta(days=60)}),
        "d61_90": aberto & Q(**{f"{v}__lt": hoje - timedelta(days=60), f"{v}__gte": hoje - timedelta(days=90)}),
        "d90_mais": aberto & Q(**{f"{v}__lt": hoje - timedelta(days=90)}),
    }
    return cortes.get(faixa, Q())


def filtro_de_mes(valor: str, campo: str = "data_vencimento") -> Q:
    """`2026-03` (ou `2026-03-01`, a chave que o grupo devolve) → o mês inteiro."""
    try:
        ano, mes = (int(p) for p in str(valor).split("-")[:2])
    except ValueError:
        return Q(pk__in=[])
    return Q(**{f"{campo}__year": ano, f"{campo}__month": mes})


def rotulo_do_mes(valor) -> str:
    if not valor:
        return "— sem data —"
    return f"{MESES[valor.month - 1]}/{valor.year}"


@dataclass(frozen=True)
class Dimensao:
    """Um eixo de agrupamento.

    `campo` vai ao GROUP BY e volta como **chave**; `filtro` é o parâmetro que a
    tela manda de volta ao abrir o grupo — por isso a chave tem de ser o que o
    filtro aceita (agrupar por nome e filtrar por id nunca se encontram).
    """
    campo: str
    rotulo: str
    filtro: str
    rotulo_campo: str | None = None
    rotulos: dict | None = None
    formatar: object = None


@dataclass(frozen=True)
class Fonte:
    """O que uma lista de títulos sabe fazer: anotar, ordenar e agrupar."""
    anotacoes: object  # (hoje) -> dict[str, expressão]
    ordenacoes: dict[str, list[str]]
    padrao: str
    dimensoes: dict[str, Dimensao]
    # Campos de valor que o subtotal soma. `saldo` e `vencido` só contam título
    # em aberto — somar o saldo de um quitado é somar zero, mas somar o de um
    # cancelado seria cobrar o que ninguém deve.
    valor: str = "valor"
    tem_saldo: bool = True
    busca_documental: tuple[str, ...] = field(default=())


def anotar(qs: QuerySet, fonte: Fonte, hoje: date, so: set[str] | None = None) -> QuerySet:
    """Anota só o que a pergunta usa.

    Cada anotação de nome (`cliente_nome`, `empreendimento_nome`) é um JOIN, e a
    política de RLS põe em cada tabela juntada um filtro que o planejador não
    sabe estimar — ele supõe 1% das linhas. Anotar tudo sempre fazia o Postgres
    juntar as 86 mil contas a seis tabelas antes de ordenar para mostrar cem.
    """
    todas = fonte.anotacoes(hoje)
    ja = set(qs.query.annotations)
    escolhidas = {
        k: v for k, v in todas.items() if (so is None or k in so) and k not in ja
    }
    return qs.annotate(**escolhidas) if escolhidas else qs


def ordenar(qs: QuerySet, fonte: Fonte, chave: str, hoje: date | None = None) -> QuerySet:
    """A chave pedida pela tela (`cliente`, `-saldo`) nos termos de `order_by`.

    Sempre com o desempate pela chave primária: sem ele, duas linhas de mesmo
    valor trocam de lugar entre páginas e a rolagem infinita repete uma e come a
    outra, sem nada na tela denunciando.
    """
    nome = (chave or "").lstrip("-")
    campos = fonte.ordenacoes.get(nome)
    if not campos:
        nome, campos = fonte.padrao.lstrip("-"), fonte.ordenacoes[fonte.padrao.lstrip("-")]
        chave = fonte.padrao
    descendente = chave.startswith("-")
    qs = anotar(qs, fonte, hoje or hoje_local(), so=set(campos))
    termos = [
        F(c).desc(nulls_last=True) if descendente else F(c).asc(nulls_last=True)
        for c in campos
    ]
    return qs.order_by(*termos, "pk")


def pagina_em_dois_passos(queryset: QuerySet, paginar, completar) -> list | None:
    """A página pelos ids primeiro, as linhas inteiras depois.

    `paginar` é o `paginate_queryset` do DRF e recebe só os ids na ordem pedida —
    sem `select_related`, sem as anotações que a ordem não usa. `completar`
    devolve o queryset completo (nomes, rateios, boletos) e é consultado só para
    os ids da página, que voltam na ordem em que o primeiro passo os deixou.
    """
    ids = paginar(queryset.values_list("pk", flat=True))
    if ids is None:
        return None
    ids = list(ids)
    por_id = {obj.pk: obj for obj in completar().filter(pk__in=ids)}
    return [por_id[i] for i in ids if i in por_id]


def _somas(fonte: Fonte, hoje: date) -> dict:
    """As somas do recorte. Prefixo `soma_` porque `valor` é campo do modelo e
    `saldo` é anotação da grade — o mesmo nome no agregado colide com os dois."""
    somas = {"contagem": Count("pk"), "soma_valor": Coalesce(Sum(fonte.valor, output_field=DINHEIRO), ZERO)}
    if fonte.tem_saldo:
        aberto = Q(status__in=EM_ABERTO)
        somas["soma_saldo"] = Coalesce(Sum("saldo", filter=aberto, output_field=DINHEIRO), ZERO)
        somas["soma_vencido"] = Coalesce(
            Sum("saldo", filter=aberto & Q(data_vencimento__lt=hoje), output_field=DINHEIRO), ZERO,
        )
    return somas


def _sem_prefixo(linha: dict) -> dict:
    saida = {"contagem": linha["contagem"], "valor": str(linha["soma_valor"])}
    if "soma_saldo" in linha:
        saida["saldo"] = str(linha["soma_saldo"])
        saida["vencido"] = str(linha["soma_vencido"])
    return saida


def totais(qs: QuerySet, fonte: Fonte, hoje: date) -> dict:
    return _sem_prefixo(qs.order_by().aggregate(**_somas(fonte, hoje)))


def _ordem_do_grupo(dim: Dimensao):
    """A chave de ordenação de um nível de agrupamento."""
    if dim.rotulos:
        return Case(
            *[When(**{dim.campo: chave}, then=Value(i)) for i, chave in enumerate(dim.rotulos)],
            default=Value(len(dim.rotulos)), output_field=IntegerField(),
        )
    if dim.campo.endswith(("__quadra", "__lote", "__bloco_torre")):
        return chave_natural(dim.campo)
    if dim.rotulo_campo:
        return NullIf(Lower(dim.rotulo_campo), Value(""))
    return F(dim.campo)


def agrupar(qs: QuerySet, fonte: Fonte, niveis: list[str], hoje: date, teto_niveis: int) -> list[dict]:
    """Subtotais por combinação de níveis, calculados no banco.

    Devolve a lista **achatada** de combinações (a tela monta a árvore), como a
    carteira: com `por=empreendimento,mes` vem uma linha por par, e o nível de
    cima é a soma dos filhos. Achatar evita uma consulta por grupo aberto.
    """
    dims = fonte.dimensoes
    validos = [n for n in niveis if n in dims][:teto_niveis]
    if not validos:
        return []
    campos = [dims[n].campo for n in validos]
    rotulos_campos = [dims[n].rotulo_campo for n in validos]
    agrupamento = campos + [c for c in rotulos_campos if c]

    # A ordem de quem lê: quadra "2" antes da "10" (é texto), nomes em ordem
    # alfabética, faixa e status na ordem em que foram declarados; vazio no fim.
    ordens = {f"_ordem_{i}": _ordem_do_grupo(dims[n]) for i, n in enumerate(validos)}
    linhas = (
        qs.order_by().annotate(**ordens).values(*agrupamento, *ordens)
        .annotate(**_somas(fonte, hoje))
        .order_by(*[F(alias).asc(nulls_last=True) for alias in ordens], *agrupamento)
    )

    saida = []
    for linha in linhas:
        chaves = [linha[c] for c in campos]
        saida.append({
            "niveis": validos,
            "filtros": [dims[n].filtro for n in validos],
            "chaves": ["" if v is None else _chave(v) for v in chaves],
            "rotulos": [
                _rotulo(dims[n], linha[rc] if rc else v)
                for n, v, rc in zip(validos, chaves, rotulos_campos)
            ],
            **_sem_prefixo(linha),
        })
    return saida


def _chave(valor) -> str:
    if hasattr(valor, "isoformat"):
        return valor.isoformat()[:7]  # mês: a chave é `AAAA-MM`
    return str(valor)


def _rotulo(dim: Dimensao, valor) -> str:
    if dim.formatar:
        return dim.formatar(valor)
    if valor in (None, ""):
        return "— sem informação —"
    if dim.rotulos:
        return dim.rotulos.get(str(valor), str(valor))
    return str(valor)


# ─── Busca ────────────────────────────────────────────────────────────────────

class BuscaDeTitulos(BuscaSemAcento):
    """A busca sem acento, com três coisas que o listão financeiro precisa.

    1. **Os campos dependem de quem pergunta.** Achar um título pelo CPF é ler o
       CPF — quem não desmascara o documento não pode usá-lo como oráculo
       ("existe alguém com este CPF?"). A view decide em `campos_de_busca`.
    2. **Documento digitado com pontuação.** O banco guarda só dígitos; quem cola
       `123.456.789-00` do contrato merece achar o cliente.
    3. **Cada palavra casa pelo começo de uma palavra do dado.** Com o `icontains`,
       `ana ro` achava "Ana Ribei**ro**" e `aco` achava "Fund**aço**es" em toda
       medição da Torre A, enterrando o "Aço Forte" que a pessoa queria (itens 51
       e 53 do dono, 01/10/2026). Quem digita o começo de uma palavra quer a
       palavra que começa assim — é como o Google e a agenda do celular acham.
    """

    def get_search_fields(self, view, request):
        if hasattr(view, "campos_de_busca"):
            return view.campos_de_busca(request)
        return super().get_search_fields(view, request)

    def filter_queryset(self, request, queryset, view):
        """Cada palavra tem de casar em algum campo — como o `SearchFilter` —,
        mas o campo de outra tabela vira `IN (subconsulta)`.

        O `SearchFilter` faz JOIN e compara `UNACCENT(nome)` linha a linha: para
        achar um cliente entre 2 mil, varria 86 mil contas juntadas (1 s). Pela
        subconsulta, o nome é procurado na tabela de clientes e as contas são
        filtradas pelo id — o Postgres a resolve uma vez só.
        """
        campos = self.get_search_fields(view, request)
        termos = self.get_search_terms(request)
        if not campos or not termos:
            return queryset
        for termo in termos:
            alvo = Q()
            for campo in campos:
                alvo |= _condicao_de_busca(queryset.model, campo, termo)
            queryset = queryset.filter(alvo)
        return queryset

    def get_search_terms(self, request):
        termos = super().get_search_terms(request)
        saida = []
        for termo in termos:
            so_digitos = "".join(ch for ch in termo if ch.isdigit())
            documento = so_digitos and all(ch.isdigit() or ch in ".-/" for ch in termo) and len(so_digitos) >= DIGITOS_DE_DOCUMENTO
            saida.append(so_digitos if documento else termo)
        return saida


def _condicao_de_busca(modelo, campo: str, termo: str) -> Q:
    """`cliente__nome_completo` → `cliente IN (clientes cujo nome contém termo)`.

    Recursivo: o boleto procura o cliente dentro da conta dentro do boleto. O
    `_base_manager` inclui o que está na lixeira — quem procura uma parcela de um
    cliente excluído ainda precisa achá-la; o isolamento entre empresas é da RLS.
    """
    if "__" not in campo:
        return _casa_termo(campo, termo)
    relacao, resto = campo.split("__", 1)
    relacionado = modelo._meta.get_field(relacao).related_model
    sub = relacionado._base_manager.filter(_condicao_de_busca(relacionado, resto, termo)).values("pk")
    return Q(**{f"{relacao}__in": sub})


#: Número com cara de documento (CPF, CNPJ, nosso número, nº de contrato): a
#: pessoa cola um trecho de qualquer ponto, então casa em qualquer lugar.
DIGITOS_DE_DOCUMENTO = 5


def _casa_termo(campo: str, termo: str) -> Q:
    """O termo no começo de uma palavra do campo, sem acento nem caixa.

    `\\m` é o começo de palavra das expressões regulares do Postgres; o
    `unaccent` é bilateral, então `aco` acha "Aço" e `aço` acha "aco". Número
    curto (quadra, lote) ignora o zero à esquerda: `5` acha o lote "05".
    """
    if termo.isdigit() and len(termo) >= DIGITOS_DE_DOCUMENTO:
        return Q(**{f"{campo}__unaccent__icontains": termo})
    padrao = r"\m0*" + termo if termo.isdigit() else r"\m" + re.escape(termo)
    return Q(**{f"{campo}__unaccent__iregex": padrao})


class OrdenacaoDoListao(filters.BaseFilterBackend):
    """`?ordering=cliente` / `?ordering=-saldo` pelas chaves da `Fonte`.

    Substitui o `OrderingFilter` do DRF nestas três listas porque ele não sabe
    duas coisas: ordenar por uma chave **composta** (a unidade é quadra › lote) e
    desempatar pela chave primária.
    """

    def filter_queryset(self, request, queryset, view):
        return ordenar(queryset, view.fonte_listao, request.query_params.get("ordering") or "")


# ─── As três fontes ──────────────────────────────────────────────────────────

_FAIXA = Dimensao(campo="faixa", rotulo="Situação do vencimento", filtro="faixa", rotulos=FAIXAS)
_MES = Dimensao(campo="mes", rotulo="Mês de vencimento", filtro="mes", formatar=rotulo_do_mes)


def _anotacoes_receber(hoje: date) -> dict:
    return {
        "cliente_nome": F("cliente__nome_completo"),
        "empreendimento_nome": F("empreendimento__empreendimento"),
        "quadra_ord": chave_natural("cliente_empreendimento__unidade__quadra"),
        "lote_ord": chave_natural("cliente_empreendimento__unidade__lote"),
        "apto_ord": chave_natural("cliente_empreendimento__unidade__apto"),
        "saldo": saldo_de(),
        "faixa": faixa_do_titulo(hoje),
        "mes": TruncMonth("data_vencimento"),
    }


RECEBER = Fonte(
    anotacoes=_anotacoes_receber,
    ordenacoes={
        "vencimento": ["data_vencimento"],
        "cliente": ["cliente_nome"],
        "empreendimento": ["empreendimento_nome"],
        "unidade": ["empreendimento_nome", "quadra_ord", "lote_ord", "apto_ord"],
        "descricao": ["descricao"],
        "valor": ["valor"],
        "saldo": ["saldo"],
        "status": ["status"],
        "recebimento": ["data_recebimento"],
    },
    padrao="vencimento",
    dimensoes={
        "empreendimento": Dimensao(
            campo="empreendimento_id", rotulo_campo="empreendimento__empreendimento",
            rotulo="Empreendimento", filtro="empreendimento",
        ),
        "cliente": Dimensao(
            campo="cliente_id", rotulo_campo="cliente__nome_completo", rotulo="Cliente", filtro="cliente",
        ),
        "quadra": Dimensao(
            campo="cliente_empreendimento__unidade__quadra", rotulo="Quadra", filtro="quadra",
        ),
        "mes": _MES,
        "faixa": _FAIXA,
        "status": Dimensao(campo="status", rotulo="Status", filtro="status", rotulos=dict(StatusConta.choices)),
    },
)


def _anotacoes_pagar(hoje: date) -> dict:
    return {
        "fornecedor_nome": F("fornecedor__razao_social"),
        "empreendimento_nome": F("empreendimento__empreendimento"),
        "saldo": saldo_de(),
        "faixa": faixa_do_titulo(hoje),
        "mes": TruncMonth("data_vencimento"),
    }


PAGAR = Fonte(
    anotacoes=_anotacoes_pagar,
    ordenacoes={
        "vencimento": ["data_vencimento"],
        "fornecedor": ["fornecedor_nome"],
        "empreendimento": ["empreendimento_nome"],
        "descricao": ["descricao"],
        "valor": ["valor"],
        "saldo": ["saldo"],
        "status": ["status"],
        "pagamento": ["data_pagamento"],
    },
    padrao="vencimento",
    dimensoes={
        "fornecedor": Dimensao(
            campo="fornecedor_id", rotulo_campo="fornecedor__razao_social", rotulo="Fornecedor", filtro="fornecedor",
        ),
        "empreendimento": Dimensao(
            campo="empreendimento_id", rotulo_campo="empreendimento__empreendimento",
            rotulo="Empreendimento", filtro="empreendimento",
        ),
        "mes": _MES,
        "faixa": _FAIXA,
        "status": Dimensao(campo="status", rotulo="Status", filtro="status", rotulos=dict(StatusConta.choices)),
    },
)


def _anotacoes_boletos(hoje: date) -> dict:
    return {
        # Quem paga o boleto: o cliente, se o boleto cobra uma conta a receber;
        # o fornecedor, se ele chegou para pagarmos.
        "pessoa_nome": Coalesce(
            F("conta_receber__cliente__nome_completo"), F("conta_pagar__fornecedor__razao_social"),
        ),
        "empreendimento_nome": Coalesce(
            F("conta_receber__empreendimento__empreendimento"),
            F("conta_pagar__empreendimento__empreendimento"),
        ),
        "quadra_ord": chave_natural("conta_receber__cliente_empreendimento__unidade__quadra"),
        "lote_ord": chave_natural("conta_receber__cliente_empreendimento__unidade__lote"),
        "mes": TruncMonth("data_vencimento"),
    }


def _rotulo_status_boleto(valor) -> str:
    from .models import Boleto
    return dict(Boleto.StatusBoleto.choices).get(valor, valor or "—")


BOLETOS = Fonte(
    anotacoes=_anotacoes_boletos,
    ordenacoes={
        "vencimento": ["data_vencimento"],
        "cliente": ["pessoa_nome"],
        "empreendimento": ["empreendimento_nome"],
        "unidade": ["empreendimento_nome", "quadra_ord", "lote_ord"],
        "valor": ["valor"],
        "status": ["status"],
        "emissao": ["data_emissao"],
        "pagamento": ["data_pagamento"],
    },
    padrao="-vencimento",
    dimensoes={
        "empreendimento": Dimensao(
            campo="conta_receber__empreendimento_id",
            rotulo_campo="conta_receber__empreendimento__empreendimento",
            rotulo="Empreendimento", filtro="empreendimento",
        ),
        "cliente": Dimensao(
            campo="conta_receber__cliente_id", rotulo_campo="conta_receber__cliente__nome_completo",
            rotulo="Cliente", filtro="cliente",
        ),
        "mes": _MES,
        "status": Dimensao(campo="status", rotulo="Status", filtro="status", formatar=_rotulo_status_boleto),
    },
    tem_saldo=False,
)
