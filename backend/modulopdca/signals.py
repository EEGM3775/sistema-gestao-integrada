# backend/modulopdca/signals.py
"""Os dois lados do sinal na fronteira do módulo: a purga e a escada de atesto.

**A purga** (D116) é o contrato do `nucleo/lixo.py`: a plataforma avisa antes do
`DELETE` e o módulo dono decide o que sobrevive.

**A escada** (PDCA.3) é o contrato gêmeo do `nucleo/aprovacao.py`: o motor
termina a escada, emite `aprovacao_concluida` e **não sabe o que aprovou** —
congelar a medição e gerar o título é daqui. É o mesmo desenho, pelo mesmo
motivo: o `nucleo` é importado por todos e não pode importar nenhum de volta.

---

O que o PDCA precisa fazer quando a plataforma vai apagar uma obra de verdade.

Primeiro cliente do sinal `antes_de_purgar` do `nucleo/lixo.py` (D116), e ele
existe por uma frase do dono:

> *"Deixa o plano para poder ser usado como modelo em outra obra — e isso tem que
> ser possível para não ter que criar 300 planos em um empreendimento grande."*

`Cronograma.obra` é `CASCADE`, e `eh_modelo` é uma marca no próprio cronograma:
sem este receptor, a purga da obra levaria a biblioteca de padrões da empresa
junto — e levaria **calada**, que é o pior modo.

**Por que aqui e não no `nucleo`.** O `nucleo` é importado por todos e não pode
importar nenhum de volta; ele não sabe que cronograma existe. O contrato é o
mesmo do `aprovacao_concluida`: a plataforma avisa, o módulo dono decide.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from nucleo.aprovacao import aprovacao_concluida
from nucleo.lixo import antes_de_purgar
from obras.models import Obra

from . import etapas
from .models import (
    AditivoContrato, Atividade, ContratoObra, Cronograma, LiberacaoRetencao,
    Medicao,
)

logger = logging.getLogger(__name__)


@receiver(antes_de_purgar, sender=Obra, dispatch_uid="pdca_preserva_plano_modelo")
def preservar_plano_modelo(sender, alvo, item, **kwargs):
    """Desliga da obra os planos marcados como modelo, antes de ela morrer.

    Roda **dentro da transação da purga** — se algo aqui falhar, a obra não é
    apagada e o item continua na lixeira com o motivo escrito. É a ordem certa:
    melhor uma purga recusada que um plano modelo perdido.

    Três passos, e a ordem importa:

    1. **soltar o calendário das atividades** e 2. **do cronograma** — os dois
       são `PROTECT` para `CalendarioTrabalho`, e o calendário *da obra* é
       `CASCADE` a partir dela. Um modelo que sobrevivesse ainda apontando para o
       calendário da obra recriaria exatamente o impasse que abriu o D116:
       `CASCADE` de um lado, `PROTECT` do outro, `DELETE` impossível. O modelo
       fica **sem** calendário, que é o estado honesto — o CPM recusa rodar até
       alguém escolher um, em vez de inventar segunda a sexta;
    3. **soltar a obra**, e aí o modelo vira o que já era por definição: um
       padrão *da empresa*. Isso nunca foi outra coisa — a constraint de nome do
       modelo já é única por `tenant`, e não por obra.

    O que **não** sobrevive: o plano comum da obra. Ele morre com ela, que é o
    desenho (`CASCADE`), e é o que separa "meu padrão de torre" de "o cronograma
    daquela obra que eu apaguei".
    """
    modelos = list(
        Cronograma.objects.filter(obra=alvo, eh_modelo=True).values_list("pk", flat=True)
    )
    if modelos:
        Atividade.objects.filter(
            cronograma_id__in=modelos, calendario__obra=alvo
        ).update(calendario=None)
        Cronograma.objects.filter(pk__in=modelos, calendario__obra=alvo).update(
            calendario=None
        )
        Cronograma.objects.filter(pk__in=modelos).update(obra=None)
        logger.info(
            "pdca_plano_modelo_preservado",
            extra={"obra_id": alvo.pk, "cronogramas": len(modelos)},
        )

    # --- E agora o nó do D116 propriamente dito -------------------------------
    # O que sobrou são os planos COMUNS, que morrem com a obra — e é aí que está
    # o impasse que abriu este achado: `CalendarioTrabalho.obra` é `CASCADE` e
    # `Cronograma.calendario` é `PROTECT`. Os dois entram na mesma fila de
    # exclusão, e o coletor do Django **não isenta o que já está na fila**: ele
    # vê um `PROTECT` apontando para o calendário e recusa o `DELETE` inteiro.
    #
    # Sem estas duas linhas, toda obra que chegou a ter cronograma seria recusada
    # na purga — a lixeira encheria de obras imortais, e a decisão do dono ("o
    # lixo é apagado depois de 15 dias") não aconteceria justamente para as obras
    # que mais ocupam espaço.
    #
    # Soltar o calendário antes resolve porque o `PROTECT` deixa de existir no
    # instante do `DELETE`: sem ninguém protegendo, o `CASCADE` leva calendário e
    # cronograma juntos, na ordem que o coletor quiser.
    restantes = list(
        Cronograma.objects.filter(obra=alvo).values_list("pk", flat=True)
    )
    if restantes:
        Atividade.objects.filter(cronograma_id__in=restantes).update(calendario=None)
        Cronograma.objects.filter(pk__in=restantes).update(calendario=None)
        logger.info(
            "pdca_calendario_solto_para_purga",
            extra={"obra_id": alvo.pk, "cronogramas": len(restantes)},
        )


@receiver(pre_delete, sender=Obra, dispatch_uid="pdca_alerta_purga_direta")
def alertar_purga_sem_lixeira(sender, instance, **kwargs):
    """Rede de segurança: avisa se uma obra for apagada por fora da lixeira.

    Um `Obra.objects.delete()` em shell, migration de dados ou management command
    não passa por `antes_de_purgar` — e levaria o plano modelo junto, em
    silêncio. Não dá para **impedir** aqui sem travar a purga legítima (que
    também termina em `pre_delete`), mas dá para deixar rastro: o log é o que
    transforma "a biblioteca de padrões sumiu" de mistério em linha de
    investigação.
    """
    sobreviventes = Cronograma.objects.filter(obra=instance, eh_modelo=True).count()
    if sobreviventes:
        logger.warning(
            "pdca_plano_modelo_em_risco",
            extra={"obra_id": instance.pk, "cronogramas": sobreviventes},
        )


# ---------------------------------------------------------------------------
# PDCA.3 — o que acontece quando a escada de atesto termina
# ---------------------------------------------------------------------------
#
# O `nucleo.aprovacao` emite `aprovacao_concluida` com `sender` = a classe do
# alvo, o que permite conectar **sem filtro em Python**: cada receptor abaixo só
# acorda para o seu tipo de documento.
#
# **Falha aqui não desfaz o atesto** — é decisão escrita do motor: *"a decisão de
# quem tem alçada é verdade independente de o efeito colateral ter dado certo"*.
# Por isso estes receptores logam e deixam o objeto num estado legível, em vez de
# levantar e apagar a assinatura do fiscal. O que eles **não** podem fazer é
# falhar em silêncio: o `logger.exception` do motor grava o pedido junto, e o
# documento fica visível na tela com o estado real.


@receiver(aprovacao_concluida, sender=Medicao, dispatch_uid="pdca_medicao_atestada")
def congelar_medicao_atestada(sender, pedido, alvo, aprovado, **kwargs):
    """Último degrau da medição → congela e (se aprovada) gera o título no ERP.

    `alvo` vem `None` quando o objeto já não existe — o motor busca a instância
    e ela pode ter ido para a lixeira entre o atesto e o anúncio. Não é erro: é
    o caso em que não há o que congelar, e seguir adiante criaria um
    `ContaPagar` para um documento que ninguém consegue mais abrir.
    """
    if alvo is None:
        logger.warning(
            "pdca_medicao_sumiu_antes_do_congelamento",
            extra={"pedido_id": pedido.pk, "alvo_id": pedido.alvo_id},
        )
        return
    if alvo.esta_congelada:
        # Idempotência: um reenvio do sinal não pode gerar um segundo título.
        # A escada já tem o `select_for_update` que impede a corrida de
        # milissegundos; isto cobre o reenvio manual e o replay de fila.
        logger.info(
            "pdca_medicao_ja_congelada",
            extra={"medicao_id": alvo.pk, "status": alvo.status},
        )
        return

    from . import services

    services._congelar_medicao(alvo, aprovada=aprovado)
    logger.info(
        "pdca_medicao_congelada",
        extra={
            "medicao_id": alvo.pk, "aprovada": aprovado,
            "conta_pagar_ref": alvo.conta_pagar_ref,
        },
    )


@receiver(aprovacao_concluida, sender=LiberacaoRetencao,
          dispatch_uid="pdca_liberacao_atestada")
def congelar_liberacao_atestada(sender, pedido, alvo, aprovado, **kwargs):
    """Último degrau da liberação → devolve o retido pelo ERP, em título próprio."""
    if alvo is None:
        logger.warning(
            "pdca_liberacao_sumiu_antes_do_congelamento",
            extra={"pedido_id": pedido.pk, "alvo_id": pedido.alvo_id},
        )
        return
    if alvo.esta_congelada:
        logger.info(
            "pdca_liberacao_ja_congelada",
            extra={"liberacao_id": alvo.pk, "status": alvo.status},
        )
        return

    from . import services

    services._congelar_liberacao(alvo, aprovada=aprovado)
    logger.info(
        "pdca_liberacao_congelada",
        extra={
            "liberacao_id": alvo.pk, "aprovada": aprovado,
            "conta_pagar_ref": alvo.conta_pagar_ref,
        },
    )


@receiver(aprovacao_concluida, sender=AditivoContrato,
          dispatch_uid="pdca_aditivo_aprovado")
def congelar_aditivo_aprovado(sender, pedido, alvo, aprovado, **kwargs):
    """Último degrau do aditivo → congela e, aprovado, **aplica no contrato**.

    Aplicar é o que separa este receptor dos outros dois: a medição aprovada
    gera um título e a liberação devolve dinheiro, mas o aditivo **muda a régua**
    — cria item novo, revisa preço, move a vigência. Por isso o serviço revalida
    antes de aplicar: entre a submissão e o atesto podem passar dias, e nesse
    intervalo uma medição pode ter consumido o saldo que a supressão ia tirar.
    """
    if alvo is None:
        logger.warning(
            "pdca_aditivo_sumiu_antes_da_aplicacao",
            extra={"pedido_id": pedido.pk, "alvo_id": pedido.alvo_id},
        )
        return
    if alvo.esta_congelado:
        # Idempotência: um reenvio do sinal não pode aplicar o aditivo duas
        # vezes — e aplicar duas vezes criaria o item novo em duplicata.
        logger.info(
            "pdca_aditivo_ja_congelado",
            extra={"aditivo_id": alvo.pk, "status": alvo.status},
        )
        return

    from . import services

    services._congelar_aditivo(alvo, aprovado=aprovado)
    logger.info(
        "pdca_aditivo_congelado",
        extra={
            "aditivo_id": alvo.pk, "aprovado": aprovado,
            "aplicado_em": str(alvo.aplicado_em),
        },
    )


@receiver(antes_de_purgar, sender=ContratoObra, dispatch_uid="pdca_purga_contrato")
def recusar_purga_de_contrato_com_titulo(sender, alvo, item, **kwargs):
    """Contrato que já gerou pagamento não some da base — nem pela purga.

    A lixeira dá ao usuário o direito de desfazer; ela não dá o direito de
    apagar a prova de para onde o dinheiro foi. Um contrato cujas medições
    geraram `ContaPagar` deixaria, se purgado, títulos no ERP apontando para um
    documento inexistente — e a conciliação do contador acabaria num id órfão.

    Recusar **dentro** da transação da purga é o comportamento certo, e o mesmo
    que o plano modelo usa: melhor uma purga recusada, com o motivo escrito no
    item da lixeira, do que um rastro financeiro perdido em silêncio.
    """
    from django.core.exceptions import ValidationError

    com_titulo = Medicao.todos.filter(
        contrato=alvo, conta_pagar_ref__isnull=False,
    ).count()
    if com_titulo:
        raise ValidationError(
            f"O contrato {alvo.numero} tem {com_titulo} medição(ões) que geraram "
            f"título no financeiro. Contrato com pagamento não é apagado — "
            f"encerre-o em vez de excluí-lo."
        )


# ---------------------------------------------------------------------------
# As etapas da obra seguem as raízes do plano em vigor (`modulopdca/etapas.py`)
# ---------------------------------------------------------------------------


def _obra_do_cronograma(cronograma_id):
    linha = (Cronograma.objects.filter(pk=cronograma_id)
             .values_list("obra_id", "tenant_id", "eh_modelo").first())
    if not linha or not linha[0] or linha[2]:
        return None, None
    return linha[0], linha[1]


@receiver(post_save, sender=Atividade, dispatch_uid="pdca_etapas_raiz_gravada")
@receiver(post_delete, sender=Atividade, dispatch_uid="pdca_etapas_raiz_excluida")
def raiz_mudou(sender, instance, **kwargs):
    """Só a raiz é etapa. A filha só interessa quando o `pai` pode ter mudado
    (deixou de ser raiz, ou virou): o resto dela chega pela raiz, no fim do CPM."""
    if instance.pai_id is not None:
        # A filha que sai junto com a etapa (a cascata) não diz nada novo.
        if kwargs.get("signal") is post_delete:
            return
        campos = kwargs.get("update_fields")
        if campos is not None and "pai" not in campos:
            return
    obra_id, tenant_id = _obra_do_cronograma(instance.cronograma_id)
    solta = instance.etapa_id if kwargs.get("signal") is post_delete and instance.pai_id is None else None
    etapas.agendar(obra_id, tenant_id, solta=solta)


@receiver(post_save, sender=Cronograma, dispatch_uid="pdca_etapas_cronograma_gravado")
@receiver(post_delete, sender=Cronograma, dispatch_uid="pdca_etapas_cronograma_excluido")
def cronograma_mudou(sender, instance, **kwargs):
    """Publicar troca o plano em vigor; descartar o rascunho também."""
    if etapas.cronograma_da_obra(instance):
        etapas.agendar(instance.obra_id, instance.tenant_id)
