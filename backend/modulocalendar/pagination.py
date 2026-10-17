"""Paginação do calendário — as pessoas do seletor de convidados e a busca de
eventos (Fatias D e E). Lista de escolha que rola infinita no `SelectComBusca`."""
from rest_framework.pagination import PageNumberPagination
from payment.planos import PAGINA_MAXIMA, PAGINA_PADRAO


class CalendarioPageNumberPagination(PageNumberPagination):
    page_size = PAGINA_PADRAO["calendario"]
    page_size_query_param = "page_size"
    max_page_size = PAGINA_MAXIMA["calendario"]
