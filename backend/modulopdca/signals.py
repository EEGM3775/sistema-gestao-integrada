# backend/modulopdca/signals.py
"""O que o PDCA precisa fazer quando a plataforma vai apagar uma obra de verdade.

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

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from nucleo.lixo import antes_de_purgar
from obras.models import Obra

from .models import Atividade, Cronograma

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
