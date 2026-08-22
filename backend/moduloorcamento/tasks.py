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
   URL da Caixa: ela lê o que foi configurado (`BaseReferencial.url_origem` não
   existe hoje) e, na ausência, faz o que sabe fazer — **avisar** que a
   publicação vigente está velha. Um job que inventa fonte é um job que um dia
   importa dado errado com a confiança de um robô.
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
