"""O vencimento do boleto antes de emitir — feriado, título vencido e encargos.

**O defeito (item 55 do dono).** Ao gerar a cobrança pela conta a receber, a
tela não dizia nada do que a de Clientes já explicava: que o vencimento cai num
feriado e o boleto vai para o próximo dia útil. E com o título já vencido o
botão continuava ativo, sem aviso nem saída — o Asaas recusa `dueDate` no
passado, e o boleto aparecia como "Erro".

**A decisão do dono (30/09/2026):** título vencido ganha uma **nova data
sugerida**, e o boleto cobra **a multa e os juros do contrato** até ela. Este
módulo calcula a prévia que a tela mostra e é a mesma conta que a emissão usa —
a tela nunca promete um valor que o boleto não carrega.

**A regra dos encargos.** O título não muda: `data_vencimento` é o do contrato,
e é por ele que se conta o atraso. Multa uma vez sobre o saldo; juros de mora
pró-rata por dia, do vencimento do contrato até o vencimento do boleto (o dia
em que o cliente pode pagar). O deslocamento de um título **em dia** para o
próximo dia útil não é atraso e não gera encargo — é o calendário do banco, não
o cliente, que empurra a data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from payment.planos import (
    ERP_ENCARGOS_JUROS_MES_PADRAO_PERCENTUAL, ERP_ENCARGOS_MULTA_PADRAO_PERCENTUAL,
    ERP_SEGUNDA_VIA_PRAZO_DIAS,
)

CENTAVO = Decimal("0.01")
DIAS_DO_MES = Decimal("30")  # juros de mora pró-rata: o mês comercial


class VencimentoInvalido(Exception):
    """A data pedida não serve para boleto. `mensagem` é para a tela."""

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


@dataclass(frozen=True)
class Encargos:
    multa: Decimal
    juros: Decimal
    dias: int
    multa_percentual: Decimal
    juros_mes_percentual: Decimal

    @property
    def total(self) -> Decimal:
        return self.multa + self.juros


SEM_ENCARGOS = Encargos(Decimal("0"), Decimal("0"), 0, Decimal("0"), Decimal("0"))


def percentuais(conta) -> tuple[Decimal, Decimal]:
    """`(multa %, juros % ao mês)` do contrato da conta, ou o padrão do dono."""
    aquisicao = getattr(conta, "cliente_empreendimento", None)
    if aquisicao is not None:
        return aquisicao.multa_atraso_percentual, aquisicao.juros_mora_mensal_percentual
    return Decimal(ERP_ENCARGOS_MULTA_PADRAO_PERCENTUAL), Decimal(ERP_ENCARGOS_JUROS_MES_PADRAO_PERCENTUAL)


def encargos_ate(conta, vencimento_do_boleto: date) -> Encargos:
    dias = (vencimento_do_boleto - conta.data_vencimento).days
    saldo = conta.saldo_aberto
    if dias <= 0 or saldo <= 0:
        return SEM_ENCARGOS
    multa_pct, juros_pct = percentuais(conta)
    multa = (saldo * multa_pct / 100).quantize(CENTAVO, ROUND_HALF_UP)
    juros = (saldo * juros_pct / 100 / DIAS_DO_MES * dias).quantize(CENTAVO, ROUND_HALF_UP)
    return Encargos(multa, juros, dias, multa_pct, juros_pct)


def boleto_ativo(conta):
    """O boleto que ainda vale no gateway — o que a segunda via substitui."""
    from moduloerp.models import Boleto

    return (
        conta.boletos.filter(
            status__in=(Boleto.StatusBoleto.EMITIDO, Boleto.StatusBoleto.VENCIDO, Boleto.StatusBoleto.AGUARDANDO),
        )
        .exclude(gateway_id__isnull=True).exclude(gateway_id="")
        .order_by("-criado_em")
        .first()
    )


def planejar(conta, vencimento_pedido: date | None = None) -> dict:
    """A prévia do boleto: datas, motivo do ajuste, encargos e o que será substituído.

    Levanta `VencimentoInvalido` se a data pedida estiver no passado.
    """
    from clientes.vencimento import ajuste_da_conta
    from modulocalendar.dias_uteis import base_sincronizada

    hoje = timezone.localdate()
    vencida = conta.data_vencimento < hoje
    if vencimento_pedido and vencimento_pedido < hoje:
        raise VencimentoInvalido("O vencimento do boleto não pode ser anterior a hoje.")

    if vencimento_pedido:
        base = vencimento_pedido
    elif vencida:
        base = hoje + timedelta(days=ERP_SEGUNDA_VIA_PRAZO_DIAS)
    else:
        base = conta.data_vencimento

    ajuste = ajuste_da_conta(conta)
    bancario, motivo = ajuste.explicar(base)
    # Encargo só por atraso do cliente: a data pedida depois do contrato. O
    # empurrão de sábado para segunda num título em dia não conta.
    encargos = encargos_ate(conta, bancario) if base > conta.data_vencimento else SEM_ENCARGOS
    saldo = conta.saldo_aberto
    anterior = boleto_ativo(conta)

    return {
        "vencimento_contratual": conta.data_vencimento,
        "vencida": vencida,
        "dias_atraso": max(0, (hoje - conta.data_vencimento).days),
        "vencimento_escolhido": base,
        "vencimento_sugerido": hoje + timedelta(days=ERP_SEGUNDA_VIA_PRAZO_DIAS) if vencida else conta.data_vencimento,
        "vencimento_bancario": bancario,
        "motivo_ajuste": motivo,
        "calendario": {
            "uf": ajuste.uf,
            "municipio": bool(ajuste.ibge),
            "feriados_carregados": base_sincronizada(),
            # O dataset municipal só publica alguns anos; nos outros o feriado
            # da cidade sai da regra (data fixa ou móvel com a Páscoa).
            "municipal_projetado": ajuste.municipal_projetado,
        },
        "saldo": saldo,
        "multa": encargos.multa,
        "juros": encargos.juros,
        "dias_encargos": encargos.dias,
        "multa_percentual": encargos.multa_percentual or percentuais(conta)[0],
        "juros_mes_percentual": encargos.juros_mes_percentual or percentuais(conta)[1],
        "total": saldo + encargos.total,
        "boleto_substituido": (
            {"boleto_id": anterior.boleto_id, "vencimento": anterior.data_vencimento, "valor": anterior.valor}
            if anterior else None
        ),
    }
