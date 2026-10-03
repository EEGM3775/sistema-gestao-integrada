# backend/nucleo/busca.py
"""Busca que não exige acento — a régua de acessibilidade do produto.

**O defeito que isto corrige.** Toda busca do sistema era `icontains` puro, que
no Postgres compara byte a byte depois de rebaixar a caixa: `fundacao` não acha
`Fundação`, `concreto` não acha `Concreto Armado` se a pessoa escrever `ç`,
`agua` não acha `Água`. Quem digita rápido, digita sem acento — e no canteiro,
no celular, com luva, ninguém vai caçar o `ç` no teclado. A pessoa conclui que o
dado não existe.

**A decisão (16/08/2026, dono):** *"quero que todo o software seja acessível,
ninguém tem que ficar digitando exatamente a palavra para conseguir achar o que
quer"*. Então a insensibilidade a acento não é recurso de um módulo: é o
comportamento padrão de **toda** busca por texto do backend, e o mesmo vale para
os filtros que rodam na tela (`frontend/src/utils/texto.ts`).

**Como.** A extensão `unaccent` do Postgres, registrada como *transform* de
`CharField`/`TextField`, e um `SearchFilter` que a interpõe antes do `icontains`.
`titulo__unaccent__icontains` vira, no SQL, `UPPER(UNACCENT(titulo)) LIKE
UPPER(UNACCENT(%s))` — os dois lados normalizados, que é o que faz `Fundação` e
`fundacao` casarem nas duas direções.

**Por que a extensão nasce no `template1`, e não numa migration.** Mesmo motivo
do PostGIS (MAP.0, ver [o init](../../infra/postgres/init/01-init-databases.sh)):
`CREATE EXTENSION unaccent` exige SUPERUSER — a extensão não é *trusted* — e o
backend roda como `erp_app`, que é de propósito um role comum, porque é disso que
a RLS FORCE depende. Criando no template, `erp_db` nasce com ela e o `test_erp_db`
de cada execução da suíte também.

**O custo, dito na cara.** `UNACCENT(coluna)` é uma chamada de função por linha,
então o índice B-tree comum da coluna não serve mais para esta busca — ela vira
varredura. Nas tabelas do produto (dezenas de milhares de linhas por tenant, já
recortadas pela RLS antes do `LIKE`) isso não aparece. Quando aparecer, o
conserto é um índice funcional por tabela quente::

    CREATE INDEX … ON tabela (UPPER(UNACCENT(coluna)) text_pattern_ops);

e não desligar a normalização, que é contrato de acessibilidade.
"""

from django.contrib.postgres.lookups import Unaccent
from django.db.models import CharField, TextField
from rest_framework import filters


def registrar_transformacoes() -> None:
    """Liga `__unaccent__` em todo campo de texto. Chamado do `NucleoConfig.ready`.

    Registrar é global por design: um campo que não aceitasse a transformação
    faria a busca dele voltar a exigir acento **em silêncio**, que é a forma de
    falha que este módulo existe para não ter.
    """
    CharField.register_lookup(Unaccent)
    TextField.register_lookup(Unaccent)


class BuscaSemAcento(filters.SearchFilter):
    """`SearchFilter` do DRF com `unaccent` interposto antes do comparador.

    **Só a comparação livre é normalizada.** O DRF dá prefixos a `search_fields`
    para pedir outro comparador — `=` exato, `^` começa-com, `@` busca de texto
    completo, `$` expressão regular. Destes, `=`, `^` e `$` continuam como estão:

    - `=` é igualdade, e quem pede igualdade quer o valor **como ele é** (um
      código, uma chave); afrouxá-lo aqui mudaria o significado de um filtro que
      outra tela usa para decidir, não para procurar.
    - `@` já é `search`, que passa pelo dicionário de texto completo do Postgres
      e **por baixo dele o `unaccent` não se encaixa como transform** — pedir
      `campo__unaccent__search` é erro de lookup, não busca melhor.
    - `$` é regex, e injetar `UNACCENT` do lado da coluna sem tocar no padrão
      daria um casamento assimétrico — pior que não normalizar.

    Sobra o caso sem prefixo, que é `icontains` e é ~toda busca do produto.

    **Campos que dependem de quem pergunta.** Se a view define
    `campos_de_busca(request)`, é ela quem diz onde procurar — buscar num campo é
    lê-lo, então documento só entra na lista para quem pode desmascará-lo (D257).
    Sem o método, valem os `search_fields` de sempre.
    """

    def get_search_fields(self, view, request):
        if hasattr(view, "campos_de_busca"):
            return view.campos_de_busca(request)
        return super().get_search_fields(view, request)

    def construct_search(self, field_name, queryset=None):
        original = super().construct_search(field_name, queryset)
        if not original.endswith("__icontains"):
            return original
        return original[: -len("__icontains")] + "__unaccent__icontains"
