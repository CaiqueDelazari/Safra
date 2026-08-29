from rest_framework.routers import DefaultRouter

from apps.cobrancas.views import CobrancaViewSet

router = DefaultRouter()
router.register("", CobrancaViewSet, basename="cobranca")

urlpatterns = router.urls
