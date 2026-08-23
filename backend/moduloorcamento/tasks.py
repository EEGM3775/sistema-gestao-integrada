# backend/moduloorcamento/tasks.py
"""Manutenção automática das séries de plataforma (ORC.7).

O calcanhar operacional de um módulo de orçamento não é cálculo — é **dado
fresco**. Os concorrentes vendem "20+ bases sempre atualizadas" e essa promessa
não é sobre software: é sobre alguém importar SINAPI de 27 estados todo mês. Com
o comando manual (`importar_base_referencial`) isso é trabalho recorrente do dono
da plataforma, e trabalho recorrente humano é o que atrasa.

Estas tasks fazem a varredura e o aviso; a **importação continua sendo a mesma**
do comando, porque duplicar o parser criaria duas verdades sobre o mesmo arquivo.

Três decisões de desenho:

1. **Nada de baixar da internet sem fonte declarada.** A task não sai adivinhando
   URL da Caixa: ela lê o que foi configurado e, na ausência, faz o que sabe
   fazer — **avisar** que a publicação vigente está velha. Um job que inventa
   fonte é um job que um dia importa dado errado com a confiança de um robô.
   *(A ORC.8 deu a essa regra o lugar que faltava: `FonteOficial` é a declaração,
   escrita por gente, e `BaseReferencial.url_origem` guarda de onde cada preço
   veio. O aviso continua; o que mudou é que agora ele pode virar carga.)*
2. **A varredura é de plataforma, não de tenant.** `BaseReferencial` e
   `IndiceEconomico` são globais (§11.1), então roda com `rls_bypass` e não
   percorre tenants — é a mesma natureza da limpeza de exportações do
   `funcoesimpexp`.
3. **Atraso é sintoma, não falha.** Base velha não quebra nada: os orçamentos já
   feitos guardam snapshot. O que ela produz é um orçamento *novo* nascendo com
   preço vencido — e isso é aviso, não exceção.
"""
import logging
from datetime import date

from celery import shared_task
from django.db.models import Max

from nucleo.tasks import DLQTask
from nucleo.tenancy import rls_bypass

logger = logging.getLogger(__name__)

# Quantos meses uma publicação pode ficar para trás antes de virar aviso. Não é
# teto de plano (não diz até onde o cliente vai, §5.6 do planos.py) — é a
# definição de "atrasada" para a operação da plataforma, e dois meses é o atraso
# que a própria SINAPI tem no pior caso entre coleta e publicação.
MESES_ATE_ATRASADA = 2


def _meses_entre(inicio: date, fim: date) -> int:
    return (fim.year - inicio.year) * 12 + (fim.month - inicio.month)


@shared_task(name="moduloorcamento.verificar_bases_desatualizadas", base=DLQTask, bind=True)
def verificar_bases_desatualizadas(self, referencia: str | None = None) -> dict:
    """Varre as publicações ativas e aponta quais ficaram para trás.

    Devolve o relatório em vez de só logar porque ele é o que a tela de
    **Bases & bancos** mostra ao dono da plataforma: a lista do que precisa de
    importação, com quantos meses cada fonte está atrasada. Um job que só escreve
    em log é um job cuja saída ninguém lê.

    `referencia` existe para o teste fixar a data — `date.today()` dentro da task
    tornaria o resultado dependente do dia em que a suíte roda.
    """
    from .models import BaseReferencial

    hoje = date.fromisoformat(referencia) if referencia else date.today()
    atrasadas, em_dia = [], []

    with rls_bypass():
        agrupado = (
            BaseReferencial.objects.filter(ativa=True)
            .values("fonte", "uf", "regime_encargos")
            .annotate(ultima=Max("mes_referencia"))
            .order_by("fonte", "uf")
        )
        for grupo in agrupado:
            atraso = _meses_entre(grupo["ultima"], hoje)
            registro = {
                "fonte": grupo["fonte"],
                "uf": grupo["uf"],
                "regime": grupo["regime_encargos"],
                "ultima_publicacao": grupo["ultima"].isoformat(),
                "meses_de_atraso": atraso,
            }
            (atrasadas if atraso >= MESES_ATE_ATRASADA else em_dia).append(registro)

    if atrasadas:
        logger.warning(
            "orcamento: %d publicação(ões) de base referencial atrasada(s) — %s",
            len(atrasadas),
            ", ".join(f"{a['fonte']}/{a['uf']} ({a['meses_de_atraso']}m)" for a in atrasadas[:10]),
        )

    return {
        "referencia": hoje.isoformat(),
        "meses_ate_atrasada": MESES_ATE_ATRASADA,
        "atrasadas": sorted(atrasadas, key=lambda a: a["meses_de_atraso"], reverse=True),
        "em_dia": em_dia,
        "total_publicacoes": len(atrasadas) + len(em_dia),
    }


@shared_task(name="moduloorcamento.verificar_indices_desatualizados", base=DLQTask, bind=True)
def verificar_indices_desatualizados(self, referencia: str | None = None) -> dict:
    """O mesmo para as séries de índice — e aqui o atraso **quebra**.

    Diferença de consequência que justifica task separada: base velha faz um
    orçamento novo nascer com preço vencido (ruim, silencioso). Índice velho faz
    o cálculo do fator de reajuste **levantar erro** — `reajuste.numero_indice`
    recusa-se a interpolar. Então este aviso é o que evita alguém descobrir a
    lacuna no dia do aniversário do contrato, que é o pior dia possível.
    """
    from .models import IndiceEconomico, ValorIndice

    hoje = date.fromisoformat(referencia) if referencia else date.today()
    atrasados, em_dia, vazios = [], [], []

    with rls_bypass():
        for indice in IndiceEconomico.objects.filter(ativo=True):
            ultima = ValorIndice.objects.filter(indice=indice).aggregate(
                m=Max("competencia")
            )["m"]
            if ultima is None:
                vazios.append({"codigo": indice.codigo, "nome": indice.nome})
                continue
            atraso = _meses_entre(ultima, hoje)
            registro = {
                "codigo": indice.codigo,
                "nome": indice.nome,
                "ultima_competencia": ultima.isoformat(),
                "meses_de_atraso": atraso,
            }
            (atrasados if atraso >= MESES_ATE_ATRASADA else em_dia).append(registro)

    if atrasados or vazios:
        logger.warning(
            "orcamento: %d índice(s) atrasado(s) e %d sem série — reajuste falhará "
            "para competência não publicada",
            len(atrasados), len(vazios),
        )

    return {
        "referencia": hoje.isoformat(),
        "atrasados": sorted(atrasados, key=lambda a: a["meses_de_atraso"], reverse=True),
        "em_dia": em_dia,
        "sem_serie": vazios,
    }


# ---------------------------------------------------------------------------
# ORC.8 — a varredura deixou de só avisar
# ---------------------------------------------------------------------------
#
# A decisão nº 1 do topo deste arquivo dizia: *"nada de baixar da internet sem
# fonte declarada — um job que inventa URL é um job que um dia importa dado
# errado com a confiança de um robô"*. Ela continua valendo **na íntegra**; o que
# mudou é que agora existe onde declarar. `FonteOficial` é essa declaração, e é
# escrita por gente: sem template cadastrado, a fonte simplesmente não é tentada.


@shared_task(name="moduloorcamento.carregar_base_oficial", base=DLQTask, bind=True)
def carregar_base_oficial(self, carga_id: int) -> dict:
    """Roda uma corrida de carga. O desfecho mora na `CargaBase`, não aqui.

    A task devolve um resumo curto para o log e para o flower, mas quem conta a
    história inteira é a linha no banco — inclusive quando falha, e principalmente
    quando falha: é ela que a tela lê.

    Não há `retry`, e é deliberado. O backoff que importa é o do **download**
    (`oficial.baixar`), que sabe distinguir 429 de 404; repetir a corrida inteira
    por fora disso reprocessaria 54 publicações já gravadas para insistir num
    mês que talvez ainda não tenha sido publicado. Repetir é decisão de gente, e
    tem verbo próprio (`cargas/{id}/repetir/`).
    """
    from . import carga as motor
    from .models import CargaBase

    with rls_bypass():
        registro = CargaBase.objects.filter(pk=carga_id).first()
        if registro is None:
            logger.warning("orcamento: carga %s não existe mais", carga_id)
            return {"carga": carga_id, "estado": "inexistente"}

        conteudo = None
        if registro.origem == CargaBase.Origem.UPLOAD and registro.arquivo:
            with registro.arquivo.open("rb") as arquivo:
                conteudo = arquivo.read()

        motor.executar(registro, conteudo)
        return {
            "carga": registro.pk,
            "fonte": registro.fonte,
            "competencia": registro.competencia.isoformat(),
            "estado": registro.estado,
            "publicacoes": registro.total_publicacoes,
            "analitica": registro.total_analitica,
        }


@shared_task(name="moduloorcamento.agendar_cargas_do_mes", base=DLQTask, bind=True)
def agendar_cargas_do_mes(self, referencia: str | None = None) -> dict:
    """A varredura diária que dispara a carga quando chega o dia da fonte.

    **O botão resolve hoje; isto evita que "alguém esqueceu" vire orçamento
    nascendo com preço vencido.** Quem escolhe o dia é o superuser, por fonte
    (`FonteOficial.dia_do_mes`) — `0` deixa só o botão.

    Três recusas, e cada uma existe para o agendamento não virar ruído:

    - fonte sem template não é tentada (a decisão nº 1);
    - fonte cujo formato o motor não sabe ler não é tentada — hoje só a SINAPI
      tem leitor do arquivo largo, e agendar as outras seria agendar falha;
    - competência já carregada com sucesso não é tentada de novo. A carga é
      idempotente, mas repeti-la todo dia é gastar minutos de worker para
      reescrever exatamente os mesmos preços.
    """
    from . import carga as motor
    from . import oficial
    from .models import CargaBase, FonteOficial

    hoje = date.fromisoformat(referencia) if referencia else date.today()
    disparadas, ignoradas = [], []

    with rls_bypass():
        for fonte in FonteOficial.objects.filter(ativa=True):
            motivo = ""
            if not fonte.dia_do_mes or fonte.dia_do_mes != hoje.day:
                continue
            if not fonte.template_url:
                motivo = "sem template de URL"
            elif fonte.fonte not in motor.fontes_conhecidas():
                motivo = "o motor ainda não lê o formato desta fonte"

            competencia = oficial.competencia_alvo(fonte.defasagem_meses, hoje)
            if not motivo and CargaBase.objects.filter(
                fonte=fonte.fonte, competencia=competencia,
                estado=CargaBase.Estado.CONCLUIDA, somente_resumo=False,
            ).exists():
                motivo = f"{competencia:%m/%Y} já carregada"
            if not motivo and CargaBase.objects.filter(
                fonte=fonte.fonte,
                estado__in=[
                    CargaBase.Estado.PENDENTE, CargaBase.Estado.BAIXANDO,
                    CargaBase.Estado.LENDO, CargaBase.Estado.GRAVANDO,
                ],
            ).exists():
                motivo = "já há uma carga desta fonte em andamento"

            if motivo:
                ignoradas.append({"fonte": fonte.fonte, "motivo": motivo})
                continue

            nova = CargaBase.objects.create(
                fonte=fonte.fonte, competencia=competencia,
                origem=CargaBase.Origem.DOWNLOAD,
                solicitada_por_nome="agendamento",
            )
            carregar_base_oficial.delay(nova.pk)
            disparadas.append({
                "fonte": fonte.fonte,
                "competencia": competencia.isoformat(),
                "carga": nova.pk,
            })

    if disparadas:
        logger.info("orcamento: %d carga(s) de base disparada(s) pelo agendamento", len(disparadas))
    return {"referencia": hoje.isoformat(), "disparadas": disparadas, "ignoradas": ignoradas}
