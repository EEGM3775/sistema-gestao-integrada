# testes/backend/funcoesimpexp/test_d73_pdf.py
"""D73 — o buscador de URL do WeasyPrint, e a porta única de PDF.

**O achado era latente, e é o tipo que se fecha antes de doer.** `HTML(string=…)`
roda com o `url_fetcher` padrão, que busca URL de verdade. Nos dois templates de
hoje não há `img`, `url()` nem `|safe`, então não havia SSRF — havia a distância
de uma linha até haver: o primeiro logo de tenant no cabeçalho, e o PDF passa a
buscar `http://169.254.169.254/…` ou `file:///etc/passwd` por conta do HTML.

Dois testes, e o segundo é o que dá durabilidade ao primeiro:

1. **o buscador recusa o que não está embutido** — `http`, `https` e `file` são
   recusados, `data:` passa (não é busca: o conteúdo já está no documento);
2. **ninguém chama `write_pdf()` por fora** — varre o backend atrás de um
   segundo ponto de emissão. Foi assim que o achado nasceu: dois módulos com a
   mesma linha, e fechar um deixaria o outro aberto. Um `write_pdf()` novo em
   qualquer app derruba este teste com o nome do arquivo.
"""
from __future__ import annotations

import pathlib
import re

from django.conf import settings
from django.test import SimpleTestCase

from funcoesimpexp.formatos.escrita import RecursoExternoRecusado, _buscador_sem_rede

#: Onde o `write_pdf()` pode aparecer. É **um** lugar, de propósito.
PORTA_DE_PDF = "funcoesimpexp/formatos/escrita.py"

#: A árvore do backend — o `BASE_DIR`, já que este teste mora em `testes/`, fora dela.
BACKEND = pathlib.Path(settings.BASE_DIR)


class BuscadorSemRedeTests(SimpleTestCase):
    def test_recusa_http_e_https(self):
        for url in ("http://169.254.169.254/latest/meta-data/",
                    "https://exemplo.invalido/logo.png"):
            with self.subTest(url=url), self.assertRaises(RecursoExternoRecusado):
                _buscador_sem_rede(url)

    def test_recusa_file(self):
        """`file://` é o que transforma "gerar PDF" em "ler disco do servidor"."""
        with self.assertRaises(RecursoExternoRecusado):
            _buscador_sem_rede("file:///etc/passwd")

    def test_aceita_data_uri(self):
        """O caminho do logo embutido, quando ele for pedido: sem rede nenhuma."""
        # 1x1 PNG transparente
        uri = ("data:image/png;base64,"
               "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
               "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
        resposta = _buscador_sem_rede(uri)
        # A 69 devolve um `URLFetcherResponse` (a 5x devolvia dict) — o que
        # importa é que os bytes vieram do próprio documento.
        self.assertEqual(resposta.content_type, "image/png")
        self.assertTrue(resposta.read())

    def test_url_relativa_tambem_e_recusada(self):
        """Sem `base_url` ela já falharia; a recusa é explícita para não depender disso."""
        with self.assertRaises(RecursoExternoRecusado):
            _buscador_sem_rede("/static/logo.png")


class PdfSaiMesmoAssimTests(SimpleTestCase):
    """A recusa não pode custar o documento — senão o conserto vira indisponibilidade.

    O raciocínio de que "o WeasyPrint pula o recurso que o `url_fetcher`
    recusou" estava escrito no `escrita.py` como se fosse sabido. Está aqui
    porque a diferença entre pular e abortar é a diferença entre um PDF sem logo
    e um relatório que ninguém consegue emitir — e é comportamento de biblioteca
    de terceiro, que muda de versão.
    """

    HTML_COM_EXTERNO = (
        "<html><body><h1>Relatório</h1>"
        "<img src='http://169.254.169.254/latest/meta-data/'>"
        "<p>corpo</p></body></html>"
    )

    def test_o_pdf_sai_sem_o_recurso_externo(self):
        from funcoesimpexp.formatos.escrita import html_para_pdf

        pdf = html_para_pdf(self.HTML_COM_EXTERNO)
        self.assertTrue(pdf.startswith(b"%PDF"), "não saiu PDF")
        self.assertGreater(len(pdf), 500)


class PortaUnicaDePdfTests(SimpleTestCase):
    """Um `write_pdf()` novo em outro app reabriria o D73 em silêncio."""

    def test_so_o_funcoesimpexp_emite_pdf(self):
        fora = []
        for arquivo in BACKEND.rglob("*.py"):
            if "/migrations/" in arquivo.as_posix() or arquivo.name.startswith("test_"):
                continue
            texto = arquivo.read_text(encoding="utf-8", errors="replace")
            if re.search(r"\.write_pdf\s*\(", texto):
                relativo = arquivo.relative_to(BACKEND).as_posix()
                if relativo != PORTA_DE_PDF:
                    fora.append(relativo)
        self.assertEqual(fora, [], (
            "Estes arquivos emitem PDF por fora da porta única — cada um carrega "
            f"o `url_fetcher` padrão, que busca rede: {fora}. Use "
            "`funcoesimpexp.formatos.escrita.html_para_pdf`."
        ))
