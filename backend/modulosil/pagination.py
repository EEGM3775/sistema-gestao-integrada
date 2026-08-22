# backend/modulosil/pagination.py
from rest_framework.pagination import PageNumberPagination
from payment.planos import PAGINA_MAXIMA, PAGINA_PADRAO


class SilPageNumberPagination(PageNumberPagination):
    page_size = PAGINA_PADRAO["sil"]
    page_size_query_param = "page_size"
    max_page_size = PAGINA_MAXIMA["sil"]
