# backend/entidades/impexp.py
"""As entidades (CNPJs/CPFs do grupo e externas) entram e saem como planilha.

**Fundação** (`entitlement = None`): `cadastro.entidade.*` mora no `base`.

**A chave é o documento**, e no arquivo ele é obrigatório — na tela não, porque
a matriz nasce sem CNPJ na migração. Sem documento a planilha não teria como
dizer se a linha é nova, e reimportar duplicaria a entidade.

**Quem importou fica no lote** (`validar_contexto`): criar entidade do grupo
concede acesso a quem criou, e a aplicação roda numa requisição posterior — a do
"sim". É o mesmo raciocínio do plano congelado no lote da Prancheta.
"""
from __future__ import annotations

import re

from funcoesimpexp.cadastro import RecursoDeCadastro
from funcoesimpexp.formatos.leitura import normalizar
from funcoesimpexp.registro import Coluna, registrar

from . import regras
from .models import Entidade

RECURSO_ENTIDADES = "cadastro.entidade"

_NAO = {"nao", "n", "0", "false", "inativa", "inativo"}
_SIM = {"sim", "s", "1", "true", "x"}


@registrar(RECURSO_ENTIDADES)
class CadastroDeEntidades(RecursoDeCadastro):
    rotulo = "Entidades"
    modulo = "cadastro"
    entitlement = None  # fundação — ver o cabeçalho
    permissoes_exigidas = ("cadastro.entidade.view", "cadastro.entidade.edit")
    modelo = Entidade
    chave = "documento"
    ordem = ("externa", "nome")
    campos_de_busca = ("nome", "nome_fantasia", "documento")
    filtros = {"papel": "papel", "externa": "externa", "ativa": "ativa", "tipo_pessoa": "tipo_pessoa"}
    referencias = {"matriz": (Entidade, "nome")}

    colunas = (
        Coluna("documento", "CPF/CNPJ", obrigatoria=True, exemplo="12.345.678/0001-90",
               aliases=("cnpj", "cpf", "documento")),
        Coluna("nome", "Razão social ou nome", obrigatoria=True, exemplo="Aurora SPE Ltda",
               aliases=("razao social", "nome civil")),
        Coluna("nome_fantasia", "Nome fantasia", exemplo="Aurora"),
        Coluna("tipo_pessoa", "Tipo de pessoa", exemplo="Pessoa jurídica"),
        Coluna("papel", "Papel", exemplo="SPE — Sociedade de Propósito Específico"),
        # Texto e não `bool`: a coluna em branco é "não" para externa e "sim"
        # para ativa — um `bool` leria as duas como falso.
        Coluna("externa", "Externa (fora do grupo)", exemplo="Não", aliases=("externa",)),
        Coluna("matriz", "Matriz (da filial)", exemplo=""),
        Coluna("inscricao_estadual", "Inscrição estadual"),
        Coluna("inscricao_municipal", "Inscrição municipal"),
        Coluna("endereco", "Endereço"),
        Coluna("cidade", "Cidade", exemplo="Salvador"),
        Coluna("estado", "UF", exemplo="BA"),
        Coluna("ativa", "Ativa", exemplo="Sim"),
    )

    def normalizar_chave(self, valor) -> str:
        return re.sub(r"\D", "", str(valor or ""))

    def validar_contexto(self, contexto, user, tenant_id) -> dict:
        return {**dict(contexto or {}), "usuario": getattr(user, "pk", None)}

    def serializar_objeto(self, obj) -> dict:
        saida = super().serializar_objeto(obj)
        saida["externa"] = "Sim" if obj.externa else "Não"
        saida["ativa"] = "Sim" if obj.ativa else "Não"
        return saida

    def campos(self, dados: dict, tenant_id) -> dict:
        saida = super().campos(dados, tenant_id)
        saida["externa"] = normalizar(dados.get("externa")) in _SIM
        saida["ativa"] = normalizar(dados.get("ativa")) not in _NAO
        saida["estado"] = (saida.get("estado") or "").upper()
        documento = saida.get("documento") or ""
        saida["tipo_pessoa"] = saida.get("tipo_pessoa") or (
            Entidade.TipoPessoa.PF if len(documento) == 11 else Entidade.TipoPessoa.PJ
        )
        saida["papel"] = saida.get("papel") or (
            Entidade.Papel.FILIAL if saida.get("matriz") else Entidade.Papel.MATRIZ
        )
        return saida

    def validar_regras(self, objeto, dados, tenant_id) -> str:
        """As regras do `EntidadeSerializer`, para a planilha não ser porta lateral."""
        from nucleo.documentos import cnpj_valido, cpf_valido

        for campo, valor in (("externa", dados.get("externa")), ("ativa", dados.get("ativa"))):
            texto = normalizar(valor)
            if texto and texto not in _SIM | _NAO:
                return f"{self._rotulo(campo)}: “{valor}” — use Sim ou Não."
        documento = objeto.documento
        pf = objeto.tipo_pessoa == Entidade.TipoPessoa.PF
        if pf and not cpf_valido(documento):
            return f"CPF “{dados.get('documento')}” não é válido (pessoa física tem CPF)."
        if not pf and not cnpj_valido(documento):
            return f"CNPJ “{dados.get('documento')}” não é válido (pessoa jurídica tem CNPJ)."
        filial = objeto.papel == Entidade.Papel.FILIAL
        if filial and objeto.matriz is None:
            return "A filial aponta a matriz dela (coluna Matriz)."
        if not filial and objeto.matriz is not None:
            return "Só a filial tem matriz."
        if objeto.matriz is not None and objeto.matriz.externa:
            return "A matriz tem de ser uma entidade do grupo."
        if objeto.externa and objeto.papel in (Entidade.Papel.MATRIZ, Entidade.Papel.FILIAL):
            return "Matriz e filial são do grupo, nunca externas."
        return ""

    def aplicar_linha(self, dados: dict, existente, tenant_id) -> dict:
        antes = list(regras.do_grupo(tenant_id).values_list("pk", flat=True))
        estado = super().aplicar_linha(dados, existente, tenant_id)
        from nucleo.models import Usuario

        criador = Usuario.objects.filter(pk=self.contexto.get("usuario") or 0).first()
        nova = Entidade.objects.get(pk=estado["pk"])
        regras.conceder_ao_criar(nova, antes, criador)
        return estado
