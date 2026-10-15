# backend/funcoesimpexp/relatorio.py
"""Relatório calculado só exporta — e exporta **os números da tela** (15/10/2026).

DRE, saldos intercompany, financeiro por obra: o cálculo mora numa view, e
refazê-lo aqui seria a segunda cópia que um dia diverge — a planilha somaria
diferente da tela que a pessoa acabou de ver. Então o recurso chama a própria
view com o recorte da tela e só achata a resposta em linhas (`linhas`).

O gate é o do recurso (`permissoes_exigidas`, as mesmas da view); a view é
chamada por dentro, sem a camada de permissão dela, que o motor já cobrou.
"""
from __future__ import annotations

from rest_framework.exceptions import ValidationError

from .cadastro import view_da_tela
from .registro import Recurso


class RecursoDeRelatorio(Recurso):
    #: A `APIView` da tela. Obrigatória.
    view = None

    def linhas(self, dados) -> list[dict]:
        """A resposta da view → uma linha (`campo -> valor`) por linha do arquivo."""
        raise NotImplementedError

    def queryset(self, request, recorte: dict):
        view = view_da_tela(self.view, request, recorte)
        resposta = view.get(view.request)
        if resposta.status_code >= 400:
            detalhe = getattr(resposta, "data", None) or {}
            raise ValidationError(detalhe.get("detail") if isinstance(detalhe, dict) else detalhe)
        return self.linhas(resposta.data)
