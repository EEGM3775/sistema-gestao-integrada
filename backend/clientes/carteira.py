"""A carteira de clientes — o motor da grade tipo planilha.

Uma tela só, duas **visões** da mesma carteira:

- ``clientes`` — uma linha por pessoa (com o resumo das unidades que ela comprou);
- ``unidades`` — uma linha por aquisição (a mesma pessoa se repete por lote).

Sobre qualquer das duas o usuário empilha **agrupamentos** (empreendimento,
quadra, cidade, faixa de atraso…), que aqui viram ``GROUP BY`` de verdade: o
subtotal do grupo sai do banco sobre a carteira **inteira**, não sobre a página
carregada — agrupar só a página daria um número errado com cara de certo.

**Adimplência.** A fonte é ``ContaReceber`` — a viva, a que tem boleto, webhook e
baixa. ``CobrancaCliente`` existe no schema mas ninguém escreve nela (pendência
A5). "Atrasado" não é status persistido: é derivado do vencimento, com as mesmas
faixas do aging do dashboard do ERP (``moduloerp/views.py``), para que os dois
lugares nunca discordem sobre o que é "31-60 dias".

**LGPD.** Os *números* da adimplência (parcelas, valor, dias) exigem
``erp.cobranca.view`` além do acesso ao cadastro — o mesmo gate de duas pontas
das divergências Asaas. Sem a permissão a linha traz só a situação
(adimplente/inadimplente) e o CPF/CNPJ segue mascarado por
``cadastro.cliente_doc.view``. Ver docs/acesso-e-permissoes.md.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import (
    Case, CharField, Count, DecimalField, F, Min, OuterRef, Q, QuerySet,
    Subquery, Sum, Value, When,
)
from django.db.models.functions import Coalesce, ExtractYear, LPad, NullIf
from django.utils import timezone

from moduloerp.models import ContaReceber, StatusConta
from nucleo.field_masking import mask_document_unless

DINHEIRO = DecimalField(max_digits=15, decimal_places=2)
ZERO = Value(Decimal("0"), output_field=DINHEIRO)

# Saldo em aberto do título — espelha `ContaReceber.saldo_aberto` (a property) e
# o aging do dashboard. Valor cheio mentiria em título com baixa parcial.
SALDO = F("valor") + F("juros") + F("multa") - F("desconto") - F("valor_pago")
STATUS_EM_ABERTO = [StatusConta.ABERTO, StatusConta.PARCIAL]


# ─── Faixas de atraso ─────────────────────────────────────────────────────────
# Os mesmos cortes do aging do ERP. `em_dia` cobre quem não tem NADA vencido —
# inclusive quem não deve nada, porque para a carteira as duas situações se
# resolvem igual: não há o que cobrar hoje.
FAIXAS = [
    {"chave": "em_dia", "rotulo": "Em dia", "de": None, "ate": None},
    {"chave": "d1_30", "rotulo": "1-30 dias", "de": 1, "ate": 30},
    {"chave": "d31_60", "rotulo": "31-60 dias", "de": 31, "ate": 60},
    {"chave": "d61_90", "rotulo": "61-90 dias", "de": 61, "ate": 90},
    {"chave": "d90_mais", "rotulo": "+90 dias", "de": 91, "ate": None},
]
FAIXA_POR_CHAVE = {f["chave"]: f for f in FAIXAS}


def faixa_de(dias_atraso: int | None) -> str:
    if not dias_atraso or dias_atraso <= 0:
        return "em_dia"
    if dias_atraso <= 30:
        return "d1_30"
    if dias_atraso <= 60:
        return "d31_60"
    if dias_atraso <= 90:
        return "d61_90"
    return "d90_mais"


def _caso_faixa(hoje: date):
    """A faixa como expressão SQL, para servir de dimensão de agrupamento.

    Deriva do vencimento **mais antigo em aberto** (anotação `venc_mais_antigo`):
    é o critério de cobrança — quem tem uma parcela de 120 dias e outra de 10
    está na faixa de 120, não na média das duas.
    """
    return Case(
        When(venc_mais_antigo__lt=hoje - timedelta(days=90), then=Value("d90_mais")),
        When(venc_mais_antigo__lt=hoje - timedelta(days=60), then=Value("d61_90")),
        When(venc_mais_antigo__lt=hoje - timedelta(days=30), then=Value("d31_60")),
        When(venc_mais_antigo__lt=hoje, then=Value("d1_30")),
        default=Value("em_dia"),
        output_field=CharField(),
    )


# ─── Anotações de adimplência ─────────────────────────────────────────────────

def _sub(contas: QuerySet, ref: str, expressao, so_vencidas: bool, hoje: date):
    """Agregado de ContaReceber correlacionado à linha de fora.

    Subquery em vez de `annotate` com join porque a linha também puxa agregados
    de aquisição; dois joins multi-valorados na mesma query inflam as somas.
    """
    base = contas.filter(**{ref: OuterRef("pk")}, status__in=STATUS_EM_ABERTO)
    if so_vencidas:
        base = base.filter(data_vencimento__lt=hoje)
    return Subquery(base.values(ref).annotate(v=expressao).values("v")[:1])


def anotar_adimplencia(qs: QuerySet, contas: QuerySet, ref: str, hoje: date) -> QuerySet:
    """Anota a situação financeira da linha.

    `ref` é o campo da ContaReceber que aponta para a linha: `cliente` na visão
    de pessoas, `cliente_empreendimento` na visão de unidades. Parcelas antigas
    (anteriores ao vínculo com a aquisição) têm `cliente_empreendimento` nulo:
    contam no total do cliente e ficam fora do rateio por unidade — é a
    consequência assumida ao criar o vínculo sem inventar o passado.
    """
    return qs.annotate(
        parcelas_atraso=Coalesce(_sub(contas, ref, Count("pk"), True, hoje), Value(0)),
        valor_atraso=Coalesce(_sub(contas, ref, Sum(SALDO, output_field=DINHEIRO), True, hoje), ZERO),
        valor_aberto=Coalesce(_sub(contas, ref, Sum(SALDO, output_field=DINHEIRO), False, hoje), ZERO),
        venc_mais_antigo=_sub(contas, ref, Min("data_vencimento"), True, hoje),
    ).annotate(faixa=_caso_faixa(hoje))


# ─── Ordem natural da unidade ─────────────────────────────────────────────────
# Quadra, lote, bloco, andar e apartamento são **texto** no modelo (existe "Quadra
# A", "Lote 12-B", "Torre Norte"), mas o usuário os lê como número: em ordem
# alfabética o lote 10 vem antes do 2, e a grade fica ilegível para quem confere
# uma quadra inteira. A chave de ordenação é o valor preenchido à esquerda com
# zeros — "0…02" < "0…10" —, e o nível vazio vira NULL para o `nulls_last`
# empurrar para o fim quem não tem aquele nível (o apartamento não tem quadra).
LARGURA_CHAVE = 20
_VAZIO = "0" * LARGURA_CHAVE


def chave_natural(campo: str):
    return NullIf(
        LPad(Coalesce(campo, Value("")), LARGURA_CHAVE, Value("0")),
        Value(_VAZIO),
    )


# A identificação da unidade, na ordem em que se lê um endereço de empreendimento:
# quadra › lote › bloco/torre › andar › apto. É a ordem padrão da visão de
# unidades e a que o clique na coluna "Unidade" aplica.
ORDEM_UNIDADE = ["quadra_ord", "lote_ord", "bloco_ord", "andar_ord", "unidade_ord"]
# A mesma leitura na visão de clientes, onde a unidade exibida é a da última
# aquisição (as chaves saem das `Subquery` de `base_clientes`).
ORDEM_UNIDADE_CLIENTE = [
    "ultima_quadra_ord", "ultimo_lote_ord", "ultimo_bloco_ord",
    "ultimo_andar_ord", "ultima_unidade_ord",
]


def _anotar_ordem_unidade(qs: QuerySet, campos: dict[str, str]) -> QuerySet:
    return qs.annotate(**{alias: chave_natural(campo) for alias, campo in campos.items()})


# ─── Dimensões de agrupamento e ordenação ─────────────────────────────────────
# `campo` é o que vai ao GROUP BY e volta como **chave** — e a chave tem de ser
# o que o filtro aceita, senão abrir um grupo não consegue pedir as linhas dele
# (agrupar por nome de empreendimento e filtrar por id não se encontram).
# `rotulo_campo` é o que o humano lê. `filtro` fecha o contrato com a tela: é o
# parâmetro que ela manda de volta ao expandir o grupo.

DIMENSOES = {
    "unidades": {
        "empreendimento": {
            "campo": "empreendimento_id", "rotulo_campo": "empreendimento__empreendimento",
            "rotulo": "Empreendimento", "filtro": "empreendimento",
        },
        "quadra": {"campo": "unidade__quadra", "rotulo": "Quadra", "filtro": "quadra"},
        "bloco_torre": {"campo": "unidade__bloco_torre", "rotulo": "Bloco/Torre", "filtro": "bloco_torre"},
        "cidade": {"campo": "empreendimento__cidade", "rotulo": "Cidade", "filtro": "cidade"},
        "estado": {"campo": "empreendimento__estado", "rotulo": "UF", "filtro": "estado"},
        "faixa": {"campo": "faixa", "rotulo": "Faixa de atraso", "filtro": "faixa", "rotulos": FAIXA_POR_CHAVE},
        "condicao_pagamento": {
            "campo": "condicoes_pagamento", "rotulo": "Condição de pagamento",
            "filtro": "condicao_pagamento",
        },
        "ano_compra": {
            "campo": "ano_compra", "rotulo": "Ano da compra", "filtro": "ano_compra",
            "expressao": ExtractYear("data_compra"),
        },
        "cliente": {
            "campo": "cliente_id", "rotulo_campo": "cliente__nome_completo",
            "rotulo": "Cliente", "filtro": "cliente",
        },
    },
    "clientes": {
        "empreendimento": {
            "campo": "clienteempreendimento__empreendimento_id",
            "rotulo_campo": "clienteempreendimento__empreendimento__empreendimento",
            "rotulo": "Empreendimento", "filtro": "empreendimento",
        },
        "quadra": {"campo": "clienteempreendimento__unidade__quadra", "rotulo": "Quadra", "filtro": "quadra"},
        "cidade": {"campo": "cidade", "rotulo": "Cidade do cliente", "filtro": "cidade"},
        "estado": {"campo": "estado", "rotulo": "UF do cliente", "filtro": "estado"},
        "faixa": {"campo": "faixa", "rotulo": "Faixa de atraso", "filtro": "faixa", "rotulos": FAIXA_POR_CHAVE},
        "profissao": {"campo": "profissao", "rotulo": "Profissão", "filtro": "profissao"},
        "estado_civil": {"campo": "estado_civil", "rotulo": "Estado civil", "filtro": "estado_civil"},
    },
}

# Ordenações expostas — **uma por coluna da grade**, porque toda coluna da tela
# tem "Ordenar por". A chave é a que o frontend manda; o valor é a lista de
# campos ORM que a compõem (a unidade são cinco, o resto é um só).
#
# Dois grupos ficam atrás de permissão, pela mesma razão: ordenar por um dado é
# lê-lo. As **financeiras** exigem `erp.cobranca.view` (ordenar por "maior
# devedor" já é ler a dívida) e o **documento** exige `cadastro.cliente_doc.view`
# (a ordem alfabética dos CPFs vaza o CPF que a máscara esconde). Sem a
# permissão a chave não existe e o pedido cai na ordem padrão da visão.
ORDENACOES = {
    "clientes": {
        "nome": ["nome_completo"],
        "email": ["email"],
        "telefone": ["telefone"],
        "empreendimento": ["ultimo_empreendimento"],
        "cidade": ["ultima_cidade"],
        "estado": ["ultimo_estado"],
        "cidade_cliente": ["cidade"],
        "estado_cliente": ["estado"],
        "unidade": ORDEM_UNIDADE_CLIENTE,
        "quadra": ["ultima_quadra_ord"],
        "lote": ["ultimo_lote_ord"],
        "bloco_torre": ["ultimo_bloco_ord"],
        "andar": ["ultimo_andar_ord"],
        "apto": ["ultima_unidade_ord"],
        "unidades_total": ["unidades_total"],
        "cadastro": ["data_cadastro"],
        "_documentais": {"documento": ["cpf_cnpj"]},
        "_financeiras": {
            "atraso": ["venc_mais_antigo"],
            "valor_aberto": ["valor_aberto"],
            "valor_atraso": ["valor_atraso"],
            "parcelas_atraso": ["parcelas_atraso"],
            "valor_venda": ["valor_venda"],
        },
    },
    "unidades": {
        "unidade": ORDEM_UNIDADE,
        "nome": ["cliente__nome_completo"],
        "email": ["cliente__email"],
        "telefone": ["cliente__telefone"],
        "empreendimento": ["empreendimento__empreendimento"],
        "cidade": ["empreendimento__cidade"],
        "estado": ["empreendimento__estado"],
        "quadra": ["quadra_ord"],
        "lote": ["lote_ord"],
        "bloco_torre": ["bloco_ord"],
        "andar": ["andar_ord"],
        "apto": ["unidade_ord"],
        "compra": ["data_compra"],
        "condicao_pagamento": ["condicoes_pagamento"],
        "_documentais": {"documento": ["cliente__cpf_cnpj"]},
        "_financeiras": {
            "atraso": ["venc_mais_antigo"],
            "valor_aberto": ["valor_aberto"],
            "valor_atraso": ["valor_atraso"],
            "parcelas_atraso": ["parcelas_atraso"],
            "valor_venda": ["valor_compra"],
        },
    },
}

# O que a grade mostra antes de o usuário pedir outra coisa: pessoas em ordem
# alfabética, unidades na ordem do endereço (quadra › lote › bloco › andar › apto).
ORDEM_PADRAO = {"clientes": "nome", "unidades": "unidade"}


def _mapa_de_ordenacao(visao: str, pode_financeiro: bool, pode_documento: bool) -> dict:
    mapa = {k: v for k, v in ORDENACOES[visao].items() if not k.startswith("_")}
    if pode_financeiro:
        mapa.update(ORDENACOES[visao]["_financeiras"])
    if pode_documento:
        mapa.update(ORDENACOES[visao]["_documentais"])
    return mapa


def ordenacao_valida(
    visao: str, chave: str, pode_financeiro: bool, pode_documento: bool = False
) -> list:
    """Traduz a chave pedida pela tela nos termos de `order_by`, ou lista vazia.

    Devolve **expressões**, não nomes: a unidade é uma ordem composta de cinco
    níveis e o vazio precisa cair no fim (`nulls_last`), o que o nome de campo
    sozinho não expressa.
    """
    campos = _mapa_de_ordenacao(visao, pode_financeiro, pode_documento).get(chave.lstrip("-"))
    if not campos:
        return []
    descendente = chave.startswith("-")
    return [
        F(c).desc(nulls_last=True) if descendente else F(c).asc(nulls_last=True)
        for c in campos
    ]


def ordenacao(
    visao: str, chave: str, pode_financeiro: bool, pode_documento: bool = False
) -> list:
    """Os termos finais do `order_by`, com o desempate obrigatório pela chave.

    Sem o desempate, duas linhas com o mesmo valor de ordenação podem trocar de
    lugar entre uma página e a próxima — e a rolagem infinita repete uma e come
    a outra, sem nada na tela denunciando.
    """
    termos = ordenacao_valida(visao, chave, pode_financeiro, pode_documento)
    if not termos:
        termos = ordenacao_valida(visao, ORDEM_PADRAO[visao], pode_financeiro, pode_documento)
    return termos + [F("pk").asc()]


# ─── Filtros ──────────────────────────────────────────────────────────────────

FILTROS = {
    "unidades": {
        "empreendimento": "empreendimento_id", "quadra": "unidade__quadra__iexact",
        "lote": "unidade__lote__iexact", "bloco_torre": "unidade__bloco_torre__iexact",
        "cidade": "empreendimento__cidade__iexact",
        "estado": "empreendimento__estado__iexact", "condicao_pagamento": "condicoes_pagamento",
        "cliente": "cliente_id",
    },
    "clientes": {
        "empreendimento": "clienteempreendimento__empreendimento_id",
        "quadra": "clienteempreendimento__unidade__quadra__iexact",
        "cidade": "cidade__iexact", "estado": "estado__iexact",
        "profissao": "profissao__iexact", "estado_civil": "estado_civil",
    },
}

BUSCA = {
    "unidades": [
        "cliente__nome_completo__icontains", "cliente__cpf_cnpj__icontains",
        "cliente__email__icontains", "unidade__quadra__iexact", "unidade__lote__iexact",
        "unidade__apto__iexact", "unidade__bloco_torre__icontains",
        "empreendimento__empreendimento__icontains",
    ],
    "clientes": [
        "nome_completo__icontains", "cpf_cnpj__icontains", "email__icontains",
        "telefone__icontains", "cidade__icontains", "bairro__icontains", "cep__icontains",
    ],
}


def aplicar_filtros(qs: QuerySet, visao: str, params, hoje: date) -> QuerySet:
    for chave, caminho in FILTROS[visao].items():
        valor = params.get(chave)
        if valor:
            qs = qs.filter(**{caminho: valor})

    faixa = params.get("faixa")
    if faixa in FAIXA_POR_CHAVE:
        if faixa == "em_dia":
            qs = qs.filter(venc_mais_antigo__isnull=True)
        else:
            f = FAIXA_POR_CHAVE[faixa]
            limites = Q(venc_mais_antigo__lte=hoje - timedelta(days=f["de"]))
            if f["ate"]:
                limites &= Q(venc_mais_antigo__gte=hoje - timedelta(days=f["ate"]))
            qs = qs.filter(limites)

    ano = params.get("ano_compra")
    if ano:
        campo = "data_compra__year" if visao == "unidades" else "clienteempreendimento__data_compra__year"
        qs = qs.filter(**{campo: ano})

    busca = (params.get("busca") or "").strip()
    if busca:
        alvo = Q()
        for caminho in BUSCA[visao]:
            alvo |= Q(**{caminho: busca})
        qs = qs.filter(alvo)

    # Filtrar pessoas por um atributo da aquisição atravessa uma relação de
    # muitos: quem comprou dois lotes na mesma quadra viria duplicado.
    atravessa_aquisicao = visao == "clientes" and any(
        params.get(k) for k in ("empreendimento", "quadra", "ano_compra")
    )
    return qs.distinct() if atravessa_aquisicao else qs


# ─── Montagem das visões ──────────────────────────────────────────────────────

def base_unidades(aquisicoes: QuerySet, contas: QuerySet, hoje: date) -> QuerySet:
    qs = anotar_adimplencia(
        aquisicoes.select_related("cliente", "empreendimento", "unidade"),
        contas, "cliente_empreendimento", hoje,
    ).annotate(ano_compra=ExtractYear("data_compra"))
    return _anotar_ordem_unidade(qs, {
        "quadra_ord": "unidade__quadra", "lote_ord": "unidade__lote",
        "bloco_ord": "unidade__bloco_torre", "andar_ord": "unidade__andar",
        "unidade_ord": "unidade__apto",
    })


def base_clientes(clientes: QuerySet, contas: QuerySet, aquisicoes: QuerySet, hoje: date) -> QuerySet:
    aquisicoes_do_cliente = aquisicoes.filter(cliente=OuterRef("pk")).order_by("-data_compra")
    return anotar_adimplencia(clientes, contas, "cliente", hoje).annotate(
        unidades_total=Coalesce(
            Subquery(
                aquisicoes.filter(cliente=OuterRef("pk")).values("cliente")
                .annotate(v=Count("pk")).values("v")[:1]
            ),
            Value(0),
        ),
        valor_venda=Coalesce(
            Subquery(
                aquisicoes.filter(cliente=OuterRef("pk")).values("cliente")
                .annotate(v=Sum("valor_compra", output_field=DINHEIRO)).values("v")[:1]
            ),
            ZERO,
        ),
        # A unidade "principal" é a última compra — é por ela que o cliente é
        # reconhecido no atendimento ("o do lote novo"), e o contador ao lado
        # avisa que existem outras.
        ultima_quadra=Subquery(aquisicoes_do_cliente.values("unidade__quadra")[:1]),
        ultimo_lote=Subquery(aquisicoes_do_cliente.values("unidade__lote")[:1]),
        ultimo_bloco=Subquery(aquisicoes_do_cliente.values("unidade__bloco_torre")[:1]),
        ultimo_andar=Subquery(aquisicoes_do_cliente.values("unidade__andar")[:1]),
        ultima_unidade_num=Subquery(aquisicoes_do_cliente.values("unidade__apto")[:1]),
        ultimo_empreendimento=Subquery(aquisicoes_do_cliente.values("empreendimento__empreendimento")[:1]),
        ultima_cidade=Subquery(aquisicoes_do_cliente.values("empreendimento__cidade")[:1]),
        ultimo_estado=Subquery(aquisicoes_do_cliente.values("empreendimento__estado")[:1]),
    ).annotate(
        # Ordenar a pessoa pela unidade dela: as mesmas chaves naturais da visão
        # de unidades, aplicadas ao que veio das `Subquery` acima.
        **{
            "ultima_quadra_ord": chave_natural("ultima_quadra"),
            "ultimo_lote_ord": chave_natural("ultimo_lote"),
            "ultimo_bloco_ord": chave_natural("ultimo_bloco"),
            "ultimo_andar_ord": chave_natural("ultimo_andar"),
            "ultima_unidade_ord": chave_natural("ultima_unidade_num"),
        }
    )


def rotulo_unidade(quadra: str, lote: str, bloco: str, andar: str, apto: str) -> str:
    """Mesma regra de `Unidade.rotulo`, aplicável a valores soltos vindos de
    `Subquery` (a visão de clientes não instancia a unidade)."""
    partes = []
    if quadra:
        partes.append(f"QD {quadra}")
    if lote:
        partes.append(f"LT {lote}")
    if bloco:
        partes.append(bloco)
    if andar:
        partes.append(f"{andar}º")
    if apto:
        partes.append(apto)
    return " · ".join(partes)


def _financeiro(linha, usuario, pode_financeiro: bool, hoje: date) -> dict:
    """A situação sempre; os números só com `erp.cobranca.view`.

    A pílula adimplente/inadimplente é o que a tela mostra a todos; parcelas,
    valor e dias ficam atrás da permissão financeira (decisão registrada em
    docs/acesso-e-permissoes.md).
    """
    dias = (hoje - linha.venc_mais_antigo).days if linha.venc_mais_antigo else 0
    dados = {"adimplente": linha.parcelas_atraso == 0, "faixa": faixa_de(dias)}
    if pode_financeiro:
        dados |= {
            "parcelasAtraso": linha.parcelas_atraso,
            "valorAtraso": str(linha.valor_atraso),
            "valorAberto": str(linha.valor_aberto),
            "diasAtraso": dias,
        }
    return dados


def serializar_cliente(c, usuario, pode_financeiro: bool, hoje: date) -> dict:
    return {
        "tipo": "cliente",
        "id": c.pk,
        "clienteId": c.pk,
        "nome": c.nome_completo,
        "documento": mask_document_unless(usuario, c.cpf_cnpj),
        "email": c.email,
        "telefone": c.telefone,
        "cidadeCliente": c.cidade,
        "estadoCliente": c.estado,
        "empreendimento": c.ultimo_empreendimento or "",
        "cidade": c.ultima_cidade or "",
        "estado": c.ultimo_estado or "",
        "unidade": rotulo_unidade(
            c.ultima_quadra or "", c.ultimo_lote or "", c.ultimo_bloco or "",
            c.ultimo_andar or "", c.ultima_unidade_num or "",
        ),
        "quadra": c.ultima_quadra or "",
        "lote": c.ultimo_lote or "",
        "blocoTorre": c.ultimo_bloco or "",
        "andar": c.ultimo_andar or "",
        "apto": c.ultima_unidade_num or "",
        "unidadesTotal": c.unidades_total,
        "valorVenda": str(c.valor_venda) if pode_financeiro else None,
        **_financeiro(c, usuario, pode_financeiro, hoje),
    }


def serializar_unidade(a, usuario, pode_financeiro: bool, hoje: date) -> dict:
    return {
        "tipo": "unidade",
        "id": a.pk,
        "clienteId": a.cliente_id,
        "nome": a.cliente.nome_completo,
        "documento": mask_document_unless(usuario, a.cliente.cpf_cnpj),
        "email": a.cliente.email,
        "telefone": a.cliente.telefone,
        "empreendimento": a.empreendimento.empreendimento,
        "cidade": a.empreendimento.cidade,
        "estado": a.empreendimento.estado,
        "unidade": a.unidade.rotulo,
        "quadra": a.unidade.quadra,
        "lote": a.unidade.lote,
        "blocoTorre": a.unidade.bloco_torre,
        "andar": a.unidade.andar,
        "apto": a.unidade.apto,
        "dataCompra": a.data_compra.isoformat() if a.data_compra else None,
        "condicaoPagamento": a.get_condicoes_pagamento_display(),
        "unidadesTotal": 1,
        "valorVenda": str(a.valor_compra) if pode_financeiro else None,
        **_financeiro(a, usuario, pode_financeiro, hoje),
    }


# ─── Agrupamento ──────────────────────────────────────────────────────────────

def agrupar(qs: QuerySet, visao: str, niveis: list[str], pode_financeiro: bool) -> list[dict]:
    """Subtotais por combinação de níveis, calculados no banco.

    Devolve a lista **achatada** de combinações (a tela monta a árvore): com
    ``por=empreendimento,quadra`` vem uma linha por par empreendimento×quadra,
    e o nível de cima é a soma dos filhos. Achatar aqui evita N consultas por
    grupo aberto e mantém a contagem coerente entre os níveis.
    """
    dims = DIMENSOES[visao]
    validos = [n for n in niveis if n in dims][:3]
    if not validos:
        return []

    campos = [dims[n]["campo"] for n in validos]
    rotulos_campos = [dims[n].get("rotulo_campo") for n in validos]
    extras = {n: dims[n]["expressao"] for n in validos if "expressao" in dims[n]}
    if extras:
        qs = qs.annotate(**extras)
    # Agrupar pela chave E pelo rótulo é equivalente a agrupar só pela chave (o
    # id determina o nome) e evita uma segunda consulta só para traduzir.
    agrupamento = campos + [c for c in rotulos_campos if c]

    # Cliente é contado distinto: agrupar pessoas por uma dimensão de muitos
    # (empreendimento) repete a linha, e "3 clientes" não pode virar "5".
    contagem = Count("pk", distinct=True)
    anotacoes = {"contagem": contagem}
    if pode_financeiro:
        anotacoes["valorAberto"] = Coalesce(Sum("valor_aberto", output_field=DINHEIRO), ZERO)
        anotacoes["valorAtraso"] = Coalesce(Sum("valor_atraso", output_field=DINHEIRO), ZERO)
        anotacoes["valorVenda"] = Coalesce(
            Sum("valor_compra" if visao == "unidades" else "valor_venda", output_field=DINHEIRO), ZERO
        )

    linhas = qs.values(*agrupamento).annotate(**anotacoes).order_by(*agrupamento)

    saida = []
    for linha in linhas:
        chaves = [linha[c] for c in campos]
        saida.append({
            "niveis": validos,
            "filtros": [dims[n]["filtro"] for n in validos],
            "chaves": [("" if v is None else str(v)) for v in chaves],
            "rotulos": [
                _rotulo_valor(dims[n], linha[rc] if rc else v)
                for n, v, rc in zip(validos, chaves, rotulos_campos)
            ],
            "contagem": linha["contagem"],
            **({
                "valorAberto": str(linha["valorAberto"]),
                "valorAtraso": str(linha["valorAtraso"]),
                "valorVenda": str(linha["valorVenda"]),
            } if pode_financeiro else {}),
        })
    return saida


def _rotulo_valor(dim: dict, valor) -> str:
    if valor in (None, ""):
        return "— sem informação —"
    if "rotulos" in dim:
        return dim["rotulos"].get(str(valor), {}).get("rotulo", str(valor))
    return str(valor)


def hoje_local() -> date:
    return timezone.localdate()
