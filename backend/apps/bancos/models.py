"""Conta bancária, lote, arquivo e ocorrência.

Estes quatro modelos são a fronteira entre o sistema e o banco. Tudo que o
banco disse fica aqui, em bruto e imutável; o efeito disso sobre a cobrança
mora em `apps.cobrancas`. A separação é a regra 22: a cobrança é a verdade
interna, o retorno é a verdade do banco, e as duas se encontram por
`identificador_bancario` — nunca por PDF, nunca por valor, nunca por "o
cliente disse que pagou".
"""
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from apps.bancos.bancos import (
    CodigoBanco,
    EspecieTitulo,
    MeioDeIntegracao,
    StatusArquivo,
    StatusLote,
    TipoArquivo,
    TipoOcorrencia,
)
from core.cripto import CampoCifrado
from core.midia import upload_arquivo_banco
from core.models import TenantModel
from core.validadores import validar_arquivo_bancario

apenas_digitos = RegexValidator(r"^\d*$", "Informe apenas números.")


class ContaBancaria(TenantModel):
    """Convênio de cobrança de uma empresa num banco.

    Uma empresa pode ter várias: contas diferentes, carteiras diferentes,
    bancos diferentes. A cobrança aponta para uma delas, e é essa conta que
    determina o adapter usado, a numeração do "nosso número" e o dinheiro que
    entra.
    """

    nome = models.CharField(
        max_length=80,
        help_text="Como esta conta aparece nas telas. Ex.: 'Safra — Matriz'.",
    )
    banco = models.CharField(max_length=3, choices=CodigoBanco.choices, db_index=True)
    meio_integracao = models.CharField(
        max_length=10, choices=MeioDeIntegracao.choices, default=MeioDeIntegracao.CNAB400
    )

    agencia = models.CharField(max_length=5, validators=[apenas_digitos])
    agencia_dv = models.CharField(max_length=1, blank=True)
    conta = models.CharField(max_length=12, validators=[apenas_digitos])
    conta_dv = models.CharField(max_length=1, blank=True)

    #: Carteira de cobrança contratada. No Safra, define se o título é
    #: registrado e como o "nosso número" é composto — trocar depois de emitir
    #: invalida a numeração já usada.
    carteira = models.CharField(max_length=3, default="1")
    #: Código do cedente/beneficiário junto ao banco. É o que identifica a
    #: empresa no arquivo; o banco fornece na abertura do convênio.
    codigo_cedente = models.CharField(max_length=20, blank=True)
    variacao_carteira = models.CharField(max_length=3, blank=True)

    especie_titulo = models.CharField(
        max_length=2, choices=EspecieTitulo.choices, default=EspecieTitulo.DUPLICATA_SERVICO
    )
    aceite = models.BooleanField(
        default=False,
        help_text="Título aceito pelo sacado. Quase sempre 'N' em cobrança de serviço.",
    )

    # --------------------------------------------------------- numeração
    #: Sequencial do "nosso número". Cada título registrado consome um, e ele
    #: nunca volta atrás: reaproveitar número dentro da janela em que o banco
    #: ainda guarda o título anterior faz o pagamento de um cair no outro.
    #: A reserva é feita com `SELECT ... FOR UPDATE` (ver `reservar_faixa`).
    proximo_nosso_numero = models.BigIntegerField(
        default=1, validators=[MinValueValidator(1)]
    )
    nosso_numero_maximo = models.BigIntegerField(
        default=99999999,
        help_text="Teto da faixa contratada com o banco. Ao chegar perto, o "
                  "sistema avisa antes de estourar.",
    )
    #: Sequencial do arquivo de remessa (NSA). O banco recusa arquivo com
    #: sequencial repetido — é o que evita processar duas vezes a mesma
    #: remessa se ela for reenviada por engano.
    proxima_remessa = models.PositiveIntegerField(default=1)

    # ------------------------------------------------- instruções padrão
    dias_protesto = models.PositiveSmallIntegerField(
        default=0, help_text="0 = não protestar."
    )
    dias_baixa_automatica = models.PositiveSmallIntegerField(
        default=0, help_text="0 = não baixar automaticamente."
    )
    # Limites em Decimal, não em int: o DRF os repassa ao campo do serializer,
    # e um limite inteiro num campo decimal gera aviso e comparação entre
    # tipos diferentes.
    juros_mes_percentual = models.DecimalField(
        max_digits=6, decimal_places=3, default=0,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Juros de mora ao mês, em %. Aplicado a partir do dia seguinte "
                  "ao vencimento.",
    )
    multa_percentual = models.DecimalField(
        max_digits=6, decimal_places=3, default=0,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    instrucoes_boleto = models.TextField(
        blank=True, help_text="Texto impresso no boleto, abaixo do vencimento."
    )

    # ------------------------------------------------------ credenciais
    # Fora de claro no banco de dados (core/cripto.py). Não protege contra
    # invasão do servidor — protege o dump que sai dele: backup extraviado,
    # réplica esquecida, acesso de manutenção ao Postgres.
    api_client_id = CampoCifrado(max_length=512, blank=True)
    api_client_secret = CampoCifrado(max_length=1024, blank=True)
    #: Certificado mTLS em PEM, quando o banco exige. Guardado cifrado pelo
    #: mesmo motivo, e escrito no disco só em memória do worker, na hora da
    #: chamada — nunca em arquivo permanente.
    api_certificado = CampoCifrado(max_length=8192, blank=True)
    api_chave_privada = CampoCifrado(max_length=8192, blank=True)
    sftp_host = models.CharField(max_length=180, blank=True)
    sftp_porta = models.PositiveIntegerField(default=22)
    sftp_usuario = models.CharField(max_length=120, blank=True)
    sftp_senha = CampoCifrado(max_length=512, blank=True)
    sftp_dir_remessa = models.CharField(max_length=255, blank=True)
    sftp_dir_retorno = models.CharField(max_length=255, blank=True)

    #: Ambiente do banco. Homologação é o padrão: subir apontando para
    #: produção por esquecimento registra título de verdade e gera tarifa de
    #: verdade.
    producao = models.BooleanField(default=False)
    ativa = models.BooleanField(default=True, db_index=True)
    padrao = models.BooleanField(
        default=False, help_text="Conta sugerida ao criar uma cobrança."
    )

    class Meta:
        db_table = "contas_bancarias"
        ordering = ("banco", "nome")
        verbose_name = "Conta bancária"
        verbose_name_plural = "Contas bancárias"
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "banco", "agencia", "conta", "carteira"],
                name="uniq_conta_carteira_por_empresa",
            ),
            # Uma conta padrão por empresa. Duas fariam a tela escolher
            # arbitrariamente, e a cobrança sairia pelo convênio errado.
            models.UniqueConstraint(
                fields=["empresa"],
                condition=models.Q(padrao=True),
                name="uniq_conta_padrao_por_empresa",
            ),
        ]
        indexes = [models.Index(fields=["empresa", "ativa"])]

    def __str__(self) -> str:
        return f"{self.nome} ({self.get_banco_display()})"

    @property
    def agencia_conta(self) -> str:
        ag = f"{self.agencia}-{self.agencia_dv}" if self.agencia_dv else self.agencia
        cc = f"{self.conta}-{self.conta_dv}" if self.conta_dv else self.conta
        return f"{ag} / {cc}"

    @property
    def integrada(self) -> bool:
        from apps.bancos.bancos import BANCOS_INTEGRADOS

        return self.banco in BANCOS_INTEGRADOS

    @property
    def credenciais_configuradas(self) -> bool:
        if self.meio_integracao == MeioDeIntegracao.API:
            return bool(self.api_client_id and self.api_client_secret)
        # CNAB não exige credencial para *gerar* o arquivo — só para
        # transmiti-lo. Gerar e baixar à mão é caminho legítimo e comum.
        return True

    @property
    def transmissao_automatica(self) -> bool:
        """Se falso, a remessa é gerada e fica para download; o operador leva
        ao internet banking. É o fluxo da maioria das empresas hoje."""
        if self.meio_integracao == MeioDeIntegracao.API:
            return self.credenciais_configuradas
        return bool(self.sftp_host and self.sftp_usuario)

    # ------------------------------------------------------------ numeração
    def reservar_faixa(self, quantidade: int) -> range:
        """Reserva `quantidade` "nossos números" de uma vez, sob lock de linha.

        Um `UPDATE ... SET proximo = proximo + n` resolveria a corrida, mas não
        devolveria a faixa reservada. Aqui a linha é travada, lida, avançada e
        liberada no commit — dois lotes simultâneos na mesma conta pegam faixas
        disjuntas, que é a única coisa que importa.
        """
        from django.db import transaction

        from core.services import RegraDeNegocioError

        if quantidade <= 0:
            return range(0)
        with transaction.atomic():
            conta = ContaBancaria.objects.select_for_update().get(pk=self.pk)
            inicio = conta.proximo_nosso_numero
            fim = inicio + quantidade
            if fim - 1 > conta.nosso_numero_maximo:
                raise RegraDeNegocioError(
                    f"A faixa de nosso número da conta '{conta.nome}' acabou "
                    f"(atual {inicio}, teto {conta.nosso_numero_maximo}). "
                    "Peça uma faixa nova ao banco antes de registrar mais títulos.",
                    "conta_bancaria",
                )
            conta.proximo_nosso_numero = fim
            conta.save(update_fields=["proximo_nosso_numero", "atualizado_em"])
        self.proximo_nosso_numero = fim
        return range(inicio, fim)

    def reservar_remessa(self) -> int:
        """Próximo NSA, sob o mesmo lock e pelo mesmo motivo."""
        from django.db import transaction

        with transaction.atomic():
            conta = ContaBancaria.objects.select_for_update().get(pk=self.pk)
            numero = conta.proxima_remessa
            conta.proxima_remessa = numero + 1
            conta.save(update_fields=["proxima_remessa", "atualizado_em"])
        self.proxima_remessa = numero + 1
        return numero


class ArquivoBancario(TenantModel):
    """Todo arquivo que entrou ou saiu, com hash. É o controle da regra 13.

    O hash existe para uma pergunta só: "este arquivo já foi processado?".
    Nome de arquivo não serve — o banco republica o mesmo retorno com nomes
    diferentes, e o operador baixa duas vezes. Conteúdo idêntico é o mesmo
    movimento, e processá-lo de novo duplicaria pagamento.
    """

    conta = models.ForeignKey(
        ContaBancaria, on_delete=models.PROTECT, related_name="arquivos",
        null=True, blank=True,
        help_text="Retorno chega antes de se saber a conta; é preenchida na "
                  "identificação do cabeçalho.",
    )
    banco = models.CharField(max_length=3, choices=CodigoBanco.choices, db_index=True)
    tipo = models.CharField(max_length=8, choices=TipoArquivo.choices, db_index=True)

    nome_original = models.CharField(
        max_length=255,
        help_text="O nome que o banco deu. É por ele que o suporte do banco procura.",
    )
    arquivo = models.FileField(
        upload_to=upload_arquivo_banco, validators=[validar_arquivo_bancario]
    )
    #: SHA-256 do conteúdo. Único por empresa: a mesma empresa não processa o
    #: mesmo arquivo duas vezes, e empresas diferentes podem receber arquivos
    #: idênticos por coincidência (ambos vazios, por exemplo).
    hash_arquivo = models.CharField(max_length=64, db_index=True)
    tamanho_bytes = models.BigIntegerField(default=0)

    recebido_em = models.DateTimeField(db_index=True)
    processado_em = models.DateTimeField(null=True, blank=True, db_index=True)
    #: Data do movimento declarada no cabeçalho do próprio arquivo — não é a
    #: data em que ele chegou aqui. Retorno de sexta processado na segunda tem
    #: as duas diferentes, e é a do banco que vale na conciliação.
    data_movimento = models.DateField(null=True, blank=True, db_index=True)

    quantidade_registros = models.PositiveIntegerField(default=0)
    quantidade_processada = models.PositiveIntegerField(default=0)
    quantidade_com_erro = models.PositiveIntegerField(default=0)
    valor_total = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    status = models.CharField(
        max_length=24, choices=StatusArquivo.choices,
        default=StatusArquivo.PENDENTE, db_index=True,
    )
    mensagem_erro = models.TextField(blank=True)
    #: Origem: 'UPLOAD' (operador), 'SFTP', 'API', 'SISTEMA' (remessa gerada).
    origem = models.CharField(max_length=12, default="UPLOAD")

    class Meta:
        db_table = "bank_files"
        ordering = ("-recebido_em",)
        verbose_name = "Arquivo bancário"
        verbose_name_plural = "Arquivos bancários"
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "hash_arquivo"], name="uniq_hash_arquivo_por_empresa"
            ),
        ]
        indexes = [
            models.Index(fields=["empresa", "tipo", "-recebido_em"]),
            models.Index(fields=["empresa", "status"]),
            models.Index(fields=["status", "tipo"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} {self.nome_original}"

    @property
    def processavel(self) -> bool:
        return self.status in (StatusArquivo.PENDENTE, StatusArquivo.ERRO)


class LoteBancario(TenantModel):
    """Um envio de N cobranças ao banco.

    O lote é a unidade que o usuário enxerga ("Lote #123, 500 títulos") e a
    unidade de retomada: falhou no meio, reprocessa o lote, não as 500
    cobranças uma a uma.
    """

    numero = models.PositiveIntegerField(db_index=True, editable=False)
    conta = models.ForeignKey(
        ContaBancaria, on_delete=models.PROTECT, related_name="lotes"
    )
    status = models.CharField(
        max_length=12, choices=StatusLote.choices,
        default=StatusLote.RASCUNHO, db_index=True,
    )

    quantidade = models.PositiveIntegerField(default=0)
    quantidade_confirmada = models.PositiveIntegerField(default=0)
    quantidade_rejeitada = models.PositiveIntegerField(default=0)
    valor_total = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    #: Sequencial do arquivo de remessa (NSA) consumido por este lote.
    numero_remessa = models.PositiveIntegerField(null=True, blank=True)
    arquivo_remessa = models.ForeignKey(
        ArquivoBancario, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="lotes",
    )
    #: O que o banco devolveu ao aceitar o envio: protocolo do internet
    #: banking, id da API, nome do arquivo no SFTP. Texto livre de propósito —
    #: cada banco chama de uma coisa, e o valor serve para o suporte.
    protocolo_banco = models.CharField(max_length=120, blank=True, db_index=True)

    #: 0 a 100. É o que a tela mostra enquanto o worker trabalha; sem isto o
    #: usuário fica olhando um spinner sem saber se travou.
    progresso = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(100)]
    )
    etapa = models.CharField(max_length=80, blank=True)
    mensagem_erro = models.TextField(blank=True)

    enviado_em = models.DateTimeField(null=True, blank=True)
    confirmado_em = models.DateTimeField(null=True, blank=True)
    criado_por = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="lotes_criados",
    )
    #: Id da tarefa Celery em curso. Permite cancelar e permite responder
    #: "está rodando há 40 minutos" em vez de "não sei".
    task_id = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "bank_batches"
        ordering = ("-numero",)
        verbose_name = "Lote bancário"
        verbose_name_plural = "Lotes bancários"
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "numero"], name="uniq_numero_lote_por_empresa"
            ),
        ]
        indexes = [
            models.Index(fields=["empresa", "status", "-numero"]),
            models.Index(fields=["empresa", "conta", "-criado_em"]),
        ]

    def __str__(self) -> str:
        return f"Lote #{self.numero} ({self.quantidade} títulos)"

    def save(self, *args, **kwargs):
        if self.numero is None:
            self.numero = self._proximo_numero(self.empresa_id)
        super().save(*args, **kwargs)

    @staticmethod
    def _proximo_numero(empresa_id: int) -> int:
        from django.db.models.functions import Coalesce

        agregado = LoteBancario.objects.filter(empresa_id=empresa_id).aggregate(
            ultimo=Coalesce(models.Max("numero"), 0)
        )
        return agregado["ultimo"] + 1

    def marcar_progresso(self, pct: int, etapa: str = "") -> None:
        """Escrita barata e frequente: só estes campos, sem tocar no resto."""
        self.progresso = max(0, min(100, int(pct)))
        if etapa:
            self.etapa = etapa[:80]
        LoteBancario.objects.filter(pk=self.pk).update(
            progresso=self.progresso, etapa=self.etapa
        )


class OcorrenciaBancaria(TenantModel):
    """Uma linha de retorno do banco, guardada como o banco mandou.

    Append-only por decisão: é a prova documental de por que uma cobrança
    mudou de estado. Se o efeito aplicado estiver errado, corrige-se o efeito
    e reprocessa — o registro do que o banco disse não se reescreve.
    """

    arquivo = models.ForeignKey(
        ArquivoBancario, on_delete=models.CASCADE, related_name="ocorrencias"
    )
    cobranca = models.ForeignKey(
        "cobrancas.Cobranca", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ocorrencias",
        help_text="Nulo quando o título do retorno não existe aqui — acontece "
                  "com título emitido direto no internet banking.",
    )

    #: Posição da linha dentro do arquivo (1-based). Junto com `arquivo`, é a
    #: chave natural que torna o reprocessamento idempotente.
    linha = models.PositiveIntegerField()
    tipo = models.CharField(max_length=24, choices=TipoOcorrencia.choices, db_index=True)
    #: Código cru do banco ('06', '02', ...). Preservado porque o suporte do
    #: banco fala nesses códigos, não nos nossos.
    codigo = models.CharField(max_length=4, db_index=True)
    descricao = models.CharField(max_length=180, blank=True)
    #: Códigos de motivo de rejeição, do jeito que vieram. Um título rejeitado
    #: costuma trazer até cinco.
    motivos = models.JSONField(default=list, blank=True)
    motivos_descricao = models.CharField(max_length=500, blank=True)

    nosso_numero = models.CharField(max_length=20, blank=True, db_index=True)
    seu_numero = models.CharField(max_length=40, blank=True, db_index=True)
    data_ocorrencia = models.DateField(null=True, blank=True, db_index=True)
    data_credito = models.DateField(null=True, blank=True)
    valor_titulo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_pago = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_juros = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_multa = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_desconto = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_abatimento = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_tarifa = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    #: Onde o título foi pago. Útil no suporte ("paguei na lotérica").
    banco_recebedor = models.CharField(max_length=3, blank=True)
    agencia_recebedora = models.CharField(max_length=8, blank=True)

    aplicada = models.BooleanField(
        default=False, db_index=True,
        help_text="Se o efeito sobre a cobrança já foi aplicado. Falso e com "
                  "cobrança nula = título órfão, tratado na tela de pendências.",
    )
    conteudo_linha = models.TextField(
        blank=True,
        help_text="A linha crua. Ocupa espaço e vale cada byte no dia em que "
                  "o banco e o sistema discordam.",
    )

    class Meta:
        db_table = "bank_occurrences"
        ordering = ("arquivo_id", "linha")
        verbose_name = "Ocorrência bancária"
        verbose_name_plural = "Ocorrências bancárias"
        constraints = [
            # A chave da idempotência: reprocessar o mesmo arquivo tenta
            # regravar as mesmas (arquivo, linha) e o banco recusa. Nenhum
            # pagamento é criado duas vezes nem que se rode o worker dez vezes.
            models.UniqueConstraint(
                fields=["arquivo", "linha"], name="uniq_ocorrencia_por_linha"
            ),
        ]
        indexes = [
            models.Index(fields=["empresa", "tipo", "-data_ocorrencia"]),
            models.Index(fields=["empresa", "nosso_numero"]),
            models.Index(fields=["cobranca", "-data_ocorrencia"]),
            models.Index(fields=["empresa", "aplicada"]),
        ]

    def __str__(self) -> str:
        return f"{self.codigo} {self.get_tipo_display()} — {self.nosso_numero}"
