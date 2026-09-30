"""O plano do tenant nos roteiros — ler, trocar e devolver.

Não há endpoint para isto (o provisionamento por plano é o D24): o plano muda
no shell da IAM, por `save()`, como a tela e o admin fazem — é o sinal que
publica a ficha na hora. O backend guarda a ficha em cache por 30 s por
processo, então quem troca o plano espera o efeito chegar (ver `ESPERA_S`).
"""
import os
import subprocess

IAM_CONTAINER = os.getenv("SGI_IAM_CONTAINER", "sgi-iam")
#: Um pouco acima do cache de 30 s da ficha no backend.
ESPERA_S = 40


def _shell(codigo: str) -> str:
    return subprocess.run(
        ["docker", "exec", IAM_CONTAINER, "python", "manage.py", "shell", "-c", codigo],
        check=True, capture_output=True, text=True,
    ).stdout


def plano_do_tenant(slug: str = "demo") -> str:
    """O plano gravado ('' quando não há). O `shell -c` imprime um banner antes
    da saída do código — daí o marcador."""
    saida = _shell(
        "from identity.models import Tenant; "
        f"print('PLANO=' + (Tenant.objects.get(slug={slug!r}).plano or ''))"
    )
    return next(
        (l[len("PLANO="):].strip() for l in saida.splitlines() if l.startswith("PLANO=")),
        "",
    )


def definir_plano(plano: str | None, slug: str = "demo") -> None:
    _shell(
        "from identity.models import Tenant; "
        f"t = Tenant.objects.get(slug={slug!r}); t.plano = {plano!r}; t.save()"
    )
