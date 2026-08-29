from rest_framework.routers import DefaultRouter

from apps.pagamentos.views import PagamentoViewSet

router = DefaultRouter()
router.register("", PagamentoViewSet, basename="pagamento")

urlpatterns = router.urls
