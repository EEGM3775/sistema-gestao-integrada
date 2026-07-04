# backend/moduloerp/pagination.py
"""
Paginação server-side dos listões financeiros do ERP (D.1.0 — fundação UI).

Os demais módulos do SGI ainda devolvem listas completas (aceitável para
dezenas de cadastros); o ERP lida com milhares de lançamentos, então a
paginação aqui é obrigatória — ver dívida registrada em docs/frontend.md
("Tabela client-side... trava com milhares de lançamentos").
"""
from rest_framework.pagination import PageNumberPagination


class ErpPageNumberPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 200
