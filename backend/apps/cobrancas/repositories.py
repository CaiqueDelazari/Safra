from apps.cobrancas.models import Cobranca
from core.repositories import TenantRepository


class CobrancaRepository(TenantRepository[Cobranca]):
    model = Cobranca
    # `select_related` sempre: a listagem mostra nome do cliente e da conta em
    # toda linha, e sem isto são duas consultas por linha — 50 consultas numa
    # página de 25.
    select_related = ("cliente", "conta_bancaria", "lote")

    def em_aberto(self, empresa_id=None):
        from apps.cobrancas.models import EM_ABERTO

        return self.query(empresa_id).filter(status__in=EM_ABERTO)

    def prontas_para_lote(self, empresa_id=None):
        from apps.cobrancas.models import ELEGIVEIS_PARA_LOTE

        return self.query(empresa_id).filter(status__in=ELEGIVEIS_PARA_LOTE)


repositorio = CobrancaRepository()
