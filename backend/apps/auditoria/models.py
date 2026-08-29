from django.db import models


class AcaoAuditoria(models.TextChoices):
    LOGIN = "LOGIN", "Login"
    LOGIN_FALHA = "LOGIN_FALHA", "Falha de login"
    LOGOUT = "LOGOUT", "Logout"
    TROCA_SENHA = "TROCA_SENHA", "Troca de senha"
    SEGUNDO_FATOR = "SEGUNDO_FATOR", "Segundo fator"
    CRIACAO = "CRIACAO", "Criação"
    EDICAO = "EDICAO", "Edição"
    EXCLUSAO = "EXCLUSAO", "Exclusão"
    EXPORTACAO = "EXPORTACAO", "Exportação"
    IMPORTACAO = "IMPORTACAO", "Importação em massa"
    # Os atos que movem dinheiro ou falam com o banco têm código próprio: numa
    # investigação, a pergunta nunca é "houve uma edição?" — é "quem mandou a
    # remessa e quando o retorno entrou?".
    COBRANCA_LOTE = "COBRANCA_LOTE", "Cobranças criadas em lote"
    COBRANCA_CANCELADA = "COBRANCA_CANCELADA", "Cobrança cancelada"
    COBRANCA_BAIXADA = "COBRANCA_BAIXADA", "Cobrança baixada"
    PAGAMENTO_MANUAL = "PAGAMENTO_MANUAL", "Baixa manual de pagamento"
    LOTE_CRIADO = "LOTE_CRIADO", "Lote criado"
    REMESSA_GERADA = "REMESSA_GERADA", "Remessa gerada"
    REMESSA_ENVIADA = "REMESSA_ENVIADA", "Remessa enviada ao banco"
    INSTRUCAO_ENVIADA = "INSTRUCAO_ENVIADA", "Instrução enviada ao banco"
    RETORNO_PROCESSADO = "RETORNO_PROCESSADO", "Retorno bancário processado"


class LogAuditoria(models.Model):
    """Append-only. Nada aqui é editável pela aplicação."""

    id = models.BigAutoField(primary_key=True)
    empresa = models.ForeignKey("empresas.Empresa", on_delete=models.SET_NULL, null=True,
                                blank=True, related_name="logs")
    usuario = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True,
                                blank=True, related_name="logs")
    usuario_nome = models.CharField(max_length=160, blank=True)

    acao = models.CharField(max_length=24, db_index=True)
    modulo = models.CharField(max_length=40, db_index=True)
    objeto_tipo = models.CharField(max_length=60, blank=True, db_index=True)
    objeto_id = models.CharField(max_length=40, blank=True, db_index=True)
    objeto_descricao = models.CharField(max_length=255, blank=True)
    descricao = models.CharField(max_length=500, blank=True)

    alteracoes = models.JSONField(default=dict, blank=True)
    metadados = models.JSONField(default=dict, blank=True)

    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "auditoria_logs"
        ordering = ("-criado_em",)
        verbose_name = "Log de auditoria"
        verbose_name_plural = "Logs de auditoria"
        indexes = [
            models.Index(fields=["empresa", "-criado_em"]),
            models.Index(fields=["empresa", "modulo", "-criado_em"]),
            models.Index(fields=["usuario", "-criado_em"]),
            models.Index(fields=["objeto_tipo", "objeto_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.criado_em:%d/%m/%Y %H:%M} {self.acao} {self.modulo}"
