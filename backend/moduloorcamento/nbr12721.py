# backend/moduloorcamento/nbr12721.py
"""ORC.4 — orçamento paramétrico (CUB) e os quadros da NBR 12721.

Os quadros da NBR 12721 **não são relatório gerencial**: são condição legal
para registrar a incorporação em cartório e vender unidade na planta
(Lei 4.591/64). Todo o resto da documentação da incorporação deriva deles, e um
número errado aqui trava o registro — por isso este módulo calcula o que é
cálculo e **não inventa** o que é descrição.

### O que é calculado e o que não é

| Quadro | Conteúdo | Aqui |
|---|---|---|
| **I** | Áreas nos pavimentos e área global | calculado |
| **II** | Áreas das unidades autônomas | calculado |
| **III** | Custo global e unitário da construção | calculado |
| **IV-A/IV-B** | Custo por unidade e rateio | calculado |
| **V–VIII** | Informações gerais e memoriais de acabamento | **descritivos** — linhas de texto (`MemorialNBR`), preenchidas pelo projetista |

### A conversão que amarra tudo: área equivalente

Área real é quanto o prédio tem; **área equivalente** é quanto ele custa, em
"m² de padrão". Garagem, varanda e área descoberta custam menos que
apartamento, e a norma converte cada uma por um coeficiente. É sobre a
equivalente que o CUB multiplica (Quadro III) e é por ela que o custo global se
rateia entre as unidades (Quadro IV).

### Duas grandezas que parecem uma

`coeficiente_proporcionalidade` (rateio do **custo**, o termo que a norma usa
nos quadros) e `fracao_ideal` (quota do **terreno**, conceito do direito civil
que vai para a matrícula) costumam coincidir — e é por isso que confundi-los
passa despercebido até o dia em que não coincidem. Ver `models.UnidadeAutonoma`.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from .models import MemorialNBR, ParametroObra, PavimentoObra, UnidadeAutonoma
from .planilha import dinheiro, orcamento_vigente

CEM = Decimal("100")
ZERO = Decimal("0")
METRO = Decimal("0.01")
COEFICIENTE = Decimal("0.00000001")


class DadosInsuficientes(Exception):
    """Quadro pedido sem a base de áreas ou de custo necessária."""


def _m2(valor: Decimal) -> Decimal:
    return Decimal(valor).quantize(METRO, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Paramétrico
# ---------------------------------------------------------------------------


@transaction.atomic
def calcular_parametrico(parametro: ParametroObra, *, sincronizar_area: bool = False) -> ParametroObra:
    """Custo estimado = área equivalente × CUB + adicionais.

    Com `sincronizar_area`, as áreas vêm dos pavimentos cadastrados em vez de
    digitadas — é o caminho natural quando o Quadro I já existe, e evita a
    incoerência de um paramétrico que discorda do quadro de áreas da mesma obra.

    Os adicionais entram nas duas formas (percentual e valor fechado) porque na
    viabilidade convivem: elevador se estima por percentual, o terreno já tem
    preço. O percentual incide sobre o custo do CUB, não sobre o total — senão
    incidiria também sobre os valores fechados.
    """
    if sincronizar_area:
        pavimentos = PavimentoObra.objects.filter(
            tenant_id=parametro.tenant_id, obra_id=parametro.obra_id
        )
        parametro.area_real = _m2(sum((p.area_real for p in pavimentos), ZERO))
        parametro.area_equivalente = _m2(sum((p.area_equivalente for p in pavimentos), ZERO))

    custo_cub = parametro.area_equivalente * parametro.cub_m2
    adicionais = custo_cub * parametro.percentual_adicionais / CEM + parametro.valor_adicionais
    parametro.custo_estimado = dinheiro(custo_cub + adicionais)
    parametro.save(update_fields=[
        "area_real", "area_equivalente", "custo_estimado",
    ])
    return parametro


def comparar_parametrico_com_analitico(parametro: ParametroObra) -> dict:
    """Paramétrico × planilha analítica aprovada — o aprendizado da estimativa.

    A diferença entre os dois não é erro de nenhum: o paramétrico foi feito com
    a informação da viabilidade, o analítico com o projeto. Medir a distância é
    o que calibra a próxima estimativa, e é uma leitura que só existe quando os
    dois moram no mesmo sistema.
    """
    analitico = orcamento_vigente(parametro.tenant_id, parametro.obra_id)
    if analitico is None:
        return {
            "parametrico": str(parametro.custo_estimado),
            "analitico": None,
            "desvio": None,
            "desvio_pct": None,
            "detalhe": "Obra ainda não tem orçamento analítico aprovado.",
        }

    desvio = analitico.valor_total - parametro.custo_estimado
    return {
        "parametrico": str(parametro.custo_estimado),
        "analitico": str(analitico.valor_total),
        "orcamento": analitico.pk,
        "desvio": str(dinheiro(desvio)),
        "desvio_pct": (
            str((desvio / parametro.custo_estimado * CEM).quantize(METRO))
            if parametro.custo_estimado > 0 else None
        ),
    }


# ---------------------------------------------------------------------------
# Quadro I — áreas nos pavimentos e área global
# ---------------------------------------------------------------------------


def quadro_i(tenant_id, obra_id) -> dict:
    """Áreas por pavimento e o global da obra."""
    pavimentos = list(
        PavimentoObra.objects.filter(tenant_id=tenant_id, obra_id=obra_id).order_by("ordem", "pavimento_id")
    )
    linhas = [
        {
            "pavimento": p.pavimento_id,
            "nome": p.nome,
            "area_coberta_padrao": str(_m2(p.area_coberta_padrao)),
            "area_coberta_diferente": str(_m2(p.area_coberta_diferente)),
            "coeficiente_coberta_diferente": str(p.coeficiente_coberta_diferente),
            "area_descoberta": str(_m2(p.area_descoberta)),
            "coeficiente_descoberta": str(p.coeficiente_descoberta),
            "area_real": str(_m2(p.area_real)),
            "area_equivalente": str(_m2(p.area_equivalente)),
        }
        for p in pavimentos
    ]
    return {
        "quadro": "I",
        "titulo": "Cálculo das áreas nos pavimentos e da área global",
        "pavimentos": linhas,
        "area_real_global": str(_m2(sum((p.area_real for p in pavimentos), ZERO))),
        "area_equivalente_global": str(_m2(sum((p.area_equivalente for p in pavimentos), ZERO))),
    }


# ---------------------------------------------------------------------------
# Quadro II — áreas das unidades autônomas
# ---------------------------------------------------------------------------


def quadro_ii(tenant_id, obra_id) -> dict:
    """Áreas real e equivalente de cada unidade, com o coeficiente de rateio."""
    unidades = list(
        UnidadeAutonoma.objects.filter(tenant_id=tenant_id, obra_id=obra_id)
        .select_related("pavimento").order_by("pavimento__ordem", "designacao")
    )
    linhas = [
        {
            "unidade": u.unidade_id,
            "designacao": u.designacao,
            "tipo": u.tipo,
            "pavimento": u.pavimento.nome if u.pavimento else None,
            "area_privativa_padrao": str(_m2(u.area_privativa_padrao)),
            "area_privativa_diferente": str(_m2(u.area_privativa_diferente)),
            "area_real_privativa": str(_m2(u.area_real_privativa)),
            "area_uso_comum": str(_m2(u.area_uso_comum)),
            "area_real_total": str(_m2(u.area_real_total)),
            "area_equivalente_privativa": str(_m2(u.area_equivalente_privativa)),
            "coeficiente_proporcionalidade": str(u.coeficiente_proporcionalidade),
            "fracao_ideal": str(u.fracao_ideal),
        }
        for u in unidades
    ]
    return {
        "quadro": "II",
        "titulo": "Cálculo das áreas das unidades autônomas",
        "unidades": linhas,
        "area_real_total": str(_m2(sum((u.area_real_total for u in unidades), ZERO))),
        "area_equivalente_total": str(
            _m2(sum((u.area_equivalente_privativa for u in unidades), ZERO))
        ),
    }


@transaction.atomic
def calcular_coeficientes(tenant_id, obra_id, *, replicar_na_fracao_ideal: bool = False) -> list[UnidadeAutonoma]:
    """Coeficiente de proporcionalidade de cada unidade, pela área equivalente.

    O resíduo do arredondamento vai na **maior unidade**, para a soma fechar
    exatamente 1,00000000 — num quadro que vai a cartório, uma soma de 0,99999999
    é motivo de exigência.

    `replicar_na_fracao_ideal` copia o resultado para a fração ideal. É
    **opcional e explícito** de propósito: as duas grandezas coincidem com
    frequência, mas a fração ideal pode ser definida por outro critério, e
    escrevê-la em silêncio seria decidir uma questão jurídica no lugar do
    incorporador (ver `models.UnidadeAutonoma`).
    """
    unidades = list(
        UnidadeAutonoma.objects.filter(tenant_id=tenant_id, obra_id=obra_id)
    )
    total = sum((u.area_equivalente_privativa for u in unidades), ZERO)
    if total <= 0:
        raise DadosInsuficientes(
            "Nenhuma unidade com área equivalente — cadastre as áreas privativas antes."
        )

    for unidade in unidades:
        unidade.coeficiente_proporcionalidade = (
            unidade.area_equivalente_privativa / total
        ).quantize(COEFICIENTE, rounding=ROUND_HALF_UP)

    residuo = Decimal("1") - sum((u.coeficiente_proporcionalidade for u in unidades), ZERO)
    if residuo != 0:
        maior = max(unidades, key=lambda u: u.area_equivalente_privativa)
        maior.coeficiente_proporcionalidade += residuo

    campos = ["coeficiente_proporcionalidade"]
    if replicar_na_fracao_ideal:
        for unidade in unidades:
            unidade.fracao_ideal = unidade.coeficiente_proporcionalidade
        campos.append("fracao_ideal")

    UnidadeAutonoma.objects.bulk_update(unidades, campos, batch_size=500)
    return unidades


# ---------------------------------------------------------------------------
# Quadro III — custo global e unitário
# ---------------------------------------------------------------------------


def _custo_global(tenant_id, obra_id, parametro: ParametroObra | None):
    """Custo da obra e de onde ele veio.

    Preferência pelo **analítico aprovado**: quando existe planilha, ela é mais
    precisa que a estimativa por CUB, e é ela que o quadro deve refletir. Sem
    analítico, cai no paramétrico — declarando a fonte, para o quadro não
    parecer mais preciso do que é.
    """
    analitico = orcamento_vigente(tenant_id, obra_id)
    if analitico is not None:
        return analitico.valor_total, "orcamento_analitico", analitico.pk
    if parametro is not None:
        return parametro.custo_estimado, "parametrico_cub", parametro.pk
    raise DadosInsuficientes(
        "A obra não tem orçamento analítico aprovado nem paramétrico — "
        "o Quadro III precisa de uma das duas bases de custo."
    )


def quadro_iii(tenant_id, obra_id, *, parametro: ParametroObra | None = None) -> dict:
    """Custo global da construção e o custo por m² de área equivalente."""
    custo, fonte, origem_id = _custo_global(tenant_id, obra_id, parametro)
    pavimentos = PavimentoObra.objects.filter(tenant_id=tenant_id, obra_id=obra_id)
    area_equivalente = sum((p.area_equivalente for p in pavimentos), ZERO)
    area_real = sum((p.area_real for p in pavimentos), ZERO)

    return {
        "quadro": "III",
        "titulo": "Avaliação do custo global e unitário da construção",
        "custo_global": str(dinheiro(custo)),
        "fonte_do_custo": fonte,
        "origem_id": origem_id,
        "area_real_global": str(_m2(area_real)),
        "area_equivalente_global": str(_m2(area_equivalente)),
        "custo_por_m2_equivalente": (
            str((custo / area_equivalente).quantize(METRO, rounding=ROUND_HALF_UP))
            if area_equivalente > 0 else None
        ),
        "custo_por_m2_real": (
            str((custo / area_real).quantize(METRO, rounding=ROUND_HALF_UP))
            if area_real > 0 else None
        ),
    }


# ---------------------------------------------------------------------------
# Quadros IV-A e IV-B — custo por unidade e rateio
# ---------------------------------------------------------------------------


@transaction.atomic
def quadro_iv(tenant_id, obra_id, *, parametro: ParametroObra | None = None, gravar: bool = True) -> dict:
    """Rateio do custo global entre as unidades, pelo coeficiente.

    O resíduo dos centavos vai na unidade de maior coeficiente, pelo mesmo
    motivo do `calcular_coeficientes`: a soma das partes tem de dar o todo,
    exatamente, num documento que vai a registro.
    """
    custo, fonte, origem_id = _custo_global(tenant_id, obra_id, parametro)
    unidades = list(
        UnidadeAutonoma.objects.filter(tenant_id=tenant_id, obra_id=obra_id)
        .order_by("pavimento__ordem", "designacao")
    )
    if not unidades:
        raise DadosInsuficientes("A obra não tem unidades autônomas cadastradas.")

    soma_coeficientes = sum((u.coeficiente_proporcionalidade for u in unidades), ZERO)
    if soma_coeficientes <= 0:
        raise DadosInsuficientes(
            "Coeficientes de proporcionalidade zerados — rode o cálculo dos coeficientes antes."
        )

    for unidade in unidades:
        unidade.custo_estimado = dinheiro(
            custo * unidade.coeficiente_proporcionalidade / soma_coeficientes
        )
    residuo = dinheiro(custo) - sum((u.custo_estimado for u in unidades), ZERO)
    if residuo != 0:
        maior = max(unidades, key=lambda u: u.coeficiente_proporcionalidade)
        maior.custo_estimado += residuo

    if gravar:
        UnidadeAutonoma.objects.bulk_update(unidades, ["custo_estimado"], batch_size=500)

    return {
        "quadro": "IV",
        "titulo": "Avaliação do custo de construção de cada unidade autônoma e rateio",
        "custo_global": str(dinheiro(custo)),
        "fonte_do_custo": fonte,
        "origem_id": origem_id,
        "soma_coeficientes": str(soma_coeficientes),
        "unidades": [
            {
                "unidade": u.unidade_id,
                "designacao": u.designacao,
                "area_equivalente_privativa": str(_m2(u.area_equivalente_privativa)),
                "coeficiente_proporcionalidade": str(u.coeficiente_proporcionalidade),
                "fracao_ideal": str(u.fracao_ideal),
                "custo_estimado": str(u.custo_estimado),
            }
            for u in unidades
        ],
        "total_rateado": str(sum((u.custo_estimado for u in unidades), ZERO)),
    }


# ---------------------------------------------------------------------------
# Quadros V a VIII — memoriais descritivos
# ---------------------------------------------------------------------------


def quadros_descritivos(tenant_id, obra_id, quadro: str | None = None) -> dict:
    """Os quadros de texto (V, VI, VII, VIII), agrupados.

    Não há cálculo aqui — e é importante que não haja. Estes quadros são
    descrição técnica do projetista; gerar conteúdo automático para eles
    produziria um memorial que não corresponde à obra, num documento que vai a
    cartório.
    """
    linhas = MemorialNBR.objects.filter(tenant_id=tenant_id, obra_id=obra_id)
    if quadro:
        linhas = linhas.filter(quadro=quadro)

    agrupado: dict[str, list] = {}
    for linha in linhas.order_by("quadro", "ordem", "memorial_id"):
        agrupado.setdefault(linha.quadro, []).append({
            "memorial_id": linha.memorial_id,
            "ordem": linha.ordem,
            "dependencia": linha.dependencia,
            "descricao": linha.descricao,
        })

    return {
        "quadros": {
            codigo: {
                "titulo": dict(MemorialNBR.Quadro.choices)[codigo],
                "linhas": itens,
            }
            for codigo, itens in agrupado.items()
        },
        "preenchidos": sorted(agrupado.keys()),
        "faltando": sorted(
            codigo for codigo, _ in MemorialNBR.Quadro.choices if codigo not in agrupado
        ),
    }


def dossie(tenant_id, obra_id, *, parametro: ParametroObra | None = None) -> dict:
    """Os oito quadros numa resposta — o dossiê de incorporação.

    Quadro que não tem base ainda entra com o motivo em `indisponivel`, em vez
    de derrubar o dossiê inteiro: montar a incorporação é processo incremental,
    e a tela precisa mostrar o que já existe e o que falta.
    """
    resultado: dict = {"obra": obra_id, "quadros": {}, "indisponivel": {}}

    for codigo, funcao in (
        ("I", lambda: quadro_i(tenant_id, obra_id)),
        ("II", lambda: quadro_ii(tenant_id, obra_id)),
        ("III", lambda: quadro_iii(tenant_id, obra_id, parametro=parametro)),
        ("IV", lambda: quadro_iv(tenant_id, obra_id, parametro=parametro, gravar=False)),
    ):
        try:
            resultado["quadros"][codigo] = funcao()
        except DadosInsuficientes as exc:
            resultado["indisponivel"][codigo] = str(exc)

    descritivos = quadros_descritivos(tenant_id, obra_id)
    resultado["quadros"].update({
        codigo.upper(): dados for codigo, dados in descritivos["quadros"].items()
    })
    resultado["descritivos_faltando"] = descritivos["faltando"]
    return resultado
