# backend/moduloscm/do_orcamento.py
"""A compra que nasce da planilha orçamentária (ORC.7 · seam SCM).

O laço `orçado → comprometido → estocado → aplicado → realizado` tinha uma
lacuna no primeiro elo: o orçamento sabia quanto de cada insumo a obra consome,
e ninguém no SCM sabia disso. A compra começava numa `Demanda` digitada à mão,
que é onde entra o erro de quantidade que a planilha já tinha resolvido.

**Este arquivo mora no SCM de propósito.** Quem sabe explodir composição é o
`moduloorcamento` — ele publica a relação consolidada de insumos e nada mais.
Quem sabe o que é uma demanda, qual centro de custo ela carrega e quando ela
nasce rascunho é o SCM. Inverter isso poria regra de compra dentro do módulo de
orçamento, e é assim que dois módulos viram um.

Três decisões que vêm do domínio:

1. **Nasce rascunho, sempre.** Uma planilha de mil linhas viraria uma demanda
   aberta com centenas de itens indo direto para cotação. O comprador confere,
   corta o que já tem em estoque e só então abre.
2. **Material e serviço se separam.** O SCM já distingue os dois (`Demanda.Tipo`)
   porque o fluxo é outro — material tem recebimento e entra no estoque, serviço
   tem medição. Uma demanda mista obrigaria o comprador a desmembrar à mão.
3. **A cobertura viaja junto.** Se metade das composições do orçamento não foi
   explodida, a relação é meia lista de compra. O resultado devolve a cobertura
   para a tela avisar **antes** de o comprador sair cotando por ela.
"""
from decimal import Decimal

from django.db import transaction

from .models import Demanda, ItemDemanda

# Naturezas de insumo que viram material comprável. Mão de obra fica de fora:
# ela é contratação, não compra, e mandá-la para cotação de fornecedor produziria
# uma RFQ pedindo preço de "PEDREIRO (H)".
_CATEGORIAS_MATERIAL = {"material"}
_CATEGORIAS_SERVICO = {"equipamento"}


class GeracaoInvalida(Exception):
    """Orçamento sem insumo explodido, ou sem nada na categoria pedida."""


@transaction.atomic
def demanda_do_orcamento(
    orcamento,
    *,
    tipo: str = Demanda.Tipo.MATERIAL,
    centro_custo=None,
    solicitante=None,
    observacao: str = "",
) -> dict:
    """Cria uma `Demanda` em rascunho a partir da relação de insumos do orçamento.

    A quantidade de cada item é a **consolidada da obra inteira** — o mesmo aço
    que aparece em nove serviços entra uma vez, somado. É exatamente o número que
    o orçamento já sabia e que ninguém conseguia levar para a compra sem digitar
    de novo.

    O item da demanda aponta o mesmo `catalogo.Item` que o orçamento usou, então
    o que for comprado casa com o que foi orçado sem tradução — que é a razão de
    o catálogo ser único no SGI.
    """
    from moduloorcamento.insumos import relacao_de_insumos

    categorias = _CATEGORIAS_MATERIAL if tipo == Demanda.Tipo.MATERIAL else _CATEGORIAS_SERVICO
    relacao = relacao_de_insumos(orcamento)

    linhas = [i for i in relacao["itens"] if i["categoria"] in categorias]
    if not linhas:
        if not relacao["itens"]:
            raise GeracaoInvalida(
                "Nenhuma composição explodida neste orçamento — sem insumos, não há "
                "o que comprar. Explodir as linhas é o passo que falta."
            )
        raise GeracaoInvalida(
            f"Este orçamento não tem insumo da natureza '{tipo}' entre os explodidos."
        )

    demanda = Demanda.objects.create(
        tenant_id=orcamento.tenant_id,
        tipo=tipo,
        centro_custo=centro_custo,
        solicitante=solicitante,
        status=Demanda.Status.RASCUNHO,
        origem=Demanda.Origem.MANUAL,
        observacao=observacao or (
            f"Gerada da relação de insumos do orçamento «{orcamento.descricao}» "
            f"(v{orcamento.versao}) — obra {orcamento.obra_id}."
        ),
    )

    ItemDemanda.objects.bulk_create([
        ItemDemanda(
            tenant_id=orcamento.tenant_id,
            demanda=demanda,
            produto_id=linha["item"],
            descricao_servico="" if linha["item"] else linha["descricao"][:255],
            # A relação traz quatro casas; `ItemDemanda.quantidade` guarda três.
            # Arredondar aqui, e não deixar o banco truncar, é o que impede a
            # demanda de sair com uma quantidade que a planilha não confirma.
            quantidade=Decimal(linha["quantidade"]).quantize(Decimal("0.001")),
            unidade=linha["unidade"],
        )
        for linha in linhas
    ])

    return {
        "demanda": demanda.pk,
        "tipo": demanda.tipo,
        "status": demanda.status,
        "itens": len(linhas),
        "orcamento": orcamento.pk,
        "valor_orcado_dos_itens": str(
            sum((Decimal(l["valor"]) for l in linhas), Decimal("0"))
        ),
        "cobertura_pct": relacao["cobertura_pct"],
        "nota_cobertura": (
            f"{relacao['cobertura_pct']}% do custo direto do orçamento está com "
            f"composição explodida ({relacao['linhas_explodidas']} de "
            f"{relacao['linhas_analiticas']} linhas). O que não foi explodido não "
            "entrou nesta demanda."
        ),
    }
