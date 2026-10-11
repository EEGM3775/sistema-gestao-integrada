# backend/moduloerp/nfe_client.py
"""
Cliente REST da NFE.io — emissão/consulta de NFS-e (Fase 11.1).

Absorve o microsserviço Node `funcoesnf` (+ o bridge PHP `NotaFiscalManager`):
em vez de o backend chamar o Node por HTTP (com o `Token` legado que hoje devolve
401 — achado **D1**), a Celery task Python (`moduloerp.tasks`) fala REST direto
com a NFE.io usando este cliente.

Wrapper fino e testável (mockável): não conhece Celery nem o ORM. Erros são
tipados para o worker decidir entre **retry** (indisponibilidade transitória:
rede/timeout/5xx) e **erro permanente** (4xx/negócio — repetir não ajuda).

Contrato REST (o mesmo que o bridge PHP usava — `api.nfe.io/v1`):
  - emitir  : POST   /companies/{companyId}/serviceinvoices
  - consultar: GET   /companies/{companyId}/serviceinvoices/{invoiceId}
  - cancelar : DELETE /companies/{companyId}/serviceinvoices/{invoiceId}
Autenticação por header `Authorization: <api_key>` (a chave crua, não Bearer).
"""
import logging

import requests
from django.conf import settings

from nucleo.rate_limit import consumir

logger = logging.getLogger(__name__)


class NFeIndisponivel(Exception):
    """Falha transitória (rede/timeout/5xx/credencial ausente) — vale repetir."""


class NFeErro(Exception):
    """Erro permanente (4xx/negócio da NFE.io) — repetir não ajuda.

    Carrega o corpo cru da resposta (`payload`) e o `status_code` quando o erro
    veio da API — é o que a UI abre no popup de "detalhes do erro" (códigos e
    mensagens que a NFE.io devolveu), em vez de só uma frase.
    """

    def __init__(self, message, *, status_code=None, payload=None):
        self.status_code = status_code
        self.payload = payload
        super().__init__(message)


def _extrair_dados(invoice):
    """Normaliza a resposta da NFE.io no shape consumido pela task/model.

    A NFE.io ora expõe os arquivos em `links: [{rel, href}]` (resposta de
    criação), ora em campos `urlPdf`/`urlXml` — cobrimos os dois defensivamente.
    """
    if not isinstance(invoice, dict):
        raise NFeErro(f"resposta da NFE.io não é um objeto JSON (tipo {type(invoice).__name__})")

    def _link(rel):
        for link in (invoice.get('links') or []):
            if isinstance(link, dict) and link.get('rel') == rel:
                return link.get('href')
        return None

    return {
        'nfe_io_id': invoice.get('id'),
        'status': invoice.get('status'),          # string crua da NFE.io (Issued/Cancelled/Error/Waiting*)
        'numero': invoice.get('number'),
        'chave_acesso': invoice.get('accessKey') or invoice.get('checkCode'),
        'data_emissao': invoice.get('issuedOn') or invoice.get('createdOn'),
        'data_cancelamento': invoice.get('cancelledOn') or invoice.get('cancelledOnUtc'),
        'url_pdf': invoice.get('urlPdf') or _link('pdf'),
        'url_xml': invoice.get('urlXml') or _link('xml'),
        'full_response': invoice,
    }


def montar_payload_nfse(*, city_service_code, description, services_amount, borrower_data):
    """Monta o payload de emissão de NFS-e a partir do snapshot da NF.

    `borrower_data` é o snapshot do tomador gravado na NF (ver
    `_dados_cliente_para_nf`). Mantém o contrato que o `emitirNF.js` usava.
    Levanta `NFeErro` se faltar dado essencial do tomador (CPF/CNPJ, CEP, IBGE).
    """
    borrower_data = borrower_data or {}
    cpf_cnpj = ''.join(filter(str.isdigit, borrower_data.get('cpf_cnpj') or ''))
    cidade_ibge = borrower_data.get('cidade_ibge')
    cep = ''.join(filter(str.isdigit, borrower_data.get('cep') or ''))

    if not cpf_cnpj or not cep or not cidade_ibge:
        raise NFeErro(
            "Dados insuficientes do tomador para emissão (CPF/CNPJ, CEP ou código IBGE da cidade)."
        )

    borrower_type = 'LegalEntity' if len(cpf_cnpj) > 11 else 'NaturalPerson'
    estado = (borrower_data.get('estado') or '').upper()

    return {
        'cityServiceCode': city_service_code,
        'description': description,
        'servicesAmount': float(services_amount),
        'borrower': {
            'type': borrower_type,
            'federalTaxNumber': int(cpf_cnpj),
            'name': borrower_data.get('nome_completo') or borrower_data.get('razao_social') or '',
            'email': borrower_data.get('email') or '',
            'address': {
                'country': 'BRA',
                'postalCode': cep,
                'street': borrower_data.get('endereco') or '',
                'number': borrower_data.get('numero_endereco') or 'S/N',
                'additionalInformation': borrower_data.get('complemento_endereco') or '',
                'district': borrower_data.get('bairro') or '',
                'city': {'code': cidade_ibge, 'name': borrower_data.get('cidade') or ''},
                'state': estado,
            },
        },
    }


class NFeClient:
    """Adapta o protocolo REST da NFE.io. Credencial global (settings)."""

    def __init__(self, base_url=None, api_key=None, company_id=None):
        self.base_url = (base_url or settings.NFE_IO_BASE_URL).rstrip('/')
        self.api_key = api_key or settings.NFE_IO_API_KEY
        self.company_id = company_id or settings.NFE_IO_COMPANY_ID

    def _headers(self):
        return {'Authorization': self.api_key, 'Content-Type': 'application/json'}

    def _request(self, method, path, **kwargs):
        if not self.api_key or not self.company_id:
            # Sem credencial não há como emitir; trata como indisponibilidade
            # para não perder o pedido silenciosamente (o worker faz retry/DLQ).
            raise NFeIndisponivel("Credenciais da NFE.io ausentes (NFE_IO_API_KEY/NFE_IO_COMPANY_ID).")

        # Camada 2 (docs/arquitetura/rate-limiting.md): um token por CHAMADA real
        # à NFE.io. É aqui que o lote de fechamento e os retries entram na conta —
        # na view, `emitir-lote` conta como 1 pedido e emite N notas.
        # Levanta LimiteFornecedorExcedido, que a task converte em `retry`.
        consumir('nfe_io')

        url = f"{self.base_url}{path}"
        try:
            response = requests.request(
                method, url, headers=self._headers(),
                timeout=getattr(settings, 'NFE_IO_TIMEOUT', (5, 30)), **kwargs,
            )
        except requests.RequestException as exc:
            raise NFeIndisponivel(str(exc)) from exc

        try:
            corpo = response.json() if response.content else {}
        except ValueError:
            corpo = {}

        if response.status_code >= 500:
            raise NFeIndisponivel(f"NFE.io respondeu {response.status_code}: {response.text[:200]}")
        if not response.ok:
            # 4xx: erro de dados/negócio — permanente. Preserva o corpo cru
            # (`payload`) para a UI listar todos os códigos/mensagens da NFE.io.
            descricao = corpo.get('message') if isinstance(corpo, dict) else None
            raise NFeErro(
                f"NFE.io respondeu {response.status_code}: {descricao or response.text[:200]}",
                status_code=response.status_code,
                payload=corpo or {'raw': response.text[:500]},
            )
        return corpo

    def _company_path(self, suffix=''):
        return f"/companies/{self.company_id}/serviceinvoices{suffix}"

    def emitir_nfse(self, payload):
        """Emite uma NFS-e. Devolve o dict normalizado (`_extrair_dados`)."""
        invoice = self._request('POST', self._company_path(), json=payload)
        return _extrair_dados(invoice)

    def consultar_nfse(self, invoice_id):
        """Consulta o status de uma NFS-e pelo id da NFE.io."""
        invoice = self._request('GET', self._company_path(f'/{invoice_id}'))
        return _extrair_dados(invoice)

    def resolver_url_arquivo(self, invoice_id, tipo):
        """Resolve o link público (assinado) do PDF/XML de uma NFS-e emitida.

        A NFE.io não devolve o link no corpo do invoice: os arquivos vêm dos
        endpoints `/serviceinvoices/{id}/pdf|xml`, que respondem **302** para um
        blob assinado (baixável sem auth). Retorna esse `Location`, ou `None` se
        indisponível. `tipo` ∈ {"pdf", "xml"}.
        """
        if not self.api_key or not self.company_id:
            return None
        url = f"{self.base_url}{self._company_path(f'/{invoice_id}/{tipo}')}"
        try:
            resp = requests.get(
                url, headers=self._headers(), allow_redirects=False,
                timeout=getattr(settings, 'NFE_IO_TIMEOUT', (5, 30)),
            )
        except requests.RequestException:
            return None
        if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
            return resp.headers.get('Location')
        return None

    def cancelar_nfse(self, invoice_id):
        """Cancela uma NFS-e emitida pelo id da NFE.io."""
        invoice = self._request('DELETE', self._company_path(f'/{invoice_id}'))
        return _extrair_dados(invoice)


def cliente_do_tenant(tenant_id) -> NFeClient:
    """O cliente com a conta **desta empresa** na NFE.io, se ela cadastrou uma;
    senão o da conta do ambiente. Lido dentro do contexto do tenant (RLS)."""
    from nucleo.tenancy import tenant_context

    from .models import IntegracaoFiscal

    with tenant_context(tenant_id):
        cadastro = IntegracaoFiscal.objects.filter(tenant_id=tenant_id).first()
    if cadastro is not None and cadastro.api_key and cadastro.company_id:
        return NFeClient(api_key=cadastro.api_key, company_id=cadastro.company_id)
    return NFeClient()
