"""Quem decide "pode?" em cada módulo — a virada da fase 3 e a volta atrás.

    python manage.py modo_autorizacao                    # mostra o modo de cada módulo
    python manage.py modo_autorizacao pdca pdp           # o PDP passa a decidir no PDCA
    python manage.py modo_autorizacao pdca token         # volta ao token, na hora
    python manage.py modo_autorizacao --todos token      # tudo de volta ao token
    python manage.py modo_autorizacao --todos pdp        # a virada de todos (confere o critério de cada um)

docs/acesso-e-permissoes.md §10.12, fase 3: "cada módulo sem divergência antes da
virada". Por isso virar para o PDP **confere o critério** e recusa quando a
sombra viu divergência real no módulo na janela, ou quando a sombra não esteve
ligada tempo bastante para dizer. `--forcar` passa por cima — existe para o
ambiente de teste, onde não há duas semanas de uso real, e fica registrado em
`alterado_por`. Voltar ao token nunca é recusado.

Vale em até alguns segundos em todos os processos (`nucleo/autorizacao.py` relê
a tabela), sem deploy e sem restart. O drone não lê o banco do backend: o
comando espelha o modo de cada módulo no Redis (`funcoesautorizacao/chaves.py`,
`modo_do_modulo`), e o PEP dele relê de lá no mesmo intervalo.
"""
from __future__ import annotations

import getpass
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

import funcoesautorizacao
from funcoesautorizacao import chaves
from nucleo import autorizacao, autorizacao_pdp
from nucleo.models import DivergenciaAutorizacao, ModoAutorizacao
from payment.planos import AUTORIZACAO_SOMBRA_DIAS_SEM_DIVERGENCIA

from .relatorio_pdp import dias_com_sombra


def modulos_conhecidos() -> list[str]:
    cat = funcoesautorizacao.catalogo()
    return sorted(set(cat["modulos_vendaveis"]) | set(cat["modulos_de_fundacao"]))


class Command(BaseCommand):
    help = "Mostra ou troca quem decide o acesso em cada módulo: token ou PDP (remodelagem, fase 3)."

    def add_arguments(self, parser):
        parser.add_argument("modulo", nargs="?")
        parser.add_argument("modo", nargs="?", choices=[ModoAutorizacao.Modo.TOKEN, ModoAutorizacao.Modo.PDP])
        parser.add_argument("--todos", choices=[ModoAutorizacao.Modo.TOKEN, ModoAutorizacao.Modo.PDP],
                            help="Todos os módulos de uma vez.")
        parser.add_argument("--forcar", action="store_true",
                            help="Vira para o PDP sem conferir o critério da sombra.")

    def handle(self, *args, **opts):
        quem = f"{getpass.getuser()} (manage.py)"
        if opts["todos"] == ModoAutorizacao.Modo.TOKEN:
            n = ModoAutorizacao.objects.update(modo=ModoAutorizacao.Modo.TOKEN, alterado_por=quem)
            self._publicar()
            self.stdout.write(self.style.SUCCESS(f"{n} módulo(s) de volta ao token."))
            return
        if opts["todos"] == ModoAutorizacao.Modo.PDP:
            if not settings.SPICEDB_URL:
                raise CommandError("SPICEDB_URL não configurada — não há PDP para decidir.")
            if opts["forcar"]:
                quem += " --forcar"
            else:
                for m in modulos_conhecidos():
                    self._conferir_criterio(m)
            for m in modulos_conhecidos():
                ModoAutorizacao.objects.update_or_create(
                    modulo=m, defaults={"modo": ModoAutorizacao.Modo.PDP, "alterado_por": quem}
                )
            self._publicar()
            self.stdout.write(self.style.SUCCESS(
                f"{len(modulos_conhecidos())} módulo(s): quem decide agora é o PDP."
            ))
            return
        if not opts["modulo"]:
            return self._mostrar()
        modulo, modo = opts["modulo"], opts["modo"]
        if modulo not in modulos_conhecidos():
            raise CommandError(f"Módulo desconhecido: {modulo}. Conhecidos: {', '.join(modulos_conhecidos())}")
        if not modo:
            raise CommandError("Diga o modo: token ou pdp.")
        if modo == ModoAutorizacao.Modo.PDP:
            if not settings.SPICEDB_URL:
                raise CommandError("SPICEDB_URL não configurada — não há PDP para decidir.")
            if not opts["forcar"]:
                self._conferir_criterio(modulo)
            else:
                quem += " --forcar"
        ModoAutorizacao.objects.update_or_create(
            modulo=modulo, defaults={"modo": modo, "alterado_por": quem}
        )
        self._publicar()
        self.stdout.write(self.style.SUCCESS(f"{modulo}: quem decide agora é o {modo}."))

    def _publicar(self) -> None:
        """Esquece o modo lido neste processo e espelha a tabela no Redis (o drone
        lê de lá). Sem Redis, o backend segue certo — ele lê a tabela — e o aviso
        diz que o drone ficou com o modo anterior."""
        autorizacao.esquecer_modos()
        modos = dict(ModoAutorizacao.objects.values_list("modulo", "modo"))
        r = autorizacao_pdp.redis()
        try:
            if r is None:
                raise ConnectionError("disjuntor do Redis aberto")
            pipe = r.pipeline()
            for m in modulos_conhecidos():
                pipe.set(chaves.modo_do_modulo(m), modos.get(m, ModoAutorizacao.Modo.TOKEN))
            pipe.execute()
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(self.style.WARNING(
                f"Modo gravado no banco, mas não espelhado no Redis ({exc}): o drone segue"
                " com o modo anterior até o próximo `modo_autorizacao`."
            ))

    def _conferir_criterio(self, modulo: str) -> None:
        dias = AUTORIZACAO_SOMBRA_DIAS_SEM_DIVERGENCIA
        desde = timezone.now() - timedelta(days=dias)
        reais = DivergenciaAutorizacao.objects.filter(
            modulo=modulo, tipo=DivergenciaAutorizacao.Tipo.REAL, criado_em__gte=desde
        ).count()
        if reais:
            raise CommandError(
                f"{modulo}: {reais} divergência(s) real(is) nos últimos {dias} dias. "
                "Investigue antes de virar (manage.py relatorio_pdp)."
            )
        com_sombra = dias_com_sombra(dias)
        if com_sombra < dias:
            raise CommandError(
                f"A sombra esteve ligada em {com_sombra} dos últimos {dias} dias; o critério "
                f"da fase 2 pede {dias} (payment/planos.py §5.5p). Use --forcar só fora de produção."
            )

    def _mostrar(self):
        modos = dict(ModoAutorizacao.objects.values_list("modulo", "modo"))
        for m in modulos_conhecidos():
            self.stdout.write(f"  {m:<16} {modos.get(m, ModoAutorizacao.Modo.TOKEN)}")
