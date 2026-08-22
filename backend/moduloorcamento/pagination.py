# backend/moduloorcamento/pagination.py
"""Paginação da base referencial. Obrigatória, não opcional: uma publicação do
SINAPI passa de 80 mil linhas — qualquer endpoint sem página aqui é um pedido de
timeout. Mesma régua do catálogo e do SCM."""
from rest_framework.pagination import PageNumberPagination
from payment.planos import PAGINA_MAXIMA, PAGINA_PADRAO


class OrcamentoPageNumberPagination(PageNumberPagination):
    page_size = PAGINA_PADRAO["orcamento"]
    page_size_query_param = "page_size"
    max_page_size = PAGINA_MAXIMA["orcamento"]
