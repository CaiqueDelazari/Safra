"""Banco Safra — CNAB 400 de cobrança.

Duas responsabilidades, e nada além delas: montar o arquivo de remessa a
partir de títulos do sistema, e ler o arquivo de retorno devolvendo fatos. Não
consulta o banco de dados, não muda status de cobrança, não sabe o que é um
lote. Quem faz isso é `apps/bancos/services.py` — e é essa separação que
permite testar o layout inteiro sem subir Postgres.

O adapter de API fica em `api.py`, registrado para o mesmo banco em outro
meio de integração. Uma empresa migra de um para o outro trocando um campo da
conta bancária.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from django.utils import timezone

from apps.bancos.adapters import registrar
from apps.bancos.adapters.base import (
    ArquivoInvalido,
    BankAdapter,
    CabecalhoRetorno,
    ErroDeIntegracao,
    RegistroRetorno,
    ResultadoLote,
    ResultadoTitulo,
    Retorno,
    Titulo,
)
from apps.bancos.adapters.cnab import juntar_linhas, quebrar_linhas
from apps.bancos.adapters.safra import campo_livre as livre
from apps.bancos.adapters.safra import layout400 as L
from apps.bancos.adapters.safra import ocorrencias as oc
from apps.bancos.bancos import MeioDeIntegracao
from apps.bancos.boleto import (
    linha_digitavel,
    montar_codigo_barras,
    so_digitos,
    validar_valor,
    zfill,
)
from core.validadores import tipo_de_pessoa

logger = logging.getLogger(__name__)

#: Base de conversão de juros ao mês para juros ao dia no arquivo. O CNAB 400
#: pede reais por dia, não percentual — 30 é a convenção comercial usada pelos
#: bancos, não o número de dias do mês corrente.
DIAS_DO_MES_COMERCIAL = Decimal("30")


@registrar
class SafraCnab400(BankAdapter):
    codigo_banco = "422"
    nome = "Banco Safra — CNAB 400"
    meios = (MeioDeIntegracao.CNAB400,)

    # ═══════════════════════════════════════════════════════════ remessa
    def registrar_cobrancas_em_lote(self, titulos: Iterable[Titulo]) -> ResultadoLote:
        titulos = list(titulos)
        if not titulos:
            raise ErroDeIntegracao("Lote vazio: não há título para enviar ao banco.")

        conta = self.conta
        cedente = self._cedente()
        hoje = timezone.localdate()
        numero_remessa = conta.reservar_remessa()

        linhas = [
            L.REMESSA_HEADER.montar({
                "codigo_empresa": self._codigo_empresa(),
                "nome_cedente": cedente["nome"],
                "data_gravacao": hoje,
                "numero_arquivo": numero_remessa,
                "sequencial": 1,
            })
        ]

        resultados: list[ResultadoTitulo] = []
        for titulo in titulos:
            try:
                linha, resultado = self._detalhe(
                    titulo, sequencial=len(linhas) + 1, numero_arquivo=numero_remessa
                )
            except Exception as exc:  # noqa: BLE001
                # Um título com dado impossível não pode derrubar o lote
                # inteiro: 499 boletos válidos precisam sair. O título ruim
                # volta como erro, o serviço o marca e o operador corrige.
                logger.warning("Título %s fora do arquivo: %s", titulo.id_interno, exc)
                resultados.append(
                    ResultadoTitulo(id_interno=titulo.id_interno, ok=False, erro=str(exc))
                )
                continue
            linhas.append(linha)
            resultados.append(resultado)

        if len(linhas) == 1:
            raise ErroDeIntegracao(
                "Nenhum título do lote pôde ser incluído no arquivo. "
                "Verifique os erros título a título."
            )

        incluidos = [t for t, r in zip(titulos, resultados) if r.ok]
        linhas.append(L.REMESSA_TRAILER.montar({
            "quantidade_titulos": len(incluidos),
            "valor_total": sum((Decimal(str(t.valor)) for t in incluidos), Decimal("0")),
            "numero_arquivo": numero_remessa,
            "sequencial": len(linhas) + 1,
        }))

        nome = f"CB{hoje:%d%m}{numero_remessa:04d}.REM"
        return ResultadoLote(
            resultados=resultados,
            conteudo=juntar_linhas(linhas),
            nome_arquivo=nome,
            numero_remessa=numero_remessa,
        )

    def _detalhe(self, titulo: Titulo, *, sequencial: int, numero_arquivo: int) -> tuple[str, ResultadoTitulo]:
        conta = self.conta
        cedente = self._cedente()
        sacado = titulo.sacado

        validar_valor(titulo.valor)
        if not so_digitos(titulo.nosso_numero):
            raise ValueError("Título sem nosso número reservado.")
        if not so_digitos(sacado.documento):
            raise ValueError("Sacado sem CPF/CNPJ.")

        numero = zfill(titulo.nosso_numero, livre.TAMANHO_NOSSO_NUMERO)
        # O nosso número precisa caber inteiro no campo do arquivo. Se não
        # couber, o `formatar` cortaria pela esquerda em silêncio e o número
        # transmitido ao banco ficaria diferente do impresso no boleto — o
        # retorno nunca casaria com a cobrança e o pagamento sumiria. Falhar
        # aqui transforma um erro invisível num título recusado com motivo.
        campo = L.REMESSA_DETALHE.por_nome["nosso_numero"]
        if len(numero) > campo.tamanho:
            raise ValueError(
                f"Nosso número {numero} não cabe nas {campo.tamanho} posições do "
                "layout. Ajuste o campo em layout400.py conforme o manual do "
                "convênio — truncar geraria boleto que o retorno não reconhece."
            )

        cep = zfill(sacado.cep, 8)
        endereco = ", ".join(p for p in [sacado.logradouro, sacado.numero] if p)
        if sacado.complemento:
            endereco = f"{endereco} {sacado.complemento}"
        # Bairro e cidade entram no mesmo campo de 40 do endereço quando cabem:
        # é o que o banco imprime na ficha de compensação, e sem eles o boleto
        # sai sem referência de entrega.
        valores = {
            "tipo_inscricao_cedente": "02" if len(cedente["documento"]) == 14 else "01",
            "documento_cedente": cedente["documento"],
            "codigo_empresa": self._codigo_empresa(),
            "uso_empresa": titulo.seu_numero,
            "nosso_numero": numero,
            "carteira": conta.carteira,
            "codigo_ocorrencia": L.OCORRENCIA_REMESSA.get(titulo.ocorrencia, "01"),
            "numero_documento": titulo.documento or titulo.seu_numero,
            "data_vencimento": titulo.vencimento,
            "valor_titulo": titulo.valor,
            "agencia_cobradora": conta.agencia,
            "especie_titulo": L.ESPECIE_TITULO.get(titulo.especie, "99"),
            "aceite": "A" if titulo.aceite else "N",
            "data_emissao": titulo.emissao,
            "instrucao_1": "00",
            "instrucao_2": "10" if titulo.dias_protesto else "00",
            "instrucao_3": titulo.dias_protesto or 0,
            "juros_mora_dia": self._juros_dia(titulo),
            "data_limite_desconto": titulo.data_limite_desconto or "",
            "valor_desconto": titulo.desconto,
            "valor_iof": Decimal("0"),
            "valor_abatimento_multa": titulo.abatimento,
            "tipo_inscricao_sacado": "01" if tipo_de_pessoa(sacado.documento) == "F" else "02",
            "documento_sacado": sacado.documento,
            "nome_sacado": sacado.nome,
            "endereco_sacado": endereco,
            "bairro_sacado": sacado.bairro,
            "cep_sacado": cep,
            "cidade_sacado": sacado.cidade,
            "uf_sacado": sacado.uf,
            "mensagem": titulo.instrucoes,
            "dias_baixa": getattr(conta, "dias_baixa_automatica", 0),
            "tipo_desconto": "1" if titulo.desconto else "0",
            "numero_arquivo": numero_arquivo,
            "sequencial": sequencial,
        }

        linha = L.REMESSA_DETALHE.montar(valores)

        barras = montar_codigo_barras(
            banco=self.codigo_banco,
            vencimento=titulo.vencimento,
            valor=titulo.valor,
            campo_livre=livre.montar(conta, numero),
        )
        return linha, ResultadoTitulo(
            id_interno=titulo.id_interno,
            ok=True,
            nosso_numero=numero,
            codigo_barras=barras,
            linha_digitavel=linha_digitavel(barras),
        )

    def _juros_dia(self, titulo: Titulo) -> Decimal:
        """Percentual ao mês vira reais por dia — que é o que o campo pede."""
        percentual = Decimal(str(titulo.juros_mes_percentual or 0))
        if percentual <= 0:
            return Decimal("0")
        ao_dia = (Decimal(str(titulo.valor)) * percentual / 100) / DIAS_DO_MES_COMERCIAL
        return ao_dia.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _cedente(self) -> dict:
        empresa = self.conta.empresa
        return {
            "nome": empresa.razao_social or empresa.nome_fantasia,
            "documento": so_digitos(empresa.cnpj),
        }

    def _codigo_empresa(self) -> str:
        """Agência (5) + conta de cobrança com dígito (9), manual 05/2026."""
        conta = self.conta
        conta_com_dv = so_digitos(conta.conta) + so_digitos(conta.conta_dv or "")
        return zfill(conta.agencia, 5) + zfill(conta_com_dv, 9)

    # ═══════════════════════════════════════════════════════════ boleto
    def gerar_boleto(self, titulo: Titulo) -> ResultadoTitulo:
        validar_valor(titulo.valor)
        numero = zfill(titulo.nosso_numero, livre.TAMANHO_NOSSO_NUMERO)
        barras = montar_codigo_barras(
            banco=self.codigo_banco,
            vencimento=titulo.vencimento,
            valor=titulo.valor,
            campo_livre=livre.montar(self.conta, numero),
        )
        return ResultadoTitulo(
            id_interno=titulo.id_interno,
            ok=True,
            nosso_numero=numero,
            codigo_barras=barras,
            linha_digitavel=linha_digitavel(barras),
        )

    # ═══════════════════════════════════════════════════════════ retorno
    def processar_retorno(self, conteudo: bytes) -> Retorno:
        linhas = quebrar_linhas(conteudo, L.TAMANHO)
        if not linhas:
            raise ArquivoInvalido("Arquivo de retorno vazio.")

        primeira = linhas[0]
        if primeira[0] != "0":
            raise ArquivoInvalido(
                "A primeira linha não é um header CNAB 400 (posição 1 deveria "
                f"ser '0' e é {primeira[0]!r}). Arquivo de outro layout?"
            )
        banco_arquivo = L.RETORNO_HEADER.ler_texto(primeira, "banco")
        if banco_arquivo and banco_arquivo != self.codigo_banco:
            raise ArquivoInvalido(
                f"Este retorno é do banco {banco_arquivo}, e a conta é do "
                f"{self.codigo_banco}. Processá-lo casaria nosso número por "
                "coincidência e daria baixa em título errado."
            )

        cabecalho = CabecalhoRetorno(
            banco=banco_arquivo,
            codigo_cedente=L.RETORNO_HEADER.ler_texto(primeira, "codigo_empresa"),
            nome_cedente=L.RETORNO_HEADER.ler_texto(primeira, "nome_cedente"),
            data_movimento=L.RETORNO_HEADER.ler_data(primeira, "data_movimento"),
            numero_arquivo=L.RETORNO_HEADER.ler_int(primeira, "numero_arquivo"),
        )

        registros: list[RegistroRetorno] = []
        ignoradas: list[tuple[int, str]] = []

        for numero_linha, linha in enumerate(linhas, start=1):
            tipo_registro = linha[0]
            if tipo_registro == "1":
                try:
                    registros.append(self._ler_detalhe(linha, numero_linha))
                except Exception as exc:  # noqa: BLE001
                    ignoradas.append((numero_linha, f"linha ilegível: {exc}"))
            elif tipo_registro in ("0", "9"):
                continue
            else:
                # Registros opcionais (tipos 2, 3, 7…) existem em algumas
                # carteiras e não carregam movimento financeiro. Contar em vez
                # de falhar: o operador vê "12 linhas não interpretadas" e
                # pergunta ao banco, em vez de ver o arquivo recusado.
                ignoradas.append((numero_linha, f"registro tipo {tipo_registro!r}"))

        return Retorno(cabecalho=cabecalho, registros=registros, linhas_ignoradas=ignoradas)

    def _ler_detalhe(self, linha: str, numero_linha: int) -> RegistroRetorno:
        R = L.RETORNO_DETALHE
        codigo = R.ler_texto(linha, "codigo_ocorrencia").zfill(2)
        tipo, descricao = oc.traduzir(codigo)
        motivos = oc.separar_motivos(R.ler(linha, "codigo_rejeicao"))

        pago = R.ler_decimal(linha, "valor_pago")
        juros = R.ler_decimal(linha, "juros_mora")
        # Tarifa e despesas saem do crédito, não entram nele. Somá-las ao
        # pagamento infla o faturamento; ignorá-las faz a conciliação nunca
        # fechar. Ficam separadas e explicam a diferença.
        tarifa = R.ler_decimal(linha, "valor_tarifa") + R.ler_decimal(linha, "outras_despesas")

        return RegistroRetorno(
            linha=numero_linha,
            tipo=tipo,
            codigo=codigo,
            descricao=descricao,
            nosso_numero=R.ler_texto(linha, "nosso_numero").lstrip("0"),
            seu_numero=R.ler_texto(linha, "uso_empresa"),
            documento=R.ler_texto(linha, "numero_documento"),
            data_ocorrencia=R.ler_data(linha, "data_ocorrencia"),
            data_credito=R.ler_data(linha, "data_credito"),
            data_vencimento=R.ler_data(linha, "data_vencimento"),
            valor_titulo=R.ler_decimal(linha, "valor_titulo"),
            valor_pago=pago,
            valor_juros=juros,
            valor_multa=Decimal("0"),
            valor_desconto=R.ler_decimal(linha, "valor_desconto"),
            valor_abatimento=R.ler_decimal(linha, "valor_abatimento"),
            valor_tarifa=tarifa,
            banco_recebedor=R.ler_texto(linha, "banco_cobrador"),
            agencia_recebedora=R.ler_texto(linha, "agencia_cobradora"),
            motivos=motivos,
            motivos_descricao=oc.descrever_motivos(motivos),
            conteudo=linha,
        )

    # ═══════════════════════════════════════════════════════ transmissão
    def transmitir(self, conteudo: bytes, nome_arquivo: str) -> str:
        from apps.bancos.transporte import enviar_sftp

        if not self.conta.sftp_host:
            return super().transmitir(conteudo, nome_arquivo)
        return enviar_sftp(self.conta, conteudo, nome_arquivo)

    def obter_retornos(self) -> list[tuple[str, bytes]]:
        from apps.bancos.transporte import baixar_sftp

        if not self.conta.sftp_host:
            return []
        return baixar_sftp(self.conta)
