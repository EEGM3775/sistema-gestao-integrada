# backend/moduloscm/notas.py
"""A NF-e da compra: lançar, anexar o documento e conferir (D284).

*Dono, 11/10/2026:* "NF-e deveria ter onde adicionar nota e onde adicionar chave
de acesso" e "caso tenha só o número vai para o ERP com o número e fica
aguardando o documento, e quando coloca o documento compara se o número está
certo".

A nota passa por três estados:

- **aguardando documento** — só o número (ou número e chave digitados);
- **conferida** — chegou o documento e nada diverge;
- **divergente** — algo não bate, e a frase de cada divergência vai para a tela
  e para a anotação do título no ERP.

O que se confere, e de onde vem cada lado:

- **A chave é testada como CPF e CNPJ, mas não é recusada** (dono, 11/10/2026:
  "não é para recusar, é apenas para verificar e avisar, pois pode uma nota
  sair em nome de outro fornecedor"). Dígito verificador, mês, modelo e o CNPJ
  embutido (`validar_chave`) viram divergência com a frase do porquê; a nota
  fica registrada e o financeiro decide.
- **A chave de acesso diz quase tudo sozinha.** Os 44 dígitos carregam o CNPJ
  do emitente, o modelo, a série e o número da nota, e terminam num dígito
  verificador (módulo 11). Com a chave digitada já se descobre o número trocado
  e o fornecedor errado, antes de o documento chegar — e o DANFE em PDF, que
  não é lido por máquina, é conferido pela chave que vem impressa nele.
- **O XML diz o resto**: valor, emissão e as duplicatas (vencimentos), pelo
  mesmo leitor que o ERP usa na entrada de notas (`moduloerp.nfe_xml`).

Divergência não bloqueia o lançamento: a nota errada fica registrada e marcada,
que é melhor que a nota recusada e esquecida.
"""
from __future__ import annotations

import re
from decimal import Decimal

from django.utils import timezone

from payment.planos import SCM_NFE_ARQUIVO_TETO_MB

from . import financeiro
from .models import EventoPedido, NotaFiscalCompra, PedidoCompra

MODELOS_ACEITOS = {"55": "NF-e", "65": "NFC-e"}


class NotaInvalida(ValueError):
    """O que veio não dá para lançar (sem número, arquivo errado…)."""


def so_digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def dv_da_chave(chave43: str) -> int:
    """Dígito verificador da chave (módulo 11, pesos 2 a 9 da direita)."""
    soma, peso = 0, 2
    for d in reversed(chave43):
        soma += int(d) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def partes_da_chave(chave: str) -> dict:
    """O que os 44 dígitos dizem (posições do Manual de Orientação da NF-e)."""
    return {
        "uf": chave[0:2], "aamm": chave[2:6], "cnpj": chave[6:20], "modelo": chave[20:22],
        "serie": chave[22:25], "numero": chave[25:34], "dv": chave[43],
    }


def validar_chave(chave: str) -> str | None:
    """`None` se a chave é válida; senão, a frase do porquê.

    Validada como CPF e CNPJ são no sistema (dono, 11/10/2026): o dígito
    verificador e o que ela carrega dentro — mês de emissão, modelo e o CNPJ
    (ou CPF, no produtor rural) do emitente, que tem os seus próprios dígitos.
    Espelha `validateChaveNFe` do frontend (`utils/masks.ts`).
    """
    from nucleo.documentos import cnpj_valido, cpf_valido

    chave = so_digitos(chave)
    if len(chave) != 44:
        return f"Chave incompleta — {len(chave)} de 44 dígitos."
    if dv_da_chave(chave[:43]) != int(chave[43]):
        return "Chave de acesso inválida — confira a digitação."
    if not 1 <= int(chave[4:6]) <= 12:
        return "Chave de acesso inválida — o mês de emissão não existe."
    p = partes_da_chave(chave)
    if p["modelo"] not in MODELOS_ACEITOS:
        return f"A chave é de um documento modelo {p['modelo']}, não de NF-e."
    emitente = p["cnpj"]
    if not cnpj_valido(emitente) and not (emitente.startswith("000") and cpf_valido(emitente[3:])):
        return "Chave de acesso inválida — o CNPJ do emitente dentro dela não confere."
    return None


def _mesmo_numero(a, b) -> bool:
    da, db = so_digitos(a).lstrip("0"), so_digitos(b).lstrip("0")
    return bool(da) and da == db


def conferir(nota: NotaFiscalCompra, pedido: PedidoCompra, *, xml: dict | None = None) -> list[str]:
    """As divergências desta nota contra o que foi digitado, o fornecedor e o pedido."""
    divergencias = []
    cnpj_fornecedor = so_digitos(getattr(pedido.fornecedor, "cnpj", ""))
    chave = nota.chave_acesso

    if chave:
        invalida = validar_chave(chave)
        if invalida:
            divergencias.append(invalida)
        if len(chave) == 44 and not (invalida or "").startswith("Chave de acesso inválida — confira"):
            p = partes_da_chave(chave)
            if not _mesmo_numero(p["numero"], nota.numero):
                divergencias.append(f"O número informado ({nota.numero}) não é o da chave ({int(p['numero'])}).")
            if nota.serie and so_digitos(nota.serie).lstrip("0") != p["serie"].lstrip("0"):
                divergencias.append(f"A série informada ({nota.serie}) não é a da chave ({int(p['serie'])}).")
            if cnpj_fornecedor and p["cnpj"] != cnpj_fornecedor.zfill(14):
                divergencias.append(
                    f"A nota foi emitida pelo CNPJ {p['cnpj']}, e o fornecedor do pedido é {cnpj_fornecedor} — "
                    "confira se ele faturou por outra empresa."
                )

    if xml is not None:
        if xml.get("chave_acesso") and chave and xml["chave_acesso"] != chave:
            divergencias.append("A chave digitada não é a do XML anexado.")
        if xml.get("numero") and not _mesmo_numero(xml["numero"], nota.numero):
            divergencias.append(f"O número informado ({nota.numero}) não é o do XML ({xml['numero']}).")
        emitente = so_digitos(xml.get("emitente_cnpj"))
        if cnpj_fornecedor and emitente and emitente.zfill(14) != cnpj_fornecedor.zfill(14):
            divergencias.append(
                f"O XML é de {xml.get('emitente_nome') or emitente} (CNPJ {emitente}), não do fornecedor do pedido."
            )

    if nota.valor_total is not None and pedido.valor_total is not None:
        outras = (pedido.notas_fiscais.exclude(pk=nota.pk).exclude(valor_total__isnull=True)
                  .values_list("valor_total", flat=True)) if nota.pk else []
        soma = nota.valor_total + sum(outras, Decimal("0"))
        if soma > pedido.valor_total:
            divergencias.append(f"As notas somam R$ {soma}, acima do pedido (R$ {pedido.valor_total}).")
        elif not outras and pedido.status == PedidoCompra.Status.RECEBIDO_TOTAL and soma != pedido.valor_total:
            divergencias.append(f"A nota é de R$ {nota.valor_total} e o pedido, de R$ {pedido.valor_total}.")
    return divergencias


def _ler_xml(arquivo) -> dict:
    try:
        from moduloerp.nfe_xml import XmlNaoEhNfe, ler_nfe
    except ImportError as exc:  # pragma: no cover - instalação sem o financeiro
        raise NotaInvalida("Leitura de XML indisponível nesta instalação.") from exc
    arquivo.seek(0)
    try:
        dados = ler_nfe(arquivo.read())
    except XmlNaoEhNfe as erro:
        raise NotaInvalida(str(erro)) from erro
    arquivo.seek(0)
    return dados


def _validar_arquivo(arquivo, *, extensao: str, assinatura: bytes | None = None) -> None:
    if arquivo is None:
        return
    if (getattr(arquivo, "size", 0) or 0) > SCM_NFE_ARQUIVO_TETO_MB * 1024 * 1024:
        raise NotaInvalida(f"O arquivo passa de {SCM_NFE_ARQUIVO_TETO_MB} MB.")
    if not (arquivo.name or "").lower().endswith(extensao):
        raise NotaInvalida(f"Envie um arquivo {extensao}.")
    if assinatura is not None:
        arquivo.seek(0)
        inicio = arquivo.read(len(assinatura))
        arquivo.seek(0)
        if inicio != assinatura:
            raise NotaInvalida("O arquivo não é um PDF.")


def _aplicar_documento(nota: NotaFiscalCompra, *, xml_arquivo=None, pdf_arquivo=None) -> dict | None:
    _validar_arquivo(xml_arquivo, extensao=".xml")
    _validar_arquivo(pdf_arquivo, extensao=".pdf", assinatura=b"%PDF")
    dados = None
    if xml_arquivo is not None:
        dados = _ler_xml(xml_arquivo)
        if not nota.numero:
            nota.numero = (dados.get("numero") or "")[:20]
        if not nota.serie:
            nota.serie = (dados.get("serie") or "")[:3]
        if not nota.chave_acesso and dados.get("chave_acesso"):
            nota.chave_acesso = dados["chave_acesso"]
        nota.data_emissao = dados.get("data_emissao") or nota.data_emissao
        nota.valor_total = dados.get("valor_total") if dados.get("valor_total") is not None else nota.valor_total
        nota.emitente_cnpj = so_digitos(dados.get("emitente_cnpj"))[:14]
        nota.emitente_nome = (dados.get("emitente_nome") or "")[:255]
        nota.duplicatas = [
            {"numero": d["numero"], "vencimento": d["vencimento"].isoformat(), "valor": str(d["valor"])}
            for d in dados.get("duplicatas") or []
        ]
        nota.arquivo_xml.save(xml_arquivo.name.rsplit("/", 1)[-1][:80], xml_arquivo, save=False)
    if pdf_arquivo is not None:
        nota.arquivo_pdf.save(pdf_arquivo.name.rsplit("/", 1)[-1][:80], pdf_arquivo, save=False)
    return dados


def _tem_documento(nota: NotaFiscalCompra) -> bool:
    """XML conferido, ou o DANFE com a chave (o PDF não é lido por máquina)."""
    return bool(nota.arquivo_xml) or (bool(nota.arquivo_pdf) and len(nota.chave_acesso) == 44)


def _concluir(nota: NotaFiscalCompra, pedido: PedidoCompra, dados, *, autor, verbo: str) -> NotaFiscalCompra:
    nota.divergencias = conferir(nota, pedido, xml=dados)
    if nota.divergencias:
        nota.situacao = NotaFiscalCompra.Situacao.DIVERGENTE
    elif _tem_documento(nota):
        nota.situacao = NotaFiscalCompra.Situacao.CONFERIDA
        nota.conferida_em = timezone.now()
    else:
        nota.situacao = NotaFiscalCompra.Situacao.AGUARDANDO_DOCUMENTO
    nota.save()

    if nota.recebimento_id and not nota.recebimento.nota_fiscal_ref:
        nota.recebimento.nota_fiscal_ref = nota.numero
        nota.recebimento.save(update_fields=["nota_fiscal_ref"])

    financeiro.sincronizar_nfe(pedido)
    if nota.situacao == NotaFiscalCompra.Situacao.DIVERGENTE:
        texto = f"NF-e {nota.numero} {verbo} com divergência: " + " ".join(nota.divergencias)
        financeiro.avisar_divergencia(pedido, texto)
    elif nota.situacao == NotaFiscalCompra.Situacao.CONFERIDA:
        texto = f"NF-e {nota.numero} {verbo} e conferida" + (" pelo XML." if nota.arquivo_xml else " pela chave do DANFE.")
    else:
        texto = f"NF-e {nota.numero} {verbo} só com o número — aguardando o documento."
    financeiro.registrar_evento(pedido, EventoPedido.Tipo.NFE, texto, valor=nota.valor_total,
                                autor=autor, vai_ao_erp=True)
    return nota


def lancar_nota(pedido: PedidoCompra, *, numero="", serie="", chave="", recebimento=None,
                xml_arquivo=None, pdf_arquivo=None, autor=None) -> NotaFiscalCompra:
    chave = so_digitos(chave)
    numero = so_digitos(numero)[:20]
    if not numero and xml_arquivo is None:
        if len(chave) == 44:
            numero = str(int(partes_da_chave(chave)["numero"]))
        else:
            raise NotaInvalida("Informe o número da nota (ou anexe o XML).")
    if chave and pedido.notas_fiscais.filter(chave_acesso=chave).exists():
        raise NotaInvalida("Esta chave de acesso já está lançada neste pedido.")
    nota = NotaFiscalCompra(
        tenant_id=pedido.tenant_id, pedido=pedido, recebimento=recebimento, numero=numero,
        serie=so_digitos(serie)[:3], chave_acesso=chave[:44],
        criado_por=autor if getattr(autor, "pk", None) else None,
    )
    dados = _aplicar_documento(nota, xml_arquivo=xml_arquivo, pdf_arquivo=pdf_arquivo)
    if not nota.numero:
        raise NotaInvalida("O XML não traz o número da nota.")
    return _concluir(nota, pedido, dados, autor=autor, verbo="lançada")


def corrigir_nota(nota: NotaFiscalCompra, *, numero="", serie="", chave="", autor=None) -> NotaFiscalCompra:
    """Corrige número, série e chave digitados errado e confere de novo.

    Nota com XML não se edita: o XML é a verdade da nota (número, valor, emitente);
    se é a nota errada, remove-se e lança-se a certa.
    """
    if nota.arquivo_xml:
        raise NotaInvalida("Esta nota veio com o XML — remova-a e lance a nota certa.")
    numero = so_digitos(numero)[:20]
    chave = so_digitos(chave)[:44]
    if not numero and len(chave) == 44:
        numero = str(int(partes_da_chave(chave)["numero"]))
    if not numero:
        raise NotaInvalida("Informe o número da nota.")
    if chave and nota.pedido.notas_fiscais.exclude(pk=nota.pk).filter(chave_acesso=chave).exists():
        raise NotaInvalida("Esta chave de acesso já está lançada neste pedido.")
    era = nota.numero
    nota.numero, nota.serie, nota.chave_acesso = numero, so_digitos(serie)[:3], chave
    if nota.recebimento_id and nota.recebimento.nota_fiscal_ref in ("", era):
        nota.recebimento.nota_fiscal_ref = ""  # `_concluir` regrava com o número novo
        nota.recebimento.save(update_fields=["nota_fiscal_ref"])
    return _concluir(nota, nota.pedido, None, autor=autor, verbo=f"corrigida (era a {era})")


def remover_nota(nota: NotaFiscalCompra, *, motivo="", autor=None) -> None:
    """Tira do pedido uma nota lançada por engano — e avisa o financeiro."""
    pedido, numero = nota.pedido, nota.numero
    recebimento = nota.recebimento
    if recebimento is not None and recebimento.nota_fiscal_ref == numero:
        recebimento.nota_fiscal_ref = ""
        recebimento.save(update_fields=["nota_fiscal_ref"])
    for campo in (nota.arquivo_xml, nota.arquivo_pdf):
        if campo:
            campo.delete(save=False)
    valor = nota.valor_total
    nota.delete()
    financeiro.sincronizar_nfe(pedido)
    texto = f"NF-e {numero} removida do pedido — lançada por engano." + (f" {motivo}" if motivo else "")
    if not pedido.notas_fiscais.exists():
        texto += " O pedido volta a aguardar a nota."
    financeiro.registrar_evento(pedido, EventoPedido.Tipo.NFE, texto, valor=valor, autor=autor, vai_ao_erp=True)


#: Ordem da lista do ERP: o que pede ação vem primeiro.
_ORDEM_SITUACAO = {"aguardando_nota": 0, "divergente": 1, "aguardando_documento": 2, "conferida": 3}
_ROTULO_SITUACAO = {
    "aguardando_nota": "Aguardando NF-e",
    "aguardando_documento": "Aguardando documento",
    "divergente": "Divergente",
    "conferida": "Conferida",
}


def notas_das_compras(tenant_id, *, so_pendentes: bool = False) -> list[dict]:
    """As NF-e das compras e as compras que ainda esperam nota — a lista do ERP.

    *Dono, 11/10/2026:* "em NF-e era para ficar a nota com pendência". A nota da
    compra mora aqui (pode nascer só com o número), e a aba de notas recebidas do
    ERP só via as importadas por XML: a nota pendente, e a compra recebida sem
    nota nenhuma, sumiam de quem paga. Cada linha diz a situação e o pedido de
    onde veio; as que pedem ação vêm primeiro.
    """
    from .impexp import RECURSO_NOTA_COMPRA

    def url(nota, especie, campo):
        if not getattr(nota, campo):
            return None
        from funcoesimpexp.entrega import url_do_arquivo

        return url_do_arquivo(RECURSO_NOTA_COMPRA, especie, nota.pk)

    def base(pedido) -> dict:
        return {
            "pedido": pedido.pk, "fornecedor": pedido.fornecedor_id,
            "fornecedor_nome": pedido.fornecedor.razao_social,
            "centro_custo_nome": getattr(pedido.centro_custo, "nome", "") or "",
            "valor_pedido": str(pedido.valor_total) if pedido.valor_total is not None else None,
        }

    linhas = []
    notas = (NotaFiscalCompra.objects.filter(tenant_id=tenant_id)
             .select_related("pedido__fornecedor", "pedido__centro_custo", "recebimento"))
    if so_pendentes:
        notas = notas.exclude(situacao=NotaFiscalCompra.Situacao.CONFERIDA)
    for n in notas:
        linhas.append({
            **base(n.pedido), "nota": n.nota_id, "numero": n.numero, "serie": n.serie,
            "chave_acesso": n.chave_acesso, "valor_total": str(n.valor_total) if n.valor_total is not None else None,
            "data_emissao": n.data_emissao.isoformat() if n.data_emissao else None,
            "data": (n.recebimento.data if n.recebimento_id else n.criado_em.date()).isoformat(),
            "situacao": n.situacao, "situacao_nome": _ROTULO_SITUACAO[n.situacao],
            "divergencias": n.divergencias,
            "url_xml": url(n, "xml", "arquivo_xml"), "url_pdf": url(n, "pdf", "arquivo_pdf"),
        })

    # A compra recebida sem nota alguma: a pendência que não tem linha de nota.
    sem_nota = (PedidoCompra.objects.filter(tenant_id=tenant_id, recebimentos__isnull=False, notas_fiscais__isnull=True)
                .exclude(status=PedidoCompra.Status.CANCELADO).distinct()
                .select_related("fornecedor", "centro_custo").prefetch_related("recebimentos"))
    for p in sem_nota:
        ultimo = max((r.data for r in p.recebimentos.all()), default=None)
        linhas.append({
            **base(p), "nota": None, "numero": "", "serie": "", "chave_acesso": "", "valor_total": None,
            "data_emissao": None, "data": ultimo.isoformat() if ultimo else None,
            "situacao": "aguardando_nota", "situacao_nome": _ROTULO_SITUACAO["aguardando_nota"],
            "divergencias": [], "url_xml": None, "url_pdf": None,
        })

    linhas.sort(key=lambda l: l["data"] or "", reverse=True)
    linhas.sort(key=lambda l: _ORDEM_SITUACAO[l["situacao"]])
    return linhas


def anexar_documento(nota: NotaFiscalCompra, *, chave="", xml_arquivo=None, pdf_arquivo=None, autor=None) -> NotaFiscalCompra:
    if xml_arquivo is None and pdf_arquivo is None and not chave:
        raise NotaInvalida("Anexe o XML ou o PDF da nota (ou informe a chave).")
    chave = so_digitos(chave)
    if chave:
        nota.chave_acesso = chave[:44]
    dados = _aplicar_documento(nota, xml_arquivo=xml_arquivo, pdf_arquivo=pdf_arquivo)
    return _concluir(nota, nota.pedido, dados, autor=autor, verbo="recebeu o documento")
