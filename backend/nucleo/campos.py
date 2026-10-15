# backend/nucleo/campos.py
"""Campos de serializer compartilhados."""
from rest_framework import serializers


class NomeDoRelacionado(serializers.Field):
    """O `str()` do objeto relacionado, ou "" quando não há relacionado.

    **Existe porque `source="fk.__str__"` mente quando a FK está vazia** (visto em
    15/10/2026): o DRF segue o caminho, `getattr(None, "__str__")` dá certo — é o
    método do próprio `None` — e a tela mostrava "Matriz de <method-wrapper
    '__str__' of NoneType…>". O `default=""` não salva, porque só vale quando o
    caminho *falha*. Aqui o vazio é decidido antes do texto.
    """

    def __init__(self, **kwargs):
        kwargs["read_only"] = True
        super().__init__(**kwargs)

    def get_attribute(self, instance):
        alvo = super().get_attribute(instance)
        return "" if alvo is None else str(alvo)

    def to_representation(self, value):
        return value
