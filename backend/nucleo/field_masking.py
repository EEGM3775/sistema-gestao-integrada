"""Mascaramento de campo por permissão — Fase 9.C (LGPD/PII).

A camada mais fina do RBAC (AD-9 §2.4): em vez de dar **403 no endpoint
inteiro** quando o usuário não pode ver um campo sensível, o endpoint retorna
o registro com os campos sensíveis **mascarados** (ou redigidos) por permissão.
Assim a ficha do funcionário "para de chover 403".

Dois eixos **independentes**, declarados por serializer:

    class FuncionarioSerializer(FieldMaskingSerializerMixin, ModelSerializer):
        sensitive_fields = {                 # LEITURA: mascara sem a permissão
            "cpf": "rh.cpf.view",
            "salario_base": "rh.folha.view",
        }
        write_protected_fields = {           # ESCRITA: rejeita sem a permissão
            "salario_base": "rh.folha.edit",
        }

Por que os dois eixos são separados (e não derivados um do outro):
- **CPF do funcionário** é sensível **na leitura** (`rh.cpf.view`), mas sua
  **escrita** faz parte do cadastro — quem pode `rh.funcionario.edit` (o gate do
  endpoint) o define; **não** existe `rh.cpf.edit`. Se a escrita fosse derivada da
  leitura (`rh.cpf.view` → `rh.cpf.edit`), **ninguém** poderia criar/editar
  funcionário (a permissão derivada não existe no catálogo). Por isso a proteção
  de escrita é **opt-in explícita** e só cobre campos cuja `.edit` é real e
  concedível (salário, dados médicos, dados bancários).

Regras:
- **Leitura** (``to_representation``): campo sem a permissão vem mascarado.
  **Fail-closed:** sem usuário no contexto (serialização fora de request), tudo
  que é sensível é mascarado — PII não vaza por um caminho sem contexto.
- **Escrita** (``validate``): gravar em ``write_protected_fields`` sem a permissão
  ``.edit`` é rejeitado com 400 (e logado). **Fail-closed** para token sem
  ``permissions`` e não-admin.
- Admin de tenant / superuser passam nos dois eixos.

Máscara por tipo de campo: documentos (CPF/CNPJ) e conta/agência vêm **parciais**
(``••••`` + últimos dígitos); valores monetários, chave PIX e textos livres vêm
``null`` (redigidos). Fecha o achado **S9** (PII em texto puro) e o DoD da Fase 9.
"""
from __future__ import annotations

import logging
from typing import Any

from rest_framework import serializers

logger = logging.getLogger(__name__)

_MASK_PARTIAL = "••••"


def _mask_document(value: Any) -> Any:
    """Mascara um CPF/CNPJ mantendo os 2 últimos dígitos (conferência rápida sem
    expor o titular). ``None``/vazio passa intacto."""
    if not value:
        return value
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return _MASK_PARTIAL
    return f"{_MASK_PARTIAL}{digits[-2:]}"


def _mask_account(value: Any) -> Any:
    """Mascara conta/agência mantendo os 4 últimos dígitos."""
    if not value:
        return value
    s = str(value)
    if len(s) <= 4:
        return _MASK_PARTIAL
    return f"{_MASK_PARTIAL}{s[-4:]}"


def _mask_value(_value: Any) -> None:
    """Valores monetários, chave PIX e texto livre são redigidos (``null``)."""
    return None


def _choose_masker(field_name: str, value: Any):
    """Seleciona a máscara pelo nome/tipo do campo. O default (redigir → ``null``)
    é o lado seguro: um campo sensível não previsto **over-redige**, não vaza."""
    name = (field_name or "").lower()
    if "cpf" in name or "cnpj" in name:
        return _mask_document(value)
    if "conta" in name or "agencia" in name:
        return _mask_account(value)
    return _mask_value(value)


def _is_privileged(user) -> bool:
    return bool(
        getattr(user, "is_tenant_admin", False) or getattr(user, "is_superuser", False)
    )


def _has(user, permission: str) -> bool:
    """Usuário tem a permissão? Admin passa. **Fail-closed:** sem a permissão no
    claim (inclusive lista vazia / token legado), retorna False."""
    if _is_privileged(user):
        return True
    perms = getattr(user, "iam_permissions", None) or []
    return permission in perms


def mask_document_unless(user, value, permission: str = "cadastro.cliente_doc.view"):
    """Mantém o CPF/CNPJ só se o usuário puder ver a PII documental do cliente;
    senão devolve a versão mascarada (``••••`` + 2 últimos dígitos). Para uso
    **fora de serializer** — ex.: o relatório de divergências Asaas, que monta um
    dict cru e não passa pelo `FieldMaskingSerializerMixin`. Fail-closed via `_has`."""
    return value if _has(user, permission) else _mask_document(value)


class FieldMaskingSerializerMixin:
    """Mascara campos sensíveis na leitura e guarda campos protegidos na escrita.

    - ``sensitive_fields = {campo: permissao_de_leitura}`` — mascara na leitura.
    - ``write_protected_fields = {campo: permissao_de_escrita}`` — rejeita a
      escrita (opt-in; só campos cuja ``.edit`` é real e concedível).
    """

    sensitive_fields: dict[str, str] = {}
    write_protected_fields: dict[str, str] = {}

    # ---- Leitura: mascara campos não autorizados ---------------------------
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.sensitive_fields:
            return data
        request = self.context.get("request") if self.context else None
        user = getattr(request, "user", None) if request else None
        # Fail-closed: sem usuário autenticado no contexto, mascara tudo que é
        # sensível (serialização fora de uma request não deve vazar PII).
        autenticado = bool(user and getattr(user, "is_authenticated", False))
        for campo, perm in self.sensitive_fields.items():
            if campo not in data:
                continue
            if autenticado and _has(user, perm):
                continue
            data[campo] = _choose_masker(campo, data[campo])
        return data

    # ---- Escrita: rejeita/loga campo protegido não autorizado --------------
    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not self.write_protected_fields:
            return attrs
        request = self.context.get("request") if self.context else None
        user = getattr(request, "user", None) if request else None
        autenticado = bool(user and getattr(user, "is_authenticated", False))
        violados: list[str] = []
        for campo, perm_edit in self.write_protected_fields.items():
            if campo not in attrs:
                continue
            # Fail-closed: sem usuário autenticado, bloqueia campo protegido.
            if not autenticado or not _has(user, perm_edit):
                violados.append(campo)
        if violados:
            logger.warning(
                "Escrita barrada em campo sensível sem permissão: user=%s campos=%s",
                getattr(user, "username", None), violados,
            )
            raise serializers.ValidationError(
                {c: "Você não tem permissão para alterar este campo." for c in violados}
            )
        return attrs
