# backend/moduloorcamento/carga.py
"""ORC.8 — o motor da carga: do ZIP oficial às publicações do mês.

**O calcanhar do módulo nunca foi cálculo, é dado fresco.** Manter 27 UFs × 3
regimes × 12 meses à mão não escala, e até aqui a `tasks.py` só sabia *avisar*
que a publicação envelheceu. Este arquivo fecha isso.

Três coisas moram aqui e é deliberado que morem juntas:

1. **A escrita**, que é a mesma da ORC.0. `gravar_itens` e `gravar_analitica`
   nasceram como métodos do `importar_base_referencial` e subiram para cá
   inteiras — o comando passou a chamá-las. Duplicar o *upsert* criaria duas
   verdades sobre o que "reimportar" significa, e a divergência apareceria como
   preço errado, não como erro.
2. **A leitura do formato largo** (SINAPI de 01/2025 em diante), que o comando
   não sabe ler porque ele foi escrito para o formato longo: uma linha por item,
   uma coluna de preço. No largo, as 27 UFs são **colunas**, e o mesmo arquivo
   rende 54 publicações.
3. **A orquestração** de uma corrida: baixar (ou receber o upload), ler, resumir,
   conferir a classe, gravar, e escrever em `CargaBase` o que aconteceu.

Quatro regras do dado brasileiro que este arquivo respeita e que quem for mexer
precisa saber antes de tocar em qualquer linha (§4.1 da planta):

- **Preço em branco numa UF significa ausência, não zero.** O cabeçalho do
  próprio arquivo declara: *"Preço em branco para determinado estado significa
  que não houve pesquisa"*. Gravar `custo_unitario = 0` faria a planilha aceitar
  um insumo a R$ 0,00 sem ninguém perceber — então a linha simplesmente não
  entra naquela publicação, e a contagem diz quantas ficaram de fora.
- **`SD` = sem desoneração = regime `onerado`**; `CD` = com desoneração =
  `desonerado`; `SE` = sem encargos. A dobra de nomenclatura é da fonte, e
  trocar os dois primeiros inverte o custo de toda composição com mão de obra.
- **A analítica é nacional e única.** Ela vai para `AnaliticaNacional`, uma vez
  por fonte + mês, e não replicada nas 54 publicações — ver o docstring do
  modelo para a conta que justifica isso.
- **Classe que não sabemos ler para a carga** (D112). A base-mãe é global: o que
  entra aqui todos os tenants enxergam, e classe traduzida errado é alavanca de
  preço para a plataforma inteira de uma vez.
"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from funcoesimpexp.formatos.leitura import normalizar
from payment import planos

from . import oficial, services
from .leitura import EXTRAS_POR_ARQUIVO, OBRIGATORIOS, detectar_colunas
from .models import (
    AnaliticaNacional,
    BaseReferencial,
    CargaBase,
    ComposicaoReferenciaItem,
    Fonte,
    FonteOficial,
    InsumoReferencia,
)

logger = logging.getLogger(__name__)

LOTE = 1_000

UFS: tuple[str, ...] = (
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT",
    "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
)

# As seis abas do arquivo nacional e o que cada sigla quer dizer. A tabela é o
# ponto onde a dobra de nomenclatura da fonte é resolvida **uma vez**: aqui, e
# não espalhada em condicionais pelo motor.
ABAS_SINAPI: dict[str, tuple[str, str]] = {
    # aba: (tipo do item, regime de encargos)
    "ISD": (InsumoReferencia.Tipo.INSUMO, BaseReferencial.Regime.ONERADO),
    "ICD": (InsumoReferencia.Tipo.INSUMO, BaseReferencial.Regime.DESONERADO),
    "ISE": (InsumoReferencia.Tipo.INSUMO, BaseReferencial.Regime.SEM_ENCARGOS),
    "CSD": (InsumoReferencia.Tipo.COMPOSICAO, BaseReferencial.Regime.ONERADO),
    "CCD": (InsumoReferencia.Tipo.COMPOSICAO, BaseReferencial.Regime.DESONERADO),
    "CSE": (InsumoReferencia.Tipo.COMPOSICAO, BaseReferencial.Regime.SEM_ENCARGOS),
}

# Quantas colunas de UF bastam para uma linha ser tida como o cabeçalho de UFs.
# Cinco é folga contra falso positivo (uma linha de observação com "SP" solto) e
# ainda reconhece um arquivo parcial, com poucos estados pesquisados.
MINIMO_DE_UFS = 5

# Até onde procurar o cabeçalho. O arquivo nacional traz um bloco de título e
# notas antes da tabela; 25 linhas é o mesmo alcance que o `detectar_colunas` da
# leitura longa usa, e por isso o número é o mesmo aqui.
LINHAS_DE_CABECALHO = 25


class CargaInvalida(Exception):
    """O arquivo chegou, mas não é o que a carga sabe ler."""


# ---------------------------------------------------------------------------
# Escrita — compartilhada com o comando da ORC.0
# ---------------------------------------------------------------------------


@transaction.atomic
def gravar_itens(base, tipo, pendentes: dict[str, InsumoReferencia]) -> tuple[int, int]:
    """Upsert em lote: a publicação é reimportável sem duplicar nem perder FK.

    Devolve `(novos, alterados)`. Era `Command._gravar_itens`; virou função para
    o comando e a carga escreverem pelo mesmo caminho.
    """
    existentes = {
        item.codigo: item
        for item in InsumoReferencia.objects.filter(base=base, tipo=tipo)
    }
    novos, alterados = [], []
    for codigo, candidato in pendentes.items():
        atual = existentes.get(codigo)
        if atual is None:
            novos.append(candidato)
            continue
        atual.descricao = candidato.descricao
        atual.unidade = candidato.unidade
        atual.custo_unitario = candidato.custo_unitario
        atual.grupo = candidato.grupo
        alterados.append(atual)
    if novos:
        InsumoReferencia.objects.bulk_create(novos, batch_size=LOTE)
    if alterados:
        InsumoReferencia.objects.bulk_update(
            alterados, ["descricao", "unidade", "custo_unitario", "grupo"], batch_size=LOTE
        )
    return len(novos), len(alterados)


@transaction.atomic
def gravar_analitica(base, composicoes: dict, filhos: dict, vinculos: list) -> tuple[int, int, int]:
    """Grava a analítica **na própria publicação** (o formato longo).

    Devolve `(composicoes_novas, filhos_novos, componentes)`. Era
    `Command._gravar_analitica`.

    A analítica é a fonte mais rica da publicação — ela também declara as
    composições e os insumos citados. Então, se a empresa só tem este arquivo, a
    base ainda fica utilizável: o que não veio da sintética nasce aqui.
    """
    faltando = []
    existentes_comp = set(
        InsumoReferencia.objects.filter(
            base=base, tipo=InsumoReferencia.Tipo.COMPOSICAO
        ).values_list("codigo", flat=True)
    )
    for codigo, dados in composicoes.items():
        if codigo in existentes_comp:
            continue
        faltando.append(InsumoReferencia(
            base=base, codigo=codigo[:30], tipo=InsumoReferencia.Tipo.COMPOSICAO,
            descricao=dados["descricao"] or codigo, unidade=dados["unidade"],
        ))
    if faltando:
        InsumoReferencia.objects.bulk_create(faltando, batch_size=LOTE)

    por_chave = {
        (i.tipo, i.codigo): i.pk for i in InsumoReferencia.objects.filter(base=base)
    }
    novos_filhos = []
    for codigo, dados in filhos.items():
        if (dados["tipo"], codigo) in por_chave:
            continue
        # Um código pode existir com o outro tipo (a sintética já o trouxe);
        # nesse caso reaproveita em vez de duplicar.
        outro = (
            InsumoReferencia.Tipo.COMPOSICAO
            if dados["tipo"] == InsumoReferencia.Tipo.INSUMO
            else InsumoReferencia.Tipo.INSUMO
        )
        if (outro, codigo) in por_chave:
            continue
        novos_filhos.append(InsumoReferencia(
            base=base, codigo=codigo[:30], tipo=dados["tipo"],
            descricao=dados["descricao"] or codigo, unidade=dados["unidade"],
        ))
    if novos_filhos:
        InsumoReferencia.objects.bulk_create(novos_filhos, batch_size=LOTE)

    por_codigo: dict[str, int] = {}
    for tipo, codigo, pk in InsumoReferencia.objects.filter(base=base).values_list(
        "tipo", "codigo", "pk"
    ):
        # Composição tem precedência no índice: o pai de um vínculo é sempre
        # composição, e o filho é resolvido pelo mesmo código.
        if codigo not in por_codigo or tipo == InsumoReferencia.Tipo.COMPOSICAO:
            por_codigo[codigo] = pk

    pais = {por_codigo[c] for c in composicoes if c in por_codigo}
    ComposicaoReferenciaItem.objects.filter(composicao_id__in=pais).delete()
    componentes, vistos = [], set()
    for cod_comp, cod_item, coeficiente in vinculos:
        pai, filho = por_codigo.get(cod_comp), por_codigo.get(cod_item)
        if pai is None or filho is None or pai == filho or (pai, filho) in vistos:
            continue
        vistos.add((pai, filho))
        componentes.append(ComposicaoReferenciaItem(
            composicao_id=pai, filho_id=filho, coeficiente=coeficiente,
        ))
    if componentes:
        ComposicaoReferenciaItem.objects.bulk_create(componentes, batch_size=LOTE)
    return len(faltando), len(novos_filhos), len(componentes)


def recontar(base: BaseReferencial) -> None:
    """Reescreve os totais da publicação a partir do que está no banco."""
    base.total_insumos = InsumoReferencia.objects.filter(
        base=base, tipo=InsumoReferencia.Tipo.INSUMO
    ).count()
    base.total_composicoes = InsumoReferencia.objects.filter(
        base=base, tipo=InsumoReferencia.Tipo.COMPOSICAO
    ).count()
    base.save(update_fields=["total_insumos", "total_composicoes", "importada_em"])


# ---------------------------------------------------------------------------
# Leitura do formato largo (SINAPI, 01/2025 em diante)
# ---------------------------------------------------------------------------


@dataclass
class TabelaLarga:
    """Uma aba do arquivo nacional já lida: itens em linhas, UFs em colunas.

    O formato compacto é de propósito. Guardar 12,5 mil `InsumoReferencia` × 27
    UFs de uma vez seriam ~340 mil objetos vivos antes da primeira escrita; aqui
    são 12,5 mil tuplas com um dicionário de preços cada, e as publicações são
    montadas **uma UF por vez**, descartando a anterior.
    """

    tipo: str
    regime: str
    ufs: tuple[str, ...]
    linhas: list[tuple[str, str, str, str, dict[str, Decimal]]] = field(default_factory=list)
    sem_preco: int = 0

    def itens_da_uf(self, uf: str) -> dict[str, InsumoReferencia]:
        pendentes: dict[str, InsumoReferencia] = {}
        for codigo, descricao, unidade, classe, precos in self.linhas:
            preco = precos.get(uf)
            if preco is None:
                continue  # ausência de pesquisa, não zero
            pendentes[codigo] = InsumoReferencia(
                codigo=codigo[:30], tipo=self.tipo, descricao=descricao[:500],
                unidade=unidade[:20], custo_unitario=preco, grupo=classe[:150],
            )
        return pendentes

    @property
    def classes(self) -> set[str]:
        return {linha[3].strip() for linha in self.linhas if linha[3].strip()}


def abrir_pacote(conteudo: bytes, nome: str = "") -> dict[str, bytes]:
    """Devolve `{nome_do_arquivo: bytes}` — do ZIP ou do XLSX solto.

    Aceitar o XLSX direto não é conveniência: no mês em que a Caixa mudar o
    empacotamento, o plano B (enviar o arquivo à mão) tem de continuar valendo
    com o que a pessoa tiver em disco.

    **A ordem das duas perguntas importa, e é contraintuitiva:** um `.xlsx` *é*
    um ZIP — o formato OOXML é um pacote comprimido de XMLs. Perguntar primeiro
    "é ZIP?" faz a planilha solta ser aberta como pacote, e o que sai são
    `sheet1.xml`, `styles.xml` e companhia, com a mensagem de erro reclamando que
    não há planilha dentro de uma planilha. Por isso a extensão decide antes.
    """
    if nome.lower().endswith((".xlsx", ".xlsm")):
        return {nome: conteudo}
    if not zipfile.is_zipfile(io.BytesIO(conteudo)):
        raise CargaInvalida(
            "O arquivo não é um ZIP nem uma planilha .xlsx. Confira se a URL "
            "aponta para o pacote oficial e não para a página que o anuncia."
        )
    dentro: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
        for info in pacote.infolist():
            if info.is_dir():
                continue
            # Nome com caminho absoluto ou `..` é a armadilha clássica do zip;
            # aqui nada é escrito em disco, mas o nome ainda vira rótulo na tela.
            limpo = info.filename.replace("\\", "/").split("/")[-1]
            if not limpo or limpo.startswith("."):
                continue
            dentro[limpo] = pacote.read(info)
    if not dentro:
        raise CargaInvalida("O ZIP veio vazio.")
    return dentro


def escolher_planilha(dentro: dict[str, bytes]) -> tuple[str, bytes]:
    """A planilha de referência é a maior `.xlsx` do pacote.

    O pacote nacional traz também mão de obra, famílias e manutenções — arquivos
    reais, menores, que não são a tabela de preço. Escolher pelo tamanho acerta
    sem depender do nome, que é o que muda entre publicações.
    """
    planilhas = {n: b for n, b in dentro.items() if n.lower().endswith(".xlsx")}
    if not planilhas:
        raise CargaInvalida(
            f"Nenhuma planilha .xlsx no pacote (veio: {', '.join(sorted(dentro))[:200]})."
        )
    nome = max(planilhas, key=lambda n: len(planilhas[n]))
    return nome, planilhas[nome]


def _abrir_workbook(conteudo: bytes, *, formulas: bool = False):
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - declarada em requirements
        raise CargaInvalida("openpyxl não instalado — necessário para ler .xlsx.") from exc
    return load_workbook(
        filename=io.BytesIO(conteudo), read_only=True, data_only=not formulas
    )


def _cabecalho_largo(linhas: list[list]) -> tuple[int, dict[str, int], dict[str, int]]:
    """Acha, no bloco de cabeçalho, a linha dos campos e a linha das UFs.

    Elas podem ser a mesma linha ou duas linhas diferentes — o arquivo oficial já
    apareceu das duas formas, e presumir uma delas é o tipo de aposta que quebra
    calada num mês qualquer. Devolve `(primeira_linha_de_dado, campos, ufs)`.
    """
    campos: dict[str, int] = {}
    linha_campos = -1
    ufs: dict[str, int] = {}
    linha_ufs = -1

    for indice, linha in enumerate(linhas[:LINHAS_DE_CABECALHO]):
        celulas = [normalizar(c) for c in linha]
        if not any(celulas):
            continue

        achados: dict[str, int] = {}
        for posicao, celula in enumerate(celulas):
            if celula in {"codigo", "codigo do insumo", "codigo da composicao",
                          "codigo insumo", "codigo composicao"}:
                achados.setdefault("codigo", posicao)
            elif celula in {"descricao", "descricao do insumo", "descricao da composicao"}:
                achados.setdefault("descricao", posicao)
            elif celula in {"unidade", "unidade de medida", "und", "unid"}:
                achados.setdefault("unidade", posicao)
            elif celula in {"classificacao", "classificacao do insumo", "classe", "grupo"}:
                achados.setdefault("grupo", posicao)
        if linha_campos < 0 and {"codigo", "descricao", "unidade"} <= set(achados):
            campos, linha_campos = achados, indice

        na_linha = {
            celula.upper(): posicao
            for posicao, celula in enumerate(celulas)
            if celula.upper() in UFS
        }
        if len(na_linha) > len(ufs):
            ufs, linha_ufs = na_linha, indice

    if linha_campos < 0:
        raise CargaInvalida(
            "Não reconheci o cabeçalho da aba (esperava Código, Descrição e Unidade)."
        )
    if len(ufs) < MINIMO_DE_UFS:
        raise CargaInvalida(
            f"A aba não parece estar no formato largo — achei {len(ufs)} coluna(s) de "
            "UF. Publicação anterior a 01/2025 é do formato longo: importe pelo "
            "comando `importar_base_referencial`, um arquivo por UF."
        )
    return max(linha_campos, linha_ufs) + 1, campos, ufs


def _coluna_crua(workbook, nome_aba: str, posicao: int | None) -> list:
    """Uma coluna só, sem resolver valor — para ler a fórmula por trás da célula.

    Materializa a coluna e não a aba: são ~8 mil strings em vez de meio milhão
    de células, e o teto de memória da carga é do dono (§5.5b do planos.py).
    """
    if posicao is None:
        return []
    return [_celula(list(linha), posicao) for linha in workbook[nome_aba].iter_rows(values_only=True)]


def ler_aba_larga(workbook, nome_aba: str, tipo: str, regime: str, formulas=None) -> TabelaLarga:
    """Lê uma aba `ISD`/`ICD`/`ISE`/`CSD`/`CCD`/`CSE` inteira.

    `formulas` é o mesmo arquivo aberto sem resolver valor (`data_only=False`).
    Existe por causa da coluna de código das abas de composição, que é um
    `=HYPERLINK(...)` cujo valor em cache é `0` — ver `codigo_de_formula`.
    """
    planilha = workbook[nome_aba]
    linhas = [list(linha) for linha in planilha.iter_rows(values_only=True)]
    inicio, campos, ufs = _cabecalho_largo(linhas)
    tabela = TabelaLarga(tipo=tipo, regime=regime, ufs=tuple(sorted(ufs)))
    coluna_codigo = campos.get("codigo")
    crus = _coluna_crua(formulas, nome_aba, coluna_codigo) if formulas is not None else []

    for indice, linha in enumerate(linhas[inicio:], start=inicio):
        codigo = _texto(_celula(linha, coluna_codigo))
        if indice < len(crus):
            da_formula = codigo_de_formula(crus[indice])
            if da_formula:
                codigo = da_formula
        descricao = _texto(_celula(linha, campos.get("descricao")))
        if not codigo or not descricao:
            continue
        precos: dict[str, Decimal] = {}
        for uf, posicao in ufs.items():
            valor = numero_ou_ausencia(_celula(linha, posicao))
            if valor is None:
                continue  # não houve pesquisa naquela UF — e isso não é zero
            precos[uf] = valor
        if not precos:
            tabela.sem_preco += 1
            continue
        tabela.linhas.append((
            codigo,
            descricao,
            _texto(_celula(linha, campos.get("unidade"))),
            _texto(_celula(linha, campos.get("grupo"))),
            precos,
        ))
    # A gravação é **por código** (`itens_da_uf` monta um dicionário). Código
    # repetido não duplica linha: apaga a anterior. Se a aba trouxe muita linha
    # e pouco código distinto, seguir daqui grava um punhado de itens no lugar
    # da publicação inteira — e foi exatamente o que aconteceu em 08/2026, com
    # um "OK" na tela. Recusar é o único jeito de isso não passar calado.
    distintos = {linha[0] for linha in tabela.linhas}
    if len(tabela.linhas) >= 100 and len(distintos) * 2 < len(tabela.linhas):
        raise CargaInvalida(
            f"A aba {nome_aba} tem {len(tabela.linhas)} linhas de dado e só "
            f"{len(distintos)} código(s) distinto(s) — a gravação é por código, "
            "então isto gravaria uma fração da publicação. A causa conhecida é a "
            "coluna de código vir como fórmula (=HYPERLINK) e ser lida pelo valor "
            "em cache, que é 0 em toda linha."
        )
    return tabela


def ler_analitica_nacional(workbook) -> tuple[list[dict], str]:
    """Acha a aba analítica **pelo cabeçalho**, não pelo nome.

    O nome dessa aba já variou entre publicações; as colunas não. Procurar pelo
    que o arquivo declara é o mesmo princípio do `detectar_colunas` da ORC.0 —
    e é o que faz a carga sobreviver a um rename da Caixa.
    """
    for nome in workbook.sheetnames:
        if normalizar(nome).upper() in ABAS_SINAPI:
            continue
        planilha = workbook[nome]
        linhas = []
        for indice, linha in enumerate(planilha.iter_rows(values_only=True)):
            linhas.append(list(linha))
            if indice >= LINHAS_DE_CABECALHO:
                break
        mapa, cabecalho, _ = detectar_colunas(
            linhas, OBRIGATORIOS["analitica"], extras=EXTRAS_POR_ARQUIVO.get("analitica")
        )
        if mapa is None:
            continue
        return _colher_analitica(workbook[nome], mapa, cabecalho), nome
    return [], ""


def _colher_analitica(planilha, mapa: dict[str, int], cabecalho: int) -> list[dict]:
    colhidas: list[dict] = []
    for indice, linha in enumerate(planilha.iter_rows(values_only=True)):
        if indice <= cabecalho:
            continue
        linha = list(linha)
        cod_comp = _limpar_codigo(_celula(linha, mapa.get("codigo_composicao")))
        cod_item = _limpar_codigo(_celula(linha, mapa.get("codigo_item")))
        if not cod_comp or not cod_item:
            continue
        # Coeficiente zero é linha sem consumo: ela não muda o custo e ainda
        # ocuparia uma das ~67 mil linhas do mês, então não entra.
        coeficiente = numero_ou_ausencia(_celula(linha, mapa.get("coeficiente")))
        if coeficiente is None:
            continue
        tipo_declarado = normalizar(_celula(linha, mapa.get("tipo_item")))
        colhidas.append({
            "codigo_composicao": cod_comp[:30],
            "codigo_item": cod_item[:30],
            "coeficiente": coeficiente,
            "descricao_item": _texto(_celula(linha, mapa.get("descricao_item")))[:500],
            "unidade_item": _texto(_celula(linha, mapa.get("unidade_item")))[:20],
            # "COMPOSICAO"/"COMPOSIÇÃO" na coluna de tipo indica composição
            # auxiliar aninhada; o resto é insumo.
            "tipo_item": (
                InsumoReferencia.Tipo.COMPOSICAO
                if "composicao" in tipo_declarado
                else InsumoReferencia.Tipo.INSUMO
            ),
            "descricao_composicao": _texto(_celula(linha, mapa.get("descricao_composicao")))[:500],
            "unidade_composicao": _texto(_celula(linha, mapa.get("unidade_composicao")))[:20],
        })
    return colhidas


def _celula(linha: list, posicao: int | None):
    if posicao is None or posicao >= len(linha):
        return None
    return linha[posicao]


def numero_ou_ausencia(valor) -> Decimal | None:
    """`para_decimal` estrito — e a diferença é a razão de esta função existir.

    O `para_decimal` do motor devolve `Decimal("0")` para célula vazia **e** para
    texto que ele não soube ler ("-", "N/A", "sem pesquisa"). É a escolha certa
    lá, onde zero é um total que ainda vai ser somado. Aqui ela seria exatamente
    a armadilha que a regra 1 do §4.1 descreve: preço em branco numa UF
    significa **ausência**, não zero, e um insumo gravado a R$ 0,00 entra na
    planilha do cliente sem ninguém perceber.

    Zero também vira ausência. Não é interpretação: a SINAPI não publica insumo
    a zero, então um zero nesta coluna é quase certamente a mesma coisa que o
    branco — e errar para "não tenho o preço" é recuperável, errar para "custa
    nada" não é.
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, str):
        texto = valor.strip().replace("R$", "").replace(" ", "")
        if "," in texto and "." in texto:
            texto = texto.replace(".", "").replace(",", ".")
        elif "," in texto:
            texto = texto.replace(",", ".")
        try:
            numero = Decimal(texto)
        except (InvalidOperation, ValueError):
            return None
    else:
        try:
            numero = Decimal(str(valor))
        except (InvalidOperation, ValueError):
            return None
    return numero if numero > 0 else None


def _texto(valor) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip()
    return texto[:-2] if texto.endswith(".0") and texto[:-2].isdigit() else texto


def _limpar_codigo(valor) -> str:
    if valor in (None, ""):
        return ""
    codigo = str(valor).strip()
    return codigo[:-2] if codigo.endswith(".0") else codigo


# O código da composição nas abas CSD/CCD/CSE **não é um número**: é um
# `=HYPERLINK(...)` que salta para a linha da composição na aba Analítico. O
# valor que o Excel deixou em cache nessas células é `0`, então ler a planilha
# por valor — `data_only=True`, que é o certo para o preço — devolve o mesmo
# código para todas as linhas, o dicionário por código colapsa e a publicação
# inteira vira **uma** composição. Foi assim que a carga de 08/2026 gravou 81
# composições onde havia ~680 mil, com um "OK" na tela.
#
# O código verdadeiro aparece duas vezes dentro da fórmula: no `MATCH(...)` que
# acha a linha e no rótulo exibido, que é o último argumento. Lemos o rótulo
# primeiro porque é ele que a Caixa mostra na planilha; o `MATCH` é a rede.
_CODIGO_NO_ROTULO = re.compile(r',\s*"?(\d+)"?\s*\)\s*$')
_CODIGO_NO_MATCH = re.compile(r'MATCH\(\s*"?(\d+)"?\s*,')


def codigo_de_formula(valor) -> str:
    """O código de dentro do `=HYPERLINK(...)`. `""` quando não é fórmula."""
    if not isinstance(valor, str) or not valor.startswith("="):
        return ""
    for padrao in (_CODIGO_NO_ROTULO, _CODIGO_NO_MATCH):
        achado = padrao.search(valor)
        if achado:
            return achado.group(1)
    return ""


# ---------------------------------------------------------------------------
# A corrida
# ---------------------------------------------------------------------------


@dataclass
class Leitura:
    """O arquivo já entendido — antes de qualquer escrita.

    É este objeto que o **resumo antes de gravar** descreve. A importação é
    idempotente e conferir 800 mil linhas seria teatro; o que resolve é dizer
    quantos insumos, composições e linhas analíticas entram, por publicação — e
    é aí que se percebe o arquivo errado.
    """

    tabelas: list[TabelaLarga] = field(default_factory=list)
    analitica: list[dict] = field(default_factory=list)
    aba_analitica: str = ""
    planilha: str = ""
    avisos: list[str] = field(default_factory=list)
    # ORC.8b — os três campos que a EMBASA trouxe, e que ficam vazios na SINAPI.
    #
    # `variante` é o eixo de identidade que uma fonte pode ter **além** de UF,
    # mês e regime: a EMBASA publica, para o mesmo semestre e o mesmo regime,
    # seis tabelas com os mesmos códigos e preços diferentes, uma por convenção
    # coletiva. Sem este eixo elas colidiriam na chave da publicação e a última
    # carga sobrescreveria as cinco anteriores — silenciosamente, porque o
    # `update_or_create` faria exatamente o que lhe pedem.
    #
    # `competencia` é a data-base que o **artefato** declara. O arquivo nacional
    # da SINAPI não a declara (ela vem do nome e de quem pede a carga); o PDF da
    # EMBASA declara ("Relatório de Serviços Junho/2026"), e a publicação de
    # semestre torna adivinhar o mês pela defasagem um palpite ruim.
    variante: str = ""
    competencia: date | None = None
    rotulo: str = ""
    extras: dict = field(default_factory=dict)

    @property
    def publicacoes(self) -> list[tuple[str, str]]:
        """`(uf, regime)` de tudo que esta leitura produziria, sem repetir.

        A `variante` não entra na tupla porque ela é do **documento**, não da
        linha: uma leitura tem uma variante só, e repeti-la em cada par seria
        carregar a mesma constante por toda a gravação.
        """
        pares = {(uf, t.regime) for t in self.tabelas for uf in t.ufs}
        return sorted(pares)

    @property
    def classes(self) -> set[str]:
        return {
            classe
            for tabela in self.tabelas
            if tabela.tipo == InsumoReferencia.Tipo.INSUMO
            for classe in tabela.classes
        }

    def resumo(self) -> dict:
        por_publicacao: dict[str, dict] = {}
        for tabela in self.tabelas:
            rotulo_tipo = (
                "insumos" if tabela.tipo == InsumoReferencia.Tipo.INSUMO else "composicoes"
            )
            for uf in tabela.ufs:
                chave = f"{uf}/{tabela.regime}"
                alvo = por_publicacao.setdefault(
                    chave, {"uf": uf, "regime": tabela.regime, "insumos": 0, "composicoes": 0}
                )
                alvo[rotulo_tipo] += sum(1 for linha in tabela.linhas if uf in linha[4])
        return {
            "planilha": self.planilha,
            "aba_analitica": self.aba_analitica,
            "publicacoes": sorted(por_publicacao.values(), key=lambda p: (p["uf"], p["regime"])),
            "total_publicacoes": len(por_publicacao),
            "linhas_analiticas": len(self.analitica),
            "itens_sem_preco_em_nenhuma_uf": sum(t.sem_preco for t in self.tabelas),
            "variante": self.variante,
            "rotulo": self.rotulo,
            "competencia_lida": (
                self.competencia.isoformat() if self.competencia else ""
            ),
            **self.extras,
            "avisos": self.avisos,
        }


def ler_pacote(conteudo: bytes, nome: str = "", fonte: str = Fonte.SINAPI) -> Leitura:
    """Do bytes ao `Leitura` — sem tocar no banco.

    `fonte` escolhe o leitor, e o default é a SINAPI porque ela foi a única por
    toda a ORC.8: quem já chamava esta função continua chamando igual. O despacho
    é uma condicional e não um registro de plugins de propósito — são dois
    formatos, e uma tabela de despacho para dois casos esconde mais do que
    organiza. Quando for o terceiro, vira tabela.
    """
    if fonte == Fonte.EMBASA:
        # Import tardio: `embasa` lê `Leitura`, `TabelaLarga` e `CargaInvalida`
        # daqui, e o par só não é ciclo porque este lado o resolve na chamada.
        from . import embasa

        return embasa.ler_documento(conteudo, nome)

    dentro = abrir_pacote(conteudo, nome)
    nome_planilha, bytes_planilha = escolher_planilha(dentro)
    leitura = Leitura(planilha=nome_planilha)
    workbook = _abrir_workbook(bytes_planilha)
    formulas = _abrir_workbook(bytes_planilha, formulas=True)
    try:
        presentes = {
            normalizar(aba).upper(): aba
            for aba in workbook.sheetnames
        }
        for sigla, (tipo, regime) in ABAS_SINAPI.items():
            aba = presentes.get(sigla)
            if aba is None:
                continue
            leitura.tabelas.append(ler_aba_larga(workbook, aba, tipo, regime, formulas))
        if not leitura.tabelas:
            # A causa quase sempre é a mesma, e o erro precisa dizê-la: o
            # arquivo é do formato **longo** (1 ZIP por UF × regime, até
            # 12/2024), que esta porta não lê e o comando lê. Sem esta frase, a
            # pessoa fica olhando uma lista de nomes de aba sem saber o que fazer.
            raise CargaInvalida(
                "Nenhuma das abas do formato nacional (ISD/ICD/ISE/CSD/CCD/CSE) foi "
                f"encontrada em {nome_planilha}. Abas vistas: "
                f"{', '.join(workbook.sheetnames)[:200]}.\n"
                "Publicação anterior a 01/2025 é do formato longo — importe pelo "
                "comando `importar_base_referencial`, um arquivo por UF."
            )
        leitura.analitica, leitura.aba_analitica = ler_analitica_nacional(workbook)
        if not leitura.analitica:
            leitura.avisos.append(
                "Nenhuma aba analítica reconhecida — as composições entram com o custo "
                "sintético, mas sem memória de cálculo."
            )
    finally:
        workbook.close()
        formulas.close()

    if len(leitura.publicacoes) > planos.ORCAMENTO_CARGA_TETO_PUBLICACOES:
        raise CargaInvalida(
            f"A leitura produziria {len(leitura.publicacoes)} publicações, acima do teto "
            f"de {planos.ORCAMENTO_CARGA_TETO_PUBLICACOES} (payment/planos.py §5.5b). "
            "Layout inesperado quase sempre aparece assim: colunas demais lidas como UF."
        )
    return leitura


@transaction.atomic
def gravar_analitica_nacional(fonte: str, competencia: date, linhas: list[dict]) -> int:
    """Reescreve a analítica daquele fonte + mês. Idempotente por definição:
    apaga a competência e regrava, porque uma republicação da Caixa pode
    **remover** um componente, e `update_or_create` nunca removeria."""
    if not linhas:
        return 0
    AnaliticaNacional.objects.filter(fonte=fonte, competencia=competencia).delete()
    vistos: set[tuple[str, str]] = set()
    objetos = []
    for linha in linhas:
        chave = (linha["codigo_composicao"], linha["codigo_item"])
        if chave in vistos:
            continue
        vistos.add(chave)
        objetos.append(AnaliticaNacional(fonte=fonte, competencia=competencia, **linha))
    AnaliticaNacional.objects.bulk_create(objetos, batch_size=LOTE)
    return len(objetos)


def gravar_publicacoes(
    leitura: Leitura, fonte: str, competencia: date, *,
    url_origem: str = "", por: str = "", progresso=None,
) -> dict:
    """Materializa as publicações da leitura. Uma UF por vez, e é de propósito.

    Escrever tudo numa transação só seria 54 publicações × ~17 mil linhas num
    lock só — e um erro na última desfaria as 53 boas. Cada publicação é
    autocontida: a que entrou, entrou.
    """
    criadas, atualizadas, insumos, composicoes = 0, 0, 0, 0
    for uf, regime in leitura.publicacoes:
        base, nova = BaseReferencial.objects.get_or_create(
            fonte=fonte, uf=uf, mes_referencia=competencia, regime_encargos=regime,
            variante=leitura.variante,
            defaults={"importada_por_nome": por, "url_origem": url_origem},
        )
        # O rótulo que a **fonte** sabe dar vence o automático: "EMBASA BA
        # 06/2026 · Expansão SINTRACOM (LS H 158,56%)" diz qual das seis tabelas
        # do semestre é esta, e o automático só saberia repetir a variante crua.
        if leitura.rotulo:
            base.rotulo = leitura.rotulo[:120]
        elif not base.rotulo:
            base.rotulo = base.rotulo_automatico()
        if por:
            base.importada_por_nome = por
        if url_origem:
            base.url_origem = url_origem[:500]
        # Carregar a publicação **reativa** o que estava desligado. Achado ao
        # rodar o E2E depois de desativar uma leva de teste: a carga gravou os
        # preços e a tela continuou sem mostrar nada, porque  só
        # lista . Carregar é ato afirmativo — diz "este mês agora
        # está aqui" —, e terminar com sucesso deixando a publicação escondida é
        # a pior das duas leituras possíveis.
        base.ativa = True
        base.save(update_fields=[
            "rotulo", "importada_por_nome", "url_origem", "ativa", "importada_em",
        ])
        criadas += 1 if nova else 0
        atualizadas += 0 if nova else 1

        for tabela in leitura.tabelas:
            if tabela.regime != regime or uf not in tabela.ufs:
                continue
            pendentes = tabela.itens_da_uf(uf)
            for item in pendentes.values():
                item.base = base
            novos, alterados = gravar_itens(base, tabela.tipo, pendentes)
            if tabela.tipo == InsumoReferencia.Tipo.INSUMO:
                insumos += novos + alterados
            else:
                composicoes += novos + alterados
        recontar(base)
        if progresso:
            progresso(f"gravando {uf} · {regime}")
    return {
        "publicacoes_criadas": criadas,
        "publicacoes_atualizadas": atualizadas,
        "insumos": insumos,
        "composicoes": composicoes,
    }


class ClasseSemTraducao(Exception):
    """A carga parou porque a fonte respondeu e nós não entendemos (D112)."""

    def __init__(self, classes: dict[str, int]):
        self.classes = classes
        super().__init__(f"{len(classes)} classe(s) sem tradução para natureza.")


def conferir_classes(fonte: str, classes: set[str]) -> dict[str, int]:
    """As classes desta publicação que o de-para não conhece.

    Devolve `{classe: 0}` — a contagem por insumo é do comando, que tem os itens
    na mão; aqui o que importa é **quais** são, porque é isso que a pessoa
    precisa declarar em `dados/classes/<fonte>.csv`.
    """
    return {
        classe: 0
        for classe in sorted(classes)
        if services.classificacao_desconhecida(classe, fonte)
    }


def executar(carga: CargaBase, conteudo: bytes | None = None) -> CargaBase:
    """Roda uma corrida do começo ao fim, escrevendo o estado a cada degrau.

    `conteudo` vem preenchido no plano B (upload). Vazio, a carga busca no site
    oficial pelo template da `FonteOficial`.
    """
    def anotar(etapa: str, estado: str | None = None) -> None:
        carga.etapa = etapa[:200]
        if estado:
            carga.estado = estado
        carga.save(update_fields=["etapa", "estado", "atualizada_em"])

    try:
        if conteudo is None:
            configuracao = FonteOficial.objects.filter(fonte=carga.fonte).first()
            # Corrida que já traz o endereço dispensa o cadastro: o que a
            # `FonteOficial` resolve é *qual* URL, e essa já foi respondida. A
            # conferência de que o endereço é legítimo é de quem criou a corrida
            # (a view amarra ao host cadastrado), não de quem a executa.
            if configuracao is None and not carga.url_origem:
                raise oficial.CargaIndisponivel(
                    "Esta fonte não tem endereço configurado. Cadastre o template da "
                    "URL antes de pedir a carga automática.",
                    motivo="sem_template",
                )
            # Corrida que já nasceu com endereço manda nele. É o que faz a EMBASA
            # funcionar sem inventar um segundo motor: a fonte não tem "o"
            # arquivo do mês — tem 65 tabelas por semestre, e quem dispara a
            # corrida escolheu uma. Para a SINAPI o campo nasce vazio e o
            # template decide, como na ORC.8.
            url = carga.url_origem or configuracao.url_para(carga.competencia)
            if not carga.url_origem and exige_escolha_de_documento(carga.fonte):
                raise oficial.CargaIndisponivel(
                    "Esta fonte publica um **menu** de tabelas, não um arquivo do "
                    "mês, e nenhuma delas é 'a principal' — a EMBASA põe 65 no ar "
                    "por semestre, entre expansão, operação de água e de esgoto, "
                    "cada uma por convenção coletiva. Escolha o documento em "
                    "`documentos-disponiveis` e dispare a carga com a URL dele.",
                    motivo="sem_documento",
                )
            anotar(f"baixando de {url[:120]}", CargaBase.Estado.BAIXANDO)
            carga.url_origem = url[:500]
            sessao = oficial.sessao_aquecida(
                configuracao.pagina_referencia if configuracao else ""
            )
            try:
                baixado = oficial.baixar(
                    url, sessao=sessao,
                    progresso=lambda mb: anotar(f"baixando ({mb:.1f} MB)"),
                )
            finally:
                sessao.close()
            conteudo, nome = baixado.conteudo, baixado.nome
        else:
            nome = carga.arquivo_nome

        carga.bytes_lidos = len(conteudo)
        carga.arquivo_nome = (nome or "")[:255]
        anotar("lendo o arquivo", CargaBase.Estado.LENDO)
        leitura = ler_pacote(conteudo, nome, fonte=carga.fonte)

        # **A data-base do artefato manda sobre a que foi pedida.** Quando o
        # documento a declara, ela é a única que não é palpite: a competência da
        # corrida nasce de uma defasagem em meses, e a EMBASA publica por
        # semestre — pedir "agosto" e receber a tabela de junho é o normal, não
        # a exceção. Gravar junho debaixo de agosto seria datar preço errado, que
        # é o defeito que não aparece até alguém comparar orçado com realizado.
        if leitura.competencia and leitura.competencia != carga.competencia:
            leitura.avisos.append(
                f"A corrida pediu {carga.competencia:%m/%Y} e o documento declara "
                f"{leitura.competencia:%m/%Y} — vale a do documento."
            )
            carga.competencia = leitura.competencia

        resumo = leitura.resumo()
        desconhecidas = conferir_classes(carga.fonte, leitura.classes)
        resumo["classes_desconhecidas"] = sorted(desconhecidas)
        carga.resumo = resumo
        carga.total_publicacoes = resumo["total_publicacoes"]
        carga.total_analitica = len(leitura.analitica)

        if desconhecidas and not carga.aceitar_sem_classe:
            raise ClasseSemTraducao(desconhecidas)

        if carga.somente_resumo:
            carga.estado = CargaBase.Estado.CONCLUIDA
            carga.etapa = "resumo pronto — nada foi gravado"
            carga.concluida_em = timezone.now()
            carga.save()
            return carga

        anotar("gravando as publicações", CargaBase.Estado.GRAVANDO)
        escrito = gravar_publicacoes(
            leitura, carga.fonte, carga.competencia,
            url_origem=carga.url_origem, por=carga.solicitada_por_nome,
            progresso=lambda etapa: anotar(etapa),
        )
        anotar("gravando a analítica nacional")
        gravadas = gravar_analitica_nacional(
            carga.fonte, carga.competencia, leitura.analitica
        )

        carga.resumo = {**resumo, **escrito, "analitica_gravada": gravadas}
        carga.total_insumos = escrito["insumos"]
        carga.total_composicoes = escrito["composicoes"]
        carga.total_analitica = gravadas
        carga.estado = CargaBase.Estado.CONCLUIDA
        carga.etapa = ""
        carga.erro = ""
        carga.concluida_em = timezone.now()
        carga.save()
        FonteOficial.objects.filter(fonte=carga.fonte).update(atualizada_em=timezone.now())
        return carga

    except ClasseSemTraducao as exc:
        # Não é falha: é uma pergunta. A base-mãe é global, e quem pode
        # respondê-la é justamente quem disparou a carga.
        carga.estado = CargaBase.Estado.AGUARDANDO
        carga.etapa = ""
        carga.erro = (
            f"{len(exc.classes)} classe(s) desta publicação não têm tradução para "
            "natureza — em `H` uma classe desconhecida vira mão de obra, que leva "
            "encargo social sobre custo que pode não ser salário.\n\n"
            + "\n".join(f"  · {classe}" for classe in sorted(exc.classes))
            + "\n\nDeclare a tradução em "
            f"moduloorcamento/dados/classes/{carga.fonte}.csv (classe;natureza), ou "
            "repita a carga aceitando que esses insumos entrem pela unidade."
        )
        carga.save()
        return carga
    except (oficial.CargaIndisponivel, CargaInvalida) as exc:
        carga.estado = CargaBase.Estado.FALHOU
        carga.etapa = ""
        carga.erro = str(exc)[:4000]
        carga.resumo = {**(carga.resumo or {}), "motivo": getattr(exc, "motivo", "invalido")}
        carga.save()
        return carga
    except Exception as exc:  # noqa: BLE001 - a corrida guarda o próprio desfecho
        logger.exception("orcamento: carga %s falhou", carga.pk)
        carga.estado = CargaBase.Estado.FALHOU
        carga.etapa = ""
        carga.erro = f"{type(exc).__name__}: {exc}"[:4000]
        carga.save()
        return carga


def competencia_sugerida(fonte: str, hoje: date | None = None) -> date:
    """Que mês o botão propõe para esta fonte."""
    configuracao = FonteOficial.objects.filter(fonte=fonte).first()
    defasagem = configuracao.defasagem_meses if configuracao else 1
    return oficial.competencia_alvo(defasagem, hoje)


def fontes_conhecidas() -> list[str]:
    """As fontes que o motor sabe carregar sozinho hoje.

    Duas: a SINAPI (formato largo, o ZIP da Caixa) e a EMBASA (PDF, a tabela de
    saneamento da Bahia). Dizer **quais** é o ponto: `Fonte` aceita sete desde a
    ORC.0 e o importador manual é genérico, mas cada fonte publica do seu jeito.
    ORSE, SICRO, SEINFRA e SEDOP continuam entrando pelo comando até alguém
    escrever o leitor de cada uma — e a tela precisa dizer isso em vez de
    oferecer um botão que só falha.
    """
    return [Fonte.SINAPI, Fonte.EMBASA]


# Fontes em que "a publicação do mês" não é **uma** coisa, e por isso a corrida
# precisa dizer qual documento quer. A EMBASA publica por semestre, e são 65
# tabelas carregáveis — expansão, operação de água e de esgoto, cada uma por
# convenção coletiva. Nenhuma delas é a principal, e escolher por ela seria
# escolher o preço de uma região para quem orça em outra.
FONTES_COM_MENU: frozenset[str] = frozenset({Fonte.EMBASA})


def exige_escolha_de_documento(fonte: str) -> bool:
    """A corrida desta fonte só faz sentido com um documento escolhido.

    É o que tira a EMBASA da varredura mensal: um agendamento que dispara "a
    carga da EMBASA" sem dizer qual tabela só sabe falhar, todo mês, no mesmo
    dia — e um agendamento que sempre falha é pior que agendamento nenhum,
    porque ensina a ignorar o alarme.
    """
    return fonte in FONTES_COM_MENU


def documentos_disponiveis(fonte: str, competencia: date | None = None) -> list[dict]:
    """O **menu** de artefatos que a fonte oferece — o que a tela lista.

    Existe porque "a publicação do mês" deixou de ser uma coisa só. A SINAPI tem
    um arquivo por competência e o template o resolve; a EMBASA tem 65 tabelas
    por semestre, divididas por escopo (expansão, operação de água, de esgoto) e
    por convenção coletiva, e nenhuma delas é a principal. Sem esta lista, a
    única saída seria pedir que alguém colasse a URL à mão — e colar a URL errada
    é indistinguível de colar a certa até o preço sair na planilha.

    O que sai daqui é menu, não verdade: espécie e rótulo vêm do nome do
    arquivo. Quem decide onde o preço entra é o cabeçalho do PDF, na leitura.
    """
    if fonte == Fonte.EMBASA:
        from . import embasa

        configuracao = FonteOficial.objects.filter(fonte=fonte).first()
        pagina = (configuracao.template_url if configuracao else "") or embasa.PAGINA_PADRAO
        return [
            {
                "url": documento.url,
                "rotulo": documento.rotulo,
                "slug": documento.slug,
                "especie": documento.especie,
                "carregavel": documento.carregavel,
            }
            for documento in embasa.baixar_lista(pagina)
        ]

    configuracao = FonteOficial.objects.filter(fonte=fonte).first()
    if configuracao is None:
        return []
    url = configuracao.url_para(competencia or competencia_sugerida(fonte))
    if not url:
        return []
    return [{
        "url": url,
        "rotulo": url.rsplit("/", 1)[-1],
        "slug": url.rsplit("/", 1)[-1],
        "especie": "pacote",
        "carregavel": True,
    }]
