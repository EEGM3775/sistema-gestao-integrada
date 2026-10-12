# backend/modulopdca/etapas.py
"""As etapas da obra **são** as etapas do plano.

*Achado do dono, 09/10/2026:* "quando eu excluo etapas no PDCA não está
excluindo etapas da obra (etapas da obra também têm que se integrar ao PDCA)".
Até aqui a `EtapaObra` e a raiz do cronograma eram duas listas ligadas por um
FK opcional: excluir uma não mexia na outra, e a obra ficava com etapas que o
plano já não tinha.

**A regra.** Quem governa as etapas da obra é o **plano em vigor** — o vigente;
sem vigente, o rascunho (o primeiro plano, ainda em montagem). Cada raiz dele
que não é marco é uma `EtapaObra`, com o nome, a ordem e as datas previstas da
raiz. O rascunho de um replanejamento **não** governa: a obra segue a versão
vigente até a publicação (é a mesma promessa da faixa da versão na tela), e ao
publicar as etapas acompanham.

- raiz nova → etapa nova (ou a de mesmo nome, que já existia, fica ligada);
- raiz renomeada → etapa renomeada;
- raiz excluída → a etapa vai para a **lixeira** (`Excluivel`), de onde volta
  se a raiz voltar (o Ctrl+Z da montagem);
- etapa cadastrada na Obra → vira raiz do plano, se o plano em montagem aceita
  edição (`puxar_para_o_plano`).

A etapa cadastrada à mão e **nunca** ligada a plano nenhum não é apagada por
ninguém aqui: o plano só tira da obra o que ele mesmo pôs (ou o que já foi
dele).

**Quando roda.** No fim da transação (`on_commit`) de qualquer gesto que mexe
numa raiz ou no status de um cronograma — e no fim do CPM, que é quem muda as
datas. É idempotente: rodar duas vezes dá o mesmo resultado que uma.
"""
from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction

logger = logging.getLogger(__name__)

_MOTIVO = "Saiu do plano da obra (PDCA)."


def plano_em_vigor(obra_id, tenant_id):
    """O cronograma que governa as etapas: o vigente, senão o rascunho mais novo."""
    from .models import Cronograma

    base = Cronograma.objects.filter(tenant_id=tenant_id, obra_id=obra_id, eh_modelo=False)
    return (base.filter(status=Cronograma.Status.VIGENTE).first()
            or base.filter(status=Cronograma.Status.RASCUNHO).order_by("-versao").first())


def _em_montagem(obra_id, tenant_id, governa):
    """O rascunho do replanejamento, se houver — é nele que a etapa nova entra
    quando o plano em vigor está congelado."""
    from .models import Cronograma

    if governa is None or governa.status == Cronograma.Status.RASCUNHO:
        return governa
    return (Cronograma.objects
            .filter(tenant_id=tenant_id, obra_id=obra_id, eh_modelo=False,
                    status=Cronograma.Status.RASCUNHO, versao__gt=governa.versao)
            .order_by("-versao").first())


def _restaurar(etapa) -> None:
    """Tira a etapa da lixeira pela porta do `nucleo` — que fecha o item do
    `Lixo` junto, para a lixeira não mostrar um registro que já voltou."""
    from django.contrib.contenttypes.models import ContentType
    from nucleo.lixo import restaurar
    from nucleo.models import Lixo

    item = (Lixo.objects
            .filter(alvo_tipo=ContentType.objects.get_for_model(etapa.__class__),
                    alvo_id=etapa.pk, restaurado_em__isnull=True, purgado_em__isnull=True)
            .order_by("-excluido_em").first())
    if item is not None:
        restaurar(item, usuario=None)
    else:
        etapa.excluido_em = None
        etapa.excluido_por = None
        etapa.motivo_exclusao = ""
        etapa.save(update_fields=["excluido_em", "excluido_por", "motivo_exclusao"])
    etapa.refresh_from_db()


def _nome_livre(nome: str, ocupados: set[str]) -> str:
    """O nome da raiz, ou com um sufixo — `EtapaObra` é única por nome na obra,
    e duas raízes "Nova etapa" no rascunho não podem derrubar o gesto."""
    base = (nome or "Etapa").strip()[:240] or "Etapa"
    candidato, n = base, 2
    while candidato.casefold() in ocupados:
        candidato = f"{base} ({n})"
        n += 1
    return candidato


def sincronizar(obra_id, tenant_id, *, soltas=None) -> dict:
    """Faz as etapas da obra espelharem as raízes do plano em vigor."""
    from obras.models import EtapaObra

    from .models import Atividade

    resumo = {"criadas": 0, "ligadas": 0, "atualizadas": 0, "restauradas": 0, "na_lixeira": 0}
    governa = plano_em_vigor(obra_id, tenant_id)
    if governa is None:
        return resumo

    todas = {e.pk: e for e in EtapaObra.todos.filter(tenant_id=tenant_id, obra_id=obra_id)}
    raizes = list(governa.atividades.filter(pai__isnull=True, eh_marco=False)
                  .order_by("ordem", "codigo", "atividade_id"))

    # 1. Cada raiz com a sua etapa: a que já aponta, senão a de mesmo nome que
    #    ainda não é de outra raiz, senão uma nova.
    usadas: set[int] = {r.etapa_id for r in raizes if r.etapa_id in todas}
    por_nome = {e.nome_etapa.casefold(): e for e in todas.values()}
    vistas: set[int] = set()
    for i, raiz in enumerate(raizes, start=1):
        etapa = todas.get(raiz.etapa_id)
        # Duas raízes na mesma etapa (a linha copiada): a segunda ganha a sua.
        if etapa is not None and etapa.pk in vistas:
            etapa = None
        if etapa is None:
            achada = por_nome.get((raiz.nome or "").strip().casefold())
            if achada is not None and achada.pk not in usadas and achada.pk not in vistas:
                etapa = achada
                resumo["ligadas"] += 1
            else:
                ocupados = {e.nome_etapa.casefold() for e in todas.values()}
                etapa = EtapaObra.objects.create(
                    tenant_id=tenant_id, obra_id=obra_id,
                    nome_etapa=_nome_livre(raiz.nome, ocupados), ordem=i,
                    data_inicio_prevista=raiz.inicio_cedo,
                    data_fim_prevista=raiz.termino_cedo,
                )
                todas[etapa.pk] = etapa
                por_nome[etapa.nome_etapa.casefold()] = etapa
                resumo["criadas"] += 1
            usadas.add(etapa.pk)
            Atividade.objects.filter(pk=raiz.pk).update(etapa=etapa)
            raiz.etapa_id = etapa.pk

        vistas.add(etapa.pk)
        if etapa.excluido_em is not None:
            _restaurar(etapa)
            resumo["restauradas"] += 1

        mudou = []
        nome = (raiz.nome or "").strip()
        if nome and nome != etapa.nome_etapa:
            outro = por_nome.get(nome.casefold())
            if outro is None or outro.pk == etapa.pk:
                por_nome.pop(etapa.nome_etapa.casefold(), None)
                etapa.nome_etapa = nome[:255]
                por_nome[nome.casefold()] = etapa
                mudou.append("nome_etapa")
        if etapa.ordem != i:
            etapa.ordem = i
            mudou.append("ordem")
        if raiz.inicio_cedo and etapa.data_inicio_prevista != raiz.inicio_cedo:
            etapa.data_inicio_prevista = raiz.inicio_cedo
            mudou.append("data_inicio_prevista")
        if raiz.termino_cedo and etapa.data_fim_prevista != raiz.termino_cedo:
            etapa.data_fim_prevista = raiz.termino_cedo
            mudou.append("data_fim_prevista")
        if mudou:
            etapa.save(update_fields=mudou)
            resumo["atualizadas"] += 1

    # 2. O que já foi do plano e saiu dele vai para a lixeira. "Já foi do plano"
    #    = alguma atividade desta obra aponta para a etapa. A raiz do rascunho em
    #    montagem segura a etapa: ela vai voltar a governar ao publicar.
    montagem = _em_montagem(obra_id, tenant_id, governa)
    seguras = set(usadas)
    if montagem is not None and montagem.pk != governa.pk:
        seguras |= set(montagem.atividades.filter(pai__isnull=True, eh_marco=False)
                       .exclude(etapa=None).values_list("etapa_id", flat=True))
    do_plano = set(Atividade.objects
                   .filter(cronograma__obra_id=obra_id, cronograma__tenant_id=tenant_id)
                   .exclude(etapa=None).values_list("etapa_id", flat=True))
    # A raiz excluída leva o vínculo junto: sem quem diga que a etapa era dela,
    # nenhuma atividade aponta mais para lá. Quem avisa é o sinal da exclusão.
    do_plano |= set(soltas or ())
    from nucleo.lixo import mover_para_lixo

    for pk in sorted(do_plano - seguras):
        etapa = todas.get(pk)
        if etapa is None or etapa.excluido_em is not None:
            continue
        mover_para_lixo(etapa, usuario=None, motivo=_MOTIVO)
        resumo["na_lixeira"] += 1

    if any(resumo.values()):
        logger.info("pdca_etapas_sincronizadas", extra={"obra_id": obra_id, **resumo})
    if resumo["criadas"] or resumo["na_lixeira"] or resumo["restauradas"]:
        # Etapa é cadastro da Obra, e o ERP e o Orçamento lançam por ela. Renomear
        # e mover datas não avisa (é o mesmo registro seguindo o plano); nascer,
        # sumir e voltar, sim.
        from nucleo.notificacoes import avisar_quem_pode

        partes = [
            f"{resumo[chave]} {rotulo}" for chave, rotulo in (
                ("criadas", "criada(s)"), ("na_lixeira", "na lixeira"),
                ("restauradas", "restaurada(s)"),
            ) if resumo[chave]
        ]
        avisar_quem_pode(
            tenant_id=tenant_id, permissao="obra.obra.edit",
            titulo=f"Etapas da obra mudaram com o plano: {', '.join(partes)}"[:200],
            mensagem=(
                "As etapas da obra seguem as fases do plano em vigor. Títulos e "
                "orçamento lançados numa etapa que foi para a lixeira continuam "
                "apontando para ela — confira."
            ),
            url=f"/app/obras/{obra_id}",
        )
    return resumo


def puxar_para_o_plano(etapa) -> bool:
    """A etapa cadastrada na Obra entra no plano como raiz, no fim.

    Entra no plano **em montagem** — o rascunho em vigor ou o do
    replanejamento. Sem nenhum dos dois (só há o vigente, congelado), ela fica
    só na obra até o próximo replanejamento, que a recebe ao nascer.
    """
    from . import services

    governa = plano_em_vigor(etapa.obra_id, etapa.tenant_id)
    destino = _em_montagem(etapa.obra_id, etapa.tenant_id, governa)
    if destino is None or not destino.editavel:
        return False
    if destino.atividades.filter(etapa_id=etapa.pk).exists():
        return False
    ultima = (destino.atividades.filter(pai__isnull=True)
              .order_by("-ordem", "-codigo").first())
    try:
        services.inserir_atividade(
            destino, pai=None, depois_de=ultima, nome=etapa.nome_etapa,
            duracao_dias=None, eh_marco=False, etapa_id=etapa.pk,
        )
    except ValidationError:
        # Plano no teto de atividades: a etapa fica só na obra, e o cadastro
        # dela não pode falhar por causa do plano.
        logger.info("pdca_etapa_fora_do_plano", extra={"etapa_id": etapa.pk})
        return False
    return True


def motivo_para_nao_excluir(etapa) -> str | None:
    """Excluir na Obra a etapa que o plano tem: recusado, com o caminho.

    Apagar daqui deixaria a raiz no plano apontando para uma etapa na lixeira —
    e a próxima sincronia a traria de volta. A etapa sai **pelo plano**, onde as
    atividades dela saem junto e o Ctrl+Z existe.
    """
    from .models import Cronograma

    raizes = (etapa.atividades_pdca
              .filter(pai__isnull=True, cronograma__eh_modelo=False)
              .exclude(cronograma__status=Cronograma.Status.SUBSTITUIDO)
              .select_related("cronograma"))
    raiz = raizes.order_by("-cronograma__versao").first()
    if raiz is None:
        return None
    return (
        f"A etapa \"{etapa.nome_etapa}\" é a etapa {raiz.codigo} do plano da obra "
        f"(v{raiz.cronograma.versao}). Exclua-a no PDCA → Plano: as atividades dela "
        f"saem junto, e a etapa sai da obra."
    )


def renomear_no_plano(etapa) -> None:
    """O nome trocado na Obra vale no plano — nas raízes que não são história
    (vigente e rascunho). A versão substituída é linha de base e fica como foi."""
    from .models import Atividade, Cronograma

    (Atividade.objects
     .filter(etapa=etapa, pai__isnull=True, cronograma__eh_modelo=False)
     .exclude(cronograma__status=Cronograma.Status.SUBSTITUIDO)
     .exclude(nome=etapa.nome_etapa[:200])
     .update(nome=etapa.nome_etapa[:200]))


def agendar(obra_id, tenant_id, *, solta=None) -> None:
    """Sincroniza no fim da transação — uma vez por gesto, depois de tudo
    gravado. Falha aqui não desfaz o gesto que já foi gravado: é registrada e a
    próxima mudança tenta de novo. `solta` é a etapa de uma raiz que acabou de
    ser excluída (ver `sincronizar`)."""
    if not obra_id or not tenant_id:
        return
    # Uma vez por obra por transação: colar 500 linhas grava 500 atividades, e
    # a sincronia do fim vale por todas. A fila é a da própria conexão — some
    # junto com o savepoint desfeito, sem estado nosso para vazar.
    chave = (obra_id, tenant_id)
    conexao = transaction.get_connection()
    for registro in conexao.run_on_commit:
        if (getattr(registro[1], "_pdca_etapas", None) == chave
                and not getattr(registro[1], "_pdca_feito", False)):
            if solta:
                registro[1]._pdca_soltas.add(solta)
            return

    soltas: set[int] = {solta} if solta else set()

    def rodar():
        rodar._pdca_feito = True
        try:
            with transaction.atomic():
                sincronizar(obra_id, tenant_id, soltas=soltas)
        except Exception:  # noqa: BLE001 — a sincronia nunca derruba o gesto
            logger.exception("pdca_etapas_falha", extra={"obra_id": obra_id})

    rodar._pdca_etapas = chave
    rodar._pdca_soltas = soltas
    transaction.on_commit(rodar)


def cronograma_da_obra(cronograma) -> bool:
    """Só o plano de uma obra mexe em etapa — o modelo da biblioteca não."""
    return bool(cronograma and cronograma.obra_id and not cronograma.eh_modelo)
