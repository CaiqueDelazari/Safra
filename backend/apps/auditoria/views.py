from django.db.models import Q
from rest_framework import mixins, serializers, viewsets

from apps.auditoria.models import LogAuditoria
from core.permissions import (
    PermissaoDeModulo,
    PertenceAEmpresa,
    SomenteAdministrador,
)


class LogAuditoriaSerializer(serializers.ModelSerializer):
    empresa_nome = serializers.CharField(source="empresa.nome_fantasia", read_only=True)

    class Meta:
        model = LogAuditoria
        fields = ("id", "empresa", "empresa_nome", "usuario", "usuario_nome", "acao",
                  "modulo", "objeto_tipo", "objeto_id", "objeto_descricao", "descricao",
                  "alteracoes", "metadados", "ip", "user_agent", "criado_em")


class LogAuditoriaViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          viewsets.GenericViewSet):
    """Somente leitura — a trilha é imutável."""

    modulo = "auditoria"
    serializer_class = LogAuditoriaSerializer
    permission_classes = [SomenteAdministrador, PermissaoDeModulo, PertenceAEmpresa]
    filterset_fields = ("acao", "modulo", "usuario", "objeto_tipo", "objeto_id")
    search_fields = ("descricao", "objeto_descricao", "usuario_nome", "ip")
    ordering_fields = ("criado_em",)

    def get_queryset(self):
        empresa_id = getattr(self.request, "empresa_id", None)
        qs = LogAuditoria.objects.select_related("empresa", "usuario")
        if empresa_id:
            # Eventos globais (login/logout) não têm empresa: mantidos na visão.
            qs = qs.filter(Q(empresa_id=empresa_id) | Q(empresa__isnull=True))
        de = self.request.query_params.get("de")
        ate = self.request.query_params.get("ate")
        if de:
            qs = qs.filter(criado_em__date__gte=de)
        if ate:
            qs = qs.filter(criado_em__date__lte=ate)
        return qs
