"""Isolamento entre empresas e permissões por papel — pela API de verdade.

Estes testes passam pelo caminho completo (JWT, middleware de contexto,
permissão, repositório) porque é aí que o isolamento pode falhar. Testar o
`TenantRepository` sozinho provaria que o filtro funciona quando alguém o
chama; o que precisa ser provado é que **não existe rota que o dispense**.

O caso que mais importa é o penúltimo: um usuário legítimo de uma empresa
mandando o `X-Empresa-Id` de outra. É a tentativa que qualquer pessoa com o
DevTools aberto faz em cinco segundos.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import User, UsuarioEmpresa
from apps.bancos.models import ContaBancaria
from apps.clientes.models import Cliente
from apps.cobrancas.models import Cobranca
from apps.empresas.models import Empresa, PlanoEmpresa
from core.roles import Papel

SENHA = "Cobranca!2026#Forte"


class BaseAPITest(APITestCase):
    def setUp(self):
        # Os tetos de requisição contam no cache, e o cache é do processo —
        # não do banco de teste. Sem limpar, o 11º login da suíte leva 429 e
        # a falha aparece num teste que não tem nada a ver com throttling.
        # Limpar aqui mantém o teto ligado (quem quiser testá-lo, testa) sem
        # deixar um teste envenenar o seguinte.
        cache.clear()

        self.alfa = Empresa.objects.create(
            cnpj="12345678000195", razao_social="ALFA LTDA", nome_fantasia="Alfa",
            cep="01310100", logradouro="Av Paulista", numero="1",
            cidade="Sao Paulo", uf="SP", plano=PlanoEmpresa.ILIMITADO,
        )
        self.beta = Empresa.objects.create(
            cnpj="98765432000109", razao_social="BETA LTDA", nome_fantasia="Beta",
            cep="20040000", logradouro="Av Rio Branco", numero="2",
            cidade="Rio de Janeiro", uf="RJ", plano=PlanoEmpresa.ILIMITADO,
        )
        self.cliente_alfa = Cliente.objects.create(
            empresa=self.alfa, nome="Cliente da Alfa", cpf_cnpj="11144477735",
            cep="01310100", logradouro="Rua A", numero="1",
            cidade="Sao Paulo", uf="SP",
        )
        self.cliente_beta = Cliente.objects.create(
            empresa=self.beta, nome="Cliente da Beta", cpf_cnpj="52998224725",
            cep="20040000", logradouro="Rua B", numero="2",
            cidade="Rio de Janeiro", uf="RJ",
        )
        self.cobranca_alfa = Cobranca.objects.create(
            empresa=self.alfa, cliente=self.cliente_alfa, descricao="Da Alfa",
            valor=Decimal("100.00"), data_emissao=timezone.localdate(),
            data_vencimento=timezone.localdate() + timedelta(days=10),
        )
        self.cobranca_beta = Cobranca.objects.create(
            empresa=self.beta, cliente=self.cliente_beta, descricao="Da Beta",
            valor=Decimal("200.00"), data_emissao=timezone.localdate(),
            data_vencimento=timezone.localdate() + timedelta(days=10),
        )

    def criar_usuario(self, email: str, empresa, papel: str) -> User:
        usuario = User.objects.create_user(
            email=email, password=SENHA, nome_completo=f"Usuário {papel}",
            empresa_padrao=empresa,
        )
        UsuarioEmpresa.objects.create(
            usuario=usuario, empresa=empresa, papel=papel, ativo=True
        )
        return usuario

    def autenticar(self, usuario: User, empresa=None):
        resposta = self.client.post(
            reverse("v1:login"), {"email": usuario.email, "password": SENHA}, format="json"
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resposta.data['access']}")
        if empresa is not None:
            self.client.credentials(
                HTTP_AUTHORIZATION=f"Bearer {resposta.data['access']}",
                HTTP_X_EMPRESA_ID=str(empresa.pk),
            )
        return resposta.data


class IsolamentoTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.usuario = self.criar_usuario("admin@alfa.com", self.alfa, Papel.ADMINISTRADOR)

    def test_lista_apenas_clientes_da_empresa_ativa(self):
        self.autenticar(self.usuario, self.alfa)
        resposta = self.client.get(reverse("v1:cliente-list"))

        self.assertEqual(resposta.status_code, 200)
        nomes = [c["nome"] for c in resposta.data["resultados"]]
        self.assertEqual(nomes, ["Cliente da Alfa"])

    def test_lista_apenas_cobrancas_da_empresa_ativa(self):
        self.autenticar(self.usuario, self.alfa)
        resposta = self.client.get(reverse("v1:cobranca-list"))

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(len(resposta.data["resultados"]), 1)
        self.assertEqual(resposta.data["resultados"][0]["descricao"], "Da Alfa")

    def test_acesso_direto_a_registro_de_outra_empresa_da_404(self):
        """404, não 403: a existência do registro é, ela própria, informação."""
        self.autenticar(self.usuario, self.alfa)
        resposta = self.client.get(
            reverse("v1:cobranca-detail", args=[self.cobranca_beta.pk])
        )
        self.assertEqual(resposta.status_code, 404)

    def test_empresa_id_de_terceiro_e_recusado(self):
        """A tentativa de cinco segundos com o DevTools aberto."""
        self.autenticar(self.usuario, self.beta)
        resposta = self.client.get(reverse("v1:cliente-list"))

        self.assertEqual(resposta.status_code, 403)
        self.assertIn("não tem acesso", str(resposta.data["detail"]))

    def test_empresa_id_inexistente_e_recusado(self):
        """Sem isto viraria um contexto fantasma: toda consulta voltaria vazia
        e o usuário acharia que perdeu os dados."""
        self.autenticar(self.usuario)
        self.client.credentials(
            HTTP_AUTHORIZATION=self.client._credentials["HTTP_AUTHORIZATION"],
            HTTP_X_EMPRESA_ID="99999",
        )
        resposta = self.client.get(reverse("v1:cliente-list"))
        self.assertEqual(resposta.status_code, 403)

    def test_sem_token_nao_passa(self):
        self.assertEqual(self.client.get(reverse("v1:cliente-list")).status_code, 401)

    def test_criacao_carimba_a_empresa_ativa(self):
        """O `empresa` do corpo é ignorado: quem decide é o contexto."""
        self.autenticar(self.usuario, self.alfa)
        resposta = self.client.post(reverse("v1:cliente-list"), {
            "nome": "Novo Cliente", "cpf_cnpj": "123.456.789-09",
            "empresa": self.beta.pk,
        }, format="json")

        self.assertEqual(resposta.status_code, 201, resposta.data)
        criado = Cliente.objects.get(pk=resposta.data["id"])
        self.assertEqual(criado.empresa_id, self.alfa.pk)

    def test_nao_da_para_apontar_cobranca_para_cliente_de_outra_empresa(self):
        """O vazamento por relação: a cobrança seria da empresa A, mas o nome,
        o CPF e o endereço do sacado listados na tela seriam da empresa B.
        Nenhuma requisição suspeita — um número trocado no corpo do POST."""
        self.autenticar(self.usuario, self.alfa)
        hoje = timezone.localdate()
        resposta = self.client.post(reverse("v1:cobranca-list"), {
            "cliente": self.cliente_beta.pk, "descricao": "Sacado alheio",
            "valor": "100.00", "data_emissao": hoje.isoformat(),
            "data_vencimento": (hoje + timedelta(days=10)).isoformat(),
        }, format="json")

        self.assertEqual(resposta.status_code, 400, resposta.data)
        self.assertIn("cliente", resposta.data)
        self.assertEqual(
            Cobranca.objects.filter(descricao="Sacado alheio").count(), 0
        )

    def test_nao_da_para_apontar_cobranca_para_conta_de_outra_empresa(self):
        conta_alheia = ContaBancaria.objects.create(
            empresa=self.beta, nome="Conta da Beta", banco="422",
            agencia="09999", conta="00099999", carteira="1",
        )
        self.autenticar(self.usuario, self.alfa)
        hoje = timezone.localdate()
        resposta = self.client.post(reverse("v1:cobranca-list"), {
            "cliente": self.cliente_alfa.pk, "conta_bancaria": conta_alheia.pk,
            "descricao": "Conta alheia", "valor": "100.00",
            "data_emissao": hoje.isoformat(),
            "data_vencimento": (hoje + timedelta(days=10)).isoformat(),
        }, format="json")

        self.assertEqual(resposta.status_code, 400, resposta.data)
        self.assertIn("conta_bancaria", resposta.data)

    def test_usuario_com_duas_empresas_troca_de_contexto(self):
        """O contador que atende dois clientes — o caso que motivou o papel
        morar no vínculo, e não no usuário."""
        UsuarioEmpresa.objects.create(
            usuario=self.usuario, empresa=self.beta, papel=Papel.CONSULTA, ativo=True
        )

        self.autenticar(self.usuario, self.alfa)
        alfa = self.client.get(reverse("v1:cliente-list"))
        self.assertEqual([c["nome"] for c in alfa.data["resultados"]], ["Cliente da Alfa"])

        self.autenticar(self.usuario, self.beta)
        beta = self.client.get(reverse("v1:cliente-list"))
        self.assertEqual([c["nome"] for c in beta.data["resultados"]], ["Cliente da Beta"])


class ValidacaoDeEntradaTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.usuario = self.criar_usuario("admin@alfa.com", self.alfa, Papel.ADMINISTRADOR)
        self.autenticar(self.usuario, self.alfa)

    def test_cpf_invalido_e_recusado_no_cadastro(self):
        """Documento inválido não é erro de cadastro que se corrige depois: é
        rejeição do banco no dia seguinte e um boleto que não foi emitido."""
        resposta = self.client.post(reverse("v1:cliente-list"), {
            "nome": "Fulano", "cpf_cnpj": "111.111.111-11",
        }, format="json")

        self.assertEqual(resposta.status_code, 400)
        self.assertIn("cpf_cnpj", resposta.data)

    def test_documento_e_normalizado_para_digitos(self):
        resposta = self.client.post(reverse("v1:cliente-list"), {
            "nome": "Beltrano", "cpf_cnpj": "123.456.789-09",
        }, format="json")

        self.assertEqual(resposta.status_code, 201, resposta.data)
        self.assertEqual(resposta.data["cpf_cnpj"], "12345678909")
        self.assertEqual(resposta.data["documento_formatado"], "123.456.789-09")

    def test_documento_repetido_na_mesma_empresa_e_recusado(self):
        resposta = self.client.post(reverse("v1:cliente-list"), {
            "nome": "Repetido", "cpf_cnpj": self.cliente_alfa.cpf_cnpj,
        }, format="json")
        self.assertIn(resposta.status_code, (400, 409))

    def test_vencimento_antes_da_emissao_e_recusado(self):
        hoje = timezone.localdate()
        resposta = self.client.post(reverse("v1:cobranca-list"), {
            "cliente": self.cliente_alfa.pk, "descricao": "Errada",
            "valor": "100.00", "data_emissao": hoje.isoformat(),
            "data_vencimento": (hoje - timedelta(days=1)).isoformat(),
        }, format="json")

        self.assertEqual(resposta.status_code, 400)
        self.assertIn("data_vencimento", resposta.data)

    def test_desconto_maior_que_o_valor_e_recusado(self):
        hoje = timezone.localdate()
        resposta = self.client.post(reverse("v1:cobranca-list"), {
            "cliente": self.cliente_alfa.pk, "descricao": "Desconto absurdo",
            "valor": "100.00", "desconto": "150.00",
            "data_emissao": hoje.isoformat(),
            "data_vencimento": (hoje + timedelta(days=10)).isoformat(),
        }, format="json")

        self.assertEqual(resposta.status_code, 400)
        self.assertIn("desconto", resposta.data)


class PermissoesTest(BaseAPITest):
    """A matriz RBAC exercitada nas rotas que custam dinheiro."""

    def setUp(self):
        super().setUp()
        self.conta = ContaBancaria.objects.create(
            empresa=self.alfa, nome="Safra", banco="422", agencia="01234",
            conta="00012345", carteira="1",
        )

    def _como(self, papel: str):
        usuario = self.criar_usuario(f"{papel.lower()}@alfa.com", self.alfa, papel)
        self.autenticar(usuario, self.alfa)
        return usuario

    def test_consulta_nao_cria_cliente(self):
        self._como(Papel.CONSULTA)
        resposta = self.client.post(reverse("v1:cliente-list"), {
            "nome": "Não pode", "cpf_cnpj": "123.456.789-09",
        }, format="json")
        self.assertEqual(resposta.status_code, 403)

    def test_consulta_le_cobrancas(self):
        self._como(Papel.CONSULTA)
        self.assertEqual(self.client.get(reverse("v1:cobranca-list")).status_code, 200)

    def test_operador_nao_gera_lote(self):
        """Gerar lote manda título ao banco e gera tarifa. É ato de quem
        responde pelo caixa, não de quem alimenta o cadastro."""
        self._como(Papel.OPERADOR)
        resposta = self.client.post(reverse("v1:batches:batch-list"), {
            "conta_bancaria": self.conta.pk, "cobrancas": [self.cobranca_alfa.pk],
        }, format="json")
        self.assertEqual(resposta.status_code, 403)

    def test_operador_nao_cancela_cobranca(self):
        self._como(Papel.OPERADOR)
        resposta = self.client.post(
            reverse("v1:cobranca-cancel", args=[self.cobranca_alfa.pk]), {}, format="json"
        )
        self.assertEqual(resposta.status_code, 403)

    def test_operador_cria_cobranca(self):
        self._como(Papel.OPERADOR)
        hoje = timezone.localdate()
        resposta = self.client.post(reverse("v1:cobranca-list"), {
            "cliente": self.cliente_alfa.pk, "descricao": "Do operador",
            "valor": "50.00", "data_emissao": hoje.isoformat(),
            "data_vencimento": (hoje + timedelta(days=10)).isoformat(),
        }, format="json")
        self.assertEqual(resposta.status_code, 201, resposta.data)

    def test_financeiro_cancela_cobranca(self):
        self._como(Papel.FINANCEIRO)
        resposta = self.client.post(
            reverse("v1:cobranca-cancel", args=[self.cobranca_alfa.pk]),
            {"motivo": "cliente desistiu"}, format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.cobranca_alfa.refresh_from_db()
        self.assertEqual(self.cobranca_alfa.status, "CANCELADA")

    def test_financeiro_nao_cadastra_conta_bancaria(self):
        """Quem escreve a conta bancária redireciona o dinheiro. Fica com o
        administrador, mesmo que o financeiro conduza toda a cobrança."""
        self._como(Papel.FINANCEIRO)
        resposta = self.client.post(reverse("v1:bank:bank-account-list"), {
            "nome": "Conta pirata", "banco": "422", "agencia": "99999",
            "conta": "99999999", "carteira": "1",
        }, format="json")
        self.assertEqual(resposta.status_code, 403)

    def test_financeiro_le_conta_bancaria_sem_ver_credencial(self):
        self.conta.api_client_id = "id-do-banco"
        self.conta.api_client_secret = "segredo-do-banco"
        self.conta.save()

        self._como(Papel.FINANCEIRO)
        resposta = self.client.get(
            reverse("v1:bank:bank-account-detail", args=[self.conta.pk])
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn("api_client_secret", resposta.data)
        self.assertTrue(resposta.data["api_configurada"])

    def test_apenas_administrador_administra_usuarios(self):
        self._como(Papel.FINANCEIRO)
        self.assertEqual(self.client.get(reverse("v1:usuario-list")).status_code, 403)

        self._como(Papel.ADMINISTRADOR)
        self.assertEqual(self.client.get(reverse("v1:usuario-list")).status_code, 200)

    def test_equipe_nao_mostra_usuario_de_outra_empresa(self):
        self.criar_usuario("gente@beta.com", self.beta, Papel.ADMINISTRADOR)
        self._como(Papel.ADMINISTRADOR)

        resposta = self.client.get(reverse("v1:usuario-list"))
        emails = [u["email"] for u in resposta.data["resultados"]]
        self.assertNotIn("gente@beta.com", emails)


class CredenciaisTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.usuario = self.criar_usuario("admin@alfa.com", self.alfa, Papel.ADMINISTRADOR)
        self.autenticar(self.usuario, self.alfa)

    def test_credencial_e_gravada_cifrada_e_nunca_devolvida(self):
        resposta = self.client.post(reverse("v1:bank:bank-account-list"), {
            "nome": "Safra", "banco": "422", "agencia": "01234",
            "conta": "00012345", "carteira": "1",
            "sftp_host": "sftp.safra.com.br", "sftp_usuario": "empresa",
            "sftp_senha": "senha-super-secreta",
        }, format="json")

        self.assertEqual(resposta.status_code, 201, resposta.data)
        self.assertNotIn("sftp_senha", resposta.data)
        self.assertTrue(resposta.data["sftp_configurado"])

        # Em claro só dentro do processo; no banco, cifrado.
        conta = ContaBancaria.objects.get(pk=resposta.data["id"])
        self.assertEqual(conta.sftp_senha, "senha-super-secreta")

        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT sftp_senha FROM contas_bancarias WHERE id = %s", [conta.pk]
            )
            bruto = cursor.fetchone()[0]
        self.assertTrue(bruto.startswith("cif1:"))
        self.assertNotIn("senha-super-secreta", bruto)

    def test_credenciais_da_api_e_certificado_nunca_sao_devolvidos(self):
        resposta = self.client.post(reverse("v1:bank:bank-account-list"), {
            "nome": "Safra API", "banco": "422", "agencia": "01234",
            "conta": "00012345", "carteira": "1", "meio_integracao": "API",
            "api_client_id": "cliente-da-api",
            "api_client_secret": "chave-super-secreta",
            "api_certificado": "-----BEGIN CERTIFICATE-----\nCERTIFICADO\n-----END CERTIFICATE-----",
            "api_chave_privada": "-----BEGIN PRIVATE KEY-----\nCHAVE\n-----END PRIVATE KEY-----",
        }, format="json")

        self.assertEqual(resposta.status_code, 201, resposta.data)
        for campo in ("api_client_id", "api_client_secret", "api_certificado",
                      "api_chave_privada"):
            self.assertNotIn(campo, resposta.data)
        self.assertTrue(resposta.data["api_configurada"])
        self.assertTrue(resposta.data["certificado_configurado"])

        conta = ContaBancaria.objects.get(pk=resposta.data["id"])
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT api_client_secret, api_certificado, api_chave_privada "
                "FROM contas_bancarias WHERE id = %s", [conta.pk]
            )
            valores = cursor.fetchone()
        for valor in valores:
            self.assertTrue(valor.startswith("cif1:"))
        self.assertNotIn("chave-super-secreta", "".join(valores))

    def test_certificado_e_chave_privada_precisam_entrar_juntos(self):
        resposta = self.client.post(reverse("v1:bank:bank-account-list"), {
            "nome": "Safra API", "banco": "422", "agencia": "01234",
            "conta": "00012345", "carteira": "1", "meio_integracao": "API",
            "api_client_id": "cliente-da-api",
            "api_client_secret": "chave-super-secreta",
            "api_certificado": "-----BEGIN CERTIFICATE-----\nCERTIFICADO\n-----END CERTIFICATE-----",
        }, format="json")

        self.assertEqual(resposta.status_code, 400)
        self.assertIn("api_certificado", resposta.data)

    def test_salvar_o_cadastro_sem_reenviar_a_senha_nao_a_apaga(self):
        """O formulário reenvia o objeto inteiro e os campos de segredo voltam
        vazios, porque nunca foram exibidos. Sem este cuidado, trocar o nome
        da conta apagaria a credencial do banco."""
        conta = ContaBancaria.objects.create(
            empresa=self.alfa, nome="Safra", banco="422", agencia="01234",
            conta="00012345", carteira="1", sftp_host="sftp.safra.com.br",
            sftp_usuario="empresa", sftp_senha="senha-original",
        )

        resposta = self.client.patch(
            reverse("v1:bank:bank-account-detail", args=[conta.pk]),
            {"nome": "Safra — Matriz", "sftp_senha": ""}, format="json",
        )

        self.assertEqual(resposta.status_code, 200, resposta.data)
        conta.refresh_from_db()
        self.assertEqual(conta.nome, "Safra — Matriz")
        self.assertEqual(conta.sftp_senha, "senha-original")

    def test_conta_de_banco_sem_adapter_e_recusada(self):
        resposta = self.client.post(reverse("v1:bank:bank-account-list"), {
            "nome": "Itaú", "banco": "341", "agencia": "1234",
            "conta": "12345", "carteira": "109",
        }, format="json")

        self.assertEqual(resposta.status_code, 400)
        self.assertIn("banco", resposta.data)


class AuditoriaTest(BaseAPITest):
    def test_operacao_deixa_rastro_com_usuario_e_ip(self):
        from apps.auditoria.models import LogAuditoria

        usuario = self.criar_usuario("admin@alfa.com", self.alfa, Papel.ADMINISTRADOR)
        self.autenticar(usuario, self.alfa)
        self.client.post(reverse("v1:cliente-list"), {
            "nome": "Auditado", "cpf_cnpj": "123.456.789-09",
        }, format="json")

        log = LogAuditoria.objects.filter(modulo="clientes", acao="CRIACAO").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.usuario_id, usuario.pk)
        self.assertEqual(log.empresa_id, self.alfa.pk)
        self.assertIn("criado", log.alteracoes)
