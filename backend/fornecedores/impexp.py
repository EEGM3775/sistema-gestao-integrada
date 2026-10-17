# backend/fornecedores/impexp.py
"""O cadastro de fornecedores entra e sai pela porta única (14/10/2026).

**`entitlement = None` porque é fundação**, como o cliente: `cadastro.*` mora no
módulo `base`, que todo tenant tem.

A chave é a **razão social**, e não o CNPJ: o CNPJ é opcional no cadastro (há
fornecedor pessoa física e prestador informal), e chave que pode faltar não
identifica ninguém. A razão social já é única por tenant no banco.
"""
from __future__ import annotations

import re

from funcoesimpexp.cadastro import RecursoDeCadastro
from funcoesimpexp.registro import Coluna, registrar

from .models import Fornecedor

RECURSO_FORNECEDORES = "cadastro.fornecedor"


@registrar(RECURSO_FORNECEDORES)
class CadastroDeFornecedores(RecursoDeCadastro):
    rotulo = "Fornecedores"
    modulo = "cadastro"
    entitlement = None  # fundação — ver o cabeçalho
    # Nenhuma coluna é mascarada (os dados bancários, que são, não vão no arquivo).
    permissoes_exigidas = ("cadastro.fornecedor.view", "cadastro.fornecedor.edit")
    modelo = Fornecedor
    chave = "razao_social"
    quota = "fornecedores"
    ordem = ("razao_social",)
    campos_de_busca = ("razao_social", "cnpj", "email", "contato", "telefone")
    filtros = {"cnpj": "cnpj"}

    colunas = (
        Coluna("razao_social", "Razão social", obrigatoria=True, exemplo="Concreto Forte Ltda",
               aliases=("fornecedor", "nome", "empresa")),
        Coluna("cnpj", "CNPJ", exemplo="12.345.678/0001-90", aliases=("cpf/cnpj", "documento")),
        Coluna("email", "E-mail", obrigatoria=False, exemplo="compras@concretoforte.com.br",
               aliases=("email", "e mail")),
        Coluna("telefone", "Telefone", exemplo="(71) 3333-0000", aliases=("fone",)),
        Coluna("contato", "Contato", exemplo="João (comercial)"),
    )

    def campos(self, dados: dict, tenant_id) -> dict:
        # A ficha grava o documento só com dígitos (CPF ou CNPJ), ou nulo.
        saida = super().campos(dados, tenant_id)
        documento = re.sub(r"\D", "", str(saida.get("cnpj") or ""))
        saida["cnpj"] = documento or None
        return saida

    def validar_regras(self, objeto, dados, tenant_id) -> str:
        from nucleo.documentos import cnpj_valido, cpf_valido

        documento = objeto.cnpj
        if not documento:
            return ""
        if (len(documento) == 11 and cpf_valido(documento)) or (
            len(documento) == 14 and cnpj_valido(documento)
        ):
            return ""
        return f"CNPJ/CPF “{dados.get('cnpj')}” não é válido (confira os dígitos)."
