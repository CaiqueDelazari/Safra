"""Repository Pattern — o acesso a dados nunca aparece direto nas views."""
from typing import Generic, Iterable, Optional, TypeVar

from django.db.models import Model, QuerySet

from core.context import current_empresa_id

T = TypeVar("T", bound=Model)


class BaseRepository(Generic[T]):
    model: type[T]
    select_related: tuple = ()
    prefetch_related: tuple = ()

    def query(self) -> QuerySet[T]:
        qs = self.model.objects.all()
        if self.select_related:
            qs = qs.select_related(*self.select_related)
        if self.prefetch_related:
            qs = qs.prefetch_related(*self.prefetch_related)
        return qs

    def get(self, pk) -> Optional[T]:
        return self.query().filter(pk=pk).first()

    def criar(self, **dados) -> T:
        return self.model.objects.create(**dados)

    def atualizar(self, instancia: T, **dados) -> T:
        for campo, valor in dados.items():
            setattr(instancia, campo, valor)
        instancia.save(update_fields=[*dados.keys(), "atualizado_em"])
        return instancia

    def remover(self, instancia: T) -> None:
        instancia.delete()

    def bulk_criar(self, objetos: Iterable[T]) -> list[T]:
        return self.model.objects.bulk_create(list(objetos))


class TenantRepository(BaseRepository[T]):
    """Repositório com isolamento obrigatório por empresa."""

    def query(self, empresa_id: Optional[int] = None) -> QuerySet[T]:
        qs = super().query()
        empresa_id = empresa_id or current_empresa_id()
        if empresa_id is None:
            return qs.none()  # sem empresa ativa não há dado visível
        return qs.filter(empresa_id=empresa_id)

    def get(self, pk, empresa_id: Optional[int] = None) -> Optional[T]:
        return self.query(empresa_id).filter(pk=pk).first()

    def criar(self, **dados) -> T:
        dados.setdefault("empresa_id", current_empresa_id())
        return self.model.objects.create(**dados)
