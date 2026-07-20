"""Camada 1 — limite de ENTRADA, eixo TENANT (D23).

Desenho e justificativas: docs/arquitetura/rate-limiting.md §2.

O S8 construiu os eixos por **IP** e por **usuário**. Faltava o eixo que define um
SaaS: o **tenant**. Sem ele, uma empresa com 50 funcionários consome legitimamente
50× o que uma de 3 consome e **nada impede que degrade a experiência da outra** —
o problema conhecido como *noisy neighbor*. A prática de mercado (AWS, API Gateway)
é limitar por tenant e fazer o teto de usuário ser uma **fração** do teto da
empresa, não um valor independente; a derivação vive em `config/settings.py`,
que é onde as taxas moram.

Duas decisões que valem registro para quem chegar aqui pelo código:

- **A chave é o tenant do espelho local** (`user.tenant_id`), sincronizado do claim
  `tenant_id` do JWT pela `IamJWTAuthentication` — o mesmo idioma que `tenancy.py`
  usa para armar a RLS. Não se lê o token de novo aqui: um segundo caminho para o
  mesmo dado é um segundo caminho para divergir dele.
- **Sem tenant → este eixo não conta.** Requisição anônima e dono da plataforma
  (que não pertence a nenhuma empresa) escapam daqui de propósito; para eles valem
  os eixos `anon` e `user`, que continuam ligados. Devolver `None` é a forma que o
  DRF tem de dizer "este eixo não se aplica", e não "pode tudo".

**Fail-open, mas ruidoso** (`FailOpenMixin`), pelo mesmo trade-off da camada 2: um
teto que depende da cache não pode transformar queda do Redis em API fora do ar.
Aqui isso não é teórico — `django_redis` com `IGNORE_EXCEPTIONS=True` devolve
`None` (não o default) quando o Redis cai, e o `SimpleRateThrottle` do DRF faz
`self.history.insert(0, ...)` logo depois: `AttributeError` → **500 em toda
requisição**. Por isso o mixin envolve os três eixos, e não só o novo.
"""
from __future__ import annotations

import logging

from rest_framework.exceptions import Throttled
from rest_framework.throttling import (
    AnonRateThrottle,
    ScopedRateThrottle,
    SimpleRateThrottle,
    UserRateThrottle,
)

logger = logging.getLogger(__name__)


class LimiteDoTenantExcedido(Throttled):
    """429 do eixo **empresa**, com texto que diz qual eixo foi atingido.

    A mensagem padrão do DRF é a mesma para todos os eixos, e a diferença importa
    para quem recebe: "sua conta foi bloqueada" e "a sua empresa atingiu o teto
    agora" levam o usuário a ações opostas (ligar para o suporte × esperar um
    minuto). Mesma lição registrada no D21/S8 sobre o texto do 429.
    """

    default_code = "limite_tenant"

    def __init__(self, wait):
        segundos = max(1, int(round(wait or 1)))
        super().__init__(
            wait=segundos,
            detail=(
                "A sua empresa atingiu o limite de requisições por hora deste "
                "sistema. Não é bloqueio da sua conta nem cobrança: tente de novo "
                f"em ~{segundos}s. Se acontecer com frequência, fale com o suporte."
            ),
        )


class FailOpenMixin:
    """Falha da cache **libera** a requisição, e registra erro.

    Travar seria pior que o problema: o teto existe contra abuso, e trocá-lo por
    indisponibilidade total entrega ao Redis o poder de derrubar o produto. Mas o
    log em nível de erro é obrigatório — um protetor fail-open que perdeu a
    dependência fica indistinguível de um protetor funcionando, e foi exatamente
    essa a origem do D21.
    """

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Throttled:
            raise  # teto atingido de verdade — não é falha de infraestrutura
        except Exception:
            logger.error(
                "throttle_indisponivel",
                extra={"escopo": getattr(self, "scope", "?")},
                exc_info=True,
            )
            return True


class TenantRateThrottle(FailOpenMixin, SimpleRateThrottle):
    """Teto por **empresa**: o balde é compartilhado por todos os usuários dela.

    O teto **não é constante** — vem do plano contratado, pela claim `rate_hora`
    que a IAM emite (regra em `payment/regras.py`). Um número fixo não tem valor que
    funcione: alto o bastante para a empresa de 1000 funcionários não protege
    contra a de 50 abusando; baixo o bastante para proteger inutiliza a de 1000.
    Derivado dos seats, o teto acompanha o tamanho **contratado** — e sobe sozinho
    quando o cliente compra o add-on de usuário extra.

    Sem a claim (token de serviço, token legado) vale o default do settings.
    """

    scope = "tenant"

    def get_cache_key(self, request, view):
        usuario = getattr(request, "user", None)
        if usuario is None or not usuario.is_authenticated:
            return None  # eixo `anon` cuida disto
        tenant_id = getattr(usuario, "tenant_id", None)
        if not tenant_id:
            return None  # dono da plataforma: sem empresa, sem este eixo
        return self.cache_format % {"scope": self.scope, "ident": tenant_id}

    def allow_request(self, request, view):
        # `self.rate is None` = teto desligado (é como a suíte roda, ver D19).
        if self.rate is not None:
            teto = getattr(getattr(request, "user", None), "iam_rate_hora", None)
            if isinstance(teto, int) and teto > 0:
                # Substitui o teto do settings pelo do plano. Feito por requisição
                # porque tenants diferentes têm planos diferentes — o `num_requests`
                # do DRF é resolvido uma vez no __init__, na configuração global.
                self.num_requests = teto
                self.duration = 3600
        permitido = super().allow_request(request, view)
        self._publicar_headers(request)
        return permitido

    def _publicar_headers(self, request) -> None:
        """Deixa o estado do balde na request para o middleware virar
        `X-RateLimit-*`. Só o eixo do tenant publica: é o teto que o cliente
        compra e o único que ele consegue administrar (comprando seats)."""
        if self.rate is None or not hasattr(self, "history"):
            return
        historico = self.history or []
        # O `request` do DRF é um WRAPPER: `setattr` nele não alcança o
        # `HttpRequest` do Django, que é o que o middleware recebe na volta.
        # Sem este `_request` o header some em silêncio.
        alvo = getattr(request, "_request", request)
        alvo.sgi_rate_info = {
            "limite": self.num_requests,
            "restante": self.num_requests - len(historico),
            # Epoch em que a requisição mais antiga sai da janela — é quando o
            # cliente volta a ter folga. Formato do GitHub (`x-ratelimit-reset`).
            "reset": int((historico[-1] if historico else self.now) + self.duration),
        }

    def throttle_failure(self):
        raise LimiteDoTenantExcedido(wait=self.wait())


class UsuarioRateThrottle(FailOpenMixin, UserRateThrottle):
    """`UserRateThrottle` do DRF + fail-open. Escopo `user` (taxa derivada do tenant)."""


class AnonimoRateThrottle(FailOpenMixin, AnonRateThrottle):
    """`AnonRateThrottle` do DRF + fail-open. Escopo `anon`.

    Limite conhecido (docs/arquitetura/rate-limiting.md §2.3): no DRF a permissão é
    resolvida ANTES do throttle, então requisição sem token a endpoint protegido
    leva 401 e **não é contada**. Este eixo protege as rotas `AllowAny` (webhooks,
    recuperação de senha); a inundação anônima de `/api/*` é barrada no nginx.
    """


class EscopoRateThrottle(FailOpenMixin, ScopedRateThrottle):
    """`ScopedRateThrottle` do DRF + fail-open. Escopos nomeados (`relatorio`,
    `integracao_externa`).

    Precisa do mixin tanto quanto os outros — mais, até: os escopos nomeados
    guardam justamente os verbos caros (dashboard consolidado, emissão de NF,
    geração de cobrança). Deixá-lo de fora faria a queda do Redis derrubar
    primeiro o que mais importa.
    """
