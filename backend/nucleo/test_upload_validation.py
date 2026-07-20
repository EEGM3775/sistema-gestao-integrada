"""A4 — validação server-side de upload (tamanho + tipo) reusando a UploadConfig.

Testa o validador puro `validate_uploaded_file` e o `UploadValidationMixin`
(sem tocar o banco: a config do tenant é injetada via patch).
"""
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework import serializers

from nucleo import upload_validation
from nucleo.upload_validation import (
    DEFAULT_TIPOS,
    UploadValidationMixin,
    validate_uploaded_file,
)

MAX = 10 * 1024 * 1024
ALLOWED = {t.lower() for t in DEFAULT_TIPOS}


def _file(name, ctype, size=1000):
    return SimpleUploadedFile(name, b"x" * size, content_type=ctype)


class ValidateUploadedFileTests(SimpleTestCase):
    def test_aceita_tipo_permitido(self):
        # Não deve levantar.
        validate_uploaded_file(
            _file("doc.pdf", "application/pdf"), max_bytes=MAX, allowed_mimes=ALLOWED
        )

    def test_rejeita_tipo_nao_permitido(self):
        with self.assertRaises(serializers.ValidationError):
            validate_uploaded_file(
                _file("payload.exe", "application/x-msdownload"),
                max_bytes=MAX,
                allowed_mimes=ALLOWED,
            )

    def test_rejeita_acima_do_limite(self):
        with self.assertRaises(serializers.ValidationError):
            validate_uploaded_file(
                _file("grande.pdf", "application/pdf", size=200),
                max_bytes=100,
                allowed_mimes=ALLOWED,
            )

    def test_content_type_generico_cai_para_extensao(self):
        # octet-stream + extensão permitida → aceita.
        validate_uploaded_file(
            _file("doc.pdf", "application/octet-stream"),
            max_bytes=MAX,
            allowed_mimes=ALLOWED,
        )
        # octet-stream + extensão perigosa → rejeita (não confia só no header).
        with self.assertRaises(serializers.ValidationError):
            validate_uploaded_file(
                _file("payload.exe", "application/octet-stream"),
                max_bytes=MAX,
                allowed_mimes=ALLOWED,
            )


class _DummySerializer(UploadValidationMixin, serializers.Serializer):
    arquivo = serializers.FileField()


class UploadValidationMixinTests(SimpleTestCase):
    def test_mixin_bloqueia_arquivo_invalido(self):
        s = _DummySerializer(
            data={"arquivo": _file("payload.exe", "application/x-msdownload")}
        )
        with patch.object(
            upload_validation, "resolve_upload_config", return_value=(MAX, ALLOWED)
        ):
            self.assertFalse(s.is_valid())
        self.assertIn("arquivo", s.errors)

    def test_mixin_passa_arquivo_valido(self):
        s = _DummySerializer(data={"arquivo": _file("doc.pdf", "application/pdf")})
        with patch.object(
            upload_validation, "resolve_upload_config", return_value=(MAX, ALLOWED)
        ):
            self.assertTrue(s.is_valid(), s.errors)
