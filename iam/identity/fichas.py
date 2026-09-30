"""As fichas — o que saiu do token na fase 4 e que o backend ainda precisa.

§10.6: "os dados de plano (`plano`, `rate_hora`, `quotas`) saem para uma leitura
do tenant com cache, porque são da empresa e não da pessoa", e o `email` sai por
minimização. A IAM publica as duas fichas no Redis da autorização
(`funcoesautorizacao.chaves.ficha_da_empresa` / `ficha_da_pessoa`) no mesmo
ciclo que leva as relações ao PDP — ao salvar empresa, assinatura ou pessoa, e
a cada volta periódica do `iam-pdp` —, e o backend as lê com cache curto.

Sem expiração: a ficha vale até a próxima publicação, e a volta periódica
reescreve todas. A empresa excluída tem as fichas apagadas junto das relações.
"""
from __future__ import annotations

import json
import logging

from funcoesautorizacao import chaves

logger = logging.getLogger(__name__)


def da_empresa(tenant) -> dict:
    from .tokens import dados_do_plano

    return {"slug": tenant.slug, "nome": tenant.nome, **dados_do_plano(tenant)}


def da_pessoa(email, janela_confirmacao_min) -> dict:
    """O e-mail, que o espelho do backend precisa, e a janela de confirmação do
    ato grave (fase 6), que o backend aplica no step-up da classe C. Nada mais:
    a ficha não é um segundo token."""
    return {"email": email, "janela_confirmacao_min": janela_confirmacao_min}


def publicar(tenant_id, redis_cliente) -> int:
    """Publica a ficha da empresa e a de cada pessoa ativa dela. Devolve quantas."""
    from .models import Tenant, Usuario

    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        return 0
    pipe = redis_cliente.pipeline()
    pipe.set(chaves.ficha_da_empresa(str(tenant.id)), json.dumps(da_empresa(tenant)))
    n = 1
    pessoas = Usuario.objects.filter(tenant=tenant, is_active=True).values_list(
        "id", "email", "janela_confirmacao_min",
    )
    for uid, email, janela in pessoas:
        pipe.set(chaves.ficha_da_pessoa(str(uid)), json.dumps(da_pessoa(email, janela)))
        n += 1
    pipe.execute()
    return n


def apagar_empresa(tenant_id, redis_cliente) -> None:
    redis_cliente.delete(chaves.ficha_da_empresa(str(tenant_id)))


def limpar_orfas(redis_cliente) -> int:
    """Apaga as fichas de empresa e de pessoa que não existem mais (ou se
    desativaram) — a volta periódica chama, depois de publicar as vivas."""
    from .models import Tenant, Usuario

    empresas = {str(t) for t in Tenant.objects.values_list("id", flat=True)}
    pessoas = {str(u) for u in Usuario.objects.filter(is_active=True).values_list("id", flat=True)}
    orfas = []
    for chave in redis_cliente.scan_iter(match=chaves.ficha_da_empresa("*")):
        if chave.rsplit(":", 1)[1] not in empresas:
            orfas.append(chave)
    for chave in redis_cliente.scan_iter(match=chaves.ficha_da_pessoa("*")):
        if chave.rsplit(":", 1)[1] not in pessoas:
            orfas.append(chave)
    for chave in orfas:
        redis_cliente.delete(chave)
    return len(orfas)
