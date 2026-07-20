"""Catálogo de mensagens: a chave que o código usa → template + assunto.

Ter o catálogo explícito (em vez de deixar cada chamador apontar para um arquivo)
dá três coisas: erro imediato e legível quando a chave não existe, um só lugar
para ver TODOS os e-mails que a plataforma manda, e o gancho natural para a
edição por tela no futuro (a chave é o identificador estável).

Convenção da chave: `<area>.<assunto>` — a área casa com a subpasta em
`templates/`.
"""


class MensagemDesconhecida(KeyError):
    """Chave não registrada. Erra alto na hora, em vez de mandar e-mail vazio."""


class Mensagem:
    __slots__ = ("chave", "template", "assunto", "descricao")

    def __init__(self, chave: str, template: str, assunto: str, descricao: str = ""):
        self.chave = chave
        self.template = template
        self.assunto = assunto
        self.descricao = descricao


def _m(chave, template, assunto, descricao=""):
    return Mensagem(chave, template, assunto, descricao)


# --- Identidade (IAM) -------------------------------------------------------
# Texto puro por decisão de segurança: e-mail de identidade não carrega HTML
# remoto nem imagem rastreadora, e precisa ser legível em qualquer cliente —
# inclusive no terminal de quem diagnostica um incidente.
_IDENTIDADE = [
    _m(
        "identidade.recuperacao",
        "identidade/recuperacao.txt",
        "Redefinição de senha",
        "O próprio usuário pediu; o token vai para a caixa DELE.",
    ),
    _m(
        "identidade.aviso_admin_recuperacao",
        "identidade/aviso_admin_recuperacao.txt",
        "Pedido de recuperação de senha: {alvo}",
        "Aviso ao admin — deliberadamente SEM o link (supervisão, não poder).",
    ),
    _m(
        "identidade.confirmacao_troca_email",
        "identidade/confirmacao_troca_email.txt",
        "Confirme a troca de e-mail da sua conta",
        "Vai para o endereço ANTIGO: é o que fecha o takeover em dois passos.",
    ),
    _m(
        "identidade.aviso_email_trocado",
        "identidade/aviso_email_trocado.txt",
        "O e-mail da sua conta foi alterado",
        "Troca aplicada direto pelo admin; avisa os dois endereços.",
    ),
    _m(
        "identidade.aviso_senha_alterada",
        "identidade/aviso_senha_alterada.txt",
        "Sua senha foi alterada",
        "Notificação pós-fato: toda mudança de senha é anunciada.",
    ),
    _m(
        "identidade.aviso_privilegio_alterado",
        "identidade/aviso_privilegio_alterado.txt",
        "Seus acessos foram alterados",
        "Escalada de privilégio é anunciada ao dono da conta.",
    ),
]

# --- CRM -------------------------------------------------------------------
_CRM = [
    _m(
        "crm.lembrete_tarefa",
        "crm/lembrete_tarefa.txt",
        "Lembrete de Tarefa: {assunto}",
        "Tarefa não concluída vencendo nas próximas 24h (job diário do beat).",
    ),
]

# --- Calendário ------------------------------------------------------------
_CALENDARIO = [
    _m(
        "calendario.lembrete_evento",
        "calendario/lembrete_evento.txt",
        "Lembrete: {titulo}",
        "Par do aviso in-app: o mesmo lembrete também vira Notificacao no sino.",
    ),
]

MENSAGENS = {m.chave: m for m in _IDENTIDADE + _CRM + _CALENDARIO}


def obter(chave: str) -> Mensagem:
    try:
        return MENSAGENS[chave]
    except KeyError:
        disponiveis = ", ".join(sorted(MENSAGENS)) or "(nenhuma)"
        raise MensagemDesconhecida(
            f"Mensagem de e-mail '{chave}' não registrada em funcoesemail/mensagens.py. "
            f"Registradas: {disponiveis}"
        ) from None
