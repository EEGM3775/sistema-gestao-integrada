"""D24 — trava de **seats**: o único enforcement de quota que vive na IAM.

Os demais objetos travados (obra, cliente, empreendimento, fornecedor) são
contados no backend, que é onde eles existem — ver `backend/nucleo/quotas.py`.
`seats` fica aqui pelo mesmo motivo que o teto do D23 é calculado aqui: quem
cria usuário é a IAM, e o `Usuario` do backend é espelho JIT (só existe quem já
logou). Contar do outro lado daria um número menor que o real durante toda a
implantação de um cliente, e a trava só apertaria depois que todo mundo tivesse
entrado pelo menos uma vez — exatamente quando ela já não serve para nada.

**Seat = usuário ATIVO.** Desativado não consome (é o padrão de mercado: Slack,
Google Workspace). Isso dá ao admin uma saída sem passar pelo checkout quando
alguém sai da empresa, que é o caso comum de "preciso de mais um usuário".

O status devolvido é **402**, não 403: não é falta de permissão (o admin *pode*
criar usuário), é falta de plano. A distinção importa para a UI, que precisa
oferecer upgrade em vez de mandar falar com o administrador — ele já é o admin.
"""
from __future__ import annotations

from rest_framework.exceptions import APIException

# Toda decisão vem de `payment/`: os VALORES de `planos.py` (QUOTA_SEATS = qual
# chave), as REGRAS de `regras.py` (como o limite se resolve). Este arquivo só
# faz o encanamento que `payment/` não pode fazer: contar usuário no banco DA IAM
# e levantar a exceção do DRF. Não há decisão comercial aqui.
from payment.planos import QUOTA_SEATS
from payment.regras import plano_valido, quota_efetiva


class QuotaExcedida(APIException):
    """402 com o suficiente para a UI montar o CTA de upgrade sozinha.

    O corpo é estruturado (não só `detail`) porque a tela precisa dizer *qual*
    limite bateu e quanto já se usou. Um 402 com texto solto obrigaria o frontend
    a interpretar string — que quebra na primeira vez que alguém reescrever a
    mensagem.
    """

    status_code = 402
    default_code = "quota_excedida"

    def __init__(self, *, quota: str, limite: int, uso: int, plano: str, detail: str):
        super().__init__("quota excedida")
        # Depois do `super()`, não dentro dele: o `APIException` converteria cada
        # valor em `ErrorDetail` (subclasse de `str`) e `limite: 1` sairia como
        # `"1"` no JSON. Mesma correção do gêmeo em `backend/nucleo/quotas.py` —
        # os dois serviços têm de devolver **um** contrato ao frontend.
        self.detail = {
            "detail": detail,
            "code": self.default_code,
            "quota": quota,
            "limite": limite,
            "uso": uso,
            "plano": plano,
        }


def seats_em_uso(tenant_id) -> int:
    """Usuários ativos do tenant. Import tardio: este módulo é importado pelas
    views, e `models` importa de volta a cadeia de identidade."""
    from .models import Usuario

    return Usuario.objects.filter(tenant_id=tenant_id, is_active=True).count()


def checar_seats(tenant) -> None:
    """Levanta `QuotaExcedida` se o tenant já ocupou todos os seats contratados.

    Chamada ANTES de criar o usuário. Sem tenant (provisionamento pelo dono da
    plataforma) não há plano a aplicar e a função é no-op.
    """
    if tenant is None:
        return

    limite = quota_efetiva(QUOTA_SEATS, tenant.plano, tenant.limites_contratados())
    if limite is None:
        return  # ilimitado por contrato ("Sob Medida")

    uso = seats_em_uso(tenant.id)
    if uso < limite:
        return

    raise QuotaExcedida(
        quota=QUOTA_SEATS,
        limite=limite,
        uso=uso,
        plano=plano_valido(tenant.plano),
        detail=(
            f"O plano contratado inclui {limite} usuário(s) e todos já estão em "
            "uso. Para liberar um seat, desative um usuário que não acessa mais "
            "o sistema; para aumentar o limite, faça upgrade do plano."
        ),
    )
