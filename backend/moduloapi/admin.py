# backend/moduloapi/admin.py
from django.contrib import admin
from .models import GoogleAccount

@admin.register(GoogleAccount)
class GoogleAccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'expires_at', 'created_at')
    search_fields = ('user__username',)
