# backend/moduloprancheta/pagination.py
"""Paginação da Prancheta. Mesma régua do catálogo/SCM/SIL/Maps.

`max_page_size` maior que o padrão porque o acervo de uma obra é lido de uma vez
pela tela de campo — paginar prancha em 25 linhas obrigaria o mestre de obras a
navegar página para achar o desenho que ele já sabe o nome. O teto continua
existindo: é o que impede um `page_size` absurdo derrubar o celular do canteiro.
"""
from rest_framework.pagination import PageNumberPagination
from payment.planos import PAGINA_MAXIMA, PAGINA_PADRAO


class PranchetaPageNumberPagination(PageNumberPagination):
    page_size = PAGINA_PADRAO["prancheta"]
    page_size_query_param = "page_size"
    max_page_size = PAGINA_MAXIMA["prancheta"]
