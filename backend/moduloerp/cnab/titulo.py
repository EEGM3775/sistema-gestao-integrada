"""O título como a remessa o lê — e os campos de largura fixa do CNAB."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .bancos import NossoNumero, so_digitos


def texto(valor, largura: int) -> str:
    """Maiúsculas sem acento, cortado ou completado com brancos — os bancos
    recusam arquivo com caractere fora do ASCII básico."""
    limpo = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode()
    limpo = "".join(ch if 32 <= ord(ch) < 127 else " " for ch in limpo).upper()
    return limpo[:largura].ljust(largura)


def numero(valor, largura: int) -> str:
    return so_digitos(valor).zfill(largura)[-largura:]


def dinheiro(valor: Decimal, largura: int) -> str:
    centavos = int((Decimal(valor or 0) * 100).quantize(Decimal("1")))
    return f"{centavos:0{largura}d}"[-largura:]


def data8(d: date | None) -> str:
    return d.strftime("%d%m%Y") if d else "0" * 8


def data6(d: date | None) -> str:
    return d.strftime("%d%m%y") if d else "0" * 6


@dataclass(frozen=True)
class Pagador:
    documento: str
    nome: str
    endereco: str
    bairro: str
    cep: str
    cidade: str
    uf: str

    @property
    def tipo(self) -> str:
        return "2" if len(self.documento) == 14 else "1"


@dataclass(frozen=True)
class Titulo:
    boleto_id: int
    seu_numero: str
    nosso_numero: NossoNumero
    vencimento: date
    emissao: date
    valor: Decimal
    juros_dia: Decimal
    multa_percentual: Decimal
    pagador: Pagador
    # Código de movimento da remessa: 01 = entrada (registrar o boleto),
    # 02 = pedido de baixa (D245). Os mesmos no 240 FEBRABAN e no 400 de
    # Bradesco e Itaú.
    movimento: str = "01"

    @property
    def entrada(self) -> bool:
        return self.movimento == "01"


ENTRADA, PEDIDO_DE_BAIXA = "01", "02"

SEM_PAGADOR = Pagador(documento="", nome="", endereco="", bairro="", cep="00000000", cidade="", uf="")
"""Para a instrução: o banco localiza o título pelo nosso número, e o pagador
já está registrado com ele."""


def pagador_do_cliente(cliente) -> tuple[Pagador | None, list[str]]:
    """O pagador — ou o que falta no cadastro para o banco aceitar o boleto."""
    doc = so_digitos(cliente.cpf_cnpj)
    cep = so_digitos(cliente.cep)
    faltando = []
    if len(doc) not in (11, 14):
        faltando.append("CPF/CNPJ")
    if not (cliente.endereco or "").strip():
        faltando.append("endereço")
    if len(cep) != 8:
        faltando.append("CEP")
    if not (cliente.cidade or "").strip() or len((cliente.estado or "").strip()) != 2:
        faltando.append("cidade/UF")
    if faltando:
        return None, faltando
    endereco = cliente.endereco
    if getattr(cliente, "numero_endereco", ""):
        endereco = f"{endereco}, {cliente.numero_endereco}"
    return Pagador(
        documento=doc, nome=cliente.nome_completo, endereco=endereco, bairro=cliente.bairro or "",
        cep=cep, cidade=cliente.cidade, uf=cliente.estado.upper(),
    ), []
