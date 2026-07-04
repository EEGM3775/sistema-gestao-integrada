"""
Confirmação do achado D1: o ERP rejeita o `Authorization: Token …` legado que
os microsserviços Node (funcoesia/funcoesnf/funcoeswhatsapp) ainda enviam —
todo callback Node→ERP morre com 401 até a absorção em Python (Fase 11) ou o
JWT de serviço (Fase 10.8).
"""
from rest_framework.test import APITestCase


class TokenLegadoRejeitadoTests(APITestCase):
    def test_callbacks_node_para_erp_recebem_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token token-legado-de-servico")
        casos = [
            ("get", "/api/clientes/"),                  # funcoeswhatsapp: identificação por telefone
            ("get", "/api/crm/interactions/"),          # funcoeslead (já absorvido — Fase 11.2)
            ("post", "/api/erp/atualizar-status-nf/"),  # funcoesnf: callback de status de NF
            ("post", "/api/log-interno/"),              # todos: log central de microsserviços
        ]
        for metodo, url in casos:
            with self.subTest(url=url):
                resp = getattr(self.client, metodo)(url, {}, format="json")
                self.assertEqual(resp.status_code, 401)
