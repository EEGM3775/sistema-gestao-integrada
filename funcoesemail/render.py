"""Renderização do texto: chave + contexto → (assunto, corpo).

Usa uma Engine de template **própria**, não a do projeto. Assim o pacote
funciona igual na IAM e no backend sem depender de `INSTALLED_APPS`, `DIRS` ou
de qualquer configuração de template do serviço que o importou — que é a
condição para ele ser realmente compartilhável.

`autoescape=False` porque estes templates são TEXTO PURO: com escape ligado,
`Fulano & Cia` viraria `Fulano &amp; Cia` no corpo do e-mail. (Se um dia houver
variante HTML, ela precisa de uma Engine própria com escape LIGADO — não reuse
esta.)
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from django.template import Context, Engine

from .mensagens import obter

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

ASSINATURA = "\n\n—\nSistema de Gestão Integrada\nEste é um e-mail automático; não responda."


@lru_cache(maxsize=1)
def _engine() -> Engine:
    return Engine(dirs=[str(TEMPLATES_DIR)], autoescape=False)


def carregar_fonte(caminho_relativo: str) -> str:
    """Devolve o texto bruto do template.

    **Ponto de troca deliberado.** Hoje lê do arquivo versionado em git. Quando a
    comunicação com clientes exigir edição sem deploy, é aqui que se consulta o
    banco primeiro e cai no arquivo como padrão — sem tocar em `enviar()` nem em
    nenhum chamador. Os e-mails de identidade devem permanecer travados em
    arquivo mesmo depois disso: ninguém reescreve aviso de segurança pela UI.
    """
    return (TEMPLATES_DIR / caminho_relativo).read_text(encoding="utf-8")


def renderizar(chave: str, contexto: dict) -> tuple[str, str]:
    """(assunto, corpo). O assunto aceita `{campo}` simples, vindo do contexto."""
    mensagem = obter(chave)
    # `autoescape=False` precisa vir TAMBÉM no Context: o da Engine não alcança
    # um Context construído à mão, e o corpo sairia com `&amp;`/`&gt;` no texto.
    corpo = _engine().from_string(carregar_fonte(mensagem.template)).render(
        Context(contexto, autoescape=False)
    )
    try:
        assunto = mensagem.assunto.format(**contexto)
    except KeyError:
        # Assunto com placeholder que o contexto não trouxe: manda o assunto cru
        # em vez de estourar — e-mail entregue com assunto imperfeito é melhor
        # que fluxo de segurança interrompido.
        assunto = mensagem.assunto
    return assunto, corpo.strip() + ASSINATURA
