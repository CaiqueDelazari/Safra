from rest_framework import serializers

from apps.empresas.models import Empresa
from core.midia import url_assinada
from core.roles import Papel
from core.validadores import cnpj_valido, so_digitos


class EmpresaResumoSerializer(serializers.ModelSerializer):
    """O que o seletor do topo do painel precisa e nada mais."""

    logo = serializers.SerializerMethodField()

    class Meta:
        model = Empresa
        fields = ("id", "uuid", "nome_fantasia", "razao_social", "cnpj",
                  "cor_primaria", "logo", "ativa")

    def get_logo(self, obj) -> str | None:
        return url_assinada(obj.logo, self.context.get("request"))


class EmpresaSerializer(serializers.ModelSerializer):
    logo = serializers.ImageField(required=False, allow_null=True)
    logo_url = serializers.SerializerMethodField()
    cnpj_formatado = serializers.CharField(read_only=True)
    endereco_completo = serializers.CharField(read_only=True)
    apta_a_emitir = serializers.BooleanField(read_only=True)
    plano_label = serializers.CharField(source="get_plano_display", read_only=True)
    limite_titulos_mes = serializers.SerializerMethodField()
    titulos_no_mes = serializers.SerializerMethodField()
    pendencias_cadastro = serializers.SerializerMethodField()

    class Meta:
        model = Empresa
        fields = (
            "id", "uuid", "cnpj", "cnpj_formatado", "razao_social", "nome_fantasia",
            "inscricao_estadual", "inscricao_municipal", "logo", "logo_url",
            "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf",
            "telefone", "email", "email_cobranca", "plano", "plano_label",
            "cor_primaria", "configuracoes", "ativa", "suspensa_em",
            "motivo_suspensao", "endereco_completo", "apta_a_emitir",
            "limite_titulos_mes", "titulos_no_mes", "pendencias_cadastro",
            "criado_em", "atualizado_em",
        )
        read_only_fields = ("id", "uuid", "suspensa_em", "motivo_suspensao",
                            "criado_em", "atualizado_em")

    def get_logo_url(self, obj) -> str | None:
        return url_assinada(obj.logo, self.context.get("request"))

    def get_limite_titulos_mes(self, obj) -> int | None:
        return obj.limite_titulos_mes()

    def get_titulos_no_mes(self, obj) -> int:
        return obj.titulos_registrados_no_mes()

    def get_pendencias_cadastro(self, obj) -> list[str]:
        """O que falta para conseguir registrar um título.

        Existe porque a alternativa é descobrir isso no primeiro lote, com a
        remessa recusada pelo banco e ninguém sabendo qual campo faltava. Aqui
        a tela mostra a lista antes de a empresa tentar.
        """
        faltando = []
        if not obj.cnpj_ok:
            faltando.append("CNPJ inválido")
        if not obj.razao_social:
            faltando.append("razão social")
        if not obj.logradouro:
            faltando.append("logradouro")
        if not obj.cidade:
            faltando.append("cidade")
        if not obj.uf:
            faltando.append("UF")
        if len(obj.cep) != 8:
            faltando.append("CEP")
        return faltando

    def validate_cnpj(self, valor):
        digitos = so_digitos(valor)
        if not cnpj_valido(digitos):
            raise serializers.ValidationError(
                "CNPJ inválido. Ele vai impresso no boleto e transmitido ao banco: "
                "um dígito errado rejeita a remessa inteira."
            )
        return digitos

    def validate_cep(self, valor):
        return so_digitos(valor)

    def validate_uf(self, valor):
        return (valor or "").upper()

    def to_representation(self, instancia):
        dados = super().to_representation(instancia)
        # Plano e configurações são assunto de quem administra a conta. Para
        # os demais papéis, a empresa é só o cabeçalho do boleto.
        if self.context.get("papel") != Papel.ADMINISTRADOR:
            for campo in ("configuracoes", "plano", "plano_label",
                          "limite_titulos_mes", "titulos_no_mes"):
                dados.pop(campo, None)
        return dados
