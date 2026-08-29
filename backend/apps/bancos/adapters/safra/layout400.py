"""Layout Safra CNAB 400 de cobrança — manual oficial, versão maio/2026."""
from apps.bancos.adapters.cnab import ALFA, NUMERICO, Campo, Registro

BANCO, NOME_BANCO, TAMANHO = "422", "BANCO SAFRA", 400

REMESSA_HEADER = Registro("Remessa · Header (tipo 0)", [
 Campo("registro",1,1,NUMERICO,fixo="0"), Campo("operacao",2,2,NUMERICO,fixo="1"), Campo("literal_remessa",3,9,ALFA,fixo="REMESSA"),
 Campo("codigo_servico",10,11,NUMERICO,fixo="01"), Campo("literal_servico",12,19,ALFA,fixo="COBRANCA"), Campo("brancos_1",20,26),
 Campo("codigo_empresa",27,40,NUMERICO), Campo("brancos_2",41,46), Campo("nome_cedente",47,76), Campo("banco",77,79,NUMERICO,fixo=BANCO),
 Campo("nome_banco",80,90,ALFA,fixo=NOME_BANCO), Campo("brancos_3",91,94), Campo("data_gravacao",95,100,NUMERICO), Campo("brancos_4",101,391),
 Campo("numero_arquivo",392,394,NUMERICO), Campo("sequencial",395,400,NUMERICO)], TAMANHO)

REMESSA_DETALHE = Registro("Remessa · Detalhe (tipo 1)", [
 Campo("registro",1,1,NUMERICO,fixo="1"), Campo("tipo_inscricao_cedente",2,3,NUMERICO), Campo("documento_cedente",4,17),
 Campo("codigo_empresa",18,31,NUMERICO), Campo("brancos_1",32,37), Campo("uso_empresa",38,62), Campo("nosso_numero",63,71,NUMERICO),
 Campo("brancos_2",72,85), Campo("data_juros_mora",86,91), Campo("uso_banco",92,92), Campo("brancos_3",93,101),
 Campo("codigo_iof",102,102,NUMERICO,fixo="0"), Campo("codigo_moeda",103,104,NUMERICO,fixo="00"), Campo("brancos_4",105,105),
 Campo("instrucao_3",106,107,NUMERICO), Campo("carteira",108,108,NUMERICO), Campo("codigo_ocorrencia",109,110,NUMERICO),
 Campo("numero_documento",111,120), Campo("data_vencimento",121,126,NUMERICO), Campo("valor_titulo",127,139,NUMERICO),
 Campo("banco_cobrador",140,142,NUMERICO,fixo=BANCO), Campo("agencia_cobradora",143,147,NUMERICO), Campo("especie_titulo",148,149,NUMERICO),
 Campo("aceite",150,150), Campo("data_emissao",151,156,NUMERICO), Campo("instrucao_1",157,158,NUMERICO), Campo("instrucao_2",159,160,NUMERICO),
 Campo("juros_mora_dia",161,173,NUMERICO), Campo("data_limite_desconto",174,179,NUMERICO), Campo("valor_desconto",180,192,NUMERICO),
 Campo("valor_iof",193,205,NUMERICO), Campo("valor_abatimento_multa",206,218,NUMERICO), Campo("tipo_inscricao_sacado",219,220,NUMERICO),
 Campo("documento_sacado",221,234), Campo("nome_sacado",235,274), Campo("endereco_sacado",275,314), Campo("bairro_sacado",315,324),
 Campo("brancos_5",325,326), Campo("cep_sacado",327,334,NUMERICO), Campo("cidade_sacado",335,349), Campo("uf_sacado",350,351),
 Campo("mensagem",352,381), Campo("dias_baixa",382,384), Campo("brancos_6",385,387), Campo("tipo_desconto",388,388,NUMERICO),
 Campo("banco_emitente",389,391,NUMERICO,fixo=BANCO), Campo("numero_arquivo",392,394,NUMERICO), Campo("sequencial",395,400,NUMERICO)], TAMANHO)

REMESSA_TRAILER = Registro("Remessa · Trailer (tipo 9)", [Campo("registro",1,1,NUMERICO,fixo="9"), Campo("brancos",2,368),
 Campo("quantidade_titulos",369,376,NUMERICO), Campo("valor_total",377,391,NUMERICO), Campo("numero_arquivo",392,394,NUMERICO), Campo("sequencial",395,400,NUMERICO)], TAMANHO)

RETORNO_HEADER = Registro("Retorno · Header (tipo 0)", [
 Campo("registro",1,1,NUMERICO), Campo("operacao",2,2,NUMERICO), Campo("literal_retorno",3,9), Campo("codigo_servico",10,11,NUMERICO),
 Campo("literal_servico",12,19), Campo("brancos_1",20,26), Campo("codigo_empresa",27,40,NUMERICO), Campo("brancos_2",41,46),
 Campo("nome_cedente",47,76), Campo("banco",77,79,NUMERICO), Campo("nome_banco",80,84), Campo("brancos_3",85,94),
 Campo("data_movimento",95,100,NUMERICO), Campo("brancos_4",101,391), Campo("numero_arquivo",392,394,NUMERICO), Campo("sequencial",395,400,NUMERICO)], TAMANHO)

RETORNO_DETALHE = Registro("Retorno · Detalhe (tipo 1)", [
 Campo("registro",1,1,NUMERICO), Campo("tipo_inscricao_cedente",2,3,NUMERICO), Campo("documento_cedente",4,17), Campo("codigo_empresa",18,31,NUMERICO),
 Campo("brancos_1",32,37), Campo("uso_empresa",38,62), Campo("nosso_numero",63,71,NUMERICO), Campo("brancos_2",72,102),
 Campo("ocorrencia_origem",103,104,NUMERICO), Campo("codigo_rejeicao",105,107,NUMERICO), Campo("carteira",108,108,NUMERICO),
 Campo("codigo_ocorrencia",109,110,NUMERICO), Campo("data_ocorrencia",111,116,NUMERICO), Campo("numero_documento",117,126),
 Campo("nosso_numero_banco",127,135,NUMERICO), Campo("brancos_3",136,146), Campo("data_vencimento",147,152,NUMERICO),
 Campo("valor_titulo",153,165,NUMERICO), Campo("banco_cobrador",166,168,NUMERICO), Campo("agencia_cobradora",169,173,NUMERICO),
 Campo("especie_titulo",174,175,NUMERICO), Campo("valor_tarifa",176,188,NUMERICO), Campo("outras_despesas",189,201,NUMERICO),
 Campo("zeros",202,214,NUMERICO), Campo("valor_iof",215,227,NUMERICO), Campo("valor_abatimento",228,240,NUMERICO),
 Campo("valor_desconto",241,253,NUMERICO), Campo("valor_pago",254,266,NUMERICO), Campo("juros_mora",267,279,NUMERICO),
 Campo("outros_creditos",280,292,NUMERICO), Campo("codigo_moeda",293,295,NUMERICO), Campo("data_credito",296,301,NUMERICO),
 Campo("brancos_4",302,307), Campo("beneficiario_transferido",308,321,NUMERICO), Campo("indicador_dda",322,322), Campo("meio_liquidacao",323,324),
 Campo("tipo_inscricao_sacado",325,326,NUMERICO), Campo("documento_sacado",327,340), Campo("nome_sacado",341,375), Campo("seu_numero_retorno",376,390),
 Campo("brancos_5",391,391), Campo("numero_arquivo",392,394,NUMERICO), Campo("sequencial",395,400,NUMERICO)], TAMANHO)

RETORNO_TRAILER = Registro("Retorno · Trailer (tipo 9)", [Campo("registro",1,1,NUMERICO), Campo("operacao",2,2), Campo("codigo_servico",3,4),
 Campo("banco",5,7,NUMERICO), Campo("uso_banco",8,391), Campo("numero_arquivo",392,394,NUMERICO), Campo("sequencial",395,400,NUMERICO)], TAMANHO)

REGISTROS={"remessa_header":REMESSA_HEADER,"remessa_detalhe":REMESSA_DETALHE,"remessa_trailer":REMESSA_TRAILER,
 "retorno_header":RETORNO_HEADER,"retorno_detalhe":RETORNO_DETALHE,"retorno_trailer":RETORNO_TRAILER}
OCORRENCIA_REMESSA={"ENTRADA":"01","BAIXA":"02","CANCELAMENTO":"02","ABATIMENTO_CONCEDER":"04","ABATIMENTO_CANCELAR":"05","ALTERACAO_VENCIMENTO":"06","PROTESTAR":"09","SUSTAR_PROTESTO":"10"}
ESPECIE_TITULO={"DM":"01","NP":"02","NS":"03","RC":"05","DS":"09","OU":"05"}
