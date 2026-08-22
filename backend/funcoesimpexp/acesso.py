# backend/funcoesimpexp/acesso.py
"""IE.0 — a regra do §3 da planta, num lugar só: **acesso total ou nada**.

Só opera quem tem o conjunto INTEIRO de `permissoes_exigidas` do recurso. Meia
permissão bloqueia; permissão nenhuma idem. Não há operação parcial nem arquivo
com coluna capada.

Por que de conjunto, e não campo a campo em tempo de request: nas telas, o
mascaramento 9.C protege o campo e a página segue útil (CPF vira `•••123`). Num
arquivo, não — a planilha sai parecendo completa, viaja para fora do sistema e é
somada por quem não estava na tela e não tem como saber que a coluna foi capada.
Bloquear na entrada dá a mesma garantia, é previsível e não custa nada no
caminho quente, **desde que a declaração inclua a permissão de máscara de toda
coluna sensível** — obrigação registrada no contrato (`registro.Recurso`).

O backend não conhece o catálogo da IAM: as permissões chegam como lista plana na
claim `permissions` do JWT. Por isso o conjunto é declarado pelo módulo dono, que
conhece as próprias.
"""
from __future__ import annotations

from rest_framework.exceptions import PermissionDenied

from .registro import Recurso


def permissoes_faltantes(user, recurso: Recurso, exigidas=None) -> tuple[str, ...]:
    """O que falta para esta pessoa operar este recurso. Vazio = pode.

    `exigidas` sobrepõe o conjunto do recurso — é como a entrega de arquivo
    (IE.3b) usa o seu, que é de leitura e não o do §3.
    """
    if _privilegiado(user):
        return ()
    concedidas = set(getattr(user, "iam_permissions", None) or [])
    alvo = recurso.permissoes_exigidas if exigidas is None else exigidas
    return tuple(p for p in alvo if p not in concedidas)


def pode_operar(user, recurso: Recurso) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return not permissoes_faltantes(user, recurso)


def exigir_acesso_total(user, recurso: Recurso, *, escrita: bool = False) -> None:
    """403 nomeando o que falta — mensagem de erro tem de ser acionável.

    "Você não tem permissão" manda a pessoa abrir chamado; dizer *qual*
    permissão falta manda ela ao admin do tenant com o pedido pronto.

    `escrita=True` nas operações que **gravam** no destino (importar, aplicar,
    desfazer): elas exigem, além do conjunto, o entitlement do módulo — ver
    `exigir_entitlement_de_escrita`.
    """
    if not user or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Autenticação necessária.")
    if escrita:
        exigir_entitlement_de_escrita(user, recurso)
    faltam = permissoes_faltantes(user, recurso)
    if not faltam:
        return
    raise PermissionDenied(
        f"Importar e exportar '{recurso.rotulo}' exige acesso total ao recurso, e faltam: "
        f"{', '.join(faltam)}. Arquivo sai inteiro ou não sai — não há exportação parcial."
    )


def exigir_entitlement_de_escrita(user, recurso: Recurso) -> None:
    """O módulo tem de estar contratado para ENTRAR dado por aqui.

    **O buraco que isto fecha** (análise de 07/08/2026). O gate deste app é o
    conjunto de permissões, e ele já carrega o entitlement por transitividade:
    `permissoes_efetivas()` na IAM filtra as permissões pelos módulos efetivos,
    então quem não assina o Orçamento não tem `orcamento.*` no token e não passa.
    Bom desenho — e o `_privilegiado` passava por cima dele, porque devolve
    conjunto vazio **antes** de olhar permissão nenhuma. Resultado concreto: o
    tenant que cancelava o Orçamento levava 403 em `/api/orcamento/**` e seguia
    importando e exportando pelo `/api/impexp/orcamento.planilha/`.

    **Só a escrita é fechada, e a assimetria é deliberada.** Exportar continua
    liberado para o admin mesmo sem o módulo, porque é **portabilidade**: é o que
    Salesforce e HubSpot fazem (retêm o dado e mantêm a saída aberta por uma
    janela depois do cancelamento, em vez de apagar ou prender), e prender o dado
    do cliente no dia em que ele cancela gera processo, não receita. A saída
    passa a ficar **auditada** (R12), que é o que faltava para ela ser uma
    decisão em vez de um acidente. Importar não tem esse argumento: é entrada de
    dado em produto não pago.

    A janela em dias já está declarada em `payment/planos.py`
    (`impexp_exportar_apos_cancelar_dias`) e está **inerte**: aplicá-la exige a
    IAM emitir a data de cancelamento na claim — hoje `modules` só diz o estado
    de agora, e um módulo cancelado é indistinguível de um nunca contratado.

    Para quem NÃO é privilegiado esta checagem é redundante (o conjunto de
    permissões já a garante) e por isso não roda: seria um segundo lugar para o
    mesmo "não" divergir do primeiro.
    """
    if not _privilegiado(user):
        return
    exigido = recurso.entitlement
    if not exigido:
        return
    if exigido in (getattr(user, "iam_modules", None) or ()):
        return
    raise PermissionDenied(
        f"Importar para '{recurso.rotulo}' exige o módulo '{exigido}' contratado. "
        "A exportação dos dados que já existem continua disponível."
    )


def exigir_entrega(user, recurso: Recurso) -> None:
    """IE.3b — gate do **download** de um arquivo do acervo.

    **Não é o `exigir_acesso_total`, e a diferença é de propósito.** O §3 fala de
    exportação tabular: "arquivo sai inteiro ou não sai" existe porque uma
    planilha com coluna capada parece completa e é somada fora do sistema. Um
    binário do acervo não tem coluna para capar — o que se pede é *um objeto*, e o
    gate certo é o de leitura dele. O recurso declara qual em
    `permissoes_entrega`; quem não declara cai no conjunto do §3, que é o
    conservador.

    **O entitlement É cobrado aqui, ao contrário da exportação tabular** — e a
    assimetria com o [D66](../../docs/historico-correcoes.md) é deliberada. Lá o
    argumento é portabilidade: a planilha do dado que o cliente digitou continua
    saindo depois do cancelamento, porque prender o dado gera processo, não
    receita. Aqui o binário **é o produto**: o acervo da Prancheta não é um
    relatório sobre o módulo, é o módulo (planta §2 — "sem metade de fundação, ao
    contrário do Maps"). Servir a prancha convertida a quem não assina é entregar
    a mercadoria, não devolver o dado.

    **E é cobrado de todo mundo, não só do privilegiado** — diferente de
    `exigir_entitlement_de_escrita`, que só roda para o admin porque para os
    demais a IAM já filtra as permissões pelos módulos efetivos. Aqui a
    redundância é o ponto: esta função substitui um `RequireModule` que valia para
    todos, e o que ela protege é o binário. Deixar a garantia por conta de um
    filtro que acontece noutro serviço é o que a planta chama de fail-open
    silencioso — se um dia a claim vier larga, o acervo inteiro sai pela URL.

    Recurso de **fundação** (`entitlement = None`, como o `maps.local`) não é
    afetado: ali não há módulo a cobrar, por desenho.
    """
    if not user or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Autenticação necessária.")

    exigido = recurso.entitlement
    if exigido and exigido not in (getattr(user, "iam_modules", None) or ()):
        raise PermissionDenied(
            f"Baixar arquivo de '{recurso.rotulo}' exige o módulo '{exigido}' "
            "contratado. A exportação dos dados que já existem continua disponível."
        )

    faltam = permissoes_faltantes(user, recurso, recurso.permissoes_da_entrega)
    if not faltam:
        return
    raise PermissionDenied(
        f"Baixar arquivo de '{recurso.rotulo}' exige: {', '.join(faltam)}."
    )


def recursos_permitidos(user, recursos) -> tuple[Recurso, ...]:
    """Para o frontend sumir com o botão antes do clique (planta §10)."""
    return tuple(r for r in recursos if pode_operar(user, r))


def _privilegiado(user) -> bool:
    """Mesmo bypass que já vale em `RequirePermission` — um único modelo mental."""
    return bool(
        getattr(user, "is_tenant_admin", False)
        or getattr(user, "is_platform_admin", False)
        or getattr(user, "is_superuser", False)
    )
