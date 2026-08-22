# backend/modulomaps/pagination.py
"""Paginação do Maps. Mesma régua do catálogo/SCM/SIL.

`max_page_size` é maior aqui de propósito: o mapa da empresa desenha centenas
de pins de uma vez, e paginar o mapa em 25 pontos seria transformar visão de
território em lista. O teto continua existindo — é o que impede um `page_size`
de 50 mil derrubar o browser.
"""
from rest_framework.pagination import PageNumberPagination
from payment.planos import PAGINA_MAXIMA, PAGINA_PADRAO


class MapsPageNumberPagination(PageNumberPagination):
    page_size = PAGINA_PADRAO["maps"]
    page_size_query_param = "page_size"
    max_page_size = PAGINA_MAXIMA["maps"]
