"""Serializer base com isolamento nas relações.

O `TenantRepository` protege a **leitura**: nenhuma listagem devolve dado de
outra empresa. Ele não protege a **escrita**, e é aí que estava o buraco.

Um `PrimaryKeyRelatedField` gerado pelo ModelSerializer aceita qualquer id que
exista na tabela. Numa aplicação de empresa única isso é inofensivo. Aqui, um
usuário legítimo da empresa A podia criar uma cobrança — carimbada como da
empresa A, tudo certo do lado do tenant — apontando para o `cliente` da
empresa B. A cobrança seria dela; o nome, o CPF e o endereço do sacado
listados na tela, não. Vazamento por relação, sem nenhuma requisição
suspeita: um número trocado no corpo do POST.

`TenantModelSerializer` fecha isso na origem: todo campo de relação que aponta
para um modelo multiempresa tem o queryset filtrado pela empresa ativa. Um id
alheio deixa de existir para a validação e volta como "objeto inválido" — a
mesma resposta que um id inventado, que é exatamente o que ele é do ponto de
vista de quem pergunta.
"""
from rest_framework import serializers

from core.models import TenantModel


class TenantModelSerializer(serializers.ModelSerializer):
    """ModelSerializer que só enxerga relações da empresa ativa.

    A empresa vem do contexto (`empresa_id`), posto por `TenantViewSet`. Sem
    contexto de empresa, nenhuma relação multiempresa é aceita — falha
    fechado, em vez de aceitar tudo.
    """

    def get_fields(self):
        campos = super().get_fields()
        empresa_id = self.context.get("empresa_id")

        for campo in campos.values():
            queryset = getattr(campo, "queryset", None)
            if queryset is None:
                continue
            modelo = queryset.model
            if not issubclass(modelo, TenantModel):
                continue
            campo.queryset = (
                queryset.filter(empresa_id=empresa_id) if empresa_id
                else queryset.none()
            )
        return campos
