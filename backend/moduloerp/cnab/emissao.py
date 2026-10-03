"""Do lote de cobrança ao arquivo de remessa (item 52).

Os boletos nascem aqui, prontos para pagar: nosso número da carteira, código
de barras, linha digitável e — para título vencido — a segunda via com multa e
juros do contrato, a mesma conta do Asaas (`funcoescobrancas.segunda_via`). O
banco só passa a aceitar o pagamento depois de registrar a remessa; até o
arquivo de retorno confirmar, o boleto fica "aguardando".

**O pagador precisa de endereço completo.** O banco recusa o registro sem CEP,
endereço, cidade e UF do pagador — e recusa o arquivo inteiro em alguns casos.
Quem não tem fica fora do lote, com a frase do que falta, em vez de levar a
remessa toda junto.

**A segunda via pede a baixa do boleto antigo (D245).** O boleto vencido segue
registrado no banco até alguém o baixar — sem a instrução, o cliente podia
pagar os dois. A mesma remessa que registra a segunda via leva o pedido de
baixa (movimento 02) de cada boleto antigo daquela conta registrado **nesta**
carteira; o retorno de baixa (09/10) o marca "Cancelado". O de outra carteira
não cabe neste arquivo, e fica anotado no item do lote.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from funcoescobrancas.segunda_via import percentuais, planejar

from ..cobranca_lote import LoteRecusado, Triagem
from ..models import Boleto, ContaCobrancaBancaria, ItemLoteCobranca, LoteCobranca, RemessaCnab
from . import remessa240, remessa400
from .bancos import banco_de
from .bancos import NossoNumero
from .codigo_barras import linha_digitavel, montar
from .titulo import PEDIDO_DE_BAIXA, SEM_PAGADOR, Titulo, pagador_do_cliente

CENTAVO = Decimal("0.01")
REGISTRADOS = (Boleto.StatusBoleto.EMITIDO, Boleto.StatusBoleto.VENCIDO)


def nosso_numero_do_boleto(boleto) -> NossoNumero:
    """O nosso número de um boleto já emitido. Todo banco imprime `numero-dv`
    (ou só o número, sem DV), e o impresso fica guardado desde a emissão."""
    dados = boleto.dados_retorno_api if isinstance(boleto.dados_retorno_api, dict) else {}
    impresso = dados.get("nosso_numero_impresso") or boleto.nosso_numero
    dv = impresso.rsplit("-", 1)[1] if "-" in impresso else ""
    return NossoNumero(boleto.nosso_numero, dv, impresso)


def _pedidos_de_baixa(conta, carteira):
    """Os boletos antigos desta conta que o banco ainda cobraria: `(nesta
    carteira, em outra)`."""
    antigos = [
        b for b in conta.boletos.all()
        if b.canal == Boleto.Canal.CNAB and b.status in REGISTRADOS and b.nosso_numero
        and not (b.dados_retorno_api or {}).get("baixa_pedida")
    ]
    nesta = [b for b in antigos if b.conta_cobranca_id == carteira.pk]
    return nesta, [b for b in antigos if b.conta_cobranca_id != carteira.pk]


def emitir_por_remessa(triagem: Triagem, *, carteira: ContaCobrancaBancaria, usuario) -> LoteCobranca:
    banco = banco_de(carteira)
    problemas = banco.problemas(carteira)
    if problemas:
        raise LoteRecusado(f"A carteira \"{carteira.nome}\" está incompleta: {', '.join(problemas)}.")
    alvo = triagem.emitir + triagem.segunda_via
    if not alvo:
        raise LoteRecusado("Nenhuma das contas escolhidas precisa de boleto agora.")

    agora = timezone.localtime()
    hoje = agora.date()
    with transaction.atomic():
        # A carteira trancada: nosso número e sequencial de remessa são
        # contadores, e o banco recusa repetido.
        carteira = ContaCobrancaBancaria.objects.select_for_update().get(pk=carteira.pk)
        lote = LoteCobranca.objects.create(
            tenant=carteira.tenant, canal=Boleto.Canal.CNAB, conta_cobranca=carteira,
            criado_por=usuario, total=len(alvo),
        )
        titulos, boletos, recusas, baixas = [], [], [], []
        segunda_via = {conta.pk for conta, _ in triagem.segunda_via}
        for conta, vencimento in alvo:
            pagador, falta = pagador_do_cliente(conta.cliente)
            if falta:
                frase = f"Falta no cadastro de {conta.cliente.nome_completo}: {', '.join(falta)}."
                recusas.append(frase)
                ItemLoteCobranca.objects.create(
                    tenant=carteira.tenant, lote=lote, conta_receber=conta, vencimento=vencimento,
                    situacao=ItemLoteCobranca.Situacao.ERRO, mensagem=frase,
                )
                continue
            plano = planejar(conta, vencimento)
            nn = banco.nosso_numero(carteira, carteira.proximo_nosso_numero)
            carteira.proximo_nosso_numero += 1
            codigo = montar(banco.codigo, plano["vencimento_bancario"], plano["total"], banco.campo_livre(carteira, nn))
            multa_pct, juros_pct = percentuais(conta)
            juros_dia = (plano["total"] * juros_pct / 100 / 30).quantize(CENTAVO, ROUND_HALF_UP)
            boleto = Boleto.objects.create(
                tenant=carteira.tenant, conta_receber=conta, canal=Boleto.Canal.CNAB, conta_cobranca=carteira,
                status=Boleto.StatusBoleto.AGUARDANDO, valor=plano["total"],
                valor_multa=plano["multa"], valor_juros=plano["juros"],
                data_vencimento=plano["vencimento_bancario"],
                nosso_numero=nn.numero, codigo_barras=codigo, linha_digitavel=linha_digitavel(codigo),
                dados_retorno_api={
                    "nosso_numero_impresso": nn.impresso,
                    **({"ajuste_de_vencimento": {
                        "contratual": conta.data_vencimento.isoformat(),
                        "bancario": plano["vencimento_bancario"].isoformat(),
                        "motivo": plano["motivo_ajuste"],
                    }} if plano["motivo_ajuste"] else {}),
                },
            )
            boletos.append(boleto)
            titulos.append(Titulo(
                boleto_id=boleto.boleto_id, seu_numero=str(conta.conta_receber_id), nosso_numero=nn,
                vencimento=plano["vencimento_bancario"], emissao=hoje, valor=plano["total"],
                juros_dia=juros_dia, multa_percentual=multa_pct, pagador=pagador,
            ))
            nota = ""
            if conta.pk in segunda_via:
                nesta, outras = _pedidos_de_baixa(conta, carteira)
                for antigo in nesta:
                    baixas.append(antigo)
                    titulos.append(Titulo(
                        boleto_id=antigo.boleto_id, seu_numero=str(conta.conta_receber_id),
                        nosso_numero=nosso_numero_do_boleto(antigo), vencimento=antigo.data_vencimento,
                        emissao=hoje, valor=antigo.valor, juros_dia=Decimal("0"),
                        multa_percentual=Decimal("0"), pagador=SEM_PAGADOR, movimento=PEDIDO_DE_BAIXA,
                    ))
                if outras:
                    nota = (
                        "O boleto anterior está registrado em outra carteira ("
                        + ", ".join(sorted({b.conta_cobranca.nome for b in outras if b.conta_cobranca}))
                        + "): peça a baixa dele por uma remessa daquela carteira ou pelo banco."
                    )
            ItemLoteCobranca.objects.create(
                tenant=carteira.tenant, lote=lote, conta_receber=conta, vencimento=vencimento,
                situacao=ItemLoteCobranca.Situacao.EMITIDO, boleto=boleto, mensagem=nota,
            )
        for conta in triagem.com_boleto_valido:
            ItemLoteCobranca.objects.create(
                tenant=carteira.tenant, lote=lote, conta_receber=conta,
                situacao=ItemLoteCobranca.Situacao.IGNORADO, mensagem="Já tem boleto válido.",
            )

        if not titulos:
            exemplos = " ".join(recusas[:3])
            raise LoteRecusado(f"Nenhum boleto pôde ir para o banco. {exemplos}")

        sequencial = carteira.proximo_sequencial_remessa
        carteira.proximo_sequencial_remessa += 1
        gerador = remessa240 if carteira.layout == ContaCobrancaBancaria.Layout.CNAB240 else remessa400
        conteudo = gerador.gerar(carteira, titulos, sequencial, agora)
        entradas = [t for t in titulos if t.entrada]
        remessa = RemessaCnab.objects.create(
            tenant=carteira.tenant, conta_cobranca=carteira, sequencial=sequencial,
            nome_arquivo=f"CB{banco.codigo}{sequencial:06d}.REM", conteudo=conteudo,
            quantidade=len(entradas), valor_total=sum((t.valor for t in entradas), Decimal("0")),
            criado_por=usuario,
        )
        Boleto.objects.filter(pk__in=[b.pk for b in boletos]).update(remessa=remessa)
        for antigo in baixas:
            antigo.dados_retorno_api = {
                **(antigo.dados_retorno_api or {}),
                "baixa_pedida": {"remessa": sequencial, "em": agora.isoformat()},
            }
            antigo.save(update_fields=["dados_retorno_api", "atualizado_em"])
        lote.remessa = remessa
        lote.save(update_fields=["remessa"])
        carteira.save(update_fields=["proximo_nosso_numero", "proximo_sequencial_remessa"])

        from nucleo.auditoria import registrar_auditoria
        registrar_auditoria(
            acao="gerar_remessa_cnab", instance=remessa, usuario=usuario,
            detalhes={"boletos": len(entradas), "pedidos_de_baixa": len(baixas),
                      "valor_total": str(remessa.valor_total), "banco": banco.codigo},
        )
    return lote
