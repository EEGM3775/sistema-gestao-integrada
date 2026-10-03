"""E-mails de identidade — adaptação do domínio da IAM para o `funcoesemail`.

O TEXTO destes e-mails mudou de lugar: agora vive em `funcoesemail/templates/`,
na raiz do repositório, junto com o de todos os outros e-mails da plataforma
(era o objetivo — `identity/` acumulava responsabilidade demais). A ENTREGA
continua sendo feita aqui, pelo SMTP da própria IAM: recuperação de senha não
pode depender de outro serviço estar no ar.

O que sobra neste módulo é tradução: objeto `Usuario` → contexto de template.
É de propósito que os chamadores (views/serializers) continuem vendo as mesmas
funções de antes — a reorganização não devia obrigá-los a saber de template.

Regra preservada: **o e-mail sempre diz quem disparou a ação e oferece um
caminho de contestação**. Um aviso que só informa "sua senha foi alterada"
transforma a vítima em espectadora; dizendo "o admin fulano disparou isto às
14h32, não foi você? clique aqui", ela vira o detector que nenhum controle
técnico substitui contra engenharia social.

Falha de envio nunca derruba o fluxo chamador (o `funcoesemail` devolve False e
loga) — mas no caminho de recuperação a view converte isso em erro explícito ao
usuário, porque "aceitei sua solicitação" sem entregar o token é pior que recusar.
"""
from django.conf import settings

from funcoesemail import enviar, enviar_varios


def _nome(usuario):
    return usuario.first_name or usuario.username


def _url(caminho, token):
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}{caminho}?token={token}"


def enviar_recuperacao(usuario, token_claro, minutos):
    """Caminho 1 — o próprio usuário pediu. Token vai para a caixa dele."""
    return enviar(
        "identidade.recuperacao",
        usuario.email,
        {
            "nome": _nome(usuario),
            "conta": usuario.username,
            "link": _url("/redefinir-senha", token_claro),
            "minutos": minutos,
        },
    )


def enviar_aviso_admin_recuperacao(admin, alvo, ip=None):
    """Aviso ao ADMIN de que houve um pedido — deliberadamente SEM o link.

    O admin precisa enxergar o que acontece no tenant: um pedido de recuperação
    para uma conta que deveria estar inativa, ou uma rajada deles, é sinal de
    ataque em curso. Mas enxergar não é o mesmo que poder agir sobre a conta: se
    o link viesse aqui, todo admin teria takeover silencioso de qualquer
    usuário, disparável por qualquer anônimo que soubesse um nome de usuário.
    Supervisão sim, poder não.
    """
    return enviar(
        "identidade.aviso_admin_recuperacao",
        admin.email,
        {
            "nome": _nome(admin),
            "alvo": alvo.username,
            "alvo_nome_completo": alvo.get_full_name(),
            "alvo_email": alvo.email,
            "origem": ip or "não identificada",
        },
    )


def enviar_confirmacao_troca_email(usuario, email_antigo, email_novo, token_claro, horas):
    """Vai para o endereço ANTIGO — é o que fecha o takeover em dois passos."""
    return enviar(
        "identidade.confirmacao_troca_email",
        email_antigo,
        {
            "nome": _nome(usuario),
            "conta": usuario.username,
            "email_antigo": email_antigo,
            "email_novo": email_novo,
            "link": _url("/confirmar-email", token_claro),
            "horas": horas,
        },
    )


def enviar_aviso_email_trocado(usuario, email_antigo, email_novo, autor):
    """Avisa o endereço ANTIGO e o NOVO de uma troca aplicada direto pelo admin.

    Usado quando o dono da empresa corrige o e-mail de um funcionário: a troca
    vale na hora (ele administra aquelas contas por direito, e exigir confirmação
    num endereço errado ou morto travaria a pessoa de vez). O aviso nos dois
    endereços é o que sobra de detecção — se o antigo ainda estiver vivo e a
    troca não fizer sentido, a pessoa descobre.
    """
    return enviar_varios(
        "identidade.aviso_email_trocado",
        [email_antigo, email_novo],
        {
            "nome": _nome(usuario),
            "conta": usuario.username,
            "email_antigo": email_antigo,
            "email_novo": email_novo,
            "autor": autor.get_full_name() or autor.username,
        },
    )


def enviar_aviso_senha_alterada(usuario, por_quem=None):
    """Notificação pós-fato. Fecha o laço: toda mudança de senha é anunciada."""
    quem = (
        f"pelo administrador {por_quem.get_full_name() or por_quem.username}"
        if por_quem
        else "por você"
    )
    return enviar(
        "identidade.aviso_senha_alterada",
        usuario.email,
        {"nome": _nome(usuario), "conta": usuario.username, "por_quem": quem},
    )


def enviar_aviso_privilegio_alterado(usuario, autor, resumo):
    """Escalada de privilégio também é anunciada ao dono da conta."""
    return enviar(
        "identidade.aviso_privilegio_alterado",
        usuario.email,
        {
            "nome": _nome(usuario),
            "conta": usuario.username,
            "autor": autor.get_full_name() or autor.username,
            "resumo": resumo,
        },
    )


# Remodelagem, fase 1 — toda mudança no segundo fator é anunciada ao dono da
# conta, pela mesma regra dos avisos acima: dizer quem fez, e o que fazer se não
# foi a pessoa. Um admin que redefine o segundo fator de alguém abre caminho para
# assumir a conta com a senha dela — e a vítima fica sabendo na hora.
_SEGUNDO_FATOR = {
    "ativado": ("ativado", "O segundo fator foi ativado"),
    "desativado": ("desativado", "O segundo fator foi desativado"),
    "trocado": ("trocado de aparelho", "O segundo fator passou para um celular novo"),
    "codigos": ("códigos trocados", "Os códigos de recuperação foram trocados {por_quem}"),
    "recuperacao": ("código de recuperação usado", "Um código de recuperação foi usado para entrar"),
    "redefinido": ("redefinido", "O segundo fator foi redefinido {por_quem}"),
}


def enviar_aviso_segundo_fator(usuario, evento, *, por_quem=None, restantes=None):
    """`por_quem` é o admin que fez (um usuário) ou, no caminho de emergência
    do shell (D240), o nome do operador da plataforma (um texto)."""
    assunto, frase = _SEGUNDO_FATOR[evento]
    if isinstance(por_quem, str):
        quem = f"pela operação da plataforma ({por_quem})"
    elif por_quem:
        quem = f"pelo administrador {por_quem.get_full_name() or por_quem.username}"
    else:
        quem = ""
    return enviar(
        "identidade.aviso_segundo_fator",
        usuario.email,
        {
            "nome": _nome(usuario),
            "conta": usuario.username,
            "assunto": assunto,
            "o_que": frase.format(por_quem=quem).strip(),
            "restantes": restantes,
        },
    )
