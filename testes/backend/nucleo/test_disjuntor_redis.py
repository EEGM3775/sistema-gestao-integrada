"""Fase 6 — o que o teste de caos achou: com o Redis fora, a API esperava o DNS.

A resolução do nome de um Redis parado não é limitada pelo `socket_timeout` e
custava ~4 s por tentativa. Cada requisição tentava várias vezes — a revogação,
o cache do PDP e os throttles (a cache do DRF engole o erro, então o fail-open
nunca via a falha) —, e o PEP, lento, acabava negando a sessão por não conseguir
perguntar à IAM. A regra da §10.8 é "Redis fora: mais lento, correto".

Aqui se cobra o disjuntor: aberto por um, vale para todos, e o throttle não toca
o Redis enquanto ele está aberto.
"""
import time
from unittest import mock

from django.test import SimpleTestCase
from rest_framework.throttling import SimpleRateThrottle

from nucleo import autorizacao_pdp, revocation, throttling


class DisjuntorCompartilhadoTests(SimpleTestCase):
    def setUp(self):
        self.addCleanup(self._fechar)
        self._fechar()

    def _fechar(self):
        autorizacao_pdp._redis_parado_ate = 0.0
        revocation._breaker_until = 0.0

    def test_a_revogacao_abre_o_do_pdp(self):
        revocation.abrir_disjuntor()
        self.assertTrue(autorizacao_pdp.redis_parado())
        self.assertIsNone(autorizacao_pdp.redis())

    def test_o_pdp_abre_o_da_revogacao(self):
        autorizacao_pdp.redis_caiu()
        self.assertTrue(revocation.disjuntor_aberto())

    def test_com_o_disjuntor_aberto_a_revogacao_nao_toca_o_redis(self):
        revocation.abrir_disjuntor()
        with mock.patch.object(revocation, "_redis", side_effect=AssertionError("tocou no Redis")):
            revocation.is_session_revoked("u1", int(time.time()))

    def test_o_throttle_nao_toca_o_redis_com_o_disjuntor_aberto(self):
        autorizacao_pdp.redis_caiu()
        th = throttling.UsuarioRateThrottle()
        with mock.patch.object(SimpleRateThrottle, "allow_request", side_effect=AssertionError("tocou")):
            self.assertTrue(th.allow_request(mock.Mock(), mock.Mock()))

    def test_fechado_o_throttle_trabalha(self):
        th = throttling.UsuarioRateThrottle()
        with mock.patch.object(SimpleRateThrottle, "allow_request", return_value=False) as chamado:
            self.assertFalse(th.allow_request(mock.Mock(), mock.Mock()))
        chamado.assert_called_once()
