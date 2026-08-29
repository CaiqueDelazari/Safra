"""Aritmética do boleto.

Estes testes são os mais importantes do repositório, e por um motivo que não é
óbvio: um erro aqui **não gera exceção em lugar nenhum**. O sistema continua
funcionando, o banco aceita a remessa, o boleto é impresso — e o caixa
eletrônico recusa a linha digitável, ou pior, credita em outro título. O
defeito aparece no telefone do cliente, dias depois.

Por isso a verificação é por valor conhecido sempre que existe um: as datas do
fator de vencimento são as documentadas pela FEBRABAN, e a consistência entre
código de barras e linha digitável é conferida nos dois sentidos.
"""
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from apps.bancos.boleto import (
    centavos_para_decimal,
    dv_codigo_barras,
    fator_vencimento,
    formatar_linha_digitavel,
    linha_digitavel,
    modulo10,
    modulo11,
    montar_codigo_barras,
    valor_em_centavos,
)


class ModuloDezTest(SimpleTestCase):
    def test_soma_algarismos_do_produto(self):
        """No módulo 10, produto de dois dígitos vira a soma deles (18 → 9).

        É o erro clássico da implementação apressada: somar 18 em vez de 9. O
        resultado passa despercebido porque continua sendo um dígito plausível.
        """
        # 9 × 2 = 18 → 1+8 = 9; total 9, resto 9, DV = 1
        self.assertEqual(modulo10("9"), 1)

    def test_resto_zero_da_dv_zero(self):
        self.assertEqual(modulo10("00000"), 0)

    def test_ignora_nao_digitos(self):
        self.assertEqual(modulo10("12-34"), modulo10("1234"))


class ModuloOnzeTest(SimpleTestCase):
    def test_devolve_o_resto_e_nao_o_digito(self):
        """A função devolve o resto de propósito: cada campo trata 0/10/11 de
        um jeito, e embutir uma das regras faria a outra virar exceção."""
        self.assertEqual(modulo11("0"), 0)
        self.assertLess(modulo11("123456789"), 11)

    def test_dv_do_codigo_de_barras_nunca_e_zero_dez_ou_onze(self):
        """Regra FEBRABAN: resto que levaria a 0, 1, 10 ou 11 vira DV 1."""
        for _ in range(1):
            self.assertIn(dv_codigo_barras("0" * 43), range(1, 10))
        # Um campo todo zero soma zero → resto 0 → DV 1, nunca 0.
        self.assertEqual(dv_codigo_barras("0" * 43), 1)


class FatorVencimentoTest(SimpleTestCase):
    def test_primeiro_fator_valido(self):
        """03/07/2000 é o fator 1000 — mil dias após a data base (07/10/1997).

        A confusão que este teste tranca: a norma diz "o fator começa em
        1000", e a leitura apressada vira `dias + 1000`, o que adianta todo
        boleto do sistema em mil dias. O fator é a contagem simples de dias.
        """
        self.assertEqual(fator_vencimento(date(2000, 7, 3)), "1000")

    def test_data_base_ainda_nao_e_fator_usavel(self):
        """Antes de 03/07/2000 o fator seria menor que 1000, que a norma não
        usa. Vira '0000' — na prática, data digitada errada."""
        self.assertEqual(fator_vencimento(date(1997, 10, 7)), "0000")

    def test_giro_de_2025(self):
        """O fator estourou 9999 em 21/02/2025 e recomeçou em 1000.

        Sem tratar a volta, todo boleto emitido de 2025 em diante sairia com
        fator de cinco dígitos — e seria recusado no caixa. É o teste que
        justifica a existência do laço em `fator_vencimento`.
        """
        self.assertEqual(fator_vencimento(date(2025, 2, 21)), "9999")
        self.assertEqual(fator_vencimento(date(2025, 2, 22)), "1000")

    def test_sempre_quatro_digitos(self):
        for dia in (date(1997, 10, 7), date(2026, 8, 28), date(2033, 1, 1)):
            self.assertEqual(len(fator_vencimento(dia)), 4, dia)

    def test_data_anterior_a_base_vira_zeros(self):
        self.assertEqual(fator_vencimento(date(1990, 1, 1)), "0000")

    def test_sem_data(self):
        self.assertEqual(fator_vencimento(None), "0000")


class ValorTest(SimpleTestCase):
    def test_decimal_e_nao_float(self):
        """1.15 em float é 1.14999…; um `int()` sobre isso perde um centavo
        por título, e a diferença só aparece na conciliação do mês."""
        self.assertEqual(valor_em_centavos(Decimal("1.15")), "0000000115")

    def test_arredonda_meio_para_cima(self):
        self.assertEqual(valor_em_centavos(Decimal("0.005")), "0000000001")

    def test_ida_e_volta(self):
        self.assertEqual(centavos_para_decimal("0000123456"), Decimal("1234.56"))

    def test_valor_nulo(self):
        self.assertEqual(valor_em_centavos(None), "0" * 10)


class CodigoDeBarrasTest(SimpleTestCase):
    CAMPO_LIVRE = "7" + "01234" + "000123456" + "000000001" + "2"

    def setUp(self):
        self.barras = montar_codigo_barras(
            banco="422",
            vencimento=date(2026, 9, 10),
            valor=Decimal("1234.56"),
            campo_livre=self.CAMPO_LIVRE,
        )

    def test_quarenta_e_quatro_posicoes(self):
        self.assertEqual(len(self.barras), 44)

    def test_exemplo_oficial_safra_maio_2026(self):
        barras = montar_codigo_barras(
            banco="422", vencimento=date(2025, 2, 23), valor=Decimal("180.84"),
            campo_livre="7" + "00400" + "000278247" + "261730011" + "2",
        )
        self.assertEqual(barras, "42296100100000180847004000002782472617300112")

    def test_estrutura(self):
        self.assertEqual(self.barras[0:3], "422")       # banco
        self.assertEqual(self.barras[3], "9")           # moeda
        self.assertEqual(self.barras[5:9], fator_vencimento(date(2026, 9, 10)))
        self.assertEqual(self.barras[9:19], "0000123456")
        self.assertEqual(self.barras[19:44], self.CAMPO_LIVRE)

    def test_dv_confere_com_o_proprio_corpo(self):
        """O DV da posição 5 tem de fechar sobre as outras 43 — é o que o
        caixa recalcula antes de aceitar o pagamento."""
        sem_dv = self.barras[:4] + self.barras[5:]
        self.assertEqual(int(self.barras[4]), dv_codigo_barras(sem_dv))

    def test_campo_livre_de_tamanho_errado_e_recusado(self):
        """Falhar alto aqui é o certo: um campo livre curto deslocaria tudo e
        geraria um boleto silenciosamente errado."""
        with self.assertRaises(ValueError):
            montar_codigo_barras(banco="422", vencimento=date(2026, 1, 1),
                                 valor=Decimal("10"), campo_livre="123")


class LinhaDigitavelTest(SimpleTestCase):
    def setUp(self):
        self.barras = montar_codigo_barras(
            banco="422",
            vencimento=date(2026, 9, 10),
            valor=Decimal("1234.56"),
            campo_livre="7" + "01234" + "000123456" + "000000001" + "2",
        )
        self.linha = linha_digitavel(self.barras)

    def test_quarenta_e_sete_posicoes(self):
        self.assertEqual(len(self.linha), 47)

    def test_carrega_os_mesmos_dados_do_codigo_de_barras(self):
        """A linha é o mesmo número reordenado, com três DVs a mais.

        Reconstruir o código de barras a partir dela é o teste que pega
        reordenação errada — o tipo de erro que só aparece quando alguém
        digita em vez de escanear.
        """
        c1, c2, c3 = self.linha[0:9], self.linha[10:20], self.linha[21:31]
        dv_geral = self.linha[32]
        fator_valor = self.linha[33:47]
        reconstruido = c1[0:4] + dv_geral + fator_valor + c1[4:9] + c2 + c3
        self.assertEqual(reconstruido, self.barras)

    def test_cada_campo_tem_dv_de_modulo_10(self):
        """É o que faz um erro de digitação ser recusado no caixa em vez de
        virar pagamento no título de outra pessoa."""
        self.assertEqual(int(self.linha[9]), modulo10(self.linha[0:9]))
        self.assertEqual(int(self.linha[20]), modulo10(self.linha[10:20]))
        self.assertEqual(int(self.linha[31]), modulo10(self.linha[21:31]))

    def test_formatacao_impressa(self):
        formatada = formatar_linha_digitavel(self.linha)
        self.assertEqual(len(formatada.replace(".", "").replace(" ", "")), 47)
        self.assertIn(".", formatada)

    def test_codigo_de_barras_invalido(self):
        with self.assertRaises(ValueError):
            linha_digitavel("123")


class CampoLivreSafraTest(SimpleTestCase):
    """As 25 posições que são do Safra, e o DV do nosso número."""

    def test_tamanho(self):
        from apps.bancos.adapters.safra import campo_livre

        class ContaFalsa:
            agencia = "1234"
            conta = "567890"
            conta_dv = "1"

        livre = campo_livre.montar(ContaFalsa(), "42")
        self.assertEqual(len(livre), 25)
        self.assertTrue(livre.startswith("7"))
        self.assertTrue(livre.endswith("2"))

    def test_extrai_o_nosso_numero_de_volta(self):
        from apps.bancos.adapters.safra import campo_livre

        class ContaFalsa:
            agencia = "1234"
            conta = "567890"
            conta_dv = "1"

        livre = campo_livre.montar(ContaFalsa(), "123456789")
        self.assertEqual(campo_livre.extrair_nosso_numero(livre), "123456789")
