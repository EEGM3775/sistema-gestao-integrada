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

    # EMBASA: ver o que o semestre publicou, carregar uma tabela, carregar tudo
    manage.py carregar_base_oficial --fonte embasa --listar
    manage.py carregar_base_oficial --fonte embasa \\
        --documento 1-1serv-exp-deson-jun-2026-h-158-56-m-119-40-r2
    manage.py carregar_base_oficial --fonte embasa --todas

**`--todas` é de bancada, e só de bancada.** Carregar as 65 tabelas da EMBASA é
uma hora de relógio entre download e extração de PDF — mais que o
`ORCAMENTO_CARGA_SEGUNDOS` do dono, que mede **uma** corrida. Pela tela, cada
documento é uma corrida sua, com o próprio registro e a própria falha; aqui a
bancada as enfileira em sequência porque quem está no terminal pode esperar, e
uma tabela que falhe não derruba as outras.
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
        parser.add_argument(
            "--listar", action="store_true",
            help="Só lista os documentos que a fonte publica — não carrega nada.",
        )
        parser.add_argument(
            "--documento", default="",
            help="URL (ou slug) do documento a carregar, quando a fonte publica vários.",
        )
        parser.add_argument(
            "--todas", action="store_true",
            help="Carrega, em sequência, todos os documentos carregáveis da fonte.",
        )
        parser.add_argument("--por", default="bancada", help="Quem rodou (registro na carga).")

    def handle(self, *args, **opcoes):
        fonte = opcoes["fonte"]
        competencia = (
            self._parse_mes(opcoes["mes"]) if opcoes["mes"]
            else carga.competencia_sugerida(fonte)
        )
        if opcoes["listar"]:
            self._listar(fonte, competencia)
            return
        if opcoes["todas"]:
            if opcoes["arquivo"] or opcoes["documento"]:
                raise CommandError(
                    "--todas carrega a lista inteira da fonte; não combina com "
                    "--documento nem com --arquivo."
                )
            self._carregar_todas(fonte, competencia, opcoes)
            return
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
            url_origem=self._resolver_documento(opcoes["documento"], fonte),
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

    # --------------------------------------------------- fonte com vários docs

    def _listar(self, fonte: str, competencia) -> None:
        documentos = carga.documentos_disponiveis(fonte, competencia)
        if not documentos:
            raise CommandError(
                f"A fonte {fonte} não tem endereço cadastrado (FonteOficial) ou o "
                "template não resolveu para esta competência."
            )
        carregaveis = sum(1 for d in documentos if d["carregavel"])
        self.stdout.write(
            f"{len(documentos)} documento(s) publicado(s), {carregaveis} carregável(is):"
        )
        for documento in documentos:
            marca = " " if documento["carregavel"] else "·"
            self.stdout.write(
                f"  {marca} [{documento['especie']:<8}] {documento['rotulo'][:62]:<62} "
                f"{documento['slug']}"
            )

    def _resolver_documento(self, bruto: str, fonte: str) -> str:
        """Slug ou URL → URL absoluta, conferida contra o endereço da fonte.

        Aceitar o slug é o que torna o comando utilizável: o nome do documento da
        EMBASA tem 46 caracteres e é o que a lista imprime. Aceitar só a URL
        obrigaria a copiar 80 caracteres para carregar cada uma das 65 tabelas.
        """
        alvo = (bruto or "").strip()
        if not alvo:
            return ""
        if alvo.startswith(("http://", "https://")):
            return alvo[:500]
        for documento in carga.documentos_disponiveis(fonte):
            if documento["slug"] == alvo:
                return documento["url"][:500]
        raise CommandError(
            f"Documento '{alvo}' não está na lista publicada por {fonte}. "
            "Rode com --listar para ver os slugs válidos."
        )

    def _carregar_todas(self, fonte: str, competencia, opcoes) -> None:
        """Enfileira uma corrida por documento carregável, em sequência.

        Cada uma é uma `CargaBase` própria — falhar na décima não apaga as nove
        que entraram, e o histórico diz qual documento deu em quê. É o mesmo
        princípio do `gravar_publicacoes`, que grava uma UF por vez.
        """
        documentos = [d for d in carga.documentos_disponiveis(fonte, competencia) if d["carregavel"]]
        if not documentos:
            raise CommandError(f"Nenhum documento carregável publicado por {fonte}.")
        self.stdout.write(f"{len(documentos)} documento(s) a carregar, um por corrida.\n")

        falhas = 0
        for numero, documento in enumerate(documentos, start=1):
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"[{numero}/{len(documentos)}] {documento['rotulo'][:70]}"
                )
            )
            registro = CargaBase.objects.create(
                fonte=fonte,
                competencia=competencia,
                origem=CargaBase.Origem.DOWNLOAD,
                url_origem=documento["url"][:500],
                somente_resumo=opcoes["resumo"],
                aceitar_sem_classe=opcoes["aceitar_sem_classe"],
                solicitada_por_nome=opcoes["por"][:150],
            )
            carga.executar(registro, None)
            try:
                self._relatar(registro)
            except CommandError as exc:
                # A corrida guarda o próprio desfecho; aqui a falha de uma não
                # pode interromper a fila — é justamente por isso que cada
                # documento é uma corrida separada.
                falhas += 1
                self.stdout.write(self.style.ERROR(f"  FALHOU: {exc}"))

        if falhas:
            raise CommandError(
                f"{falhas} de {len(documentos)} documento(s) falharam — o histórico "
                "de cargas diz qual e por quê."
            )
        self.stdout.write(self.style.SUCCESS(f"OK | {len(documentos)} documento(s) carregado(s)."))

    # ------------------------------------------------------------------ saída

    def _relatar(self, registro: CargaBase) -> None:
        resumo = registro.resumo or {}
        if resumo.get("rotulo"):
            # Fonte com menu: o rótulo é a conferência de que veio o documento
            # certo — ele traz escopo, convenção e a LS do cabeçalho do PDF.
            self.stdout.write(f"  {resumo['rotulo']}")
        if resumo.get("publicacoes"):
            self.stdout.write(
                f"  Arquivo: {resumo.get('planilha') or '—'} · "
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
