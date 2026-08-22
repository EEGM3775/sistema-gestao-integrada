# backend/moduloorcamento/management/commands/reclassificar_itens_catalogo.py
"""ORC.9 — corrige a natureza dos itens já adotados no catálogo do tenant.

**O defeito que este comando fecha.** Até 20/08/2026 o catálogo não tinha
`MAO_DE_OBRA`: a adoção olhava a unidade e, vendo `H`/`MES`, gravava
`Tipo.SERVICO`. Do outro lado, a precificação lia todo `SERVICO` como mão de
obra para aplicar encargo social. O par funcionava por acidente para o pedreiro
e errava para o serviço **terceirizado**, que levava encargo em cima de um preço
que já vem com encargo dentro. A coluna `Classificação` da SINAPI — que responde
isso desde 01/2025 — era lida e descartada.

**O que ele faz.** Relê a classificação da fonte de cada item adotado, corrige o
`tipo` e as flags de domínio, e então acerta o que já foi explodido:

- **orçamento em rascunho** — a categoria do insumo é corrigida e a parcela
  refeita (com ou sem encargo, conforme a natureza certa); a planilha é
  recalculada de baixo para cima.
- **aprovado, superado ou cancelado** — não se toca. Planilha aprovada é a régua
  da medição feita contra ela; corrigi-la em silêncio moveria o chão de contrato
  assinado. A próxima revisão já nasce certa, porque copia do catálogo corrigido.

**Preço digitado à mão sobrevive.** Se o custo unitário da linha não bate mais
com a soma dos insumos (alguém aplicou preço real do SCM/SIL, ou digitou), o
comando corrige a categoria e a parcela mas **não** reescreve o custo da linha —
e diz isso no relatório, em vez de decidir sozinho.

**Código igual não é insumo igual (D110).** O de-para era montado por
`codigo__in` e indexado por `(fonte, código)`, com o **último registro lido
vencendo**: duas publicações da mesma fonte trazendo o mesmo código com
descrições diferentes carimbavam no item do tenant a natureza do *outro* insumo
— e natureza errada é encargo social errado, ou seja, preço errado. Agora cada
candidato é conferido contra a descrição e a unidade do item
(`moduloorcamento.identidade`), e:

- **nenhum candidato confere** → o item fica de fora do lote e sai no relatório
  como "não confere — conferir à mão";
- **candidatos conferem mas discordam da natureza** → também fica de fora, como
  "ambíguo": duas edições afirmando coisas diferentes sobre o mesmo item é
  pergunta para gente, não para o comando.

**Publicação sem a coluna `Classificação` (D111).** Ela só existe a partir de
01/2025. Quem carregou publicação anterior — a SINAPI BA 10/2024, por exemplo —
não tem o que reler: sem classificação, todo insumo que não é hora nem mês cai
no plano B da unidade e vira material. O comando **não adivinha pelo texto da
descrição** ("contém CAMINHÃO → equipamento"), que é a classe de palpite que
produziu o D109. Em vez disso faz duas coisas: **conta e declara** quantos itens
estão sem classificação na fonte, e aceita `--de-para`, uma planilha em que a
empresa classifica à mão só o que importa (as poucas centenas de equipamentos,
não os milhares de insumos).

O arquivo do `--de-para` é CSV/TSV com `codigo;natureza[;fonte]`, cabeçalho
opcional, e aceita tanto o rótulo publicado (`EQUIPAMENTO`, `MÃO DE OBRA`)
quanto a chave interna (`equipamento`, `mao_de_obra`). A terceira coluna limita
a linha a uma fonte; sem ela, vale para qualquer fonte. Declaração explícita da
empresa **vence** a classificação da publicação — quem escreveu o arquivo estava
olhando o item —, e o relatório diz quantas linhas contrariaram a fonte, para a
divergência não passar calada.

Uso::

    # conferência primeiro (nada é gravado):
    manage.py reclassificar_itens_catalogo --dry-run
    # um tenant:
    manage.py reclassificar_itens_catalogo --tenant demo
    # todos:
    manage.py reclassificar_itens_catalogo --all-tenants
    # classificando à mão o que a publicação antiga não classifica:
    manage.py reclassificar_itens_catalogo --tenant demo --de-para equipamentos.csv
"""
from __future__ import annotations

import csv
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalogo.models import Item
from funcoesimpexp.formatos.leitura import normalizar
from nucleo.models import Tenant
from nucleo.tenancy import rls_bypass

from moduloorcamento import encargos as encargos_mod
from moduloorcamento import identidade, planilha, precificacao
from moduloorcamento.models import (
    InsumoReferencia,
    ItemOrcado,
    ItemOrcadoInsumo,
    Orcamento,
)
from moduloorcamento.services import (
    classificacao_desconhecida,
    flags_da_natureza,
    natureza_da_classificacao,
)

QUATRO = Decimal("0.0001")

# As naturezas que o de-para pode declarar. `composicao` fica de fora de
# propósito: composição não é insumo, e o comando já a pula antes de chegar aqui.
NATUREZAS_ACEITAS = {
    Item.Tipo.MATERIAL, Item.Tipo.MAO_DE_OBRA, Item.Tipo.EQUIPAMENTO,
    Item.Tipo.ENCARGOS_COMPLEMENTARES, Item.Tipo.SERVICO, Item.Tipo.EPI,
    Item.Tipo.ATIVO,
}


class Command(BaseCommand):
    help = "Reclassifica itens adotados pela classificação da fonte (ORC.9)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="Slug ou id de um tenant.")
        parser.add_argument("--all-tenants", action="store_true", help="Todos os tenants.")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Só imprime o de-para e o impacto; não grava nada.",
        )
        parser.add_argument(
            "--sem-recalculo", action="store_true",
            help="Corrige o catálogo e não mexe em nenhum orçamento (nem rascunho).",
        )
        parser.add_argument(
            "--de-para", dest="de_para", metavar="ARQUIVO.CSV",
            help=(
                "Planilha 'codigo;natureza[;fonte]' com a classificação que a "
                "empresa declara — para publicação anterior a 01/2025, que não "
                "traz a coluna Classificação (D111)."
            ),
        )

    def handle(self, *args, **opts):
        seco = opts["dry_run"]
        tenants = self._tenants(opts)
        if not tenants:
            raise CommandError("Informe --tenant ou --all-tenants.")
        declarado = self._ler_de_para(opts.get("de_para"))

        for tenant in tenants:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n== {tenant.slug} =="))
            with rls_bypass():
                # A transação envolve o tenant inteiro: catálogo e planilha têm de
                # mudar juntos, senão um erro no meio deixa item corrigido com
                # composição do jeito antigo — pior que não ter rodado.
                with transaction.atomic():
                    depara, achados = self._reclassificar_itens(
                        tenant, seco=seco, declarado=declarado
                    )
                    if opts["sem_recalculo"]:
                        tocados = []
                    else:
                        tocados = self._acertar_rascunhos(tenant, seco=seco)
                    if seco:
                        transaction.set_rollback(True)
            self._relatorio(depara, tocados, achados, seco=seco)

    # -- de-para declarado pela empresa (D111) -----------------------------

    def _ler_de_para(self, caminho: str | None) -> dict:
        """`{(fonte|"", codigo): natureza}` a partir da planilha da empresa.

        **Linha ruim derruba o arquivo inteiro**, com a lista do que está errado.
        O contrário — pular em silêncio — é o pior desfecho possível aqui: quem
        classificou trezentos equipamentos à mão iria embora achando que aplicou
        trezentos, e a diferença só apareceria no preço meses depois.
        """
        if not caminho:
            return {}
        arquivo = Path(caminho)
        if not arquivo.is_file():
            raise CommandError(f"Arquivo de de-para não encontrado: {caminho}")

        # O delimitador é decidido só sobre as linhas de DADOS: um preâmbulo de
        # comentário explicando o arquivo (que é o formato útil, porque o de-para
        # sem o porquê envelhece mal) tem vírgula de texto corrido e faria a
        # contagem eleger o separador errado.
        linhas_uteis = [
            linha for linha in arquivo.read_text(encoding="utf-8-sig").splitlines()
            if linha.strip() and not linha.lstrip().startswith("#")
        ]
        amostra = "\n".join(linhas_uteis)
        delimitador = ";" if amostra.count(";") >= amostra.count("\t") else "\t"
        if amostra.count(",") > amostra.count(delimitador):
            delimitador = ","

        declarado: dict[tuple[str, str], str] = {}
        problemas: list[str] = []
        for numero, campos in enumerate(csv.reader(linhas_uteis, delimiter=delimitador), 1):
            campos = [c.strip() for c in campos if c is not None]
            if not campos or not campos[0]:
                continue
            if len(campos) < 2:
                problemas.append(f'linha útil {numero} ("{campos[0]}"): faltou a natureza')
                continue
            codigo, bruta = campos[0], campos[1]
            fonte = (campos[2].strip().lower() if len(campos) > 2 else "")
            natureza = self._natureza_declarada(bruta)
            if natureza is None:
                # Cabeçalho é a exceção legítima — e não está preso à primeira
                # linha, porque comentário vem antes dele em arquivo que se
                # explica. Só vale enquanto nenhuma linha de dado foi lida: um
                # "codigo;natureza" no MEIO do arquivo é engano, não cabeçalho.
                if not declarado and "codig" in normalizar(codigo):
                    continue
                problemas.append(
                    f'linha útil {numero} (código {codigo}): natureza "{bruta}" '
                    "não é uma das do catálogo"
                )
                continue
            declarado[(fonte, codigo)] = natureza

        if problemas:
            raise CommandError(
                "O de-para tem linha que o comando não sabe aplicar — nada foi "
                "gravado:\n  " + "\n  ".join(problemas[:20])
                + ("\n  …" if len(problemas) > 20 else "")
                + "\nNaturezas aceitas: " + ", ".join(sorted(NATUREZAS_ACEITAS))
            )
        if not declarado:
            raise CommandError(f"O de-para {caminho} não tem nenhuma linha aplicável.")
        return declarado

    def _natureza_declarada(self, texto: str) -> str | None:
        """Aceita a chave interna (`mao_de_obra`) e o rótulo publicado (`MÃO DE OBRA`)."""
        chave = (texto or "").strip().lower().replace(" ", "_").replace("-", "_")
        if chave in NATUREZAS_ACEITAS:
            return chave
        pela_fonte = natureza_da_classificacao(texto)
        return pela_fonte if pela_fonte in NATUREZAS_ACEITAS else None

    # -- tenants -----------------------------------------------------------

    def _tenants(self, opts) -> list[Tenant]:
        if opts["all_tenants"]:
            return list(Tenant.objects.all().order_by("slug"))
        alvo = opts.get("tenant")
        if not alvo:
            return []
        tenant = Tenant.objects.filter(slug=alvo).first()
        if tenant is None:
            # O id do tenant é UUID (espelho da IAM), não inteiro.
            try:
                tenant = Tenant.objects.filter(pk=alvo).first()
            except (ValueError, ValidationError):
                tenant = None
        if tenant is None:
            raise CommandError(f"Tenant '{alvo}' não encontrado.")
        return [tenant]

    # -- catálogo ----------------------------------------------------------

    def _reclassificar_itens(self, tenant, *, seco: bool, declarado: dict) -> tuple[dict, dict]:
        """Relê a classificação da fonte item a item.

        Devolve `(de-para aplicado, achados)` — o segundo é o que **não** foi
        aplicado e por quê, que é a metade que o comando não tinha.
        """
        itens = list(
            Item.objects.filter(tenant=tenant)
            .exclude(codigo_referencia="")
            .select_related("tipo_proprio")
        )
        # Uma consulta por (fonte, código) seria uma ida ao banco por item — a
        # base da empresa passa de dez mil linhas depois de duas adoções em lote.
        # Guardamos **todos** os candidatos de cada par, e não só o último lido:
        # é entre eles que mora o D110.
        candidatos: dict[tuple[str, str], list] = {}
        for ref in (
            InsumoReferencia.objects.filter(codigo__in={i.codigo_referencia for i in itens})
            .select_related("base")
            .order_by("-base__mes_referencia")
        ):
            candidatos.setdefault((ref.base.fonte, ref.codigo), []).append(ref)

        depara: dict[tuple[str, str], int] = {}
        achados = {
            "nao_confere": [], "ambiguos": [], "sem_classificacao": 0,
            "sem_referencia": 0, "pelo_de_para": 0, "de_para_contra_a_fonte": [],
            "classes_desconhecidas": {},
        }
        for item in itens:
            if item.tipo_proprio_id:
                continue  # tipo próprio manda: a empresa já declarou a natureza
            if item.tipo == Item.Tipo.COMPOSICAO:
                continue  # composição não é insumo; a classificação não a descreve

            natureza = self._natureza_do_item(
                item, candidatos=candidatos, declarado=declarado, achados=achados
            )
            if natureza is None or natureza == item.tipo:
                continue
            depara[(item.tipo, natureza)] = depara.get((item.tipo, natureza), 0) + 1
            if not seco:
                item.tipo = natureza
                for campo, valor in flags_da_natureza(natureza).items():
                    setattr(item, campo, valor)
                item.save(update_fields=[
                    "tipo", "compravel", "estocavel", "vendavel", "consumivel", "rastreavel",
                ])
        return depara, achados

    def _natureza_do_item(self, item, *, candidatos: dict, declarado: dict, achados: dict):
        """A natureza a aplicar, ou `None` para "não mexer neste item".

        Ordem de decisão — da declaração explícita da empresa para o palpite
        mais fraco, e cada degrau só é alcançado porque o de cima calou:

        1. **de-para da empresa** (`--de-para`): alguém olhou o item e disse o
           que ele é. Vence inclusive a fonte, e quando as duas discordam isso
           sai no relatório.
        2. **classificação da fonte**, entre os candidatos que **conferem** com
           o item pela descrição e pela unidade. Candidato que não confere é
           outro insumo com o mesmo número (D110) e não classifica nada aqui;
           candidatos que conferem e discordam entre si são ambiguidade, e
           ambiguidade não se resolve por sorteio.
        3. **proxy da unidade**, e só o conserto do defeito antigo: `servico`
           com unidade de hora/mês era mão de obra mal nomeada. Fora disso não
           há informação nova, e mexer seria adivinhar por cima do que o usuário
           pode já ter corrigido à mão.
        """
        pelo_arquivo = declarado.get((item.fonte_referencia, item.codigo_referencia))
        if pelo_arquivo is None:
            pelo_arquivo = declarado.get(("", item.codigo_referencia))

        conferem, discordantes = [], []
        for ref in candidatos.get((item.fonte_referencia, item.codigo_referencia), []):
            divergencia = identidade.conferir(
                descricao_catalogo=item.descricao,
                unidade_catalogo=item.unidade,
                descricao_publicacao=ref.descricao,
                unidade_publicacao=ref.unidade,
            )
            (discordantes if divergencia else conferem).append((ref, divergencia))

        pela_fonte = None
        if conferem:
            # A fonte respondeu e o de-para de classes não conheceu a palavra:
            # registrar o texto literal é o que permite a alguém decidir se
            # aquilo é uma classe de verdade (e vira linha em PREFIXOS_DE_CLASSE)
            # ou capítulo/lixo (e continua ignorada).
            for ref, _ in conferem:
                if classificacao_desconhecida(ref.grupo):
                    chave = ref.grupo.strip()
                    achados["classes_desconhecidas"][chave] = (
                        achados["classes_desconhecidas"].get(chave, 0) + 1
                    )
            naturezas = {
                natureza_da_classificacao(ref.grupo) for ref, _ in conferem
            } - {None}
            if len(naturezas) > 1:
                if pelo_arquivo is None:
                    achados["ambiguos"].append({
                        "codigo": item.codigo_referencia,
                        "descricao": item.descricao,
                        "naturezas": sorted(naturezas),
                        "publicacoes": [str(ref.base) for ref, _ in conferem],
                    })
                    return None
            elif naturezas:
                pela_fonte = naturezas.pop()

        if pelo_arquivo is not None:
            achados["pelo_de_para"] += 1
            if pela_fonte is not None and pela_fonte != pelo_arquivo:
                achados["de_para_contra_a_fonte"].append({
                    "codigo": item.codigo_referencia,
                    "descricao": item.descricao,
                    "da_fonte": pela_fonte,
                    "declarada": pelo_arquivo,
                })
            return pelo_arquivo

        if pela_fonte is not None:
            return pela_fonte

        if discordantes and not conferem:
            # Havia o que reler, e o que estava lá não é este item. Este é o
            # relato que o D110 pede: nada aplicado, e o caso na mão de alguém.
            ref, divergencia = discordantes[0]
            achados["nao_confere"].append({
                "codigo": item.codigo_referencia,
                "publicacao": str(ref.base),
                **divergencia.como_dict(),
            })
            return None

        # As duas ausências são diferentes e somá-las esconderia a do D111. O
        # item **achado** na publicação e sem a coluna `Classificação` é o caso
        # da publicação anterior a 01/2025; o item que a publicação carregada
        # não tem é procedência órfã (a edição de onde ele veio saiu do ar), e
        # para esse não há nada a reler nem a declarar aqui.
        if conferem:
            achados["sem_classificacao"] += 1
        else:
            achados["sem_referencia"] += 1
        if item.tipo == Item.Tipo.SERVICO and item.unidade.strip().upper() in {
            "H", "HORA", "MES", "MÊS", "H/M", "MÊS/H",
        }:
            return Item.Tipo.MAO_DE_OBRA
        return None

    # -- orçamentos em rascunho -------------------------------------------

    def _acertar_rascunhos(self, tenant, *, seco: bool) -> list[dict]:
        """Refaz categoria e parcela dos insumos já explodidos, só em rascunho."""
        tocados = []
        rascunhos = Orcamento.objects.filter(
            tenant=tenant, status=Orcamento.Status.RASCUNHO
        ).select_related("base_referencial")

        for orcamento in rascunhos:
            resolvedor = encargos_mod.ResolvedorEncargos(orcamento)
            antes = orcamento.valor_total
            mudou, preservadas = 0, 0

            linhas = ItemOrcado.objects.filter(orcamento=orcamento).exclude(insumos=None).distinct()
            for linha in linhas:
                insumos = list(
                    ItemOrcadoInsumo.objects.filter(item_orcado=linha).select_related(
                        "item", "item__tipo_proprio"
                    )
                )
                soma_antiga = sum((i.custo_no_item for i in insumos), Decimal("0"))
                soma_nova = Decimal("0")
                alterados = []
                for insumo in insumos:
                    if insumo.item is None:
                        soma_nova += insumo.custo_no_item
                        continue
                    categoria = precificacao.categoria_do_item(insumo.item)
                    bruto = insumo.coeficiente * insumo.custo_unitario
                    if precificacao.leva_encargo_social(insumo.item, categoria):
                        bruto *= resolvedor.fator(insumo.unidade or insumo.item.unidade)
                    novo_custo = bruto.quantize(QUATRO, rounding=ROUND_HALF_UP)
                    soma_nova += novo_custo
                    if categoria != insumo.categoria or novo_custo != insumo.custo_no_item:
                        insumo.categoria = categoria
                        insumo.custo_no_item = novo_custo
                        alterados.append(insumo)

                if not alterados:
                    continue
                mudou += len(alterados)
                if not seco:
                    ItemOrcadoInsumo.objects.bulk_update(
                        alterados, ["categoria", "custo_no_item"]
                    )
                # O custo da linha só acompanha se ele ainda ERA a soma dos
                # insumos. Preço aplicado do SCM/SIL ou digitado à mão é decisão
                # de alguém, e o comando não desfaz decisão de ninguém.
                if linha.custo_unitario == soma_antiga.quantize(QUATRO, rounding=ROUND_HALF_UP):
                    if not seco:
                        linha.custo_unitario = soma_nova.quantize(QUATRO, rounding=ROUND_HALF_UP)
                        linha.save(update_fields=["custo_unitario"])
                else:
                    preservadas += 1

            if not mudou:
                continue
            if not seco:
                planilha.recalcular_orcamento(orcamento)
                orcamento.refresh_from_db()
            tocados.append({
                "orcamento": f"{orcamento.descricao} v{orcamento.versao}",
                "obra": orcamento.obra_id,
                "insumos": mudou,
                "precos_preservados": preservadas,
                "antes": antes,
                "depois": orcamento.valor_total,
            })
        return tocados

    # -- relatório ---------------------------------------------------------

    def _relatorio(self, depara: dict, tocados: list[dict], achados: dict, *, seco: bool):
        rotulos = dict(Item.Tipo.choices)
        if not depara:
            self.stdout.write("Catálogo: nenhum item muda de natureza.")
        else:
            total = sum(depara.values())
            self.stdout.write(f"Catálogo: {total} item(ns) mudam de natureza.")
            for (antigo, novo), quantos in sorted(depara.items(), key=lambda x: -x[1]):
                self.stdout.write(
                    f"  {rotulos.get(antigo, antigo)} → {rotulos.get(novo, novo)}: {quantos}"
                )

        self._relatorio_dos_achados(achados, rotulos)

        if not tocados:
            self.stdout.write("Rascunhos: nenhum orçamento muda.")
        else:
            self.stdout.write(f"Rascunhos afetados: {len(tocados)}")
            for t in tocados:
                delta = t["depois"] - t["antes"]
                sinal = "+" if delta >= 0 else ""
                self.stdout.write(
                    f"  {t['orcamento']} (obra {t['obra']}): {t['insumos']} insumo(s), "
                    f"R$ {t['antes']} → R$ {t['depois']} ({sinal}{delta})"
                )
                if t["precos_preservados"]:
                    self.stdout.write(
                        f"    {t['precos_preservados']} linha(s) com preço próprio: "
                        "categoria corrigida, preço mantido."
                    )

        if seco:
            self.stdout.write(self.style.WARNING(
                "--dry-run: nada foi gravado. Rode sem o flag para aplicar."
            ))
        else:
            self.stdout.write(self.style.SUCCESS("Aplicado."))

    @staticmethod
    def _rotulo(rotulos: dict, natureza: str) -> str:
        """`Item.Tipo.choices` traz rótulo **lazy** (`gettext_lazy`), e concatenar
        um desses num `join` estoura. O `str()` resolve a tradução aqui."""
        return str(rotulos.get(natureza, natureza))

    def _relatorio_dos_achados(self, achados: dict, rotulos: dict):
        """O que o comando **não** aplicou — e é a parte que precisa ser lida.

        Sai antes do bloco dos rascunhos de propósito: quem roda isto quer saber
        primeiro o que ficou de fora, e não quantos totais mudaram.
        """
        if achados["pelo_de_para"]:
            self.stdout.write(
                f"  {achados['pelo_de_para']} pela classificação declarada no --de-para."
            )
        for caso in achados["de_para_contra_a_fonte"]:
            self.stdout.write(self.style.WARNING(
                f"    {caso['codigo']} — o --de-para diz "
                f"{self._rotulo(rotulos, caso['declarada'])} e a fonte diz "
                f"{self._rotulo(rotulos, caso['da_fonte'])}; valeu o --de-para."
            ))

        if achados["nao_confere"]:
            self.stdout.write(self.style.WARNING(
                f"Não confere ({len(achados['nao_confere'])}): o código existe na "
                "publicação, mas o item de lá não é o do catálogo. Nada aplicado — "
                "confira à mão."
            ))
            for caso in achados["nao_confere"][:20]:
                self.stdout.write(
                    f"  {caso['codigo']} ({caso['publicacao']}) — {caso['motivo']}: "
                    f'catálogo "{caso["descricao_catalogo"]}" ({caso["unidade_catalogo"]}) × '
                    f'publicação "{caso["descricao_publicacao"]}" ({caso["unidade_publicacao"]})'
                )
            if len(achados["nao_confere"]) > 20:
                self.stdout.write(f"  … e mais {len(achados['nao_confere']) - 20}.")

        if achados["ambiguos"]:
            self.stdout.write(self.style.WARNING(
                f"Ambíguos ({len(achados['ambiguos'])}): duas publicações classificam "
                "o mesmo item de formas diferentes. Nada aplicado — resolva com "
                "--de-para ou à mão."
            ))
            for caso in achados["ambiguos"][:20]:
                naturezas = " × ".join(self._rotulo(rotulos, n) for n in caso["naturezas"])
                self.stdout.write(
                    f"  {caso['codigo']} — {caso['descricao']}: {naturezas} "
                    f"({', '.join(caso['publicacoes'])})"
                )

        if achados["sem_classificacao"]:
            self.stdout.write(self.style.WARNING(
                f"Sem classificação na fonte: {achados['sem_classificacao']} item(ns). "
                "A coluna `Classificação` só existe nas publicações a partir de "
                "01/2025 — nas anteriores tudo que não é hora nem mês fica como "
                "material, e o comando não adivinha pela descrição. Saídas: "
                "importar uma publicação 2025+ e rodar de novo, ou classificar o "
                "que importa em planilha e passar em --de-para."
            ))
        if achados["sem_referencia"]:
            self.stdout.write(
                f"Sem publicação carregada: {achados['sem_referencia']} item(ns) "
                "trazem código de fonte que não está no banco — nada a reler."
            )

        if achados["classes_desconhecidas"]:
            desconhecidas = achados["classes_desconhecidas"]
            self.stdout.write(self.style.WARNING(
                f"Classes que o sistema não sabe ler: {len(desconhecidas)}. A fonte "
                "classificou e nós é que não entendemos a palavra — o item caiu no "
                "plano B da unidade, e unidade `H` vira mão de obra (leva encargo "
                "social). Cada uma, com quantos itens do seu catálogo dependem dela:"
            ))
            for classe, quantos in sorted(desconhecidas.items(), key=lambda x: -x[1])[:15]:
                self.stdout.write(f"  {quantos:>5}×  {classe}")
            if len(desconhecidas) > 15:
                self.stdout.write(f"  … e mais {len(desconhecidas) - 15}.")
