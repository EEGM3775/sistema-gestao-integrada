"""Põe o nome do empreendimento na descrição dos títulos de carnê já gravados.

**O defeito que isto conserta, no que já existe.** A descrição de um título de
carnê é o texto que o comprador lê no boleto, e ela saía como::

    Parcela 32/36 — QD 4 · LT 06

que identifica o lote para quem já sabe de que loteamento se fala. Quem recebe o
boleto pode ter comprado em dois, e a quadra 4 existe nos dois. A geração passou
a escrever o nome do empreendimento (`plano_pagamento.descricao_do_titulo`); os
títulos anteriores continuam com o texto curto, e é isso que este comando
reescreve::

    Parcela 32/36 — Residencial Aurora · QD 4 · LT 06

**Prévia por padrão.** Sem `--aplicar` ele só conta e mostra exemplos: mexer na
descrição de título já emitido é mexer no que o cliente vai ler, e a mesma régua
de "prévia antes de aplicar" que vale para o reajuste vale aqui.

**Não toca no boleto já emitido.** A descrição vai ao Asaas no momento da
emissão; um boleto que já existe no gateway continua com o texto de então. O que
muda é o título — e, portanto, todo boleto emitido daqui para a frente.

    python manage.py renomear_titulos_do_carne                    # prévia
    python manage.py renomear_titulos_do_carne --aplicar
    python manage.py renomear_titulos_do_carne --tenant demo --aplicar
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from moduloerp.models import ContaReceber
from nucleo.models import Tenant
from nucleo.tenancy import rls_bypass

#: O separador que a geração usa entre "o que a parcela é" e "qual unidade ela
#: paga". É por ele que se sabe onde inserir o empreendimento sem reescrever a
#: parte da esquerda, que continua correta.
SEPARADOR = " — "


class Command(BaseCommand):
    help = "Acrescenta o nome do empreendimento à descrição dos títulos de carnê."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="Slug do tenant. Vazio = todos.")
        parser.add_argument(
            "--aplicar", action="store_true",
            help="Grava. Sem isto, só mostra o que mudaria.",
        )

    def handle(self, *args, **opcoes):
        aplicar = opcoes["aplicar"]
        with rls_bypass():
            titulos = (
                ContaReceber.objects.filter(cliente_empreendimento__isnull=False)
                .select_related("empreendimento", "cliente_empreendimento__empreendimento")
                .order_by("pk")
            )
            if opcoes["tenant"]:
                tenant = Tenant.objects.filter(slug=opcoes["tenant"]).first()
                if tenant is None:
                    self.stderr.write(f"Tenant '{opcoes['tenant']}' não existe.")
                    return
                titulos = titulos.filter(tenant=tenant)

            alterados, exemplos = [], []
            for titulo in titulos.iterator(chunk_size=2000):
                nova = self._reescrever(titulo)
                if nova is None:
                    continue
                if len(exemplos) < 5:
                    exemplos.append((titulo.descricao, nova))
                titulo.descricao = nova
                alterados.append(titulo)

            self.stdout.write(f"{len(alterados)} título(s) a renomear.")
            for antes, depois in exemplos:
                self.stdout.write(f"  {antes}\n    → {depois}")

            if not alterados:
                return
            if not aplicar:
                self.stdout.write(self.style.WARNING("Prévia — nada gravado. Use --aplicar."))
                return

            with transaction.atomic():
                ContaReceber.objects.bulk_update(alterados, ["descricao"], batch_size=1000)
            self.stdout.write(self.style.SUCCESS(f"{len(alterados)} título(s) renomeado(s)."))

    @staticmethod
    def _reescrever(titulo) -> str | None:
        """A nova descrição, ou `None` quando não há o que fazer.

        Devolve `None` — e não a mesma string — para o comando poder dizer
        quantos títulos ele realmente mexeu. Reexecutável: o título que já tem o
        nome do empreendimento cai aqui e é ignorado.
        """
        aquisicao = titulo.cliente_empreendimento
        empreendimento = titulo.empreendimento or getattr(aquisicao, "empreendimento", None)
        nome = getattr(empreendimento, "empreendimento", "") or ""
        descricao = titulo.descricao or ""
        if not nome or SEPARADOR not in descricao:
            return None
        esquerda, direita = descricao.split(SEPARADOR, 1)
        if direita.startswith(f"{nome} · ") or nome in direita:
            return None
        return f"{esquerda}{SEPARADOR}{nome} · {direita}"
