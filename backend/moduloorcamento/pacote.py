# backend/moduloorcamento/pacote.py
"""DMS.1 — o pacote da base referencial: levar SINAPI/ORSE/EMBASA para fora do dev.

**O problema (D185).** As 1.460 publicações oficiais (17 milhões de insumos,
5,6 GB) chegaram ao banco de desenvolvimento por cargas que leem o arquivo da
fonte e o descartam. Staging e produção nascem vazios, e recarregar de novo da
fonte não é garantido: a Caixa já devolveu HTML no lugar do ZIP (D184) e as
fontes tiram meses antigos do ar.

**A saída para um SaaS num servidor.** O que se transporta é a base **já
carregada e conferida**, não os ZIPs: um arquivo só, com um CSV comprimido por
tabela e um manifesto (contagens, SHA-256 de cada membro, colunas, migration de
origem). É o arquivo que o DMS coordena — sai de um ambiente, entra em outro —,
e por isso é **um arquivo**, conferível antes de tocar no banco.

**Importar em lotes, com commit por publicação** *(lição de 03/10/2026)*. A
versão 1 importava tudo numa transação, com uma tabela temporária do tamanho da
base inteira; na primeira carga real (17 milhões de linhas, com as duas stacks no
ar) a VM da WSL ficou sem memória e caiu, e a transação desfeita deixou 5,5 GB de
linhas mortas. Agora:

- cada publicação entra **com os seus insumos** numa transação só — ou inteira,
  ou nada —, e a seguinte começa do zero. Se o processo cair, a que caiu não
  existe no destino e a próxima rodada a refaz; as prontas são puladas;
- os insumos vêm **ordenados por base** no pacote, para serem lidos em fluxo, uma
  publicação de cada vez, sem carregar o arquivo inteiro em lugar nenhum;
- a analítica nacional e as composições vão em lotes de
  `ORCAMENTO_PACOTE_LINHAS_POR_LOTE` linhas (payment/planos.py), com
  `ON CONFLICT DO NOTHING`;
- as composições se resolvem pela **chave natural** (publicação + tipo + código
  do pai e do filho), não por um mapa de ids em memória — por isso podem ser
  refeitas a qualquer momento.

Nulo é `\\N` no CSV (o texto vazio continua sendo texto vazio): sem isso, ler e
reescrever a linha em Python confundiria `NULL` com `''`.

A base é catálogo de **plataforma** (sem tenant, sem RLS): quem roda é a
bancada (`manage.py pacote_base`), como o `carregar_base_oficial`.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
from datetime import date

from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from payment import planos

from nucleo.models import IndiceEconomico, ValorIndice

from .models import (
    AnaliticaNacional,
    BaseReferencial,
    ComposicaoReferenciaItem,
    FonteOficial,
    InsumoReferencia,
)

#: 3 desde 10/10/2026: os índices passaram à série única do `nucleo`
#: (pk `id`, variação e número-índice opcionais).
VERSAO = 3
MANIFESTO = "manifesto.json"
NULO = r"\N"
OPCOES_CSV = f"FORMAT csv, HEADER true, NULL '{NULO}'"

#: Ordem de exportação e de importação (a de dependência das FKs).
TABELAS = (
    ("fontes", FonteOficial),
    ("bases", BaseReferencial),
    ("insumos", InsumoReferencia),
    ("componentes", ComposicaoReferenciaItem),
    ("analitica", AnaliticaNacional),
    ("indices", IndiceEconomico),
    ("valores_indice", ValorIndice),
)

#: As FKs que o import sabe remapear. Outra qualquer → recusa (ver `_conferir`).
FKS_REMAPEADAS = {
    ("insumos", "base_id"),
    ("componentes", "composicao_id"),
    ("componentes", "filho_id"),
    ("valores_indice", "indice_id"),
}

CHAVE_DA_BASE = ("fonte", "uf", "mes_referencia", "regime_encargos", "variante")


class PacoteInvalido(Exception):
    """O arquivo não é um pacote que este código saiba importar com segurança."""


def _colunas(modelo) -> list[str]:
    return [f.column for f in modelo._meta.concrete_fields]


def _sem_pk(modelo) -> list[str]:
    pk = modelo._meta.pk.column
    return [col for col in _colunas(modelo) if col != pk]


def _ultima_migracao() -> str:
    return (
        MigrationRecorder.Migration.objects.filter(app="moduloorcamento")
        .order_by("-applied", "-id").values_list("name", flat=True).first() or ""
    )


def _q(nome: str) -> str:
    return connection.ops.quote_name(nome)


def _lote() -> int:
    return planos.ORCAMENTO_PACOTE_LINHAS_POR_LOTE


# ---------------------------------------------------------------------------
# Exportar
# ---------------------------------------------------------------------------


def _filtro_bases(fontes: list[str] | None, desde: date | None) -> str:
    """O `WHERE` das bases escolhidas, montado pelo `mogrify` (sem SQL na mão)."""
    partes, params = ["TRUE"], []
    if fontes:
        partes.append("fonte = ANY(%s)")
        params.append(list(fontes))
    if desde:
        partes.append("mes_referencia >= %s")
        params.append(desde)
    with connection.cursor() as c:
        return c.cursor.mogrify(" AND ".join(partes), params).decode()


def _selects(filtro: str) -> dict[str, str]:
    """Um `SELECT` por tabela, todos recortados pelas mesmas bases.

    Os insumos saem **ordenados por base** — é o que deixa o import ler uma
    publicação de cada vez. O índice `(base, tipo)` serve a ordem sem sort.
    """
    t = {nome: modelo._meta.db_table for nome, modelo in TABELAS}
    cols = {nome: ", ".join(_q(c) for c in _colunas(modelo)) for nome, modelo in TABELAS}
    bases = f"SELECT base_id FROM {t['bases']} WHERE {filtro}"
    return {
        "fontes": f"SELECT {cols['fontes']} FROM {t['fontes']}",
        "bases": f"SELECT {cols['bases']} FROM {t['bases']} WHERE {filtro} ORDER BY base_id",
        "insumos": (
            f"SELECT {cols['insumos']} FROM {t['insumos']} WHERE base_id IN ({bases}) "
            f"ORDER BY base_id, tipo"
        ),
        "componentes": (
            f"SELECT {cols['componentes']} FROM {t['componentes']} WHERE composicao_id IN "
            f"(SELECT referencia_id FROM {t['insumos']} WHERE base_id IN ({bases}))"
        ),
        "analitica": (
            f"SELECT {cols['analitica']} FROM {t['analitica']} WHERE (fonte, competencia) IN "
            f"(SELECT DISTINCT fonte, mes_referencia FROM {t['bases']} WHERE {filtro})"
        ),
        "indices": f"SELECT {cols['indices']} FROM {t['indices']}",
        "valores_indice": f"SELECT {cols['valores_indice']} FROM {t['valores_indice']}",
    }


def exportar(saida: str, *, fontes: list[str] | None = None, desde: date | None = None, avisar=print) -> dict:
    """Grava o pacote em `saida` (.tar) e devolve o manifesto. Lê em fluxo (`COPY`)."""
    selects = _selects(_filtro_bases(fontes, desde))
    manifesto = {
        "versao": VERSAO,
        "gerado_em": timezone.now().isoformat(),
        "migracao": _ultima_migracao(),
        "nulo": NULO,
        "recorte": {"fontes": fontes or [], "desde": desde.isoformat() if desde else None},
        "tabelas": {},
    }
    pasta = tempfile.mkdtemp(prefix="pacote_base_", dir=os.path.dirname(os.path.abspath(saida)) or None)
    try:
        with connection.cursor() as c:
            for nome, modelo in TABELAS:
                caminho = os.path.join(pasta, f"{nome}.csv.gz")
                with gzip.open(caminho, "wb", compresslevel=6) as gz:
                    c.cursor.copy_expert(f"COPY ({selects[nome]}) TO STDOUT WITH ({OPCOES_CSV})", gz)
                    linhas = c.cursor.rowcount
                manifesto["tabelas"][nome] = {
                    "linhas": linhas, "colunas": _colunas(modelo), "sha256": _sha256(caminho),
                }
                avisar(f"  {nome}: {linhas} linhas")
        with tarfile.open(saida, "w") as tar:
            dados = json.dumps(manifesto, ensure_ascii=False, indent=2).encode()
            info = tarfile.TarInfo(MANIFESTO)
            info.size = len(dados)
            tar.addfile(info, io.BytesIO(dados))
            for nome, _ in TABELAS:
                tar.add(os.path.join(pasta, f"{nome}.csv.gz"), arcname=f"{nome}.csv.gz")
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    return manifesto


def _sha256(caminho: str) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Conferir
# ---------------------------------------------------------------------------


def ler_manifesto(arquivo: str) -> dict:
    with tarfile.open(arquivo, "r") as tar:
        try:
            manifesto = json.load(tar.extractfile(MANIFESTO))
        except KeyError:
            raise PacoteInvalido("O arquivo não tem manifesto — não é um pacote da base.")
    if manifesto.get("versao") != VERSAO:
        raise PacoteInvalido(
            f"Pacote na versão {manifesto.get('versao')}; este código lê a {VERSAO}. "
            "Gere o pacote de novo (`pacote_base exportar`) com esta versão."
        )
    return manifesto


def conferir(arquivo: str, manifesto: dict | None = None) -> dict:
    """Somas e colunas antes de tocar no banco — o que o ensaio de restore faz com o backup."""
    manifesto = manifesto or ler_manifesto(arquivo)
    for nome, modelo in TABELAS:
        meta = manifesto["tabelas"].get(nome)
        if meta is None:
            raise PacoteInvalido(f"O pacote não traz a tabela '{nome}'.")
        if meta["colunas"] != _colunas(modelo):
            raise PacoteInvalido(
                f"As colunas de '{nome}' no pacote não são as deste banco "
                f"(pacote da migration {manifesto.get('migracao')}, banco em {_ultima_migracao()}). "
                "Gere o pacote de um ambiente na mesma versão."
            )
        for coluna in (f.column for f in modelo._meta.concrete_fields if f.is_relation):
            if (nome, coluna) not in FKS_REMAPEADAS:
                raise PacoteInvalido(f"'{nome}.{coluna}' é FK que o import não sabe remapear.")
    with tarfile.open(arquivo, "r") as tar:
        for nome, _ in TABELAS:
            h = hashlib.sha256()
            membro = tar.extractfile(f"{nome}.csv.gz")
            for bloco in iter(lambda: membro.read(1 << 20), b""):
                h.update(bloco)
            if h.hexdigest() != manifesto["tabelas"][nome]["sha256"]:
                raise PacoteInvalido(f"A soma de '{nome}' não bate: o arquivo foi alterado ou corrompido.")
    return manifesto


# ---------------------------------------------------------------------------
# Importar — em lotes, retomável
# ---------------------------------------------------------------------------


def _linhas(tar, nome: str):
    """`(cabeçalho, iterador de linhas)` do CSV de uma tabela, em fluxo."""
    texto = io.TextIOWrapper(gzip.open(tar.extractfile(f"{nome}.csv.gz"), "rb"), encoding="utf-8", newline="")
    leitor = csv.reader(texto)
    return next(leitor), leitor


def _csv(cabecalho: list[str], linhas) -> io.StringIO:
    """Linhas de volta em CSV para o `COPY FROM` — com o mesmo marcador de nulo."""
    saida = io.StringIO()
    escritor = csv.writer(saida, lineterminator="\n")
    escritor.writerow(cabecalho)
    escritor.writerows(linhas)
    saida.seek(0)
    return saida


def _copiar(c, tabela: str, cabecalho: list[str], linhas) -> None:
    colunas = ", ".join(_q(x) for x in cabecalho)
    c.cursor.copy_expert(f"COPY {tabela} ({colunas}) FROM STDIN WITH ({OPCOES_CSV})", _csv(cabecalho, linhas))


def _temporaria(c, nome: str, modelo) -> str:
    """Uma temporária vazia com a forma da tabela — reaproveitada a cada lote."""
    tmp = f"tmp_pacote_{nome}"
    c.execute(f"DROP TABLE IF EXISTS {tmp}")
    c.execute(f"CREATE TEMP TABLE {tmp} (LIKE {modelo._meta.db_table} INCLUDING DEFAULTS)")
    return tmp


def _em_lotes(leitor, tamanho: int):
    lote = []
    for linha in leitor:
        lote.append(linha)
        if len(lote) >= tamanho:
            yield lote
            lote = []
    if lote:
        yield lote


def _pequenas(c, tar, t: dict, resumo: dict) -> None:
    """Fontes oficiais e índices: poucas linhas, uma transação."""
    with transaction.atomic():
        cab, linhas = _linhas(tar, "fontes")
        tmp = _temporaria(c, "fontes", FonteOficial)
        _copiar(c, tmp, cab, linhas)
        cols = ", ".join(_q(x) for x in _sem_pk(FonteOficial))
        c.execute(f"INSERT INTO {t['fontes']} ({cols}) SELECT {cols} FROM {tmp} ON CONFLICT (fonte) DO NOTHING")
        resumo["fontes"] = c.rowcount

        cab, linhas = _linhas(tar, "indices")
        tmp_ind = _temporaria(c, "indices", IndiceEconomico)
        _copiar(c, tmp_ind, cab, linhas)
        cols = ", ".join(_q(x) for x in _sem_pk(IndiceEconomico))
        c.execute(f"INSERT INTO {t['indices']} ({cols}) SELECT {cols} FROM {tmp_ind} ON CONFLICT (codigo) DO NOTHING")
        resumo["indices"] = c.rowcount

        cab, linhas = _linhas(tar, "valores_indice")
        tmp_val = _temporaria(c, "valores_indice", ValorIndice)
        _copiar(c, tmp_val, cab, linhas)
        resto = [x for x in _sem_pk(ValorIndice) if x != "indice_id"]
        cols = ", ".join(_q(x) for x in resto)
        c.execute(f"INSERT INTO {t['valores_indice']} (indice_id, {cols}) "
                  f"SELECT d.id, {', '.join('v.' + _q(x) for x in resto)} FROM {tmp_val} v "
                  f"JOIN {tmp_ind} o ON v.indice_id = o.id "
                  f"JOIN {t['indices']} d ON d.codigo = o.codigo ON CONFLICT DO NOTHING")
        resumo["valores_indice"] = c.rowcount


def _analitica(c, tar, t: dict, resumo: dict) -> None:
    """Sem FK; a chave única decide. Um lote, um commit."""
    cab, linhas = _linhas(tar, "analitica")
    cols = ", ".join(_q(x) for x in _sem_pk(AnaliticaNacional))
    resumo["analitica"] = 0
    for lote in _em_lotes(linhas, _lote()):
        with transaction.atomic():
            tmp = _temporaria(c, "analitica", AnaliticaNacional)
            _copiar(c, tmp, cab, lote)
            c.execute(f"INSERT INTO {t['analitica']} ({cols}) SELECT {cols} FROM {tmp} ON CONFLICT DO NOTHING")
            resumo["analitica"] += c.rowcount


def _bases_e_insumos(c, tar, t: dict, resumo: dict, avisar) -> tuple[dict, dict]:
    """Uma publicação por transação: a base e todos os insumos dela, ou nada.

    Devolve dois mapas para as composições, ambos pequenos: `base de origem →
    chave natural`, e `insumo de origem → (base de origem, tipo, código)` só dos
    insumos que alguma composição cita.
    """
    cab_b, linhas_b = _linhas(tar, "bases")
    i_id = cab_b.index("base_id")
    chave = [cab_b.index(k) for k in CHAVE_DA_BASE]
    bases = {linha[i_id]: linha for linha in linhas_b}
    natural = {origem: tuple(linha[i] for i in chave) for origem, linha in bases.items()}

    citados = set()
    cab_k, linhas_k = _linhas(tar, "componentes")
    i_comp, i_filho = cab_k.index("composicao_id"), cab_k.index("filho_id")
    for linha in linhas_k:
        citados.update((linha[i_comp], linha[i_filho]))

    existentes = _bases_existentes(c, t)
    cab_i, linhas_i = _linhas(tar, "insumos")
    ii_id, ii_base = cab_i.index("referencia_id"), cab_i.index("base_id")
    ii_tipo, ii_cod = cab_i.index("tipo"), cab_i.index("codigo")
    cab_sem_pk = [x for x in cab_i if x != "referencia_id"]
    sem_pk = [n for n, x in enumerate(cab_i) if x != "referencia_id"]
    i_base_sem_pk = cab_sem_pk.index("base_id")
    cols_base = [x for x in cab_b if x != "base_id"]
    i_cols_base = [cab_b.index(x) for x in cols_base]

    do_insumo: dict[str, tuple] = {}
    resumo.update(bases=0, bases_ja_existentes=0, insumos=0)
    atual, grupo = None, []

    def fechar(base_origem, grupo):
        if base_origem is None:
            return
        if natural[base_origem] in existentes:
            resumo["bases_ja_existentes"] += 1
            return
        with transaction.atomic():
            _copiar(c, "tmp_pacote_uma_base", cols_base, [[bases[base_origem][i] for i in i_cols_base]])
            c.execute(f"INSERT INTO {t['bases']} ({', '.join(_q(x) for x in cols_base)}) "
                      f"SELECT {', '.join(_q(x) for x in cols_base)} FROM tmp_pacote_uma_base RETURNING base_id")
            novo = str(c.fetchone()[0])
            c.execute("TRUNCATE tmp_pacote_uma_base")
            for lote in _em_lotes(iter(grupo), _lote()):
                linhas = []
                for linha in lote:
                    sem = [linha[n] for n in sem_pk]
                    sem[i_base_sem_pk] = novo
                    linhas.append(sem)
                _copiar(c, t["insumos"], cab_sem_pk, linhas)
                resumo["insumos"] += len(linhas)
        existentes.add(natural[base_origem])
        resumo["bases"] += 1
        if resumo["bases"] % 50 == 0:
            avisar(f"    {resumo['bases']} publicações novas, {resumo['insumos']} insumos")

    c.execute("DROP TABLE IF EXISTS tmp_pacote_uma_base")
    c.execute(f"CREATE TEMP TABLE tmp_pacote_uma_base AS SELECT {', '.join(_q(x) for x in cols_base)} "
              f"FROM {t['bases']} WITH NO DATA")
    vistos = set()
    for linha in linhas_i:
        base_origem = linha[ii_base]
        if linha[ii_id] in citados:
            do_insumo[linha[ii_id]] = (base_origem, linha[ii_tipo], linha[ii_cod])
        if base_origem != atual:
            if base_origem in vistos:
                raise PacoteInvalido("Os insumos do pacote não vêm ordenados por base — gere o pacote de novo.")
            fechar(atual, grupo)
            vistos.add(base_origem)
            atual, grupo = base_origem, []
        grupo.append(linha)
    fechar(atual, grupo)
    # Base sem insumo nenhum também é publicação (a carga pode ter falhado nela).
    for origem in bases:
        if origem not in vistos:
            fechar(origem, [])
    return natural, do_insumo


def _bases_existentes(c, t: dict) -> set[tuple]:
    """Chaves naturais já no destino, no MESMO texto que o CSV traz (nulo = `\\N`)."""
    colunas = ", ".join(f"COALESCE({_q(k)}::text, %s)" for k in CHAVE_DA_BASE)
    c.execute(f"SELECT {colunas} FROM {t['bases']}", [NULO] * len(CHAVE_DA_BASE))
    return {tuple(linha) for linha in c.fetchall()}


def _componentes(c, tar, t: dict, resumo: dict, natural: dict, do_insumo: dict) -> None:
    """Pai e filho pela chave natural — não pelo id, que no destino é outro."""
    cab, linhas = _linhas(tar, "componentes")
    i_comp, i_filho = cab.index("composicao_id"), cab.index("filho_id")
    resto = [x for x in cab if x not in ("componente_id", "composicao_id", "filho_id")]
    i_resto = [cab.index(x) for x in resto]
    lado = [f"{p}_{k}" for p in ("pai", "filho") for k in CHAVE_DA_BASE + ("tipo", "codigo")]
    c.execute("DROP TABLE IF EXISTS tmp_pacote_comp")
    c.execute("CREATE TEMP TABLE tmp_pacote_comp (" + ", ".join(f"{x} text" for x in lado) + ", "
              + ", ".join(f"{_q(x)} text" for x in resto) + ")")

    def chave(origem):
        base, tipo, codigo = do_insumo[origem]
        return list(natural[base]) + [tipo, codigo]

    def junta(p, b):
        # O `COPY` já transformou o `\N` em NULL na temporária: os dois lados
        # passam pelo mesmo COALESCE, senão a UF nula nunca casaria.
        return " AND ".join(
            f"COALESCE({b}.{_q(k)}::text, '{NULO}') = COALESCE(k.{p}_{k}, '{NULO}')" for k in CHAVE_DA_BASE
        )

    tipos = {f.column: f.db_type(connection) for f in ComposicaoReferenciaItem._meta.concrete_fields}
    resumo["componentes"] = 0
    for lote in _em_lotes(linhas, _lote()):
        with transaction.atomic():
            c.execute("TRUNCATE tmp_pacote_comp")
            dados = [chave(linha[i_comp]) + chave(linha[i_filho]) + [linha[i] for i in i_resto]
                     for linha in lote if linha[i_comp] in do_insumo and linha[i_filho] in do_insumo]
            if not dados:
                continue
            _copiar(c, "tmp_pacote_comp", lado + resto, dados)
            convertidos = ", ".join(f"k.{_q(x)}::{tipos[x]}" for x in resto)
            c.execute(
                f"INSERT INTO {t['componentes']} (composicao_id, filho_id, {', '.join(_q(x) for x in resto)}) "
                f"SELECT pi.referencia_id, fi.referencia_id, {convertidos} FROM tmp_pacote_comp k "
                f"JOIN {t['bases']} pb ON {junta('pai', 'pb')} "
                f"JOIN {t['insumos']} pi ON pi.base_id = pb.base_id AND pi.tipo = k.pai_tipo AND pi.codigo = k.pai_codigo "
                f"JOIN {t['bases']} fb ON {junta('filho', 'fb')} "
                f"JOIN {t['insumos']} fi ON fi.base_id = fb.base_id AND fi.tipo = k.filho_tipo AND fi.codigo = k.filho_codigo "
                f"ON CONFLICT DO NOTHING"
            )
            resumo["componentes"] += c.rowcount


def importar(arquivo: str, *, avisar=print) -> dict:
    """Confere o pacote e grava o que o destino ainda não tem, em lotes. Retomável."""
    manifesto = conferir(arquivo)
    avisar("  pacote conferido (somas e colunas)")
    t = {nome: modelo._meta.db_table for nome, modelo in TABELAS}
    resumo: dict = {}
    with connection.cursor() as c, tarfile.open(arquivo, "r") as tar:
        _pequenas(c, tar, t, resumo)
        avisar(f"  fontes: {resumo['fontes']} · índices: {resumo['indices']} · valores: {resumo['valores_indice']}")
        _analitica(c, tar, t, resumo)
        avisar(f"  analítica: {resumo['analitica']}")
        natural, do_insumo = _bases_e_insumos(c, tar, t, resumo, avisar)
        avisar(f"  publicações novas: {resumo['bases']} (já existiam {resumo['bases_ja_existentes']}) · "
               f"insumos: {resumo['insumos']}")
        _componentes(c, tar, t, resumo, natural, do_insumo)
        avisar(f"  componentes: {resumo['componentes']}")
    resumo["manifesto_bases"] = manifesto["tabelas"]["bases"]["linhas"]
    return resumo
