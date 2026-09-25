"""A origem registrada é o IP REAL, não o que o cliente afirma ser.

O gateway não reescreve o `X-Forwarded-For` — ele **acrescenta** o IP real ao
que veio do cliente (`$proxy_add_x_forwarded_for`). Portanto o primeiro elemento
da cadeia é texto arbitrário do requisitante. Antes de 19/07/2026 era justamente
ele que ia para a trilha de segurança, o que permitia:

- **poluir a auditoria** — gravar um IP inventado no registro que existe para
  reconstituir incidente, incriminando outro endereço ou escondendo o próprio;
- **furar o teto por IP** — a mesma cadeia servia de chave do throttle no DRF,
  então trocar o valor falso a cada requisição dava um balde novo.

Estes testes fixam a regra: vale o endereço acrescentado pelo proxy confiável.
"""
from django.test import RequestFactory, TestCase, override_settings

from identity.recuperacao import _origem


class OrigemIpTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _req(self, xff=None, remote="172.18.0.1"):
        extra = {"REMOTE_ADDR": remote}
        if xff is not None:
            extra["HTTP_X_FORWARDED_FOR"] = xff
        return self.factory.post("/auth/senha/esqueci/", **extra)

    def test_usa_o_endereco_acrescentado_pelo_gateway(self):
        """Cadeia normal: `<cliente>, <proxy>` → vale o último (o real)."""
        ip, _ = _origem(self._req(xff="203.0.113.10"))
        self.assertEqual(ip, "203.0.113.10")

    def test_ignora_xff_forjado_pelo_cliente(self):
        """O cliente manda um IP falso; o gateway acrescenta o real ao final.
        O falso NÃO pode prevalecer — era o furo."""
        ip, _ = _origem(self._req(xff="1.2.3.4, 203.0.113.10"))
        self.assertEqual(ip, "203.0.113.10", "IP forjado pelo cliente prevaleceu")

    def test_cadeia_longa_forjada_nao_engana(self):
        """Encher a cadeia de lixo não muda o resultado."""
        ip, _ = _origem(self._req(xff="9.9.9.9, 8.8.8.8, 7.7.7.7, 203.0.113.10"))
        self.assertEqual(ip, "203.0.113.10")

    @override_settings(NUM_PROXIES=2)
    def test_respeita_dois_proxies_confiaveis(self):
        """Com CDN + gateway, o real é o penúltimo — o número tem de bater com a
        topologia real, senão volta a valer um endereço errado."""
        ip, _ = _origem(self._req(xff="1.2.3.4, 203.0.113.10, 10.0.0.5"))
        self.assertEqual(ip, "203.0.113.10")

    def test_sem_xff_usa_remote_addr(self):
        ip, _ = _origem(self._req(xff=None, remote="192.0.2.7"))
        self.assertEqual(ip, "192.0.2.7")

    def test_xff_vazio_nao_quebra(self):
        ip, _ = _origem(self._req(xff="   ", remote="192.0.2.7"))
        self.assertEqual(ip, "192.0.2.7")

    def test_sem_request_nao_quebra(self):
        self.assertEqual(_origem(None), (None, ""))
