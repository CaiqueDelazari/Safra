from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenVerifyView

from apps.accounts.views import (
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
    SegundoFatorView,
    TrocaSenhaView,
    UsuarioViewSet,
)

router = DefaultRouter()
router.register("users", UsuarioViewSet, basename="usuario")

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("verify/", TokenVerifyView.as_view(), name="verify"),
    path("me/", MeView.as_view(), name="me"),
    path("change-password/", TrocaSenhaView.as_view(), name="trocar-senha"),
    path("two-factor/", SegundoFatorView.as_view(), name="segundo-fator"),
    path("", include(router.urls)),
]
