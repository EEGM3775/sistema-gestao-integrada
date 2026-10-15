# backend/moduloerp/impexp.py
"""D70 — `nfe_xmls/` e `notas_fiscais/` saem pela porta única.

**Três modelos e seis campos, num recurso só, porque o gate é um só.** A NFS-e
(serviço) e a NF-e (produto) são as notas que **nós emitimos** pela NFE.io; a
`NotaFiscal` é a nota de **entrada**, que o fornecedor mandou e alguém anexou ao
empreendimento. Os três guardam PDF e/ou XML, e `erp.nf.view` responde pelos
três — foi assim que o catálogo os agrupou desde a Fase 9.

**Por que o XML importa tanto quanto o PDF.** O XML da NF-e carrega CNPJ,
endereço e a lista de itens do que se comprou; é dado fiscal completo, legível
por máquina, e era o mais fácil de varrer em massa a partir de `/media/` — os
caminhos tinham data (`nfe_xmls/2026/08/`) e nada mais, então quem descobrisse
um nome de arquivo enumerava o mês inteiro sem token.

`id` é `erp.nota_fiscal` e `modulo` é `erp_financeiro`: o primeiro segue o
espaço de nomes das permissões (`erp.nf.*`), o segundo é o código do módulo
vendável, que é o que o `entitlement` cobra. São dois vocabulários que já
existiam assim, e forçá-los a coincidir aqui renomearia um dos dois.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction

from funcoesimpexp.cadastro import RecursoDeCadastro, RecursoDeLista
from funcoesimpexp.entrega import buscar_do_tenant, entregar_campo
from funcoesimpexp.importacao import ImportacaoInvalida
from funcoesimpexp.relatorio import RecursoDeRelatorio
from funcoesimpexp.registro import (
    NATUREZA_ARQUIVO,
    ArquivoEntregue,
    Coluna,
    EntregaInvalida,
    Guardado,
    Recurso,
    registrar,
)

from .models import Boleto, ContaPagar, ContaReceber, NotaFiscal, NotaFiscalProduto, NotaFiscalServico

RECURSO_NOTA_FISCAL = "erp.nota_fiscal"
RECURSO_CONTAS_A_PAGAR = "erp.conta_pagar"
RECURSO_CONTAS_A_RECEBER = "erp.conta_receber"
RECURSO_BOLETOS = "erp.boleto"
RECURSO_NFSE_EMITIDAS = "erp.nfse"
RECURSO_SALDOS_INTERCOMPANY = "erp.intercompany"
RECURSO_FINANCEIRO_OBRAS = "erp.financeiro_obras"
RECURSO_DRE_ENTIDADES = "erp.dre_entidades"

#: Espécie → (modelo, campo, nome de fallback). Tabela e não uma cadeia de `if`
#: porque são seis casos idênticos: o que muda entre eles é só de onde o binário
#: vem, e um `if` por caso convidaria a divergirem.
_ARQUIVOS = {
    "nfse_pdf": (NotaFiscalServico, "arquivo_pdf", "nfse.pdf"),
    "nfse_xml": (NotaFiscalServico, "arquivo_xml", "nfse.xml"),
    "nfe_pdf": (NotaFiscalProduto, "arquivo_pdf", "nfe.pdf"),
    "nfe_xml": (NotaFiscalProduto, "arquivo_xml", "nfe.xml"),
    "entrada_pdf": (NotaFiscal, "arquivo_pdf", "nota-entrada.pdf"),
    "entrada_xml": (NotaFiscal, "arquivo_xml", "nota-entrada.xml"),
}


@registrar(RECURSO_NOTA_FISCAL)
class ArquivosDeNotaFiscal(Recurso):
    """PDF e XML das notas emitidas e da nota de entrada."""

    rotulo = "Arquivos de nota fiscal"
    modulo = "erp_financeiro"
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("erp.nf.view", "erp.nf.edit")
    permissoes_entrega = ("erp.nf.view",)
    guardados = tuple(
        Guardado(especie, modelo, campo) for especie, (modelo, campo, _) in _ARQUIVOS.items()
    )

    colunas = (
        Coluna("numero", "Número da nota"),
        Coluna("chave_acesso", "Chave de acesso"),
        Coluna("data_emissao", "Data de emissão"),
        Coluna("arquivo", "Arquivo"),
    )

    def entregar_arquivo(self, especie: str, chave: str, tenant_id) -> ArquivoEntregue:
        alvo = _ARQUIVOS.get(especie)
        if alvo is None:
            raise EntregaInvalida(f"Espécie '{especie}' não existe nas notas fiscais.")
        modelo, campo, alternativa = alvo
        nota = buscar_do_tenant(modelo, chave, tenant_id)
        return entregar_campo(nota, getattr(nota, campo), alternativa=alternativa)


# ---------------------------------------------------------------------------
# A NF-e de entrada **pelo XML** — sem API (pergunta do dono, 10/10/2026)
# ---------------------------------------------------------------------------
#
# "Como adiciono minhas NF-e sem API? O DMS deveria estar mais integrado aqui
# no ERP." O XML que o fornecedor manda é a nota inteira; entra pela porta única
# (R17) — e por isso aparece no DMS (Documentos › Entraram) como todo arquivo
# que entra —, a conferência mostra número, emitente e valor lidos do XML (R1),
# e aplicar grava a `NotaFiscal` com o XML e abre uma conta a pagar por
# duplicata. Desfazer (R6) leva as duas.

from decimal import Decimal  # noqa: E402

from django.utils.dateparse import parse_date  # noqa: E402
from funcoesimpexp.limites import NATUREZA_ARQUIVO as _ARQ, FormatoEntrada, registrar_formato  # noqa: E402
from funcoesimpexp.registro import CAMPO_ARQUIVO, ContextoInvalido  # noqa: E402

from .nfe_xml import XmlNaoEhNfe, ler_nfe, so_digitos  # noqa: E402

RECURSO_NOTA_ENTRADA = "erp.nota_entrada"

#: O XML da NF-e: texto, reconhecido pelo bloco `infNFe` (ou o envelope
#: `nfeProc`) nos primeiros bytes — nunca pela extensão.
registrar_formato(FormatoEntrada(
    codigo="nfe_xml",
    rotulo="XML de NF-e",
    extensoes=(".xml",),
    natureza=_ARQ,
    marcadores_texto=(b"<nfeProc", b"<infNFe", b"<NFe"),
    max_mb=0,
    origem="moduloerp",
))


@registrar(RECURSO_NOTA_ENTRADA)
class NotasDeEntradaPorXml(Recurso):
    """O XML da NF-e do fornecedor vira nota de entrada e contas a pagar."""

    rotulo = "Notas fiscais de entrada (XML)"
    modulo = "erp_financeiro"
    natureza = NATUREZA_ARQUIVO
    permissoes_exigidas = ("erp.nf.view", "erp.nf.edit")
    permissoes_entrega = ("erp.nf.view",)
    formatos_arquivo = ("nfe_xml",)
    contexto_requerido = ("empreendimento",)
    chave = "chave_acesso"
    colunas = (
        Coluna("chave_acesso", "Chave de acesso", obrigatoria=True),
        Coluna("numero", "Número"),
        Coluna("data_emissao", "Emissão"),
        Coluna("emitente_nome", "Emitente"),
        Coluna("emitente_cnpj", "CNPJ"),
        Coluna("fornecedor", "Fornecedor cadastrado"),
        Coluna("valor_total", "Valor"),
        Coluna("parcelas", "Contas a pagar"),
        Coluna("nome", "Arquivo"),
    )

    def validar_contexto(self, contexto, user, tenant_id) -> dict:
        from empreendimentos.models import Empreendimento

        alvo = Empreendimento.objects.filter(
            pk=contexto.get("empreendimento") or 0, tenant_id=tenant_id,
        ).first()
        if alvo is None:
            raise ContextoInvalido("Escolha o empreendimento que recebe as notas.")
        # O tenant viaja no contexto: `dados_do_conteudo` não o recebe, e é ele
        # que escopa a busca do fornecedor pelo CNPJ.
        return {"empreendimento": alvo.pk, "tenant": str(tenant_id)}

    def rotulo_do_contexto(self) -> str:
        from empreendimentos.models import Empreendimento

        alvo = Empreendimento.objects.filter(pk=self.contexto.get("empreendimento") or 0).first()
        return f"Empreendimento: {alvo}" if alvo else ""

    def _fornecedores(self, tenant_id) -> dict[str, tuple[int, str]]:
        """CNPJ (só dígitos) → fornecedor, lido uma vez por operação."""
        if not hasattr(self, "_por_cnpj"):
            from fornecedores.models import Fornecedor

            self._por_cnpj = {
                so_digitos(f.cnpj): (f.pk, f.razao_social)
                for f in Fornecedor.objects.filter(tenant_id=tenant_id).exclude(cnpj__isnull=True)
                if so_digitos(f.cnpj)
            }
        return self._por_cnpj

    def dados_do_conteudo(self, arquivo, conteudo) -> dict:
        try:
            nota = ler_nfe(conteudo.read())
        except XmlNaoEhNfe as erro:
            return {"nome": arquivo.nome, "erro_leitura": str(erro)}
        fornecedor = self._fornecedores(self.contexto.get("tenant")).get(nota["emitente_cnpj"])
        return {
            "nome": arquivo.nome,
            "chave_acesso": nota["chave_acesso"],
            "numero": nota["numero"],
            "data_emissao": nota["data_emissao"].isoformat() if nota["data_emissao"] else "",
            "emitente_nome": nota["emitente_nome"],
            "emitente_cnpj": nota["emitente_cnpj"],
            "fornecedor": fornecedor[1] if fornecedor else "",
            "fornecedor_id": fornecedor[0] if fornecedor else None,
            "valor_total": str(nota["valor_total"]) if nota["valor_total"] is not None else "",
            "parcelas": len(nota["duplicatas"]),
            "duplicatas": [
                {"numero": d["numero"], "vencimento": d["vencimento"].isoformat(), "valor": str(d["valor"])}
                for d in nota["duplicatas"]
            ],
        }

    def validar_linha(self, dados: dict) -> str:
        if dados.get("erro_leitura"):
            return dados["erro_leitura"]
        if len(dados.get("chave_acesso") or "") != 44:
            return "A NF-e não traz a chave de acesso de 44 dígitos."
        if not dados.get("data_emissao") or not dados.get("valor_total"):
            return "A NF-e não traz data de emissão ou valor total."
        if not dados.get("fornecedor_id"):
            return (f"O emitente {dados.get('emitente_nome') or ''} (CNPJ {dados.get('emitente_cnpj')}) "
                    "não está cadastrado em Fornecedores. Cadastre-o e envie de novo.")
        return ""

    def localizar(self, dados: dict, tenant_id):
        return NotaFiscal.objects.filter(
            tenant_id=tenant_id, chave_acesso=dados.get("chave_acesso") or "-",
        ).first()

    def aplicar_linha(self, dados: dict, existente, tenant_id) -> dict | None:
        if existente is not None:
            return None
        from .models import ContaPagar

        nota = NotaFiscal(
            tenant_id=tenant_id,
            empreendimento_id=self.contexto["empreendimento"],
            fornecedor_id=dados["fornecedor_id"],
            numero_nota=(dados.get("numero") or dados["chave_acesso"][25:34])[:50],
            chave_acesso=dados["chave_acesso"],
            data_emissao=parse_date(dados["data_emissao"]),
            valor_total=Decimal(dados["valor_total"]),
        )
        binario = dados[CAMPO_ARQUIVO]
        binario.open("rb")
        nota.arquivo_xml.save(dados.get("nome") or f"nfe-{dados['chave_acesso']}.xml", binario, save=False)
        nota.save()

        contas = []
        for dup in dados.get("duplicatas") or []:
            conta = ContaPagar.objects.create(
                tenant_id=tenant_id, fornecedor_id=dados["fornecedor_id"],
                empreendimento_id=self.contexto["empreendimento"], nota_fiscal=nota,
                descricao=f"NF-e {nota.numero_nota} — {dados.get('emitente_nome') or ''} "
                          f"(parcela {dup.get('numero') or len(contas) + 1})".strip(),
                valor=Decimal(dup["valor"]), data_emissao=nota.data_emissao,
                data_vencimento=parse_date(dup["vencimento"]),
            )
            contas.append(conta.pk)
        return {"acao": "criou", "nota": nota.pk, "contas": contas}

    def desfazer_linha(self, estado_anterior: dict, tenant_id) -> None:
        from .models import ContaPagar

        ContaPagar.todos.filter(
            tenant_id=tenant_id, pk__in=estado_anterior.get("contas") or [],
            valor_pago=0,
        ).delete()
        nota = NotaFiscal.todos.filter(tenant_id=tenant_id, pk=estado_anterior.get("nota") or 0).first()
        if nota is not None:
            arquivo = nota.arquivo_xml
            nota.delete()
            if arquivo:
                arquivo.delete(save=False)


# ---------------------------------------------------------------------------
# As listas do financeiro (15/10/2026)
# ---------------------------------------------------------------------------
#
# **Títulos importam; o resto só exporta** (decisão do dono, 15/10/2026). A conta
# a pagar e a receber é a carga clássica de quem chega de outro sistema — uma
# linha é o título inteiro, e ele nasce **em aberto**: baixa, situação e saldo
# só saem (a baixa tem caminho único, `dar_baixa`). Boleto e NFS-e são emissão
# em terceiro (Asaas, NFE.io); DRE, saldo intercompany e financeiro por obra são
# relatório calculado.
#
# **O arquivo vê o que a tela vê**: a saída roda o ViewSet da própria tela
# (`viewset`), com o escopo por entidade e a busca do listão. A entrada confere o
# mesmo alcance — calculado no "importar" e congelado no lote, como o plano na
# Prancheta: o "sim" vem numa requisição posterior.


def _decimal(valor):
    return Decimal(str(valor)) if valor not in (None, "") else None


class _TitulosDoErp(RecursoDeCadastro):
    modulo = "erp_financeiro"
    chave = "descricao"
    ordem = ("data_vencimento", "pk")
    #: "fornecedor" ou "cliente".
    campo_pessoa: str = ""
    #: Campo da última baixa ("data_pagamento" / "data_recebimento").
    campo_baixa: str = ""
    nao_validar = ("entidade",)

    @property
    def so_saida(self) -> tuple[str, ...]:
        return ("saldo_aberto", "status", self.campo_baixa)

    @property
    def referencias(self) -> dict:
        from empreendimentos.models import Empreendimento
        from entidades.models import Entidade

        return {
            self.campo_pessoa: self._modelo_da_pessoa(),
            "empreendimento": (Empreendimento, "empreendimento"),
            "entidade": (Entidade, "nome"),
        }

    def _modelo_da_pessoa(self):
        raise NotImplementedError

    def _colunas(self, pessoa: Coluna) -> tuple[Coluna, ...]:
        return (
            pessoa,
            Coluna("descricao", "Descrição", obrigatoria=True, exemplo="Concreto usinado — 1ª medição"),
            Coluna("valor", "Valor", tipo=Decimal, obrigatoria=True, exemplo="12.500,00"),
            Coluna("data_emissao", "Emissão", tipo=date, exemplo="01/11/2026"),
            Coluna("data_vencimento", "Vencimento", tipo=date, obrigatoria=True, exemplo="30/11/2026"),
            Coluna("empreendimento", "Empreendimento", exemplo="Residencial Aurora"),
            Coluna("obra", "Obra", exemplo="Torre A"),
            Coluna("entidade", "Entidade (CNPJ do grupo)", exemplo="",
                   aliases=("entidade", "empresa do grupo")),
            Coluna("saldo_aberto", "Em aberto (só sai)", tipo=Decimal),
            Coluna(self.campo_baixa, "Última baixa (só sai)", tipo=date),
            Coluna("status", "Situação (só sai)"),
        )

    # --- identidade: pessoa + descrição + vencimento + valor -------------------

    def chave_da_linha(self, dados: dict) -> str:
        return " · ".join(str(dados.get(c) or "").strip() for c in (
            self.campo_pessoa, "descricao", "data_vencimento", "valor",
        ))

    def localizar(self, dados: dict, tenant_id):
        pessoa = self._referencia(self.campo_pessoa, dados.get(self.campo_pessoa), tenant_id)
        descricao = str(dados.get("descricao") or "").strip()
        if pessoa is None or not descricao or not dados.get("data_vencimento") or dados.get("valor") is None:
            return None
        return self.modelo.objects.filter(
            tenant_id=tenant_id, **{self.campo_pessoa: pessoa}, descricao__iexact=descricao,
            data_vencimento=dados.get("data_vencimento"), valor=dados.get("valor"),
        ).first()

    # --- contexto: quem importa e o que alcança ---------------------------------

    def validar_contexto(self, contexto, user, tenant_id) -> dict:
        from entidades.escopo import alcance, empreendimentos_concedidos

        entidades = alcance(user)
        return {
            **dict(contexto or {}),
            "usuario": getattr(user, "pk", None),
            "alcance": None if entidades is None else sorted(entidades),
            "empreendimentos": sorted(empreendimentos_concedidos(user)),
        }

    # --- entrada ----------------------------------------------------------------

    def campos(self, dados: dict, tenant_id) -> dict:
        from obras.models import Obra

        saida = super().campos(dados, tenant_id)
        # A obra é "Torre A" **dentro** do empreendimento da linha — duas Torre A
        # em empreendimentos diferentes são duas obras.
        nome = str(dados.get("obra") or "").strip()
        obras = Obra.objects.filter(tenant_id=tenant_id, nome_obra__iexact=nome) if nome else Obra.objects.none()
        if saida.get("empreendimento") is not None:
            obras = obras.filter(empreendimento=saida["empreendimento"])
        achadas = list(obras[:2])
        saida["obra"] = achadas[0] if len(achadas) == 1 else None
        return saida

    def validar_no_destino(self, dados: dict, tenant_id) -> str:
        nome = str(dados.get("obra") or "").strip()
        if nome and self.campos(dados, tenant_id).get("obra") is None:
            return f"Obra “{nome}” não existe nesse empreendimento, ou há mais de uma com esse nome."
        return super().validar_no_destino(dados, tenant_id)

    def validar_regras(self, objeto, dados, tenant_id) -> str:
        from entidades.regras import preencher

        if objeto.valor is not None and objeto.valor <= 0:
            return "Valor tem de ser maior que zero."
        if objeto.data_emissao and objeto.data_vencimento and objeto.data_vencimento < objeto.data_emissao:
            return "Vencimento anterior à emissão."
        if objeto.entidade_id and objeto.entidade.externa:
            return f"{objeto.entidade} é uma entidade externa: ela não tem financeiro neste sistema."
        preencher(objeto)
        alcance = self.contexto.get("alcance")
        if alcance is not None and objeto.entidade_id not in alcance and (
            objeto.empreendimento_id not in (self.contexto.get("empreendimentos") or [])
        ):
            return "Você não tem acesso ao financeiro da entidade deste título."
        return ""

    def aplicar_linha(self, dados: dict, existente, tenant_id) -> dict:
        """Como o `_criar_com_par` da tela: grava sem o gatilho e sincroniza o par
        intercompany uma vez (a despesa do empreendimento com sócio vira título
        na outra entidade — e o `sincronizar` avisa quem cuida dela)."""
        from .intercompany import sincronizar

        ausente = self._referencia_ausente(dados, tenant_id)
        if ausente:
            raise ImportacaoInvalida(f"{ausente} Nada foi importado.")
        conta = self.modelo(tenant_id=tenant_id, **self.campos(dados, tenant_id))
        conta._sem_intercompany = True
        with transaction.atomic():
            conta.save()
            sincronizar(conta)
        return {"acao": "criou", "pk": conta.pk}

    def desfazer_linha(self, estado_anterior: dict, tenant_id) -> None:
        conta = self.modelo.objects.filter(pk=estado_anterior.get("pk"), tenant_id=tenant_id).first()
        if conta is None:
            return
        if conta.valor_pago > 0:
            raise ImportacaoInvalida(
                f"“{conta.descricao}” já tem baixa — o lote não pode mais ser desfeito. "
                "Estorne a baixa ou exclua pela tela."
            )
        with transaction.atomic():
            for par in conta.pares_intercompany.all():
                espelho = par.titulo_receber if self.modelo is ContaPagar else par.titulo_pagar
                if espelho is not None and espelho.valor_pago > 0:
                    raise ImportacaoInvalida(
                        f"O título de {par.contraparte} gerado por “{conta.descricao}” já tem baixa — "
                        "o lote não pode mais ser desfeito."
                    )
                par.delete()
                if espelho is not None:
                    espelho.delete()
            conta.delete()


@registrar(RECURSO_CONTAS_A_PAGAR)
class ContasAPagar(_TitulosDoErp):
    rotulo = "Contas a pagar"
    permissoes_exigidas = ("erp.conta_pagar.view", "erp.conta_pagar.edit")
    modelo = ContaPagar
    campo_pessoa = "fornecedor"
    campo_baixa = "data_pagamento"

    @property
    def viewset(self):
        from .views import ContaPagarViewSet

        return ContaPagarViewSet

    def _modelo_da_pessoa(self):
        from fornecedores.models import Fornecedor

        return (Fornecedor, "razao_social")

    @property
    def colunas(self):
        return self._colunas(Coluna(
            "fornecedor", "Fornecedor", obrigatoria=True, exemplo="Concreto Forte Ltda",
            aliases=("razao social", "credor"),
        ))


@registrar(RECURSO_CONTAS_A_RECEBER)
class ContasAReceber(_TitulosDoErp):
    """A receber avulso. A parcela do contrato de venda nasce do contrato, com
    unidade e correção — não pela planilha."""

    rotulo = "Contas a receber"
    permissoes_exigidas = ("erp.conta_receber.view", "erp.conta_receber.edit")
    modelo = ContaReceber
    campo_pessoa = "cliente"
    campo_baixa = "data_recebimento"

    @property
    def viewset(self):
        from .views import ContaReceberViewSet

        return ContaReceberViewSet

    def _modelo_da_pessoa(self):
        from clientes.models import Cliente

        return (Cliente, "nome_completo")

    @property
    def colunas(self):
        return self._colunas(Coluna(
            "cliente", "Cliente", obrigatoria=True, exemplo="Maria da Silva",
            aliases=("nome do cliente", "pagador", "devedor"),
        ))


@registrar(RECURSO_BOLETOS)
class BoletosEmitidos(RecursoDeLista):
    rotulo = "Boletos"
    modulo = "erp_financeiro"
    permissoes_exigidas = ("erp.cobranca.view",)
    modelo = Boleto
    ordem = ("-data_vencimento", "pk")

    @property
    def viewset(self):
        from .views import BoletoViewSet

        return BoletoViewSet

    colunas = (
        Coluna("pessoa", "Pagador"),
        Coluna("conta", "Título"),
        Coluna("empreendimento", "Empreendimento"),
        Coluna("valor", "Valor", tipo=Decimal),
        Coluna("data_vencimento", "Vencimento", tipo=date),
        Coluna("status", "Situação"),
        Coluna("data_pagamento", "Pago em", tipo=date),
        Coluna("linha_digitavel", "Linha digitável"),
    )

    def serializar_objeto(self, obj) -> dict:
        conta = obj.conta_receber or obj.conta_pagar
        emp = getattr(conta, "empreendimento", None)
        return {
            "pessoa": conta.nome_da_pessoa if conta else "",
            "conta": conta.descricao if conta else "",
            "empreendimento": emp.empreendimento if emp else "",
            "valor": obj.valor,
            "data_vencimento": obj.data_vencimento,
            "status": obj.get_status_display(),
            "data_pagamento": obj.data_pagamento,
            "linha_digitavel": obj.linha_digitavel or "",
        }


@registrar(RECURSO_NFSE_EMITIDAS)
class NfseEmitidas(RecursoDeLista):
    rotulo = "NFS-e emitidas"
    modulo = "erp_financeiro"
    permissoes_exigidas = ("erp.nf.view",)
    modelo = NotaFiscalServico
    ordem = ("-criado_em",)

    @property
    def viewset(self):
        from .views import NotaFiscalServicoViewSet

        return NotaFiscalServicoViewSet

    colunas = (
        Coluna("numero", "Número"),
        Coluna("data_emissao", "Emissão", tipo=date),
        Coluna("tomador", "Tomador"),
        Coluna("description", "Discriminação"),
        Coluna("services_amount", "Valor", tipo=Decimal),
        Coluna("status", "Situação"),
        Coluna("entidade", "Entidade emitente"),
        Coluna("chave_acesso", "Chave de acesso"),
    )

    def serializar_objeto(self, obj) -> dict:
        tomador = obj.borrower_data if isinstance(obj.borrower_data, dict) else {}
        return {
            "numero": obj.numero or "",
            "data_emissao": obj.data_emissao,
            "tomador": tomador.get("name") or tomador.get("nome") or "",
            "description": obj.description,
            "services_amount": obj.services_amount,
            "status": obj.get_status_display(),
            "entidade": str(obj.entidade) if obj.entidade_id else "",
            "chave_acesso": obj.chave_acesso or "",
        }


@registrar(RECURSO_SALDOS_INTERCOMPANY)
class SaldosIntercompany(RecursoDeRelatorio):
    rotulo = "Saldos intercompany"
    modulo = "erp_financeiro"
    permissoes_exigidas = ("erp.conta_receber.view",)

    @property
    def view(self):
        from .views import IntercompanyView

        return IntercompanyView

    colunas = (
        Coluna("credora_nome", "Credora"),
        Coluna("devedora_nome", "Devedora"),
        Coluna("saldo", "Saldo em aberto", tipo=Decimal),
    )

    def linhas(self, dados) -> list[dict]:
        return [{**s, "saldo": _decimal(s["saldo"])} for s in dados.get("saldos", [])]


@registrar(RECURSO_FINANCEIRO_OBRAS)
class FinanceiroPorObra(RecursoDeRelatorio):
    rotulo = "Financeiro por obra"
    modulo = "erp_financeiro"
    permissoes_exigidas = ("erp.relatorio.view",)

    @property
    def view(self):
        from .views import FinanceiroObrasView

        return FinanceiroObrasView

    colunas = (
        Coluna("obra_nome", "Obra"),
        Coluna("receita", "Receita", tipo=Decimal),
        Coluna("recebido", "Recebido", tipo=Decimal),
        Coluna("custo", "Custo", tipo=Decimal),
        Coluna("pago", "Pago", tipo=Decimal),
        Coluna("resultado", "Resultado", tipo=Decimal),
    )

    def linhas(self, dados) -> list[dict]:
        campos = ("receita", "recebido", "custo", "pago", "resultado")
        return [{**o, **{c: _decimal(o.get(c)) for c in campos}} for o in dados.get("obras", [])]


@registrar(RECURSO_DRE_ENTIDADES)
class DrePorEntidade(RecursoDeRelatorio):
    """Uma linha por entidade e regime (competência e caixa), mais o consolidado."""

    rotulo = "DRE por entidade"
    modulo = "erp_financeiro"
    permissoes_exigidas = ("erp.relatorio.view",)

    @property
    def view(self):
        from .views import DreEntidadesView

        return DreEntidadesView

    colunas = (
        Coluna("entidade", "Entidade"),
        Coluna("regime", "Regime"),
        Coluna("receita", "Receita", tipo=Decimal),
        Coluna("despesa", "Despesa", tipo=Decimal),
        Coluna("resultado", "Resultado próprio", tipo=Decimal),
        Coluna("resultado_com_cotas", "Resultado com as cotas", tipo=Decimal),
    )

    def linhas(self, dados) -> list[dict]:
        saida = []
        regimes = (("competencia", "Competência"), ("caixa", "Caixa"))
        for e in dados.get("entidades", []):
            for chave, rotulo in regimes:
                lado = e.get(chave) or {}
                saida.append({
                    "entidade": e.get("nome", ""), "regime": rotulo,
                    "receita": _decimal(lado.get("receita")), "despesa": _decimal(lado.get("despesa")),
                    "resultado": _decimal(lado.get("resultado")),
                    "resultado_com_cotas": _decimal((e.get("resultado_com_cotas") or {}).get(chave)),
                })
        consolidado = dados.get("consolidado") or {}
        for chave, rotulo in regimes:
            lado = consolidado.get(chave) or {}
            saida.append({
                "entidade": "Consolidado", "regime": rotulo,
                "receita": _decimal(lado.get("receita")), "despesa": _decimal(lado.get("despesa")),
                "resultado": _decimal(lado.get("resultado")),
                "resultado_com_cotas": _decimal((consolidado.get("resultado") or {}).get(chave)),
            })
        return saida
