"""Paginação **sob pedido** dos cadastros que viram seletor.

Fornecedores, funcionários, obras e empreendimentos voltavam inteiros, e é assim
que as telas de lista de cada um os consomem (com busca e filtro locais). Os
formulários, porém, escolhem um deles pelo `SelectComBusca` da Malha, que busca
no servidor e rola de página em página até o último resultado — e para ele a
lista inteira é peso sem motivo.

Então a página só acontece **quando o cliente pede uma** (`?page=`): a lista de
tela segue recebendo tudo, como sempre recebeu, e o seletor recebe páginas. É o
contrário de uma paginação nova que cortaria em silêncio quem não a conhece — o
defeito que o F2 existiu para tirar dos formulários.
"""
from rest_framework.pagination import PageNumberPagination
from payment.planos import PAGINA_MAXIMA, PAGINA_PADRAO


class PaginaSobPedido(PageNumberPagination):
    page_size = PAGINA_PADRAO["cadastros"]
    page_size_query_param = "page_size"
    max_page_size = PAGINA_MAXIMA["cadastros"]

    def paginate_queryset(self, queryset, request, view=None):
        if self.page_query_param not in request.query_params:
            return None  # sem `?page=`: a lista inteira, como antes
        return super().paginate_queryset(queryset, request, view)
