# backend/catalogo/pagination.py
"""Paginação server-side do catálogo — os selects de item (SCM/SIL) buscam
`?search=&page_size=` sem carregar o catálogo inteiro no cliente (padrão
Coupa/Ariba/Nimbi). Mesma régua da paginação do SCM."""
from rest_framework.pagination import PageNumberPagination


class CatalogoPageNumberPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
