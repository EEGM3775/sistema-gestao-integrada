# backend/nucleo/frota.py
"""D98 — a gerência da frota de trabalho pesado: admissão, fila e recolocação.

**O que faltava.** O `worker-conversao` tem freio desde o D57 (`--concurrency 1`,
`mem_limit`, o orçamento de `moduloprancheta/limites.py`) e nunca teve
**porteiro**: quem chegava primeiro ocupava a frota, quem chegava depois esperava
sem ordem, sem posição e sem garantia. Um tenant free podia segurar a única vaga
enquanto um premium esperava, e um premium podia segurar todas enquanto o free
esperava indefinidamente.

**O papel é o do ClusterODM**, que o drone já tem na frente dos `NodeODM`: ele
enfileira, distribui entre nós e diz a posição a quem espera. É esse papel que
este módulo cumpre para a conversão — e por isso o endereço é `nucleo` e não
`moduloprancheta`: a Prancheta é a **primeira** cliente, não a dona. Importação
de acervo, exportação grande e ortofoto do Maps têm o mesmo problema, e entram
pelo campo `frota` sem uma segunda fila paralela.

## O desenho, em uma frase

Quem tem trabalho pesado chama `enfileirar()` em vez de `.delay()`, e recebe a
**posição**. O `despachar()` é quem publica no Celery, respeitando a política — e
ele roda em dois momentos: logo depois de enfileirar (para a fila vazia não
esperar nada) e quando um job termina (para a cadeira liberada ser ocupada na
hora).

## As três decisões do dono que este arquivo aplica

1. **Fila única com prioridade e cadeira marcada em FRAÇÃO da frota** — nunca
   fila separada por plano, nunca número absoluto de cadeiras. Os números estão
   em [payment/planos.py](../../payment/planos.py) §5.4c, declarados como
   provisórios até o estudo existir.
2. **Recolocação com envelhecimento** — o job que passou do turno volta ao fim da
   fila, mas sobe um degrau a cada volta. Sem o degrau, um arquivo de 40 MB atrás
   de um fluxo contínuo de arquivos pequenos voltaria ao fim para sempre; com
   ele, cede a vez a quem esperou **e** converge.
3. **O administrador passa na frente só da própria empresa** — a ordem entre
   empresas do mesmo plano continua sendo a de chegada. Um botão que atrasasse o
   vizinho é um botão que todo mundo aperta sempre, e aí ele não prioriza nada:
   só torna a fila imprevisível.

## O limite honesto deste desenho

O despachante não é um processo próprio rodando em laço: ele é chamado nos dois
momentos acima, dentro do processo que já estava trabalhando. É o suficiente
enquanto todo job que ocupa cadeira **termina avisando** — e o `DLQTask` garante
que até o que falha avisa. O que este desenho não cobre sozinho é a cadeira presa
por um worker morto (OOM do cgroup, container derrubado): para isso existe
`liberar_orfas()`, que o beat chama e que devolve à fila o que passou do tempo
máximo em `despachada` sem notícia. Sem ela, uma morte violenta reduziria a frota
em uma vaga em silêncio, para sempre — que é a forma clássica deste defeito.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from payment.addons import ADDONS
from payment.planos import (
    FROTA_BANDA_DE_ENVELHECIMENTO,
    FROTA_CADEIRAS_POR_ADDON,
    FROTA_DEGRAU_POR_VOLTA,
    FROTA_FRACAO_RESERVADA_FREE,
    FROTA_FRACAO_RESERVADA_PREMIUM,
    FROTA_PENALIDADE_DA_VOLTA,
    FROTA_PLANOS_FREE,
    FROTA_PLANOS_PREMIUM,
)

from .models import TarefaNaFila

logger = logging.getLogger(__name__)

#: A frota da conversão de projeto. Nomeada aqui e não em `moduloprancheta` para
#: o módulo cliente não precisar inventar a string — e para o dia em que a
#: segunda frota existir, a primeira já ter nome próprio.
FROTA_CONVERSAO = "conversao"

#: Prioridade de partida de cada classe de cadeira. Menor sai primeiro.
#:
#: **São patamares largos de propósito**, e a `FROTA_BANDA_DE_ENVELHECIMENTO` os
#: mantém estanques: um job free que voltou trinta vezes anda dentro do patamar
#: dele e nunca alcança o de um premium recém-chegado. Isso é a política, não um
#: efeito colateral — o envelhecimento existe para o arquivo pesado convergir
#: contra os *iguais* dele, não para comprar plano de graça.
PARTIDA = {"premium": 100, "comum": 200, "free": 300}


def _prioridade(classe: str, voltas: int = 0) -> int:
    """Onde este job entra na fila, dadas as voltas que já deu.

    Volta zero é a partida do patamar. A cada volta o job recomeça **atrás** de
    quem não gastou turno nenhum (a penalidade) e essa penalidade decai — é o
    "volta pro fim, mas com prioridade crescente" em uma linha. O `max` prende o
    resultado dentro do patamar do plano.
    """
    ajuste = FROTA_PENALIDADE_DA_VOLTA - voltas * FROTA_DEGRAU_POR_VOLTA
    if voltas == 0:
        ajuste = 0
    return PARTIDA[classe] + max(-FROTA_BANDA_DE_ENVELHECIMENTO, ajuste)

#: Quanto tempo uma cadeira pode ficar `despachada` sem notícia antes de ser
#: considerada órfã. Não é limite comercial e por isso **não** mora no
#: `planos.py` (§5.6): é o relógio de um protocolo interno — o teto de conversão
#: mais a folga de agendamento do broker. Encurtá-lo despacharia o mesmo trabalho
#: duas vezes; alongá-lo só atrasa a recuperação de uma morte violenta.
MINUTOS_ATE_ORFA = 30


def classe_do_plano(plano: str) -> str:
    """Em qual reserva este plano senta. `comum` é o meio, e é o caso normal."""
    codigo = (plano or "").strip().lower()
    if codigo in FROTA_PLANOS_PREMIUM:
        return "premium"
    if codigo in FROTA_PLANOS_FREE:
        return "free"
    return "comum"


def cadeiras_de_addon(user) -> int:
    """Quantas cadeiras os add-ons deste cliente compram.

    Lê a claim `iam_addons`, a mesma que o `moduloprancheta/planos.py` já usa
    para o snap — um add-on desconhecido é ignorado em silêncio, porque catálogo
    novo no IAM não pode derrubar conversão em backend que ainda não subiu.
    """
    contratados = getattr(user, "iam_addons", None) or []
    if isinstance(contratados, str):
        contratados = [contratados]
    unidades = sum(
        ADDONS.get(codigo, {}).get("incrementa", {}).get("cadeiras_frota", 0)
        for codigo in contratados
    )
    return unidades * FROTA_CADEIRAS_POR_ADDON


def vagas_da_frota(frota: str = FROTA_CONVERSAO) -> int:
    """Quantas cadeiras a frota tem, ao todo.

    **Sai da configuração do worker e não de um número neste arquivo**: a frota é
    o que o compose subiu (`--concurrency`), e um número aqui divergiria dela na
    primeira vez que alguém escalasse a máquina — prometendo cadeiras que não
    existem ou desperdiçando as que existem. Um só é o default honesto: é o que
    o `worker-conversao` roda hoje, e a razão está escrita no `base.yml`
    (converter é trabalho de CPU e memória; dois processos dobram o pico de RAM
    sem dobrar a vazão).
    """
    from django.conf import settings

    vagas = getattr(settings, "FROTA_VAGAS", {}) or {}
    return max(1, int(vagas.get(frota, 1)))


def _reserva(vagas: int) -> dict[str, int]:
    """Quantas cadeiras cada classe tem garantidas, e quantas são livres.

    **Abaixo de ~5 vagas toda fração arredonda para zero, e isso está certo.**
    Com uma vaga só — a frota de hoje — não existe "metade de cadeira": a reserva
    degenera em ordem de prioridade, que é exatamente o comportamento desejável
    numa frota mínima. A fração passa a ter efeito material quando a frota
    crescer, sem ninguém trocar código. É a razão de ser fração e não número.
    """
    premium = int(vagas * FROTA_FRACAO_RESERVADA_PREMIUM)
    free = int(vagas * FROTA_FRACAO_RESERVADA_FREE)
    return {"premium": premium, "free": free, "livre": max(0, vagas - premium - free)}


# ---------------------------------------------------------------------------
# Entrar na fila
# ---------------------------------------------------------------------------
def enfileirar(*, tenant_id, chave: str, tarefa: str, argumentos: list,
               user=None, plano: str = "", frota: str = FROTA_CONVERSAO) -> TarefaNaFila:
    """Põe um trabalho pesado na fila e devolve a linha, já com a posição.

    **Substitui o `.delay()` no chamador**, e a diferença é toda a promessa do
    D98: um `.delay()` não sabe dizer quem está na frente nem recusar admissão.

    **Idempotente pela `chave`**, e é o que impede o upload reenviado, o
    `reprocessar` clicado duas vezes e o retry do Celery de virarem três lugares
    para o mesmo arquivo. A linha viva vence: quem chega de novo recebe a que já
    existe, com a posição dela — nunca uma segunda.

    **Despacha em seguida, e é por isso que o chamador não precisa lembrar.** A
    admissão existe para segurar quem não cabe, não para atrasar quem cabe: com a
    frota livre, fazer o arquivo esperar um tique seria porteiro virando
    burocracia. Deixar o despacho a cargo de quem chama seria a mesma armadilha
    do `.delay()` esquecido — funciona nos quatro lugares que alguém lembrou.
    """
    plano = plano or getattr(user, "iam_plano", "") or ""
    with transaction.atomic():
        vivo = (
            TarefaNaFila.objects.select_for_update()
            .filter(frota=frota, chave=chave,
                    situacao__in=[TarefaNaFila.Situacao.AGUARDANDO,
                                  TarefaNaFila.Situacao.DESPACHADA])
            .first()
        )
        if vivo is not None:
            return vivo
        criada = TarefaNaFila.objects.create(
            tenant_id=tenant_id, plano=plano,
            cadeiras_extras=cadeiras_de_addon(user) if user is not None else 0,
            frota=frota, tarefa=tarefa, argumentos=list(argumentos), chave=chave,
            prioridade=_prioridade(classe_do_plano(plano)),
        )
    # Fora da transação: o `_publicar` manda a mensagem, e o worker pode pegá-la
    # antes de um commit que ainda não aconteceu. É o D8 visto de outro ângulo.
    despachar(frota)
    criada.refresh_from_db()
    return criada


def _antes_de(tarefa: TarefaNaFila):
    """Quem sai antes de `tarefa`, na ordem da política, como `Q`.

    Função e não expressão inline porque a ordem aparece em três lugares
    (posição, aviso de urgência e a listagem da tela) e três cópias divergiriam
    na primeira vez que alguém mexesse no critério — e a divergência seria
    silenciosa: a tela diria "3º" e a fila entregaria em quinto.
    """
    from django.db.models import Q

    return Q(prioridade__lt=tarefa.prioridade) | Q(
        prioridade=tarefa.prioridade, criada_em__lt=tarefa.criada_em,
    )


def posicao(tarefa: TarefaNaFila) -> int:
    """Quantos estão na frente **deste** trabalho, +1. `0` se já saiu da fila.

    A contagem é sobre a fila inteira e não sobre a do plano: a pergunta que a
    pessoa faz é "quando chega a minha vez", e a resposta honesta considera todo
    mundo que vai passar antes dela. Contar só os do mesmo plano daria um número
    menor e errado — a pior combinação numa tela de espera.
    """
    if tarefa.situacao != TarefaNaFila.Situacao.AGUARDANDO:
        return 0
    return 1 + (
        TarefaNaFila.objects
        .filter(frota=tarefa.frota, situacao=TarefaNaFila.Situacao.AGUARDANDO)
        .filter(_antes_de(tarefa))
        .count()
    )


def ha_espera(chave: str, frota: str = FROTA_CONVERSAO) -> bool:
    """Existe alguém aguardando nesta frota, além de quem pergunta?

    *(decisão do dono, 16/08/2026: ceder a vez "só se tiverem arquivos na fila".)*
    É a pergunta que o motor pesado faz quando o turno vence, para não largar a
    cadeira nas mãos de ninguém e pagar de novo o custo fixo da retomada.

    **Aguardando, e não "existe outra tarefa".** Quem já está rodando ocupa outra
    cadeira e não está esperando por esta; contá-lo faria o arquivo pesado ceder a
    vez para quem não a receberia. E a própria `chave` sai da conta porque uma
    tarefa recolocada pode reaparecer como aguardando enquanto sua última passada
    ainda termina — sem a exclusão, ela cederia a vez para si mesma, para sempre.
    """
    return (
        TarefaNaFila.objects
        .filter(frota=frota, situacao=TarefaNaFila.Situacao.AGUARDANDO)
        .exclude(chave=chave)
        .exists()
    )


# ---------------------------------------------------------------------------
# Sair da fila — o despachante
# ---------------------------------------------------------------------------
def despachar(frota: str = FROTA_CONVERSAO, *, limite: int = 8) -> list[int]:
    """Ocupa as cadeiras livres com quem está esperando. Devolve os ids que saíram.

    **A política mora aqui e em nenhum outro lugar.** Uma cadeira reservada ao
    premium não recebe free mesmo com a fila cheia de free — é o que impede o
    premium de esperar atrás de um lote de trezentas pranchas de um cliente free.
    E a recíproca: a reserva do free não recebe premium, que é o que impede o
    free de esperar uma eternidade. As cadeiras livres são de quem chegar.

    `limite` existe para o laço não virar uma varredura da fila inteira quando a
    frota for grande; o despachante roda de novo a cada job concluído.
    """
    saidas: list[int] = []
    for _ in range(limite):
        with transaction.atomic():
            escolhida = _proxima(frota)
            if escolhida is None:
                break
            escolhida.situacao = TarefaNaFila.Situacao.DESPACHADA
            escolhida.despachada_em = timezone.now()
            escolhida.save(update_fields=["situacao", "despachada_em"])
        # **Publicar FORA da transação, e isto custou o D8 em outro módulo.**
        # Dentro dela, o worker pode pegar a mensagem antes do commit e não achar
        # a linha que acabou de ser marcada — a corrida clássica de agendar
        # dentro da transação. Fora, o pior caso é uma linha `despachada` cuja
        # mensagem não saiu, e essa a `liberar_orfas` devolve à fila.
        _publicar(escolhida)
        saidas.append(escolhida.tarefa_id)
    return saidas


def _proxima(frota: str) -> TarefaNaFila | None:
    """A próxima que pode sentar, considerando as cadeiras que sobraram.

    Duas perguntas, nesta ordem: **há cadeira para esta classe?** e, entre as que
    podem sentar, **quem está na frente?** Inverter as duas — pegar o primeiro da
    fila e depois perguntar se cabe — daria uma fila que trava: o primeiro seria
    sempre o mesmo job sem cadeira, e ninguém atrás dele andaria.
    """
    from django.db.models import Q

    vagas = vagas_da_frota(frota)
    reserva = _reserva(vagas)
    ocupadas = _ocupacao(frota)
    if sum(ocupadas.values()) >= vagas:
        return None

    # Uma classe consome primeiro a **própria** reserva e só depois as cadeiras
    # livres; o `comum` só tem as livres, porque não tem reserva. Contar assim —
    # e não "sobrou vaga, entra qualquer um" — é o que faz a reserva existir:
    # sem isto, a última cadeira do premium seria ocupada pelo primeiro free da
    # fila e a garantia viraria decoração.
    usadas_das_livres = (
        max(0, ocupadas["premium"] - reserva["premium"])
        + ocupadas["comum"]
        + max(0, ocupadas["free"] - reserva["free"])
    )
    ha_livre = usadas_das_livres < reserva["livre"]

    podem = [
        classe for classe in ("premium", "free")
        if ocupadas[classe] < reserva[classe]
    ]
    if ha_livre:
        podem = ["premium", "comum", "free"]
    if not podem:
        return None

    # **A classe sai do PLANO, nunca da faixa de prioridade**, e esta linha é a
    # correção de um acoplamento que o teste pegou. A primeira versão deduzia a
    # classe pela faixa (`prioridade < 200` = premium), e como o envelhecimento
    # mexe na prioridade, um job free com voltas suficientes passava a ser lido
    # como `comum` e sentava numa cadeira que não era dele — a reserva vazando
    # justamente para quem mais espera. Plano é imutável na linha; prioridade não.
    planos_da_classe = Q()
    if "premium" in podem:
        planos_da_classe |= Q(plano__in=FROTA_PLANOS_PREMIUM)
    if "free" in podem:
        planos_da_classe |= Q(plano__in=FROTA_PLANOS_FREE)
    if "comum" in podem:
        planos_da_classe |= ~Q(plano__in=[*FROTA_PLANOS_PREMIUM, *FROTA_PLANOS_FREE])

    return (
        TarefaNaFila.objects.select_for_update(skip_locked=True)
        .filter(frota=frota, situacao=TarefaNaFila.Situacao.AGUARDANDO)
        .filter(planos_da_classe)
        .order_by("prioridade", "criada_em")
        .first()
    )


def _ocupacao(frota: str) -> dict[str, int]:
    """Quantas cadeiras cada classe está ocupando agora.

    Conta `despachada` e não "executando": a cadeira é ocupada no instante em que
    a mensagem sai, senão o despachante publicaria cem mensagens no intervalo
    entre publicar e o worker começar.
    """
    contagem = {"premium": 0, "comum": 0, "free": 0}
    em_voo = TarefaNaFila.objects.filter(
        frota=frota, situacao=TarefaNaFila.Situacao.DESPACHADA,
    ).values_list("plano", flat=True)
    for plano in em_voo:
        contagem[classe_do_plano(plano)] += 1
    return contagem


def _publicar(tarefa: TarefaNaFila) -> None:
    """Manda a mensagem ao Celery. Falha aqui devolve a linha à fila.

    **Não engolir o erro é o ponto.** Se o broker está fora, a linha marcada
    `despachada` prometeria uma cadeira ocupada por um trabalho que nunca vai
    rodar — e a frota encolheria em silêncio a cada tentativa. Voltando para
    `aguardando`, o próximo despacho tenta de novo.
    """
    from celery import current_app

    try:
        current_app.send_task(tarefa.tarefa, args=list(tarefa.argumentos))
    except Exception:
        logger.exception("frota: falha ao publicar %s; devolvendo à fila", tarefa.chave)
        TarefaNaFila.objects.filter(pk=tarefa.pk).update(
            situacao=TarefaNaFila.Situacao.AGUARDANDO, despachada_em=None,
        )


# ---------------------------------------------------------------------------
# Devolver a cadeira
# ---------------------------------------------------------------------------
def concluir(chave: str, frota: str = FROTA_CONVERSAO) -> None:
    """O trabalho acabou (bem ou mal): libera a cadeira e chama o próximo."""
    TarefaNaFila.objects.filter(
        frota=frota, chave=chave, situacao=TarefaNaFila.Situacao.DESPACHADA,
    ).update(situacao=TarefaNaFila.Situacao.CONCLUIDA, concluida_em=timezone.now())
    despachar(frota)


def recolocar(chave: str, frota: str = FROTA_CONVERSAO) -> TarefaNaFila | None:
    """PRA.11 — o trabalho passou do turno: volta ao fim da fila, um degrau acima.

    **É a metade do item 23 que só existe com checkpoint.** Devolver à fila um
    trabalho que recomeçaria do zero gastaria mais CPU total do que deixá-lo
    terminar — foi por isso que a preempção ficou registrada como impossível até
    aqui. Com a conversão gravando folha a folha, cada volta preserva o que ficou
    pronto, e a recolocação passa a ser o que o dono descreveu: *"continua assim
    até terminar"*.

    **Volta ao fim, mas envelhecendo.** `criada_em` é reescrita — o job vai para
    trás de todo mundo que esperava — e a `prioridade` desce
    `FROTA_DEGRAU_POR_VOLTA`. Sem o degrau, um arquivo pesado atrás de um fluxo
    contínuo de arquivos pequenos nunca chegaria ao fim; com ele, ele cede a vez
    e converge. Os patamares de `PARTIDA` são largos o bastante para o
    envelhecimento não fazer um free ultrapassar um premium — a política continua
    de pé enquanto o arquivo avança.
    """
    tarefa = TarefaNaFila.objects.filter(
        frota=frota, chave=chave, situacao=TarefaNaFila.Situacao.DESPACHADA,
    ).first()
    if tarefa is None:
        return None
    return _devolver_a_fila(tarefa, frota)


def _devolver_a_fila(tarefa: TarefaNaFila, frota: str) -> TarefaNaFila:
    """A mecânica de voltar para o fim, usada pela recolocação e pela órfã.

    Uma função e não duas cópias porque as duas situações querem a **mesma**
    coisa: o job já ocupou uma cadeira e volta atrás de quem ainda não ocupou
    nenhuma. Para a órfã isso tem um efeito extra e desejado — um job que derruba
    o worker toda vez que roda não consegue monopolizar a frota morrendo em
    série, porque cada morte o manda para trás.
    """
    tarefa.situacao = TarefaNaFila.Situacao.AGUARDANDO
    tarefa.voltas += 1
    tarefa.prioridade = _prioridade(classe_do_plano(tarefa.plano), tarefa.voltas)
    tarefa.criada_em = timezone.now()
    tarefa.despachada_em = None
    tarefa.save(update_fields=[
        "situacao", "voltas", "prioridade", "criada_em", "despachada_em",
    ])
    despachar(frota)
    return tarefa


def cancelar(chave: str, frota: str = FROTA_CONVERSAO) -> None:
    """Sai da fila sem executar — a revisão foi apagada, o lote foi desfeito."""
    TarefaNaFila.objects.filter(
        frota=frota, chave=chave,
        situacao__in=[TarefaNaFila.Situacao.AGUARDANDO, TarefaNaFila.Situacao.DESPACHADA],
    ).update(situacao=TarefaNaFila.Situacao.CANCELADA, concluida_em=timezone.now())
    despachar(frota)


def liberar_orfas(frota: str = FROTA_CONVERSAO) -> int:
    """Devolve à fila as cadeiras presas por um worker que morreu sem avisar.

    **É a rede do desenho sem processo despachante próprio.** Todo job que ocupa
    cadeira termina avisando — `concluir` no caminho feliz, e o `DLQTask` garante
    o aviso até no caminho de falha. O que nenhum aviso cobre é a morte violenta:
    OOM do cgroup, container derrubado, máquina reiniciada. Sem esta varredura,
    cada morte dessas reduziria a frota em uma vaga **para sempre**, e o sintoma
    seria uma fila que anda cada vez mais devagar sem nada nos logs.
    """
    limite = timezone.now() - timedelta(minutes=MINUTOS_ATE_ORFA)
    orfas = list(
        TarefaNaFila.objects.filter(
            frota=frota, situacao=TarefaNaFila.Situacao.DESPACHADA,
            despachada_em__lt=limite,
        )
    )
    if not orfas:
        return 0
    # Pelo caminho da recolocação, e **não** de volta ao lugar de origem: a órfã
    # já teve a sua vez na cadeira. Devolvê-la ao topo faria um job que mata o
    # worker toda vez monopolizar a frota morrendo em série — cada morte lhe
    # daria a vaga de novo, e ninguém atrás dela andaria nunca.
    for orfa in orfas:
        _devolver_a_fila(orfa, frota)
    logger.warning(
        "frota: %s cadeira(s) presas há mais de %s min devolvidas à fila: %s",
        len(orfas), MINUTOS_ATE_ORFA, [o.chave for o in orfas],
    )
    return len(orfas)


# ---------------------------------------------------------------------------
# Passar na frente — só dentro da própria empresa
# ---------------------------------------------------------------------------
def priorizar(tarefa: TarefaNaFila, *, user) -> TarefaNaFila:
    """Sobe este trabalho à frente dos **da mesma empresa**. Nunca dos outros.

    *(decisão do dono, 16/08/2026.)* O administrador do tenant reordena a própria
    fila — "esta prancha é urgente, sobe ela" — e a ordem entre empresas do mesmo
    plano continua sendo a de chegada. Deixar furar a fila do plano inteiro seria
    dar a um cliente o poder de atrasar outro que não fez nada; e como nada
    impediria todos os administradores de marcarem tudo como urgente, o efeito
    líquido seria zero prioridade e uma fila imprevisível.

    **A mecânica é uma PERMUTAÇÃO de lugares, e a primeira versão desta função
    errava exatamente aqui.** Ela dava ao job urgente a `criada_em` do primeiro
    da empresa menos um instante — e isso o fazia saltar por cima de qualquer
    tenant que estivesse *entremeado*. Com a fila `[acme-1, beta-1, acme-2]`,
    subir a `acme-2` empurrava a `beta-1` de segunda para terceira: um cliente
    que não fez nada atrasava, que é literalmente o que a decisão proíbe. O teste
    pegou (`4 != 3`).

    O que a função faz agora: pega os **lugares que esta empresa já ocupa** na
    ordem global, reordena só a lista dela e devolve as mesmas chaves de ordenação
    aos seus jobs, na ordem nova. Os lugares são os mesmos; muda quem está em
    cada um. Todo mundo de fora fica onde estava, no lugar exato — não "quase".
    """
    if tarefa.situacao != TarefaNaFila.Situacao.AGUARDANDO:
        return tarefa

    da_empresa = list(
        TarefaNaFila.objects.filter(
            frota=tarefa.frota, tenant_id=tarefa.tenant_id,
            situacao=TarefaNaFila.Situacao.AGUARDANDO,
        ).order_by("prioridade", "criada_em")
    )
    if len(da_empresa) < 2:
        return tarefa

    # Os lugares (chaves de ordenação) que a empresa ocupa, na ordem em que
    # aparecem na fila global. Eles não mudam — só quem os ocupa.
    lugares = [(t.prioridade, t.criada_em) for t in da_empresa]
    nova_ordem = [t for t in da_empresa if t.pk == tarefa.pk]
    nova_ordem += [t for t in da_empresa if t.pk != tarefa.pk]

    for ocupante, (prioridade, criada_em) in zip(nova_ordem, lugares):
        ocupante.prioridade = prioridade
        ocupante.criada_em = criada_em
    TarefaNaFila.objects.bulk_update(nova_ordem, ["prioridade", "criada_em"])

    tarefa.urgente_por = user if getattr(user, "pk", None) else None
    tarefa.urgente_em = timezone.now()
    tarefa.save(update_fields=["urgente_por", "urgente_em"])
    tarefa.refresh_from_db()
    return tarefa


def situacao_da_fila(tarefa: TarefaNaFila) -> dict:
    """O que a tela mostra a quem espera — e o que ela precisa para perguntar.

    Inclui `pode_priorizar` e `na_frente_da_empresa` porque o aviso que o dono
    pediu (*"faça um aviso do que está acontecendo e se ele quer passar"*) tem de
    dizer **o que vai acontecer**: subir este arquivo atrasa os outros N da sua
    empresa, e nenhum de fora. Um botão "passar na frente" sem esse número seria
    o mesmo botão que todo mundo aperta sempre.
    """
    a_frente = posicao(tarefa)
    da_empresa = (
        TarefaNaFila.objects.filter(
            frota=tarefa.frota, tenant_id=tarefa.tenant_id,
            situacao=TarefaNaFila.Situacao.AGUARDANDO,
        )
        .exclude(pk=tarefa.pk)
        .filter(_antes_de(tarefa))
        .count()
    )
    return {
        "situacao": tarefa.situacao,
        "posicao": a_frente,
        "voltas": tarefa.voltas,
        "na_frente_da_empresa": da_empresa,
        "pode_priorizar": (
            tarefa.situacao == TarefaNaFila.Situacao.AGUARDANDO and da_empresa > 0
        ),
        "priorizada_em": tarefa.urgente_em,
    }
