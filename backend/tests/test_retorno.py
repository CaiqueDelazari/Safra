"""Processamento de retorno: a promessa de não duplicar pagamento.

A regra 9 do enunciado diz que processar o mesmo arquivo duas vezes não pode
duplicar pagamento. Este é o arquivo de teste que transforma essa frase em
garantia — e ele exercita o caminho inteiro: arquivo em bytes, ocorrências
gravadas, cobrança atualizada, pagamento criado.

Os casos foram escolhidos pelo que acontece de verdade na operação, não pelo
que é fácil de testar: o operador que sobe o arquivo duas vezes porque "não
pareceu ter funcionado", o título que chega no retorno antes de existir aqui,
o banco que manda baixa depois da liquidação.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.bancos.adapters.cnab import juntar_linhas
from apps.bancos.adapters.safra import layout400 as L
from apps.bancos.bancos import StatusArquivo, TipoArquivo
from apps.bancos.models import ArquivoBancario, ContaBancaria, OcorrenciaBancaria
from apps.bancos.services import RetornoService
from apps.clientes.models import Cliente
from apps.cobrancas.models import Cobranca, StatusCobranca
from apps.empresas.models import Empresa
from apps.pagamentos.models import Pagamento
from core.context import use_context


def montar_retorno(detalhes: list[dict], *, banco: str = "422") -> bytes:
    header = L.RETORNO_HEADER.montar({
        "registro": "0", "operacao": "2", "literal_retorno": "RETORNO",
        "codigo_servico": "01", "literal_servico": "COBRANCA",
        "codigo_empresa": "12345", "nome_cedente": "EMPRESA TESTE",
        "banco": banco, "nome_banco": "BANCO SAFRA",
        "data_movimento": date(2026, 9, 11), "sequencial": 1,
    })
    linhas = [header]
    for indice, dados in enumerate(detalhes, start=2):
        linhas.append(
            L.RETORNO_DETALHE.montar({"registro": "1", "sequencial": indice, **dados})
        )
    linhas.append(L.RETORNO_TRAILER.montar({
        "registro": "9", "operacao": "2", "banco": banco, "sequencial": len(linhas) + 1,
    }))
    return juntar_linhas(linhas)


class BaseRetornoTest(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            cnpj="12345678000195", razao_social="EMPRESA TESTE LTDA",
            nome_fantasia="Teste", cep="01310100", logradouro="Av Paulista",
            numero="1000", cidade="Sao Paulo", uf="SP",
        )
        self.conta = ContaBancaria.objects.create(
            empresa=self.empresa, nome="Safra", banco="422",
            agencia="01234", conta="00012345", conta_dv="6", carteira="1",
        )
        self.cliente = Cliente.objects.create(
            empresa=self.empresa, nome="Cliente Teste", cpf_cnpj="12345678000195",
            cep="01310100", logradouro="Rua A", numero="1",
            cidade="Sao Paulo", uf="SP",
        )
        self.cobranca = Cobranca.objects.create(
            empresa=self.empresa, cliente=self.cliente, conta_bancaria=self.conta,
            descricao="Mensalidade", valor=Decimal("1000.00"),
            data_emissao=date(2026, 8, 1), data_vencimento=date(2026, 9, 10),
            nosso_numero="123456789", seu_numero="1",
            status=StatusCobranca.REGISTRADA,
        )

    def processar(self, conteudo: bytes, nome: str = "RET001.RET"):
        with use_context(empresa_id=self.empresa.pk):
            arquivo, novo = RetornoService.registrar_arquivo(
                empresa_id=self.empresa.pk, nome=nome, conteudo=conteudo,
                banco="422", conta=self.conta,
            )
            resumo = RetornoService.processar(arquivo)
        return arquivo, novo, resumo


class LiquidacaoTest(BaseRetornoTest):
    LIQUIDACAO = {
        "codigo_ocorrencia": "06",
        "nosso_numero": "123456789",
        "uso_empresa": "1",
        "data_ocorrencia": date(2026, 9, 10),
        "data_credito": date(2026, 9, 11),
        "valor_titulo": Decimal("1000.00"),
        "valor_pago": Decimal("1015.00"),
        "juros_mora": Decimal("15.00"),
        "valor_tarifa": Decimal("2.50"),
    }

    def test_pagamento_marca_a_cobranca_como_paga(self):
        _, _, resumo = self.processar(montar_retorno([self.LIQUIDACAO]))

        self.cobranca.refresh_from_db()
        self.assertEqual(self.cobranca.status, StatusCobranca.PAGA)
        self.assertEqual(self.cobranca.valor_pago, Decimal("1015.00"))
        self.assertEqual(self.cobranca.data_pagamento, date(2026, 9, 10))
        self.assertEqual(self.cobranca.data_liquidacao, date(2026, 9, 11))
        self.assertEqual(self.cobranca.valor_juros_recebido, Decimal("15.00"))
        self.assertEqual(resumo["pagamentos"], 1)

    def test_cria_um_pagamento_com_a_prova_de_origem(self):
        self.processar(montar_retorno([self.LIQUIDACAO]))

        pagamento = Pagamento.objects.get()
        self.assertEqual(pagamento.valor, Decimal("1015.00"))
        self.assertEqual(pagamento.tarifa, Decimal("2.50"))
        # O líquido é o que entra na conta: o pago menos a tarifa do banco.
        self.assertEqual(pagamento.valor_liquido, Decimal("1012.50"))
        self.assertEqual(pagamento.origem, "RETORNO")
        self.assertIsNotNone(pagamento.ocorrencia)
        self.assertIsNone(pagamento.registrado_por)

    def test_processar_o_mesmo_arquivo_duas_vezes_nao_duplica(self):
        """A regra 9, literal. O operador sobe de novo porque não teve certeza."""
        conteudo = montar_retorno([self.LIQUIDACAO])
        self.processar(conteudo)
        arquivo, novo, _ = self.processar(conteudo, nome="RET001-copia.RET")

        self.assertFalse(novo, "conteúdo idêntico deveria ser reconhecido pelo hash")
        self.assertEqual(Pagamento.objects.count(), 1)
        self.assertEqual(OcorrenciaBancaria.objects.count(), 1)

    def test_reprocessar_o_mesmo_registro_nao_duplica(self):
        """Mesmo forçando o reprocessamento do MESMO arquivo — o caso do worker
        que morreu no meio e a tarefa voltou para a fila."""
        arquivo, _, _ = self.processar(montar_retorno([self.LIQUIDACAO]))

        with use_context(empresa_id=self.empresa.pk):
            RetornoService.processar(arquivo)
            RetornoService.processar(arquivo)

        self.assertEqual(Pagamento.objects.count(), 1)
        self.assertEqual(OcorrenciaBancaria.objects.count(), 1)

    def test_valor_total_do_arquivo(self):
        _, _, resumo = self.processar(montar_retorno([self.LIQUIDACAO]))
        self.assertEqual(resumo["valor_pago"], Decimal("1015.00"))
        arquivo = ArquivoBancario.objects.get(tipo=TipoArquivo.RETORNO)
        self.assertEqual(arquivo.status, StatusArquivo.PROCESSADO)
        self.assertEqual(arquivo.quantidade_registros, 1)
        self.assertEqual(arquivo.data_movimento, date(2026, 9, 11))


class OutrasOcorrenciasTest(BaseRetornoTest):
    def test_entrada_confirmada(self):
        self.cobranca.status = StatusCobranca.ENVIADA_AO_BANCO
        self.cobranca.save(update_fields=["status"])

        self.processar(montar_retorno([
            {"codigo_ocorrencia": "02", "nosso_numero": "123456789"}
        ]))

        self.cobranca.refresh_from_db()
        self.assertEqual(self.cobranca.status, StatusCobranca.REGISTRADA)

    def test_entrada_rejeitada_devolve_a_cobranca_ao_pool(self):
        """Rejeitada sem lote reaparece em 'prontas para envio' depois de
        corrigida — senão ela ficaria presa num lote que já foi."""
        from apps.bancos.models import LoteBancario

        lote = LoteBancario.objects.create(
            empresa=self.empresa, conta=self.conta, quantidade=1
        )
        self.cobranca.lote = lote
        self.cobranca.status = StatusCobranca.ENVIADA_AO_BANCO
        self.cobranca.save(update_fields=["lote", "status"])

        self.processar(montar_retorno([{
            "codigo_ocorrencia": "03", "nosso_numero": "123456789",
            "codigo_rejeicao": "068",
        }]))

        self.cobranca.refresh_from_db()
        self.assertEqual(self.cobranca.status, StatusCobranca.REJEITADA)
        self.assertIsNone(self.cobranca.lote_id)
        self.assertIn("CEP do pagador", self.cobranca.mensagem_erro)

    def test_baixa_nao_desfaz_pagamento(self):
        """Algumas carteiras mandam baixa depois da liquidação. Obedecer
        cegamente apagaria um pagamento real do dashboard."""
        self.processar(montar_retorno([{
            "codigo_ocorrencia": "06", "nosso_numero": "123456789",
            "data_ocorrencia": date(2026, 9, 10),
            "valor_pago": Decimal("1000.00"),
        }]))
        self.processar(
            montar_retorno([{"codigo_ocorrencia": "09", "nosso_numero": "123456789"}]),
            nome="RET002.RET",
        )

        self.cobranca.refresh_from_db()
        self.assertEqual(self.cobranca.status, StatusCobranca.PAGA)

    def test_prorrogacao_de_vencimento(self):
        self.cobranca.status = StatusCobranca.VENCIDA
        self.cobranca.save(update_fields=["status"])

        self.processar(montar_retorno([{
            "codigo_ocorrencia": "14", "nosso_numero": "123456789",
            "data_vencimento": date(2026, 10, 20),
        }]))

        self.cobranca.refresh_from_db()
        self.assertEqual(self.cobranca.data_vencimento, date(2026, 10, 20))
        self.assertEqual(self.cobranca.status, StatusCobranca.REGISTRADA)

    def test_abatimento_concedido_e_cancelado(self):
        self.processar(montar_retorno([{
            "codigo_ocorrencia": "12", "nosso_numero": "123456789",
            "valor_abatimento": Decimal("100.00"),
        }]))
        self.cobranca.refresh_from_db()
        self.assertEqual(self.cobranca.abatimento, Decimal("100.00"))

        self.processar(
            montar_retorno([{"codigo_ocorrencia": "13", "nosso_numero": "123456789"}]),
            nome="RET003.RET",
        )
        self.cobranca.refresh_from_db()
        self.assertEqual(self.cobranca.abatimento, Decimal("0"))

    def test_ocorrencia_informativa_nao_mexe_no_estado(self):
        anterior = self.cobranca.status
        self.processar(montar_retorno([
            {"codigo_ocorrencia": "19", "nosso_numero": "123456789"}
        ]))
        self.cobranca.refresh_from_db()
        self.assertEqual(self.cobranca.status, anterior)
        self.assertEqual(OcorrenciaBancaria.objects.count(), 1)


class TituloOrfaoTest(BaseRetornoTest):
    """Retorno de um título que não existe aqui.

    Acontece com título emitido direto no internet banking, e com título
    cadastrado no sistema depois do retorno chegar. Nos dois casos, engolir o
    registro em silêncio seria perder um pagamento.
    """

    ORFAO = {
        "codigo_ocorrencia": "06", "nosso_numero": "999999999",
        "data_ocorrencia": date(2026, 9, 10), "valor_pago": Decimal("500.00"),
    }

    def test_ocorrencia_fica_gravada_sem_cobranca(self):
        _, _, resumo = self.processar(montar_retorno([self.ORFAO]))

        self.assertEqual(resumo["orfaos"], 1)
        self.assertEqual(resumo["pagamentos"], 0)
        ocorrencia = OcorrenciaBancaria.objects.get()
        self.assertIsNone(ocorrencia.cobranca_id)
        self.assertFalse(ocorrencia.aplicada)

    def test_arquivo_fica_marcado_como_processado_com_erros(self):
        self.processar(montar_retorno([self.ORFAO]))
        arquivo = ArquivoBancario.objects.get(tipo=TipoArquivo.RETORNO)
        self.assertEqual(arquivo.status, StatusArquivo.PROCESSADO_COM_ERROS)
        self.assertIn("não foram encontrados", arquivo.mensagem_erro)

    def test_reprocessar_adota_o_titulo_cadastrado_depois(self):
        """O caso que justifica o botão 'reprocessar' na tela de arquivos."""
        arquivo, _, _ = self.processar(montar_retorno([self.ORFAO]))
        self.assertEqual(Pagamento.objects.count(), 0)

        atrasada = Cobranca.objects.create(
            empresa=self.empresa, cliente=self.cliente, conta_bancaria=self.conta,
            descricao="Cadastrada depois", valor=Decimal("500.00"),
            data_emissao=date(2026, 8, 1), data_vencimento=date(2026, 9, 10),
            nosso_numero="999999999", status=StatusCobranca.REGISTRADA,
        )

        with use_context(empresa_id=self.empresa.pk):
            RetornoService.processar(arquivo)

        atrasada.refresh_from_db()
        self.assertEqual(atrasada.status, StatusCobranca.PAGA)
        self.assertEqual(Pagamento.objects.count(), 1)


class CasamentoTest(BaseRetornoTest):
    def test_casa_por_seu_numero_quando_o_nosso_numero_nao_bate(self):
        self.processar(montar_retorno([{
            "codigo_ocorrencia": "06", "nosso_numero": "", "uso_empresa": "1",
            "data_ocorrencia": date(2026, 9, 10),
            "valor_pago": Decimal("1000.00"),
        }]))

        self.cobranca.refresh_from_db()
        self.assertEqual(self.cobranca.status, StatusCobranca.PAGA)

    def test_nao_casa_por_valor_e_vencimento(self):
        """Duas cobranças de mesmo valor no mesmo dia é o caso comum de uma
        carteira de mensalidades. Casar por valor daria baixa no cliente
        errado — e ninguém descobriria."""
        self.processar(montar_retorno([{
            "codigo_ocorrencia": "06", "nosso_numero": "888888888",
            "uso_empresa": "", "data_ocorrencia": date(2026, 9, 10),
            "valor_titulo": Decimal("1000.00"),
            "valor_pago": Decimal("1000.00"),
            "data_vencimento": date(2026, 9, 10),
        }]))

        self.cobranca.refresh_from_db()
        self.assertEqual(self.cobranca.status, StatusCobranca.REGISTRADA)
        self.assertEqual(Pagamento.objects.count(), 0)

    def test_nao_casa_com_cobranca_de_outra_empresa(self):
        """O isolamento vale também aqui — talvez principalmente aqui."""
        outra = Empresa.objects.create(
            cnpj="98765432000109", razao_social="OUTRA LTDA", nome_fantasia="Outra"
        )
        conta_outra = ContaBancaria.objects.create(
            empresa=outra, nome="Safra", banco="422", agencia="01234",
            conta="00099999", carteira="1",
        )
        cliente_outro = Cliente.objects.create(
            empresa=outra, nome="Cliente Outro", cpf_cnpj="11144477735",
        )
        alheia = Cobranca.objects.create(
            empresa=outra, cliente=cliente_outro, conta_bancaria=conta_outra,
            descricao="Alheia", valor=Decimal("1000.00"),
            data_emissao=date(2026, 8, 1), data_vencimento=date(2026, 9, 10),
            nosso_numero="777777777", status=StatusCobranca.REGISTRADA,
        )

        self.processar(montar_retorno([{
            "codigo_ocorrencia": "06", "nosso_numero": "777777777",
            "data_ocorrencia": date(2026, 9, 10),
            "valor_pago": Decimal("1000.00"),
        }]))

        alheia.refresh_from_db()
        self.assertEqual(alheia.status, StatusCobranca.REGISTRADA)
        self.assertEqual(Pagamento.objects.count(), 0)


class ArquivoRepetidoTest(BaseRetornoTest):
    def test_hash_reconhece_o_mesmo_conteudo_com_outro_nome(self):
        """O banco republica o mesmo retorno com nomes diferentes. Nome não
        serve de chave; conteúdo serve."""
        conteudo = montar_retorno([
            {"codigo_ocorrencia": "06", "nosso_numero": "123456789",
             "data_ocorrencia": date(2026, 9, 10),
             "valor_pago": Decimal("1000.00")}
        ])
        with use_context(empresa_id=self.empresa.pk):
            primeiro, novo1 = RetornoService.registrar_arquivo(
                empresa_id=self.empresa.pk, nome="RETORNO-1.RET",
                conteudo=conteudo, banco="422", conta=self.conta,
            )
            segundo, novo2 = RetornoService.registrar_arquivo(
                empresa_id=self.empresa.pk, nome="COBRANCA_11092026.RET",
                conteudo=conteudo, banco="422", conta=self.conta,
            )

        self.assertTrue(novo1)
        self.assertFalse(novo2)
        self.assertEqual(primeiro.pk, segundo.pk)
        self.assertEqual(ArquivoBancario.objects.filter(tipo=TipoArquivo.RETORNO).count(), 1)

    def test_empresas_diferentes_podem_ter_arquivos_identicos(self):
        """Dois retornos vazios de dias diferentes têm o mesmo conteúdo. Isso
        não pode impedir a segunda empresa de registrar o dela."""
        outra = Empresa.objects.create(
            cnpj="98765432000109", razao_social="OUTRA LTDA", nome_fantasia="Outra"
        )
        conteudo = montar_retorno([])

        with use_context(empresa_id=self.empresa.pk):
            RetornoService.registrar_arquivo(
                empresa_id=self.empresa.pk, nome="a.RET", conteudo=conteudo,
                banco="422", conta=self.conta,
            )
        with use_context(empresa_id=outra.pk):
            _, novo = RetornoService.registrar_arquivo(
                empresa_id=outra.pk, nome="a.RET", conteudo=conteudo, banco="422",
            )

        self.assertTrue(novo)
        self.assertEqual(ArquivoBancario.objects.count(), 2)

    def test_arquivo_vazio_e_recusado(self):
        from core.services import RegraDeNegocioError

        with self.assertRaises(RegraDeNegocioError):
            RetornoService.registrar_arquivo(
                empresa_id=self.empresa.pk, nome="vazio.RET", conteudo=b"",
                banco="422", conta=self.conta,
            )
