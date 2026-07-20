"""funcoesemail — o lugar único onde mora e-mail na plataforma.

**Por que é um pacote na raiz e não um app Django.** IAM e backend são serviços
separados, com processo e banco próprios. Um app Django do backend não é
importável pela IAM, e fazer a IAM pedir o envio ao backend por HTTP quebraria a
propriedade que motivou o D11: **recuperação de senha tem de funcionar com o
backend fora do ar**. É também o que fazem os provedores de identidade de
mercado (Entra ID, WSO2, ForgeRock): o serviço de identidade entrega os próprios
e-mails de segurança. O que se centraliza é o TEXTO, não o caminho de rede.

    IAM ─────┐                        (cada serviço entrega pelo próprio SMTP;
             ├──> funcoesemail        em produção os dois apontam para o mesmo
    backend ─┘    (templates)          provedor — SES/SendGrid)

**Como usar** (uma função só):

    from funcoesemail import enviar

    enviar("identidade.recuperacao", "pessoa@empresa.com", {
        "nome": "Maria", "link": url, "minutos": 30,
    })

**Como acrescentar um e-mail novo:** crie o `.txt` em `templates/` e registre a
chave em `mensagens.py`. Nada além disso — quem chama não muda.

**Costura deixada de propósito** (`render.carregar_fonte`): hoje o texto vem de
arquivo. Quando a comunicação com clientes exigir edição sem deploy, troca-se a
fonte por banco ali, e nenhum chamador é afetado.

Não faz (ainda): fila/retry próprios, log de entrega em banco, canal in-app ou
WhatsApp, preferência por usuário. Ver README.md.
"""

from .mensagens import MENSAGENS, MensagemDesconhecida
from .transporte import enviar, enviar_varios

__all__ = ["enviar", "enviar_varios", "MENSAGENS", "MensagemDesconhecida"]
