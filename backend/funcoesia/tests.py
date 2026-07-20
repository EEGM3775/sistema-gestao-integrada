"""
Testes da absorção do microsserviço Node `funcoesia` (Fase 11.3).

A análise de imagem virou uma Celery task Python (`analisar_documento_ia`) que
lê a imagem do documento in-process e chama a LLM de visão local. Estes testes
cobrem o worker (sucesso, resposta inválida, documento inexistente) e o cliente
HTTP da LLM (`llm_client`), com o boundary da LLM mockado.
"""
from datetime import date
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from obras.models import Obra
from nucleo.models import Tenant
from modulodiario.models import DiarioObra, DocumentoDiario
from .models import AnaliseImagemIA
from .llm_client import analisar_imagem, LLMIndisponivel, LLMResultadoInvalido
from .tasks import analisar_documento_ia

# 1x1 GIF válido — corpo mínimo para o FileField.
_GIF_1PX = (
    b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
    b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
)


class AnaliseWorkerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(slug="ia-a", nome="IA A")
        cls.obra = Obra.objects.create(
            tenant=cls.tenant, nome_obra="Obra IA", endereco="Rua 1",
        )
        cls.diario = DiarioObra.objects.create(
            tenant=cls.tenant, obra=cls.obra, data=date.today(),
        )

    def _documento(self):
        return DocumentoDiario.objects.create(
            tenant=self.tenant, diario_obra=self.diario, origem='whatsapp',
            arquivo=SimpleUploadedFile("foto.gif", _GIF_1PX, content_type="image/gif"),
        )

    @patch('funcoesia.tasks.analisar_imagem')
    def test_sucesso_grava_resultado_concluido(self, mock_llm):
        mock_llm.return_value = {'resumo': 'parede erguida', 'confianca': 0.9}
        doc = self._documento()

        analisar_documento_ia.apply(kwargs={'documento_id': doc.pk, 'tipo_analise': 'completa'})

        analise = AnaliseImagemIA.objects.get(documento_id=doc.pk)
        self.assertEqual(analise.status, 'concluido')
        self.assertEqual(analise.resultado_analise['resumo'], 'parede erguida')
        self.assertEqual(analise.tenant_id, self.tenant.id)
        # A imagem foi lida in-process e repassada à LLM (sem HTTP de download).
        self.assertTrue(mock_llm.called)
        (image_bytes, mime_type, tipo), _ = mock_llm.call_args
        self.assertEqual(image_bytes, _GIF_1PX)
        self.assertEqual(mime_type, 'image/gif')
        self.assertEqual(tipo, 'completa')

    @patch('funcoesia.tasks.analisar_imagem')
    def test_resposta_invalida_marca_erro(self, mock_llm):
        mock_llm.side_effect = LLMResultadoInvalido("resposta não é objeto JSON")
        doc = self._documento()

        analisar_documento_ia.apply(kwargs={'documento_id': doc.pk})

        analise = AnaliseImagemIA.objects.get(documento_id=doc.pk)
        self.assertEqual(analise.status, 'erro')
        self.assertIn('inválido', analise.resultado_analise['erro'])

    @patch('funcoesia.tasks.analisar_imagem')
    def test_documento_inexistente_e_noop(self, mock_llm):
        analisar_documento_ia.apply(kwargs={'documento_id': 999999})
        self.assertFalse(mock_llm.called)
        self.assertEqual(AnaliseImagemIA.objects.count(), 0)


class LlmClientTests(TestCase):
    @override_settings(LLM_VISION_URL='')
    def test_sem_url_e_indisponivel(self):
        with self.assertRaises(LLMIndisponivel):
            analisar_imagem(b'x', 'image/gif', 'completa')

    @override_settings(LLM_VISION_URL='http://llm.local/analise', IA_SERVICE_SECRET_TOKEN='t')
    @patch('funcoesia.llm_client.requests')
    def test_resposta_nao_dict_e_invalida(self, mock_requests):
        resp = MagicMock()
        resp.json.return_value = ['isto', 'não', 'é', 'objeto']
        mock_requests.post.return_value = resp
        mock_requests.RequestException = Exception
        with self.assertRaises(LLMResultadoInvalido):
            analisar_imagem(b'x', 'image/gif', 'completa')

    @override_settings(LLM_VISION_URL='http://llm.local/analise', IA_SERVICE_SECRET_TOKEN='t')
    @patch('funcoesia.llm_client.requests')
    def test_sucesso_carimba_tipo_ausente(self, mock_requests):
        resp = MagicMock()
        resp.json.return_value = {'resumo': 'ok'}
        mock_requests.post.return_value = resp
        mock_requests.RequestException = Exception
        resultado = analisar_imagem(b'x', 'image/gif', 'seguranca_obra')
        self.assertEqual(resultado['tipo_analise'], 'seguranca_obra')
        self.assertEqual(resultado['resumo'], 'ok')
