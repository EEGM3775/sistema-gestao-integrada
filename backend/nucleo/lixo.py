# backend/nucleo/lixo.py
"""A política da lixeira — fundação de plataforma (D116).

Os modelos moram em `models.py` (como os da escada de atesto e os da frota); o
que **decide** mora aqui. A lápide em si está em `nucleo/tenancy.py`, junto da
tenancy, porque é lá que o gerente padrão de 16 modelos é montado.

> **Decisão do dono, 23/08/2026:** *"Coloca como «Obra excluída por «usuário» na
> data xx/xx/xx». Deixa o plano para poder ser usado como modelo em outra obra."*
> **13/09/2026:** *"O lixo é uma página à parte. Como é custo para o programa,
> terá uma paywall. O lixo é apagado depois de 15 dias. O lixo pode ser
> restaurado através da página de lixo."*

**Duas etapas, e é a segunda que o nome "lixo" descreve.** Excluir marca a
lápide: a linha some das listagens e nada mais acontece — nenhum `CASCADE`
dispara, nenhum `PROTECT` é consultado, o cronograma e o orçamento da obra
continuam de pé. Só no 15º dia vem a exclusão de verdade, e só aí o desenho de
cada módulo entra em cena. É isso que destrava o D116: a obra que **rodou** nunca
conseguiu sair por exclusão física, e agora ela não precisa — ela sai de vista
hoje e morre depois, quando já não há o que desfazer.

Cinco regras que nenhuma tela redecide:

1. **Quem exclui não precisa de permissão nova.** Quem já podia apagar continua
   podendo; o que mudou é que agora dá para voltar atrás. Trancar a exclusão
   atrás de um verbo novo tornaria a lixeira um downgrade de permissão disfarçado
   de melhoria.
2. **Ver, restaurar e purgar são do `gestor_lixo`.** Restaurar ressuscita dado
   que alguém decidiu tirar de circulação, e purgar destrói o que ainda estava no
   prazo: as duas são da classe de `plataforma.papel.gerir`, não da classe de
   "editar um cadastro".
3. **O prazo é congelado na exclusão**, nunca recalculado (ver
   `payment/planos.py` §5.5g). Downgrade de plano não encurta a janela de quem
   apagou antes dele.
4. **A purga que falha não mente.** Se o `PROTECT` de um módulo recusar o
   `DELETE`, o item **fica** na lixeira com o motivo escrito em
   `falha_na_purga` — em vez de sumir do relatório como se tivesse funcionado.
   Foi exatamente esse silêncio (um 500 mudo) que abriu o D116.
5. **O `nucleo` não sabe o que está apagando.** Antes do `DELETE` ele emite
   `antes_de_purgar`; desligar o que precisa sobreviver ao dono é do módulo dono.
   É o mesmo contrato do `aprovacao_concluida`, e pelo mesmo motivo: o `nucleo` é
   importado por todos e não pode importar nenhum de volta.

Onde a regra 5 se paga, hoje: o **plano modelo**. `Cronograma.obra` é `CASCADE`,
e o dono mandou o plano sobreviver à obra. O `modulopdca` conecta
`antes_de_purgar` e desliga da obra os cronogramas marcados `eh_modelo` antes de
o `DELETE` acontecer — sem que este arquivo saiba que cronograma existe.
"""
from __future__ import annotations

import logging
from datetime import timedelta

import django.dispatch
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError, RestrictedError
from django.utils import timezone

from payment.planos import LIXO_RETENCAO_PADRAO_DIAS, LIXO_TETO_PURGAS_POR_VOLTA

from .models import Lixo
from .tenancy import Excluivel, rls_bypass, tenant_context

logger = logging.getLogger(__name__)

#: Emitido **antes** do `DELETE` definitivo, dentro da mesma transação. `sender` é
#: a classe do alvo, para o módulo dono conectar sem filtro em Python.
#: Argumentos: `alvo` (a instância) e `item` (a linha do `Lixo`).
#:
#: Levantar exceção aqui **aborta a purga** — e é legítimo: é como um módulo diz
#: "este objeto não pode morrer ainda". O motivo vai para `falha_na_purga` e o
#: item continua na lixeira, visível.
antes_de_purgar = django.dispatch.Signal()


def _nome_de(usuario) -> str:
    if usuario is None:
        return ""
    nome = (getattr(usuario, "get_full_name", lambda: "")() or "").strip()
    return nome or getattr(usuario, "username", "") or ""


def retencao_dias(usuario) -> int:
    """Dias de lixeira do plano deste usuário, lidos da claim `quotas`.

    Fail-open no padrão da casa: sem claim (token de serviço, legado) vale
    `LIXO_RETENCAO_PADRAO_DIAS`. O contrário — recusar a exclusão porque não deu
    para saber o plano — transformaria uma feature comercial em impossibilidade
    de apagar, que é o trade-off já registrado em `nucleo/quotas.py`.
    """
    quotas = getattr(usuario, "iam_quotas", None)
    if isinstance(quotas, dict):
        dias = quotas.get("lixo_retencao_dias")
        if isinstance(dias, int) and dias > 0:
            return dias
    return LIXO_RETENCAO_PADRAO_DIAS


def item_de(objeto) -> Lixo | None:
    """A linha ativa da lixeira que corresponde a `objeto`, se houver."""
    tipo = ContentType.objects.get_for_model(objeto.__class__)
    return Lixo.objects.filter(
        alvo_tipo=tipo,
        alvo_id=objeto.pk,
        restaurado_em__isnull=True,
        purgado_em__isnull=True,
    ).first()


def alvo_de(item: Lixo):
    """A instância por trás da linha da lixeira, ou `None` se já não existe.

    Usa `_base_manager` **de propósito**: o gerente padrão do alvo filtra a
    lápide (é para isso que ele existe), e aqui queremos justamente o que está
    sob ela. É o mesmo gerente que o ORM usa para travessia de FK.
    """
    modelo = item.alvo_tipo.model_class()
    if modelo is None:
        return None
    return modelo._base_manager.filter(pk=item.alvo_id).first()


@transaction.atomic
def mover_para_lixo(objeto, *, usuario, motivo: str = "") -> Lixo:
    """Marca a lápide e indexa o objeto na lixeira. Não apaga nada.

    Chamado pelo `perform_destroy` do `TenantScopedViewSetMixin` — os módulos não
    chamam isto à mão, e é o que faz a lixeira valer para os 118 ViewSets sem que
    nenhum deles a importe.
    """
    if not isinstance(objeto, Excluivel):
        raise ValidationError("Este tipo de registro não vai para a lixeira.")
    if objeto.excluido_em is not None:
        raise ValidationError("Este registro já está na lixeira.")

    tenant_id = getattr(objeto, "tenant_id", None)
    if tenant_id is None:
        # Sem tenant não há a quem mostrar a lixeira, e a linha do `Lixo` é
        # `TenantScopedModel`. Falhar aqui é melhor que gravar um item órfão que
        # ninguém consegue listar nem restaurar.
        raise ValidationError("Registro sem tenant não pode ir para a lixeira.")

    agora = timezone.now()
    objeto.excluido_em = agora
    objeto.excluido_por = usuario if getattr(usuario, "pk", None) else None
    objeto.motivo_exclusao = motivo or ""
    objeto.save(update_fields=["excluido_em", "excluido_por", "motivo_exclusao"])

    item = Lixo.objects.create(
        tenant_id=tenant_id,
        alvo_tipo=ContentType.objects.get_for_model(objeto.__class__),
        alvo_id=objeto.pk,
        rotulo=str(objeto)[:255],
        excluido_em=agora,
        excluido_por=objeto.excluido_por,
        excluido_por_nome=_nome_de(usuario),
        motivo=motivo or "",
        purgar_em=agora + timedelta(days=retencao_dias(usuario)),
    )
    logger.info(
        "lixo_item_movido",
        extra={
            "lixo_id": item.lixo_id,
            "modelo": item.alvo_tipo.model,
            "alvo_id": item.alvo_id,
            "purgar_em": item.purgar_em.isoformat(),
        },
    )
    return item


@transaction.atomic
def restaurar(item: Lixo, *, usuario) -> object:
    """Tira a lápide. É o inverso exato de `mover_para_lixo`, e é só isso.

    Sem payload para desserializar, sem `INSERT` com id explícito, sem
    `setval()` na sequência: o registro nunca saiu do lugar. Toda a seção 3 da
    prancha original (*"Garantia de ID — sem reutilização"*) deixou de ter
    assunto no dia em que a lápide substituiu o snapshot.
    """
    item = Lixo.objects.select_for_update().get(pk=item.pk)
    if not item.ativo:
        raise ValidationError("Este item já saiu da lixeira.")

    alvo = alvo_de(item)
    if alvo is None:
        raise ValidationError(
            "O registro original não existe mais — não há o que restaurar."
        )

    alvo.excluido_em = None
    alvo.excluido_por = None
    alvo.motivo_exclusao = ""
    alvo.save(update_fields=["excluido_em", "excluido_por", "motivo_exclusao"])

    item.restaurado_em = timezone.now()
    item.restaurado_por = usuario if getattr(usuario, "pk", None) else None
    item.falha_na_purga = ""
    item.save(update_fields=["restaurado_em", "restaurado_por", "falha_na_purga"])

    logger.info(
        "lixo_item_restaurado",
        extra={"lixo_id": item.lixo_id, "modelo": item.alvo_tipo.model},
    )
    return alvo


def purgar(item: Lixo, *, usuario=None) -> Lixo:
    """Apaga de verdade. Irreversível — e é aqui que o `CASCADE` do módulo roda.

    `usuario=None` significa **a varredura automática**, não um ator anônimo: a
    tela lê `purgado_por` nulo com `purgado_em` preenchido e diz "purga
    automática". Inventar um usuário-robô para assinar isso poria um ator falso
    no log de auditoria.

    A transação é **por item** (e não em volta da varredura inteira): uma obra
    que recusa o `DELETE` não pode desfazer a purga das outras 199 da volta.
    """
    ja_saiu = False
    try:
        with transaction.atomic():
            item = Lixo.objects.select_for_update().get(pk=item.pk)
            if not item.ativo:
                ja_saiu = True
                raise ValidationError("Este item já saiu da lixeira.")

            alvo = alvo_de(item)
            if alvo is not None:
                # O módulo dono tem a última palavra sobre o que precisa
                # sobreviver ao objeto — hoje, o plano modelo do PDCA.
                antes_de_purgar.send(sender=alvo.__class__, alvo=alvo, item=item)
                alvo.delete()

            item.purgado_em = timezone.now()
            item.purgado_por = usuario if getattr(usuario, "pk", None) else None
            item.falha_na_purga = ""
            item.save(update_fields=["purgado_em", "purgado_por", "falha_na_purga"])
    except (ProtectedError, RestrictedError, ValidationError) as exc:
        if ja_saiu:
            # Purgar o que já foi purgado/restaurado é erro do chamador, não
            # recusa do banco — sobe como 409 em vez de virar nota na lixeira.
            raise
        # Regra 4: a purga que falha fica escrita. O item continua na lixeira,
        # visível, com o motivo — em vez de sumir do relatório como sucesso.
        motivo = str(exc)[:2000]
        Lixo.objects.filter(pk=item.pk).update(falha_na_purga=motivo)
        logger.warning(
            "lixo_purga_recusada",
            extra={"lixo_id": item.pk, "motivo": motivo},
        )
        item.refresh_from_db()
        return item

    logger.info(
        "lixo_item_purgado",
        extra={
            "lixo_id": item.lixo_id,
            "modelo": item.alvo_tipo.model,
            "automatica": usuario is None,
        },
    )
    return item


def purgar_vencidos(*, agora=None, teto: int | None = None) -> dict:
    """A varredura do 15º dia. Roda sem usuário e **sem consultar plano nenhum**.

    Lê `purgar_em`, que foi congelado na exclusão — ver `planos.py` §5.5g.

    **RLS:** a política é fail-closed, e uma task de Celery não tem tenant
    armado; sem `rls_bypass()` a varredura enxergaria zero linhas e falharia em
    silêncio para sempre (a classe de defeito do D21). Lista sob bypass, mas
    **apaga dentro do contexto do tenant de cada item** — o `DELETE` toca as
    tabelas do módulo, e elas têm política própria.
    """
    agora = agora or timezone.now()
    teto = teto or LIXO_TETO_PURGAS_POR_VOLTA

    with rls_bypass():
        vencidos = list(
            Lixo.objects.filter(
                purgar_em__lte=agora,
                restaurado_em__isnull=True,
                purgado_em__isnull=True,
            )
            .order_by("purgar_em")
            .values_list("pk", "tenant_id")[:teto]
        )

    purgados, recusados = 0, 0
    for pk, tenant_id in vencidos:
        with tenant_context(tenant_id):
            item = Lixo.objects.filter(pk=pk).first()
            if item is None or not item.ativo:
                continue
            resultado = purgar(item, usuario=None)
            if resultado.purgado_em is not None:
                purgados += 1
            else:
                recusados += 1

    logger.info(
        "lixo_varredura",
        extra={
            "encontrados": len(vencidos),
            "purgados": purgados,
            "recusados": recusados,
        },
    )
    return {"encontrados": len(vencidos), "purgados": purgados, "recusados": recusados}
