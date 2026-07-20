# backend/funcoeswhatsapp/flows/diario.py
"""
Fluxo do Diário de Obra pelo WhatsApp (Fase C, §5/§6).

Porte do `diarioObraFlow.js`, **simplificado ao modelo novo** de *um diário por
obra por dia* (some a seleção de múltiplos diários e o nível empreendimento→obra
vira uma lista de obras direta, paginada). A escrita passa pelo serviço único
`modulodiario.services.registrar_contribuicao` — o mesmo que a tela web usa —,
que decide autoria, tenant e disparo da IA.

Regra de contribuição (decisão do cliente): equipe ∪ responsáveis técnicos da
obra. O fluxo só lista obras onde o funcionário pode contribuir, então
`pode_contribuir` fica garantido por construção.
"""
import logging
import mimetypes

from django.core.files.base import ContentFile
from django.db.models import Q

from ..steps import DIARIO_CONFIRMAR, DIARIO_OBRA, DIARIO_COLETA

logger = logging.getLogger(__name__)

_POR_PAGINA = 9  # 9 + "Mais opções" = 10 (limite de lista do WhatsApp)


# ── entrada do fluxo ────────────────────────────────────────────────────────
def start(conversa):
    obras = _obras_do_funcionario(conversa.pessoa)
    if not obras:
        conversa.responder(
            "Não encontrei obras nas quais você faça parte da equipe ou seja "
            "responsável técnico. Fale com o administrador."
        )
        conversa.clear_state()
        return

    if len(obras) == 1:
        _iniciar_coleta(conversa, obras[0])
        return

    conversa.set_state({'flow': 'diario', 'step': DIARIO_CONFIRMAR})
    nome = (conversa.pessoa.nome_completo or '').split(' ')[0]
    conversa.botoes(
        f"Olá, {nome}! Vamos registrar no diário de obra?",
        [{'id': 'sim', 'title': 'Sim'}, {'id': 'nao', 'title': 'Não'}],
    )


def handle(conversa, estado):
    step = estado.get('step')
    if step == DIARIO_CONFIRMAR:
        _handle_confirmar(conversa, estado)
    elif step == DIARIO_OBRA:
        _handle_obra(conversa, estado)
    elif step == DIARIO_COLETA:
        _handle_coleta(conversa, estado)


# ── passos ──────────────────────────────────────────────────────────────────
def _handle_confirmar(conversa, estado):
    if conversa.texto.lower() in ('sim', 'sim, continuar'):
        obras = _obras_do_funcionario(conversa.pessoa)
        _listar_obras(conversa, obras, pagina=1)
    else:
        conversa.responder("Ok, quando precisar é só chamar!")
        conversa.clear_state()


def _handle_obra(conversa, estado):
    body = conversa.texto
    if body == 'obra_mais':
        # A lista é determinística (ordenada por nome); recarrega e avança a página.
        obras = _obras_do_funcionario(conversa.pessoa)
        _listar_obras(conversa, obras, pagina=estado.get('pagina', 1) + 1)
        return
    if not body.startswith('obra'):
        conversa.responder("Por favor, selecione uma das obras da lista.")
        return
    try:
        obra_id = int(body.replace('obra', ''))
    except ValueError:
        conversa.responder("Por favor, selecione uma das obras da lista.")
        return

    obra = _obra_valida(conversa.pessoa, obra_id)
    if obra is None:
        conversa.responder("Obra não encontrada entre as suas. Selecione uma da lista.")
        return
    _iniciar_coleta(conversa, obra)


def _handle_coleta(conversa, estado):
    if conversa.texto.lower() == 'salvar':
        _salvar(conversa, estado)
        return

    texto = estado.get('texto', '')
    midias = list(estado.get('midias', []))
    if conversa.mensagem.get('body'):
        texto = (texto + '\n' + conversa.mensagem['body']).strip()
    if conversa.media_id:
        midias.append(conversa.media_id)

    conversa.set_state({**estado, 'texto': texto, 'midias': midias})
    conversa.responder("Conteúdo recebido. Envie mais ou digite 'salvar'.")


def _iniciar_coleta(conversa, obra):
    conversa.set_state({
        'flow': 'diario',
        'step': DIARIO_COLETA,
        'obra_id': obra.obra_id,
        'texto': '',
        'midias': [],
    })
    conversa.responder(
        f"📝 Diário de hoje para a obra \"{obra.nome_obra}\". Envie texto, fotos "
        "ou vídeos. Quando terminar, digite 'salvar' (ou 'sair' para cancelar)."
    )


def _salvar(conversa, estado):
    from modulodiario.services import registrar_contribuicao

    obra = _obra_valida(conversa.pessoa, estado.get('obra_id'))
    if obra is None:
        conversa.responder("Não foi possível localizar a obra. Operação cancelada.")
        conversa.clear_state()
        return

    texto = (estado.get('texto') or '').strip()
    midias = estado.get('midias', [])
    if not texto and not midias:
        conversa.responder("Nenhum conteúdo enviado. Envie texto/mídia e digite 'salvar', ou 'sair'.")
        return

    funcionario = conversa.pessoa
    criado_por = getattr(funcionario, 'usuario', None)

    if texto:
        registrar_contribuicao(
            obra=obra, funcionario=funcionario, texto=texto,
            origem='whatsapp', criado_por=criado_por, tenant_id=conversa.tenant_id,
        )

    enviadas = 0
    for media_id in midias:
        conteudo, mime = conversa.client.baixar_midia(media_id)
        if conteudo is None:
            continue
        ext = mimetypes.guess_extension(mime or '') or '.bin'
        arquivo = ContentFile(conteudo, name=f"whatsapp_{media_id}{ext}")
        registrar_contribuicao(
            obra=obra, funcionario=funcionario, arquivo=arquivo,
            descricao='Enviado pelo WhatsApp', origem='whatsapp',
            criado_por=criado_por, tenant_id=conversa.tenant_id,
        )
        enviadas += 1

    conversa.clear_state()
    if midias:
        conversa.responder(f"Diário salvo! {enviadas} de {len(midias)} arquivo(s) de mídia registrados.")
    else:
        conversa.responder("Diário salvo com sucesso!")


# ── consultas de obra (escopadas por tenant pela RLS da task) ───────────────
def _obras_do_funcionario(funcionario):
    from obras.models import Obra
    if funcionario is None:
        return []
    return list(
        Obra.objects
        .filter(Q(equipe=funcionario) | Q(responsaveis_tecnicos=funcionario))
        .distinct()
        .select_related('empreendimento')
        .order_by('nome_obra')
    )


def _obra_valida(funcionario, obra_id):
    if not obra_id:
        return None
    for obra in _obras_do_funcionario(funcionario):
        if obra.obra_id == obra_id:
            return obra
    return None


def _listar_obras(conversa, obras, pagina):
    inicio = (pagina - 1) * _POR_PAGINA
    fatia = obras[inicio:inicio + _POR_PAGINA]
    itens = [{
        'id': f"obra{o.obra_id}",
        'title': o.nome_obra,
        'description': o.empreendimento.nome_empreendimento if o.empreendimento else 'Sem empreendimento',
    } for o in fatia]
    if len(obras) > inicio + _POR_PAGINA:
        itens.append({'id': 'obra_mais', 'title': 'Mais opções'})

    conversa.set_state({
        'flow': 'diario',
        'step': DIARIO_OBRA,
        'pagina': pagina,
    })
    conversa.lista("Selecione a obra:", "Ver obras", itens)
