# backend/moduloscm/pagination.py
"""Paginação server-side do SCM.

Os listões (produtos, ofertas, demandas, pedidos…) crescem com o uso e os
selects de produto/fornecedor/centro de custo buscam server-side (padrão de
mercado: Coupa/Ariba/Nimbi não carregam o catálogo inteiro no cliente). Por
isso as listas do SCM paginam desde o início — fecha o F2 para este módulo em
vez de herdá-lo. As tabelas-filhas (itens de pedido/demanda/proposta), sempre
lidas por pai e pequenas, ficam sem paginação de propósito.
"""
from rest_framework.pagination import PageNumberPagination
from payment.planos import PAGINA_MAXIMA, PAGINA_PADRAO


class ScmPageNumberPagination(PageNumberPagination):
    page_size = PAGINA_PADRAO["scm"]
    page_size_query_param = "page_size"
    max_page_size = PAGINA_MAXIMA["scm"]
