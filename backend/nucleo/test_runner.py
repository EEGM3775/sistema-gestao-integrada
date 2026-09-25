"""
Test runner ciente da RLS fail-closed (Fase 8.1).

Sob a política fail-closed (migration `0011`), **inserir/ler** uma linha de
negócio exige contexto de tenant ou o bypass explícito de plataforma. A maioria
dos testes cria fixtures direto pelo ORM em `setUpTestData`/`setUp` — fora de um
request, sem contexto — e seria barrada pelo `WITH CHECK`.

Este runner arma `app.rls_bypass='on'` em **nível de sessão** (`is_local=false`)
a cada conexão criada durante os testes. Isso espelha produção:

- **seed/plataforma** (fora de request) roda com bypass — como migrações e jobs;
- **cada request** de teste que passa pelo mixin/autenticação arma o tenant com
  `set_config(..., is_local=true)`, que **sobrepõe** o bypass de sessão dentro da
  transação do request → o escopo real por tenant continua sendo exercitado;
- os testes de isolamento dedicados (`test_rls_fail_closed`,
  `test_tenant_isolation`) chamam `clear_rls_context()`/`arm_rls_for_tenant()`
  (também `is_local=true`), que sobrepõem o bypass e **provam** o fail-closed.

Só é ativado quando os testes rodam (é o `TEST_RUNNER`); jamais afeta produção.
No-op fora do PostgreSQL (SQLite de dev), onde a RLS já é no-op.

**Onde moram os testes.** Não dentro dos apps: em `testes/backend/<app>/`, na raiz
do repositório (pacotes `testes.backend.<app>`). Por isso o runner também resolve
os rótulos — sem rótulo, descobre `testes/backend` inteiro; um rótulo que começa
por um app (`moduloorcamento`, `nucleo.test_quotas`) vira `testes.backend.<...>`.
Sem essa tradução, `manage.py test` a partir de `backend/` rodaria **0 testes e
diria OK**. A IAM tem o espelho disto em `iam_project/runner_testes.py`.
"""
import sys
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.backends.signals import connection_created
from django.test.runner import DiscoverRunner

SUITE = "backend"


def _rotulos_em_testes(rotulos):
    """Traduz os rótulos para a árvore `testes/backend/` (ver docstring do módulo).

    `testes/` é procurada ao lado do `BASE_DIR` (clone do repositório) ou dentro
    dele (cópia descartável num contêiner, com `testes/` copiada junto). A raiz
    onde ela está entra no `sys.path` para o rótulo pontuado importar.
    """
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
    apps = {p.name for p in pasta.iterdir() if (p / "__init__.py").is_file()}
    return [f"testes.{SUITE}.{r}" if r.split(".")[0] in apps else r for r in rotulos]


def _arm_session_bypass(sender, connection, **kwargs):
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        # is_local=false → vale pela sessão inteira até um is_local sobrepor.
        cursor.execute("SELECT set_config('app.rls_bypass', 'on', false)")


class RLSAwareTestRunner(DiscoverRunner):
    """`DiscoverRunner` que arma o bypass de sessão da RLS durante os testes."""

    def build_suite(self, test_labels=None, **kwargs):
        return super().build_suite(_rotulos_em_testes(test_labels), **kwargs)

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        connection_created.connect(_arm_session_bypass)

    def teardown_test_environment(self, **kwargs):
        connection_created.disconnect(_arm_session_bypass)
        super().teardown_test_environment(**kwargs)
