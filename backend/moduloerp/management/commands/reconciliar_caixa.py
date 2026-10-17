"""Confere o caixa: todo título com `valor_pago` precisa ter o mesmo valor em `Transacao`.

A baixa (`dar_baixa`) é o único caminho que grava as duas coisas juntas. Título
quitado por outro caminho — carga direta, semeador de demo — fica pago na lista
e **ausente do fluxo de caixa**, que lê o ledger (item 88 do dono).

Sem `--aplicar` só relata. Com ele, lança a diferença como `Transacao` datada do
dia do pagamento, para o caixa de cada empresa voltar a bater com os títulos.
"""
from datetime import datetime, time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone

from moduloerp.models import ContaPagar, ContaReceber, Transacao
from nucleo.tenancy import rls_bypass


class Command(BaseCommand):
    help = "Relata (ou lança) os pagamentos de título que faltam no ledger de caixa."

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true", help="Grava as Transacao que faltam.")

    def handle(self, *args, aplicar=False, **opcoes):
        with rls_bypass():
            for rotulo, modelo, relacao, tipo, campo_data in (
                ("pagar", ContaPagar, "conta_pagar", Transacao.TipoTransacao.SAIDA, "data_pagamento"),
                ("receber", ContaReceber, "conta_receber", Transacao.TipoTransacao.ENTRADA, "data_recebimento"),
            ):
                lancados = dict(
                    Transacao.objects.filter(**{f"{relacao}__isnull": False})
                    .values_list(f"{relacao}_id").annotate(total=Sum("valor"))
                )
                novas, divergentes = [], 0
                for titulo in modelo.objects.filter(valor_pago__gt=0).iterator(chunk_size=2000):
                    falta = titulo.valor_pago - lancados.get(titulo.pk, Decimal("0"))
                    if falta == 0:
                        continue
                    if falta < 0:
                        divergentes += 1  # lançado a mais: não se mexe sozinho
                        continue
                    dia = getattr(titulo, campo_data) or titulo.data_vencimento
                    novas.append(Transacao(
                        tenant_id=titulo.tenant_id, entidade_id=titulo.entidade_id,
                        empreendimento_id=titulo.empreendimento_id, obra_id=titulo.obra_id,
                        descricao=f"Reconciliação do caixa — {titulo.descricao[:200]}",
                        valor=falta, tipo=tipo, meio_pagamento="Reconciliação",
                        data_transacao=timezone.make_aware(datetime.combine(dia, time.min)),
                        **{relacao: titulo},
                    ))
                self.stdout.write(f"{rotulo}: {len(novas)} sem lançamento no caixa, {divergentes} lançados a mais.")
                if aplicar and novas:
                    Transacao.objects.bulk_create(novas, batch_size=1000)
                    self.stdout.write(self.style.SUCCESS(f"{rotulo}: {len(novas)} lançadas."))
