# backend/moduloorcamento/identidade.py
"""D110 — *"o item que eu achei pelo código é mesmo o item que a publicação
está descrevendo?"*

Dois lugares do módulo tratavam **mesmo código** como **mesmo insumo** e não
olhavam mais nada: a adoção (`services.py`/`bancos.py`, que localiza o
`catalogo.Item` pelo par `(fonte, codigo_referencia)` e reescreve descrição e
unidade) e a reclassificação (o comando `reclassificar_itens_catalogo`, que
montava o de-para por `codigo__in` e deixava o **último registro lido vencer**).

Enquanto houver uma publicação por fonte e a fonte for a SINAPI — estável nos
códigos de insumo — isso funciona. Deixa de funcionar quando a fonte reaproveita
o número entre edições, que é o que tabela de prefeitura faz: o `1379` que era
*cimento CP II, KG* vira *locação de betoneira, H*, a adoção reescreve a
descrição do item do tenant e ele passa a se chamar outra coisa **carregando o
histórico do anterior** — as composições que o referenciam e as linhas orçadas
que apontam para ele continuam apontando. Ninguém vê: não há erro na tela, só um
preço diferente do que deveria ser.

**A régua do dono (21/08/2026): divergiu, não classifica e não sobrescreve —
reporta.** Este módulo é só a pergunta; quem decide o que fazer com a resposta é
quem chama.

Descrição e unidade estão nas duas pontas e respondem — mas cada uma responde de
um jeito:

- **unidade** é vocabulário curto e fechado, então a comparação é de igualdade
  sobre a forma normalizada (com as poucas grafias que as publicações alternam
  para a mesma unidade reunidas em `SINONIMOS_DE_UNIDADE`). Unidade diferente é
  sinal forte: o coeficiente da composição foi escrito contra a unidade antiga.
- **descrição** muda de redação entre edições sem mudar de item ("CIMENTO
  PORTLAND CP II-32" ganha "COMPOSTO" no meio), então igualdade estrita acusaria
  divergência em toda republicação. A comparação é de **semelhança de conjunto
  de palavras** (Jaccard): ela sobrevive a acréscimo e reordenação de termo e
  cai a quase zero quando o item é outro.

O limiar não é teto de plano: ele muda o *acerto* da conferência, não até onde o
cliente vai — é a mesma classe do `JANELA` do extrator de CEP, registrada na
§5.6 do `payment/planos.py`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Abaixo disto, as duas descrições não falam do mesmo insumo. Calibrado nos dois
# casos que importam: "CIMENTO PORTLAND CP II-32" x "CIMENTO PORTLAND COMPOSTO
# CP II-32 (revisado)" fica acima do limiar (mesmo item, republicado com outra
# redação); "CIMENTO PORTLAND CP II-32" x "LOCACAO DE BETONEIRA 400L" dá 0,00 —
# o reaproveitamento de código que o D110 descreve.
LIMIAR_SEMELHANCA = 0.55

# Grafias que as publicações alternam para a **mesma** unidade. Deliberadamente
# curta: cada linha aqui é uma divergência que o sistema deixa de reportar, e
# unidade não reportada é coeficiente lido contra a régua errada. Só entra par
# que já apareceu em publicação real.
SINONIMOS_DE_UNIDADE = {
    "UND": "UN", "UNID": "UN", "UNIDADE": "UN",
    "HORA": "H", "HR": "H", "HM": "H",
    "MESES": "MES",
    "QUILO": "KG", "QUILOGRAMA": "KG",
    "LITRO": "L", "LT": "L",
    "METRO": "M",
    "CJ": "CONJ", "CONJUNTO": "CONJ",
    "PC": "PCT", "PACOTE": "PCT",
}

# Palavras que não distinguem insumo nenhum e só inflam a semelhança quando as
# duas descrições são longas. Sem elas, "DE" e "COM" fariam duas descrições
# alheias parecerem parentes.
VAZIAS = {
    "de", "da", "do", "das", "dos", "com", "sem", "e", "em",
    "para", "por", "a", "o", "as", "os", "no", "na", "ou",
}

_NAO_ALFANUM = re.compile(r"[^0-9a-z]+")


def _sem_acento(texto) -> str:
    if texto is None:
        return ""
    decomposto = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def normalizar_unidade(unidade) -> str:
    """`m³` -> `M3`, `Und.` -> `UN`. Vazio continua vazio (e não confere nada)."""
    bruta = _NAO_ALFANUM.sub("", _sem_acento(unidade).lower()).upper()
    return SINONIMOS_DE_UNIDADE.get(bruta, bruta)


def palavras(descricao) -> set[str]:
    """`"CIMENTO PORTLAND CP II-32"` -> `{cimento, portland, cp, ii, 32}`.

    Sem acento, sem pontuação, caixa única — e sem as palavras de ligação, que
    aproximariam descrições que não têm nada a ver uma com a outra.
    """
    limpo = _NAO_ALFANUM.sub(" ", _sem_acento(descricao).lower())
    return {p for p in limpo.split() if p and p not in VAZIAS}


def semelhanca(descricao_a, descricao_b) -> float:
    """Jaccard sobre o conjunto de palavras: 1,0 é a mesma redação, 0,0 é nada
    em comum. Descrição vazia dos dois lados não diz nada — devolve 1,0, e quem
    chama trata "não há o que conferir" como "confere"."""
    a, b = palavras(descricao_a), palavras(descricao_b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True)
class Divergencia:
    """O item do catálogo e o da publicação **não são o mesmo insumo**.

    Não é erro do usuário nem dado inválido: é a pergunta que o código passou a
    fazer, respondida com "não". Quem recebe decide — a adoção recusa a
    sobrescrita, o comando deixa o item fora do lote, e os dois listam.
    """

    motivo: str  # "descrição" | "unidade" | "descrição e unidade"
    descricao_catalogo: str
    descricao_publicacao: str
    unidade_catalogo: str
    unidade_publicacao: str
    semelhanca: float

    def __str__(self) -> str:
        return (
            f"{self.motivo} não confere — no catálogo: "
            f'"{self.descricao_catalogo}" ({self.unidade_catalogo}); '
            f'na publicação: "{self.descricao_publicacao}" ({self.unidade_publicacao}). '
            "Item deixado como está; confira à mão."
        )

    def como_dict(self) -> dict:
        return {
            "motivo": self.motivo,
            "descricao_catalogo": self.descricao_catalogo,
            "descricao_publicacao": self.descricao_publicacao,
            "unidade_catalogo": self.unidade_catalogo,
            "unidade_publicacao": self.unidade_publicacao,
            "semelhanca": round(self.semelhanca, 2),
        }


def conferir(
    *,
    descricao_catalogo,
    unidade_catalogo,
    descricao_publicacao,
    unidade_publicacao,
) -> Divergencia | None:
    """`None` quando é o mesmo insumo; a `Divergencia` quando não é.

    **Silêncio de um lado não é divergência.** Item sem descrição ou sem unidade
    gravada (cadastro antigo, importação parcial) não tem como responder, e
    tratar ausência como discordância transformaria a guarda numa enxurrada de
    falso positivo — que é como uma guarda deixa de ser lida.
    """
    u_cat = normalizar_unidade(unidade_catalogo)
    u_pub = normalizar_unidade(unidade_publicacao)
    unidade_diverge = bool(u_cat) and bool(u_pub) and u_cat != u_pub

    tem_descricao = bool(palavras(descricao_catalogo)) and bool(palavras(descricao_publicacao))
    parecenca = semelhanca(descricao_catalogo, descricao_publicacao)
    descricao_diverge = tem_descricao and parecenca < LIMIAR_SEMELHANCA

    if not unidade_diverge and not descricao_diverge:
        return None
    if unidade_diverge and descricao_diverge:
        motivo = "descrição e unidade"
    elif unidade_diverge:
        motivo = "unidade"
    else:
        motivo = "descrição"
    return Divergencia(
        motivo=motivo,
        descricao_catalogo=str(descricao_catalogo or ""),
        descricao_publicacao=str(descricao_publicacao or ""),
        unidade_catalogo=str(unidade_catalogo or ""),
        unidade_publicacao=str(unidade_publicacao or ""),
        semelhanca=parecenca,
    )
