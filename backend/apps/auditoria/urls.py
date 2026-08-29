from rest_framework.routers import DefaultRouter

from apps.auditoria.views import LogAuditoriaViewSet

router = DefaultRouter()
router.register("", LogAuditoriaViewSet, basename="auditoria")

urlpatterns = router.urls
