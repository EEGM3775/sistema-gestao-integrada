# backend/catalogo/pagination.py
"""Paginação server-side do catálogo — os selects de item (SCM/SIL) buscam
`?search=&page_size=` sem carregar o catálogo inteiro no cliente (padrão
Coupa/Ariba/Nimbi). Mesma régua da paginação do SCM."""
from rest_framework.pagination import PageNumberPagination
from payment.planos import PAGINA_MAXIMA, PAGINA_PADRAO


class CatalogoPageNumberPagination(PageNumberPagination):
    page_size = PAGINA_PADRAO["catalogo"]
    page_size_query_param = "page_size"
    max_page_size = PAGINA_MAXIMA["catalogo"]
