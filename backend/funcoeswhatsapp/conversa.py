# backend/funcoeswhatsapp/conversa.py
"""
Contexto de uma conversa — o objeto que os fluxos recebem (Fase C).

Reúne canal/tenant, cliente de saída, remetente (pessoa+papel), a mensagem
normalizada e os atalhos de estado (Redis). Substitui o `context` montado no
`bot.js` do Node. Os fluxos só falam com este objeto; não conhecem Redis nem a
Graph API diretamente.
"""
from . import state


class Conversa:
    def __init__(self, *, canal, client, telefone, mensagem, pessoa, role):
        self.canal = canal
        self.tenant_id = canal.tenant_id
        self.client = client
        self.telefone = telefone
        self.mensagem = mensagem
        self.pessoa = pessoa
        self.role = role

    # --- mensagem recebida ---------------------------------------------------
    @property
    def texto(self):
        return (self.mensagem.get('body') or '').strip()

    @property
    def media_id(self):
        return self.mensagem.get('media_id')

    # --- saída ---------------------------------------------------------------
    def responder(self, texto):
        self.client.enviar_texto(self.telefone, texto)

    def botoes(self, texto, botoes):
        self.client.enviar_botoes(self.telefone, texto, botoes)

    def lista(self, texto, texto_botao, itens):
        self.client.enviar_lista(self.telefone, texto, texto_botao, itens)

    # --- estado (Redis, escopado por tenant+telefone) ------------------------
    def get_state(self):
        return state.get_state(self.tenant_id, self.telefone)

    def set_state(self, estado):
        # Carimba o papel: mudança de cadastro no meio da conversa reinicia a sessão.
        estado = {**estado, 'role': self.role}
        state.set_state(self.tenant_id, self.telefone, estado)

    def clear_state(self):
        state.clear_state(self.tenant_id, self.telefone)
