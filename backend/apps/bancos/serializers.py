from rest_framework import serializers

from apps.bancos.bancos import BANCOS_INTEGRADOS, MeioDeIntegracao
from apps.bancos.models import ArquivoBancario, ContaBancaria, LoteBancario, OcorrenciaBancaria
from core.midia import url_assinada
from core.serializers import TenantModelSerializer


class ContaBancariaSerializer(TenantModelSerializer):
    """As credenciais entram, nunca saem.

    Cada segredo aparece como um par: um campo `write_only` para gravar e um
    booleano `..._configurado` para a tela poder dizer "cadastrada" sem
    revelar o valor. Devolver a credencial mascarada ('****1234') seria pior
    do que não devolver: o final de uma chave já é meio caminho para quem
    tenta adivinhar o resto, e a tela não precisa dela para nada.
    """

    banco_label = serializers.CharField(source="get_banco_display", read_only=True)
    agencia_conta = serializers.CharField(read_only=True)
    integrada = serializers.BooleanField(read_only=True)
    transmissao_automatica = serializers.BooleanField(read_only=True)
    credenciais_configuradas = serializers.BooleanField(read_only=True)

    api_client_id = serializers.CharField(write_only=True, required=False, allow_blank=True)
    api_client_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    api_certificado = serializers.CharField(write_only=True, required=False, allow_blank=True)
    api_chave_privada = serializers.CharField(write_only=True, required=False, allow_blank=True)
    sftp_senha = serializers.CharField(write_only=True, required=False, allow_blank=True)

    api_configurada = serializers.SerializerMethodField()
    sftp_configurado = serializers.SerializerMethodField()
    certificado_configurado = serializers.SerializerMethodField()

    class Meta:
        model = ContaBancaria
        fields = [
            "id", "uuid", "nome", "banco", "banco_label", "meio_integracao",
            "agencia", "agencia_dv", "conta", "conta_dv", "agencia_conta",
            "carteira", "codigo_cedente", "variacao_carteira", "especie_titulo",
            "aceite", "proximo_nosso_numero", "nosso_numero_maximo",
            "proxima_remessa", "dias_protesto", "dias_baixa_automatica",
            "juros_mes_percentual", "multa_percentual", "instrucoes_boleto",
            "api_client_id", "api_client_secret", "api_certificado",
            "api_chave_privada", "sftp_host", "sftp_porta", "sftp_usuario",
            "sftp_senha", "sftp_dir_remessa", "sftp_dir_retorno",
            "api_configurada", "sftp_configurado", "certificado_configurado",
            "producao", "ativa", "padrao", "integrada", "transmissao_automatica",
            "credenciais_configuradas", "criado_em", "atualizado_em",
        ]
        read_only_fields = ["id", "uuid", "proximo_nosso_numero", "proxima_remessa",
                            "criado_em", "atualizado_em"]

    def get_api_configurada(self, obj) -> bool:
        return bool(obj.api_client_id and obj.api_client_secret)

    def get_sftp_configurado(self, obj) -> bool:
        return bool(obj.sftp_host and obj.sftp_usuario)

    def get_certificado_configurado(self, obj) -> bool:
        return bool(obj.api_certificado and obj.api_chave_privada)

    def validate(self, dados):
        banco = dados.get("banco") or getattr(self.instance, "banco", "")
        meio = dados.get("meio_integracao") or getattr(self.instance, "meio_integracao", "")

        if banco and banco not in BANCOS_INTEGRADOS:
            raise serializers.ValidationError({
                "banco": (
                    "Ainda não há integração implementada para este banco. "
                    "Hoje o sistema registra títulos no Banco Safra (422); os "
                    "demais podem ser cadastrados quando o adapter existir."
                )
            })

        if meio == MeioDeIntegracao.API:
            tem_id = dados.get("api_client_id") or getattr(self.instance, "api_client_id", "")
            tem_secret = dados.get("api_client_secret") or getattr(
                self.instance, "api_client_secret", ""
            )
            if not (tem_id and tem_secret):
                raise serializers.ValidationError({
                    "meio_integracao": (
                        "Integração por API exige client_id e client_secret. "
                        "Sem eles, nenhum título seria registrado."
                    )
                })
        return dados

    def update(self, instancia, dados):
        # Campo de segredo enviado vazio significa "não mexer", não "apagar":
        # o formulário reenvia o objeto inteiro e os write_only voltam em
        # branco por não terem sido exibidos. Sem isto, salvar o cadastro para
        # trocar o telefone apagaria a credencial do banco.
        for campo in ("api_client_id", "api_client_secret", "api_certificado",
                      "api_chave_privada", "sftp_senha"):
            if campo in dados and not dados[campo]:
                dados.pop(campo)
        return super().update(instancia, dados)


class ArquivoBancarioSerializer(TenantModelSerializer):
    tipo_label = serializers.CharField(source="get_tipo_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    banco_label = serializers.CharField(source="get_banco_display", read_only=True)
    conta_nome = serializers.CharField(source="conta.nome", read_only=True)
    download = serializers.SerializerMethodField()

    class Meta:
        model = ArquivoBancario
        fields = [
            "id", "uuid", "conta", "conta_nome", "banco", "banco_label", "tipo",
            "tipo_label", "nome_original", "hash_arquivo", "tamanho_bytes",
            "recebido_em", "processado_em", "data_movimento",
            "quantidade_registros", "quantidade_processada", "quantidade_com_erro",
            "valor_total", "status", "status_label", "mensagem_erro", "origem",
            "download", "criado_em",
        ]
        read_only_fields = fields

    def get_download(self, obj):
        """Link assinado e com prazo — o arquivo carrega a carteira inteira."""
        return url_assinada(obj.arquivo, self.context.get("request"))


class LoteBancarioSerializer(TenantModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    conta_nome = serializers.CharField(source="conta.nome", read_only=True)
    banco = serializers.CharField(source="conta.banco", read_only=True)
    arquivo = ArquivoBancarioSerializer(source="arquivo_remessa", read_only=True)
    criado_por_nome = serializers.CharField(
        source="criado_por.nome_completo", read_only=True
    )

    class Meta:
        model = LoteBancario
        fields = [
            "id", "uuid", "numero", "conta", "conta_nome", "banco", "status",
            "status_label", "quantidade", "quantidade_confirmada",
            "quantidade_rejeitada", "valor_total", "numero_remessa",
            "protocolo_banco", "progresso", "etapa", "mensagem_erro",
            "enviado_em", "confirmado_em", "criado_por", "criado_por_nome",
            "arquivo", "criado_em", "atualizado_em",
        ]
        read_only_fields = fields


class CriarLoteSerializer(serializers.Serializer):
    conta_bancaria = serializers.IntegerField()
    cobrancas = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=False,
        help_text="Ids das cobranças a incluir. O sistema valida uma a uma e "
                  "informa quais ficaram de fora, sem recusar o lote inteiro.",
    )
    enviar = serializers.BooleanField(
        default=False,
        help_text="Transmitir logo após montar, quando a conta tem canal automático.",
    )


class OcorrenciaBancariaSerializer(TenantModelSerializer):
    tipo_label = serializers.CharField(source="get_tipo_display", read_only=True)
    arquivo_nome = serializers.CharField(source="arquivo.nome_original", read_only=True)
    cobranca_numero = serializers.IntegerField(source="cobranca.numero", read_only=True)
    cliente_nome = serializers.CharField(source="cobranca.cliente.nome", read_only=True)

    class Meta:
        model = OcorrenciaBancaria
        fields = [
            "id", "uuid", "arquivo", "arquivo_nome", "cobranca", "cobranca_numero",
            "cliente_nome", "linha", "tipo", "tipo_label", "codigo", "descricao",
            "motivos", "motivos_descricao", "nosso_numero", "seu_numero",
            "data_ocorrencia", "data_credito", "valor_titulo", "valor_pago",
            "valor_juros", "valor_multa", "valor_desconto", "valor_abatimento",
            "valor_tarifa", "banco_recebedor", "agencia_recebedora", "aplicada",
            "criado_em",
        ]
        read_only_fields = fields
