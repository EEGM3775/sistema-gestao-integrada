# backend/obras/impexp.py
"""D70 — `documentos_obras/` sai pela porta única.

Contrato, ART/RRT, licença, memorial: documento da obra, com status e aprovador
próprios. Não é PII de titular como o do RH, e continua sendo **arquivo do
cliente saindo do perímetro** — que é a linha que o R12 usa, e não a gravidade
do conteúdo.

**Não confundir com o acervo da Prancheta.** Ali estão os *desenhos*, com
revisão, conversão e visualizador; aqui está a papelada administrativa da obra,
que ninguém converte. Os dois vizinhos justificam a pergunta e a resposta é o
gate: `obra.obra.view` contra `prancheta.documento.view`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from funcoesimpexp.cadastro import RecursoDeCadastro
from funcoesimpexp.entrega import buscar_do_tenant, entregar_campo
from funcoesimpexp.registro import (
    NATUREZA_ARQUIVO,
    ArquivoEntregue,
    Coluna,
    EntregaInvalida,
    Guardado,
    Recurso,
    registrar,
)

from .models import DocumentoObra, Obra

RECURSO_DOCUMENTOS = "obra.documento"
RECURSO_OBRAS = "obra.obra"
ESPECIE_DOCUMENTO = "documento"


@registrar(RECURSO_OBRAS)
class CadastroDeObras(RecursoDeCadastro):
    """As obras. A identidade é **nome + empreendimento**, como no banco.

    Duas obras "Bloco A" em empreendimentos diferentes são duas obras; a chave
    do arquivo é o nome, e o `localizar` soma o empreendimento — senão a segunda
    "Bloco A" travaria como se já existisse. Etapas, equipe e documentos ficam
    fora: são outras tabelas, com tela própria.
    """

    rotulo = "Obras"
    modulo = "obra"
    entitlement = None  # obra é fundação: as permissões `obra.*` são do `base`
    permissoes_exigidas = ("obra.obra.view", "obra.obra.edit")
    modelo = Obra
    chave = "nome_obra"
    quota = "obras"
    ordem = ("nome_obra",)
    campos_de_busca = ("nome_obra", "endereco")
    busca_por_palavra = False  # a tela filtra no navegador, pela frase
    filtros = {
        "status": "status_obra", "status_obra": "status_obra",
        "empreendimento": "empreendimento_id", "empreendimento_id": "empreendimento_id",
    }

    @property
    def referencias(self) -> dict:
        from empreendimentos.models import Empreendimento
        from entidades.models import Entidade

        return {
            "empreendimento": (Empreendimento, "empreendimento"),
            "entidade": (Entidade, "nome"),
        }

    colunas = (
        Coluna("nome_obra", "Obra", obrigatoria=True, exemplo="Torre A",
               aliases=("nome", "nome da obra")),
        Coluna("empreendimento", "Empreendimento", exemplo="Residencial Aurora"),
        Coluna("entidade", "Entidade executora", exemplo="",
               aliases=("entidade", "executora")),
        Coluna("endereco", "Endereço", obrigatoria=True, exemplo="Av. Paralela, 1000"),
        Coluna("status_obra", "Situação", exemplo="Planejamento", aliases=("status",)),
        Coluna("data_inicio_prevista", "Início previsto", tipo=date, exemplo="01/03/2026"),
        Coluna("data_fim_prevista", "Fim previsto", tipo=date, exemplo="30/11/2027"),
        Coluna("data_inicio_real", "Início real", tipo=date),
        Coluna("data_fim_real", "Fim real", tipo=date),
        Coluna("orcamento_previsto", "Orçamento previsto", tipo=Decimal, exemplo="4.800.000,00"),
        Coluna("descricao", "Descrição"),
    )

    def chave_da_linha(self, dados: dict) -> str:
        nome = self.normalizar_chave(dados.get("nome_obra"))
        empreendimento = str(dados.get("empreendimento") or "").strip()
        return f"{nome} ({empreendimento})" if nome and empreendimento else nome

    def localizar(self, dados: dict, tenant_id):
        nome = self.normalizar_chave(dados.get("nome_obra"))
        if not nome:
            return None
        empreendimento = self._referencia("empreendimento", dados.get("empreendimento"), tenant_id)
        return Obra.objects.filter(
            tenant_id=tenant_id, nome_obra__iexact=nome, empreendimento=empreendimento,
        ).first()

    def campos(self, dados: dict, tenant_id) -> dict:
        saida = super().campos(dados, tenant_id)
        saida["status_obra"] = saida.get("status_obra") or "planejamento"
        return saida

    def validar_regras(self, objeto, dados, tenant_id) -> str:
        if objeto.data_fim_prevista and objeto.data_inicio_prevista and (
            objeto.data_fim_prevista < objeto.data_inicio_prevista
        ):
            return "Fim previsto anterior ao início previsto."
        if objeto.orcamento_previsto is not None and objeto.orcamento_previsto < 0:
            return "Orçamento previsto negativo."
        return ""


@registrar(RECURSO_DOCUMENTOS)
class DocumentosDaObra(Recurso):
    """A papelada da obra — contrato, licença, memorial."""

    rotulo = "Documentos da obra"
    modulo = "obra"
    entitlement = None  # obra é fundação: as permissões `obra.*` são do `base`
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("obra.obra.view", "obra.obra.edit")
    permissoes_entrega = ("obra.obra.view",)
    guardados = (Guardado(ESPECIE_DOCUMENTO, DocumentoObra, "arquivo", quando="data_cadastro",
                          titulo="nome_documento", onde="obra__nome_obra"),)

    colunas = (
        Coluna("obra", "Obra"),
        Coluna("tipo_documento", "Tipo de documento"),
        Coluna("nome_documento", "Nome do documento"),
        Coluna("versao", "Versão"),
        Coluna("arquivo", "Arquivo"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        if especie != ESPECIE_DOCUMENTO:
            raise EntregaInvalida(f"Espécie '{especie}' não existe nos documentos da obra.")
        doc = buscar_do_tenant(DocumentoObra, chave, tenant_id)
        return entregar_campo(doc, doc.arquivo, alternativa="documento")
