"""A IAM reconhece o navegador pelo cookie da sessão (fase 5, §10.5).

A IAM é o BFF: ela não precisa trocar o cookie por um token para falar com ela
mesma. `/auth/me/`, a tela de segurança da conta e a administração de papéis
(`/iam/...`) autenticam direto pela credencial do cookie, com a mesma regra de
escrita do gateway (`bff.escrita_legitima`). O `Authorization: Bearer` continua
aceito depois deste — para `aud` `sgi-iam` e `typ` `at+jwt` (`TokenDaIam`).
"""
from __future__ import annotations

import jwt
from django.conf import settings
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from funcoesautorizacao import audiencias

from . import bff, sessoes


class SessaoDoNavegador(BaseAuthentication):
    def authenticate(self, request):
        credencial = request.COOKIES.get(settings.SESSAO_COOKIE_NAME)
        if not credencial:
            return None
        sessao = sessoes.pela_credencial(credencial)
        if sessao is None:
            return None  # cookie vencido ou revogado: anônimo, e a view decide
        if not bff.escrita_legitima(request.method, request.headers, request.get_host()):
            raise exceptions.PermissionDenied("Escrita sem o cabeçalho anti-CSRF ou de outra origem.")
        return sessao.usuario, sessao

    def authenticate_header(self, request):
        # Primeiro da lista: é ele que decide o 401 (e não 403) do não autenticado.
        return 'Bearer realm="sgi-iam"'


class TokenDaIam(JWTAuthentication):
    """O Bearer que a IAM aceita: emitido para ela, do tipo de pessoa."""

    def get_validated_token(self, raw_token):
        try:
            tipo = jwt.get_unverified_header(raw_token).get("typ")
        except jwt.PyJWTError as erro:
            raise InvalidToken("Token ilegível.") from erro
        if tipo != audiencias.TIPO_PESSOA:
            raise InvalidToken("Tipo de token não aceito aqui.")
        return super().get_validated_token(raw_token)
