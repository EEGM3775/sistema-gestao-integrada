# backend/moduloorcamento/management/commands/pacote_base.py
"""DMS.1 — o pacote da base referencial, pela bancada (`moduloorcamento/pacote.py`).

Exemplos::

    # No ambiente que tem a base (dev): tudo, ou um recorte
    manage.py pacote_base exportar /tmp/base.tar
    manage.py pacote_base exportar /tmp/sinapi-2026.tar --fonte sinapi --desde 2026-01

    # No destino (staging/produção): conferir sem gravar, depois importar
    manage.py pacote_base conferir /tmp/base.tar
    manage.py pacote_base importar /tmp/base.tar

Importar de novo o mesmo pacote não duplica nada: publicação que já existe é
pulada pela chave natural. A importação vai em lotes, com um commit por
publicação — se cair no meio, rodar de novo continua de onde parou.
"""
from __future__ import annotations

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from moduloorcamento import pacote


class Command(BaseCommand):
    help = "Exporta, confere ou importa o pacote da base referencial (SINAPI, ORSE, EMBASA…)."

    def add_arguments(self, parser):
        parser.add_argument("acao", choices=["exportar", "conferir", "importar"])
        parser.add_argument("arquivo", help="O .tar do pacote.")
        parser.add_argument("--fonte", action="append", default=[],
                            help="Só esta fonte (repita para mais de uma). Exportar.")
        parser.add_argument("--desde", default="", help="Só competências a partir de AAAA-MM. Exportar.")

    def handle(self, *args, acao, arquivo, fonte, desde, **opts):
        avisar = self.stdout.write
        try:
            if acao == "exportar":
                inicio = datetime.strptime(desde, "%Y-%m").date() if desde else None
                manifesto = pacote.exportar(arquivo, fontes=fonte or None, desde=inicio, avisar=avisar)
                avisar(f"Pacote gravado em {arquivo} (migration {manifesto['migracao']}).")
            elif acao == "conferir":
                manifesto = pacote.conferir(arquivo)
                for nome, meta in manifesto["tabelas"].items():
                    avisar(f"  {nome}: {meta['linhas']} linhas")
                avisar("Pacote íntegro e compatível com este banco.")
            else:
                pacote.importar(arquivo, avisar=avisar)
                avisar("Importação concluída.")
        except pacote.PacoteInvalido as erro:
            raise CommandError(str(erro))
        except ValueError as erro:
            raise CommandError(f"--desde precisa ser AAAA-MM ({erro}).")
