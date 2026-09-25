"""
Testes da observabilidade (Fase 10.1): correlação de requisição, logging
estruturado, sondas de saúde e métricas.
"""
import json
import logging

from django.test import Client, TestCase

from nucleo import observability as obs


class RequestIdMiddlewareTests(TestCase):
    """O ObservabilityMiddleware estabelece e devolve o request_id."""

    def setUp(self):
        self.client = Client()

    def test_gera_request_id_quando_ausente(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        rid = resp.headers.get("X-Request-ID")
        self.assertTrue(rid)
        self.assertEqual(len(rid), 32)  # uuid4 hex

    def test_honra_request_id_recebido(self):
        resp = self.client.get("/healthz", HTTP_X_REQUEST_ID="abc-123-borda")
        self.assertEqual(resp.headers.get("X-Request-ID"), "abc-123-borda")

    def test_contexto_e_limpo_entre_requisicoes(self):
        # Após a resposta, o contextvar não vaza para a próxima requisição.
        self.client.get("/healthz", HTTP_X_REQUEST_ID="req-1")
        self.assertIsNone(obs.get_request_id())


class JsonLogFormatterTests(TestCase):
    """O formatter emite JSON de uma linha com o contexto de correlação."""

    def _record(self, **extra):
        return logging.LogRecord(
            name="sgi.test", level=logging.INFO, pathname=__file__, lineno=1,
            msg="ola %s", args=("mundo",), exc_info=None,
        )

    def test_formata_json_com_contexto(self):
        obs.set_request_id("rid-xyz")
        obs.set_tenant_id(42)
        try:
            record = self._record()
            obs.RequestContextFilter().filter(record)
            linha = obs.JsonLogFormatter().format(record)
        finally:
            obs.reset_request_context()

        payload = json.loads(linha)
        self.assertEqual(payload["msg"], "ola mundo")
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["request_id"], "rid-xyz")
        self.assertEqual(payload["tenant_id"], "42")

    def test_inclui_extras_estruturados(self):
        record = logging.LogRecord(
            name="sgi.access", level=logging.INFO, pathname=__file__, lineno=1,
            msg="GET /x", args=(), exc_info=None,
        )
        record.status = 500
        record.duration_ms = 12.3
        obs.RequestContextFilter().filter(record)
        payload = json.loads(obs.JsonLogFormatter().format(record))
        self.assertEqual(payload["status"], 500)
        self.assertEqual(payload["duration_ms"], 12.3)


class HealthEndpointsTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_healthz_e_liveness_sem_io(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_readyz_reporta_dependencias(self):
        resp = self.client.get("/readyz")
        # 200 (tudo up) ou 503 (Redis fora no ambiente de teste) — mas o banco,
        # que o teste comprovadamente usa, tem de estar "ok".
        self.assertIn(resp.status_code, (200, 503))
        checks = resp.json()["checks"]
        self.assertEqual(checks["database"], "ok")

    def test_metrics_responde(self):
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)


class MetricsHelperTests(TestCase):
    def test_observe_request_nao_quebra(self):
        # Deve ser no-op seguro mesmo sem prometheus_client instalado.
        obs.observe_request("erp", "GET", "cliente-list", 200, 0.01)

    def test_render_latest_metrics_retorna_bytes(self):
        body, content_type = obs.render_latest_metrics()
        self.assertIsInstance(body, bytes)
        self.assertTrue(content_type)
