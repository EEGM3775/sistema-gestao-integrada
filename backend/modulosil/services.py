# backend/modulosil/services.py
"""Regras de negócio do estoque (SIL) — o único lugar que altera saldo.

Custo médio **ponderado móvel** (norma brasileira): toda entrada recalcula o
`custo_medio`; saídas valorizam pelo custo médio vigente. Reserva protege o saldo
comprometido. Integrações vivas: entrada automática do Recebimento do SCM e
geração de Demanda (origem=estoque) quando o item cai abaixo do mínimo.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .events import emitir_evento_dominio
from .models import (
    Devolucao,
    Inventario,
    LocalEstoque,
    MovimentacaoEstoque,
    Requisicao,
    SaldoEstoque,
    Transferencia,
)

D0 = Decimal("0")
Tipo = MovimentacaoEstoque.Tipo


class EstoqueInsuficiente(Exception):
    """Saída/consumo maior que o saldo disponível no local."""


def _dec(v):
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _saldo(tenant_id, item_id, local_id, lock=True):
    """Saldo (item, local), criado se ainda não existe. Trava a linha (lock)
    para o read-modify-write do custo médio ser seguro sob concorrência."""
    qs = SaldoEstoque.objects.filter(tenant_id=tenant_id, item_id=item_id, local_id=local_id)
    if lock:
        qs = qs.select_for_update()
    saldo = qs.first()
    if saldo is None:
        saldo = SaldoEstoque.objects.create(tenant_id=tenant_id, item_id=item_id, local_id=local_id)
        if lock:
            saldo = SaldoEstoque.objects.select_for_update().get(pk=saldo.pk)
    return saldo


def _registrar(tenant_id, item_id, local_id, tipo, quantidade, custo_unitario, **extra):
    return MovimentacaoEstoque.objects.create(
        tenant_id=tenant_id, item_id=item_id, local_id=local_id, tipo=tipo,
        quantidade=_dec(quantidade), custo_unitario=_dec(custo_unitario or 0), **extra,
    )


def _checar_minimo(saldo):
    if saldo.abaixo_minimo:
        emitir_evento_dominio("sil.estoque_minimo_atingido", saldo.tenant_id, {
            "item_id": saldo.item_id, "local_id": saldo.local_id,
            "quantidade": str(saldo.quantidade), "ponto_reposicao": str(saldo.ponto_reposicao),
        })


@transaction.atomic
def aplicar_entrada(tenant_id, item_id, local_id, quantidade, custo_unitario=0, tipo=None, **extra):
    """Entrada: soma ao saldo e recalcula o custo médio ponderado móvel."""
    quantidade = _dec(quantidade)
    custo = _dec(custo_unitario or 0)
    saldo = _saldo(tenant_id, item_id, local_id)
    q0, c0 = saldo.quantidade, saldo.custo_medio
    qn = q0 + quantidade
    if qn > 0:
        saldo.custo_medio = (q0 * c0 + quantidade * custo) / qn
    saldo.quantidade = qn
    saldo.save(update_fields=["quantidade", "custo_medio"])
    mov = _registrar(tenant_id, item_id, local_id, tipo or Tipo.ENTRADA, quantidade, custo, **extra)
    _checar_minimo(saldo)
    return mov


@transaction.atomic
def aplicar_saida(tenant_id, item_id, local_id, quantidade, tipo=None, usar_reserva=False, **extra):
    """Saída: subtrai do saldo (valorizada pelo custo médio). Bloqueia se o saldo
    for insuficiente. `usar_reserva` também libera o reservado (consumo de requisição)."""
    quantidade = _dec(quantidade)
    saldo = _saldo(tenant_id, item_id, local_id)
    if quantidade > saldo.quantidade:
        raise EstoqueInsuficiente(
            f"Saldo insuficiente ({saldo.quantidade}) para saída de {quantidade}."
        )
    saldo.quantidade -= quantidade
    if usar_reserva:
        saldo.reservado = max(D0, saldo.reservado - quantidade)
    saldo.save(update_fields=["quantidade", "reservado"])
    mov = _registrar(tenant_id, item_id, local_id, tipo or Tipo.SAIDA, quantidade, saldo.custo_medio, **extra)
    _checar_minimo(saldo)
    return mov


@transaction.atomic
def aplicar_ajuste(tenant_id, item_id, local_id, quantidade_alvo, custo_unitario=None, **extra):
    """Ajuste de inventário: leva o saldo à quantidade contada. Ajuste positivo
    entra ao custo informado (senão preserva o custo médio)."""
    alvo = _dec(quantidade_alvo)
    saldo = _saldo(tenant_id, item_id, local_id)
    delta = alvo - saldo.quantidade
    if delta == 0:
        return None
    if delta > 0 and custo_unitario is not None:
        c = _dec(custo_unitario)
        qn = saldo.quantidade + delta
        if qn > 0:
            saldo.custo_medio = (saldo.quantidade * saldo.custo_medio + delta * c) / qn
    saldo.quantidade = alvo
    saldo.save(update_fields=["quantidade", "custo_medio"])
    observacao = extra.pop("observacao", "") or f"Ajuste de inventário ({delta:+f})"
    mov = _registrar(tenant_id, item_id, local_id, Tipo.AJUSTE, abs(delta), saldo.custo_medio, observacao=observacao, **extra)
    _checar_minimo(saldo)
    return mov


@transaction.atomic
def reservar(tenant_id, item_id, local_id, quantidade):
    saldo = _saldo(tenant_id, item_id, local_id)
    saldo.reservado += _dec(quantidade)
    saldo.save(update_fields=["reservado"])
    return saldo


# ---------------------------------------------------------------------------
# Documentos de logística
# ---------------------------------------------------------------------------
def aprovar_requisicao(requisicao, aprovador=None):
    with transaction.atomic():
        for it in requisicao.itens.all():
            reservar(requisicao.tenant_id, it.item_id, requisicao.local_id, it.quantidade)
        requisicao.status = Requisicao.Status.APROVADA
        if aprovador is not None and getattr(aprovador, "pk", None):
            requisicao.aprovador = aprovador
        requisicao.save(update_fields=["status", "aprovador"])
    return requisicao


def atender_requisicao(requisicao):
    with transaction.atomic():
        tenant_id = requisicao.tenant_id
        completo = True
        for it in requisicao.itens.all():
            pendente = it.quantidade - it.quantidade_atendida
            if pendente <= 0:
                continue
            saldo = _saldo(tenant_id, it.item_id, requisicao.local_id)
            entregar = min(pendente, saldo.quantidade)
            if entregar <= 0:
                completo = False
                continue
            aplicar_saida(
                tenant_id, it.item_id, requisicao.local_id, entregar, usar_reserva=True,
                requisicao=requisicao, obra_id=requisicao.obra_id, etapa_id=requisicao.etapa_id,
                observacao=f"Atendimento da requisição #{requisicao.requisicao_id}",
            )
            it.quantidade_atendida += entregar
            it.save(update_fields=["quantidade_atendida"])
            if entregar < pendente:
                completo = False
        requisicao.status = Requisicao.Status.ATENDIDA if completo else Requisicao.Status.PARCIAL
        requisicao.save(update_fields=["status"])
    return requisicao


def executar_transferencia(transferencia):
    with transaction.atomic():
        if transferencia.status == Transferencia.Status.EXECUTADA:
            return transferencia
        tenant_id = transferencia.tenant_id
        for it in transferencia.itens.all():
            saldo_origem = _saldo(tenant_id, it.item_id, transferencia.origem_id)
            custo = saldo_origem.custo_medio
            aplicar_saida(
                tenant_id, it.item_id, transferencia.origem_id, it.quantidade,
                tipo=Tipo.TRANSF_SAIDA, transferencia=transferencia, lote_id=it.lote_id,
                observacao=f"Transferência #{transferencia.transferencia_id} (saída)",
            )
            aplicar_entrada(
                tenant_id, it.item_id, transferencia.destino_id, it.quantidade, custo,
                tipo=Tipo.TRANSF_ENTRADA, transferencia=transferencia, lote_id=it.lote_id,
                observacao=f"Transferência #{transferencia.transferencia_id} (entrada)",
            )
        transferencia.status = Transferencia.Status.EXECUTADA
        transferencia.save(update_fields=["status"])
    return transferencia


def executar_devolucao(devolucao):
    with transaction.atomic():
        if devolucao.status == Devolucao.Status.EXECUTADA:
            return devolucao
        tenant_id = devolucao.tenant_id
        for it in devolucao.itens.all():
            if devolucao.tipo == Devolucao.Tipo.FORNECEDOR:
                aplicar_saida(
                    tenant_id, it.item_id, devolucao.local_id, it.quantidade,
                    tipo=Tipo.DEVOLUCAO, devolucao=devolucao, lote_id=it.lote_id,
                    observacao=f"Devolução ao fornecedor #{devolucao.devolucao_id}",
                )
            else:
                # Estorno ao estoque: reentra ao custo médio vigente (não distorce a valorização).
                saldo = _saldo(tenant_id, it.item_id, devolucao.local_id)
                aplicar_entrada(
                    tenant_id, it.item_id, devolucao.local_id, it.quantidade, saldo.custo_medio,
                    tipo=Tipo.DEVOLUCAO, devolucao=devolucao, lote_id=it.lote_id,
                    observacao=f"Devolução ao estoque #{devolucao.devolucao_id}",
                )
        devolucao.status = Devolucao.Status.EXECUTADA
        devolucao.save(update_fields=["status"])
    return devolucao


def fechar_inventario(inventario):
    with transaction.atomic():
        if inventario.status == Inventario.Status.FECHADO:
            return inventario
        tenant_id = inventario.tenant_id
        for it in inventario.itens.all():
            antes = _saldo(tenant_id, it.item_id, inventario.local_id).quantidade
            aplicar_ajuste(
                tenant_id, it.item_id, inventario.local_id, it.quantidade_contada,
                inventario=inventario, observacao=f"Inventário #{inventario.inventario_id}",
            )
            # O ledger não guarda o sentido do ajuste; reabrir precisa dele.
            it.ajuste_aplicado = _dec(it.quantidade_contada) - antes
            it.save(update_fields=["ajuste_aplicado"])
        inventario.status = Inventario.Status.FECHADO
        inventario.fechado_em = timezone.now()
        inventario.save(update_fields=["status", "fechado_em"])
    return inventario


def reabrir_inventario(inventario):
    """Volta a contagem para aberta **estornando** o que o fechamento ajustou.

    O estorno é o ajuste ao contrário, aplicado sobre o saldo de **hoje** — e
    não "volta ao saldo de antes": o que entrou e saiu depois do fechamento é
    real e fica. Recusa se o estorno deixaria algum saldo negativo (o material
    já foi consumido). Contagem fechada antes de o ajuste ser guardado volta a
    abrir sem estorno; refechar acerta o saldo, porque o fechamento leva o saldo
    à quantidade contada.
    """
    with transaction.atomic():
        if inventario.status != Inventario.Status.FECHADO:
            raise ValidationError("Só um inventário fechado se reabre.")
        tenant_id = inventario.tenant_id
        itens = list(inventario.itens.select_related("item").exclude(ajuste_aplicado=None))
        for it in itens:
            if not it.ajuste_aplicado:
                continue
            saldo = _saldo(tenant_id, it.item_id, inventario.local_id)
            if saldo.quantidade - it.ajuste_aplicado < 0:
                raise ValidationError(
                    f"{it.item.descricao}: estornar o ajuste deixaria o saldo negativo — "
                    f"o material já saiu depois do inventário."
                )
        for it in itens:
            if it.ajuste_aplicado:
                saldo = _saldo(tenant_id, it.item_id, inventario.local_id)
                saldo.quantidade -= it.ajuste_aplicado
                saldo.save(update_fields=["quantidade"])
                _registrar(
                    tenant_id, it.item_id, inventario.local_id, Tipo.AJUSTE,
                    abs(it.ajuste_aplicado), saldo.custo_medio, inventario=inventario,
                    observacao=f"Estorno do inventário #{inventario.inventario_id} (reaberto)",
                )
            it.ajuste_aplicado = None
            it.save(update_fields=["ajuste_aplicado"])
        inventario.status = Inventario.Status.ABERTO
        inventario.fechado_em = None
        inventario.save(update_fields=["status", "fechado_em"])
    return inventario


# ---------------------------------------------------------------------------
# Integrações vivas com o SCM
# ---------------------------------------------------------------------------
def _resolver_local_entrega(tenant_id, ref):
    """Resolve o LocalEstoque de destino de um recebimento a partir do seam
    `local_entrega` (id ou nome); senão o central ativo; auto-provisiona um
    'Almoxarifado Central' na 1ª entrada, para o laço funcionar sem setup."""
    ref = (ref or "").strip()
    q = LocalEstoque.objects.filter(tenant_id=tenant_id)
    if ref.isdigit():
        le = q.filter(pk=int(ref)).first()
        if le:
            return le
    if ref:
        le = q.filter(nome__iexact=ref).first()
        if le:
            return le
    le = q.filter(tipo=LocalEstoque.Tipo.CENTRAL, ativo=True).order_by("local_id").first()
    if le is None:
        le = q.filter(ativo=True).order_by("local_id").first()
    if le is None:
        le = LocalEstoque.objects.create(tenant_id=tenant_id, nome="Almoxarifado Central", tipo=LocalEstoque.Tipo.CENTRAL)
    return le


def registrar_entrada_de_item_recebimento(item_recebimento):
    """Um item de recebimento do SCM → ENTRADA no estoque (ativa o seam
    `local_entrega`). Gatilho é o **item** (no SCM o recebimento nasce antes das
    linhas). Idempotente por `item_recebimento_ref`; só itens do catálogo com
    `estocavel`."""
    ir = item_recebimento
    tenant_id = ir.tenant_id
    if MovimentacaoEstoque.objects.filter(tenant_id=tenant_id, item_recebimento_ref=ir.pk).exists():
        return
    ip = getattr(ir, "item_pedido", None)
    produto = getattr(ip, "produto", None) if ip else None
    if produto is None or not getattr(produto, "estocavel", False):
        return
    recebimento = ir.recebimento
    local = _resolver_local_entrega(tenant_id, getattr(recebimento, "local_entrega", ""))
    aplicar_entrada(
        tenant_id, produto.item_id, local.local_id, ir.quantidade_recebida, ip.preco_unitario,
        recebimento_scm_ref=ir.recebimento_id, item_recebimento_ref=ir.pk,
        observacao=f"Entrada do recebimento SCM #{ir.recebimento_id}",
    )
    # Um aviso por recebimento, não por linha: o título é a chave (régua 3).
    from nucleo.notificacoes import avisar_quem_pode

    avisar_quem_pode(
        tenant_id=tenant_id, permissao="sil.requisicao.atender",
        titulo=f"Recebimento {ir.recebimento_id} do Suprimentos deu entrada no estoque",
        mensagem=f"Entrou no local {local}. Confira as quantidades no Estoque.",
        url="/app/sil",
    )


def registrar_entrada_de_recebimento(recebimento):
    """Reprocessa todas as linhas de um recebimento (útil p/ teste/backfill)."""
    from moduloscm.models import ItemRecebimento  # lazy (evita ciclo na carga)

    itens = (
        ItemRecebimento.objects.filter(tenant_id=recebimento.tenant_id, recebimento_id=recebimento.recebimento_id)
        .select_related("item_pedido", "item_pedido__produto", "recebimento")
    )
    for ir in itens:
        registrar_entrada_de_item_recebimento(ir)


def gerar_demanda_de_saldo(saldo, quantidade, user=None):
    """SIL → SCM: cria uma Demanda (origem=estoque) para repor o item."""
    from moduloscm.models import Demanda, ItemDemanda  # lazy

    tenant_id = saldo.tenant_id
    solicitante = user if (user is not None and getattr(user, "pk", None)) else None
    demanda = Demanda.objects.create(
        tenant_id=tenant_id, tipo=Demanda.Tipo.MATERIAL, origem=Demanda.Origem.ESTOQUE,
        status=Demanda.Status.ABERTA, solicitante=solicitante,
        observacao=f"Reposição de estoque (item abaixo do mínimo no local {saldo.local_id}).",
    )
    ItemDemanda.objects.create(
        tenant_id=tenant_id, demanda=demanda, produto_id=saldo.item_id,
        quantidade=_dec(quantidade), unidade=getattr(saldo.item, "unidade", ""),
    )
    emitir_evento_dominio("sil.demanda_gerada", tenant_id, {
        "demanda_id": demanda.demanda_id, "item_id": saldo.item_id, "quantidade": str(quantidade),
    })
    from nucleo.models import Notificacao
    from nucleo.notificacoes import avisar_quem_pode

    avisar_quem_pode(
        tenant_id=tenant_id, permissao="scm.demanda.edit",
        titulo=f"Estoque pediu reposição: demanda {demanda.demanda_id}",
        mensagem=(
            f"{getattr(saldo.item, 'descricao', saldo.item_id)} abaixo do mínimo no "
            f"local {saldo.local_id} — {_dec(quantidade)} {getattr(saldo.item, 'unidade', '')}."
        ),
        url="/app/scm", nivel=Notificacao.Nivel.DECIDIR,
    )
    return demanda
