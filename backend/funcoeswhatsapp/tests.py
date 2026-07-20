"""
Testes da absorção do microsserviço Node `funcoeswhatsapp` (Fase 11.3 / Fase C).

Cobrem a borda (parsing do payload da Meta, assinatura HMAC, webhook GET/POST,
idempotência), a identidade telefone→pessoa tenant-scoped, o serviço único de
escrita do diário e as transições dos fluxos (diário e lead) com o cliente de
saída da Meta mockado.
"""
import hashlib
import hmac
import json
import types
from datetime import date
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from nucleo.models import Tenant
from nucleo.tenancy import tenant_context
from obras.models import Obra
from rh.models import Funcionario

from . import state
from .conversa import Conversa
from .identity import identificar, ROLE_FUNCIONARIO, ROLE_UNKNOWN
from .payload import extrair_mensagem, extrair_phone_number_id, sanitizar_payload
from .security import assinatura_valida

_LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


def _funcionario(tenant, **kw):
    """Cria um Funcionario com os campos NOT NULL mínimos preenchidos."""
    dados = dict(
        tenant=tenant, nome_completo='Fulano de Tal', cpf='11144477735',
        data_nascimento=date(1990, 1, 1), genero='masculino',
        endereco_completo='Rua 1, 100', data_admissao=date(2020, 1, 1),
        salario_base=2000,
    )
    dados.update(kw)
    return Funcionario.objects.create(**dados)


def _payload(pnid, from_num='5575988887777', *, text='oi', mtype='text', mid=None):
    msg = {'id': 'wamid.TESTE', 'from': from_num, 'type': mtype}
    if mtype == 'text':
        msg['text'] = {'body': text}
    elif mtype == 'interactive':
        msg['interactive'] = {'type': 'button_reply', 'button_reply': {'id': text, 'title': 'X'}}
    elif mtype in ('image', 'video', 'audio', 'document'):
        msg[mtype] = {'id': mid or 'media-1'}
    return {
        'object': 'whatsapp_business_account',
        'entry': [{'changes': [{'value': {
            'metadata': {'phone_number_id': pnid},
            'messages': [msg],
        }}]}],
    }


class FakeClient:
    """Cliente de saída da Meta mockado: só registra o que foi enviado."""
    def __init__(self):
        self.enviados = []

    def enviar_texto(self, to, texto):
        self.enviados.append(('texto', texto))

    def enviar_botoes(self, to, texto, botoes):
        self.enviados.append(('botoes', texto, botoes))

    def enviar_lista(self, to, texto, texto_botao, itens):
        self.enviados.append(('lista', texto, itens))

    def baixar_midia(self, media_id):
        return None, None


# ── Borda: payload + assinatura ─────────────────────────────────────────────
class PayloadTests(TestCase):
    def test_extrai_phone_number_id(self):
        self.assertEqual(extrair_phone_number_id(_payload('PNID1')), 'PNID1')
        self.assertIsNone(extrair_phone_number_id({'foo': 'bar'}))

    def test_texto(self):
        msg = extrair_mensagem(_payload('P', text='  Olá  '))
        self.assertEqual(msg['type'], 'text')
        self.assertEqual(msg['body'], 'Olá')
        self.assertIsNone(msg['media_id'])

    def test_interactive_vira_id_do_botao(self):
        msg = extrair_mensagem(_payload('P', text='sim', mtype='interactive'))
        self.assertEqual(msg['body'], 'sim')

    def test_midia(self):
        msg = extrair_mensagem(_payload('P', mtype='image', mid='m9'))
        self.assertEqual(msg['media_id'], 'm9')
        self.assertEqual(msg['body'], '')

    def test_status_sem_messages_e_none(self):
        env = {'entry': [{'changes': [{'value': {'statuses': [{'id': 'x'}]}}]}]}
        self.assertIsNone(extrair_mensagem(env))

    def test_sanitiza_remove_pii(self):
        seguro = sanitizar_payload(_payload('P', from_num='5575999998888', text='segredo'))
        msg = seguro['entry'][0]['changes'][0]['value']['messages'][0]
        self.assertEqual(msg['from'], '...8888')
        self.assertEqual(msg['text']['body'], '[CONTEÚDO REMOVIDO]')


class SecurityTests(TestCase):
    def test_assinatura_valida_e_invalida(self):
        segredo = 'app-secret'
        corpo = b'{"a":1}'
        bom = 'sha256=' + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
        self.assertTrue(assinatura_valida(segredo, corpo, bom))
        self.assertFalse(assinatura_valida(segredo, corpo, 'sha256=deadbeef'))
        self.assertFalse(assinatura_valida(segredo, corpo, ''))
        self.assertFalse(assinatura_valida('', corpo, bom))


# ── Webhook (view) ──────────────────────────────────────────────────────────
@override_settings(CACHES=_LOCMEM)
class WebhookViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug='wa-a', nome='WA A')
        from .models import CanalWhatsApp
        cls.canal = CanalWhatsApp.objects.create(
            tenant=cls.tenant, phone_number_id='PNID-A',
            app_secret='segredo-a', verify_token='verify-a', access_token='tok',
        )

    def setUp(self):
        cache.clear()
        self.client = Client()

    def _assinar(self, corpo, segredo='segredo-a'):
        return 'sha256=' + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()

    def test_get_handshake_ok(self):
        resp = self.client.get('/webhooks/whatsapp', {
            'hub.mode': 'subscribe', 'hub.verify_token': 'verify-a',
            'hub.challenge': 'DESAFIO', 'phone_number_id': 'PNID-A',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content.decode(), 'DESAFIO')

    def test_get_handshake_token_errado_403(self):
        resp = self.client.get('/webhooks/whatsapp', {
            'hub.mode': 'subscribe', 'hub.verify_token': 'errado',
            'hub.challenge': 'X', 'phone_number_id': 'PNID-A',
        })
        self.assertEqual(resp.status_code, 403)

    @patch('funcoeswhatsapp.tasks.processar_mensagem_whatsapp.delay')
    def test_post_valido_enfileira(self, mock_delay):
        corpo = json.dumps(_payload('PNID-A')).encode()
        resp = self.client.post(
            '/webhooks/whatsapp', data=corpo, content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=self._assinar(corpo),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(mock_delay.called)
        args = mock_delay.call_args.args
        self.assertEqual(args[0], 'PNID-A')
        self.assertEqual(args[1]['from'], '5575988887777')

    @patch('funcoeswhatsapp.tasks.processar_mensagem_whatsapp.delay')
    def test_post_assinatura_invalida_403(self, mock_delay):
        corpo = json.dumps(_payload('PNID-A')).encode()
        resp = self.client.post(
            '/webhooks/whatsapp', data=corpo, content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256='sha256=falso',
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(mock_delay.called)

    @patch('funcoeswhatsapp.tasks.processar_mensagem_whatsapp.delay')
    def test_post_numero_desconhecido_descarta_200(self, mock_delay):
        corpo = json.dumps(_payload('PNID-DESCONHECIDO')).encode()
        resp = self.client.post(
            '/webhooks/whatsapp', data=corpo, content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=self._assinar(corpo),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(mock_delay.called)

    @patch('funcoeswhatsapp.tasks.processar_mensagem_whatsapp.delay')
    def test_post_idempotente_ignora_repeticao(self, mock_delay):
        corpo = json.dumps(_payload('PNID-A')).encode()
        sig = self._assinar(corpo)
        r1 = self.client.post('/webhooks/whatsapp', data=corpo, content_type='application/json', HTTP_X_HUB_SIGNATURE_256=sig)
        r2 = self.client.post('/webhooks/whatsapp', data=corpo, content_type='application/json', HTTP_X_HUB_SIGNATURE_256=sig)
        self.assertEqual((r1.status_code, r2.status_code), (200, 200))
        self.assertEqual(mock_delay.call_count, 1)  # a 2ª (mesmo message.id) não enfileira


# ── Identidade telefone → pessoa (tenant-scoped) ────────────────────────────
class IdentityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug='id-a', nome='ID A')
        cls.func = _funcionario(
            cls.tenant, nome_completo='João da Obra',
            telefone_celular='+55 (75) 98888-7777',
        )

    def test_funcionario_por_celular_ignorando_mais_e_pontuacao(self):
        with tenant_context(self.tenant.id):
            pessoa, role = identificar('5575988887777')
        self.assertEqual(role, ROLE_FUNCIONARIO)
        self.assertEqual(pessoa.pk, self.func.pk)

    def test_numero_desconhecido(self):
        with tenant_context(self.tenant.id):
            pessoa, role = identificar('5511000000000')
        self.assertIsNone(pessoa)
        self.assertEqual(role, ROLE_UNKNOWN)


# ── Serviço único de escrita do diário ──────────────────────────────────────
class RegistrarContribuicaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug='svc-a', nome='SVC A')
        cls.obra = Obra.objects.create(tenant=cls.tenant, nome_obra='Obra Serviço')
        cls.func = _funcionario(cls.tenant, nome_completo='Maria')

    @patch('modulodiario.tasks.disparar_analise_ia.delay')
    def test_texto_cria_diario_e_entrada_sem_ia(self, mock_ia):
        from modulodiario.services import registrar_contribuicao
        from modulodiario.models import DiarioObra, EntradaDiario

        diario = registrar_contribuicao(
            obra=self.obra, funcionario=self.func, texto='Concretagem ok',
            origem='whatsapp', tenant_id=self.tenant.id,
        )
        self.assertEqual(DiarioObra.objects.filter(obra=self.obra, data=date.today()).count(), 1)
        entrada = EntradaDiario.objects.get(diario_obra=diario)
        self.assertEqual(entrada.origem, 'whatsapp')
        self.assertEqual(entrada.autor, self.func)
        self.assertEqual(entrada.tenant_id, self.tenant.id)
        self.assertFalse(mock_ia.called)  # texto não dispara IA

    @patch('modulodiario.tasks.disparar_analise_ia.delay')
    def test_reusa_diario_do_dia(self, mock_ia):
        from modulodiario.services import registrar_contribuicao
        from modulodiario.models import DiarioObra

        registrar_contribuicao(obra=self.obra, funcionario=self.func, texto='a', tenant_id=self.tenant.id)
        registrar_contribuicao(obra=self.obra, funcionario=self.func, texto='b', tenant_id=self.tenant.id)
        self.assertEqual(DiarioObra.objects.filter(obra=self.obra, data=date.today()).count(), 1)


# ── Fluxos (cliente mockado, cache locmem) ──────────────────────────────────
@override_settings(CACHES=_LOCMEM)
class LeadFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug='lead-a', nome='LEAD A')

    def setUp(self):
        cache.clear()
        self.client_wa = FakeClient()
        self.canal = types.SimpleNamespace(tenant_id=self.tenant.id)

    def _conversa(self, body):
        return Conversa(
            canal=self.canal, client=self.client_wa, telefone='5511999990000',
            mensagem={'body': body, 'media_id': None}, pessoa=None, role=ROLE_UNKNOWN,
        )

    def test_precadastro_cria_lead_pontuado(self):
        from .flows import lead
        from modulocrm.models import Lead

        with tenant_context(self.tenant.id):
            lead.start(self._conversa('oi, quero informações'))
            estado = state.get_state(self.tenant.id, '5511999990000')
            lead.handle(self._conversa('Ana Paula Souza'), estado)
            estado = state.get_state(self.tenant.id, '5511999990000')
            lead.handle(self._conversa('cliente'), estado)

        leads = Lead.objects.filter(tenant=self.tenant)
        self.assertEqual(leads.count(), 1)
        novo = leads.first()
        self.assertEqual(novo.first_name, 'Ana')
        self.assertEqual(novo.last_name, 'Paula Souza')
        self.assertIn('WhatsApp', novo.source)
        self.assertIsNone(state.get_state(self.tenant.id, '5511999990000'))  # sessão encerrada


@override_settings(CACHES=_LOCMEM)
class DiarioFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug='dia-a', nome='DIA A')
        cls.obra = Obra.objects.create(tenant=cls.tenant, nome_obra='Obra Única')
        cls.func = _funcionario(cls.tenant, nome_completo='Pedro Alvares')
        cls.obra.equipe.add(cls.func)

    def setUp(self):
        cache.clear()
        self.client_wa = FakeClient()
        self.canal = types.SimpleNamespace(tenant_id=self.tenant.id)

    def _conversa(self, body):
        return Conversa(
            canal=self.canal, client=self.client_wa, telefone='5575988887777',
            mensagem={'body': body, 'media_id': None}, pessoa=self.func, role=ROLE_FUNCIONARIO,
        )

    @patch('modulodiario.tasks.disparar_analise_ia.delay')
    def test_obra_unica_coleta_e_salva(self, mock_ia):
        from .flows import diario
        from .steps import DIARIO_COLETA
        from modulodiario.models import DiarioObra, EntradaDiario

        with tenant_context(self.tenant.id):
            # 1 obra → pula direto para a coleta
            diario.start(self._conversa('diario'))
            estado = state.get_state(self.tenant.id, '5575988887777')
            self.assertEqual(estado['step'], DIARIO_COLETA)
            self.assertEqual(estado['obra_id'], self.obra.obra_id)

            # coleta de texto
            diario.handle(self._conversa('Fundação concluída'), estado)
            estado = state.get_state(self.tenant.id, '5575988887777')

            # salvar
            diario.handle(self._conversa('salvar'), estado)

        diarios = DiarioObra.objects.filter(obra=self.obra, data=date.today())
        self.assertEqual(diarios.count(), 1)
        entrada = EntradaDiario.objects.get(diario_obra=diarios.first())
        self.assertEqual(entrada.origem, 'whatsapp')
        self.assertIn('Fundação concluída', entrada.texto)
        self.assertIsNone(state.get_state(self.tenant.id, '5575988887777'))  # sessão encerrada
