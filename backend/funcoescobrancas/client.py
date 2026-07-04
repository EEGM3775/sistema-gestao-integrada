# backend/funcoescobrancas/client.py
"""
Cliente HTTP do gateway Asaas — adapta o protocolo REST (sandbox ou real,
conforme `ASAAS_BASE_URL`/`ASAAS_API_KEY` do ambiente). Reaproveitável pelo
funcoesnf para emissão de NFS-e via Asaas (`invoices`), conforme o plano.

Credencial **global** nesta fase (uma conta sandbox para todos os tenants — ver
moduloerp.md §15); migrar para `IntegracaoAsaas` por tenant quando a gestão de
segredos da Fase 5 estiver pronta.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class AsaasAPIError(Exception):
    def __init__(self, message, status_code=None, payload=None):
        self.status_code = status_code
        self.payload = payload
        super().__init__(message)


class AsaasClient:
    def __init__(self, base_url=None, api_key=None):
        self.base_url = (base_url or settings.ASAAS_BASE_URL).rstrip('/')
        self.api_key = api_key or settings.ASAAS_API_KEY

    def _headers(self):
        return {
            'Content-Type': 'application/json',
            'access_token': self.api_key,
        }

    def _request(self, method, path, **kwargs):
        url = f"{self.base_url}{path}"
        response = requests.request(method, url, headers=self._headers(), timeout=20, **kwargs)
        try:
            corpo = response.json() if response.content else {}
        except ValueError:
            corpo = {}
        if not response.ok:
            erros = corpo.get('errors') if isinstance(corpo, dict) else None
            descricao = erros[0].get('description') if erros else response.text
            raise AsaasAPIError(
                f"Asaas respondeu {response.status_code}: {descricao}",
                status_code=response.status_code,
                payload=corpo,
            )
        return corpo

    # --- customers ---

    def buscar_customer_por_cpf_cnpj(self, cpf_cnpj):
        documento = ''.join(filter(str.isdigit, cpf_cnpj or ''))
        # Sem documento NÃO buscamos: `GET /customers?cpfCnpj=` faz o Asaas
        # ignorar o filtro vazio e devolver a conta inteira — pegar `dados[0]`
        # aí emite o boleto no primeiro customer qualquer (foi assim que uma
        # cobrança saiu no cadastro errado). Ver funcoescobrancas/services.py.
        if not documento:
            return None
        resultado = self._request('GET', '/customers', params={'cpfCnpj': documento})
        dados = resultado.get('data') or []
        # Defensivo: confirma que o customer retornado tem exatamente este
        # documento antes de considerá-lo um match (o filtro do Asaas é exato,
        # mas não delegamos a segurança da identidade a esse pressuposto).
        for candidato in dados:
            if ''.join(filter(str.isdigit, candidato.get('cpfCnpj') or '')) == documento:
                return candidato
        return None

    def listar_customers(self, *, offset=0, limit=100):
        return self._request('GET', '/customers', params={'offset': offset, 'limit': limit})

    def iterar_todos_customers(self, *, limit=100, max_paginas=200):
        """
        Percorre a conta Asaas inteira paginando `GET /customers` (uma varredura
        só, em vez de um GET por cliente). `max_paginas` é um teto de segurança
        contra loop infinito caso o gateway não sinalize o fim (`hasMore`).
        """
        offset = 0
        for _ in range(max_paginas):
            pagina = self.listar_customers(offset=offset, limit=limit)
            for customer in (pagina.get('data') or []):
                yield customer
            if not pagina.get('hasMore'):
                break
            offset += limit

    def criar_customer(self, *, nome, cpf_cnpj, email='', telefone='', endereco=None):
        payload = {
            'name': nome,
            'cpfCnpj': ''.join(filter(str.isdigit, cpf_cnpj or '')),
            'email': email,
            'mobilePhone': ''.join(filter(str.isdigit, telefone or '')),
        }
        if endereco:
            payload.update(endereco)
        return self._request('POST', '/customers', json=payload)

    # --- payments ---

    def criar_payment(self, *, customer_id, valor, vencimento, descricao='', billing_type='UNDEFINED', external_reference=None):
        payload = {
            'customer': customer_id,
            'billingType': billing_type,
            'value': float(valor),
            'dueDate': vencimento.isoformat() if hasattr(vencimento, 'isoformat') else vencimento,
            'description': descricao,
        }
        if external_reference is not None:
            payload['externalReference'] = str(external_reference)
        return self._request('POST', '/payments', json=payload)

    def buscar_payment(self, payment_id):
        return self._request('GET', f'/payments/{payment_id}')

    def cancelar_payment(self, payment_id):
        return self._request('DELETE', f'/payments/{payment_id}')

    def estornar_payment(self, payment_id, *, valor=None, descricao=''):
        payload = {}
        if valor is not None:
            payload['value'] = float(valor)
        if descricao:
            payload['description'] = descricao
        return self._request('POST', f'/payments/{payment_id}/refund', json=payload)
