"""Intercompany — o par que um título gera para outra entidade do grupo.

docs/modulos/entidades.md §3. Quando um título de uma entidade carrega custo ou
receita que é de outra — o rateio para centro de custo dela, ou a cota dela num
empreendimento sem entidade própria —, o par nasce **no mesmo gesto**: a receber
na que pagou e a pagar na que consumiu (repasse de despesa), ou o contrário
(repasse de receita). Ninguém cria par pela API: este módulo o mantém igual à
origem a cada gravação dela.

**A conta da DRE** (`dre_da_entidade`): a despesa rateada sai de quem pagou (o a
receber do par a abate) e entra em quem consumiu (o a pagar do par é despesa
dela). No consolidado os dois lados se anulam.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import F, Q, Sum

from .models import (
    AnotacaoContaPagar, BaixaRequerRevisao, ContaPagar, ContaReceber, NaturezaIntercompany,
    ParIntercompany, StatusConta,
)

ZERO = Decimal("0")
CENTAVO = Decimal("0.01")
EM_ABERTO = (StatusConta.ABERTO, StatusConta.PARCIAL)
MEIO_COMPENSACAO = "Compensação"


def _q(valor) -> Decimal:
    return (valor or ZERO).quantize(CENTAVO, rounding=ROUND_HALF_UP)


class NadaACompensar(Exception):
    def __init__(self, mensagem):
        super().__init__(mensagem)
        self.mensagem = mensagem


# ─── O que a origem pede ──────────────────────────────────────────────────────

def fracoes_desejadas(origem) -> dict[int, tuple[Decimal, str]]:
    """`{contraparte: (valor, de onde vem)}` — o par que a origem deveria ter hoje."""
    from entidades.models import ParticipacaoEmpreendimento

    if origem.natureza or origem.status == StatusConta.CANCELADO or getattr(origem, "excluido_em", None):
        return {}
    valor = origem.valor or ZERO
    desejado: dict[int, Decimal] = defaultdict(lambda: ZERO)
    motivos: dict[int, list[str]] = defaultdict(list)

    for rateio in origem.rateios.select_related("centro_custo"):
        entidade = rateio.centro_custo.entidade_id
        if entidade and entidade != origem.entidade_id:
            desejado[entidade] += rateio.valor or ZERO
            motivos[entidade].append(f"rateio para {rateio.centro_custo.nome}")

    # A cota: só no empreendimento do grupo sem entidade própria, sobre o que o
    # rateio não mandou para outra entidade, e só se a dona do título participa.
    base = valor - sum(desejado.values(), ZERO)
    emp = origem.empreendimento if origem.empreendimento_id else None
    if base > 0 and emp is not None and emp.entidade_propria_id is None:
        participacoes = list(
            ParticipacaoEmpreendimento.objects.filter(empreendimento=emp).select_related("entidade")
        )
        if len(participacoes) > 1 and any(p.entidade_id == origem.entidade_id for p in participacoes):
            for p in participacoes:
                if p.entidade_id == origem.entidade_id or p.entidade.externa:
                    continue
                desejado[p.entidade_id] += base * p.cota / Decimal("100")
                motivos[p.entidade_id].append(f"cota de {p.cota.normalize()}% em {emp.empreendimento}")

    return {e: (_q(v), "; ".join(motivos[e])) for e, v in desejado.items() if _q(v) > 0}


def precisa_de_par_de_cota(empreendimento) -> bool:
    """O empreendimento reparte por cota: do grupo, sem entidade própria e com mais
    de uma participante. Quem cria título em lote pergunta antes."""
    from entidades.models import ParticipacaoEmpreendimento

    if empreendimento is None or empreendimento.entidade_propria_id is not None:
        return False
    return ParticipacaoEmpreendimento.objects.filter(empreendimento=empreendimento).count() > 1


# ─── Manter o par igual à origem ──────────────────────────────────────────────

def _sem_baixa(*titulos) -> bool:
    return all((t.valor_pago or ZERO) <= 0 for t in titulos)


def _descricao(origem, contraparte_nome: str) -> str:
    return f"Intercompany com {contraparte_nome} — {(origem.descricao or '')[:200]}"


def _criar(origem, contraparte_id, valor, motivo):
    from entidades.models import Entidade

    eh_pagar = isinstance(origem, ContaPagar)
    natureza = NaturezaIntercompany.REPASSE_DESPESA if eh_pagar else NaturezaIntercompany.REPASSE_RECEITA
    contraparte = Entidade.objects.get(pk=contraparte_id)
    dona = origem.entidade
    comum = dict(
        tenant_id=origem.tenant_id, natureza=natureza, valor=valor,
        data_emissao=origem.data_emissao, data_vencimento=origem.data_vencimento,
        empreendimento_id=origem.empreendimento_id,
    )
    # Repasse de despesa: quem pagou tem a receber; quem consumiu tem a pagar.
    # Repasse de receita: quem recebeu tem a pagar; a dona da receita, a receber.
    credora, devedora = (dona, contraparte) if eh_pagar else (contraparte, dona)
    receber = ContaReceber.objects.create(
        entidade=credora, contraparte=devedora, descricao=_descricao(origem, str(devedora)), **comum,
    )
    pagar = ContaPagar.objects.create(
        entidade=devedora, contraparte=credora, descricao=_descricao(origem, str(credora)), **comum,
    )
    return ParIntercompany.objects.create(
        tenant_id=origem.tenant_id,
        origem_pagar=origem if eh_pagar else None, origem_receber=None if eh_pagar else origem,
        entidade_origem_id=origem.entidade_id, contraparte_id=contraparte_id, natureza=natureza,
        valor=valor, titulo_receber=receber, titulo_pagar=pagar, motivo=motivo[:255],
    )


def _anotar_divergencia(par, texto):
    AnotacaoContaPagar.objects.create(
        tenant_id=par.tenant_id, conta_pagar=par.titulo_pagar, tipo=AnotacaoContaPagar.Tipo.DIVERGENCIA,
        origem="intercompany", texto=texto[:4000],
    )


def _ajustar(par, valor, motivo) -> bool:
    receber, pagar = par.titulo_receber, par.titulo_pagar
    if par.valor == valor and receber.status != StatusConta.CANCELADO:
        return False
    if not _sem_baixa(receber, pagar):
        _anotar_divergencia(
            par, f"O título de origem passou a pedir R$ {valor} neste intercompany (era R$ {par.valor}), "
                 "mas o par já tem baixa e não foi mudado. Acerte a diferença à mão.",
        )
        return False
    for titulo in (receber, pagar):
        titulo.valor = valor
        titulo.status = StatusConta.ABERTO
        titulo.save(update_fields=["valor", "status"])
    par.valor, par.motivo = valor, motivo[:255]
    par.save(update_fields=["valor", "motivo", "atualizado_em"])
    return True


def _cancelar(par) -> bool:
    receber, pagar = par.titulo_receber, par.titulo_pagar
    if receber.status == StatusConta.CANCELADO and pagar.status == StatusConta.CANCELADO:
        return False
    if not _sem_baixa(receber, pagar):
        _anotar_divergencia(
            par, "O título de origem não pede mais este intercompany, mas o par já tem baixa e "
                 "continua de pé. Estorne a baixa ou acerte a diferença.",
        )
        return False
    for titulo in (receber, pagar):
        titulo.status = StatusConta.CANCELADO
        titulo.save(update_fields=["status"])
    return True


def sincronizar(origem) -> list[ParIntercompany]:
    """Cria, ajusta ou cancela o par para que bata com a origem. Idempotente."""
    from entidades.regras import modo_simples

    if origem is None or origem.natureza or origem.pk is None:
        return []
    if modo_simples(origem.tenant_id) and not ParIntercompany.objects.filter(
        Q(origem_pagar_id=origem.pk) if isinstance(origem, ContaPagar) else Q(origem_receber_id=origem.pk)
    ).exists():
        return []
    eh_pagar = isinstance(origem, ContaPagar)
    filtro = {"origem_pagar": origem} if eh_pagar else {"origem_receber": origem}
    with transaction.atomic():
        desejado = fracoes_desejadas(origem)
        existentes = {
            p.contraparte_id: p
            for p in ParIntercompany.objects.filter(**filtro).select_related("titulo_receber", "titulo_pagar")
        }
        mudados = []
        for contraparte, par in existentes.items():
            alvo = desejado.pop(contraparte, None)
            if alvo is None:
                if _cancelar(par):
                    mudados.append(par)
            elif _ajustar(par, *alvo):
                mudados.append(par)
        for contraparte, (valor, motivo) in desejado.items():
            mudados.append(_criar(origem, contraparte, valor, motivo))
        if mudados:
            _avisar(origem, mudados)
    return mudados


def _avisar(origem, pares) -> None:
    """Regra do dono (11/10/2026): escrita cruzada tem aviso — o par cria título
    no financeiro de outra entidade."""
    from nucleo.notificacoes import avisar_quem_pode

    nomes = ", ".join(sorted({str(p.contraparte) for p in pares}))
    tipo = "a pagar" if isinstance(origem, ContaPagar) else "a receber"
    avisar_quem_pode(
        tenant_id=origem.tenant_id, permissao="erp.conta_pagar.baixar",
        titulo=f"Intercompany: título {tipo} #{origem.pk} mexeu no financeiro de {nomes}"[:200],
        mensagem=f"{origem.descricao[:200]} — par entre {origem.entidade} e {nomes}.",
        url="/app/erp/intercompany",
    )


# ─── Baixa e estorno do par ───────────────────────────────────────────────────

def espelho_de(titulo):
    """O outro lado do par: o a pagar de um a receber, e vice-versa."""
    if not titulo.natureza:
        return None
    try:
        par = titulo.par_intercompany
    except ParIntercompany.DoesNotExist:
        return None
    return par.titulo_pagar if isinstance(titulo, ContaReceber) else par.titulo_receber


def espelhar_baixa(titulo, *, valor, data, juros, multa, desconto, meio_pagamento, usuario) -> None:
    """A mesma baixa no espelho: o dinheiro que A recebeu de B é o que B pagou a A."""
    espelho = espelho_de(titulo)
    if espelho is None:
        return
    try:
        espelho.dar_baixa(
            valor=valor, data=data, juros=juros, multa=multa, desconto=desconto,
            meio_pagamento=meio_pagamento, usuario=usuario, origem="espelho",
        )
    except BaixaRequerRevisao:
        # O espelho já estava quitado: a revisão fica na fila do financeiro e a
        # baixa deste lado vale.
        pass


# ─── Saldos e encontro de contas ──────────────────────────────────────────────

def _saldo(qs) -> Decimal:
    total = qs.aggregate(
        t=Sum(F("valor") + F("juros") + F("multa") - F("desconto") - F("valor_pago")),
    )["t"]
    return _q(total)


def saldos(tenant_id, entidades: set[int] | None = None) -> list[dict]:
    """Quem deve quanto a quem, em aberto: uma linha por par de entidades."""
    qs = ContaReceber.objects.filter(
        tenant_id=tenant_id, status__in=EM_ABERTO,
    ).exclude(natureza="")
    if entidades is not None:
        qs = qs.filter(Q(entidade_id__in=entidades) | Q(contraparte_id__in=entidades))
    linhas = (
        qs.values("entidade_id", "entidade__nome", "contraparte_id", "contraparte__nome")
        .annotate(saldo=Sum(F("valor") + F("juros") + F("multa") - F("desconto") - F("valor_pago")))
        .order_by("entidade__nome", "contraparte__nome")
    )
    return [
        {
            "credora": l["entidade_id"], "credora_nome": l["entidade__nome"],
            "devedora": l["contraparte_id"], "devedora_nome": l["contraparte__nome"],
            "saldo": str(_q(l["saldo"])),
        }
        for l in linhas if _q(l["saldo"]) > 0
    ]


def previa_encontro(tenant_id, a_id, b_id) -> dict:
    a_recebe = ContaReceber.objects.filter(
        tenant_id=tenant_id, entidade_id=a_id, contraparte_id=b_id, status__in=EM_ABERTO,
    ).exclude(natureza="")
    b_recebe = ContaReceber.objects.filter(
        tenant_id=tenant_id, entidade_id=b_id, contraparte_id=a_id, status__in=EM_ABERTO,
    ).exclude(natureza="")
    a_tem, b_tem = _saldo(a_recebe), _saldo(b_recebe)
    return {
        "a_recebe_de_b": str(a_tem), "b_recebe_de_a": str(b_tem),
        "compensavel": str(min(a_tem, b_tem)), "saldo_final": str(abs(a_tem - b_tem)),
        "quem_fica_devendo": (b_id if a_tem > b_tem else a_id if b_tem > a_tem else None),
        "_qs": (a_recebe, b_recebe),
    }


def encontro_de_contas(tenant_id, a_id, b_id, *, data, usuario) -> dict:
    """Compensa o que A e B devem um ao outro até o menor dos saldos.

    Baixa os a receber dos dois lados, do mais antigo para o mais novo, com o
    meio "Compensação"; cada baixa quita o espelho (o a pagar da outra). Numa
    transação só: ou compensa tudo, ou nada.
    """
    if a_id == b_id:
        raise NadaACompensar("Escolha duas entidades diferentes.")
    with transaction.atomic():
        previa = previa_encontro(tenant_id, a_id, b_id)
        compensar = Decimal(previa["compensavel"])
        if compensar <= 0:
            raise NadaACompensar("Não há saldo dos dois lados para compensar entre estas entidades.")
        baixados = []
        for lista in previa["_qs"]:
            restante = compensar
            for titulo in lista.select_for_update().order_by("data_vencimento", "pk"):
                if restante <= 0:
                    break
                parte = min(titulo.saldo_aberto, restante)
                if parte <= 0:
                    continue
                titulo.dar_baixa(
                    valor=parte, data=data, meio_pagamento=MEIO_COMPENSACAO, usuario=usuario,
                    origem="compensacao",
                )
                restante -= parte
                baixados.append(titulo.pk)
        from nucleo.auditoria import registrar_auditoria
        from nucleo.models import Tenant
        registrar_auditoria(
            acao="encontro_de_contas", modelo="entidades.Entidade", objeto_id=a_id, usuario=usuario,
            tenant=Tenant.objects.get(pk=tenant_id),
            detalhes={"entidades": [a_id, b_id], "valor": str(compensar), "titulos": baixados},
        )
    return {"compensado": str(compensar), "titulos_baixados": baixados}
