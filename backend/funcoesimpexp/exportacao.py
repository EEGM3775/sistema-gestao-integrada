# backend/funcoesimpexp/exportacao.py
"""IE.0 — o motor de exportação: recorte da tela → arquivo com procedência.

**R7:** o arquivo é o que a pessoa está vendo. Os mesmos filtros, a mesma ordem,
nunca mais linhas do que ela veria. Um export que ignora o filtro entrega 40.000
linhas para quem pediu 12; um que ignora a permissão de linha vira porta paralela
mais permissiva que a UI — que é exatamente o defeito do caminho genérico do v01.

**R9:** toda saída carrega de onde veio. Peça sem procedência não é conferível, e
é a primeira coisa que quem recebe procura.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.files.base import ContentFile
from django.utils import timezone

from .formatos.escrita import escrever
from .models import Exportacao
from .registro import Recurso

# R10, lado da saída. O corte é menor que o da importação porque exportar
# materializa o arquivo inteiro em memória antes de responder: 2.000 linhas de
# XLSX com estilo já são alguns MB, e o custo cresce com a largura da declaração,
# não só com a altura.
LIMITE_SINCRONO = 2_000

# Quanto tempo o arquivo gerado fica disponível. Curto de propósito: é uma
# fotografia de dado sensível fora da RLS (mora no filesystem), e o valor de
# retê-lo cai a zero assim que a pessoa baixa. Quem precisar de novo, gera de
# novo — e a geração nova reflete o dado de agora, que é o que quase sempre se
# quer.
VALIDADE_HORAS = 24


class ExportacaoInvalida(Exception):
    """Exportação pedida em formato ou recurso que não a oferece."""


def construir(
    *, recurso: Recurso, request, formato: str = "xlsx", recorte: dict | None = None,
) -> tuple[bytes, str, str, int]:
    """O arquivo, sem rastro nem persistência: `(bytes, content_type, nome, linhas)`.

    Separado de `exportar` porque os dois caminhos da R10 precisam do arquivo mas
    registram o rastro em momentos diferentes — o síncrono ao devolver, o job ao
    concluir. Devolver o total daqui evita materializar o recorte duas vezes só
    para saber quantas linhas saíram.
    """
    if not recurso.exporta:
        raise ExportacaoInvalida(f"O recurso '{recurso.id}' não oferece exportação.")
    if formato not in recurso.formatos_saida:
        raise ExportacaoInvalida(
            f"'{recurso.rotulo}' não sai em {formato}. Disponíveis: "
            f"{', '.join(recurso.formatos_saida)}."
        )

    recorte = recorte or {}
    linhas = _materializar(recurso, request, recorte)
    procedencia = _procedencia(recurso, request, recorte, len(linhas))
    conteudo, content_type = escrever(
        formato, colunas=recurso.colunas, linhas=linhas, procedencia=procedencia,
    )
    return conteudo, content_type, nome_do_arquivo(recurso, formato), len(linhas)


def exportar(
    *,
    recurso: Recurso,
    request,
    formato: str = "xlsx",
    recorte: dict | None = None,
    tenant_id=None,
    registrar_rastro: bool = True,
) -> tuple[bytes, str, str]:
    """Devolve `(conteudo, content_type, nome_do_arquivo)`."""
    recorte = recorte or {}
    conteudo, content_type, nome, total = construir(
        recurso=recurso, request=request, formato=formato, recorte=recorte,
    )

    if registrar_rastro and tenant_id is not None:
        # O valor da linha é o rastro, não o arquivo: "quem levou a carteira de
        # clientes embora, quando e com que recorte" precisa ter resposta (R12).
        user = getattr(request, "user", None)
        Exportacao.objects.create(
            tenant_id=tenant_id,
            recurso=recurso.id,
            formato=formato,
            recorte=_recorte_serializavel(recorte),
            contexto=dict(recurso.contexto or {}),
            linhas=total,
            status=Exportacao.Status.PRONTA,
            usuario_nome=_nome_do_usuario(user)[:150],
        )

    return conteudo, content_type, nome


def _materializar(recurso: Recurso, request, recorte: dict) -> list[dict]:
    """O gancho pode devolver dicionários prontos ou objetos do ORM."""
    linhas = []
    for item in recurso.queryset(request, recorte):
        linhas.append(item if isinstance(item, dict) else recurso.serializar_objeto(item))
    return linhas


# ---------------------------------------------------------------------------
# R10 — o caminho de job
# ---------------------------------------------------------------------------


def vale_a_pena_job(recurso: Recurso, request, recorte: dict) -> bool:
    """Conta as linhas do recorte sem materializá-las, quando dá.

    Num `QuerySet` isso é um `COUNT` no banco e custa quase nada; numa lista já
    pronta, o `len` é imediato. O gancho pode devolver um gerador, e aí não há o
    que contar sem consumir — nesse caso a resposta é "não", e o recurso que
    espera volume declara `contar()` para não cair na exceção do timeout.
    """
    total = recurso.contar(request, recorte)
    return total is not None and total > LIMITE_SINCRONO


def abrir_lote(*, recurso: Recurso, formato: str, recorte: dict, tenant_id, usuario_nome: str):
    """Cria a exportação em `GERANDO` — a tela precisa de um id para acompanhar."""
    if not recurso.exporta:
        raise ExportacaoInvalida(f"O recurso '{recurso.id}' não oferece exportação.")
    if formato not in recurso.formatos_saida:
        raise ExportacaoInvalida(
            f"'{recurso.rotulo}' não sai em {formato}. Disponíveis: "
            f"{', '.join(recurso.formatos_saida)}."
        )
    return Exportacao.objects.create(
        tenant_id=tenant_id,
        recurso=recurso.id,
        formato=formato,
        recorte=_recorte_serializavel(recorte or {}),
        contexto=dict(recurso.contexto or {}),
        status=Exportacao.Status.GERANDO,
        usuario_nome=usuario_nome[:150],
    )


def gerar_no_lote(exportacao: Exportacao, *, recurso: Recurso, request) -> Exportacao:
    """Executa a geração de um lote aberto e guarda o arquivo (chamada do worker)."""
    conteudo, _tipo, nome, total = construir(
        recurso=recurso, request=request, formato=exportacao.formato,
        recorte=exportacao.recorte or {},
    )
    exportacao.arquivo.save(nome, ContentFile(conteudo), save=False)
    exportacao.linhas = total
    exportacao.status = Exportacao.Status.PRONTA
    exportacao.expira_em = timezone.now() + timedelta(hours=VALIDADE_HORAS)
    exportacao.save(update_fields=["arquivo", "linhas", "status", "expira_em"])
    return exportacao


def _procedencia(recurso: Recurso, request, recorte: dict, total: int) -> dict:
    destino = recurso.rotulo_do_contexto()
    return {
        "recurso_rotulo": f"{recurso.rotulo} — {destino}" if destino else recurso.rotulo,
        "recorte": descrever_recorte(recorte),
        "usuario": _nome_do_usuario(getattr(request, "user", None)) or "—",
        "emitido_em": timezone.localtime().strftime("%d/%m/%Y %H:%M"),
        "linhas": total,
    }


def _nome_do_usuario(user) -> str:
    return getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "") or ""


def descrever_recorte(recorte: dict) -> str:
    """"obra=Alfa · status=aprovado" — o que estava filtrado na tela, em uma linha."""
    if not recorte:
        return ""
    partes = [f"{k}={v}" for k, v in sorted(recorte.items()) if v not in (None, "", [])]
    return " · ".join(partes)


def _recorte_serializavel(recorte: dict) -> dict:
    return {k: (v if isinstance(v, (str, int, float, bool, type(None))) else str(v))
            for k, v in recorte.items()}


def nome_do_arquivo(recurso: Recurso, formato: str) -> str:
    """`planilha-orcamentaria-25-07-2026.xlsx` — legível na pasta de downloads."""
    base = f"{recurso.rotulo}-{timezone.localtime():%d-%m-%Y}"
    limpo = "".join(c if c.isalnum() or c in "-_" else "-" for c in base.lower())
    while "--" in limpo:
        limpo = limpo.replace("--", "-")
    return f"{limpo.strip('-')}.{formato}"
