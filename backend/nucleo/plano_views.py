"""`GET /api/plano/` — o que o tenant contratou, quanto já usou, e o que vem depois.

Existe para a UI conseguir mostrar o medidor **antes** da parede. Descobrir o
limite ao levar um 402 no meio de um cadastro é a pior hora possível: a pessoa já
digitou tudo, e o produto parece quebrado em vez de parecer um plano pequeno.
Com o medidor visível, o 402 vira confirmação do que já se sabia — e o upgrade
vira decisão tomada com antecedência, não reação a um erro.

É também o único ponto do backend que importa `payment/` (o pacote de valores
compartilhado com a IAM). É o que o `payment/README.md` já antecipava: a tabela
de preços tem de sair de um lugar só, senão a vitrine e a cobrança divergem —
e quem descobre a divergência é o cliente, na fatura.
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from payment.planos import ORDEM_PLANOS, PLANO_PADRAO, PLANOS
from payment.regras import proximo_plano

from .quotas import RECURSOS_CONTADOS, ROTULOS, uso_atual
from .tenancy import TenantScopedAPIViewMixin

# Quotas travadas que NÃO são contadas aqui: `seats` é enforcement da IAM
# (`iam/identity/quotas.py`), porque o `Usuario` do backend é espelho JIT — só
# existe quem já logou, então uma contagem local sairia menor que a real durante
# toda a implantação de um cliente. O limite aparece na resposta (a UI precisa
# dele para o comparativo de planos) com `uso: null` e a fonte declarada, em vez
# de um número plausível e errado.
QUOTAS_EXTERNAS = {"seats": "iam"}


def _plano_resumo(slug: str) -> dict:
    plano = PLANOS[slug]
    return {
        "slug": slug,
        "nome": plano["nome"],
        "preco_mensal": plano["preco_mensal"],
        "publico": plano.get("publico"),
    }


def _proximo_plano_resumo(slug: str) -> dict | None:
    """Resumo (nome/preço) do plano acima, para o CTA de upgrade. A REGRA de qual
    é o próximo vem de `payment.regras.proximo_plano` — a mesma que a IAM usa, sem
    reimplementar. Aqui fica só a formatação do resumo, que é apresentação."""
    proximo = proximo_plano(slug)
    return _plano_resumo(proximo) if proximo else None


class PlanoView(TenantScopedAPIViewMixin, APIView):
    """Plano vigente + medidores + próximo degrau.

    Aberto a qualquer usuário autenticado do tenant, não só ao admin: quem
    esbarra na quota é quem está cadastrando, e a mensagem só ajuda se a pessoa
    conseguir ver o medidor que a explica. Não há PII aqui — são contagens da
    própria empresa e a tabela de preços pública.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        tenant_id = getattr(user, "tenant_id", None)
        slug = getattr(user, "iam_plano", None) or PLANO_PADRAO
        if slug not in PLANOS:
            slug = PLANO_PADRAO
        quotas_claim = getattr(user, "iam_quotas", None) or {}

        medidores = []
        for recurso, limite in quotas_claim.items():
            externa = QUOTAS_EXTERNAS.get(recurso)
            contavel = recurso in RECURSOS_CONTADOS and tenant_id and not externa
            uso = uso_atual(recurso, tenant_id) if contavel else None
            ilimitado = limite is None
            medidores.append(
                {
                    "recurso": recurso,
                    "rotulo": ROTULOS.get(recurso, recurso),
                    "limite": limite,
                    "uso": uso,
                    "ilimitado": ilimitado,
                    # `restante` já vem calculado para a barra não precisar tratar
                    # `None` em dois eixos. Nunca negativo: quem caiu de plano com
                    # dados acima do teto fica em 0, não em "-3 obras".
                    "restante": None if (ilimitado or uso is None) else max(0, limite - uso),
                    "excedido": bool(uso is not None and not ilimitado and uso >= limite),
                    "fonte": externa or "backend",
                }
            )
        medidores.sort(key=lambda m: m["recurso"])

        return Response(
            {
                "plano": _plano_resumo(slug),
                "quotas": medidores,
                "proximo_plano": _proximo_plano_resumo(slug),
                # A vitrine inteira, para a tela de upgrade não repetir preço em
                # código de frontend — que é como ela ficaria desatualizada.
                "catalogo": [
                    {**_plano_resumo(s), "quotas": {
                        k: v for k, v in PLANOS[s].items()
                        if k not in ("nome", "preco_mensal", "publico")
                    }}
                    for s in ORDEM_PLANOS
                ],
            }
        )
