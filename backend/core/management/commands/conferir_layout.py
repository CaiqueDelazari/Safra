"""Imprime o layout CNAB campo a campo, para conferir com o manual do banco.

    python manage.py conferir_layout                 # só a tabela
    python manage.py conferir_layout --conta 1       # com uma linha de exemplo
    python manage.py conferir_layout --arquivo x.RET # decodifica um arquivo real

Este comando existe por um motivo específico: um campo deslocado uma coluna no
CNAB não gera exceção em lugar nenhum. O arquivo sai, o banco recusa, e a
mensagem que volta é genérica. Conferir posição por posição contra o PDF do
banco é a única forma de pegar isso antes — e sem uma saída como esta, essa
conferência é feita contando caracteres na tela, que é como o erro entra.

Com `--arquivo`, faz o caminho inverso sobre um retorno de verdade: mostra o
que o parser está lendo em cada campo. É o que resolve "o banco diz que mandou
o pagamento e o sistema não viu" em minutos.
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Mostra o layout CNAB 400 do Safra campo a campo."

    def add_arguments(self, parser):
        parser.add_argument("--conta", type=int, help="Id da conta para montar exemplo.")
        parser.add_argument("--arquivo", help="Arquivo CNAB para decodificar.")
        parser.add_argument(
            "--registro", help="Só um registro (remessa_header, retorno_detalhe, …)."
        )
        parser.add_argument("--linha", type=int, default=2,
                            help="Com --arquivo: qual linha decodificar (1-based).")

    def handle(self, *args, **opcoes):
        from apps.bancos.adapters.safra import layout400 as L

        if opcoes["arquivo"]:
            return self._decodificar(opcoes["arquivo"], opcoes["linha"], L)

        nomes = [opcoes["registro"]] if opcoes["registro"] else list(L.REGISTROS)
        exemplo = self._exemplo(opcoes.get("conta"), L) if opcoes.get("conta") else {}

        for nome in nomes:
            registro = L.REGISTROS.get(nome)
            if registro is None:
                raise CommandError(
                    f"Registro '{nome}' não existe. Opções: {', '.join(L.REGISTROS)}"
                )
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(registro.nome))
            self.stdout.write(registro.regua(exemplo.get(nome, "")))

        self.stdout.write("")
        self.stdout.write(self.style.WARNING(
            "Campos marcados com nota 'CONFERIR' são os que variam entre bancos "
            "da mesma família. Comece por eles."
        ))

    def _exemplo(self, conta_id: int, L) -> dict:
        """Monta uma remessa de mentira com dados reais da conta.

        Dados reais importam: metade dos erros de layout só aparece com um
        nome de 40 letras ou um CNPJ de verdade no campo.
        """
        from datetime import date, timedelta
        from decimal import Decimal

        from apps.bancos.adapters.base import DadosSacado, Titulo
        from apps.bancos.adapters.safra.adapter import SafraCnab400
        from apps.bancos.models import ContaBancaria

        conta = ContaBancaria.objects.select_related("empresa").filter(pk=conta_id).first()
        if conta is None:
            raise CommandError(f"Conta bancária #{conta_id} não encontrada.")

        adapter = SafraCnab400(conta)
        titulo = Titulo(
            id_interno=0,
            nosso_numero="123456789",
            seu_numero="1",
            documento="EXEMPLO-1",
            valor=Decimal("1234.56"),
            emissao=date.today(),
            vencimento=date.today() + timedelta(days=30),
            sacado=DadosSacado(
                nome="EMPRESA EXEMPLO DE SACADO LTDA ME",
                documento="12345678000195",
                logradouro="Avenida Paulista", numero="1000",
                bairro="Bela Vista", cidade="Sao Paulo", uf="SP", cep="01310100",
            ),
            especie=conta.especie_titulo,
        )
        linha, _ = adapter._detalhe(titulo, sequencial=2)
        cabecalho = L.REMESSA_HEADER.montar({
            "codigo_empresa": adapter._codigo_empresa(),
            "nome_cedente": conta.empresa.razao_social,
            "data_gravacao": date.today(),
            "sequencial": 1,
        })
        return {
            "remessa_header": cabecalho,
            "remessa_detalhe": linha,
            "remessa_trailer": L.REMESSA_TRAILER.montar({"sequencial": 3}),
        }

    def _decodificar(self, caminho: str, numero_linha: int, L):
        from apps.bancos.adapters.cnab import quebrar_linhas

        with open(caminho, "rb") as arquivo:
            linhas = quebrar_linhas(arquivo.read(), L.TAMANHO)

        if not linhas:
            raise CommandError("Arquivo vazio ou ilegível.")
        if numero_linha > len(linhas):
            raise CommandError(f"O arquivo tem {len(linhas)} linha(s).")

        linha = linhas[numero_linha - 1]
        tipo = linha[0]
        registro = {
            "0": L.RETORNO_HEADER, "1": L.RETORNO_DETALHE, "9": L.RETORNO_TRAILER,
        }.get(tipo)
        if registro is None:
            raise CommandError(f"Tipo de registro desconhecido: {tipo!r}")

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"{caminho} — linha {numero_linha} de {len(linhas)} ({registro.nome})"
        ))
        self.stdout.write(registro.regua(linha))

        if tipo == "1":
            from apps.bancos.adapters.safra import ocorrencias as oc

            codigo = registro.ler_texto(linha, "codigo_ocorrencia").zfill(2)
            tipo_sistema, descricao = oc.traduzir(codigo)
            motivos = oc.separar_motivos(registro.ler(linha, "motivos_rejeicao"))
            self.stdout.write("")
            self.stdout.write(f"  ocorrência {codigo}: {descricao} → {tipo_sistema}")
            if motivos:
                self.stdout.write(f"  motivos: {oc.descrever_motivos(motivos)}")
