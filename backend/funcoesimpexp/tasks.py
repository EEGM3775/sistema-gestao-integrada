# backend/funcoesimpexp/tasks.py
"""IE.0b — o caminho de job da R10: pequeno é síncrono, grande é job.

**O corte existe por causa do gateway, não por elegância.** Um request que lê e
classifica 30.000 linhas fica pendurado, o nginx corta em 60 s, o usuário não vê
resultado e reenvia — dobrando a carga exatamente quando o sistema já está
apertado. Com o job, o upload responde na hora com um id, a tela acompanha o
progresso e o reenvio deixa de fazer sentido.

**Contexto de tenant, sempre.** Task que lê o ORM sem `rls_bypass()` →
`tenant_context()` não acha linha nenhuma sob a RLS fail-closed do worker: foi
exatamente o **D8** (a cobrança que respondia 202 e nunca gerava boleto). As três
tasks daqui armam o contexto na primeira linha, e o teste
`TaskSemContextoDeRequestTests` prova que funcionam sem request nenhum.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from nucleo.tasks import DLQTask
from nucleo.tenancy import rls_bypass, tenant_context

from . import exportacao as motor_exportacao
from . import importacao as motor_importacao
from .limites import Limites
from .models import Exportacao, Importacao
from .registro import RecursoDesconhecido, obter

#: Por quantos dias um lote que ficou esperando de-para guarda o arquivo. É a
#: outra metade do `preservar_arquivo` da R4: sem prazo, "preservado" vira
#: "para sempre" — e arquivo de importação é o dado mais cru que existe
#: (carteira de clientes, folha), guardado fora de qualquer quota de storage.
#: Uma semana cobre com folga o "escolha qual coluna é cada campo" e fecha o
#: acervo permanente de graça que o desenho anterior deixava aberto.
DIAS_PARA_ARQUIVO_ORFAO = 7

logger = logging.getLogger(__name__)


class RequisicaoDiferida:
    """O mínimo de "request" que os ganchos de um recurso esperam.

    `queryset(self, request, recorte)` recebe um request porque no caminho
    síncrono é dele que sai o usuário (para escopo por dono, permissão de linha,
    unidade de medida da pessoa). No worker não existe request — e inventar um
    `HttpRequest` de mentira, com sessão e headers vazios, convidaria um recurso
    a ler dali algo que nunca estará preenchido.

    Então o contrato fica explícito: no job, `request` é isto — usuário e mais
    nada. Recurso que dependa de outra coisa do request quebra aqui, alto e claro,
    em vez de exportar dado errado em silêncio.
    """

    def __init__(self, user):
        self.user = user
        self.query_params: dict = {}
        self.diferida = True


def _usuario(usuario_id):
    """Carrega o usuário que pediu a operação, sob bypass (a RLS ainda não foi armada)."""
    from nucleo.models import Usuario

    if not usuario_id:
        return None
    with rls_bypass():
        return Usuario.objects.filter(pk=usuario_id).select_related("tenant").first()


@shared_task(bind=True, base=DLQTask, max_retries=2, name="funcoesimpexp.preparar_importacao")
def preparar_importacao(self, importacao_id, tenant_id, *, limites=None, de_para=None,
                        delimitador=None, teto=None, formato=None):
    """Lê e classifica um arquivo grande já persistido, deixando-o em `CONFERINDO`.

    O arquivo vem do storage e não como argumento: mandar megabytes pelo broker
    seria carregar o Redis com o que o filesystem já guarda melhor, e o Celery
    serializa argumento em JSON.
    """
    with tenant_context(tenant_id):
        lote = Importacao.objects.filter(
            pk=importacao_id, tenant_id=tenant_id,
        ).first()
        if lote is None:
            logger.warning("impexp: importação %s sumiu antes do job.", importacao_id)
            return None
        try:
            recurso = obter(lote.recurso).com_contexto(lote.contexto)
        except RecursoDesconhecido:
            _marcar_erro(lote, f"O recurso '{lote.recurso}' não existe mais.")
            return None

        try:
            conteudo = lote.arquivo.read()
        except (OSError, ValueError) as exc:
            _marcar_erro(lote, f"Arquivo não pôde ser lido no servidor: {exc}")
            return None

        try:
            motor_importacao.preparar(
                recurso=recurso,
                conteudo=conteudo,
                nome_arquivo=lote.arquivo_nome,
                tenant_id=tenant_id,
                usuario_nome=lote.usuario_nome,
                limites=limites,
                de_para=de_para,
                delimitador=delimitador,
                lote=lote,
                # O orçamento de recurso vem resolvido do request (é lá que
                # existe a claim `plano`), e o formato veio reconhecido pelos
                # bytes. Sem os dois, este é o caminho onde um XLSX de poucos MB
                # descomprime sem teto — no worker GERAL, que também carrega
                # cobrança, NF-e e lembrete.
                teto=Limites.de_json(teto),
                formato=formato or (lote.parametros or {}).get("formato") or None,
            )
        except motor_importacao.LimiteDoPlano as exc:
            # Teto do plano é decisão de negócio, não falha: não vai para a DLQ
            # nem para retry — vira mensagem que a tela mostra.
            _marcar_erro(lote, str(exc))
            return None
        finally:
            # O arquivo de entrada some assim que foi lido: o que interessa dele
            # já está em `LinhaImportacao.bruto`, e guardar o original seria
            # manter dado cru (folha, carteira) fora de qualquer política.
            #
            # A exceção é o lote que ficou esperando um de-para (R4): sem o
            # arquivo, "escolha qual coluna é cada campo" viraria "suba tudo de
            # novo" — e o arquivo é grande, que é a razão de ter virado job.
            lote.refresh_from_db(fields=["parametros"])
            if not (lote.parametros or {}).get("aguarda_de_para"):
                _descartar_arquivo(lote)
        return lote.pk


@shared_task(bind=True, base=DLQTask, max_retries=2, name="funcoesimpexp.gerar_exportacao")
def gerar_exportacao(self, exportacao_id, tenant_id, usuario_id=None):
    """Materializa um recorte grande e guarda o arquivo com validade limitada."""
    usuario = _usuario(usuario_id)
    with tenant_context(tenant_id):
        lote = Exportacao.objects.filter(pk=exportacao_id, tenant_id=tenant_id).first()
        if lote is None:
            logger.warning("impexp: exportação %s sumiu antes do job.", exportacao_id)
            return None
        try:
            recurso = obter(lote.recurso).com_contexto(lote.contexto)
            motor_exportacao.gerar_no_lote(
                lote, recurso=recurso, request=RequisicaoDiferida(usuario),
            )
        except (RecursoDesconhecido, motor_exportacao.ExportacaoInvalida) as exc:
            lote.status = Exportacao.Status.ERRO
            lote.mensagem = str(exc)[:500]
            lote.save(update_fields=["status", "mensagem"])
            return None
        return lote.pk


@shared_task(name="funcoesimpexp.limpar_exportacoes_expiradas")
def limpar_exportacoes_expiradas():
    """Apaga os arquivos vencidos — a outra metade da "validade limitada" da R10.

    Sem esta varredura, `expira_em` seria só uma data bonita no banco enquanto o
    arquivo seguiria no disco para sempre. **A linha permanece** (é o rastro da
    R12, e rastro não expira); o que some é o arquivo.

    Roda sob `rls_bypass` porque é job global: varre todos os tenants, como o
    lembrete do CRM.
    """
    apagados = 0
    with rls_bypass():
        vencidas = Exportacao.objects.filter(
            expira_em__lt=timezone.now(),
        ).exclude(arquivo="").exclude(arquivo=None)
        for lote in vencidas.iterator():
            lote.arquivo.delete(save=False)
            lote.arquivo = None
            lote.save(update_fields=["arquivo"])
            apagados += 1
    if apagados:
        logger.info("impexp: %s arquivo(s) de exportação expirados removidos.", apagados)
    return apagados


@shared_task(name="funcoesimpexp.limpar_entradas_orfas")
def limpar_entradas_orfas():
    """Apaga o arquivo de entrada que ficou esperando um de-para e ninguém voltou.

    **O buraco que isto fecha** (análise de 07/08/2026): `limpar_exportacoes_expiradas`
    varria só a SAÍDA. Na entrada, o arquivo é apagado assim que lido — menos no
    lote que ficou em `aguarda_de_para`, que o preserva de propósito (R4) e não
    tinha prazo nenhum. Subir arquivos com cabeçalho que não casa era, portanto,
    acervo permanente e fora de qualquer quota.

    Como a exportação: **a linha permanece** (é o rastro de que se tentou
    importar); o que some é o arquivo, e o lote passa a dizer isso, para a tela
    não oferecer um "escolha as colunas" que não tem mais o que reler.

    Sob `rls_bypass` porque é job global, como a faxina da saída.
    """
    corte = timezone.now() - timedelta(days=DIAS_PARA_ARQUIVO_ORFAO)
    apagados = 0
    with rls_bypass():
        orfas = (
            Importacao.objects
            .filter(criada_em__lt=corte)
            .exclude(arquivo="")
            .exclude(arquivo=None)
        )
        for lote in orfas.iterator():
            try:
                lote.arquivo.delete(save=False)
            except OSError:  # pragma: no cover - disco/storage indisponível
                logger.warning("impexp: não consegui apagar a entrada %s.", lote.pk)
            lote.arquivo = None
            lote.parametros = {
                **(lote.parametros or {}),
                "aguarda_de_para": False,
                "arquivo_expirado": True,
            }
            lote.mensagem = (
                "O arquivo desta importação expirou no servidor e foi removido. "
                "Suba de novo para escolher as colunas."
            )[:500]
            lote.save(update_fields=["arquivo", "parametros", "mensagem"])
            apagados += 1
    if apagados:
        logger.info("impexp: %s arquivo(s) de entrada órfãos removidos.", apagados)
    return apagados


def _marcar_erro(lote: Importacao, mensagem: str) -> None:
    lote.status = Importacao.Status.ERRO
    lote.mensagem = mensagem[:500]
    lote.decidida_em = timezone.now()
    lote.save(update_fields=["status", "mensagem", "decidida_em"])
    _descartar_arquivo(lote)


def _descartar_arquivo(lote: Importacao) -> None:
    if not lote.arquivo:
        return
    try:
        lote.arquivo.delete(save=False)
    except OSError:  # pragma: no cover - disco/storage indisponível
        logger.warning("impexp: não consegui apagar o arquivo da importação %s.", lote.pk)
    lote.arquivo = None
    lote.save(update_fields=["arquivo"])
