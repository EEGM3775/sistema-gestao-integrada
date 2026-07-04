from django.contrib import admin
from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request):
    return Response({
        "servico": "SGI — Identity & Access Management",
        "versao": "1.0",
        "endpoints": {
            "login":       request.build_absolute_uri("/auth/login/"),
            "refresh":     request.build_absolute_uri("/auth/refresh/"),
            "logout":      request.build_absolute_uri("/auth/logout/"),
            "me":          request.build_absolute_uri("/auth/me/"),
            "tenants":     request.build_absolute_uri("/tenants/"),
            "modulos":     request.build_absolute_uri("/modulos/"),
            "assinaturas": request.build_absolute_uri("/assinaturas/"),
            "usuarios":    request.build_absolute_uri("/usuarios/"),
            "perfis":      request.build_absolute_uri("/perfis/"),
            "admin":       request.build_absolute_uri("/admin/"),
        },
    })


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", api_root, name="api-root"),
    path("", include("identity.urls")),
]
