# backend/clientes/impexp.py
"""D70 — `documentos_clientes/` sai pela porta única.

RG, CPF, CNH, comprovante de residência e certidão de casamento **do titular**:
é a mesma natureza dos documentos do RH, com um agravante de alcance — o cliente
não é empregado da empresa, e o dado dele está aqui por causa de um contrato.

**`entitlement = None` porque cadastro de cliente é fundação.** As permissões
`cadastro.*` moram no módulo `base` (catálogo da IAM), que todo tenant tem: não
há módulo a cobrar, e cobrar um faria a ficha do cliente exigir assinatura que
ninguém vende. É o mesmo caso do `maps.local`, e por isso a herança do padrão
(`entitlement = modulo`) precisa ser desligada à mão.
"""
from __future__ import annotations

import re
from datetime import date

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

from .models import Cliente, DocumentoCliente

RECURSO_CLIENTES = "cadastro.cliente"
RECURSO_DOCUMENTOS = "cadastro.documento_cliente"
ESPECIE_DOCUMENTO = "documento"


@registrar(RECURSO_CLIENTES)
class CarteiraDeClientes(RecursoDeCadastro):
    """O cadastro de clientes: a carteira sai no recorte da tela e entra só nova.

    O CPF/CNPJ é a chave e vai no arquivo — por isso o gate soma
    `cadastro.cliente_doc.view` (§3): sem ele a coluna sairia mascarada, e
    meio-arquivo é pior que arquivo nenhum.
    """

    rotulo = "Clientes"
    modulo = "cadastro"
    entitlement = None  # fundação — ver o cabeçalho
    permissoes_exigidas = (
        "cadastro.cliente.view", "cadastro.cliente.edit", "cadastro.cliente_doc.view",
    )
    modelo = Cliente
    chave = "cpf_cnpj"
    quota = "clientes"
    ordem = ("nome_completo",)
    nao_validar = ("id_cliente_gateway", "cidade_ibge")

    colunas = (
        Coluna("cpf_cnpj", "CPF/CNPJ", obrigatoria=True, exemplo="12345678900",
               aliases=("cpf", "cnpj", "documento")),
        Coluna("nome_completo", "Nome completo", obrigatoria=True, exemplo="Maria da Silva",
               aliases=("nome", "cliente", "razao social")),
        Coluna("email", "E-mail", obrigatoria=True, exemplo="maria@exemplo.com",
               aliases=("email", "e mail")),
        Coluna("telefone", "Telefone", exemplo="(71) 99999-0000", aliases=("celular", "fone")),
        Coluna("data_nascimento", "Data de nascimento", tipo=date, obrigatoria=True,
               exemplo="15/03/1985", aliases=("nascimento",)),
        Coluna("estado_civil", "Estado civil", exemplo="Casado(a)"),
        Coluna("profissao", "Profissão", exemplo="Engenheira"),
        Coluna("cep", "CEP", exemplo="41820-021"),
        Coluna("endereco", "Endereço", exemplo="Av. Tancredo Neves", aliases=("logradouro",)),
        Coluna("numero_endereco", "Número", exemplo="1632", aliases=("numero", "nº")),
        Coluna("complemento_endereco", "Complemento", exemplo="Sala 101"),
        Coluna("bairro", "Bairro", exemplo="Caminho das Árvores"),
        Coluna("cidade", "Cidade", exemplo="Salvador"),
        Coluna("estado", "UF", exemplo="BA", aliases=("estado",)),
    )

    def normalizar_chave(self, valor) -> str:
        # "123.456.789-00" e "12345678900" são o mesmo cliente; o model guarda
        # só dígitos (`cpf_cnpj_validator`).
        return re.sub(r"\D", "", str(valor or ""))

    def campos(self, dados: dict, tenant_id) -> dict:
        saida = super().campos(dados, tenant_id)
        saida["estado"] = (saida.get("estado") or "").upper()
        return saida

    def validar_regras(self, objeto, dados, tenant_id) -> str:
        # O mesmo módulo 11 que a ficha confere — e que o gateway de cobrança
        # recusa depois, quando já é tarde (`nucleo/documentos.py`).
        from nucleo.documentos import cnpj_valido, cpf_valido

        documento = objeto.cpf_cnpj
        if len(documento) == 11 and cpf_valido(documento):
            return ""
        if len(documento) == 14 and cnpj_valido(documento):
            return ""
        return f"CPF/CNPJ “{dados.get('cpf_cnpj')}” não é válido (confira os dígitos)."

    def recortar(self, qs, recorte: dict, request):
        """R7 — os mesmos filtros e a mesma busca da carteira."""
        if not any(recorte.values()):
            return qs
        from moduloerp.models import ContaReceber

        from . import carteira
        from .models import ClienteEmpreendimento

        tenant_id = getattr(getattr(request.user, "tenant", None), "id", None)
        hoje = carteira.hoje_local()
        base = carteira.base_clientes(
            Cliente.objects.filter(tenant_id=tenant_id),
            ContaReceber.objects.filter(tenant_id=tenant_id),
            ClienteEmpreendimento.objects.filter(tenant_id=tenant_id),
            hoje,
        )
        # `pode_documento=True`: quem exporta tem `cliente_doc.view` (está no gate).
        filtrados = carteira.aplicar_filtros(base, "clientes", recorte, hoje, pode_documento=True)
        return qs.filter(pk__in=filtrados.values("pk"))


@registrar(RECURSO_DOCUMENTOS)
class DocumentosDoCliente(Recurso):
    """Os documentos anexados à ficha do cliente."""

    rotulo = "Documentos do cliente"
    modulo = "cadastro"
    entitlement = None  # fundação — ver o cabeçalho
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("cadastro.cliente.view", "cadastro.cliente.edit")
    permissoes_entrega = ("cadastro.cliente.view",)
    guardados = (Guardado(ESPECIE_DOCUMENTO, DocumentoCliente, "arquivo", quando="data_upload",
                          titulo="nome_documento", onde="cliente__nome_completo"),)

    colunas = (
        Coluna("cliente", "Cliente"),
        Coluna("tipo_documento", "Tipo de documento"),
        Coluna("nome_documento", "Nome do documento"),
        Coluna("arquivo", "Arquivo"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        if especie != ESPECIE_DOCUMENTO:
            raise EntregaInvalida(f"Espécie '{especie}' não existe nos documentos do cliente.")
        doc = buscar_do_tenant(DocumentoCliente, chave, tenant_id)
        return entregar_campo(doc, doc.arquivo, alternativa="documento")
