# backend/nucleo/lixo_pagination.py
"""Paginação da lixeira. Mesma régua do resto da casa — os dois lados do limite
vêm de `payment/planos.py`.

**Não é detalhe cosmético.** Este projeto não tem `DEFAULT_PAGINATION_CLASS`
global: ViewSet sem paginador declarado devolve um **array puro**, e não o
envelope `{count, next, previous, results}`. A tela do lixo lia `results` e
recebia `undefined` — o painel dizia "1 na lixeira" (o `resumo/`, que é um objeto
e funcionava) e a tabela logo abaixo dizia "Nada na lixeira". O `resumo/` existe
justamente porque a lista é paginada; sem paginador, ele virava a única metade
certa de uma tela que se contradizia.
"""
from rest_framework.pagination import PageNumberPagination

from payment.planos import PAGINA_MAXIMA, PAGINA_PADRAO


class LixoPageNumberPagination(PageNumberPagination):
    page_size = PAGINA_PADRAO["lixo"]
    page_size_query_param = "page_size"
    max_page_size = PAGINA_MAXIMA["lixo"]
