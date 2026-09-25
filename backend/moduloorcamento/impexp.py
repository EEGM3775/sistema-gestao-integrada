# backend/moduloorcamento/impexp.py
"""IE.1 — o Orçamento declara o que sai e o que entra.

**Este arquivo é o teste do desenho do `funcoesimpexp`.** O ORC.5b resolveu
importação de preço com conferência linha a linha, teto de plano em duas
grandezas, base-mãe do dono da plataforma e lote desfazível — tudo dentro de
`moduloorcamento/`. Migrar isso para o motor prova a fundação contra requisitos
reais (PDF de prefeitura, base de 90 mil linhas, banco travado) em vez de contra
requisitos imaginados.

O que a migração exigiu do motor, e que não existia no IE.0, está registrado
porque é o valor de ter migrado o primeiro consumidor:

1. **Contexto de destino** — importar não é "para o tenant", é "para *este*
   banco de preço" ou "para *esta* publicação". O motor ganhou `com_contexto()`
   e `validar_contexto()`.
2. **Quota de acervo** — `importacao_linhas` é de operação e o motor cuida; mas
   `banco_preco_linhas` conta linhas de tabela de preço e só o módulo sabe
   contar. Virou o gancho `checar_quota_objeto`.

O que **não** migrou, e por quê: a planilha orçamentária formatada (XLSX com
árvore EAP indentada e totais, PDF para assinar), a curva ABC e o cronograma
continuam em [exportacao.py](exportacao.py). Aquilo não é exportação tabular — é
**peça de documento**, com hierarquia, subtotal e cabeçalho técnico. Espremer no
escritor genérico de colunas perderia função, e a régua diz "sem perder função".
Aqui ficam as saídas que *são* tabelas.
"""
from __future__ import annotations

from decimal import Decimal

from funcoesimpexp.importacao import LimiteDoPlano
from funcoesimpexp.registro import Coluna, ContextoInvalido, Recurso, registrar

from nucleo import autorizacao

from .bancos import BancoTravado, exigir_editavel, recontar
from .models import (
    BancoPreco, BaseReferencial, InsumoReferencia, ItemBancoPreco, ItemOrcado, Orcamento,
)

# Sinônimos vistos em publicação real (SINAPI, ORSE, tabela de prefeitura). Vêm
# do `leitura.py` do ORC.5b, onde foram descobertos um a um abrindo arquivo de
# cliente — é conhecimento caro e o motivo de `aliases` existir no contrato.
ALIAS_CODIGO = ("codigo", "cod", "código", "cod.", "item", "referencia", "referência")
ALIAS_DESCRICAO = ("descricao", "descrição", "discriminacao", "discriminação", "insumo",
                   "servico", "serviço", "especificacao", "especificação")
ALIAS_UNIDADE = ("und", "un", "unid", "unidade", "u.m.", "um")
ALIAS_PRECO = ("preco", "preço", "custo", "valor", "preco unitario", "preço unitário",
               "custo unitario", "custo unitário", "preco mediano", "preço mediano",
               "valor unitario", "valor unitário")
ALIAS_GRUPO = ("grupo", "classe", "familia", "família", "categoria")


def _decimal(valor) -> Decimal:
    return valor if isinstance(valor, Decimal) else Decimal(str(valor or "0"))


# ---------------------------------------------------------------------------
# Banco de preço da empresa — a importação que o ORC.5b entregou
# ---------------------------------------------------------------------------


@registrar("orcamento.banco_preco")
class TabelaDePreco(Recurso):
    """Itens de um banco de preço próprio: a tabela da prefeitura, o histórico.

    O caso que motivou a conferência da R1 mora aqui — publicação oficial muda de
    layout entre edições, e preço errado não aparece como erro: aparece como
    orçamento perdido semanas depois.
    """

    rotulo = "Tabela de preço"
    modulo = "orcamento"
    # §3 — acesso total: ver o banco da empresa e poder escrever nele. Desde a
    # ORC.9 escrever numa tabela de preço é `orcamento.banco.edit`, e não mais a
    # permissão de quem orça: importar preço é montar a régua, não usá-la.
    # Nenhuma coluna daqui é PII, então não há permissão de máscara a somar.
    permissoes_exigidas = ("orcamento.banco.view", "orcamento.banco.edit")
    chave = "codigo"
    contexto_requerido = ("banco",)
    formatos_entrada = ("xlsx", "csv", "pdf")

    colunas = (
        Coluna("codigo", "Código", obrigatoria=True, exemplo="88309", aliases=ALIAS_CODIGO),
        Coluna("descricao", "Descrição", obrigatoria=True, aliases=ALIAS_DESCRICAO,
               exemplo="PEDREIRO COM ENCARGOS COMPLEMENTARES"),
        Coluna("unidade", "Und", obrigatoria=True, exemplo="H", aliases=ALIAS_UNIDADE),
        Coluna("custo_unitario", "Custo unitário", tipo=Decimal, obrigatoria=True,
               exemplo="23,45", aliases=ALIAS_PRECO),
        Coluna("grupo", "Grupo", exemplo="MÃO DE OBRA", aliases=ALIAS_GRUPO),
        Coluna("tipo", "Tipo", exemplo="insumo", aliases=("tipo item", "natureza")),
    )

    # --- destino ---------------------------------------------------------

    def validar_contexto(self, contexto, user, tenant_id) -> dict:
        banco = self._banco(contexto.get("banco"), tenant_id)
        try:
            # A trava do banco vale na porta: descobrir que ele está travado
            # depois de classificar 40 mil linhas é fazer o usuário esperar para
            # receber um "não".
            exigir_editavel(banco)
        except BancoTravado as exc:
            raise ContextoInvalido(str(exc)) from exc
        return {"banco": banco.pk}

    def _banco(self, banco_id, tenant_id) -> BancoPreco:
        banco = BancoPreco.objects.filter(pk=banco_id or 0, tenant_id=tenant_id).first()
        if banco is None:
            # Mesma mensagem para "não existe" e "é de outro tenant": distinguir
            # confirmaria a existência do banco alheio.
            raise ContextoInvalido("Escolha um banco de preço da sua empresa.")
        return banco

    def rotulo_do_contexto(self) -> str:
        banco = BancoPreco.objects.filter(pk=self.contexto.get("banco") or 0).first()
        return f"Banco: {banco.nome}" if banco else ""

    # --- teto de acervo (planta §9) --------------------------------------

    def checar_quota_objeto(self, novas, limites, tenant_id) -> None:
        limite = (limites or {}).get("banco_preco_linhas")
        if not isinstance(limite, int) or limite < 0:
            return
        atual = ItemBancoPreco.objects.filter(tenant_id=tenant_id).count()
        if atual + novas <= limite:
            return
        raise LimiteDoPlano(
            f"Sua empresa mantém {atual} linhas de banco próprio e o plano permite "
            f"{limite}. Este arquivo traria mais {novas}. Apague um banco que não usa "
            "ou faça upgrade.",
            limite=limite, tentado=atual + novas, quota="banco_preco_linhas",
        )

    # --- entrada ---------------------------------------------------------

    def validar_linha(self, dados) -> str:
        if _decimal(dados.get("custo_unitario")) < 0:
            return "Preço negativo."
        return ""

    def localizar(self, dados, tenant_id):
        return ItemBancoPreco.objects.filter(
            banco_id=self.contexto.get("banco"),
            tipo=self._tipo(dados),
            codigo=str(dados.get("codigo") or "")[:30],
        ).first()

    def aplicar_linha(self, dados, existente, tenant_id) -> dict:
        campos = {
            "descricao": str(dados.get("descricao") or "")[:500],
            "unidade": str(dados.get("unidade") or "")[:20],
            "custo_unitario": _decimal(dados.get("custo_unitario")),
            "grupo": str(dados.get("grupo") or "")[:150],
        }
        if existente is None:
            criado = ItemBancoPreco.objects.create(
                tenant_id=tenant_id, banco_id=self.contexto["banco"],
                tipo=self._tipo(dados), codigo=str(dados["codigo"])[:30], **campos,
            )
            self._marcar_importado(tenant_id)
            return {"acao": "criou", "pk": criado.pk}

        antes = {
            "descricao": existente.descricao,
            "unidade": existente.unidade,
            "custo_unitario": str(existente.custo_unitario),
            "grupo": existente.grupo,
        }
        for campo, valor in campos.items():
            setattr(existente, campo, valor)
        existente.save(update_fields=list(campos))
        self._marcar_importado(tenant_id)
        return {"acao": "atualizou", "pk": existente.pk, "antes": antes}

    def desfazer_linha(self, estado_anterior, tenant_id) -> None:
        item = ItemBancoPreco.objects.filter(pk=estado_anterior.get("pk")).first()
        if item is None:
            return
        if estado_anterior.get("acao") == "criou":
            banco_id = item.banco_id
            item.delete()
            self._recontar(banco_id)
            return
        antes = estado_anterior.get("antes") or {}
        item.descricao = antes.get("descricao", item.descricao)
        item.unidade = antes.get("unidade", item.unidade)
        item.custo_unitario = _decimal(antes.get("custo_unitario"))
        item.grupo = antes.get("grupo", item.grupo)
        item.save(update_fields=["descricao", "unidade", "custo_unitario", "grupo"])

    @staticmethod
    def _tipo(dados) -> str:
        bruto = str(dados.get("tipo") or "").strip().lower()
        if bruto.startswith("comp"):
            return InsumoReferencia.Tipo.COMPOSICAO
        return InsumoReferencia.Tipo.INSUMO

    def _marcar_importado(self, tenant_id) -> None:
        """Carimba a procedência do banco e reconta — como fazia o ORC.5b."""
        banco = BancoPreco.objects.filter(pk=self.contexto.get("banco")).first()
        if banco is None:
            return
        if banco.origem != BancoPreco.Origem.IMPORTADA:
            banco.origem = BancoPreco.Origem.IMPORTADA
            banco.save(update_fields=["origem", "atualizado_em"])
        recontar(banco)

    def _recontar(self, banco_id) -> None:
        banco = BancoPreco.objects.filter(pk=banco_id).first()
        if banco is not None:
            recontar(banco)

    # --- saída -----------------------------------------------------------

    def queryset(self, request, recorte):
        """R7 — os mesmos filtros da tela de bancos."""
        itens = ItemBancoPreco.objects.filter(banco_id=self.contexto.get("banco"))
        if recorte.get("tipo"):
            itens = itens.filter(tipo=recorte["tipo"])
        if recorte.get("grupo"):
            itens = itens.filter(grupo__icontains=recorte["grupo"])
        if recorte.get("busca"):
            itens = itens.filter(descricao__icontains=recorte["busca"])
        return itens.order_by("codigo")


# ---------------------------------------------------------------------------
# Base-mãe: publicação global, só o dono da plataforma
# ---------------------------------------------------------------------------


@registrar("orcamento.base_referencial")
class PublicacaoReferencial(TabelaDePreco):
    """SINAPI/ORSE — a base pública, que vale para **todos** os tenants.

    Herda a leitura da tabela de preço porque o arquivo é o mesmo (é literalmente
    a mesma publicação); o que muda é o destino e quem pode. A conferência
    continua morando no tenant de quem importou — é só o `aplicar` que atravessa
    a fronteira, e ele é o único ponto do módulo que faz isso.
    """

    rotulo = "Base referencial (pública)"
    contexto_requerido = ("base",)

    def validar_contexto(self, contexto, user, tenant_id) -> dict:
        if not autorizacao.supervisiona(user):
            raise ContextoInvalido(
                "Só o dono da plataforma publica base-mãe — ela vale para todas as "
                "empresas. Importe para um banco de preço da sua empresa."
            )
        base = BaseReferencial.objects.filter(pk=contexto.get("base") or 0).first()
        if base is None:
            raise ContextoInvalido("Informe a publicação de destino.")
        return {"base": base.pk}

    def rotulo_do_contexto(self) -> str:
        base = BaseReferencial.objects.filter(pk=self.contexto.get("base") or 0).first()
        return f"Publicação: {base.rotulo or base.rotulo_automatico()}" if base else ""

    def checar_quota_objeto(self, novas, limites, tenant_id) -> None:
        """Base pública não consome quota de ninguém: não é acervo de tenant."""
        return None

    def localizar(self, dados, tenant_id):
        return InsumoReferencia.objects.filter(
            base_id=self.contexto.get("base"),
            tipo=self._tipo(dados),
            codigo=str(dados.get("codigo") or "")[:30],
        ).first()

    def aplicar_linha(self, dados, existente, tenant_id) -> dict:
        campos = {
            "descricao": str(dados.get("descricao") or "")[:500],
            "unidade": str(dados.get("unidade") or "")[:20],
            "custo_unitario": _decimal(dados.get("custo_unitario")),
            "grupo": str(dados.get("grupo") or "")[:150],
        }
        if existente is None:
            criado = InsumoReferencia.objects.create(
                base_id=self.contexto["base"], tipo=self._tipo(dados),
                codigo=str(dados["codigo"])[:30], **campos,
            )
            self._recontar_base()
            return {"acao": "criou", "pk": criado.pk}
        antes = {
            "descricao": existente.descricao, "unidade": existente.unidade,
            "custo_unitario": str(existente.custo_unitario), "grupo": existente.grupo,
        }
        for campo, valor in campos.items():
            setattr(existente, campo, valor)
        existente.save(update_fields=list(campos))
        return {"acao": "atualizou", "pk": existente.pk, "antes": antes}

    def desfazer_linha(self, estado_anterior, tenant_id) -> None:
        referencia = InsumoReferencia.objects.filter(pk=estado_anterior.get("pk")).first()
        if referencia is None:
            return
        if estado_anterior.get("acao") == "criou":
            referencia.delete()
            self._recontar_base()
            return
        antes = estado_anterior.get("antes") or {}
        referencia.descricao = antes.get("descricao", referencia.descricao)
        referencia.unidade = antes.get("unidade", referencia.unidade)
        referencia.custo_unitario = _decimal(antes.get("custo_unitario"))
        referencia.grupo = antes.get("grupo", referencia.grupo)
        referencia.save(update_fields=["descricao", "unidade", "custo_unitario", "grupo"])

    def _recontar_base(self) -> None:
        base = BaseReferencial.objects.filter(pk=self.contexto.get("base") or 0).first()
        if base is None:
            return
        base.total_insumos = InsumoReferencia.objects.filter(
            base=base, tipo=InsumoReferencia.Tipo.INSUMO,
        ).count()
        base.total_composicoes = InsumoReferencia.objects.filter(
            base=base, tipo=InsumoReferencia.Tipo.COMPOSICAO,
        ).count()
        base.save(update_fields=["total_insumos", "total_composicoes"])

    def queryset(self, request, recorte):
        referencias = InsumoReferencia.objects.filter(base_id=self.contexto.get("base"))
        if recorte.get("tipo"):
            referencias = referencias.filter(tipo=recorte["tipo"])
        if recorte.get("busca"):
            referencias = referencias.filter(descricao__icontains=recorte["busca"])
        return referencias.order_by("codigo")


# ---------------------------------------------------------------------------
# Planilha orçamentária — as linhas da EAP como tabela
# ---------------------------------------------------------------------------


@registrar("orcamento.planilha")
class PlanilhaOrcamentaria(Recurso):
    """As linhas de um orçamento, para levar ao Excel e trazer de volta.

    Complementa (não substitui) a exportação formatada de
    [exportacao.py](exportacao.py): lá sai a peça com árvore indentada e totais,
    para o edital; aqui sai a tabela plana, que volta editada.
    """

    rotulo = "Planilha orçamentária"
    modulo = "orcamento"
    permissoes_exigidas = (
        "orcamento.orcamento.view", "orcamento.orcamento.edit",
        "orcamento.item.view", "orcamento.item.edit",
    )
    chave = "codigo_eap"
    contexto_requerido = ("orcamento",)

    colunas = (
        Coluna("codigo_eap", "Item", obrigatoria=True, exemplo="1.2.1",
               aliases=("item", "eap", "codigo", "código")),
        Coluna("descricao", "Descrição", obrigatoria=True, aliases=ALIAS_DESCRICAO,
               exemplo="Alvenaria de vedação"),
        Coluna("unidade", "Und", exemplo="m²", aliases=ALIAS_UNIDADE),
        Coluna("quantidade", "Quantidade", tipo=Decimal, exemplo="128,50",
               aliases=("qtd", "quant")),
        Coluna("custo_unitario", "Custo unitário", tipo=Decimal, exemplo="87,30",
               aliases=ALIAS_PRECO),
    )

    def validar_contexto(self, contexto, user, tenant_id) -> dict:
        orcamento = Orcamento.objects.filter(
            pk=contexto.get("orcamento") or 0, tenant_id=tenant_id,
        ).first()
        if orcamento is None:
            raise ContextoInvalido("Escolha um orçamento da sua empresa.")
        return {"orcamento": orcamento.pk, "editavel": orcamento.editavel}

    def rotulo_do_contexto(self) -> str:
        orcamento = self._orcamento()
        return f"{orcamento.descricao} (v{orcamento.versao})" if orcamento else ""

    def _orcamento(self):
        return Orcamento.objects.filter(pk=self.contexto.get("orcamento") or 0).first()

    # --- entrada ---------------------------------------------------------

    def validar_linha(self, dados) -> str:
        # Régua congelada não recebe linha por importação: orçamento aprovado é
        # compromisso, e mexer nele exige a revisão (que gera versão nova e deixa
        # rastro). Deixar a importação furar isso seria a porta paralela que a R7
        # existe para fechar, do lado da escrita.
        if not self.contexto.get("editavel", True):
            return "Orçamento aprovado — crie uma revisão para alterar as linhas."
        if _decimal(dados.get("quantidade")) < 0:
            return "Quantidade negativa."
        if _decimal(dados.get("custo_unitario")) < 0:
            return "Custo unitário negativo."
        return ""

    def localizar(self, dados, tenant_id):
        return ItemOrcado.objects.filter(
            orcamento_id=self.contexto.get("orcamento"),
            codigo_eap=str(dados.get("codigo_eap") or "")[:30],
        ).first()

    def aplicar_linha(self, dados, existente, tenant_id) -> dict:
        campos = {
            "descricao": str(dados.get("descricao") or "")[:255],
            "unidade": str(dados.get("unidade") or "")[:20],
            "quantidade": _decimal(dados.get("quantidade")),
            "custo_unitario": _decimal(dados.get("custo_unitario")),
        }
        if existente is None:
            criado = ItemOrcado.objects.create(
                tenant_id=tenant_id, orcamento_id=self.contexto["orcamento"],
                codigo_eap=str(dados["codigo_eap"])[:30],
                tipo_linha=ItemOrcado.TipoLinha.ANALITICO, **campos,
            )
            self._recalcular()
            return {"acao": "criou", "pk": criado.pk}

        antes = {
            "descricao": existente.descricao, "unidade": existente.unidade,
            "quantidade": str(existente.quantidade),
            "custo_unitario": str(existente.custo_unitario),
        }
        for campo, valor in campos.items():
            setattr(existente, campo, valor)
        existente.save(update_fields=list(campos))
        self._recalcular()
        return {"acao": "atualizou", "pk": existente.pk, "antes": antes}

    def desfazer_linha(self, estado_anterior, tenant_id) -> None:
        item = ItemOrcado.objects.filter(pk=estado_anterior.get("pk")).first()
        if item is None:
            return
        if estado_anterior.get("acao") == "criou":
            item.delete()
        else:
            antes = estado_anterior.get("antes") or {}
            item.descricao = antes.get("descricao", item.descricao)
            item.unidade = antes.get("unidade", item.unidade)
            item.quantidade = _decimal(antes.get("quantidade"))
            item.custo_unitario = _decimal(antes.get("custo_unitario"))
            item.save(update_fields=["descricao", "unidade", "quantidade", "custo_unitario"])
        self._recalcular()

    def _recalcular(self) -> None:
        """Totais e pesos saem do mesmo lugar de sempre — importar não é atalho."""
        from .planilha import recalcular_orcamento

        orcamento = self._orcamento()
        if orcamento is not None:
            recalcular_orcamento(orcamento)

    # --- saída -----------------------------------------------------------

    def queryset(self, request, recorte):
        itens = ItemOrcado.objects.filter(orcamento_id=self.contexto.get("orcamento"))
        if recorte.get("etapa"):
            itens = itens.filter(etapa_id=recorte["etapa"])
        if (recorte.get("nivel") or "").lower() == "sintetico":
            itens = itens.filter(tipo_linha=ItemOrcado.TipoLinha.SINTETICO)
        return itens.order_by("codigo_eap", "ordem", "item_orcado_id")
