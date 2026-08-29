"""Geração de lote: a operação central do produto.

"Selecionei 500 cobranças e cliquei em gerar" precisa terminar de um jeito
previsível mesmo quando parte das 500 está com problema — e precisa nunca
consumir dois números iguais da faixa contratada com o banco, porque número
repetido faz o pagamento de um título cair no outro.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.bancos.bancos import StatusLote
from apps.bancos.models import ContaBancaria, LoteBancario
from apps.bancos.services import LoteService
from apps.clientes.models import Cliente
from apps.cobrancas.models import Cobranca, StatusCobranca
from apps.empresas.models import Empresa, PlanoEmpresa
from core.context import use_context
from core.services import RegraDeNegocioError


class BaseLoteTest(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(
            cnpj="12345678000195", razao_social="EMPRESA TESTE LTDA",
            nome_fantasia="Teste", cep="01310100", logradouro="Av Paulista",
            numero="1000", cidade="Sao Paulo", uf="SP",
            plano=PlanoEmpresa.ILIMITADO,
        )
        self.conta = ContaBancaria.objects.create(
            empresa=self.empresa, nome="Safra", banco="422",
            agencia="01234", conta="00012345", conta_dv="6", carteira="1",
            codigo_cedente="12345678901234567890",
        )
        self.vencimento = timezone.localdate() + timedelta(days=30)
        # Contador próprio em vez de índices escolhidos à mão: `f"{20:02d}"` e
        # `f"{20:03d}"` viram o mesmo CPF, e o teste quebrava por colisão de
        # documento — um defeito do teste, não do sistema.
        self._proximo_documento = 1

    def cliente(self, rotulo: str = "", completo: bool = True) -> Cliente:
        numero = self._proximo_documento
        self._proximo_documento += 1
        return Cliente.objects.create(
            empresa=self.empresa,
            nome=f"Cliente {rotulo or numero}",
            cpf_cnpj=self._documento(numero),
            cep="01310100" if completo else "",
            logradouro="Rua A" if completo else "",
            numero="1",
            cidade="Sao Paulo" if completo else "",
            uf="SP" if completo else "",
        )

    @staticmethod
    def _documento(numero: int) -> str:
        """CPF com dígitos verificadores válidos, a partir de um sequencial."""
        from core.validadores import _digito_mod11

        base = f"{numero:09d}"
        d1 = _digito_mod11(base, list(range(10, 1, -1)))
        d2 = _digito_mod11(base + d1, list(range(11, 1, -1)))
        return base + d1 + d2

    def cobranca(self, cliente, **ajustes) -> Cobranca:
        padrao = dict(
            empresa=self.empresa, cliente=cliente, conta_bancaria=self.conta,
            descricao="Mensalidade", valor=Decimal("100.00"),
            data_emissao=timezone.localdate(), data_vencimento=self.vencimento,
            status=StatusCobranca.PENDENTE,
        )
        padrao.update(ajustes)
        return Cobranca.objects.create(**padrao)


class ValidacaoTest(BaseLoteTest):
    def test_cobranca_completa_e_apta(self):
        cobranca = self.cobranca(self.cliente())
        resumo = LoteService.validar([cobranca], self.conta)
        self.assertEqual(resumo.aptas, [cobranca.pk])
        self.assertEqual(resumo.recusadas, [])

    def test_cliente_sem_endereco_e_recusado_com_motivo(self):
        """O banco exige endereço no registro. Sem esta checagem, a rejeição
        viria no retorno do dia seguinte — um boleto a menos emitido."""
        cobranca = self.cobranca(self.cliente(completo=False))
        resumo = LoteService.validar([cobranca], self.conta)

        self.assertEqual(resumo.aptas, [])
        self.assertIn("endereço completo", resumo.recusadas[0][1])

    def test_vencimento_no_passado_e_recusado(self):
        cobranca = self.cobranca(
            self.cliente(), data_vencimento=timezone.localdate() - timedelta(days=1),
            data_emissao=timezone.localdate() - timedelta(days=10),
        )
        resumo = LoteService.validar([cobranca], self.conta)
        self.assertIn("vencimento já passou", resumo.recusadas[0][1])

    def test_cobranca_ja_paga_nao_entra(self):
        cobranca = self.cobranca(self.cliente(), status=StatusCobranca.PAGA)
        resumo = LoteService.validar([cobranca], self.conta)
        self.assertIn("não permite envio", resumo.recusadas[0][1])

    def test_duplicata_na_propria_selecao(self):
        """Mesma pessoa, mesmo valor, mesmo vencimento: quase sempre é a
        planilha carregada duas vezes. O banco registraria os dois sem
        reclamar e o cliente receberia cobrança dobrada."""
        cliente = self.cliente()
        primeira = self.cobranca(cliente)
        segunda = self.cobranca(cliente)

        resumo = LoteService.validar([primeira, segunda], self.conta)
        self.assertEqual(resumo.aptas, [primeira.pk])
        self.assertIn("duplicada", resumo.recusadas[0][1])

    def test_recusa_e_por_titulo_e_nao_pelo_lote(self):
        boa = self.cobranca(self.cliente())
        ruim = self.cobranca(self.cliente(completo=False))

        resumo = LoteService.validar([boa, ruim], self.conta)
        self.assertEqual(resumo.aptas, [boa.pk])
        self.assertEqual(len(resumo.recusadas), 1)
        self.assertEqual(resumo.total, 2)


class CriacaoDeLoteTest(BaseLoteTest):
    def test_reserva_uma_faixa_contigua_de_nosso_numero(self):
        cobrancas = [self.cobranca(self.cliente()) for _ in range(5)]

        with use_context(empresa_id=self.empresa.pk):
            lote = LoteService.criar(
                empresa_id=self.empresa.pk, conta=self.conta,
                cobranca_ids=[c.pk for c in cobrancas],
            )

        self.assertEqual(lote.quantidade, 5)
        numeros = sorted(
            int(c.nosso_numero)
            for c in Cobranca.objects.filter(lote=lote)
        )
        self.assertEqual(numeros, [1, 2, 3, 4, 5])
        self.conta.refresh_from_db()
        self.assertEqual(self.conta.proximo_nosso_numero, 6)

    def test_dois_lotes_nao_repetem_numero(self):
        """Número repetido dentro da janela em que o banco ainda guarda o
        título anterior faz o pagamento de um cair no outro."""
        primeiros = [self.cobranca(self.cliente()) for _ in range(3)]
        segundos = [self.cobranca(self.cliente()) for _ in range(3)]

        with use_context(empresa_id=self.empresa.pk):
            lote1 = LoteService.criar(empresa_id=self.empresa.pk, conta=self.conta,
                                      cobranca_ids=[c.pk for c in primeiros])
            lote2 = LoteService.criar(empresa_id=self.empresa.pk, conta=self.conta,
                                      cobranca_ids=[c.pk for c in segundos])

        numeros1 = set(Cobranca.objects.filter(lote=lote1).values_list("nosso_numero", flat=True))
        numeros2 = set(Cobranca.objects.filter(lote=lote2).values_list("nosso_numero", flat=True))
        self.assertEqual(numeros1 & numeros2, set())

    def test_faixa_esgotada_recusa_antes_de_gastar(self):
        self.conta.proximo_nosso_numero = 99999998
        self.conta.nosso_numero_maximo = 99999999
        self.conta.save()
        cobrancas = [self.cobranca(self.cliente()) for _ in range(5)]

        with self.assertRaises(RegraDeNegocioError) as erro:
            LoteService.criar(empresa_id=self.empresa.pk, conta=self.conta,
                              cobranca_ids=[c.pk for c in cobrancas])
        self.assertIn("faixa de nosso número", str(erro.exception))

    def test_cobrancas_recusadas_ficam_marcadas_e_fora_do_lote(self):
        boa = self.cobranca(self.cliente())
        ruim = self.cobranca(self.cliente(completo=False))

        with use_context(empresa_id=self.empresa.pk):
            lote = LoteService.criar(empresa_id=self.empresa.pk, conta=self.conta,
                                     cobranca_ids=[boa.pk, ruim.pk])

        self.assertEqual(lote.quantidade, 1)
        ruim.refresh_from_db()
        self.assertIsNone(ruim.lote_id)
        self.assertIn(f"Fora do lote #{lote.numero}", ruim.mensagem_erro)

    def test_nenhuma_apta_nao_cria_lote(self):
        ruim = self.cobranca(self.cliente(completo=False))
        with self.assertRaises(RegraDeNegocioError):
            LoteService.criar(empresa_id=self.empresa.pk, conta=self.conta,
                              cobranca_ids=[ruim.pk])
        self.assertEqual(LoteBancario.objects.count(), 0)

    def test_cobranca_de_outra_empresa_e_recusada(self):
        outra = Empresa.objects.create(
            cnpj="98765432000109", razao_social="OUTRA LTDA", nome_fantasia="Outra"
        )
        cliente_alheio = Cliente.objects.create(
            empresa=outra, nome="Alheio", cpf_cnpj="11144477735"
        )
        alheia = Cobranca.objects.create(
            empresa=outra, cliente=cliente_alheio, descricao="Alheia",
            valor=Decimal("10.00"), data_emissao=timezone.localdate(),
            data_vencimento=self.vencimento,
        )
        minha = self.cobranca(self.cliente())

        with self.assertRaises(RegraDeNegocioError) as erro:
            LoteService.criar(empresa_id=self.empresa.pk, conta=self.conta,
                              cobranca_ids=[minha.pk, alheia.pk])
        self.assertIn("outra empresa", str(erro.exception))

    def test_empresa_com_cadastro_incompleto_nao_gera_lote(self):
        self.empresa.cidade = ""
        self.empresa.save(update_fields=["cidade"])
        cobranca = self.cobranca(self.cliente())

        with self.assertRaises(RegraDeNegocioError) as erro:
            LoteService.criar(empresa_id=self.empresa.pk, conta=self.conta,
                              cobranca_ids=[cobranca.pk])
        self.assertIn("cadastro da empresa", str(erro.exception))

    def test_plano_limita_a_quantidade(self):
        self.empresa.plano = PlanoEmpresa.TESTE  # 50 títulos/mês
        self.empresa.save(update_fields=["plano"])
        cobrancas = [self.cobranca(self.cliente()) for _ in range(60)]

        with self.assertRaises(RegraDeNegocioError) as erro:
            LoteService.criar(empresa_id=self.empresa.pk, conta=self.conta,
                              cobranca_ids=[c.pk for c in cobrancas])
        self.assertIn("plano", str(erro.exception).lower())


class RemessaTest(BaseLoteTest):
    def _lote(self, quantidade: int = 3) -> LoteBancario:
        cobrancas = [self.cobranca(self.cliente()) for _ in range(quantidade)]
        with use_context(empresa_id=self.empresa.pk):
            return LoteService.criar(
                empresa_id=self.empresa.pk, conta=self.conta,
                cobranca_ids=[c.pk for c in cobrancas],
            )

    def test_monta_o_arquivo_e_atualiza_as_cobrancas(self):
        lote = self._lote(3)

        with use_context(empresa_id=self.empresa.pk):
            arquivo = LoteService.montar_remessa(lote)

        lote.refresh_from_db()
        self.assertEqual(lote.status, StatusLote.PRONTO)
        self.assertEqual(lote.progresso, 100)
        self.assertEqual(arquivo.quantidade_processada, 3)
        self.assertTrue(arquivo.nome_original.endswith(".REM"))
        self.assertEqual(len(arquivo.hash_arquivo), 64)

        for cobranca in Cobranca.objects.filter(lote=lote):
            self.assertEqual(cobranca.status, StatusCobranca.ENVIADA_AO_BANCO)
            self.assertEqual(len(cobranca.codigo_barras), 44)
            self.assertEqual(len(cobranca.linha_digitavel), 47)

    def test_o_arquivo_tem_uma_linha_por_titulo_mais_header_e_trailer(self):
        from apps.bancos.adapters.cnab import quebrar_linhas
        from apps.bancos.services import ler_arquivo

        lote = self._lote(5)
        with use_context(empresa_id=self.empresa.pk):
            arquivo = LoteService.montar_remessa(lote)

        linhas = quebrar_linhas(ler_arquivo(arquivo.arquivo))
        self.assertEqual(len(linhas), 7)

    def test_nao_remonta_lote_ja_enviado(self):
        """Arquivo já transmitido não se reescreve: o banco recusaria o NSA
        repetido, e o operador ficaria sem saber qual dos dois vale."""
        lote = self._lote(2)
        with use_context(empresa_id=self.empresa.pk):
            LoteService.montar_remessa(lote)
            LoteService.enviar(LoteBancario.objects.get(pk=lote.pk))

        lote.refresh_from_db()
        with self.assertRaises(RegraDeNegocioError) as erro:
            LoteService.montar_remessa(lote)
        self.assertIn("remontado", str(erro.exception))

    def test_envio_sem_canal_automatico_nao_e_falha(self):
        """A maioria das empresas baixa a remessa e leva ao internet banking.
        Marcar isso como erro faria o painel mentir sobre um fluxo que
        funciona."""
        lote = self._lote(2)
        with use_context(empresa_id=self.empresa.pk):
            LoteService.montar_remessa(lote)
            protocolo = LoteService.enviar(LoteBancario.objects.get(pk=lote.pk))

        lote.refresh_from_db()
        self.assertEqual(lote.status, StatusLote.ENVIADO)
        self.assertTrue(protocolo)
        self.assertIsNotNone(lote.enviado_em)

    def test_numero_do_lote_e_sequencial_por_empresa(self):
        primeiro = self._lote(1)
        segundo = self._lote(1)
        self.assertEqual(segundo.numero, primeiro.numero + 1)
