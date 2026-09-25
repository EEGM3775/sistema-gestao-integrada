"""Deixa o PDP (SpiceDB) igual às tabelas da IAM — remodelagem, fase 2.

    python manage.py sincronizar_pdp                # grava o schema e reconcilia tudo, uma vez
    python manage.py sincronizar_pdp --tenant <id>  # só uma empresa
    python manage.py sincronizar_pdp --continuo     # o processo `iam-pdp` do compose

O modo contínuo faz três coisas, nesta ordem de urgência: refaz na hora o
tenant cuja escrita falhou (fila de pendentes no Redis), e a cada
`AUTORIZACAO_SINCRONIA_PERIODO_S` reconcilia tudo — é o que leva ao PDP a
assinatura que venceu à meia-noite e o que foi mudado por SQL cru.
"""
from __future__ import annotations

import signal
import time

from django.core.management.base import BaseCommand, CommandError

from funcoesautorizacao.cliente import ErroDoPdp
from identity import pdp
from payment.planos import AUTORIZACAO_SINCRONIA_PERIODO_S

# Cadência do laço: de quanto em quanto tempo a fila de pendentes é olhada.
# Não é teto (§5.6): é o passo do relógio do processo, não o quanto alguém pode.
_PASSO_S = 1.0


class Command(BaseCommand):
    help = "Reconcilia as relações do PDP (SpiceDB) com papéis, acessos e assinaturas da IAM."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="Só esta empresa (id).")
        parser.add_argument("--continuo", action="store_true",
                            help="Não termina: fila de pendentes + volta periódica.")

    def handle(self, *args, **opts):
        if not pdp.ativo():
            raise CommandError("SPICEDB_URL não configurada.")
        if opts["continuo"]:
            return self._continuo()
        pdp.garantir_esquema()
        if opts["tenant"]:
            r = pdp.reconciliar_tenant(opts["tenant"])
        else:
            r = pdp.reconciliar_tudo()
        self.stdout.write(self.style.SUCCESS(f"PDP em dia: {r}"))

    def _continuo(self):
        parar = {"agora": False}
        signal.signal(signal.SIGTERM, lambda *_: parar.update(agora=True))

        # O schema primeiro: sem ele, toda escrita é recusada. O PDP pode estar
        # subindo junto — insiste até conseguir.
        while not parar["agora"]:
            try:
                pdp.garantir_esquema()
                self.stdout.write("pdp: schema gravado")
                break
            except ErroDoPdp as exc:
                self.stderr.write(f"pdp: schema ainda não gravado ({exc}); tentando de novo")
                time.sleep(5)

        ultima_volta = 0.0
        while not parar["agora"]:
            agora = time.monotonic()
            try:
                if agora - ultima_volta >= AUTORIZACAO_SINCRONIA_PERIODO_S:
                    r = pdp.reconciliar_tudo()
                    ultima_volta = agora
                    if r["tocadas"] or r["removidas"]:
                        self.stdout.write(f"pdp: volta periódica {r}")
                acertados = pdp.drenar_pendentes()
                if acertados:
                    self.stdout.write(f"pdp: {acertados} pendente(s) refeito(s)")
            except Exception as exc:  # noqa: BLE001 - o processo não morre por um PDP fora
                self.stderr.write(f"pdp: volta falhou ({exc}); tentando de novo")
                time.sleep(5)
                continue
            time.sleep(_PASSO_S)
