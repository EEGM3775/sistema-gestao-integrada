"""As chaves de Redis da autorização — um formato só, para quem escreve e quem lê.

A IAM escreve (ao gravar relação: ZedToken e versão do tenant), o invalidador
escreve (a cada evento do Watch: versões), e o backend lê (cache de decisão).
Se cada um montasse a própria string, um erro de digitação desligaria a
invalidação em silêncio — o cache continuaria respondendo o que foi revogado.

**O tenant está em toda chave de decisão**, e a função que monta a chave recusa
tenant vazio (§10.8): uma decisão cacheada sem tenant seria lida por outra
empresa com o mesmo id de pessoa.
"""
from __future__ import annotations

PREFIXO = "authz"

VERSAO_GLOBAL = f"{PREFIXO}:v:g"
CURSOR_DO_WATCH = f"{PREFIXO}:watch:cursor"
WATCH_VIVO = f"{PREFIXO}:watch:vivo"
TENANTS_PENDENTES = f"{PREFIXO}:pendentes"


def versao_do_tenant(tenant_id: str) -> str:
    return f"{PREFIXO}:v:t:{tenant_id}"


def versao_do_usuario(tenant_id: str, usuario_id: str) -> str:
    return f"{PREFIXO}:v:u:{tenant_id}:{usuario_id}"


def zedtoken_do_tenant(tenant_id: str) -> str:
    """O ZedToken da última mudança de relação do tenant — a régua da classe B."""
    return f"{PREFIXO}:zed:{tenant_id}"


def mudanca_do_tenant(tenant_id: str) -> str:
    """Quando a relação do tenant mudou pela última vez (epoch, segundos).

    Serve à sombra para separar a divergência **esperada** — o token foi emitido
    antes da mudança e ainda diz o que era verdade — da divergência real.
    """
    return f"{PREFIXO}:mudanca:{tenant_id}"


def decisao(tenant_id: str, usuario_id: str, versoes: tuple, pergunta: str) -> str:
    if not tenant_id:
        raise ValueError("Chave de decisão sem tenant é recusada (§10.8).")
    if not usuario_id:
        raise ValueError("Chave de decisão sem pessoa é recusada.")
    v = ".".join(str(x or 0) for x in versoes)
    return f"{PREFIXO}:d:{tenant_id}:{usuario_id}:{v}:{pergunta}"


def volume_do_dia(dia: str) -> str:
    """Hash ``tenant|pessoa → decisões`` do dia (``AAAAMMDD``) — a medida da §10.9."""
    return f"{PREFIXO}:vol:{dia}"


def comparacoes_do_dia(dia: str) -> str:
    """Quantas decisões a sombra comparou no dia — prova de que ela estava ligada."""
    return f"{PREFIXO}:cmp:{dia}"


def descartes_do_dia(dia: str) -> str:
    """Comparações que a sombra deixou de fazer por fila cheia."""
    return f"{PREFIXO}:desc:{dia}"


def divergencia_vista(tenant_id: str, usuario_id: str, pergunta: str, tipo: str) -> str:
    """Trava de repetição: a mesma divergência entra uma vez por janela."""
    return f"{PREFIXO}:div:{tenant_id}:{usuario_id}:{pergunta}:{tipo}"


def marcar_mudanca(cliente_redis, tenant_id: str, zedtoken: str, agora: float) -> None:
    """O que todo escritor de relação faz depois de gravar: guarda o ZedToken,
    sobe a versão do tenant (o cache inteiro dele deixa de ser lido) e anota a
    hora. Uma ida ao Redis, em pipeline."""
    pipe = cliente_redis.pipeline()
    if zedtoken:
        pipe.set(zedtoken_do_tenant(tenant_id), zedtoken)
    pipe.incr(versao_do_tenant(tenant_id))
    pipe.set(mudanca_do_tenant(tenant_id), int(agora))
    pipe.execute()
