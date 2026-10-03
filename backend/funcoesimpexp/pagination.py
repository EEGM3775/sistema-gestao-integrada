# backend/funcoesimpexp/pagination.py
"""Tamanho de página do registro de arquivos do DMS (`ArquivosView`).

O registro junta várias fontes e corta depois de ordenar, então não usa o
`paginate_queryset`; usa só o `get_page_size`, que é o que lê o padrão e o
teto do `payment/planos.py` e respeita o `?page_size=` dentro dele.
"""
from rest_framework.pagination import PageNumberPagination

from payment.planos import PAGINA_MAXIMA, PAGINA_PADRAO


class DmsPageNumberPagination(PageNumberPagination):
    page_size = PAGINA_PADRAO["dms"]
    page_size_query_param = "page_size"
    max_page_size = PAGINA_MAXIMA["dms"]
