# backend/moduloorcamento/management/commands/carregar_base_oficial.py
"""ORC.8 — a carga da base oficial pela bancada, sem passar pela tela.

**Por que existe, se a fatia inteira é sobre trocar o comando por um botão:**
porque o botão depende de Celery, de gateway e de sessão de `is_platform_admin`,
e a hora em que a carga mais importa é justamente a hora em que uma dessas três
está fora. É a mesma razão de o `--consolidar` da bancada de medição existir ao
lado da tela: instrumento de quem opera a máquina.

O motor é **o mesmo** — `carga.executar`, com a mesma `CargaBase` no banco. O
comando não é um segundo caminho de importação; é outra porta para a mesma.

Exemplos::

    # Baixa a SINAPI do mês que a defasagem da fonte indica
    manage.py carregar_base_oficial --fonte sinapi

    # Confere o que entraria, sem gravar nada
    manage.py carregar_base_oficial --fonte sinapi --mes 2026-07 --resumo

    # Plano B: o ZIP já está em disco
    manage.py carregar_base_oficial --fonte sinapi --mes 2026-07 \\
        --arquivo /tmp/SINAPI-2026-07.zip
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from moduloorcamento import carga, services
from moduloorcamento.models import CargaBase, Fonte


class Command(BaseCommand):
    help = "Carrega uma publicação de base oficial (download ou arquivo local)."

    def add_arguments(self, parser):
        parser.add_argument("--fonte", required=True, choices=[f.value for f in Fonte])
        parser.add_argument(
            "--mes", default="",
            help="Competência AAAA-MM (default: a que a defasagem da fonte indica).",
        )
        parser.add_argument(
            "--arquivo", default="",
            help="ZIP ou .xlsx local, em vez de baixar (o plano B).",
        )
        parser.add_argument(
            "--resumo", action="store_true",
            help="Lê e conta, não grava — o equivalente ao --dry-run do importador.",
        )
        parser.add_argument(
            "--aceitar-sem-classe", dest="aceitar_sem_classe", action="store_true",
            help="Aceita classes sem tradução para natureza (entram pela unidade).",
        )
        parser.add_argument("--por", default="bancada", help="Quem rodou (registro na carga).")

    def handle(self, *args, **opcoes):
        fonte = opcoes["fonte"]
        competencia = (
            self._parse_mes(opcoes["mes"]) if opcoes["mes"]
            else carga.competencia_sugerida(fonte)
        )
        # Mesma razão do importador: o de-para de classes é cacheado por
        # processo, e numa bancada o arquivo pode ter acabado de ser editado —
        # justamente por causa da recusa da corrida anterior.
        services.esquecer_classes_declaradas()

        conteudo = None
        nome = ""
        if opcoes["arquivo"]:
            caminho = Path(opcoes["arquivo"])
            if not caminho.exists():
                raise CommandError(f"Arquivo não encontrado: {caminho}")
            conteudo = caminho.read_bytes()
            nome = caminho.name

        registro = CargaBase.objects.create(
            fonte=fonte,
            competencia=competencia,
            origem=(
                CargaBase.Origem.UPLOAD if conteudo is not None
                else CargaBase.Origem.DOWNLOAD
            ),
            arquivo_nome=nome[:255],
            somente_resumo=opcoes["resumo"],
            aceitar_sem_classe=opcoes["aceitar_sem_classe"],
            solicitada_por_nome=opcoes["por"][:150],
        )
        self.stdout.write(
            f"Carga #{registro.pk}: {registro.get_fonte_display()} {competencia:%m/%Y} "
            f"({registro.get_origem_display().lower()})."
        )

        carga.executar(registro, conteudo)
        self._relatar(registro)

    # ------------------------------------------------------------------ saída

    def _relatar(self, registro: CargaBase) -> None:
        resumo = registro.resumo or {}
        if resumo.get("publicacoes"):
            self.stdout.write(
                f"  Planilha: {resumo.get('planilha') or '—'} · "
                f"analítica: {resumo.get('aba_analitica') or '(nenhuma)'}"
            )
            for publicacao in resumo["publicacoes"][:10]:
                self.stdout.write(
                    f"    {publicacao['uf']} {publicacao['regime']:<10} "
                    f"{publicacao['insumos']:>6} insumos · "
                    f"{publicacao['composicoes']:>6} composições"
                )
            restantes = len(resumo["publicacoes"]) - 10
            if restantes > 0:
                self.stdout.write(f"    … e mais {restantes} publicação(ões).")
        for aviso in resumo.get("avisos", []):
            self.stdout.write(self.style.WARNING(f"  ! {aviso}"))

        if registro.estado == CargaBase.Estado.CONCLUIDA:
            if registro.somente_resumo:
                self.stdout.write(self.style.WARNING("--resumo: nada foi gravado."))
                return
            self.stdout.write(self.style.SUCCESS(
                f"OK | {registro.total_publicacoes} publicações, "
                f"{registro.total_insumos} insumos, {registro.total_composicoes} "
                f"composições, {registro.total_analitica} linhas analíticas."
            ))
            return
        if registro.estado == CargaBase.Estado.AGUARDANDO:
            # Não é erro de execução, é uma pergunta — e por isso sai como aviso
            # e não como `CommandError`: o comando fez o que sabia fazer.
            self.stdout.write(self.style.WARNING(registro.erro))
            return
        raise CommandError(registro.erro or "A carga falhou sem motivo registrado.")

    def _parse_mes(self, valor: str):
        for formato in ("%Y-%m", "%Y-%m-%d", "%m/%Y"):
            try:
                return datetime.strptime(valor.strip(), formato).date().replace(day=1)
            except ValueError:
                continue
        raise CommandError(f"--mes inválido: '{valor}'. Use AAAA-MM.")
