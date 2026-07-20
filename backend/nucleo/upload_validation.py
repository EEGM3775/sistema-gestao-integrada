# backend/nucleo/upload_validation.py
"""Validação server-side de uploads (achado A4).

Antes, tipo/tamanho de arquivo só eram checados no cliente — qualquer POST
direto à API subia arquivo de qualquer tipo/tamanho. Este módulo reusa a
`ConfiguracaoArquivos` do tenant (a mesma fonte do endpoint
`/api/configuracoes/upload/`) para impor o limite no backend.

Uso: misture `UploadValidationMixin` no serializer que expõe FileField/
ImageField para escrita. É no-op quando o request não traz arquivo novo
(ex.: PATCH sem re-upload), então aplicar de sobra é seguro.
"""
import os

from django.core.files.uploadedfile import UploadedFile
from rest_framework import serializers

from .models import ConfiguracaoArquivos

# Padrão global (fallback) — espelha _DEFAULT_TIPOS de nucleo.views.
DEFAULT_MAX_MB = 10
DEFAULT_TIPOS = [
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]

# Extensões plausíveis por MIME aceito — segunda barreira quando o
# Content-Type do multipart vier genérico/ausente (é definido pelo cliente,
# logo não confiável sozinho).
_MIME_EXTS = {
    "application/pdf": {".pdf"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/gif": {".gif"},
    "image/webp": {".webp"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
    "application/xml": {".xml"},
    "text/xml": {".xml"},
    "text/csv": {".csv"},
}

_GENERIC_CTYPES = {"", "application/octet-stream", "binary/octet-stream"}


def resolve_upload_config(tenant_id):
    """Resolve (max_bytes, allowed_mimes) efetivos para o tenant.

    Mesma precedência do `ConfiguracaoUploadView`: config do tenant → config
    global (tenant nulo) → padrão embutido. Fonte única para a view e para a
    validação, evitando divergência cliente↔servidor.
    """
    obj = None
    if tenant_id:
        obj = ConfiguracaoArquivos.objects.filter(tenant_id=tenant_id).first()
    if obj is None:
        obj = ConfiguracaoArquivos.objects.filter(tenant__isnull=True).first()

    max_mb = obj.max_tamanho_mb if obj else DEFAULT_MAX_MB
    tipos = (obj.tipos_aceitos if obj and obj.tipos_aceitos else DEFAULT_TIPOS)
    allowed = {str(t).split(";")[0].strip().lower() for t in tipos}
    return max_mb * 1024 * 1024, allowed


def _allowed_extensions(allowed_mimes):
    exts = set()
    for mime in allowed_mimes:
        exts |= _MIME_EXTS.get(mime, set())
    return exts


def validate_uploaded_file(uploaded, *, max_bytes, allowed_mimes):
    """Valida um arquivo enviado contra limite de tamanho e tipo.

    Levanta `serializers.ValidationError` (→ 400 limpo) em violação.
    """
    size = getattr(uploaded, "size", None)
    if size is not None and size > max_bytes:
        limite_mb = max_bytes // (1024 * 1024)
        raise serializers.ValidationError(
            f"Arquivo excede o limite de {limite_mb} MB."
        )

    ctype = (getattr(uploaded, "content_type", "") or "").split(";")[0].strip().lower()
    ext = os.path.splitext(getattr(uploaded, "name", "") or "")[1].lower()

    if ctype in allowed_mimes:
        return
    # Content-Type genérico/ausente: aceita só se a extensão bater com um MIME aceito.
    if ctype in _GENERIC_CTYPES and ext in _allowed_extensions(allowed_mimes):
        return
    raise serializers.ValidationError("Tipo de arquivo não permitido.")


class UploadValidationMixin:
    """Impõe tamanho/tipo em todo FileField/ImageField escrito no serializer.

    Descobre os campos de arquivo do próprio serializer e valida só os que
    trazem um upload novo neste request (`UploadedFile`), usando a config do
    tenant do request. Sem request no contexto, cai no padrão global.
    """

    def validate(self, attrs):
        attrs = super().validate(attrs)
        arquivos = {
            name: value
            for name, value in attrs.items()
            if isinstance(value, UploadedFile)
        }
        if not arquivos:
            return attrs

        request = self.context.get("request")
        tenant_id = getattr(getattr(request, "user", None), "tenant_id", None)
        max_bytes, allowed = resolve_upload_config(tenant_id)

        errors = {}
        for name, uploaded in arquivos.items():
            try:
                validate_uploaded_file(
                    uploaded, max_bytes=max_bytes, allowed_mimes=allowed
                )
            except serializers.ValidationError as exc:
                errors[name] = exc.detail
        if errors:
            raise serializers.ValidationError(errors)
        return attrs
