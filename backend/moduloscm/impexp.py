# backend/moduloscm/impexp.py
"""D70 — o XML e o DANFE da NF-e da compra saem pela porta única (D284).

O XML de uma NF-e carrega CNPJ, endereço e a lista do que se comprou: é dado
fiscal completo, e não pode sair por `/media/` (fora de auth, entitlement e
RLS). Entra pelo recebimento do pedido; sai daqui, com `scm.recebimento.view`,
e aparece no DMS como todo arquivo guardado.

**As listas da tela de Suprimentos (15/10/2026).** A oferta importa; demanda,
cotação e pedido só exportam (decisão do dono): a tabela de preço do fornecedor
é o caso clássico de carga por planilha — uma linha é a oferta inteira —, e os
outros são documentos com itens e fluxo (cotar, adjudicar, aprovar, gerar título
no ERP), que nascem pela tela.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Count

from funcoesimpexp.cadastro import RecursoDeCadastro, RecursoDeLista, sim_ou_nao
from funcoesimpexp.entrega import buscar_do_tenant, entregar_campo
from funcoesimpexp.registro import (
    NATUREZA_ARQUIVO,
    ArquivoEntregue,
    Coluna,
    ContextoInvalido,
    EntregaInvalida,
    Guardado,
    Recurso,
    registrar,
)

from .models import Cotacao, Demanda, NotaFiscalCompra, OfertaFornecedor, PedidoCompra

RECURSO_NOTA_COMPRA = "scm.nota_compra"
RECURSO_OFERTAS = "scm.oferta"
RECURSO_DEMANDAS = "scm.demanda"
RECURSO_COTACOES = "scm.cotacao"
RECURSO_PEDIDOS = "scm.pedido"

#: Espécie → (campo, nome de fallback).
_ARQUIVOS = {
    "xml": ("arquivo_xml", "nfe.xml"),
    "pdf": ("arquivo_pdf", "danfe.pdf"),
}


@registrar(RECURSO_NOTA_COMPRA)
class ArquivosDaNotaDeCompra(Recurso):
    """XML e DANFE da NF-e lançada no recebimento do pedido de compra."""

    rotulo = "NF-e das compras"
    modulo = "scm"
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("scm.recebimento.view", "scm.recebimento.edit")
    permissoes_entrega = ("scm.recebimento.view",)
    guardados = tuple(Guardado(especie, NotaFiscalCompra, campo) for especie, (campo, _) in _ARQUIVOS.items())

    colunas = (
        Coluna("numero", "Número da nota"),
        Coluna("chave_acesso", "Chave de acesso"),
        Coluna("data_emissao", "Data de emissão"),
        Coluna("arquivo", "Arquivo"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        alvo = _ARQUIVOS.get(especie)
        if alvo is None:
            raise EntregaInvalida(f"Espécie '{especie}' não existe na NF-e da compra.")
        campo, alternativa = alvo
        nota = buscar_do_tenant(NotaFiscalCompra, chave, tenant_id)
        return entregar_campo(nota, getattr(nota, campo), alternativa=alternativa)


# ---------------------------------------------------------------------------
# As listas da tela de Suprimentos (15/10/2026) — ver o cabeçalho
# ---------------------------------------------------------------------------


@registrar(RECURSO_OFERTAS)
class OfertasDosFornecedores(RecursoDeCadastro):
    """A oferta: item do catálogo **+** fornecedor, como a restrição do banco.

    O item vem pelo código do catálogo e o fornecedor pela razão social — os dois
    têm de existir (cadastre o item e o fornecedor antes). A publicação na rede
    fica fora do arquivo: é opt-in na tela.
    """

    rotulo = "Ofertas dos fornecedores"
    modulo = "scm"
    permissoes_exigidas = ("scm.oferta.view", "scm.oferta.edit")
    modelo = OfertaFornecedor
    chave = "produto"
    ordem = ("produto__descricao", "preco_direto")
    campos_de_busca = ("produto__descricao", "produto__codigo_interno", "codigo_no_fornecedor")
    filtros = {"produto": "produto_id", "fornecedor": "fornecedor_id", "ativo": "ativo"}

    @property
    def referencias(self) -> dict:
        from catalogo.models import Item
        from fornecedores.models import Fornecedor

        return {
            "produto": (Item, "codigo_interno"),
            "fornecedor": (Fornecedor, "razao_social"),
        }

    colunas = (
        Coluna("produto", "Código do item", obrigatoria=True, exemplo="CIM-50",
               aliases=("item", "codigo", "código")),
        Coluna("fornecedor", "Fornecedor", obrigatoria=True, exemplo="Concreto Forte Ltda",
               aliases=("razao social", "loja")),
        Coluna("codigo_no_fornecedor", "Código no fornecedor", exemplo="CF-1020"),
        Coluna("preco_direto", "Preço", tipo=Decimal, obrigatoria=True, exemplo="38,90",
               aliases=("preco direto", "preço direto", "valor")),
        Coluna("estoque_disponivel", "Estoque disponível", tipo=Decimal, exemplo="500",
               aliases=("estoque",)),
        Coluna("prazo_entrega_dias", "Prazo de entrega (dias)", tipo=int, exemplo="3",
               aliases=("prazo",)),
        Coluna("compra_direta", "Compra direta", exemplo="Sim"),
        Coluna("regiao_entrega", "Região de entrega", exemplo="Salvador/BA"),
        Coluna("vigencia_inicio", "Vigência (início)", tipo=date, exemplo="01/11/2026"),
        Coluna("vigencia_fim", "Vigência (fim)", tipo=date, exemplo="31/12/2026"),
        Coluna("ativo", "Ativa", exemplo="Sim"),
    )

    def chave_da_linha(self, dados: dict) -> str:
        codigo = self.normalizar_chave(dados.get("produto"))
        fornecedor = str(dados.get("fornecedor") or "").strip()
        return f"{codigo} ({fornecedor})" if codigo and fornecedor else codigo

    def localizar(self, dados: dict, tenant_id):
        item = self._referencia("produto", dados.get("produto"), tenant_id)
        fornecedor = self._referencia("fornecedor", dados.get("fornecedor"), tenant_id)
        if item is None or fornecedor is None:
            return None
        return OfertaFornecedor.objects.filter(
            tenant_id=tenant_id, produto=item, fornecedor=fornecedor,
        ).first()

    def serializar_objeto(self, obj) -> dict:
        saida = super().serializar_objeto(obj)
        saida["compra_direta"] = "Sim" if obj.compra_direta else "Não"
        saida["ativo"] = "Sim" if obj.ativo else "Não"
        return saida

    def campos(self, dados: dict, tenant_id) -> dict:
        saida = super().campos(dados, tenant_id)
        saida["compra_direta"] = sim_ou_nao(dados.get("compra_direta"), False)
        saida["ativo"] = sim_ou_nao(dados.get("ativo"), True)
        if saida.get("estoque_disponivel") is None:
            saida["estoque_disponivel"] = Decimal("0")
        return saida

    def validar_no_destino(self, dados: dict, tenant_id) -> str:
        # Antes do `full_clean`, que leria o `None` de um Sim/Não torto como
        # "campo obrigatório" — e a frase certa é dizer o que veio.
        for campo in ("compra_direta", "ativo"):
            if sim_ou_nao(dados.get(campo), True) is None:
                return f"{self._rotulo(campo)}: “{dados.get(campo)}” — use Sim ou Não."
        return super().validar_no_destino(dados, tenant_id)

    def validar_regras(self, objeto, dados, tenant_id) -> str:
        if objeto.preco_direto is not None and objeto.preco_direto <= 0:
            return "Preço tem de ser maior que zero."
        if objeto.estoque_disponivel < 0:
            return "Estoque disponível negativo."
        if objeto.vigencia_inicio and objeto.vigencia_fim and objeto.vigencia_fim < objeto.vigencia_inicio:
            return "Fim da vigência anterior ao início."
        return ""


@registrar(RECURSO_DEMANDAS)
class DemandasParaDecidir(RecursoDeLista):
    """As demandas que a tela mostra: as que ainda esperam cotação ou compra."""

    rotulo = "Demandas"
    modulo = "scm"
    permissoes_exigidas = ("scm.demanda.view",)
    modelo = Demanda
    ordem = ("-criado_em",)
    filtros = {"tipo": "tipo", "origem": "origem", "centro_custo": "centro_custo_id"}

    colunas = (
        Coluna("demanda_id", "Demanda", tipo=int),
        Coluna("tipo", "Tipo"),
        Coluna("origem", "Origem"),
        Coluna("centro_custo__nome", "Centro de custo"),
        Coluna("itens_count", "Itens", tipo=int),
        Coluna("status", "Estado"),
        Coluna("categoria", "Categoria"),
        Coluna("observacao", "Observação"),
        Coluna("criado_em", "Criada em", tipo=date),
    )

    def escopo(self, qs, request):
        abertas = (Demanda.Status.RASCUNHO, Demanda.Status.ABERTA, Demanda.Status.EM_COTACAO)
        return qs.filter(status__in=abertas).select_related("centro_custo").annotate(
            itens_count=Count("itens"),
        )


@registrar(RECURSO_COTACOES)
class CotacoesDaEmpresa(RecursoDeLista):
    rotulo = "Cotações"
    modulo = "scm"
    permissoes_exigidas = ("scm.cotacao.view",)
    modelo = Cotacao
    ordem = ("-criado_em",)
    filtros = {"status": "status", "demanda": "demanda_id"}

    colunas = (
        Coluna("cotacao_id", "Cotação", tipo=int),
        Coluna("demanda_id", "Demanda", tipo=int),
        Coluna("status", "Estado"),
        Coluna("propostas_count", "Propostas", tipo=int),
        Coluna("data_limite", "Encerra", tipo=date),
        Coluna("observacao", "Observação"),
    )

    def escopo(self, qs, request):
        return qs.annotate(propostas_count=Count("propostas"))


@registrar(RECURSO_PEDIDOS)
class PedidosDeCompra(RecursoDeLista):
    rotulo = "Pedidos de compra"
    modulo = "scm"
    permissoes_exigidas = ("scm.pedido.view",)
    modelo = PedidoCompra
    ordem = ("-criado_em",)
    filtros = {"status": "status", "origem": "origem", "fornecedor": "fornecedor_id",
               "centro_custo": "centro_custo_id"}

    colunas = (
        Coluna("pedido_id", "Pedido", tipo=int),
        Coluna("origem", "Via"),
        Coluna("fornecedor__razao_social", "Fornecedor"),
        Coluna("centro_custo__nome", "Centro de custo"),
        Coluna("valor_total", "Valor", tipo=Decimal),
        Coluna("data_pedido", "Data", tipo=date),
        Coluna("data_entrega_prevista", "Entrega prevista", tipo=date),
        Coluna("status", "Estado"),
        Coluna("observacao", "Observação"),
    )

    def escopo(self, qs, request):
        return qs.select_related("fornecedor", "centro_custo")


# --- A planilha da cotação: sai para o fornecedor, volta com o preço (16/10/2026) ---

RECURSO_PROPOSTA = "scm.proposta"


@registrar(RECURSO_PROPOSTA)
class PlanilhaDaCotacao(Recurso):
    """Os itens de uma cotação, para o fornecedor preencher o preço — e a volta.

    *Dono, 16/10/2026:* a cotação também é alimentada por quem compra, digitando
    ou importando; a rede ainda não está no ar. É o padrão do Senior e do
    Alterdata: o sistema gera a planilha com o que se pede, o fornecedor devolve
    com o preço, e ela entra como a proposta dele.

    **Destino (`contexto`):** a cotação e, na volta, o fornecedor — com a data em
    que o preço chegou e o prazo, que não são coluna (valem para a proposta
    inteira). Linha sem preço é item que ele não cotou: não trava o lote, só não
    entra. O total sai de `propostas.recalcular_total`, o mesmo da tela.
    """

    rotulo = "Planilha para cotação"
    modulo = "scm"
    permissoes_exigidas = ("scm.cotacao.view", "scm.cotacao.edit")
    chave = "item_demanda"
    contexto_requerido = ("cotacao", "fornecedor")
    # A planilha vai ao fornecedor e volta preenchida: PDF não tem onde digitar.
    formatos_saida = ("xlsx", "csv")

    colunas = (
        Coluna("item_demanda", "Nº da linha (não altere)", tipo=int, obrigatoria=True, exemplo="41",
               aliases=("linha", "nº da linha", "n da linha")),
        Coluna("codigo", "Código", exemplo="ITM-0012"),
        Coluna("descricao", "Item", exemplo="Cimento CP-II 50 kg"),
        Coluna("unidade", "Und", exemplo="sc"),
        Coluna("quantidade", "Quantidade", tipo=Decimal, exemplo="50"),
        Coluna("preco_unitario", "Preço unitário", tipo=Decimal, exemplo="32,50",
               aliases=("preço", "preco", "valor unitário", "valor unitario")),
    )

    # --- destino ------------------------------------------------------------------

    def validar_contexto(self, contexto, user, tenant_id) -> dict:
        from fornecedores.models import Fornecedor

        contexto = dict(contexto or {})
        cotacao = Cotacao.objects.filter(pk=contexto.get("cotacao") or 0, tenant_id=tenant_id).first()
        if cotacao is None:
            raise ContextoInvalido("Abra uma cotação da sua empresa.")
        saida = {"cotacao": cotacao.pk}
        if not contexto.get("fornecedor"):
            return saida  # a ida: a planilha sai sem fornecedor
        fornecedor = Fornecedor.objects.filter(pk=contexto["fornecedor"], tenant_id=tenant_id).first()
        if fornecedor is None:
            raise ContextoInvalido("Escolha um fornecedor da sua empresa.")
        if cotacao.status != Cotacao.Status.ABERTA:
            raise ContextoInvalido("A cotação não está aberta: proposta só entra enquanto ela está em aberto.")
        if cotacao.propostas.filter(fornecedor=fornecedor).exists():
            raise ContextoInvalido("Este fornecedor já tem proposta nesta cotação — edite a que existe.")
        try:
            recebida = date.fromisoformat(contexto["recebida_em"]) if contexto.get("recebida_em") else None
            prazo = contexto.get("prazo_entrega_dias")
            prazo = int(prazo) if prazo not in (None, "") else None
        except (TypeError, ValueError):
            raise ContextoInvalido("Data ou prazo inválido.")
        if prazo is not None and prazo < 0:
            raise ContextoInvalido("Prazo negativo.")
        return {
            **saida, "fornecedor": fornecedor.pk,
            "recebida_em": recebida.isoformat() if recebida else None, "prazo_entrega_dias": prazo,
        }

    def rotulo_do_contexto(self) -> str:
        from fornecedores.models import Fornecedor

        fornecedor = Fornecedor.objects.filter(pk=self.contexto.get("fornecedor") or 0).only("razao_social").first()
        base = f"Cotação #{self.contexto.get('cotacao')}"
        return f"{base} · {fornecedor.razao_social}" if fornecedor else base

    def _cotacao(self):
        return Cotacao.objects.filter(pk=self.contexto.get("cotacao") or 0).first()

    # --- a ida --------------------------------------------------------------------

    def queryset(self, request, recorte):
        from .models import ItemDemanda

        cotacao = self._cotacao()
        if cotacao is None:
            return ItemDemanda.objects.none()
        return (ItemDemanda.objects.filter(demanda_id=cotacao.demanda_id)
                .select_related("produto").order_by("item_demanda_id"))

    def serializar_objeto(self, obj) -> dict:
        produto = obj.produto if obj.produto_id else None
        return {
            "item_demanda": obj.pk,
            "codigo": produto.codigo_interno if produto else "",
            "descricao": produto.descricao if produto else (obj.descricao_servico or ""),
            "unidade": obj.unidade or (produto.unidade if produto else ""),
            "quantidade": obj.quantidade,
            "preco_unitario": None,
        }

    # --- a volta ------------------------------------------------------------------

    def validar_linha(self, dados) -> str:
        if not self.contexto.get("fornecedor"):
            return "Escolha o fornecedor desta proposta antes de importar."
        preco = dados.get("preco_unitario")
        if preco not in (None, "") and Decimal(str(preco)) < 0:
            return "Preço negativo."
        return ""

    def validar_no_destino(self, dados, tenant_id) -> str:
        from .models import ItemDemanda

        cotacao = self._cotacao()
        if cotacao is None or not ItemDemanda.objects.filter(
            pk=dados.get("item_demanda") or 0, demanda_id=cotacao.demanda_id,
        ).exists():
            return "Linha que não é desta cotação — use a planilha baixada dela."
        return ""

    def localizar(self, dados, tenant_id):
        from .models import ItemProposta

        return ItemProposta.objects.filter(
            proposta__cotacao_id=self.contexto.get("cotacao"),
            proposta__fornecedor_id=self.contexto.get("fornecedor"),
            item_demanda_id=dados.get("item_demanda") or 0,
        ).first()

    def aplicar_linha(self, dados, existente, tenant_id) -> dict | None:
        from django.utils import timezone

        from fornecedores.models import Fornecedor

        from . import propostas
        from .models import ItemDemanda, ItemProposta, Proposta

        if dados.get("preco_unitario") in (None, ""):
            return None  # item que o fornecedor não cotou
        cotacao = self._cotacao()
        linha = ItemDemanda.objects.get(pk=dados["item_demanda"], demanda_id=cotacao.demanda_id)
        proposta = cotacao.propostas.filter(fornecedor_id=self.contexto["fornecedor"]).first()
        if proposta is None:
            fornecedor = Fornecedor.objects.get(pk=self.contexto["fornecedor"])
            recebida = self.contexto.get("recebida_em")
            proposta = Proposta.objects.create(
                tenant_id=cotacao.tenant_id, cotacao=cotacao, fornecedor=fornecedor,
                fornecedor_nome=fornecedor.razao_social,
                recebida_em=date.fromisoformat(recebida) if recebida else timezone.localdate(),
                prazo_entrega_dias=self.contexto.get("prazo_entrega_dias"),
            )
        item = ItemProposta.objects.create(
            tenant_id=cotacao.tenant_id, proposta=proposta, item_demanda=linha,
            preco_unitario=Decimal(str(dados["preco_unitario"])), quantidade=linha.quantidade,
        )
        propostas.recalcular_total(proposta)
        return {"acao": "criou", "pk": item.pk}

    def desfazer_linha(self, estado_anterior, tenant_id) -> None:
        from . import propostas
        from .models import ItemProposta

        item = ItemProposta.objects.select_related("proposta").filter(pk=estado_anterior.get("pk")).first()
        if item is None:
            return
        proposta = item.proposta
        item.delete()
        if proposta.itens.exists():
            propostas.recalcular_total(proposta)
        else:
            proposta.delete()
