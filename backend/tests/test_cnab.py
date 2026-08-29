"""Layout CNAB 400: montagem da remessa e leitura do retorno.

O teste mais valioso aqui é o de ida e volta: monta uma remessa, lê o arquivo
de volta pelas mesmas tabelas de posição e confere que cada campo voltou como
entrou. Ele não prova que as posições estão certas em relação ao manual do
Safra — isso só o manual prova, e é o que `manage.py conferir_layout` existe
para apoiar. Prova outra coisa, igualmente necessária: que a escrita e a
leitura concordam entre si, que nenhum campo ficou deslocado dentro do nosso
próprio mundo, e que o dia em que alguém corrigir uma posição vai corrigir os
dois lados juntos.
"""
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from apps.bancos.adapters.base import DadosSacado, Titulo
from apps.bancos.adapters.cnab import (
    ALFA,
    NUMERICO,
    Campo,
    Registro,
    converter_data,
    formatar,
    juntar_linhas,
    normalizar_texto,
    quebrar_linhas,
)
from apps.bancos.adapters.safra import layout400 as L


class ContaFalsa:
    """Conta bancária de mentira. O adapter não conhece o ORM, então não é
    preciso banco de dados para exercitar o layout inteiro — que é
    exatamente a vantagem de o adapter não conhecer o ORM."""

    class EmpresaFalsa:
        razao_social = "MINHA EMPRESA DE COBRANCA LTDA"
        nome_fantasia = "Minha Empresa"
        cnpj = "12345678000195"

    empresa = EmpresaFalsa()
    pk = 1
    agencia = "01234"
    agencia_dv = "5"
    conta = "00012345"
    conta_dv = "6"
    carteira = "1"
    codigo_cedente = ""
    variacao_carteira = ""
    especie_titulo = "DS"
    aceite = False
    dias_protesto = 0
    dias_baixa_automatica = 0
    instrucoes_boleto = ""
    sftp_host = ""
    producao = False
    proxima_remessa = 1

    def reservar_remessa(self):
        numero = self.proxima_remessa
        self.proxima_remessa += 1
        return numero


def titulo_exemplo(**ajustes) -> Titulo:
    padrao = dict(
        id_interno=1,
        nosso_numero="123456789",
        seu_numero="42",
        documento="NF-1001",
        valor=Decimal("1234.56"),
        emissao=date(2026, 8, 1),
        vencimento=date(2026, 9, 10),
        sacado=DadosSacado(
            nome="José da Silva Comércio ME",
            documento="12345678000195",
            logradouro="Rua das Acácias", numero="42", bairro="Centro",
            cidade="São Paulo", uf="SP", cep="01310100",
        ),
    )
    padrao.update(ajustes)
    return Titulo(**padrao)


class RegistroTest(SimpleTestCase):
    """A conferência de layout — a rede que pega erro de transcrição."""

    def test_layout_com_buraco_e_recusado_na_importacao(self):
        with self.assertRaises(ValueError) as erro:
            Registro("teste", [Campo("a", 1, 5), Campo("b", 7, 10)], 10)
        self.assertIn("buraco", str(erro.exception))

    def test_layout_com_sobreposicao_e_recusado(self):
        with self.assertRaises(ValueError) as erro:
            Registro("teste", [Campo("a", 1, 5), Campo("b", 4, 10)], 10)
        self.assertIn("sobreposição", str(erro.exception))

    def test_layout_que_nao_cobre_o_registro_inteiro_e_recusado(self):
        with self.assertRaises(ValueError) as erro:
            Registro("teste", [Campo("a", 1, 5)], 10)
        self.assertIn("cobrem 5 posições", str(erro.exception))

    def test_todos_os_registros_do_safra_estao_integros(self):
        """Importar `layout400` já roda a conferência — se ela passar, os seis
        registros cobrem exatamente 400 posições, sem falha nem sobra."""
        for nome, registro in L.REGISTROS.items():
            self.assertEqual(registro.tamanho, 400, nome)
            self.assertEqual(registro.campos[-1].fim, 400, nome)


class FormatacaoTest(SimpleTestCase):
    def test_numerico_alinha_a_direita_com_zeros(self):
        self.assertEqual(formatar("42", Campo("x", 1, 6, NUMERICO)), "000042")

    def test_alfa_alinha_a_esquerda_com_brancos(self):
        self.assertEqual(formatar("AB", Campo("x", 1, 5, ALFA)), "AB   ")

    def test_texto_perde_acento_e_vira_maiuscula(self):
        """O CNAB é ASCII: acento vira byte que o mainframe lê como outra
        coisa, e nome de sacado com cedilha é a regra, não a exceção."""
        self.assertEqual(normalizar_texto("José Ação"), "JOSE ACAO")

    def test_texto_longo_e_cortado_e_nao_derruba_a_remessa(self):
        campo = Campo("x", 1, 5, ALFA)
        self.assertEqual(formatar("NOME MUITO COMPRIDO", campo), "NOME ")

    def test_data_de_seis_posicoes(self):
        self.assertEqual(formatar(date(2026, 9, 10), Campo("x", 1, 6, NUMERICO)),
                         "100926")

    def test_decimal_vira_centavos(self):
        self.assertEqual(formatar(Decimal("12.34"), Campo("x", 1, 13, NUMERICO)),
                         "0000000001234")


class ConversaoDeDataTest(SimpleTestCase):
    def test_ddmmaa(self):
        self.assertEqual(converter_data("100926"), date(2026, 9, 10))

    def test_campo_zerado_vira_none_e_nao_excecao(self):
        """Data zerada é comum e significativa ('sem data de crédito'). Uma
        exceção aqui derrubaria o processamento de um arquivo inteiro por
        causa de um campo opcional."""
        self.assertIsNone(converter_data("000000"))

    def test_lixo_vira_none(self):
        self.assertIsNone(converter_data("999999"))
        self.assertIsNone(converter_data("      "))


class QuebraDeLinhasTest(SimpleTestCase):
    def test_aceita_crlf(self):
        conteudo = ("A" * 400 + "\r\n" + "B" * 400 + "\r\n").encode()
        self.assertEqual(len(quebrar_linhas(conteudo)), 2)

    def test_aceita_lf(self):
        conteudo = ("A" * 400 + "\n" + "B" * 400 + "\n").encode()
        self.assertEqual(len(quebrar_linhas(conteudo)), 2)

    def test_aceita_bloco_continuo_sem_separador(self):
        """Banco entrega assim com mais frequência do que se esperaria.
        Assumir só CRLF faria o parser devolver 'arquivo vazio' para um
        retorno perfeito."""
        conteudo = ("A" * 400 + "B" * 400).encode()
        self.assertEqual(len(quebrar_linhas(conteudo)), 2)

    def test_completa_linha_curta(self):
        linhas = quebrar_linhas(b"ABC\r\n")
        self.assertEqual(len(linhas[0]), 400)


class RemessaTest(SimpleTestCase):
    def setUp(self):
        from apps.bancos.adapters.safra.adapter import SafraCnab400

        self.adapter = SafraCnab400(ContaFalsa())

    def test_arquivo_tem_header_detalhe_e_trailer(self):
        resultado = self.adapter.registrar_cobrancas_em_lote([titulo_exemplo()])
        linhas = quebrar_linhas(resultado.conteudo)
        self.assertEqual(len(linhas), 3)
        self.assertEqual(linhas[0][0], "0")
        self.assertEqual(linhas[1][0], "1")
        self.assertEqual(linhas[2][0], "9")

    def test_toda_linha_tem_exatamente_400_posicoes(self):
        titulos = [titulo_exemplo(id_interno=i, nosso_numero=str(i)) for i in range(1, 6)]
        resultado = self.adapter.registrar_cobrancas_em_lote(titulos)
        for linha in quebrar_linhas(resultado.conteudo):
            self.assertEqual(len(linha), 400)

    def test_campos_do_detalhe_voltam_como_entraram(self):
        """Ida e volta pelas mesmas tabelas de posição."""
        titulo = titulo_exemplo()
        resultado = self.adapter.registrar_cobrancas_em_lote([titulo])
        detalhe = quebrar_linhas(resultado.conteudo)[1]
        R = L.REMESSA_DETALHE

        self.assertEqual(R.ler_texto(detalhe, "uso_empresa"), "42")
        self.assertEqual(R.ler_int(detalhe, "nosso_numero"), 123456789)
        self.assertEqual(R.ler_data(detalhe, "data_vencimento"), date(2026, 9, 10))
        self.assertEqual(R.ler_data(detalhe, "data_emissao"), date(2026, 8, 1))
        self.assertEqual(R.ler_decimal(detalhe, "valor_titulo"), Decimal("1234.56"))
        self.assertEqual(R.ler_texto(detalhe, "documento_sacado"), "12345678000195")
        self.assertEqual(R.ler_texto(detalhe, "nome_sacado"), "JOSE DA SILVA COMERCIO ME")
        self.assertEqual(R.ler_texto(detalhe, "cep_sacado"), "01310")
        self.assertEqual(R.ler_texto(detalhe, "sufixo_cep_sacado"), "100")
        self.assertEqual(R.ler_texto(detalhe, "codigo_ocorrencia"), "01")

    def test_sequencial_cresce_e_o_trailer_fecha_a_conta(self):
        titulos = [titulo_exemplo(id_interno=i, nosso_numero=str(i)) for i in range(1, 4)]
        resultado = self.adapter.registrar_cobrancas_em_lote(titulos)
        linhas = quebrar_linhas(resultado.conteudo)
        self.assertEqual(L.REMESSA_HEADER.ler_int(linhas[0], "sequencial"), 1)
        for indice, linha in enumerate(linhas[1:-1], start=2):
            self.assertEqual(L.REMESSA_DETALHE.ler_int(linha, "sequencial"), indice)
        self.assertEqual(L.REMESSA_TRAILER.ler_int(linhas[-1], "sequencial"), len(linhas))

    def test_boleto_sai_junto_com_o_arquivo(self):
        resultado = self.adapter.registrar_cobrancas_em_lote([titulo_exemplo()])
        titulo = resultado.resultados[0]
        self.assertTrue(titulo.ok)
        self.assertEqual(len(titulo.codigo_barras), 44)
        self.assertEqual(len(titulo.linha_digitavel), 47)

    def test_titulo_ruim_nao_derruba_o_lote(self):
        """499 boletos válidos precisam sair. O título ruim volta como erro."""
        bons = [titulo_exemplo(id_interno=i, nosso_numero=str(i)) for i in (1, 2)]
        ruim = titulo_exemplo(id_interno=99, nosso_numero="")  # sem nosso número
        resultado = self.adapter.registrar_cobrancas_em_lote([*bons, ruim])

        self.assertEqual(resultado.quantidade_ok, 2)
        self.assertEqual(resultado.quantidade_erro, 1)
        falha = next(r for r in resultado.resultados if not r.ok)
        self.assertEqual(falha.id_interno, 99)
        self.assertIn("nosso número", falha.erro)
        # E o arquivo saiu com os dois bons — header + 2 detalhes + trailer.
        self.assertEqual(len(quebrar_linhas(resultado.conteudo)), 4)

    def test_lote_vazio_e_recusado(self):
        from apps.bancos.adapters.base import ErroDeIntegracao

        with self.assertRaises(ErroDeIntegracao):
            self.adapter.registrar_cobrancas_em_lote([])

    def test_juros_ao_mes_vira_reais_por_dia(self):
        titulo = titulo_exemplo(
            valor=Decimal("3000.00"), juros_mes_percentual=Decimal("1.000")
        )
        resultado = self.adapter.registrar_cobrancas_em_lote([titulo])
        detalhe = quebrar_linhas(resultado.conteudo)[1]
        # 1% de 3000 = 30,00 ao mês → 1,00 por dia (mês comercial de 30 dias).
        self.assertEqual(
            L.REMESSA_DETALHE.ler_decimal(detalhe, "juros_mora_dia"), Decimal("1.00")
        )

    def test_instrucao_de_cancelamento_muda_o_codigo_de_ocorrencia(self):
        titulo = titulo_exemplo()
        titulo.ocorrencia = "CANCELAMENTO"
        resultado = self.adapter.registrar_cobrancas_em_lote([titulo])
        detalhe = quebrar_linhas(resultado.conteudo)[1]
        self.assertEqual(L.REMESSA_DETALHE.ler_texto(detalhe, "codigo_ocorrencia"), "02")


class RetornoTest(SimpleTestCase):
    """Leitura do retorno, sobre um arquivo montado com as próprias tabelas."""

    def setUp(self):
        from apps.bancos.adapters.safra.adapter import SafraCnab400

        self.adapter = SafraCnab400(ContaFalsa())

    def _arquivo(self, detalhes: list[dict]) -> bytes:
        header = L.RETORNO_HEADER.montar({
            "registro": "0", "operacao": "2", "literal_retorno": "RETORNO",
            "codigo_servico": "01", "literal_servico": "COBRANCA",
            "codigo_empresa": "12345", "nome_cedente": "MINHA EMPRESA",
            "banco": "422", "nome_banco": "BANCO SAFRA",
            "data_movimento": date(2026, 9, 11), "sequencial": 1,
        })
        linhas = [header]
        for indice, dados in enumerate(detalhes, start=2):
            linhas.append(L.RETORNO_DETALHE.montar(
                {"registro": "1", "sequencial": indice, **dados}
            ))
        linhas.append(L.RETORNO_TRAILER.montar({
            "registro": "9", "operacao": "2", "banco": "422",
            "sequencial": len(linhas) + 1,
        }))
        return juntar_linhas(linhas)

    def test_le_cabecalho(self):
        retorno = self.adapter.processar_retorno(self._arquivo([]))
        self.assertEqual(retorno.cabecalho.banco, "422")
        self.assertEqual(retorno.cabecalho.data_movimento, date(2026, 9, 11))

    def test_liquidacao(self):
        conteudo = self._arquivo([{
            "codigo_ocorrencia": "06",
            "nosso_numero": "123456789",
            "uso_empresa": "42",
            "data_ocorrencia": date(2026, 9, 10),
            "data_credito": date(2026, 9, 11),
            "valor_titulo": Decimal("1234.56"),
            "valor_principal": Decimal("1240.00"),
            "juros_mora": Decimal("5.44"),
            "valor_tarifa": Decimal("2.50"),
            "banco_cobrador": "341",
        }])
        retorno = self.adapter.processar_retorno(conteudo)

        self.assertEqual(len(retorno.registros), 1)
        registro = retorno.registros[0]
        self.assertEqual(registro.tipo, "LIQUIDACAO")
        self.assertEqual(registro.codigo, "06")
        self.assertEqual(registro.nosso_numero, "123456789")
        self.assertEqual(registro.seu_numero, "42")
        self.assertEqual(registro.valor_pago, Decimal("1240.00"))
        self.assertEqual(registro.valor_juros, Decimal("5.44"))
        self.assertEqual(registro.valor_tarifa, Decimal("2.50"))
        self.assertEqual(registro.data_credito, date(2026, 9, 11))
        self.assertEqual(registro.banco_recebedor, "341")

    def test_rejeicao_traz_os_motivos_legiveis(self):
        conteudo = self._arquivo([{
            "codigo_ocorrencia": "03",
            "nosso_numero": "123456789",
            "motivos_rejeicao": "4816",
        }])
        registro = self.adapter.processar_retorno(conteudo).registros[0]

        self.assertEqual(registro.tipo, "ENTRADA_REJEITADA")
        self.assertEqual(registro.motivos, ["48", "16"])
        self.assertIn("CEP inválido", registro.motivos_descricao)
        self.assertIn("Data de vencimento inválida", registro.motivos_descricao)

    def test_ocorrencia_desconhecida_nao_derruba_o_arquivo(self):
        """Banco acrescenta código sem avisar. Derrubar 500 pagamentos por
        causa de uma linha estranha seria trocar um problema pequeno por um
        grande."""
        conteudo = self._arquivo([
            {"codigo_ocorrencia": "97", "nosso_numero": "1"},
            {"codigo_ocorrencia": "06", "nosso_numero": "2",
             "valor_principal": Decimal("10.00")},
        ])
        retorno = self.adapter.processar_retorno(conteudo)

        self.assertEqual(len(retorno.registros), 2)
        self.assertEqual(retorno.registros[0].tipo, "DESCONHECIDA")
        self.assertEqual(retorno.registros[1].tipo, "LIQUIDACAO")

    def test_arquivo_de_outro_banco_e_recusado(self):
        """Processá-lo casaria nosso número por coincidência e daria baixa em
        título errado — o pior desfecho possível."""
        from apps.bancos.adapters.base import ArquivoInvalido

        conteudo = self._arquivo([]).replace(b"422BANCO SAFRA", b"341BANCO ITAU  ")
        with self.assertRaises(ArquivoInvalido) as erro:
            self.adapter.processar_retorno(conteudo)
        self.assertIn("341", str(erro.exception))

    def test_arquivo_vazio_e_recusado(self):
        from apps.bancos.adapters.base import ArquivoInvalido

        with self.assertRaises(ArquivoInvalido):
            self.adapter.processar_retorno(b"")

    def test_arquivo_que_nao_comeca_com_header(self):
        from apps.bancos.adapters.base import ArquivoInvalido

        with self.assertRaises(ArquivoInvalido):
            self.adapter.processar_retorno(("1" + "X" * 399).encode())

    def test_registro_opcional_e_contado_e_nao_falha(self):
        conteudo = self._arquivo([{"codigo_ocorrencia": "06", "nosso_numero": "1"}])
        linhas = quebrar_linhas(conteudo)
        linhas.insert(2, "3" + " " * 399)  # registro tipo 3, que não interpretamos
        retorno = self.adapter.processar_retorno(juntar_linhas(linhas))

        self.assertEqual(len(retorno.registros), 1)
        self.assertEqual(len(retorno.linhas_ignoradas), 1)
