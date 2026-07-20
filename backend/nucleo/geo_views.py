# backend/nucleo/geo_views.py
"""Endpoint HTTP fino sobre o serviço compartilhado `nucleo.geo`.

Existe para os consumidores que não rodam em Python no mesmo processo (o front
React, o drone em Java): os módulos Django devem importar `nucleo.geo` direto.
"""
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import geo


class ResolverEnderecoView(APIView):
    """`GET /api/geo/resolver/` → resolve cidade/UF/IBGE a partir de CEP e/ou nome.

    Query params (qualquer combinação): `cep`, `endereco` (texto livre),
    `cidade`, `uf`. Sem entitlement de módulo — utilitário base, só autenticado.
    Responde `{resultado: {...}}` ou `{resultado: null}` quando nada casa.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        resultado = geo.resolver(
            cep=request.query_params.get("cep"),
            endereco=request.query_params.get("endereco"),
            cidade=request.query_params.get("cidade"),
            uf=request.query_params.get("uf"),
        )
        return Response({"resultado": resultado})


class MunicipiosView(APIView):
    """`GET /api/geo/municipios/?uf=SP` → `[{ibge, nome}]` da UF (para o seletor de
    município que abre depois de escolher o estado). Só autenticado."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        uf = request.query_params.get("uf", "")
        return Response({"municipios": geo.listar_municipios(uf)})
