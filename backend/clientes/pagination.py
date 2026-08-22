"""Paginação dos cadastros de cliente.

O listão de clientes devolvia a tabela inteira: com milhares de cadastros isso é
um JSON gigante por tecla digitada na busca. A grade da carteira consome páginas
grandes (rolagem infinita), daí o teto mais alto que o do ERP.
"""
from rest_framework.pagination import PageNumberPagination
from payment.planos import PAGINA_MAXIMA, PAGINA_PADRAO


class ClientePageNumberPagination(PageNumberPagination):
    page_size = PAGINA_PADRAO["clientes"]
    page_size_query_param = 'page_size'
    max_page_size = PAGINA_MAXIMA["clientes"]
