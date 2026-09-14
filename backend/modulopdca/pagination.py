# backend/modulopdca/pagination.py
"""Paginação do PDCA. Mesma régua do resto da casa — os dois lados do limite
vêm de `payment/planos.py`.

O `max_page_size` é 200 e não 100 por um motivo do domínio: a árvore de locais é
lida **inteira** por tela (o seletor de local do apontamento mostra a torre toda),
e paginar de 25 transformaria escolher um pavimento numa navegação de 8 páginas.
"""
from rest_framework.pagination import PageNumberPagination

from payment.planos import PAGINA_MAXIMA, PAGINA_PADRAO


class PdcaPageNumberPagination(PageNumberPagination):
    page_size = PAGINA_PADRAO["pdca"]
    page_size_query_param = "page_size"
    max_page_size = PAGINA_MAXIMA["pdca"]
