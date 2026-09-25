"""Test runner da IAM: os testes moram em `testes/iam/`, não dentro dos apps.

Espelho do que `backend/nucleo/test_runner.py` faz para o backend. Sem rótulo,
descobre `testes/iam` inteiro (`identity` + o pacote compartilhado
`funcoesemail`); um rótulo que começa por um desses (`identity`,
`identity.test_planos`) vira `testes.iam.<...>`. Sem essa tradução,
`manage.py test` a partir de `iam/` rodaria **0 testes e diria OK**.

Não tem o nome `test_*.py` de propósito: não é módulo de teste.
"""
import sys
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test.runner import DiscoverRunner

SUITE = "iam"


def _rotulos_em_testes(rotulos):
    """`testes/` fica ao lado do `BASE_DIR` (clone) ou dentro dele (cópia num contêiner)."""
    base = Path(settings.BASE_DIR)
    for raiz in (base, base.parent):
        pasta = raiz / "testes" / SUITE
        if (pasta / "__init__.py").is_file():
            break
    else:
        raise ImproperlyConfigured(
            f"testes/{SUITE}/ não encontrada em {base} nem em {base.parent}. "
            "Os testes não vão para a imagem: copie `testes/` junto do código."
        )
    if str(raiz) not in sys.path:
        sys.path.insert(0, str(raiz))
    if not rotulos:
        return [str(pasta)]
    pacotes = {p.name for p in pasta.iterdir() if (p / "__init__.py").is_file()}
    return [f"testes.{SUITE}.{r}" if r.split(".")[0] in pacotes else r for r in rotulos]


class TestesDaIamRunner(DiscoverRunner):
    def build_suite(self, test_labels=None, **kwargs):
        return super().build_suite(_rotulos_em_testes(test_labels), **kwargs)
