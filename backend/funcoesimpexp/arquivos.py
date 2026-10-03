"""DMS — o registro de todo arquivo, dentro e fora do sistema.

**Por que mora aqui e não num `modulodms`.** O `funcoesimpexp` já era a porta
única por onde todo arquivo entra (`entrada.admitir`) e sai (`entrega.servir`,
exportação) — a R17. Coordenar documentos é responder, sobre esses mesmos
arquivos, três perguntas, e as três já têm onde ser lidas:

- **guardados** — o que está aqui dentro: cada recurso declara em `guardados`
  (registro.`Guardado`) o model e o `FileField` onde mora o que ele recebeu;
- **entraram** — o que chegou por lote: `Importacao`;
- **saíram** — o que deixou o perímetro: `Exportacao` (planilha, PDF) e a
  entrega de binário auditada no `AuditLog` (`EXPORTAR_DADOS` com `entrega`).

Um app à parte teria de copiar o arquivo ou reimplementar a porta — as duas
formas da divergência que a R17 existe para impedir. O gate é o da entrega
(`acesso.exigir_entrega`): só aparece o que a pessoa poderia baixar, e o link
é o mesmo do download.
"""
from __future__ import annotations

import os

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from . import registro
from .acesso import exigir_entrega, pode_operar


def _pode_ver(user, recurso) -> bool:
    try:
        exigir_entrega(user, recurso)
    except PermissionDenied:
        return False
    return True


def recursos_visiveis(user) -> list:
    """Os recursos com arquivos guardados que esta pessoa pode abrir."""
    return [r for r in registro.listar() if r.guardados and _pode_ver(user, r)]


def _link(recurso_id: str, especie: str, chave) -> str:
    return f"/api/impexp/{recurso_id}/arquivo/{especie}/{chave}/"


def _valor(linha: dict, lookup: str):
    return linha.get(lookup) if lookup else None


def guardados(user, tenant_id, *, busca: str = "", recurso_id: str = "", limite: int = 50) -> dict:
    """Os arquivos que estão dentro do sistema, mais novos primeiro.

    Cada `Guardado` traz no máximo `limite` linhas, e o conjunto é cortado em
    `limite` depois de ordenado — o total por recurso vem de um `COUNT` à parte,
    para a tela dizer quanto existe sem materializar tudo.
    """
    linhas, totais = [], []
    for recurso in recursos_visiveis(user):
        if recurso_id and recurso.id != recurso_id:
            continue
        total = 0
        for g in recurso.guardados:
            qs = g.modelo.objects.filter(tenant_id=tenant_id, **(g.filtro or {}))
            qs = qs.exclude(**{g.campo: ""}).exclude(**{f"{g.campo}__isnull": True})
            if busca:
                termo = Q(**{f"{g.campo}__icontains": busca})
                for lookup in (g.titulo, g.onde):
                    if lookup:
                        termo |= Q(**{f"{lookup}__unaccent__icontains": busca})
                qs = qs.filter(termo)
            total += qs.count()
            pk = g.modelo._meta.pk.name
            campos = [c for c in (pk, g.campo, g.quando, g.titulo, g.onde) if c]
            ordem = f"-{g.quando}" if g.quando else f"-{pk}"
            for linha in qs.order_by(ordem).values(*dict.fromkeys(campos))[:limite]:
                caminho = linha.get(g.campo) or ""
                quando = _valor(linha, g.quando)
                linhas.append({
                    "recurso": recurso.id,
                    "recurso_rotulo": recurso.rotulo,
                    "modulo": recurso.modulo,
                    "especie": g.especie,
                    "chave": linha[pk],
                    "nome": os.path.basename(caminho),
                    "titulo": str(_valor(linha, g.titulo) or ""),
                    "onde": str(_valor(linha, g.onde) or ""),
                    "quando": quando.isoformat() if quando else None,
                    "link": _link(recurso.id, g.especie, linha[pk]),
                })
        totais.append({"recurso": recurso.id, "rotulo": recurso.rotulo, "modulo": recurso.modulo, "total": total})
    linhas.sort(key=lambda l: l["quando"] or "", reverse=True)
    return {"arquivos": linhas[:limite], "por_recurso": totais}


def _ids_visiveis(user) -> set[str]:
    """Recursos cujo movimento a pessoa pode ver: o que ela opera ou abre."""
    return {r.id for r in registro.listar() if pode_operar(user, r) or (r.guardados and _pode_ver(user, r))}


def entraram(user, tenant_id, *, limite: int = 50) -> list[dict]:
    """Os lotes que trouxeram arquivo ou planilha para dentro."""
    from .models import Importacao

    ids = _ids_visiveis(user)
    rotulos = {r.id: r.rotulo for r in registro.listar()}
    qs = Importacao.objects.filter(tenant_id=tenant_id, recurso__in=ids).order_by("-criada_em")[:limite]
    return [{
        "id": i.importacao_id, "recurso": i.recurso, "recurso_rotulo": rotulos.get(i.recurso, i.recurso),
        "arquivo": i.arquivo_nome, "situacao": i.get_status_display(), "status": i.status,
        "linhas": i.total_linhas, "aplicadas": i.total_aplicadas,
        "quem": i.usuario_nome, "quando": i.criada_em.isoformat(),
    } for i in qs]


def sairam(user, tenant_id, *, limite: int = 50) -> list[dict]:
    """O que deixou o perímetro: exportações e entregas de binário auditadas."""
    from nucleo.models import AuditLog

    from .models import Exportacao

    ids = _ids_visiveis(user)
    rotulos = {r.id: r.rotulo for r in registro.listar()}
    saida = [{
        "tipo": "exportacao", "recurso": e.recurso, "recurso_rotulo": rotulos.get(e.recurso, e.recurso),
        "descricao": f"{e.formato.upper()} · {e.linhas} linhas", "quem": e.usuario_nome,
        "quando": e.criada_em.isoformat(),
    } for e in Exportacao.objects.filter(tenant_id=tenant_id, recurso__in=ids).order_by("-criada_em")[:limite]]
    entregas = AuditLog.objects.filter(
        tenant_id=tenant_id, acao=AuditLog.Acao.EXPORTAR_DADOS, detalhes__entrega=True,
        detalhes__recurso__in=list(ids),
    ).order_by("-timestamp")[:limite]
    for a in entregas:
        d = a.detalhes or {}
        tamanho = d.get("bytes")
        saida.append({
            "tipo": "entrega", "recurso": d.get("recurso"), "recurso_rotulo": rotulos.get(d.get("recurso"), d.get("recurso")),
            "descricao": f"download ({d.get('especie')})" + (f" · {tamanho // 1024} KB" if tamanho else ""),
            "quem": a.usuario_nome, "quando": a.timestamp.isoformat(),
        })
    saida.sort(key=lambda l: l["quando"], reverse=True)
    return saida[:limite]
