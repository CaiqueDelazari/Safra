from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import User, UsuarioEmpresa


class VinculoInline(admin.TabularInline):
    """O papel mora aqui: é por empresa, não por usuário."""

    model = UsuarioEmpresa
    extra = 1
    fields = ("empresa", "papel", "ativo")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("nome_completo",)
    list_display = ("nome_completo", "email", "is_active", "plataforma_admin")
    list_filter = ("is_active", "plataforma_admin")
    search_fields = ("nome_completo", "email")
    inlines = [VinculoInline]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados", {"fields": ("nome_completo", "telefone", "avatar")}),
        ("Acesso", {"fields": ("empresa_padrao", "is_active", "is_staff",
                               "is_superuser", "plataforma_admin")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",),
                "fields": ("email", "nome_completo", "password1", "password2")}),
    )
