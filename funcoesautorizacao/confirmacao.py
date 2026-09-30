"""O step-up do ato grave — a autenticação tem de ser recente (fase 6, §10.5).

Atestar pagamento, mudar papel ou alçada e exportar dado pessoal — a classe C da
§10.8 — exigem que a pessoa tenha provado quem é **há pouco**: o `auth_time` do
token dentro da janela que ela escolheu na tela de perfil (padrão 15 minutos,
de 1 a 120; `payment/planos.py` §5.5o). Fora dela o serviço responde o desafio
da RFC 9470 e a tela pede o código (ou a senha, para quem não tem segundo
fator); a IAM faz o `auth_time` andar (`/auth/confirmar/`) e o pedido é refeito.

Uma sessão sequestrada navega, mas não paga. A regra mora aqui para o backend e
a IAM a aplicarem igual — a janela, o formato do desafio e o código da recusa.
"""
from __future__ import annotations

import time

#: O `codigo` do corpo da recusa, que a tela reconhece para abrir a confirmação.
CODIGO = "confirmacao_necessaria"


def janela_em_segundos(janela_min, padrao_min: int, minimo_min: int, maximo_min: int) -> int:
    """A janela da pessoa, dentro da faixa do dono — o servidor aplica o teto,
    mesmo que a ficha traga outro número."""
    try:
        minutos = int(janela_min)
    except (TypeError, ValueError):
        minutos = padrao_min
    return 60 * max(minimo_min, min(maximo_min, minutos))


def recente(auth_time, janela_s: int, agora: float | None = None) -> bool:
    """A autenticação desta sessão cabe na janela? Sem `auth_time`, não."""
    try:
        instante = int(auth_time)
    except (TypeError, ValueError):
        return False
    return (agora if agora is not None else time.time()) - instante <= janela_s


def desafio(janela_s: int) -> str:
    """O `WWW-Authenticate` da RFC 9470 §3."""
    return (
        'Bearer error="insufficient_user_authentication", '
        'error_description="Confirme sua identidade para este ato.", '
        f"max_age={int(janela_s)}"
    )


def corpo(janela_s: int) -> dict:
    return {
        "detail": "Este ato pede que você confirme sua identidade.",
        "codigo": CODIGO,
        "max_age": int(janela_s),
    }
