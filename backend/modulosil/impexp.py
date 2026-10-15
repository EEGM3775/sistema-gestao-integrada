# backend/modulosil/impexp.py
"""Estoque & Logística entram e saem como planilha (15/10/2026).

**Almoxarifado e ferramenta importam; o resto só exporta** (decisão do dono,
15/10/2026). Os dois são cadastro — uma linha é o registro inteiro. Movimento,
requisição, transferência, devolução, inventário, entrega de EPI e empréstimo
mexem no saldo ou têm fluxo (aprovar, atender, fechar, devolver): nascem pela
tela. A curva ABC é relatório calculado.

Toda saída roda o ViewSet da própria tela (`viewset`), no recorte dela.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from funcoesimpexp.cadastro import RecursoDeCadastro, RecursoDeLista, sim_ou_nao
from funcoesimpexp.registro import Coluna, registrar
from funcoesimpexp.relatorio import RecursoDeRelatorio

from . import views
from .models import (
    Devolucao, EmprestimoFerramenta, EntregaEPI, Ferramenta, Inventario, LocalEstoque,
    MovimentacaoEstoque, Requisicao, SaldoEstoque, Transferencia,
)


def _pessoa(funcionario, nome: str) -> str:
    return nome or (funcionario.nome_completo if funcionario is not None else "")


def _sim_nao_invalido(recurso, dados: dict, campos: tuple[str, ...]) -> str:
    for campo in campos:
        if sim_ou_nao(dados.get(campo), True) is None:
            return f"{recurso._rotulo(campo)}: “{dados.get(campo)}” — use Sim ou Não."
    return ""


# ---------------------------------------------------------------------------
# Cadastros — importam
# ---------------------------------------------------------------------------


@registrar("sil.local")
class Almoxarifados(RecursoDeCadastro):
    """Almoxarifado, canteiro, consignação. A chave é o nome, único por empresa."""

    rotulo = "Almoxarifados e canteiros"
    modulo = "sil"
    permissoes_exigidas = ("sil.local.view", "sil.local.edit")
    modelo = LocalEstoque
    chave = "nome"
    ordem = ("nome",)
    viewset = views.LocalEstoqueViewSet

    @property
    def referencias(self) -> dict:
        from empreendimentos.models import Empreendimento
        from fornecedores.models import Fornecedor
        from obras.models import Obra

        return {
            "obra": (Obra, "nome_obra"),
            "empreendimento": (Empreendimento, "empreendimento"),
            "fornecedor": (Fornecedor, "razao_social"),
        }

    colunas = (
        Coluna("nome", "Nome", obrigatoria=True, exemplo="Canteiro Torre A", aliases=("local", "almoxarifado")),
        Coluna("tipo", "Tipo", exemplo="Canteiro de obra"),
        Coluna("obra", "Obra", exemplo="Torre A"),
        Coluna("empreendimento", "Empreendimento", exemplo="Residencial Aurora"),
        Coluna("fornecedor", "Fornecedor (consignação)", exemplo=""),
        Coluna("endereco", "Endereço", exemplo="Av. Paralela, 1000"),
        Coluna("ativo", "Ativo", exemplo="Sim"),
    )

    def localizar(self, dados: dict, tenant_id):
        nome = self.normalizar_chave(dados.get("nome"))
        return LocalEstoque.objects.filter(tenant_id=tenant_id, nome__iexact=nome).first() if nome else None

    def serializar_objeto(self, obj) -> dict:
        saida = super().serializar_objeto(obj)
        saida["ativo"] = "Sim" if obj.ativo else "Não"
        return saida

    def campos(self, dados: dict, tenant_id) -> dict:
        saida = super().campos(dados, tenant_id)
        saida["tipo"] = saida.get("tipo") or LocalEstoque.Tipo.CENTRAL
        saida["ativo"] = sim_ou_nao(dados.get("ativo"), True)
        return saida

    def validar_no_destino(self, dados: dict, tenant_id) -> str:
        return _sim_nao_invalido(self, dados, ("ativo",)) or super().validar_no_destino(dados, tenant_id)


@registrar("sil.ferramenta")
class Ferramentas(RecursoDeCadastro):
    """A ferramenta do comodato. Identidade: o **patrimônio** quando há; sem ele,
    o nome — então duas "Furadeira" sem plaqueta não entram (dê o patrimônio).
    "Emprestada" não entra pela planilha: é o empréstimo que põe a ferramenta
    na mão de alguém."""

    rotulo = "Ferramentas"
    modulo = "sil"
    permissoes_exigidas = ("sil.ferramenta.view", "sil.ferramenta.edit")
    modelo = Ferramenta
    chave = "nome"
    ordem = ("nome", "patrimonio")
    viewset = views.FerramentaViewSet

    @property
    def referencias(self) -> dict:
        from catalogo.models import Item

        return {"item": (Item, "codigo_interno"), "local": (LocalEstoque, "nome")}

    colunas = (
        Coluna("nome", "Ferramenta", obrigatoria=True, exemplo="Furadeira de impacto"),
        Coluna("patrimonio", "Patrimônio", exemplo="PAT-0042", aliases=("plaqueta",)),
        Coluna("item", "Código do item", exemplo=""),
        Coluna("local", "Almoxarifado", exemplo="Almoxarifado central"),
        Coluna("estado", "Estado", exemplo="Disponível"),
        Coluna("calibravel", "Calibrável", exemplo="Não"),
        Coluna("proxima_calibracao", "Próxima calibração", tipo=date),
        Coluna("proxima_manutencao", "Próxima manutenção", tipo=date),
        Coluna("valor", "Valor", tipo=Decimal, exemplo="890,00"),
        Coluna("observacao", "Observação"),
    )

    def chave_da_linha(self, dados: dict) -> str:
        return str(dados.get("patrimonio") or "").strip() or self.normalizar_chave(dados.get("nome"))

    def localizar(self, dados: dict, tenant_id):
        patrimonio = str(dados.get("patrimonio") or "").strip()
        if patrimonio:
            return Ferramenta.objects.filter(tenant_id=tenant_id, patrimonio__iexact=patrimonio).first()
        nome = self.normalizar_chave(dados.get("nome"))
        return Ferramenta.objects.filter(tenant_id=tenant_id, nome__iexact=nome, patrimonio="").first() if nome else None

    def serializar_objeto(self, obj) -> dict:
        saida = super().serializar_objeto(obj)
        saida["calibravel"] = "Sim" if obj.calibravel else "Não"
        return saida

    def campos(self, dados: dict, tenant_id) -> dict:
        saida = super().campos(dados, tenant_id)
        saida["estado"] = saida.get("estado") or Ferramenta.Estado.DISPONIVEL
        saida["calibravel"] = sim_ou_nao(dados.get("calibravel"), False)
        saida["patrimonio"] = str(saida.get("patrimonio") or "").strip()
        return saida

    def validar_no_destino(self, dados: dict, tenant_id) -> str:
        return _sim_nao_invalido(self, dados, ("calibravel",)) or super().validar_no_destino(dados, tenant_id)

    def validar_regras(self, objeto, dados, tenant_id) -> str:
        if objeto.estado == Ferramenta.Estado.EMPRESTADA:
            return "“Emprestada” não entra pela planilha — registre o empréstimo pela tela."
        if objeto.valor is not None and objeto.valor < 0:
            return "Valor negativo."
        return ""


# ---------------------------------------------------------------------------
# Movimento e fluxo — só exportam
# ---------------------------------------------------------------------------


@registrar("sil.saldo")
class SaldosValorados(RecursoDeLista):
    rotulo = "Saldos de estoque"
    modulo = "sil"
    permissoes_exigidas = ("sil.saldo.view",)
    modelo = SaldoEstoque
    ordem = ("item__descricao", "local__nome")
    viewset = views.SaldoEstoqueViewSet
    colunas = (
        Coluna("item__codigo_interno", "Código"),
        Coluna("item__descricao", "Item"),
        Coluna("item__unidade", "Unidade"),
        Coluna("local__nome", "Local"),
        Coluna("quantidade", "Quantidade", tipo=Decimal),
        Coluna("reservado", "Reservado", tipo=Decimal),
        Coluna("custo_medio", "Custo médio", tipo=Decimal),
        Coluna("valor", "Valor em estoque", tipo=Decimal),
        Coluna("ponto_reposicao", "Mínimo", tipo=Decimal),
    )

    def serializar_objeto(self, obj) -> dict:
        saida = super().serializar_objeto(obj)
        saida["valor"] = (obj.quantidade * obj.custo_medio).quantize(Decimal("0.01"))
        return saida


@registrar("sil.movimentacao")
class Movimentacoes(RecursoDeLista):
    rotulo = "Movimentações de estoque"
    modulo = "sil"
    permissoes_exigidas = ("sil.movimentacao.view",)
    modelo = MovimentacaoEstoque
    ordem = ("-criado_em", "-mov_id")
    viewset = views.MovimentacaoEstoqueViewSet
    colunas = (
        Coluna("criado_em", "Data", tipo=date),
        Coluna("tipo", "Tipo"),
        Coluna("item__codigo_interno", "Código"),
        Coluna("item__descricao", "Item"),
        Coluna("local__nome", "Local"),
        Coluna("quantidade", "Quantidade", tipo=Decimal),
        Coluna("custo_unitario", "Custo unitário", tipo=Decimal),
        Coluna("obra__nome_obra", "Obra"),
        Coluna("observacao", "Observação"),
    )


@registrar("sil.requisicao")
class Requisicoes(RecursoDeLista):
    rotulo = "Requisições"
    modulo = "sil"
    permissoes_exigidas = ("sil.requisicao.view",)
    modelo = Requisicao
    ordem = ("-criado_em",)
    viewset = views.RequisicaoViewSet
    colunas = (
        Coluna("requisicao_id", "Requisição", tipo=int),
        Coluna("criado_em", "Data", tipo=date),
        Coluna("local__nome", "Local"),
        Coluna("obra__nome_obra", "Obra"),
        Coluna("solicitante", "Solicitante"),
        Coluna("status", "Situação"),
        Coluna("observacao", "Observação"),
    )

    def serializar_objeto(self, obj) -> dict:
        saida = super().serializar_objeto(obj)
        quem = obj.solicitante
        saida["solicitante"] = (quem.get_full_name() or quem.username) if quem is not None else ""
        return saida


@registrar("sil.transferencia")
class Transferencias(RecursoDeLista):
    rotulo = "Transferências"
    modulo = "sil"
    permissoes_exigidas = ("sil.transferencia.view",)
    modelo = Transferencia
    ordem = ("-criado_em",)
    viewset = views.TransferenciaViewSet
    colunas = (
        Coluna("transferencia_id", "Transferência", tipo=int),
        Coluna("criado_em", "Data", tipo=date),
        Coluna("origem__nome", "De"),
        Coluna("destino__nome", "Para"),
        Coluna("status", "Situação"),
        Coluna("observacao", "Observação"),
    )


@registrar("sil.devolucao")
class Devolucoes(RecursoDeLista):
    rotulo = "Devoluções"
    modulo = "sil"
    permissoes_exigidas = ("sil.devolucao.view",)
    modelo = Devolucao
    ordem = ("-criado_em",)
    viewset = views.DevolucaoViewSet
    colunas = (
        Coluna("devolucao_id", "Devolução", tipo=int),
        Coluna("criado_em", "Data", tipo=date),
        Coluna("tipo", "Tipo"),
        Coluna("local__nome", "Local"),
        Coluna("fornecedor__razao_social", "Fornecedor"),
        Coluna("status", "Situação"),
        Coluna("observacao", "Observação"),
    )


@registrar("sil.inventario")
class Inventarios(RecursoDeLista):
    rotulo = "Inventários"
    modulo = "sil"
    permissoes_exigidas = ("sil.inventario.view",)
    modelo = Inventario
    ordem = ("-criado_em",)
    viewset = views.InventarioViewSet
    colunas = (
        Coluna("inventario_id", "Inventário", tipo=int),
        Coluna("criado_em", "Aberto em", tipo=date),
        Coluna("local__nome", "Local"),
        Coluna("tipo", "Tipo"),
        Coluna("status", "Situação"),
        Coluna("fechado_em", "Fechado em", tipo=date),
    )


@registrar("sil.epi")
class EntregasDeEpi(RecursoDeLista):
    rotulo = "Entregas de EPI"
    modulo = "sil"
    permissoes_exigidas = ("sil.epi.view",)
    modelo = EntregaEPI
    ordem = ("-data_entrega", "-entrega_epi_id")
    viewset = views.EntregaEPIViewSet
    colunas = (
        Coluna("data_entrega", "Entrega", tipo=date),
        Coluna("colaborador", "Colaborador"),
        Coluna("item__descricao", "EPI"),
        Coluna("quantidade", "Quantidade", tipo=Decimal),
        Coluna("ca_numero", "CA"),
        Coluna("ca_validade", "Validade do CA", tipo=date),
        Coluna("data_prevista_troca", "Troca prevista", tipo=date),
        Coluna("obra__nome_obra", "Obra"),
        Coluna("status", "Situação"),
    )

    def serializar_objeto(self, obj) -> dict:
        saida = super().serializar_objeto(obj)
        saida["colaborador"] = _pessoa(obj.colaborador, obj.colaborador_nome)
        return saida


@registrar("sil.emprestimo")
class EmprestimosDeFerramenta(RecursoDeLista):
    rotulo = "Empréstimos de ferramenta"
    modulo = "sil"
    permissoes_exigidas = ("sil.ferramenta.view",)
    modelo = EmprestimoFerramenta
    ordem = ("-data_emprestimo", "-emprestimo_id")
    viewset = views.EmprestimoFerramentaViewSet
    colunas = (
        Coluna("ferramenta__nome", "Ferramenta"),
        Coluna("ferramenta__patrimonio", "Patrimônio"),
        Coluna("colaborador", "Com quem"),
        Coluna("obra__nome_obra", "Obra"),
        Coluna("data_emprestimo", "Emprestada em", tipo=date),
        Coluna("data_prevista_devolucao", "Devolução prevista", tipo=date),
        Coluna("data_devolucao", "Devolvida em", tipo=date),
        Coluna("status", "Situação"),
    )

    def serializar_objeto(self, obj) -> dict:
        saida = super().serializar_objeto(obj)
        saida["colaborador"] = _pessoa(obj.colaborador, obj.colaborador_nome)
        return saida


@registrar("sil.curva_abc")
class CurvaAbc(RecursoDeRelatorio):
    rotulo = "Curva ABC"
    modulo = "sil"
    permissoes_exigidas = ("sil.relatorio.view",)
    view = views.CurvaABCView
    colunas = (
        Coluna("classe", "Classe"),
        Coluna("codigo", "Código"),
        Coluna("descricao", "Item"),
        Coluna("unidade", "Unidade"),
        Coluna("quantidade", "Quantidade", tipo=Decimal),
        Coluna("valor", "Valor", tipo=Decimal),
        Coluna("pct", "% do valor", tipo=Decimal),
        Coluna("pct_acumulado", "% acumulado", tipo=Decimal),
    )

    def linhas(self, dados) -> list[dict]:
        numeros = ("quantidade", "valor", "pct", "pct_acumulado")
        return [{**i, **{c: Decimal(i[c]) for c in numeros}} for i in dados.get("itens", [])]
