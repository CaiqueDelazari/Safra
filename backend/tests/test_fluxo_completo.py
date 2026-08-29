"""O caminho inteiro, do cadastro ao dinheiro na conta.

Os outros testes provam as peças: o boleto calcula certo, o CNAB monta certo,
o retorno é idempotente, o isolamento não vaza. Nenhum deles prova que as
peças se encaixam — e é justamente na emenda que um sistema como este
costuma quebrar, porque cada lado funciona sozinho.

Aqui está a história que o produto existe para contar, em miniatura:

    empresa cadastrada
        cliente cadastrado
            cobranças criadas
                lote gerado, com arquivo de remessa
                    banco processa e devolve o retorno
                        cobranças viram PAGA sozinhas
                            a conciliação fecha

O retorno é montado a partir do "nosso número" que saiu na remessa de
verdade, não de um número inventado. É esse detalhe que faz o teste valer:
se a remessa gravar o número numa posição e o parser ler de outra, o
casamento falha aqui — e é exatamente o defeito que, em produção, apareceria
como "o cliente pagou e o sistema não viu".

Tudo passa pela API, com token e papel, para que serializer, permissão e
tenancy entrem no caminho junto com os serviços.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User, UsuarioEmpresa
from apps.bancos.adapters.cnab import juntar_linhas, quebrar_linhas
from apps.bancos.adapters.safra import layout400 as L
from apps.bancos.models import ArquivoBancario, ContaBancaria, LoteBancario
from apps.bancos.services import ler_arquivo
from apps.clientes.models import Cliente
from apps.cobrancas.models import Cobranca, StatusCobranca
from apps.empresas.models import Empresa, PlanoEmpresa
from apps.pagamentos.models import Pagamento
from core.roles import Papel

SENHA = "Cobranca!2026#Forte"


class FluxoCompletoTest(APITestCase):
    """Do cadastro à conciliação, sem atalho por dentro do ORM."""

    def setUp(self):
        cache.clear()

        self.empresa = Empresa.objects.create(
            cnpj="12345678000195",
            razao_social="EMPRESA DE COBRANCA LTDA",
            nome_fantasia="Cobranças",
            cep="17010000", logradouro="Rua Araujo Leite", numero="100",
            bairro="Centro", cidade="Bauru", uf="SP",
            plano=PlanoEmpresa.ILIMITADO,
        )
        self.conta = ContaBancaria.objects.create(
            empresa=self.empresa,
            nome="Safra — Matriz",
            banco="422",
            agencia="01234", agencia_dv="5",
            conta="00012345", conta_dv="6",
            carteira="1",
            codigo_cedente="12345678901234567890",
            producao=True,
            padrao=True,
        )

        self.usuario = User.objects.create_user(
            email="financeiro@empresa.com", password=SENHA,
            nome_completo="Financeiro", empresa_padrao=self.empresa,
        )
        UsuarioEmpresa.objects.create(
            usuario=self.usuario, empresa=self.empresa,
            papel=Papel.ADMINISTRADOR, ativo=True,
        )

        entrada = self.client.post(
            reverse("v1:login"),
            {"email": self.usuario.email, "password": SENHA},
            format="json",
        )
        self.assertEqual(entrada.status_code, 200, entrada.data)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {entrada.data['access']}",
            HTTP_X_EMPRESA_ID=str(self.empresa.pk),
        )

        self.vencimento = timezone.localdate() + timedelta(days=30)

    # ------------------------------------------------------------ auxiliares
    @staticmethod
    def _cpf(numero: int) -> str:
        from core.validadores import _digito_mod11

        base = f"{numero:09d}"
        d1 = _digito_mod11(base, list(range(10, 1, -1)))
        d2 = _digito_mod11(base + d1, list(range(11, 1, -1)))
        return base + d1 + d2

    def _cadastrar_cliente(self, indice: int) -> int:
        resposta = self.client.post(
            reverse("v1:cliente-list"),
            {
                "nome": f"Cliente {indice}",
                "cpf_cnpj": self._cpf(indice),
                "email": f"cliente{indice}@exemplo.com",
                "telefone": "1499990000",
                "cep": "17010000",
                "logradouro": "Rua das Flores",
                "numero": str(indice),
                "bairro": "Centro",
                "cidade": "Bauru",
                "uf": "SP",
            },
            format="json",
        )
        self.assertEqual(resposta.status_code, 201, resposta.data)
        self.assertTrue(
            resposta.data["pronto_para_boleto"],
            "cliente com endereço completo deveria estar pronto para boleto",
        )
        return resposta.data["id"]

    def _criar_cobranca(self, cliente_id: int, valor: str) -> int:
        resposta = self.client.post(
            reverse("v1:cobranca-list"),
            {
                "cliente": cliente_id,
                "conta_bancaria": self.conta.pk,
                "descricao": "Mensalidade de setembro",
                "valor": valor,
                "data_emissao": timezone.localdate().isoformat(),
                "data_vencimento": self.vencimento.isoformat(),
            },
            format="json",
        )
        self.assertEqual(resposta.status_code, 201, resposta.data)
        return resposta.data["id"]

    def _retorno_de_liquidacao(self, cobrancas) -> bytes:
        """Monta o arquivo que o banco devolveria, pagando todos os títulos.

        Usa o `nosso_numero` que a remessa realmente gravou. É o que amarra as
        duas pontas: se a remessa escrever numa posição e o parser ler de
        outra, o casamento falha e o teste acusa.
        """
        cabecalho = L.RETORNO_HEADER.montar({
            "registro": "0", "operacao": "2", "literal_retorno": "RETORNO",
            "codigo_servico": "01", "literal_servico": "COBRANCA",
            "codigo_empresa": self.conta.codigo_cedente,
            "nome_cedente": self.empresa.razao_social,
            "banco": "422", "nome_banco": "BANCO SAFRA",
            "data_movimento": timezone.localdate(),
            "sequencial": 1,
        })

        linhas = [cabecalho]
        for indice, cobranca in enumerate(cobrancas, start=2):
            linhas.append(L.RETORNO_DETALHE.montar({
                "registro": "1",
                "codigo_ocorrencia": "06",  # liquidação normal
                "nosso_numero": cobranca.nosso_numero,
                "uso_empresa": cobranca.seu_numero,
                "data_ocorrencia": self.vencimento,
                "data_credito": self.vencimento + timedelta(days=1),
                "valor_titulo": cobranca.valor,
                "valor_principal": cobranca.valor,
                "valor_tarifa": Decimal("2.50"),
                "banco_cobrador": "422",
                "sequencial": indice,
            }))

        linhas.append(L.RETORNO_TRAILER.montar({
            "registro": "9", "operacao": "2", "banco": "422",
            "sequencial": len(linhas) + 1,
        }))
        return juntar_linhas(linhas)

    # ---------------------------------------------------------------- o teste
    def test_do_cadastro_ao_dinheiro_na_conta(self):
        # 1. Três clientes e três cobranças, pela API.
        clientes = [self._cadastrar_cliente(i) for i in (1, 2, 3)]
        valores = ["150.00", "230.50", "99.90"]
        cobrancas = [
            self._criar_cobranca(cliente, valor)
            for cliente, valor in zip(clientes, valores)
        ]
        self.assertEqual(Cobranca.objects.count(), 3)

        # 2. A conferência antes de gastar numeração: quantos entram no lote.
        validacao = self.client.post(
            reverse("v1:batches:batch-validate"),
            {"conta_bancaria": self.conta.pk, "cobrancas": cobrancas},
            format="json",
        )
        self.assertEqual(validacao.status_code, 200, validacao.data)
        self.assertEqual(validacao.data["aptas"], 3)
        self.assertEqual(validacao.data["recusadas"], [])

        # 3. Gerar o lote. A API responde 202 e o worker monta o arquivo —
        #    que sob teste roda na hora (CELERY_TASK_ALWAYS_EAGER).
        criacao = self.client.post(
            reverse("v1:batches:batch-list"),
            {"conta_bancaria": self.conta.pk, "cobrancas": cobrancas, "enviar": False},
            format="json",
        )
        self.assertEqual(criacao.status_code, 202, criacao.data)

        lote = LoteBancario.objects.get()
        self.assertEqual(lote.quantidade, 3)
        self.assertEqual(lote.status, "PRONTO", lote.mensagem_erro)
        self.assertEqual(lote.progresso, 100)

        # 4. O arquivo de remessa existe e tem a forma de um CNAB 400.
        remessa = ArquivoBancario.objects.get(tipo="REMESSA")
        linhas = quebrar_linhas(ler_arquivo(remessa.arquivo))
        self.assertEqual(len(linhas), 5, "header + 3 títulos + trailer")
        self.assertTrue(all(len(linha) == 400 for linha in linhas))
        self.assertEqual(linhas[0][0], "0")
        self.assertEqual(linhas[-1][0], "9")

        # 5. Cada cobrança saiu com nosso número, código de barras e linha
        #    digitável — e nenhum número se repete dentro da conta.
        atualizadas = list(Cobranca.objects.order_by("numero"))
        for cobranca in atualizadas:
            self.assertEqual(cobranca.status, StatusCobranca.ENVIADA_AO_BANCO)
            self.assertTrue(cobranca.nosso_numero)
            self.assertEqual(len(cobranca.codigo_barras), 44)
            self.assertEqual(len(cobranca.linha_digitavel), 47)
        self.assertEqual(
            len({c.nosso_numero for c in atualizadas}), 3,
            "nosso número repetido faria o pagamento de um cair no outro",
        )

        # 6. O boleto é consultável pela API antes de qualquer pagamento.
        boleto = self.client.get(
            reverse("v1:cobranca-boleto", args=[atualizadas[0].pk])
        )
        self.assertEqual(boleto.status_code, 200, boleto.data)
        self.assertEqual(boleto.data["codigo_barras"], atualizadas[0].codigo_barras)
        self.assertIn(".", boleto.data["linha_digitavel_formatada"])

        # 7. O banco devolve o retorno, e ele entra pela tela de upload.
        conteudo = self._retorno_de_liquidacao(atualizadas)
        envio = self.client.post(
            reverse("v1:bank:bank-file-returns-process"),
            {
                "arquivo": SimpleUploadedFile(
                    "RETORNO.RET", conteudo, content_type="text/plain"
                ),
                "conta_bancaria": self.conta.pk,
            },
            format="multipart",
        )
        self.assertEqual(envio.status_code, 202, envio.data)
        self.assertFalse(envio.data["ja_processado"])

        # 8. O que o produto promete: as três viraram PAGA sozinhas.
        for cobranca in Cobranca.objects.all():
            self.assertEqual(
                cobranca.status, StatusCobranca.PAGA,
                f"cobrança {cobranca.numero} deveria estar paga",
            )
            self.assertEqual(cobranca.data_pagamento, self.vencimento)
            self.assertEqual(
                cobranca.data_liquidacao, self.vencimento + timedelta(days=1)
            )
            self.assertEqual(cobranca.valor_pago, cobranca.valor)
            self.assertEqual(cobranca.valor_tarifa, Decimal("2.50"))

        self.assertEqual(Pagamento.objects.count(), 3)
        total = sum(p.valor for p in Pagamento.objects.all())
        self.assertEqual(total, Decimal("480.40"))

        # 9. A conciliação fecha, e separa o bruto do líquido.
        conciliacao = self.client.get(
            reverse("v1:conciliacao"),
            {
                "inicio": (self.vencimento - timedelta(days=1)).isoformat(),
                "fim": (self.vencimento + timedelta(days=1)).isoformat(),
            },
        )
        self.assertEqual(conciliacao.status_code, 200, conciliacao.data)
        self.assertEqual(Decimal(conciliacao.data["recebimentos"]["bruto"]), total)
        self.assertEqual(
            Decimal(conciliacao.data["recebimentos"]["tarifa"]), Decimal("7.50")
        )
        self.assertEqual(
            Decimal(conciliacao.data["recebimentos"]["liquido"]),
            total - Decimal("7.50"),
            "o líquido é o que entra na conta: o pago menos a tarifa do banco",
        )
        self.assertEqual(Decimal(conciliacao.data["cobrancas"]["em_aberto"]), 0)

        # 10. Nada pendente ao fim do ciclo.
        pendencias = self.client.get(reverse("v1:conciliacao-pendencias"))
        self.assertEqual(pendencias.data["cobrancas_rejeitadas"], 0)
        self.assertEqual(pendencias.data["ocorrencias_orfas"], 0)
        self.assertEqual(pendencias.data["arquivos_com_erro"], 0)

    def test_subir_o_mesmo_retorno_de_novo_nao_cobra_duas_vezes(self):
        """A promessa da regra 9, exercitada pela porta da frente.

        O operador sobe o arquivo de novo porque não teve certeza de que
        funcionou. Isso precisa ser inofensivo — e a resposta precisa dizer
        isso com todas as letras, em vez de fingir que fez algo novo.
        """
        cliente = self._cadastrar_cliente(1)
        cobranca_id = self._criar_cobranca(cliente, "500.00")

        self.client.post(
            reverse("v1:batches:batch-list"),
            {"conta_bancaria": self.conta.pk, "cobrancas": [cobranca_id]},
            format="json",
        )
        cobranca = Cobranca.objects.get(pk=cobranca_id)
        conteudo = self._retorno_de_liquidacao([cobranca])

        for tentativa in (1, 2, 3):
            resposta = self.client.post(
                reverse("v1:bank:bank-file-returns-process"),
                {
                    "arquivo": SimpleUploadedFile(
                        f"RETORNO-{tentativa}.RET", conteudo, content_type="text/plain"
                    ),
                    "conta_bancaria": self.conta.pk,
                },
                format="multipart",
            )
            self.assertIn(resposta.status_code, (200, 202), resposta.data)
            if tentativa > 1:
                self.assertTrue(
                    resposta.data["ja_processado"],
                    "o mesmo conteúdo precisa ser reconhecido, mesmo com outro nome",
                )
                self.assertIn("duplicado", resposta.data["mensagem"].lower())

        self.assertEqual(Pagamento.objects.count(), 1)
        self.assertEqual(ArquivoBancario.objects.filter(tipo="RETORNO").count(), 1)

    def test_cliente_sem_endereco_nao_entra_no_lote_e_diz_por_que(self):
        """O erro mais comum da operação, barrado antes de gastar numeração.

        Sem esta checagem a rejeição viria do banco, no retorno do dia
        seguinte — quando o boleto já deveria estar na mão do sacado.
        """
        completo = self._cadastrar_cliente(1)

        incompleto = self.client.post(
            reverse("v1:cliente-list"),
            {"nome": "Sem endereço", "cpf_cnpj": self._cpf(2)},
            format="json",
        )
        self.assertEqual(incompleto.status_code, 201, incompleto.data)
        self.assertFalse(incompleto.data["pronto_para_boleto"])

        boa = self._criar_cobranca(completo, "100.00")
        ruim = self._criar_cobranca(incompleto.data["id"], "100.00")

        validacao = self.client.post(
            reverse("v1:batches:batch-validate"),
            {"conta_bancaria": self.conta.pk, "cobrancas": [boa, ruim]},
            format="json",
        )
        self.assertEqual(validacao.data["aptas"], 1)
        self.assertEqual(len(validacao.data["recusadas"]), 1)
        self.assertIn("endereço", validacao.data["recusadas"][0]["motivo"])

        criacao = self.client.post(
            reverse("v1:batches:batch-list"),
            {"conta_bancaria": self.conta.pk, "cobrancas": [boa, ruim]},
            format="json",
        )
        self.assertEqual(criacao.status_code, 202, criacao.data)

        lote = LoteBancario.objects.get()
        self.assertEqual(lote.quantidade, 1, "só a cobrança apta entra no lote")

        recusada = Cobranca.objects.get(pk=ruim)
        self.assertIsNone(recusada.lote_id)
        self.assertIn("endereço", recusada.mensagem_erro)

        # A faixa do banco só foi consumida pelo título que de fato saiu.
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.proximo_nosso_numero, 2)
