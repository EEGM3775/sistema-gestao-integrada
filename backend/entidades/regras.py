"""A regra de quem é dono de cada lançamento — docs/modulos/entidades.md §2.

Um lugar só: o `save()` do título, do centro de custo, da nota e da carteira
chama `entidade_do_lancamento` quando ninguém informou a entidade, e a migração
de dados repete a mesma ordem. Quem cria título em outro módulo (SCM, PDCA,
carteira, importação) não precisa saber da regra.
"""
from __future__ import annotations

from .models import Entidade, ParticipacaoEmpreendimento


class SemEntidade(Exception):
    """O tenant não tem entidade do grupo — não acontece depois da migração."""


def do_grupo(tenant_id):
    return Entidade.objects.filter(tenant_id=tenant_id, externa=False)


def matriz(tenant_id) -> Entidade:
    """A matriz do tenant; sem papel de matriz, a primeira entidade do grupo.

    Toda conta tem ao menos uma (docs/modulos/entidades.md §1): a conta nova, que
    nasceu depois da migração, ganha a matriz aqui, na primeira vez que alguém
    pergunta — com o nome do tenant e sem documento (a tela pede o CNPJ).
    """
    grupo = do_grupo(tenant_id).filter(ativa=True)
    achada = grupo.filter(papel=Entidade.Papel.MATRIZ).order_by("entidade_id").first() or grupo.order_by("entidade_id").first()
    if achada is not None:
        return achada
    from nucleo.models import Tenant

    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        raise SemEntidade(f"Tenant {tenant_id} não existe.")
    return Entidade.objects.create(tenant=tenant, nome=tenant.nome, papel=Entidade.Papel.MATRIZ)


def modo_simples(tenant_id) -> bool:
    """Uma entidade do grupo só: sem seletor, sem recorte, sem intercompany."""
    return do_grupo(tenant_id).count() <= 1


def dona_do_empreendimento(empreendimento) -> int | None:
    """A entidade do grupo que é dona do empreendimento, ou `None` se o dono é de
    fora (o empreendimento em que o tenant só executa)."""
    if empreendimento is None:
        return None
    propria = getattr(empreendimento, "entidade_propria", None)
    if propria is not None:
        return None if propria.externa else propria.pk
    participacoes = list(
        ParticipacaoEmpreendimento.objects.filter(empreendimento=empreendimento)
        .select_related("entidade").order_by("-administradora", "-cota", "participacao_id")
    )
    if not participacoes:
        return matriz(empreendimento.tenant_id).pk
    for p in participacoes:
        if not p.entidade.externa:
            return p.entidade_id
    return None


def entidade_da_obra(obra) -> int:
    """Quem executa a obra: a dela, ou a dona do empreendimento do grupo, ou a matriz."""
    if obra.entidade_id:
        return obra.entidade_id
    dona = dona_do_empreendimento(obra.empreendimento) if obra.empreendimento_id else None
    return dona or matriz(obra.tenant_id).pk


def entidade_do_lancamento(tenant_id, *, empreendimento=None, obra=None) -> int:
    """§2: obra → a da obra; empreendimento do grupo → a dona; senão a matriz."""
    if obra is not None:
        return entidade_da_obra(obra)
    dona = dona_do_empreendimento(empreendimento) if empreendimento is not None else None
    return dona or matriz(tenant_id).pk


def preencher(objeto, *, empreendimento_attr="empreendimento", obra_attr="obra") -> None:
    """Põe a entidade no objeto que ainda não tem (o `save()` dos modelos chama)."""
    if getattr(objeto, "entidade_id", None):
        return
    obra = getattr(objeto, obra_attr, None) if obra_attr and getattr(objeto, f"{obra_attr}_id", None) else None
    emp = (
        getattr(objeto, empreendimento_attr, None)
        if empreendimento_attr and getattr(objeto, f"{empreendimento_attr}_id", None) else None
    )
    objeto.entidade_id = entidade_do_lancamento(objeto.tenant_id, empreendimento=emp, obra=obra)
