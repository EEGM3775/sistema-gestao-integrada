# backend/modulomaps/admin.py
from django.contrib import admin

from .models import Camada, Feicao, Geofence, Local, Ortofoto, ParadaRota, PlanoVoo, Rota


@admin.register(Local)
class LocalAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "cidade", "uf", "precisao", "fonte", "ativo")
    list_filter = ("tipo", "precisao", "uf", "ativo")
    search_fields = ("nome", "logradouro", "cidade")


@admin.register(Camada)
class CamadaAdmin(admin.ModelAdmin):
    list_display = ("nome", "obra", "ordem", "visivel")
    list_filter = ("visivel",)


@admin.register(Feicao)
class FeicaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "camada", "tipo", "data_referencia", "obra")
    list_filter = ("tipo", "data_referencia")
    search_fields = ("nome", "grupo")


@admin.register(Ortofoto)
class OrtofotoAdmin(admin.ModelAdmin):
    list_display = ("titulo", "data_voo", "obra", "gsd_cm")
    list_filter = ("data_voo",)
    search_fields = ("titulo", "chunk_uuid")


@admin.register(PlanoVoo)
class PlanoVooAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "obra", "altura_m", "fotos_estimadas", "calculado_em")
    list_filter = ("tipo",)
    search_fields = ("nome",)


class ParadaRotaInline(admin.TabularInline):
    model = ParadaRota
    extra = 0


@admin.register(Rota)
class RotaAdmin(admin.ModelAdmin):
    list_display = ("nome", "origem", "status", "distancia_m", "procedencia", "data_planejada")
    list_filter = ("status", "procedencia")
    inlines = [ParadaRotaInline]


@admin.register(Geofence)
class GeofenceAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "local", "raio_m", "ativo")
    list_filter = ("tipo", "ativo")
