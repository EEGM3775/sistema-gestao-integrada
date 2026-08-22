# backend/moduloprancheta/tasks.py
"""Conversão em background — a fatia assíncrona da Prancheta.

**Contexto de tenant na primeira linha, sempre.** Task que toca o ORM sem
`tenant_context()` não acha linha nenhuma sob a RLS fail-closed do worker: é o
**D8** literal (a cobrança que respondia 202 e nunca gerava boleto), e o
`funcoesimpexp` já paga esse pedágio nas três tasks dele. Aqui a armadilha seria
pior que um 202 vazio — a derivada ficaria `pendente` para sempre e a tela do
canteiro mostraria "aguardando conversão" sem nada aguardando de fato.

**Por que assíncrona e não no request:** a planta §5 é explícita — um RVT de
300 MB não converte dentro de uma requisição, e o nginx corta em 60 s. É a mesma
régua do corte de volume do `funcoesimpexp` (a R10), pela mesma razão: o usuário
que não vê resultado reenvia, e o reenvio dobra a carga exatamente quando o
sistema já está apertado.

**Retry só no que retentativa conserta.** O `ErroDeConversao` carrega
`retentavel`, e o `pipeline.executar` já persistiu o estado antes de deixar a
exceção subir. Então o Celery repete rede/memória/pico e **não** repete "este
DWG exige o motor premium" — que falharia idêntico 3× e entulharia a DLQ de
limite de plano.
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

from nucleo.tasks import DLQTask
from nucleo.tenancy import tenant_context

from . import pipeline
from .models import DerivadaProjeto, RevisaoDocumento

logger = logging.getLogger(__name__)


#: Relógio do Celery para a conversão — a camada de fora (D57).
#:
#: **Folgado em relação ao teto de `limites.py` de propósito.** O de dentro
#: levanta exceção capturável e produz erro legível; este só existe para o caso em
#: que o de dentro não consegue agir (motor preso em extensão C, onde o SIGALRM
#: não é entregue). Se os dois disparassem junto, o pior venceria a corrida.
_SOFT = getattr(settings, "PRANCHETA_CONVERSAO_SEGUNDOS", 300) + 60
_HARD = _SOFT + 60


@shared_task(bind=True, base=DLQTask, max_retries=2, default_retry_delay=60,
             name="moduloprancheta.converter_derivada",
             soft_time_limit=_SOFT, time_limit=_HARD)
def converter_derivada(self, derivada_id, tenant_id, tiers=None, teto_snap=0, *_extras):
    """Converte UMA derivada. Uma task por derivada, de propósito.

    Um IFC rende `modelo_3d` e um DWG rende `vetor_2d`; se o dia em que um
    formato render duas derivadas as duas viverem na mesma task, a falha de uma
    levaria a outra junto no retry. Task por derivada também deixa o
    `reprocessar` de uma linha só custar uma linha só.

    **`teto_snap` viaja como argumento, e não é consultado aqui**, pela mesma
    razão que `tiers`: o worker não tem usuário, e o teto é do PLANO de quem
    subiu. Resolvê-lo aqui exigiria o worker ler assinatura e add-ons do IAM a
    cada job — mais uma dependência de rede no caminho da conversão, para
    responder algo que quem enfileirou já sabia. `0` desliga o snap, que é o
    default seguro para todo chamador antigo (e para a fila que ficou parada
    de um deploy para o outro, com a mensagem sem o campo).

    **`*_extras` engole argumento que este worker ainda não conhece, e custou
    uma tarde para ser escrito.** Ao introduzir o `teto_snap`, o backend passou a
    enfileirar com 5 posicionais enquanto o worker ainda rodava a versão de 4:
    `TypeError` a cada mensagem, e como o `DLQTask` reagenda com 60 s de espera,
    o sintoma na tela não foi "erro" — foi **conversão de segundos levando
    minutos**, que é muito mais difícil de ligar à causa. Num deploy rolante o
    produtor sobe antes do worker em algum momento, sempre; a fila também
    guarda mensagem de antes do deploy. Engolir o extra é o que torna a ordem
    do deploy irrelevante em vez de armadilha.

    A regra que fica: **argumento novo entra no fim, com default, e o worker
    ignora o que não entende.** Mudar a POSIÇÃO ou o significado de um argumento
    existente continua exigindo task nova com outro nome.
    """
    tiers = tiers or list(pipeline.TIERS_PADRAO)
    with tenant_context(tenant_id):
        derivada = (
            DerivadaProjeto.objects
            .select_related("revisao")
            .filter(pk=derivada_id, tenant_id=tenant_id)
            .first()
        )
        if derivada is None:
            # Revisão apagada entre o agendamento e o worker. Não é erro: a
            # cascata levou a derivada junto, e não há o que converter.
            logger.info("prancheta: derivada %s sumiu antes do job.", derivada_id)
            return None

        pipeline.executar(derivada, tiers=tiers, teto_snap=teto_snap)
        return derivada.pk


@shared_task(bind=True, base=DLQTask, max_retries=1,
             name="moduloprancheta.reprocessar_revisao")
def reprocessar_revisao(self, revisao_id, tenant_id, tiers=None, teto_snap=0):
    """Reagenda **tudo** de uma revisão, ignorando a idempotência.

    É o verbo por trás de `prancheta.conversao.reprocessar`. Existe separado do
    `agendar` normal porque o caso de uso é o oposto: ali a pergunta é "falta
    converter?", aqui é "converta de novo mesmo que esteja pronto" — motor novo
    na imagem, binário do LibreDWG que finalmente entrou, derivada que saiu torta.
    """
    tiers = tiers or list(pipeline.TIERS_PADRAO)
    with tenant_context(tenant_id):
        revisao = RevisaoDocumento.objects.filter(pk=revisao_id, tenant_id=tenant_id).first()
        if revisao is None:
            logger.info("prancheta: revisão %s sumiu antes do reprocessamento.", revisao_id)
            return []
        return pipeline.agendar(revisao, tiers=tiers, teto_snap=teto_snap, forcar=True)
