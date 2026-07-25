# backend/catalogo/urls.py
from rest_framework.routers import DefaultRouter

from .views import ComponenteComposicaoViewSet, ItemViewSet

router = DefaultRouter()
router.register(r"itens", ItemViewSet, basename="catalogo-item")
router.register(r"componentes-composicao", ComponenteComposicaoViewSet, basename="catalogo-componente")

urlpatterns = router.urls
