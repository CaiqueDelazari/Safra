from django.db.models import Count, Q, Sum

from apps.clientes.models import Cliente
from core.repositories import TenantRepository


class ClienteRepository(TenantRepository[Cliente]):
    model = Cliente

    def query(self, empresa_id=None):
        # `annotate` aqui e não na view: a lista de clientes sempre mostra
        # quantas cobranças em aberto cada um tem, e calcular isso por linha
        # na serialização faria uma consulta por cliente (N+1) numa tela que
        # pagina de 25 em 25.
        return super().query(empresa_id).annotate(
            cobrancas_abertas=Count(
                "cobrancas",
                filter=Q(cobrancas__status__in=[
                    "PENDENTE", "ENVIADA_AO_BANCO", "REGISTRADA", "DISPONIVEL", "VENCIDA",
                ]),
                distinct=True,
            ),
            valor_em_aberto=Sum(
                "cobrancas__valor",
                filter=Q(cobrancas__status__in=[
                    "PENDENTE", "ENVIADA_AO_BANCO", "REGISTRADA", "DISPONIVEL", "VENCIDA",
                ]),
            ),
        )

    def por_documento(self, documento: str, empresa_id=None):
        return self.query(empresa_id).filter(cpf_cnpj=documento).first()


repositorio = ClienteRepository()
