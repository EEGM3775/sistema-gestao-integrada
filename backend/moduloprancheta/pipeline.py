# backend/moduloprancheta/pipeline.py
"""PRA.1 — o pipeline de conversão: planejar, agendar, executar.

Três responsabilidades, e a fronteira entre elas é o que mantém isto testável:

- **planejar** (em `motores/`) — que derivadas este formato rende neste plano;
- **agendar** (aqui) — criar as linhas e enfileirar, com idempotência;
- **executar** (aqui) — rodar o adaptador e gravar o resultado ou o erro.

**A idempotência é por `hash` + versão do motor**, e é o que a planta §11 pede
pelo nome. O hash da revisão é imutável por construção (o arquivo é write-once,
planta §9), então o que de fato varia é a versão do motor: subir o `ezdxf` muda
`ezdxf-1.1.4` para `ezdxf-1.2.0` e todo o acervo convertido passa a estar
desatualizado **por comparação**, sem flag manual e sem migration de dados. Uma
derivada `PRONTO` cuja dupla ainda bate é pulada; qualquer outra roda.

**O erro é dado, não exceção engolida.** Toda falha de motor vira estado +
motivo + detalhe na linha, e aparece na tela. A única coisa que sobe para o
Celery é o que uma segunda tentativa pode consertar (`retentavel`) — repetir 3×
uma conversão que vai falhar igual só encheria a DLQ de limite de plano.
"""
from __future__ import annotations

import inspect
import logging
import os
import tempfile
import time
from functools import lru_cache

from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from nucleo.consumo import medir

from .limites import orcamento_de_conversao
from .motores.base import orcamento_de_subprocesso
from .models import DerivadaProjeto, DesenhoProjeto, RevisaoDocumento
from .motores import ErroDeConversao, MotorIndisponivel, MotorInsuficiente, adaptador_de, planejar
from .motores.base import RecursoExcedido, Retomada

logger = logging.getLogger(__name__)

#: Tiers assumidos quando ninguém informa (job de manutenção, reprocessamento em
#: massa). Só o livre: escalar para um motor pago sem o plano na mão seria gastar
#: COGS por omissão — o oposto da regra de ouro do `monetizacao.md`.
TIERS_PADRAO = ("livre",)

#: Quanto duas envolventes precisam se sobrepor (interseção sobre união) para
#: serem lidas como **o mesmo desenho** em revisões diferentes, e portanto para o
#: nome dado por alguém atravessar da R01 para a R02.
#:
#: Meio é folgado o bastante para o projetista ter mexido no desenho — acrescentar
#: um bloco ou apagar um detalhe muda a envolvente — e apertado o bastante para
#: duas folhas vizinhas nunca se confundirem: um nome no desenho errado é pior
#: que nome nenhum, porque ninguém vai conferir.
SOBREPOSICAO_MINIMA = 0.5


def agendar(revisao: RevisaoDocumento, *, tiers=TIERS_PADRAO, teto_snap: int | None = 0,
            forcar: bool = False, plano: str = "", user=None) -> list[int]:
    """Cria/atualiza as derivadas desta revisão e enfileira o que precisa rodar.

    Devolve os ids agendados. Chamado no `on_commit` do upload: antes do commit a
    linha da revisão ainda não existe para o worker, e o job pegaria o arquivo
    inexistente — a versão clássica do erro de agendar dentro da transação.

    **Um par `(tipo, motor)` pode render várias linhas**, uma por desenho, e por
    isso o agendamento passou a raciocinar sobre o *grupo* em vez de sobre a
    linha: quantas folhas o arquivo tem só se sabe depois de abrir o arquivo, que
    é justamente o que o worker vai fazer. Enfileira-se a linha mais antiga do
    grupo, e é `executar` quem abre o leque — assim o `hash` + versão de motor
    continua decidindo sozinho se há trabalho, sem uma segunda fila de controle.
    """
    from .tasks import converter_derivada  # tardio: evita ciclo tasks↔pipeline

    planejadas = planejar(revisao.formato, tiers)
    agendados: list[int] = []

    for tipo, codigo_motor in planejadas:
        grupo = list(
            DerivadaProjeto.objects.filter(revisao=revisao, tipo=tipo, motor=codigo_motor)
            .order_by("derivada_id")
        )
        if not grupo:
            grupo = [DerivadaProjeto.objects.create(
                revisao=revisao, tipo=tipo, motor=codigo_motor,
                tenant_id=revisao.tenant_id,
            )]
        if not forcar and all(_esta_atual(d, revisao) for d in grupo):
            continue

        DerivadaProjeto.objects.filter(pk__in=[d.pk for d in grupo]).update(
            estado=DerivadaProjeto.Estado.PENDENTE,
            erro_motivo="", erro_detalhe="", concluido_em=None,
        )
        cabeca = grupo[0]
        agendados.append(cabeca.pk)
        # **`frota.enfileirar` e não `.delay()`** (D98). A diferença é a promessa
        # inteira do porteiro: um `.delay()` publica e esquece — não sabe dizer
        # quem está na frente, não reserva cadeira para plano nenhum e não tem
        # onde um job recolocado voltar. Quem publica agora é o despachante, que
        # é chamado logo depois de a linha entrar.
        transaction.on_commit(
            lambda pk=cabeca.pk: _entrar_na_fila(
                revisao, pk, tiers, teto_snap, plano=plano, user=user)
        )

    return agendados


def chave_na_fila(derivada_id) -> str:
    """A identidade do TRABALHO na fila da frota, não da linha.

    É o que torna o `enfileirar` idempotente: o upload reenviado, o
    `reprocessar` clicado duas vezes e o retry do Celery pedem o mesmo trabalho,
    e três lugares na fila para o mesmo arquivo seriam três conversões idênticas
    disputando a mesma cadeira.
    """
    return f"prancheta.derivada:{derivada_id}"


def _entrar_na_fila(revisao, derivada_id, tiers, teto_snap, *, plano="", user=None) -> None:
    """Põe a conversão na fila da frota e chama o despachante.

    **O plano é congelado aqui**, e é a mesma razão de `tiers` viajarem como
    argumento da task: o despachante roda sem usuário e o worker sem token.
    Resolvê-lo na hora de despachar exigiria uma consulta ao IAM por job, para
    responder algo que quem enfileirou já tinha na mão.

    Plano vazio cai em `comum`, que é a classe do meio — nunca em `premium`. É a
    régua de sempre: na dúvida, o benefício não é presumido. Acontece de verdade
    no reprocessamento em massa e no job de manutenção, que não têm usuário.
    """
    from nucleo import frota

    frota.enfileirar(
        tenant_id=revisao.tenant_id,
        chave=chave_na_fila(derivada_id),
        tarefa="moduloprancheta.converter_derivada",
        argumentos=[derivada_id, str(revisao.tenant_id), list(tiers), teto_snap],
        plano=plano or getattr(user, "iam_plano", "") or "",
        user=user,
    )


def _esta_atual(derivada: DerivadaProjeto, revisao: RevisaoDocumento) -> bool:
    """Pronta, sobre este mesmo arquivo e com a versão de motor que roda hoje."""
    if derivada.estado != DerivadaProjeto.Estado.PRONTO:
        return False
    if derivada.hash_origem != revisao.hash_sha256:
        return False
    adaptador = adaptador_de(derivada.motor)
    return bool(adaptador) and derivada.motor_versao == adaptador.versao()


def executar(derivada: DerivadaProjeto, *, tiers=TIERS_PADRAO,
             teto_snap: int | None = 0) -> DerivadaProjeto:
    """Roda o motor desta derivada e grava o resultado — ou o erro.

    Retorna a derivada atualizada. Levanta `ErroDeConversao` **apenas** quando a
    falha é retentável, para o Celery reagendar; o estado já foi persistido antes
    de subir, então a tela nunca vê uma linha parada em `convertendo`.
    """
    revisao = derivada.revisao
    adaptador = adaptador_de(derivada.motor)
    if adaptador is None:
        return _falhar(derivada, MotorIndisponivel(
            f"O motor '{derivada.motor}' não tem adaptador nesta versão do sistema."
        ))

    # **Numa passada de RETOMADA a linha não volta a "convertendo"** (PRA.11).
    # Ela é a folha 1, gravada e abrindo desde a primeira passada; rebaixá-la a
    # "convertendo" faria a tela esconder um desenho que está pronto no disco —
    # e, se a conversão terminasse com as folhas novas em linhas novas, ela
    # ficaria presa em "convertendo" para sempre, que foi o defeito que o teste
    # pegou. Quem conta o andamento do ARQUIVO é `retomada_restam`, não o estado
    # de uma folha.
    retomando = bool(derivada.retomada_restam)
    if not retomando:
        _marcar(derivada, DerivadaProjeto.Estado.LENDO)
    try:
        caminho, temporario = _materializar(revisao)
    except OSError as exc:
        return _falhar(derivada, MotorIndisponivel(f"Arquivo de origem ilegível: {exc}"))

    if not retomando:
        _marcar(derivada, DerivadaProjeto.Estado.CONVERTENDO,
                motor_versao=adaptador.versao())
    # **O custo é medido AQUI, e é o custo deste arquivo.** A janela abraça só a
    # escada — materializar e gravar são custos nossos, previsíveis e iguais para
    # todo mundo; o que varia por desenho é o motor. Ela fecha no `finally` do
    # `medir`, então o número existe também no caminho de erro, que é justamente
    # onde ele é mais necessário: `recurso_excedido` sem quanto custou é um
    # veredito sem prova. Ver [nucleo/consumo.py](../nucleo/consumo.py) para as
    # três medições que já mediram outra coisa (D76, D78, D82).
    # O plano que pagou por esta conversão, congelado no enfileiramento. Fora da
    # fila não há linha e o orçamento cai no padrão — que é o de sempre (D101).
    tarefa = _tarefa_desta_derivada(derivada)
    plano = getattr(tarefa, "plano", "") or ""
    custo: dict = {}
    try:
        with medir() as custo:
            saida = _rodar_a_escada(adaptador, caminho, derivada=derivada, revisao=revisao,
                                    teto_snap=teto_snap, plano=plano)
    except ErroDeConversao as exc:
        derivada = _falhar(derivada, _traduzir(exc, tiers), custo=custo)
        if exc.retentavel:
            raise
        return derivada
    except SoftTimeLimitExceeded as exc:
        # O relógio do CELERY chegou antes do nosso (`limites.teto_de_relogio`).
        # Acontece de verdade quando o motor está preso dentro de uma extensão C,
        # onde o SIGALRM não é entregue entre bytecodes. Sem este ramo a exceção
        # cairia no `except Exception` abaixo e viraria `falha_motor` — "o motor
        # quebrou" —, quando o que houve foi o nosso teto agindo. D57.
        return _falhar(derivada, RecursoExcedido(
            "A conversão passou do tempo máximo de processamento e foi "
            "interrompida. O arquivo continua disponível para download.",
            teto="relogio_celery",
        ), custo=custo)
    except Exception as exc:  # motor pode estourar de formas que não previmos
        logger.exception("prancheta: motor %s quebrou na derivada %s", derivada.motor, derivada.pk)
        from .motores import FalhaMotor

        return _falhar(derivada, FalhaMotor(str(exc)[:400]), custo=custo)
    finally:
        if temporario:
            _apagar(caminho)

    if not saida.partes:
        # Miniatura de PDF, modelo 3D: uma folha só, e nenhum desenho separável.
        pronta = _gravar(
            derivada, revisao, adaptador, saida.conteudo, saida.extensao, saida.detalhe,
            custo=custo,
        )
        _liberar_cadeira(pronta)
        return pronta

    desenhos = _sincronizar_desenhos(revisao, saida.partes)
    grupo = {
        d.desenho_id: d for d in
        DerivadaProjeto.objects.filter(
            revisao=revisao, tipo=derivada.tipo, motor=derivada.motor,
        )
    }
    principal = derivada
    for parte, desenho in zip(saida.partes, desenhos):
        alvo = grupo.get(desenho.pk)
        if alvo is None:
            # A linha que veio da fila ainda não tem dono: ela vira a do primeiro
            # desenho, em vez de virar lixo. Reaproveitar em vez de criar+apagar é
            # o que mantém o id estável para quem já tinha a prancha aberta.
            alvo = grupo.pop(None, None) or DerivadaProjeto(
                revisao=revisao, tipo=derivada.tipo, motor=derivada.motor,
                tenant_id=revisao.tenant_id,
            )
            alvo.desenho = desenho
        # **O custo vai só na folha #1, e isso é para a soma fechar.** Uma
        # conversão produz N folhas de uma passada só; repetir o mesmo custo em
        # cada linha faria qualquer relatório que somasse `custo` multiplicar a
        # conta pelo número de folhas — que é a forma exata do erro que este
        # medidor existe para não cometer.
        _gravar(
            alvo, revisao, adaptador, parte.conteudo, saida.extensao, parte.detalhe,
            custo=custo if parte.ordem == 1 else None, parte=parte,
        )
        _publicar_escala(desenho, parte.detalhe)
        if parte.ordem == 1:
            principal = alvo

    if saida.retomada is not None:
        # **A passada acabou, o arquivo não** (PRA.11). As folhas desta rodada já
        # estão gravadas acima — a prancha abre pelo que há —, e o que falta volta
        # ao fim da fila. `_remover_orfas` NÃO roda: ele apaga o que esta conversão
        # não produziu, e numa passada parcial "não produziu ainda" e "não produz
        # mais" são indistinguíveis. Apagar aqui destruiria, a cada volta, as
        # folhas que a volta anterior acabou de gravar.
        return _recolocar(derivada, saida.retomada, custo=custo)

    _marcar_progresso(derivada, restam=0)
    # A linha da fila volta a `pronto` quando o ARQUIVO termina. Ela pode ter
    # ficado em `retomando` desde a passada anterior sem receber folha nesta —
    # as novas nasceram em linhas próprias — e sem isto ficaria assim para
    # sempre, com um SVG perfeitamente aberto no disco e a tela dizendo que
    # ainda está na fila.
    DerivadaProjeto.objects.filter(
        revisao=revisao, tipo=derivada.tipo, motor=derivada.motor,
        estado=DerivadaProjeto.Estado.RETOMANDO,
    ).exclude(arquivo="").update(
        estado=DerivadaProjeto.Estado.PRONTO, concluido_em=timezone.now(),
    )
    _fechar_censo(revisao, derivada, saida.partes)
    # `total` = a maior `ordem` que este arquivo rendeu, somando TODAS as
    # passadas. Numa conversão de passada única é o tamanho de `desenhos`, e o
    # comportamento não muda; numa retomada é o que impede a última passada de
    # apagar as folhas das anteriores.
    _remover_orfas(
        revisao, derivada, desenhos,
        total=max((p.ordem for p in saida.partes), default=0),
    )
    _liberar_cadeira(derivada)
    return principal


def _recolocar(derivada, marcador, *, custo: dict) -> DerivadaProjeto:
    """Grava o progresso e devolve o arquivo ao fim da fila — ou desiste.

    **A desistência é por tempo ACUMULADO, não por número de voltas** (decisão do
    dono, 16/08/2026). Contar voltas mediria a nossa política e não o custo: um
    arquivo que faz trinta folhas por passada e outro que faz uma gastariam o
    mesmo "orçamento" tendo custado dez vezes diferente. O que a máquina paga é
    segundo de CPU, e é isso que se soma.

    Desistir **preserva as folhas já convertidas**, e é o que separa este erro do
    de antes: a prancha abre pelo que deu, a fila do cockpit mostra o motivo e a
    frase diz quantas faltaram. É a mesma degradação honesta do resto do módulo —
    nunca a folha fabricada, nunca a tela em branco sem explicação.
    """
    gastos = (derivada.retomada_segundos or 0.0) + float((custo or {}).get("segundos", 0) or 0)
    teto = int(getattr(settings, "PRANCHETA_CONVERSAO_TOTAL_SEGUNDOS", 0) or 0)

    _marcar_progresso(
        derivada,
        grupos=marcador.grupos_feitos,
        desenhos=marcador.desenhos_feitos,
        restam=marcador.restam,
        vazios=marcador.vazios_feitos,
        registros_vazios=marcador.registros_vazios_feitos,
        segundos=gastos,
    )

    if teto and gastos >= teto:
        derivada.refresh_from_db()
        return _falhar(derivada, RecursoExcedido(
            f"A conversão passou de {int(gastos)}s de processamento somados e foi "
            f"encerrada com {marcador.desenhos_feitos} folha(s) prontas — faltaram "
            f"{marcador.restam}. As que ficaram continuam abrindo, e o arquivo "
            "original segue disponível para download.",
            teto="relogio_acumulado", segundos=int(gastos),
        ), custo=custo)

    DerivadaProjeto.objects.filter(pk=derivada.pk).update(
        estado=DerivadaProjeto.Estado.RETOMANDO,
    )
    from nucleo import frota

    frota.recolocar(chave_na_fila(derivada.pk))
    derivada.refresh_from_db()
    return derivada


def _marcar_progresso(derivada, *, grupos=None, desenhos=None, restam=0,
                      vazios=None, registros_vazios=None, segundos=None) -> None:
    """Persiste onde a conversão parou. `UPDATE` direto, e não `save()`.

    A linha em memória já foi reaproveitada como a da folha 1 lá em cima (o
    `_gravar` a salvou com arquivo, estado e memória); um `save()` daqui
    reescreveria aqueles campos com o que estava em memória antes. O `UPDATE`
    toca só o que é progresso.
    """
    campos = {"retomada_restam": restam}
    if grupos is not None:
        campos["retomada_grupos"] = grupos
    if desenhos is not None:
        campos["retomada_desenhos"] = desenhos
    if vazios is not None:
        campos["retomada_vazios"] = vazios
    if registros_vazios is not None:
        campos["retomada_registros_vazios"] = registros_vazios
    if segundos is not None:
        campos["retomada_segundos"] = segundos
    DerivadaProjeto.objects.filter(pk=derivada.pk).update(**campos)


def _fechar_censo(revisao, derivada, partes) -> None:
    """Reescreve `desenhos` nas folhas das passadas anteriores (PRA.11).

    Cada passada só sabe quantas folhas viu até ali, e grava esse número na
    memória de conversão de cada folha que emitiu. A frase da tela — "este
    arquivo traz N desenhos" — sairia então **menor** nas folhas antigas: quem
    abrisse a folha 1 leria "12 desenhos" num arquivo de 40. A passada que fecha
    é a única que conhece o total, e é ela que acerta as outras.

    Sem efeito na conversão de passada única, que é o caso comum: ali o número já
    nasce certo e o `UPDATE` não encontra nada divergente.
    """
    if not partes:
        return
    total = (partes[-1].detalhe or {}).get("desenhos")
    if not total:
        return
    for linha in DerivadaProjeto.objects.filter(
        revisao=revisao, tipo=derivada.tipo, motor=derivada.motor,
    ):
        if (linha.memoria or {}).get("desenhos") == total:
            continue
        linha.memoria = {**(linha.memoria or {}), "desenhos": total}
        linha.save(update_fields=["memoria"])


def _liberar_cadeira(derivada) -> None:
    """Devolve a cadeira da frota e chama o próximo (D98).

    Roda no fim do caminho feliz **e** no de erro (`_falhar`), porque cadeira
    presa por job que falhou é frota que encolhe em silêncio — o defeito que a
    `frota.liberar_orfas` existe para varrer e que aqui é barato evitar.
    """
    try:
        from nucleo import frota

        frota.concluir(chave_na_fila(derivada.pk))
    except Exception:  # pragma: no cover — a fila não pode derrubar a conversão
        logger.exception("prancheta: falha ao liberar a cadeira de %s", derivada.pk)


def _rodar_a_escada(adaptador, caminho: str, *, derivada, revisao, teto_snap: int | None = 0,
                    plano: str = ""):
    """Converte fiel; se não couber no orçamento, desce um degrau e tenta de novo.

    **O orçamento de recurso envolve o motor, e só ele** (D57): materializar o
    arquivo e gravar a saída são custos nossos e previsíveis; o que a medição de
    06/08 mostrou explodir — 62 GB de RAM — é a expansão de geometria lá dentro.
    O estouro vira `RecursoExcedido`, que é estado com motivo; sem isto, o kernel
    mataria o worker e a derivada ficaria presa em `convertendo` para sempre.

    **A primeira tentativa é sempre a fiel, e é o que garante que nada regrida.**
    Nenhuma prancha que hoje converte bem muda de aparência: a degradação não é
    escolhida por palpite sobre o arquivo — nenhum limiar, nenhuma heurística de
    "este parece pesado" —, é escolhida pelo **orçamento tendo sido estourado**.
    Só desce a escada quem provou não caber.

    **Cada degrau roda com orçamento novo, e é por isso que a escada mora aqui.**
    Dentro do motor, a segunda passada herdaria o que a primeira já consumiu do
    relógio e do teto de memória, e começaria quase sem folga — degradaria a
    prancha e estouraria assim mesmo, que é o pior dos dois mundos.

    **Limite honesto do mecanismo:** a segunda passada roda no mesmo processo,
    onde o pico da primeira pode ter deixado o alocador fragmentado. O
    `RLIMIT_AS` mede espaço de endereçamento, não memória viva, então uma
    fragmentação ruim pode fazer o segundo degrau falhar por causa do primeiro.
    Quando isso acontecer o resultado ainda é honesto (`recurso_excedido`), e a
    rede que o cobre é o `--max-memory-per-child`, que recicla o processo.
    """
    tentativas = ("", *getattr(adaptador, "economias", ()))
    # **Índice explícito, e não `for`, porque a escada agora sabe SALTAR.** Um
    # estouro pode declarar que só um degrau específico o resolve; percorrer os
    # do meio seria repetir trabalho pesado para falhar igual.
    indice = 0
    ja_tentados: set[str] = set()
    while indice < len(tentativas):
        economia = tentativas[indice]
        ja_tentados.add(economia)
        try:
            # **Os três orçamentos desta passada, e cada um vem de um lugar.** A
            # RAM sai do plano (D101) — é o que o cliente compra; o relógio duro
            # sai do que resta do acumulado deste arquivo, porque desde 16/08 uma
            # passada pode passar do turno de propósito quando não há fila; e o
            # do subprocesso viaja por contexto, porque ele é consultado quatro
            # níveis abaixo, dentro de `dwg.py`.
            with orcamento_de_conversao(
                memoria_mb=_memoria_do_plano(plano),
                segundos=_relogio_da_passada(adaptador, derivada),
            ), orcamento_de_subprocesso(_memoria_do_subprocesso_do_plano(plano)):
                return adaptador.converter(
                    caminho, formato=revisao.formato, tipo=derivada.tipo,
                    economia=economia,
                    **_extras_do_motor(adaptador, teto_snap),
                    # A retomada só vale para a conversão **fiel** (PRA.11). Uma
                    # passada que desceu a escada desenha diferente da anterior, e
                    # continuar da folha 12 com outro nível de hachura daria uma
                    # prancha com duas aparências dentro do mesmo arquivo. Quando
                    # a escada entra, o arquivo recomeça inteiro — que é o que ela
                    # sempre fez, e continua certo.
                    **(_turno_do_motor(adaptador, derivada) if not economia else {}),
                )
        except RecursoExcedido as exc:
            # **Nem todo estouro desce um degrau de cada vez** (D78). As economias
            # de um motor podem agir num estágio que o arquivo nem alcançou —
            # quando quem estoura é o subprocesso de decodificação, economizar no
            # desenho repete a decodificação inteira (9 s a 110 s) para falhar
            # igual. Quem levanta a exceção sabe disso e declara:
            #
            # - `degradavel=False` → não há degrau que ajude, a falha fica de pé;
            # - `pular_para="…"` → só um degrau específico pode ajudar; vá a ele
            #   direto, sem pagar os do meio.
            if not exc.extra.get("degradavel", True):
                raise
            alvo = exc.extra.get("pular_para")
            if alvo:
                # `ja_tentados` fecha o laço: sem ele, um degrau que estourasse
                # pedindo a si mesmo repetiria para sempre.
                if alvo in ja_tentados or alvo not in tentativas:
                    raise
                indice = tentativas.index(alvo)
            elif indice == len(tentativas) - 1:
                raise
            else:
                indice += 1
            logger.info(
                "prancheta: derivada %s não coube no orçamento; tentando com '%s'",
                derivada.pk, tentativas[indice],
            )
    raise AssertionError("escada de conversão sem tentativa nenhuma")  # pragma: no cover


@lru_cache(maxsize=64)
def _aceita_teto_snap(classe) -> bool:
    """Este motor conhece o `teto_snap`?

    **Perguntar é mais barato que quebrar.** `teto_snap` entrou no contrato do
    adaptador depois que já havia cinco motores; um que não tenha sido atualizado
    — porta de um plugin, motor experimental, o falso de um teste — levanta
    `TypeError` no `converter()`, e o `except Exception` do `executar` traduz
    isso para `falha_motor`. O cliente lê "o motor quebrou ao abrir seu arquivo"
    quando o que houve foi o servidor oferecendo um recurso opcional a quem não o
    conhece. Nenhum diagnóstico levaria a lugar nenhum: a prancha abre sozinha.

    `lru_cache` pela CLASSE porque a resposta não muda em execução, e a
    introspecção é cara demais para o caminho de cada conversão.
    """
    try:
        parametros = inspect.signature(classe.converter).parameters
    except (TypeError, ValueError):
        return False  # builtin, C, ou algo que não se deixa inspecionar
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parametros.values()):
        return True  # aceita `**kwargs`: engole o que não conhece
    return "teto_snap" in parametros


def _extras_do_motor(adaptador, teto_snap) -> dict:
    """O que passar a mais para este motor — nada, se ele não souber o que é."""
    return {"teto_snap": teto_snap} if _aceita_teto_snap(type(adaptador)) else {}


@lru_cache(maxsize=64)
def _aceita_retomada(classe) -> bool:
    """Este motor conhece `retomada`/`prazo`? Mesma cautela do `teto_snap`.

    Motor de terceiro, motor experimental e o falso de um teste ficaram para trás
    quando a PRA.11 acrescentou dois parâmetros ao contrato, e oferecê-los a quem
    não os conhece levantaria `TypeError` — que o `except Exception` do `executar`
    traduziria para "o motor quebrou ao abrir seu arquivo". A régua é a do D57:
    recurso opcional não pode virar defeito de quem não o pediu.
    """
    try:
        parametros = inspect.signature(classe.converter).parameters
    except (TypeError, ValueError):
        return False
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parametros.values()):
        return True
    return "retomada" in parametros and "prazo" in parametros


def _tarefa_desta_derivada(derivada):
    """A linha da frota que autorizou esta conversão — `None` fora da fila.

    Ela é a fonte de duas coisas que a derivada não sabe: **qual plano** pagou
    por esta passada (congelado no enfileiramento, D98) e **quem está esperando**
    para receber a vez. Uma consulta só, reaproveitada pelos dois.

    Conversão disparada fora da fila (comando de bancada, teste, `forcar`) não tem
    linha, e aí tudo cai no padrão — que é o comportamento de sempre.
    """
    try:
        from nucleo.frota import TarefaNaFila

        return TarefaNaFila.objects.filter(chave=chave_na_fila(derivada.pk)).first()
    except Exception:  # pragma: no cover — a fila não pode derrubar a conversão
        logger.exception("prancheta: falha ao ler a tarefa de %s na frota", derivada.pk)
        return None


def _memoria_do_plano(plano: str) -> int | None:
    """O teto de RAM da conversão neste plano — `None` para usar o padrão (D101)."""
    from payment.planos import PRANCHETA_CONVERSAO_MEMORIA_MB_POR_PLANO

    return PRANCHETA_CONVERSAO_MEMORIA_MB_POR_PLANO.get(plano or "")


def _memoria_do_subprocesso_do_plano(plano: str) -> int | None:
    """Idem para o `dwg2dxf`/`dwg2SVG`, que é processo à parte (D101)."""
    from payment.planos import PRANCHETA_SUBPROCESSO_MEMORIA_MB_POR_PLANO

    return PRANCHETA_SUBPROCESSO_MEMORIA_MB_POR_PLANO.get(plano or "")


def _relogio_da_passada(adaptador, derivada) -> int | None:
    """Quantos segundos esta passada pode durar — `None` = o padrão de sempre.

    **Por que ele deixou de ser sempre `PRANCHETA_CONVERSAO_SEGUNDOS`.** Desde que
    o motor só cede a vez quando há fila (16/08/2026), uma passada com a fila
    vazia passa do turno de propósito — e o teto duro de 300 s a mataria em pleno
    trabalho útil, com `recurso_excedido`, destruindo o progresso da passada. Seria
    trocar um desperdício por um estrago.

    A resposta é esticar o teto duro até **o que resta do orçamento acumulado do
    arquivo** (`PRANCHETA_CONVERSAO_TOTAL_SEGUNDOS` menos o que ele já gastou).
    Nada fica sem freio: o arquivo continua tendo exatamente o mesmo orçamento
    total que tinha: o que muda é ele poder gastá-lo de uma vez, quando gastar de
    uma vez não atrapalha ninguém.

    Vale só para quem retoma. Motor indivisível continua com o turno de sempre —
    para ele, passar do teto nunca foi negociável.
    """
    if not getattr(adaptador, "retomavel", False) or not _aceita_retomada(type(adaptador)):
        return None
    turno = int(getattr(settings, "PRANCHETA_CONVERSAO_SEGUNDOS", 0) or 0)
    total = int(getattr(settings, "PRANCHETA_CONVERSAO_TOTAL_SEGUNDOS", 0) or 0)
    if not turno or not total:
        return None
    restante = total - int(derivada.retomada_segundos or 0)
    # Nunca menos que um turno: um arquivo que já queimou quase todo o acumulado
    # ainda merece uma passada inteira para tentar terminar — o freio que o para
    # de vez é o `_recolocar`, que confere o acumulado DEPOIS, com o custo real
    # na mão, e sabe explicar. Cortar aqui daria `recurso_excedido` sem esse
    # relato.
    return max(turno, restante)


def _turno_do_motor(adaptador, derivada) -> dict:
    """O par `retomada`/`prazo` desta passada — vazio para quem não retoma.

    **O prazo é do TURNO, e nasce um pouco antes do teto que mata** (PRA.11): o
    motor precisa de folga para gravar a folha que está emitindo e devolver o
    marcador. Se os dois batessem juntos, o `teto_de_relogio` do `limites.py`
    venceria a corrida e a passada inteira viraria `recurso_excedido` — que é
    exatamente o comportamento que a retomada existe para substituir. Fica em 80%
    porque a folha mediana custa muito menos que isso, e a folha que não couber
    nos 20% restantes não caberia em passada nenhuma.
    """
    if not getattr(adaptador, "retomavel", False) or not _aceita_retomada(type(adaptador)):
        return {}
    turno = int(getattr(settings, "PRANCHETA_CONVERSAO_SEGUNDOS", 0) or 0)
    if not turno:
        return {}
    anterior = None
    if derivada.retomada_restam:
        anterior = Retomada(
            grupos_feitos=derivada.retomada_grupos,
            desenhos_feitos=derivada.retomada_desenhos,
            restam=derivada.retomada_restam,
            vazios_feitos=derivada.retomada_vazios,
            registros_vazios_feitos=derivada.retomada_registros_vazios,
        )
    extra: dict = {"retomada": anterior, "prazo": time.monotonic() + turno * 0.8}
    if _aceita_ceder(type(adaptador)):
        extra["ceder"] = _ha_quem_receba_a_vez(derivada)
    return extra


@lru_cache(maxsize=64)
def _aceita_ceder(classe) -> bool:
    """Este motor sabe perguntar se há fila? Mesma cautela do `teto_snap`.

    `ceder` entrou no contrato depois de `retomada`/`prazo`, então um motor que
    conheça os dois primeiros e não o terceiro é uma combinação possível — e
    oferecer o que ele não conhece levantaria `TypeError`, que o pipeline
    traduziria para "o motor quebrou ao abrir seu arquivo". D57 de novo.
    """
    try:
        parametros = inspect.signature(classe.converter).parameters
    except (TypeError, ValueError):
        return False
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parametros.values()):
        return True
    return "ceder" in parametros


def _ha_quem_receba_a_vez(derivada):
    """A pergunta que o motor faz quando o turno vence: alguém espera por esta vaga?

    Devolve um **callable**, não um booleano, porque a resposta muda durante a
    conversão: a fila pode estar vazia aos 240 s e ter três arquivos aos 300 s. O
    motor pergunta de novo a cada folha, e cede na primeira em que a resposta for
    sim — então o atraso máximo de quem chega é **uma folha**, não uma passada.

    **Erro responde `True`.** Se a consulta à frota falhar, ceder é o
    comportamento conservador: volta-se ao de antes desta mudança, que já era
    correto, em vez de segurar a cadeira por causa de um defeito nosso.
    """
    chave = chave_na_fila(derivada.pk)

    def ha_fila() -> bool:
        try:
            from nucleo import frota

            return frota.ha_espera(chave)
        except Exception:  # pragma: no cover — a fila não pode derrubar a conversão
            logger.exception("prancheta: falha ao consultar a fila para %s", derivada.pk)
            return True

    return ha_fila


def _gravar(
    derivada, revisao, adaptador, conteudo: bytes, extensao: str, detalhe,
    *, custo: dict | None = None, parte=None,
) -> DerivadaProjeto:
    """Persiste o produto da conversão nesta linha."""
    sufixo = f"-d{derivada.desenho_id}" if derivada.desenho_id else ""
    nome = f"rev{revisao.pk}-{derivada.tipo}-{derivada.motor}{sufixo}.{extensao}"
    derivada.arquivo.save(nome, ContentFile(conteudo), save=False)
    _gravar_snap(derivada, parte, nome)
    derivada.estado = DerivadaProjeto.Estado.PRONTO
    derivada.tamanho_bytes = len(conteudo)
    derivada.hash_origem = revisao.hash_sha256
    derivada.motor_versao = adaptador.versao()
    derivada.memoria = {**(detalhe or {}), **({"custo": custo} if custo else {})}
    derivada.erro_motivo = ""
    derivada.erro_detalhe = ""
    derivada.concluido_em = timezone.now()
    derivada.save()
    return derivada


def _gravar_snap(derivada, parte, nome_do_svg: str) -> None:
    """Grava (ou limpa) o índice de snap desta folha.

    **Limpar quando não veio é tão importante quanto gravar quando veio.** Uma
    reconversão pode produzir menos que a anterior — o plano caiu de degrau, o
    desenho mudou, a extração falhou —, e o sidecar antigo sobrevivente ficaria
    apontando para uma geometria que não existe mais. A mira grudaria em traço
    que a prancha não tem, que é pior do que não ter mira.
    """
    anterior = derivada.snap
    octetos = getattr(parte, "snap", None) if parte is not None else None

    if octetos:
        derivada.snap.save(
            f"{nome_do_svg.rsplit('.', 1)[0]}.snap",
            ContentFile(octetos), save=False,
        )
        derivada.snap_pontos = parte.snap_pontos
        derivada.snap_truncado = parte.snap_truncado
    else:
        derivada.snap = None
        derivada.snap_pontos = 0
        derivada.snap_truncado = False

    if anterior and anterior.name and (not octetos or anterior.name != derivada.snap.name):
        # O storage não apaga sozinho quando o campo troca de nome; sem isto,
        # cada reconversão deixaria um sidecar órfão de até 5 MB para trás.
        anterior.storage.delete(anterior.name)


def _sincronizar_desenhos(revisao: RevisaoDocumento, partes) -> list:
    """Casa as folhas que o motor produziu com as linhas de `DesenhoProjeto`.

    Reaproveita a linha de mesma `ordem` quando ela já existe (reconversão),
    porque é ela que carrega o nome que alguém deu e a calibração que alguém
    fez — recriar do zero a cada conversão apagaria os dois em silêncio, que é
    exatamente o que `reprocessar/` não pode fazer.

    **A ordem de quem batiza a folha**, do mais humano para o menos: o nome que
    já está na linha (alguém escreveu na tela) · o herdado da revisão anterior
    (alguém escreveu lá) · o nome da aba de layout, quando o arquivo traz um
    (PRA.1b/D44) · nada, e a tela mostra "Desenho N". O nome da aba entra por
    último entre os escritos porque um `Layout1` genérico não deve apagar o
    "FACHADA LESTE" que alguém digitou na revisão passada.
    """
    existentes = {d.ordem: d for d in revisao.desenhos.all()}
    desenhos = []
    for parte in partes:
        desenho = existentes.get(parte.ordem) or DesenhoProjeto(
            tenant_id=revisao.tenant_id, revisao=revisao, ordem=parte.ordem,
        )
        desenho.caixa = parte.caixa
        # Só sobrescreve quando a conversão mediu: um motor que não rende
        # coordenada (PDF, imagem) não deve apagar a que uma conversão vetorial
        # anterior já tinha gravado para a mesma folha.
        if parte.mundo:
            desenho.mundo = parte.mundo
        desenho.tracos = parte.tracos
        if not desenho.nome:
            _herdar_nome(revisao, desenho)
        if not desenho.nome and parte.nome:
            desenho.nome = parte.nome[:DesenhoProjeto._meta.get_field("nome").max_length]
        desenho.save()
        desenhos.append(desenho)
    return desenhos


def _herdar_nome(revisao: RevisaoDocumento, desenho) -> None:
    """Traz o nome que alguém deu ao mesmo desenho na revisão anterior.

    **A identidade é o lugar no terreno, não a ordem.** O projetista mexe no
    desenho entre a R01 e a R02 — acrescenta um bloco, apaga um detalhe —, e com
    isso a área muda e a ordem pode trocar. O que não muda é onde aquele desenho
    está em coordenada de desenho: é por isso que `caixa` viaja em unidade de
    desenho e a comparação é de sobreposição (interseção sobre união), não de
    índice.

    Sem herança, o projetista que manda revisão toda semana teria de renomear as
    50 folhas a cada envio — e um "Desenho 7" que troca de desenho a cada revisão
    é pior que não ter nome nenhum.

    Silencioso quando não há candidato com sobreposição suficiente: desenho novo
    numa revisão nova **é** desenho novo, e herdar um nome por proximidade vaga
    poria o rótulo errado em cima do desenho errado — o defeito que a fila de
    decisão nunca pegaria, porque nada estaria vazio.
    """
    anterior = (
        RevisaoDocumento.objects
        .filter(documento_id=revisao.documento_id, revisao_id__lt=revisao.pk)
        .order_by("-revisao_id").first()
    )
    if anterior is None:
        return
    melhor, melhor_iou = None, 0.0
    for candidato in anterior.desenhos.exclude(nome=""):
        iou = _sobreposicao(desenho.caixa, candidato.caixa)
        if iou > melhor_iou:
            melhor, melhor_iou = candidato, iou
    if melhor is not None and melhor_iou >= SOBREPOSICAO_MINIMA:
        desenho.nome = melhor.nome
        desenho.herdado_de = melhor


def _sobreposicao(a: dict, b: dict) -> float:
    """Interseção sobre união de duas envolventes. `0.0` quando não se tocam."""
    if not a or not b:
        return 0.0
    try:
        ix = min(a["xmax"], b["xmax"]) - max(a["xmin"], b["xmin"])
        iy = min(a["ymax"], b["ymax"]) - max(a["ymin"], b["ymin"])
    except KeyError:
        return 0.0
    if ix <= 0 or iy <= 0:
        return 0.0
    intersecao = ix * iy
    area_a = (a["xmax"] - a["xmin"]) * (a["ymax"] - a["ymin"])
    area_b = (b["xmax"] - b["xmin"]) * (b["ymax"] - b["ymin"])
    uniao = area_a + area_b - intersecao
    return intersecao / uniao if uniao > 0 else 0.0


def _remover_orfas(revisao: RevisaoDocumento, derivada: DerivadaProjeto,
                   desenhos, *, total: int = 0) -> None:
    """Apaga as folhas que esta conversão não produziu mais.

    Acontece quando o motor melhora (um aglomerado que era dois vira um) ou
    quando o critério de separação muda. Apagar o `DesenhoProjeto` leva junto a
    derivada dele (CASCADE) e **preserva a marcação** (SET_NULL): o apontamento
    do canteiro sobrevive à mudança de folha, sem pino e dizendo por quê. Perder
    o apontamento seria perder trabalho de campo por causa de uma decisão nossa.

    **`total` é a correção da PRA.11, e o defeito sem ele era destrutivo.** Numa
    conversão retomada, `desenhos` traz só as folhas da ÚLTIMA passada — e como
    esta função apaga tudo o que não está na lista, a passada final apagava as
    folhas de todas as anteriores, com as derivadas delas por cascata. O arquivo
    de cinco folhas terminava com uma. Passando o total emitido, o critério vira
    o certo: sobrevive quem tem `ordem` dentro do que o arquivo rende hoje.
    """
    if total:
        orfas = revisao.desenhos.filter(ordem__gt=total)
    else:
        vivos = [d.pk for d in desenhos]
        orfas = revisao.desenhos.exclude(pk__in=vivos)
    if orfas.exists():
        logger.info(
            "prancheta: revisão %s perdeu %s desenho(s) na reconversão",
            revisao.pk, orfas.count(),
        )
        orfas.delete()
    # A linha sem dono (a que veio da fila antes de se saber quantas folhas há)
    # não pode ficar: ela não tem arquivo e apareceria como conversão pendente.
    DerivadaProjeto.objects.filter(
        revisao=revisao, tipo=derivada.tipo, motor=derivada.motor, desenho__isnull=True,
    ).delete()


def _publicar_escala(desenho, detalhe: dict | None) -> None:
    """Leva para o desenho a escala que o motor leu dele (PRA.3b).

    Mora no pipeline e não no motor porque o motor não conhece banco (é o que o
    mantém testável sem `TestCase`) — e não no serializer porque a conversão é
    assíncrona: quando o DXF termina de virar SVG, ninguém está olhando um
    request.

    **Não sobrescreve calibração humana** (`pode_derivar_escala`). O silêncio
    aqui é tão importante quanto a escrita: uma reconversão em massa que
    reescrevesse a régua de mil pranchas mudaria, sem pedido de ninguém, o valor
    de toda medida já anotada no canteiro.
    """
    largura = (detalhe or {}).get("escala_largura_m") or 0
    if largura <= 0 or not desenho.pode_derivar_escala:
        return
    if desenho.escala_valor == largura and desenho.escala_origem:
        return  # reconversão idempotente não precisa tocar a linha

    desenho.escala_valor = largura
    desenho.escala_unidade = "m"
    desenho.escala_origem = RevisaoDocumento.OrigemEscala.DESENHO
    # A memória da derivação, no mesmo campo que guarda a referência da
    # calibração humana: as duas respondem "de onde saiu este metro?", e quem
    # for conferir uma prancha suspeita procura num lugar só.
    desenho.escala_referencia = {
        "origem": "desenho",
        "unidades_desenho": (detalhe or {}).get("unidades_desenho"),
        "unidades_rotulo": (detalhe or {}).get("unidades_rotulo", ""),
        "largura_m": largura,
        # Quando a coordenada contradisse o cabeçalho, quem for conferir a régua
        # precisa achar isso aqui — é a explicação de por que o metro não bate
        # com o que o AutoCAD mostra na barra de status de um template errado.
        "georreferenciado": (detalhe or {}).get("georreferenciado", False),
        "unidade_corrigida": (detalhe or {}).get("unidade_corrigida", ""),
    }
    desenho.save(update_fields=[
        "escala_valor", "escala_unidade", "escala_origem", "escala_referencia",
    ])


def _traduzir(erro: ErroDeConversao, tiers) -> ErroDeConversao:
    """Ajusta a frase do `MotorInsuficiente` a quem JÁ paga o motor premium.

    "Exige o motor de alta fidelidade" é a mensagem certa para quem não o
    contratou — é upsell honesto. Para quem contratou, a mesma frase manda
    comprar o que já está comprado, e o problema real é outro: a escalada para a
    APS chega na PRA.4. Dizer isso é a diferença entre um cliente que espera e um
    cliente que abre chamado achando que pagou por nada.
    """
    if not isinstance(erro, MotorInsuficiente) or "premium" not in set(tiers):
        return erro
    return MotorIndisponivel(
        f"{erro.detalhe} O seu plano inclui esse motor, mas ele ainda não está "
        "ligado neste servidor.",
        **erro.extra,
    )


def _materializar(revisao: RevisaoDocumento) -> tuple[str, bool]:
    """Caminho local do arquivo de origem, copiando do storage se necessário.

    Motor externo (`dwg2dxf`) e biblioteca compilada (IfcOpenShell) querem um
    **caminho**, não um file-like: nenhum dos dois lê de um `FileField` remoto.
    Com storage local o `.path` já serve e nada é copiado; com storage remoto a
    cópia temporária é o preço, e o `bool` de retorno é quem manda apagá-la.
    """
    try:
        return revisao.arquivo.path, False
    except (NotImplementedError, ValueError):
        pass

    descritor, destino = tempfile.mkstemp(prefix="prancheta-origem-")
    with os.fdopen(descritor, "wb") as saida:
        revisao.arquivo.open("rb")
        try:
            for bloco in revisao.arquivo.chunks():
                saida.write(bloco)
        finally:
            revisao.arquivo.close()
    return destino, True


def _apagar(caminho: str) -> None:
    try:
        os.unlink(caminho)
    except OSError:  # pragma: no cover
        pass


def _marcar(derivada: DerivadaProjeto, estado: str, **campos) -> None:
    """Estado visível **agora** — a planta §5 pede o estado na tela, e uma
    conversão de 3 minutos que só grava no fim deixa a tela mentindo por 3
    minutos."""
    derivada.estado = estado
    for campo, valor in campos.items():
        setattr(derivada, campo, valor)
    derivada.save(update_fields=["estado", *campos])


def _falhar(
    derivada: DerivadaProjeto, erro: ErroDeConversao, *, custo: dict | None = None,
) -> DerivadaProjeto:
    derivada.estado = DerivadaProjeto.Estado.ERRO
    derivada.erro_motivo = erro.motivo
    derivada.erro_detalhe = (erro.detalhe or str(erro))[:1000]
    derivada.memoria = {
        **{k: v for k, v in (erro.extra or {}).items()},
        # O custo de quem NÃO converteu é o número mais útil dos dois: é ele que
        # diz se `recurso_excedido` foi teto apertado ou desenho caro de verdade.
        **({"custo": custo} if custo else {}),
    }
    derivada.concluido_em = timezone.now()
    derivada.save(update_fields=[
        "estado", "erro_motivo", "erro_detalhe", "memoria", "concluido_em",
    ])
    # A cadeira sai junto com a falha (D98). Erro que não devolve vaga é frota
    # que encolhe em silêncio — e o sintoma seria uma fila cada vez mais lenta
    # sem nada nos logs, que é o pior formato possível para este defeito.
    _liberar_cadeira(derivada)
    return derivada
