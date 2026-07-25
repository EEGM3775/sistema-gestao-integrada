# backend/moduloorcamento/management/commands/importar_base_referencial.py
"""Importa uma publicação de base referencial (SINAPI, ORSE, SICRO…) do arquivo
oficial para as tabelas globais do módulo Orçamento.

**Por que comando e não upload na API:** a base é catálogo público de
plataforma, não dado de tenant (ver `moduloorcamento/models.py`). Escrita por
comando mantém a API read-only e deixa a operação auditável no runbook — é o
mesmo padrão do `sincronizar_feriados` do calendário.

**O que o arquivo precisa ter.** As publicações mudam de layout de mês para mês
e de fonte para fonte, então o comando **não** presume posição de coluna: ele
detecta o cabeçalho por sinônimos nas primeiras linhas da planilha. Se não
reconhecer, imprime os cabeçalhos que encontrou e aceita mapeamento explícito
por `--colunas`. Aceita `.xlsx` e `.csv`.

Exemplos::

    # SINAPI de SP, julho/2026, desonerado — insumos + composições + analítica
    manage.py importar_base_referencial --fonte sinapi --uf SP --mes 2026-07 \\
        --regime desonerado --insumos ISD.xlsx --composicoes CSD.xlsx --analitica CAD.xlsx

    # ORSE (Sergipe) só com insumos, mapeando as colunas na mão
    manage.py importar_base_referencial --fonte orse --uf SE --mes 2026-07 \\
        --insumos orse.csv --colunas "codigo=1,descricao=2,unidade=3,preco=4"

    # Conferir antes de gravar
    manage.py importar_base_referencial --fonte sinapi --uf SP --mes 2026-07 \\
        --insumos ISD.xlsx --dry-run
"""
from __future__ import annotations

import csv
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from moduloorcamento.models import (
    BaseReferencial,
    ComposicaoReferenciaItem,
    Fonte,
    InsumoReferencia,
)

LOTE = 1_000

# Sinônimos de cabeçalho por campo lógico, já normalizados (sem acento, minúsculo).
# A ordem importa: o primeiro alias que casar vence, então os mais específicos
# vêm antes ("codigo da composicao" antes de "codigo").
ALIASES: dict[str, tuple[str, ...]] = {
    "codigo": ("codigo do insumo", "codigo insumo", "codigo", "cod", "cod insumo"),
    "descricao": ("descricao do insumo", "descricao insumo", "descricao", "descricao do item"),
    "unidade": ("unidade", "unid", "und", "un", "unidade de medida"),
    "preco": (
        "preco mediano", "preco mediano r$", "custo unitario", "preco unitario",
        "custo total", "preco", "valor", "custo",
    ),
    "grupo": ("grupo", "classe", "descricao da classe", "grupo classe", "categoria"),
    # --- analítica (composição → item) ---
    "codigo_composicao": ("codigo da composicao", "codigo composicao", "cod composicao", "codigo"),
    "descricao_composicao": ("descricao da composicao", "descricao composicao"),
    "unidade_composicao": ("unidade da composicao", "unidade composicao", "unidade"),
    "codigo_item": ("codigo do item", "codigo item", "cod item", "codigo do insumo", "codigo insumo"),
    "descricao_item": ("descricao do item", "descricao item", "descricao do insumo", "descricao insumo"),
    "unidade_item": ("unidade do item", "unidade item", "und item"),
    "tipo_item": ("tipo de item", "tipo item", "tipo"),
    "coeficiente": ("coeficiente", "coef", "consumo", "quantidade"),
}

OBRIGATORIOS = {
    "insumos": ("codigo", "descricao", "unidade", "preco"),
    "composicoes": ("codigo", "descricao", "unidade", "preco"),
    "analitica": ("codigo_composicao", "codigo_item", "coeficiente"),
}


def normalizar(texto) -> str:
    """"Preço Mediano R$" → "preco mediano r$" (comparável entre publicações)."""
    if texto is None:
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().replace("\n", " ").split())


def para_decimal(valor) -> Decimal:
    """Aceita float do XLSX e texto no formato brasileiro ("1.234,56")."""
    if valor is None or valor == "":
        return Decimal("0")
    if isinstance(valor, (int, float, Decimal)):
        return Decimal(str(valor))
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")  # 1.234,56
    elif "," in texto:
        texto = texto.replace(",", ".")  # 1234,56
    try:
        return Decimal(texto)
    except InvalidOperation:
        return Decimal("0")


def detectar_delimitador(amostra: str) -> str:
    """Delimitador de CSV com preferência brasileira: **`;` vence**.

    `csv.Sniffer` não serve aqui. Numa linha como
    ``1379;CIMENTO;KG;0,58`` ele elege a vírgula (que é o separador **decimal**)
    e parte a última coluna em duas — sem erro, só com dado silenciosamente
    errado. Como toda base oficial brasileira exporta com `;`, a ordem de
    preferência é fixa e previsível; `--delimitador` cobre a exceção.
    """
    primeira = next((l for l in amostra.splitlines() if l.strip()), "")
    for candidato in (";", "\t", "|"):
        if candidato in primeira:
            return candidato
    return ","


def ler_planilha(caminho: Path, aba: str | None = None, delimitador: str | None = None):
    """Itera as linhas do arquivo como listas de valores. `.xlsx` via openpyxl em
    modo read-only (streaming — a SINAPI tem dezenas de milhares de linhas)."""
    if not caminho.exists():
        raise CommandError(f"Arquivo não encontrado: {caminho}")
    if caminho.suffix.lower() in {".csv", ".txt"}:
        with caminho.open("r", encoding="utf-8-sig", newline="") as f:
            sep = delimitador or detectar_delimitador(f.read(8192))
            f.seek(0)
            for linha in csv.reader(f, delimiter=sep):
                yield linha
        return
    if caminho.suffix.lower() != ".xlsx":
        raise CommandError(f"Formato não suportado ({caminho.suffix}). Use .xlsx ou .csv.")
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - dependência declarada em requirements
        raise CommandError("openpyxl não instalado — necessário para ler .xlsx.") from exc
    wb = load_workbook(filename=str(caminho), read_only=True, data_only=True)
    try:
        planilha = wb[aba] if aba else wb.worksheets[0]
        for linha in planilha.iter_rows(values_only=True):
            yield list(linha)
    finally:
        wb.close()


def detectar_colunas(linhas, obrigatorios: tuple[str, ...], limite: int = 25):
    """Procura, nas primeiras `limite` linhas, a que serve de cabeçalho.

    Devolve `(mapa, indice_da_linha, cabecalhos_vistos)`. `mapa` leva campo
    lógico → índice de coluna. Falha explícita é melhor que adivinhação: quem
    chama imprime `cabecalhos_vistos` para o operador decidir o `--colunas`.
    """
    vistos: list[list[str]] = []
    for indice, linha in enumerate(linhas[:limite]):
        celulas = [normalizar(c) for c in linha]
        if not any(celulas):
            continue
        vistos.append([c for c in celulas if c])
        mapa: dict[str, int] = {}
        usados: set[int] = set()
        for campo in obrigatorios + tuple(c for c in ALIASES if c not in obrigatorios):
            for alias in ALIASES[campo]:
                for pos, celula in enumerate(celulas):
                    if pos in usados or celula != alias:
                        continue
                    mapa[campo] = pos
                    usados.add(pos)
                    break
                if campo in mapa:
                    break
        if all(campo in mapa for campo in obrigatorios):
            return mapa, indice, vistos
    return None, -1, vistos


def parsear_colunas_manuais(spec: str) -> dict[str, int]:
    """`"codigo=1,descricao=2"` → `{"codigo": 0, "descricao": 1}` (1-based na CLI)."""
    mapa: dict[str, int] = {}
    for parte in spec.split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "=" not in parte:
            raise CommandError(f"--colunas malformado em '{parte}' (use campo=numero).")
        campo, _, numero = parte.partition("=")
        campo = campo.strip()
        if campo not in ALIASES:
            raise CommandError(f"--colunas: campo desconhecido '{campo}'. Válidos: {sorted(ALIASES)}")
        try:
            posicao = int(numero)
        except ValueError as exc:
            raise CommandError(f"--colunas: '{numero}' não é número de coluna.") from exc
        if posicao < 1:
            raise CommandError("--colunas: a numeração de coluna começa em 1.")
        mapa[campo] = posicao - 1
    return mapa


class Command(BaseCommand):
    help = "Importa uma publicação de base referencial de custos (SINAPI/ORSE/SICRO…)."

    def add_arguments(self, parser):
        parser.add_argument("--fonte", required=True, choices=[f.value for f in Fonte])
        parser.add_argument("--uf", default="", help="UF da publicação (vazio = nacional).")
        parser.add_argument("--mes", required=True, help="Mês de referência (AAAA-MM).")
        parser.add_argument(
            "--regime", default=BaseReferencial.Regime.ONERADO,
            choices=[r.value for r in BaseReferencial.Regime],
            help="Regime de encargos sociais da publicação.",
        )
        parser.add_argument("--insumos", help="Planilha de preços de insumos.")
        parser.add_argument("--composicoes", help="Planilha de custos de composições (sintética).")
        parser.add_argument("--analitica", help="Planilha de composições analíticas.")
        parser.add_argument("--aba", help="Nome da aba (default: a primeira).")
        parser.add_argument(
            "--delimitador", default="",
            help="Delimitador do CSV (default: ';' quando presente, senão ',').",
        )
        parser.add_argument("--rotulo", default="", help="Rótulo legível da publicação.")
        parser.add_argument("--colunas", default="", help='Mapa explícito: "codigo=1,descricao=2".')
        parser.add_argument("--por", type=str, default="", help="Quem rodou (registro na base).")
        parser.add_argument(
            "--substituir", action="store_true",
            help="Apaga os itens da publicação antes de importar (em vez de atualizar).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Só conta e valida; não grava.")

    def handle(self, *args, **opcoes):
        if not any(opcoes.get(k) for k in ("insumos", "composicoes", "analitica")):
            raise CommandError("Informe ao menos um de --insumos / --composicoes / --analitica.")
        mes = self._parse_mes(opcoes["mes"])
        manual = parsear_colunas_manuais(opcoes["colunas"]) if opcoes["colunas"] else {}
        seco = opcoes["dry_run"]

        base, criada = BaseReferencial.objects.get_or_create(
            fonte=opcoes["fonte"], uf=(opcoes["uf"] or "").upper()[:2],
            mes_referencia=mes, regime_encargos=opcoes["regime"],
            defaults={"rotulo": opcoes["rotulo"], "importada_por_nome": opcoes["por"]},
        )
        if not base.rotulo:
            base.rotulo = opcoes["rotulo"] or base.rotulo_automatico()
        if opcoes["por"]:
            base.importada_por_nome = opcoes["por"]
        self.stdout.write(
            f"{'Criada' if criada else 'Atualizando'} publicação: {base.rotulo or base}"
        )

        if opcoes["substituir"] and not seco:
            apagados = InsumoReferencia.objects.filter(base=base).delete()[0]
            self.stdout.write(f"  --substituir: {apagados} linhas removidas da publicação.")

        sep = opcoes["delimitador"] or None
        total_insumos = total_composicoes = total_componentes = 0
        if opcoes["insumos"]:
            total_insumos = self._importar_itens(
                base, Path(opcoes["insumos"]), InsumoReferencia.Tipo.INSUMO,
                "insumos", opcoes["aba"], manual, seco, sep,
            )
        if opcoes["composicoes"]:
            total_composicoes = self._importar_itens(
                base, Path(opcoes["composicoes"]), InsumoReferencia.Tipo.COMPOSICAO,
                "composicoes", opcoes["aba"], manual, seco, sep,
            )
        if opcoes["analitica"]:
            criados_comp, componentes = self._importar_analitica(
                base, Path(opcoes["analitica"]), opcoes["aba"], manual, seco, sep,
            )
            total_composicoes = max(total_composicoes, criados_comp)
            total_componentes = componentes

        if seco:
            self.stdout.write(self.style.WARNING("--dry-run: nada foi gravado."))
            return

        base.total_insumos = InsumoReferencia.objects.filter(
            base=base, tipo=InsumoReferencia.Tipo.INSUMO
        ).count()
        base.total_composicoes = InsumoReferencia.objects.filter(
            base=base, tipo=InsumoReferencia.Tipo.COMPOSICAO
        ).count()
        base.save()
        self.stdout.write(self.style.SUCCESS(
            f"OK | {base.rotulo}: {base.total_insumos} insumos, "
            f"{base.total_composicoes} composições, {total_componentes} componentes analíticos "
            f"(nesta corrida: {total_insumos} insumos / {total_composicoes} composições)."
        ))

    # ------------------------------------------------------------------ helpers

    def _parse_mes(self, valor: str) -> date:
        texto = valor.strip()
        for formato in ("%Y-%m", "%Y-%m-%d", "%m/%Y"):
            try:
                from datetime import datetime

                return datetime.strptime(texto, formato).date().replace(day=1)
            except ValueError:
                continue
        raise CommandError(f"--mes inválido: '{valor}'. Use AAAA-MM.")

    def _mapear(self, linhas, tipo_arquivo: str, manual: dict[str, int], caminho: Path):
        obrigatorios = OBRIGATORIOS[tipo_arquivo]
        if manual and all(c in manual for c in obrigatorios):
            return manual, -1
        mapa, cabecalho, vistos = detectar_colunas(linhas, obrigatorios)
        if mapa is None:
            amostra = "\n    ".join(" | ".join(v[:12]) for v in vistos[:5]) or "(vazio)"
            raise CommandError(
                f"Não reconheci o cabeçalho de {caminho.name} (esperava {obrigatorios}).\n"
                f"  Cabeçalhos vistos:\n    {amostra}\n"
                f"  Use --colunas \"campo=numero,...\" para mapear na mão."
            )
        mapa.update(manual)  # override pontual continua valendo
        return mapa, cabecalho

    def _celula(self, linha, mapa, campo):
        pos = mapa.get(campo)
        if pos is None or pos >= len(linha):
            return None
        return linha[pos]

    def _importar_itens(self, base, caminho, tipo, tipo_arquivo, aba, manual, seco, sep=None) -> int:
        linhas = list(ler_planilha(caminho, aba, sep))
        mapa, cabecalho = self._mapear(linhas, tipo_arquivo, manual, caminho)
        pendentes: dict[str, InsumoReferencia] = {}
        ignoradas = 0
        for linha in linhas[cabecalho + 1:]:
            codigo = self._celula(linha, mapa, "codigo")
            descricao = self._celula(linha, mapa, "descricao")
            if codigo in (None, "") or descricao in (None, ""):
                ignoradas += 1
                continue
            codigo = str(codigo).strip()
            if codigo.endswith(".0"):  # XLSX devolve código numérico como float
                codigo = codigo[:-2]
            pendentes[codigo] = InsumoReferencia(
                base=base, codigo=codigo[:30], tipo=tipo,
                descricao=str(descricao).strip()[:500],
                unidade=str(self._celula(linha, mapa, "unidade") or "").strip()[:20],
                custo_unitario=para_decimal(self._celula(linha, mapa, "preco")),
                grupo=str(self._celula(linha, mapa, "grupo") or "").strip()[:150],
            )
        rotulo = "insumos" if tipo == InsumoReferencia.Tipo.INSUMO else "composições"
        self.stdout.write(
            f"  {caminho.name}: {len(pendentes)} {rotulo} lidos"
            f"{f' ({ignoradas} linhas ignoradas)' if ignoradas else ''}."
        )
        if seco:
            return len(pendentes)
        return self._gravar_itens(base, tipo, pendentes)

    @transaction.atomic
    def _gravar_itens(self, base, tipo, pendentes: dict[str, InsumoReferencia]) -> int:
        """Upsert em lote: a publicação é reimportável sem duplicar nem perder FK."""
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
        self.stdout.write(f"    → {len(novos)} novos, {len(alterados)} atualizados.")
        return len(pendentes)

    def _importar_analitica(self, base, caminho, aba, manual, seco, sep=None) -> tuple[int, int]:
        """Lê a analítica: cria as composições que faltarem e reescreve os componentes.

        A analítica é a fonte mais rica da publicação — ela **também** declara as
        composições e os insumos citados. Então, se a empresa só tem este arquivo,
        a base ainda fica utilizável: o que não veio da sintética nasce aqui.
        """
        linhas = list(ler_planilha(caminho, aba, sep))
        mapa, cabecalho = self._mapear(linhas, "analitica", manual, caminho)

        composicoes: dict[str, dict] = {}
        filhos: dict[str, dict] = {}
        vinculos: list[tuple[str, str, Decimal]] = []
        for linha in linhas[cabecalho + 1:]:
            cod_comp = self._celula(linha, mapa, "codigo_composicao")
            cod_item = self._celula(linha, mapa, "codigo_item")
            if cod_comp in (None, "") or cod_item in (None, ""):
                continue
            cod_comp, cod_item = self._limpar_codigo(cod_comp), self._limpar_codigo(cod_item)
            composicoes.setdefault(cod_comp, {
                "descricao": str(self._celula(linha, mapa, "descricao_composicao") or "")[:500],
                "unidade": str(self._celula(linha, mapa, "unidade_composicao") or "")[:20],
            })
            tipo_declarado = normalizar(self._celula(linha, mapa, "tipo_item"))
            filhos.setdefault(cod_item, {
                "descricao": str(self._celula(linha, mapa, "descricao_item") or "")[:500],
                "unidade": str(self._celula(linha, mapa, "unidade_item") or "")[:20],
                # "COMPOSICAO"/"COMPOSIÇÃO" na coluna de tipo indica composição
                # auxiliar aninhada; o resto é insumo.
                "tipo": (
                    InsumoReferencia.Tipo.COMPOSICAO
                    if "composicao" in tipo_declarado
                    else InsumoReferencia.Tipo.INSUMO
                ),
            })
            vinculos.append((cod_comp, cod_item, para_decimal(self._celula(linha, mapa, "coeficiente"))))

        self.stdout.write(
            f"  {caminho.name}: {len(composicoes)} composições, {len(vinculos)} linhas analíticas."
        )
        if seco:
            return len(composicoes), len(vinculos)
        return self._gravar_analitica(base, composicoes, filhos, vinculos)

    def _limpar_codigo(self, valor) -> str:
        codigo = str(valor).strip()
        return codigo[:-2] if codigo.endswith(".0") else codigo

    @transaction.atomic
    def _gravar_analitica(self, base, composicoes, filhos, vinculos) -> tuple[int, int]:
        # 1. garante as composições declaradas na analítica
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

        # 2. garante os filhos citados (insumo ou composição auxiliar)
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

        # 3. resolve códigos → pk (agora completo) e reescreve os componentes
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
        self.stdout.write(
            f"    → {len(faltando)} composições novas, {len(novos_filhos)} filhos novos, "
            f"{len(componentes)} componentes gravados."
        )
        return len(composicoes), len(componentes)
