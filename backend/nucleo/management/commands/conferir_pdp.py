"""Confere, para um token real, todas as perguntas: o que o token diz × o que o PDP diz.

    python manage.py conferir_pdp --token <access JWT>
    python manage.py conferir_pdp --token <jwt> --pergunta c:pdca.medicao.atestar

É o instrumento da E2E da remodelagem (`testes/e2e/seg2_pdp_sombra_test.py`) e
de quem investiga uma divergência: valida o JWT como o backend valida, monta a
pessoa como a requisição monta, e faz as mesmas perguntas pelo mesmo código
(`nucleo/autorizacao.py`), sem passar por view nenhuma. Sai em JSON.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

import funcoesautorizacao
from nucleo import autorizacao, autorizacao_pdp, autorizacao_sombra
from nucleo.authentication import IamJWTAuthentication


def todas_as_perguntas():
    cat = funcoesautorizacao.catalogo()
    return (
        [autorizacao._pergunta_de_codigo(c) for c in sorted(cat["codigos"])]
        + [autorizacao._pergunta_de_modulo(m) for m in cat["modulos_vendaveis"]]
        + [autorizacao._ADMINISTRA, autorizacao._SUPERVISIONA]
    )


class Command(BaseCommand):
    help = "Compara token e PDP em todas as perguntas de acesso, para um JWT."

    def add_arguments(self, parser):
        parser.add_argument("--token", required=True)
        parser.add_argument("--pergunta", help="Só esta (c:<código>, m:<módulo>, administra, supervisiona).")

    def handle(self, *args, **opts):
        auth = IamJWTAuthentication()
        try:
            validado = auth.get_validated_token(opts["token"].encode())
            user = auth.get_user(validado)
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Token recusado: {exc}") from exc
        quem = autorizacao._quem(user)
        if quem is None:
            raise CommandError("Token sem pessoa da IAM (token de serviço?).")

        perguntas = todas_as_perguntas()
        if opts["pergunta"]:
            perguntas = [p for p in perguntas if p.chave == opts["pergunta"]]
            if not perguntas:
                raise CommandError(f"Pergunta desconhecida: {opts['pergunta']}")

        divergencias, indisponivel = [], 0
        respostas = {}
        for p in perguntas:
            pelo_token = autorizacao._pelo_token(user, p)
            pelo_pdp, origem = autorizacao_pdp.decidir(quem, p)
            respostas[p.chave] = {"token": pelo_token, "pdp": pelo_pdp, "origem": origem}
            c = autorizacao_sombra.Comparacao(
                quem=quem, iat=getattr(user, "iam_token_iat", None), pergunta=p,
                modo="conferencia", decisao_token=pelo_token,
                decisao_pdp=pelo_pdp, origem_pdp=origem,
            )
            tipo = autorizacao_sombra.classificar(c, pelo_pdp, origem)
            if tipo == "pdp_indisponivel":
                indisponivel += 1
            if tipo:
                divergencias.append({"pergunta": p.chave, "tipo": tipo,
                                     "token": pelo_token, "pdp": pelo_pdp})
        self.stdout.write(json.dumps({
            "usuario": user.username,
            "tenant": quem.tenant_id,
            "perguntas": len(perguntas),
            "divergencias": divergencias,
            "pdp_indisponivel": indisponivel,
            "respostas": respostas if opts["pergunta"] else None,
        }, ensure_ascii=False))
