# backend/moduloprancheta/disciplinas.py
"""PRA.9b — o vocabulário de disciplinas: **13 embutidas + as do cliente**.

Um lugar só resolve as três perguntas que a tela faz (qual o rótulo? qual a cor?
em que ordem?), e existe porque elas passaram a ter duas fontes. As 13 de
`Disciplina` são o piso — o que o carimbo brasileiro escreve, e de onde a
[taxonomia](taxonomia.py) adivinha a pasta no lote — e a `DisciplinaProjeto`
é o andar de cima, criada pelo próprio tenant.

**A cor mora aqui e não no frontend**, e a troca é deliberada: era um dicionário
em `pages/grade.ts`, e no momento em que o cliente pôde criar disciplina a tela
teria de inventar cor para o que não conhecia — duas fontes para o mesmo atributo,
divergindo na primeira disciplina nova. Agora o servidor responde a cor de todas,
e a tela só a pinta.

Os hexes das 13 não são tokens da Malha de propósito: precisam ser
**distinguíveis entre si** sob sol, e o acento da Malha é um por tela.
"""
from __future__ import annotations

from .models import Disciplina, DisciplinaProjeto

#: Cor e ordem das embutidas. A ordem não é alfabética: é a frequência com que o
#: canteiro consulta cada uma — Arquitetura e Estrutural vêm dez vezes mais que
#: Paisagismo, e a fileira da grade é onde isso paga.
_EMBUTIDAS: dict[str, tuple[str, int]] = {
    Disciplina.ARQUITETURA: ("#C2410C", 10),
    Disciplina.ESTRUTURAL: ("#4338CA", 20),
    Disciplina.FUNDACAO: ("#3F3F46", 30),
    Disciplina.HIDROSSANITARIO: ("#0369A1", 40),
    Disciplina.ELETRICA: ("#CA8A04", 50),
    Disciplina.INCENDIO: ("#B91C1C", 60),
    Disciplina.CLIMATIZACAO: ("#0891B2", 70),
    Disciplina.TERRAPLANAGEM: ("#78350F", 80),
    Disciplina.PAVIMENTACAO: ("#525252", 90),
    Disciplina.TOPOGRAFIA: ("#15803D", 100),
    Disciplina.IMPLANTACAO: ("#7E22CE", 110),
    Disciplina.LEGAL: ("#BE185D", 120),
    Disciplina.OUTRA: ("#9CA3AF", 900),
}

_ROTULOS = dict(Disciplina.choices)

#: Paleta de fallback para disciplina criada sem cor escolhida. Doze matizes bem
#: separados, percorridos por hash do código: estável entre sessões (a mesma
#: disciplina não muda de cor a cada carga) e sem depender de ninguém escolher.
_PALETA = (
    "#B45309", "#1D4ED8", "#047857", "#A21CAF", "#B91C1C", "#0E7490",
    "#4D7C0F", "#7C2D12", "#6D28D9", "#0F766E", "#9D174D", "#374151",
)


def cor_estavel(codigo: str) -> str:
    """A cor de quem não escolheu — derivada do código, nunca sorteada.

    Sorteio daria cor nova a cada carga da tela, e cor é justamente o que faz a
    pessoa reconhecer a disciplina sem ler. A soma dos bytes basta: o conjunto é
    pequeno, e colisão aqui custa duas disciplinas parecidas, não um defeito.
    """
    return _PALETA[sum(codigo.encode()) % len(_PALETA)]


def catalogo(scope_qs) -> list[dict]:
    """As disciplinas que este tenant tem, embutidas e próprias, já ordenadas.

    Recebe o `scope_qs` da view (e não um `tenant_id`) porque é ele que aplica o
    escopo do mixin — montar o filtro aqui seria uma segunda regra de tenancy
    fora do lugar onde o resto do módulo a aplica.

    A do tenant **sobrepõe** a embutida de mesmo código: quem quiser chamar
    `legal` de "Aprovação na prefeitura" muda o rótulo sem perder as pranchas que
    já estão marcadas com aquele slug — o documento guarda o código, não o nome.
    """
    itens: dict[str, dict] = {
        codigo: {
            "codigo": codigo,
            "nome": _ROTULOS[codigo],
            "cor": cor,
            "ordem": ordem,
            "padrao": True,
            "ativa": True,
        }
        for codigo, (cor, ordem) in _EMBUTIDAS.items()
    }

    for propria in scope_qs(DisciplinaProjeto.objects.all()):
        itens[propria.codigo] = {
            "codigo": propria.codigo,
            "nome": propria.nome,
            "cor": propria.cor or cor_estavel(propria.codigo),
            "ordem": propria.ordem,
            # `padrao` continua True quando ela **renomeia** uma embutida: para a
            # tela o que importa é se dá para apagar, e apagar a linha de uma
            # embutida só devolve o rótulo original — não some do vocabulário.
            "padrao": propria.codigo in _EMBUTIDAS,
            "ativa": propria.ativa,
            "disciplina_id": propria.disciplina_id,
        }

    return sorted(
        (i for i in itens.values() if i["ativa"]),
        key=lambda i: (i["ordem"], i["nome"]),
    )


def indice(scope_qs) -> dict[str, dict]:
    """O catálogo por código — o que os serializers usam para resolver rótulo."""
    return {i["codigo"]: i for i in catalogo(scope_qs)}


def rotulo(codigo: str, mapa: dict[str, dict] | None = None) -> str:
    """O nome de exibição, com degradação honesta.

    Tabela do tenant → embutida → **o próprio slug**. O último caso não é erro: é
    a disciplina que alguém apagou depois de marcar pranchas com ela, e mostrar
    `impermeabilizacao` é melhor do que mostrar "Outra" — que seria mentir sobre
    uma classificação que a prancha ainda carrega.
    """
    if mapa and codigo in mapa:
        return mapa[codigo]["nome"]
    return _ROTULOS.get(codigo, codigo)


def cor(codigo: str, mapa: dict[str, dict] | None = None) -> str:
    if mapa and codigo in mapa:
        return mapa[codigo]["cor"]
    embutida = _EMBUTIDAS.get(codigo)
    return embutida[0] if embutida else cor_estavel(codigo)
