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

from .models import NotaFiscal, NotaFiscalProduto, NotaFiscalServico

RECURSO_NOTA_FISCAL = "erp.nota_fiscal"

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
