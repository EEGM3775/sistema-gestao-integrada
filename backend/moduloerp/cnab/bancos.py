"""O que muda de banco para banco: nosso número, o dígito dele e o campo livre.

Cada classe traduz uma carteira (`ContaCobrancaBancaria`) nos campos do banco.
O significado dos campos genéricos da carteira muda por banco, e a tela de
cadastro mostra a ajuda de `AJUDA_CAMPOS`:

| Banco | `convenio` | `variacao_carteira` |
|---|---|---|
| Banco do Brasil (001) | convênio de 7 dígitos | variação da carteira |
| Santander (033) | código do beneficiário (7) | — |
| Caixa (104) | código do beneficiário (6) | — |
| Bradesco (237) | código da empresa (CNAB 400) | — |
| Itaú (341) | — | — |
| Sicredi (748) | código do beneficiário (5) | posto (2) |
| Sicoob (756) | código do cliente | modalidade (2) |

As regras de dígito seguem os manuais públicos de cada banco. O banco confere
tudo na homologação da carteira — ver `cnab/__init__.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .codigo_barras import modulo10, modulo11, soma_modulo11


def so_digitos(texto) -> str:
    return "".join(ch for ch in str(texto or "") if ch.isdigit())


def z(texto, largura: int) -> str:
    """Só dígitos, zeros à esquerda, exatamente `largura` (corta pela esquerda)."""
    return so_digitos(texto).zfill(largura)[-largura:]


@dataclass(frozen=True)
class NossoNumero:
    numero: str       # os dígitos que vão ao código de barras / remessa (sem DV)
    dv: str           # o dígito verificador ('' quando o banco não usa)
    impresso: str     # como aparece no boleto


class Banco:
    codigo = ""
    nome = ""
    layouts = ("240",)
    versao_arquivo_240 = "087"
    versao_lote_240 = "045"
    campos_obrigatorios: tuple[str, ...] = ()

    def problemas(self, c) -> list[str]:
        faltando = [rotulo for campo, rotulo in self.campos_obrigatorios if not so_digitos(getattr(c, campo))]
        if c.layout not in self.layouts:
            faltando.append(f"o {self.nome} não usa CNAB {c.layout} nesta versão")
        return faltando

    def nosso_numero(self, c, sequencial: int) -> NossoNumero:
        raise NotImplementedError

    def campo_livre(self, c, nn: NossoNumero) -> str:
        raise NotImplementedError

    # CNAB 240 — os três campos que cada banco preenche do seu jeito.
    def convenio_240(self, c) -> str:
        return z(c.convenio, 20)

    def identificacao_240(self, c, nn: NossoNumero) -> str:
        return (nn.numero + nn.dv).ljust(20)

    def conta_240(self, c) -> str:
        """Agência(5) + DV(1) + conta(12) + DV(1) + DV agência/conta(1)."""
        return f"{z(c.agencia, 5)}{(c.agencia_dv or ' ')[:1]}{z(c.conta, 12)}{(c.conta_dv or ' ')[:1]} "

    # Onde o banco se afasta do FEBRABAN — cada valor abaixo é o padrão do
    # manual, e a classe do banco troca o que o validador dele recusa.
    def conta_header_arquivo_240(self, c) -> str:
        return self.conta_240(c)

    def convenio_lote_240(self, c) -> str:
        return self.convenio_240(c)

    #: Header de lote, 12-13: "uso exclusivo FEBRABAN", em branco.
    reservado_lote_240 = "  "
    #: Segmento P, 59-60: forma de cadastramento (1 = com cadastro) e tipo de
    #: documento (1 = tradicional).
    cadastro_e_documento_240 = "11"

    def beneficiario_impresso(self, c) -> str:
        return f"{so_digitos(c.agencia)} / {so_digitos(c.conta)}-{c.conta_dv}".strip("-")


class BancoDoBrasil(Banco):
    codigo, nome = "001", "Banco do Brasil"
    versao_arquivo_240, versao_lote_240 = "083", "042"
    campos_obrigatorios = (("convenio", "convênio"), ("carteira", "carteira"), ("agencia", "agência"), ("conta", "conta"))

    def problemas(self, c):
        p = super().problemas(c)
        if so_digitos(c.convenio) and len(so_digitos(c.convenio)) != 7:
            p.append("o convênio de cobrança do Banco do Brasil precisa ter 7 dígitos")
        return p

    def nosso_numero(self, c, sequencial):
        numero = z(c.convenio, 7) + f"{sequencial:010d}"
        return NossoNumero(numero, "", numero)

    def campo_livre(self, c, nn):
        return "000000" + nn.numero + z(c.carteira, 2)

    def convenio_240(self, c):
        return f"{z(c.convenio, 9)}0014{z(c.carteira, 2)}{z(c.variacao_carteira, 3)}  "


class Santander(Banco):
    codigo, nome = "033", "Santander"
    versao_arquivo_240, versao_lote_240 = "040", "030"
    campos_obrigatorios = (("convenio", "código do beneficiário"), ("carteira", "carteira"), ("agencia", "agência"))

    def nosso_numero(self, c, sequencial):
        numero = f"{sequencial:012d}"
        resto = soma_modulo11(numero) % 11
        dv = "0" if resto in (0, 1) else str(11 - resto)
        return NossoNumero(numero, dv, f"{numero}-{dv}")

    def campo_livre(self, c, nn):
        return "9" + z(c.convenio, 7) + nn.numero + nn.dv + "0" + z(c.carteira, 3)

    def convenio_240(self, c):
        return (z(c.agencia, 4) + z(c.convenio, 9)).ljust(20)

    def identificacao_240(self, c, nn):
        return (nn.numero + nn.dv).zfill(13).ljust(20)

    def beneficiario_impresso(self, c):
        return f"{so_digitos(c.agencia)} / {so_digitos(c.convenio)}"


class Caixa(Banco):
    codigo, nome = "104", "Caixa Econômica Federal"
    versao_arquivo_240, versao_lote_240 = "107", "067"
    campos_obrigatorios = (("convenio", "código do beneficiário"), ("agencia", "agência"))

    def nosso_numero(self, c, sequencial):
        # SIGCB: "14" = cobrança registrada, boleto emitido pelo beneficiário.
        numero = "14" + f"{sequencial:015d}"
        dv = str(modulo11(numero))
        return NossoNumero(numero, dv, f"{numero}-{dv}")

    def campo_livre(self, c, nn):
        cod = z(c.convenio, 6)
        n = nn.numero
        base = cod + str(modulo11(cod)) + n[2:5] + n[0] + n[5:8] + n[1] + n[8:17]
        return base + str(modulo11(base))

    def convenio_240(self, c):
        return z(c.convenio, 6).ljust(20, "0")

    def identificacao_240(self, c, nn):
        return (nn.numero + "   ").ljust(20)

    def beneficiario_impresso(self, c):
        cod = z(c.convenio, 6)
        return f"{so_digitos(c.agencia)} / {cod}-{modulo11(cod)}"


def _dv_bradesco(carteira: str, numero: str) -> str:
    resto = soma_modulo11(z(carteira, 2) + numero, peso_maximo=7) % 11
    if resto == 0:
        return "0"
    return "P" if 11 - resto == 10 else str(11 - resto)


class Bradesco(Banco):
    codigo, nome = "237", "Bradesco"
    layouts = ("240", "400")
    versao_arquivo_240, versao_lote_240 = "084", "042"
    campos_obrigatorios = (("carteira", "carteira"), ("agencia", "agência"), ("conta", "conta"))

    def nosso_numero(self, c, sequencial):
        numero = f"{sequencial:011d}"
        dv = _dv_bradesco(c.carteira, numero)
        return NossoNumero(numero, dv, f"{z(c.carteira, 2)}/{numero}-{dv}")

    def campo_livre(self, c, nn):
        return z(c.agencia, 4) + z(c.carteira, 2) + nn.numero + z(c.conta, 7) + "0"

    def identificacao_240(self, c, nn):
        return (z(c.carteira, 3) + "00000" + nn.numero + nn.dv).ljust(20)


class Itau(Banco):
    codigo, nome = "341", "Itaú"
    layouts = ("240", "400")
    versao_arquivo_240, versao_lote_240 = "040", "030"
    reservado_lote_240 = "00"
    campos_obrigatorios = (("carteira", "carteira"), ("agencia", "agência"), ("conta", "conta"))
    # Carteiras em que o dígito do nosso número ignora agência e conta.
    CARTEIRAS_ESPECIAIS = {"126", "131", "146", "150", "168"}

    def nosso_numero(self, c, sequencial):
        numero = f"{sequencial:08d}"
        cart = z(c.carteira, 3)
        base = cart + numero if cart in self.CARTEIRAS_ESPECIAIS else z(c.agencia, 4) + z(c.conta, 5) + cart + numero
        dv = str(modulo10(base))
        return NossoNumero(numero, dv, f"{cart}/{numero}-{dv}")

    def campo_livre(self, c, nn):
        agencia, conta = z(c.agencia, 4), z(c.conta, 5)
        return z(c.carteira, 3) + nn.numero + nn.dv + agencia + conta + str(modulo10(agencia + conta)) + "000"

    def identificacao_240(self, c, nn):
        return (z(c.carteira, 3) + nn.numero + nn.dv).ljust(20)


class Sicredi(Banco):
    codigo, nome = "748", "Sicredi"
    versao_arquivo_240, versao_lote_240 = "081", "040"
    campos_obrigatorios = (
        ("convenio", "código do beneficiário"), ("agencia", "cooperativa"), ("variacao_carteira", "posto"),
    )

    def nosso_numero(self, c, sequencial):
        # AA + byte "2" (gerado pelo beneficiário) + sequencial de 5 + DV.
        ano = f"{date.today():%y}"
        numero = f"{ano}2{sequencial % 100000:05d}"
        base = z(c.agencia, 4) + z(c.variacao_carteira, 2) + z(c.convenio, 5) + numero
        dv = str(modulo11(base))
        return NossoNumero(numero, dv, f"{numero[:2]}/{numero[2:]}-{dv}")

    def campo_livre(self, c, nn):
        base = "11" + nn.numero + nn.dv + z(c.agencia, 4) + z(c.variacao_carteira, 2) + z(c.convenio, 5) + "10"
        resto = soma_modulo11(base) % 11
        return base + ("0" if resto <= 1 else str(11 - resto))

    def beneficiario_impresso(self, c):
        return f"{so_digitos(c.agencia)}.{so_digitos(c.variacao_carteira)}.{so_digitos(c.convenio)}"


class Sicoob(Banco):
    codigo, nome = "756", "Sicoob"
    versao_arquivo_240, versao_lote_240 = "081", "040"
    campos_obrigatorios = (("convenio", "código do cliente"), ("agencia", "cooperativa"))
    CONSTANTE = "3197"
    # O validador CNAB do Sicoob (laudo de 01/10/2026) pede zero na forma de
    # cadastramento (59) e branco no tipo de documento (60).
    cadastro_e_documento_240 = "0 "

    def conta_header_arquivo_240(self, c):
        """No header de arquivo, o DV de agência/conta (72) é zero."""
        return self.conta_240(c)[:-1] + "0"

    def convenio_lote_240(self, c):
        """No header de lote, o convênio (34-53) vai em branco."""
        return " " * 20

    def nosso_numero(self, c, sequencial):
        numero = f"{sequencial:07d}"
        base = z(c.agencia, 4) + z(c.convenio, 10) + numero
        soma = sum(int(d) * int(self.CONSTANTE[i % 4]) for i, d in enumerate(base))
        resto = soma % 11
        dv = "0" if resto in (0, 1) else str(11 - resto)
        return NossoNumero(numero, dv, f"{numero}-{dv}")

    def campo_livre(self, c, nn):
        modalidade = z(c.variacao_carteira or "01", 2)
        return z(c.carteira or "1", 1) + z(c.agencia, 4) + modalidade + z(c.convenio, 7) + nn.numero + nn.dv + "001"

    def identificacao_240(self, c, nn):
        modalidade = z(c.variacao_carteira or "01", 2)
        return (nn.numero + nn.dv + "01" + modalidade + "1").ljust(20)

    def beneficiario_impresso(self, c):
        return f"{so_digitos(c.agencia)} / {so_digitos(c.convenio)}"


BANCOS: dict[str, Banco] = {b.codigo: b for b in (
    BancoDoBrasil(), Santander(), Caixa(), Bradesco(), Itau(), Sicredi(), Sicoob(),
)}

AJUDA_CAMPOS = {
    "001": {"convenio": "Convênio de cobrança (7 dígitos)", "variacao_carteira": "Variação da carteira (ex.: 019)"},
    "033": {"convenio": "Código do beneficiário (7 dígitos)"},
    "104": {"convenio": "Código do beneficiário (6 dígitos)"},
    "237": {"convenio": "Código da empresa no Bradesco (CNAB 400)"},
    "341": {},
    "748": {"convenio": "Código do beneficiário (5 dígitos)", "variacao_carteira": "Posto (2 dígitos)"},
    "756": {"convenio": "Código do cliente", "variacao_carteira": "Modalidade (ex.: 01)"},
}


def banco_de(carteira) -> Banco:
    try:
        return BANCOS[carteira.banco]
    except KeyError as exc:
        raise ValueError(f"Banco {carteira.banco} ainda não tem cobrança CNAB no SGI.") from exc
