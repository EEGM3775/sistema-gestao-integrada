"""Entrega. Cada serviço envia pelo SMTP que ele mesmo configurou.

Regra que vale para todo mundo aqui: **falha de envio nunca derruba o fluxo
chamador** — é logada em WARNING e devolvida como `False`. Quem precisa tratar
(a recuperação de senha precisa: "aceitei sua solicitação" sem entregar o token
é pior que recusar) olha o retorno e decide.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

from .render import renderizar

logger = logging.getLogger(__name__)


def enviar(chave: str, destinatario: str, contexto: dict | None = None) -> bool:
    """Renderiza e entrega. Devolve True/False; nunca levanta por falha de envio.

    Levanta apenas `MensagemDesconhecida` — erro de programação, não de ambiente:
    chave errada tem de aparecer no primeiro teste, não virar e-mail vazio.
    """
    contexto = contexto or {}
    if not destinatario:
        logger.warning("E-mail '%s' não enviado: destinatário vazio.", chave)
        return False

    assunto, corpo = renderizar(chave, contexto)

    if not getattr(settings, "EMAIL_HOST", ""):
        # Só acontece em dev: fora de DEBUG os settings recusam subir sem MAIL_HOST.
        logger.warning("E-mail '%s' não enviado: MAIL_HOST não configurado.", chave)
        return False

    # Camada 2 — provedores de e-mail cortam ou marcam como spam quem dispara em
    # rajada, e a reputação do domínio é difícil de recuperar. O limitador é
    # OPCIONAL aqui de propósito: este pacote é compartilhado com a IAM, que não
    # tem (nem deve ter) as dependências do backend — recuperação de senha
    # precisa funcionar mesmo isolada. Onde o limitador existe, ele vale; onde
    # não existe, o envio segue. Ver docs/arquitetura/rate-limiting.md §3.
    try:
        from nucleo.rate_limit import LimiteFornecedorExcedido, consumir
    except ImportError:
        pass
    else:
        try:
            consumir("email")
        except LimiteFornecedorExcedido as exc:
            # Não levanta: quem chama e-mail quase nunca tem como reagendar (o
            # aviso é efeito colateral de outra operação). Perder o aviso é
            # melhor que abortar a operação de negócio — mas fica registrado.
            logger.warning("E-mail '%s' não enviado: %s", chave, exc)
            return False
    try:
        send_mail(
            subject=assunto,
            message=corpo,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[destinatario],
            fail_silently=False,
        )
        return True
    except Exception:  # noqa: BLE001 — indisponibilidade de SMTP não derruba negócio
        logger.exception("Falha ao enviar e-mail '%s' para %s", chave, destinatario)
        return False


def enviar_varios(chave: str, destinatarios, contexto: dict | None = None) -> int:
    """Mesma mensagem para vários endereços; devolve quantos foram entregues.

    Deduplica: avisar troca de e-mail manda para o endereço antigo e o novo, que
    podem ser iguais se só a caixa mudou de grafia — a pessoa receberia duas
    vezes o mesmo aviso.
    """
    return sum(1 for destino in dict.fromkeys(d for d in destinatarios if d)
               if enviar(chave, destino, contexto))
