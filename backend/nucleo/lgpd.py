"""Serviços LGPD — portabilidade (export) e esquecimento (anonimização). Fase 9.D.

Titulares suportados: **funcionário** (RH) e **cliente**. Para cada um, uma
config declara os campos de PII a anonimizar, os registros-filhos de PII a
apagar e o login vinculado a desativar.

- **Portabilidade** (`exportar_titular`): reúne todos os dados do titular
  (inclusive PII) num dicionário JSON — é o dado do próprio titular, então a
  exportação é integral (LGPD art. 18, V). Nunca passa pelos serializers (que
  mascarariam).
- **Esquecimento** (`anonimizar_titular`): sobrescreve a PII com marcador
  (`[ANON-<id>]`), apaga os filhos de PII (médico/bancário/documentos) e
  desativa o login. Mantém o registro-casca por integridade referencial e
  histórico contábil (LGPD art. 16 — guarda para obrigação legal).
"""
from __future__ import annotations

import datetime
import json
import logging

from django.apps import apps
from django.db import models as djmodels
from django.forms.models import model_to_dict

logger = logging.getLogger(__name__)


# tipo -> configuração do titular
TITULARES: dict[str, dict] = {
    "funcionario": {
        "app": "rh", "model": "Funcionario", "pk": "funcionario_id",
        "pii": [
            "nome_completo", "cpf", "rg", "data_nascimento", "genero", "estado_civil",
            "telefone_pessoal", "telefone_celular", "email_pessoal", "endereco_completo",
            "numero_ctps", "serie_ctps", "pis_pasep", "carteira_trabalho_numero",
            "carteira_trabalho_serie", "carteira_trabalho_uf", "carteira_trabalho_observacoes",
        ],
        "relacionados_pii": [
            ("rh", "DadoMedicoFuncionario", "funcionario"),
            ("rh", "DadoBancarioFuncionario", "funcionario"),
            ("rh", "DocumentoFuncionario", "funcionario"),
            ("rh", "ASOFuncionario", "funcionario"),
        ],
        "usuario_field": "usuario",
    },
    "cliente": {
        "app": "clientes", "model": "Cliente", "pk": "cliente_id",
        "pii": [
            "nome_completo", "cpf_cnpj", "email", "telefone", "endereco",
            "numero_endereco", "complemento_endereco", "bairro", "cidade", "estado",
            "cep", "cidade_ibge", "data_nascimento", "estado_civil", "profissao",
        ],
        "relacionados_pii": [
            ("clientes", "DadoBancarioCliente", "cliente"),
            ("clientes", "DocumentoCliente", "cliente"),
        ],
        "usuario_field": None,
    },
}


def titular_model(tipo: str):
    cfg = TITULARES[tipo]
    return apps.get_model(cfg["app"], cfg["model"])


def _jsonable(d: dict) -> dict:
    """Coage o dict (datas, Decimal, FileField…) para JSON puro via str fallback."""
    return json.loads(json.dumps(d, default=str))


def exportar_titular(tipo: str, obj) -> dict:
    """Reúne os dados do titular + filhos de PII num dict JSON (portabilidade)."""
    cfg = TITULARES[tipo]
    dados = {"tipo": tipo, "id": getattr(obj, cfg["pk"]), "titular": model_to_dict(obj)}
    relacionados: dict[str, list] = {}
    for app, model, fk in cfg["relacionados_pii"]:
        M = apps.get_model(app, model)
        relacionados[model] = [model_to_dict(x) for x in M.objects.filter(**{fk: obj})]
    dados["relacionados"] = relacionados
    return _jsonable(dados)


def _redact_value(field, pk):
    """Marcador de anonimização por tipo de campo, respeitando null/constraints."""
    if getattr(field, "null", False):
        return None
    if isinstance(field, (djmodels.DateField, djmodels.DateTimeField)):
        return datetime.date(1900, 1, 1)
    if getattr(field, "blank", False):
        return ""
    ml = getattr(field, "max_length", None)
    token = f"[ANON-{pk}]"          # único por registro → não colide em unique
    return token[:ml] if ml else token


def anonimizar_titular(tipo: str, obj) -> None:
    """Direito ao esquecimento: sobrescreve PII, apaga filhos de PII, desativa login."""
    cfg = TITULARES[tipo]
    pk = getattr(obj, cfg["pk"])
    for campo in cfg["pii"]:
        try:
            f = obj._meta.get_field(campo)
        except Exception:
            continue
        setattr(obj, campo, _redact_value(f, pk))
    obj.save()
    for app, model, fk in cfg["relacionados_pii"]:
        apps.get_model(app, model).objects.filter(**{fk: obj}).delete()
    if cfg["usuario_field"]:
        u = getattr(obj, cfg["usuario_field"], None)
        if u is not None:
            u.is_active = False
            u.save(update_fields=["is_active"])
    logger.warning("LGPD esquecimento aplicado: tipo=%s id=%s", tipo, pk)
