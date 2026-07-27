# backend/modulomaps/campos.py
"""Campos DRF para geometria — GeoJSON de um lado, GEOS do outro.

Escritos à mão em vez de trazer `djangorestframework-gis` por uma razão de
proporção: o que se precisa aqui são duas conversões (ponto e geometria
genérica), e a biblioteca acrescentaria uma dependência a mais para acompanhar
no `pip-audit`/Dependabot. Quando o módulo pedir paginação GeoJSON de verdade
(FeatureCollection com bbox negociado), aí ela se paga.

Contrato com o frontend:
- ponto → `{"lon": -38.5, "lat": -12.9}` (e aceita também `[lon, lat]`);
- demais geometrias → **GeoJSON puro**, que é o que o MapLibre consome direto.

SRID sempre 4326 na entrada: geometria sem SRID declarado grava no banco como
"sem sistema de referência" e passa a comparar com tudo, silenciosamente errado.
"""
from __future__ import annotations

import json

from django.contrib.gis.geos import GEOSGeometry, Point
from django.contrib.gis.geos.error import GEOSException
from rest_framework import serializers

SRID = 4326


class PontoField(serializers.Field):
    """`Point` ↔ `{"lon", "lat"}`."""

    def to_representation(self, valor):
        if valor is None:
            return None
        return {"lon": round(valor.x, 7), "lat": round(valor.y, 7)}

    def to_internal_value(self, dado):
        if dado in (None, "", {}):
            return None
        try:
            if isinstance(dado, (list, tuple)) and len(dado) == 2:
                lon, lat = float(dado[0]), float(dado[1])
            else:
                lon, lat = float(dado["lon"]), float(dado["lat"])
        except (KeyError, TypeError, ValueError):
            raise serializers.ValidationError(
                'Ponto deve ser {"lon": -38.5, "lat": -12.9} ou [lon, lat].'
            )
        # Fora do intervalo válido não é "quase certo": é coordenada trocada
        # (lat no lugar de lon é o erro mais comum) e vira pin no oceano.
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise serializers.ValidationError(
                "Coordenada fora do intervalo válido — confira se lon e lat não estão trocados."
            )
        return Point(lon, lat, srid=SRID)


class GeometriaField(serializers.Field):
    """Qualquer geometria ↔ GeoJSON."""

    tipos_aceitos: tuple[str, ...] = ()

    def __init__(self, *args, tipos=(), **kwargs):
        self.tipos_aceitos = tuple(tipos)
        super().__init__(*args, **kwargs)

    def to_representation(self, valor):
        return json.loads(valor.geojson) if valor is not None else None

    def to_internal_value(self, dado):
        if dado in (None, "", {}):
            return None
        try:
            geom = GEOSGeometry(dado if isinstance(dado, str) else json.dumps(dado), srid=SRID)
        except (GEOSException, TypeError, ValueError) as e:
            raise serializers.ValidationError(f"Geometria inválida: {e}")
        if geom.srid is None:
            geom.srid = SRID
        if self.tipos_aceitos and geom.geom_type not in self.tipos_aceitos:
            raise serializers.ValidationError(
                f"Esperado {' ou '.join(self.tipos_aceitos)}; veio {geom.geom_type}."
            )
        # Polígono aberto ou auto-interceptado passa no parse e explode depois,
        # no índice ou no cálculo de área. Barrar aqui devolve mensagem legível.
        if geom.geom_type in ("Polygon", "MultiPolygon") and not geom.valid:
            raise serializers.ValidationError(f"Polígono inválido: {geom.valid_reason}")
        return geom
