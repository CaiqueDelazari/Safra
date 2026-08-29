/**
 * Formato das respostas da API.
 *
 * Escrito à mão e não gerado do OpenAPI de propósito: o schema tem o dobro do
 * tamanho e descreve campos que o painel não usa. O que está aqui é o
 * contrato que as telas realmente consomem — quando ele diverge da API, a
 * compilação quebra numa tela, que é onde o problema é visível.
 */

export interface Pagina<T> {
  total: number;
  pagina: number;
  paginas: number;
  page_size: number;
  resultados: T[];
}

// ─────────────────────────────────────────────────────────────── identidade
export type Papel = "ADMINISTRADOR" | "FINANCEIRO" | "OPERADOR" | "CONSULTA";

export interface Empresa {
  id: number;
  uuid: string;
  nome_fantasia: string;
  razao_social: string;
  cnpj: string;
  cor_primaria: string;
  logo: string | null;
  ativa: boolean;
  /** Papel do usuário logado NESTA empresa — muda ao trocar no seletor. */
  papel?: Papel | null;
}

export interface EmpresaCompleta extends Empresa {
  cnpj_formatado: string;
  inscricao_estadual: string;
  inscricao_municipal: string;
  cep: string;
  logradouro: string;
  numero: string;
  complemento: string;
  bairro: string;
  cidade: string;
  uf: string;
  telefone: string;
  email: string;
  email_cobranca: string;
  plano?: string;
  plano_label?: string;
  endereco_completo: string;
  apta_a_emitir: boolean;
  limite_titulos_mes?: number | null;
  titulos_no_mes?: number;
  pendencias_cadastro: string[];
}

export interface Permissoes {
  papel: Papel | null;
  ve_valores: boolean;
  modulos: Record<string, string[]>;
  capacidades: string[];
}

export interface Usuario {
  id: number;
  uuid: string;
  email: string;
  nome_completo: string;
  telefone: string;
  papel: Papel | null;
  avatar: string | null;
  empresa_padrao: number | null;
  empresas: Empresa[];
  permissoes: Permissoes;
  is_active: boolean;
  segundo_fator_ativo: boolean;
  plataforma_admin: boolean;
}

export interface UsuarioEquipe {
  id: number;
  uuid: string;
  email: string;
  nome_completo: string;
  telefone: string;
  papel: Papel | null;
  avatar: string | null;
  is_active: boolean;
  ativo_na_empresa: boolean;
  segundo_fator_ativo: boolean;
  criado_em: string;
}

// ──────────────────────────────────────────────────────────────── clientes
export type StatusCliente = "ATIVO" | "INATIVO" | "INADIMPLENTE" | "BLOQUEADO";

export interface Cliente {
  id: number;
  uuid: string;
  codigo: number;
  nome: string;
  nome_fantasia: string;
  cpf_cnpj: string;
  documento_formatado: string;
  email: string;
  email_secundario: string;
  telefone: string;
  telefone_secundario: string;
  cep: string;
  cep_formatado: string;
  logradouro: string;
  numero: string;
  complemento: string;
  bairro: string;
  cidade: string;
  uf: string;
  observacoes: string;
  status: StatusCliente;
  codigo_externo: string;
  endereco_completo: string;
  /** Falso = o banco recusaria o registro do título deste sacado. */
  pronto_para_boleto: boolean;
  cobrancas_abertas?: number;
  valor_em_aberto?: string | null;
  criado_em: string;
  atualizado_em: string;
}

// ─────────────────────────────────────────────────────────────── cobranças
export type StatusCobranca =
  | "RASCUNHO"
  | "PENDENTE"
  | "ENVIADA_AO_BANCO"
  | "REGISTRADA"
  | "DISPONIVEL"
  | "PAGA"
  | "VENCIDA"
  | "CANCELADA"
  | "BAIXADA"
  | "REJEITADA"
  | "ERRO";

export interface ItemCobranca {
  id?: number;
  descricao: string;
  quantidade: string;
  valor_unitario: string;
  total?: string;
  ordem?: number;
}

export interface CobrancaLista {
  id: number;
  uuid: string;
  numero: number;
  cliente: number;
  cliente_nome: string;
  cliente_documento: string;
  descricao: string;
  documento: string;
  seu_numero: string;
  nosso_numero: string;
  valor: string;
  data_emissao: string;
  data_vencimento: string;
  status: StatusCobranca;
  status_label: string;
  data_pagamento: string | null;
  valor_pago: string;
  conta_bancaria: number | null;
  conta_nome: string | null;
  lote: number | null;
  vencida: boolean;
  dias_em_atraso: number;
  linha_digitavel: string;
  mensagem_erro: string;
  criado_em: string;
}

export interface Cobranca extends CobrancaLista {
  cliente_detalhe: {
    id: number;
    codigo: number;
    nome: string;
    cpf_cnpj: string;
    documento_formatado: string;
    email: string;
  };
  identificador_bancario: string;
  valor_liquido: string;
  juros_mes_percentual: string;
  multa_percentual: string;
  desconto: string;
  data_limite_desconto: string | null;
  abatimento: string;
  data_liquidacao: string | null;
  valor_juros_recebido: string;
  valor_multa_recebida: string;
  valor_desconto_concedido: string;
  valor_tarifa: string;
  codigo_barras: string;
  url_boleto: string;
  enviado_ao_cliente_em: string | null;
  observacoes: string;
  chave_externa: string;
  itens: ItemCobranca[];
  atualizado_em: string;
}

export interface DadosBoleto {
  linha_digitavel: string;
  linha_digitavel_formatada: string;
  codigo_barras: string;
  url_banco: string | null;
  pdf: string | null;
  nosso_numero: string;
  vencimento: string;
  valor: string;
  beneficiario: string;
  sacado: string;
}

// ─────────────────────────────────────────────────────────────────── banco
export type MeioIntegracao = "CNAB400" | "CNAB240" | "API";

export interface ContaBancaria {
  id: number;
  uuid: string;
  nome: string;
  banco: string;
  banco_label: string;
  meio_integracao: MeioIntegracao;
  agencia: string;
  agencia_dv: string;
  conta: string;
  conta_dv: string;
  agencia_conta: string;
  carteira: string;
  codigo_cedente: string;
  variacao_carteira: string;
  especie_titulo: string;
  aceite: boolean;
  proximo_nosso_numero: number;
  nosso_numero_maximo: number;
  proxima_remessa: number;
  dias_protesto: number;
  dias_baixa_automatica: number;
  juros_mes_percentual: string;
  multa_percentual: string;
  instrucoes_boleto: string;
  sftp_host: string;
  sftp_porta: number;
  sftp_usuario: string;
  sftp_dir_remessa: string;
  sftp_dir_retorno: string;
  /** Booleanos de presença: a credencial em si nunca volta da API. */
  api_configurada: boolean;
  sftp_configurado: boolean;
  certificado_configurado: boolean;
  producao: boolean;
  ativa: boolean;
  padrao: boolean;
  integrada: boolean;
  transmissao_automatica: boolean;
  credenciais_configuradas: boolean;
  criado_em: string;
  atualizado_em: string;
}

export type StatusLote =
  | "RASCUNHO"
  | "MONTANDO"
  | "PRONTO"
  | "ENVIANDO"
  | "ENVIADO"
  | "CONFIRMADO"
  | "PARCIAL"
  | "ERRO"
  | "CANCELADO";

export interface ArquivoBancario {
  id: number;
  uuid: string;
  conta: number | null;
  conta_nome: string | null;
  banco: string;
  banco_label: string;
  tipo: "REMESSA" | "RETORNO";
  tipo_label: string;
  nome_original: string;
  hash_arquivo: string;
  tamanho_bytes: number;
  recebido_em: string;
  processado_em: string | null;
  data_movimento: string | null;
  quantidade_registros: number;
  quantidade_processada: number;
  quantidade_com_erro: number;
  valor_total: string;
  status:
    | "PENDENTE"
    | "PROCESSANDO"
    | "PROCESSADO"
    | "PROCESSADO_COM_ERROS"
    | "ERRO";
  status_label: string;
  mensagem_erro: string;
  origem: string;
  download: string | null;
  criado_em: string;
}

export interface Lote {
  id: number;
  uuid: string;
  numero: number;
  conta: number;
  conta_nome: string;
  banco: string;
  status: StatusLote;
  status_label: string;
  quantidade: number;
  quantidade_confirmada: number;
  quantidade_rejeitada: number;
  valor_total: string;
  numero_remessa: number | null;
  protocolo_banco: string;
  progresso: number;
  etapa: string;
  mensagem_erro: string;
  enviado_em: string | null;
  confirmado_em: string | null;
  criado_por: number | null;
  criado_por_nome: string | null;
  arquivo: ArquivoBancario | null;
  criado_em: string;
  atualizado_em: string;
}

export interface Ocorrencia {
  id: number;
  uuid: string;
  arquivo: number;
  arquivo_nome: string;
  cobranca: number | null;
  cobranca_numero: number | null;
  cliente_nome: string | null;
  linha: number;
  tipo: string;
  tipo_label: string;
  codigo: string;
  descricao: string;
  motivos: string[];
  motivos_descricao: string;
  nosso_numero: string;
  seu_numero: string;
  data_ocorrencia: string | null;
  data_credito: string | null;
  valor_titulo: string;
  valor_pago: string;
  valor_juros: string;
  valor_multa: string;
  valor_desconto: string;
  valor_abatimento: string;
  valor_tarifa: string;
  banco_recebedor: string;
  agencia_recebedora: string;
  aplicada: boolean;
  criado_em: string;
}

// ────────────────────────────────────────────────────────────── pagamentos
export interface Pagamento {
  id: number;
  uuid: string;
  cobranca: number;
  cobranca_numero: number;
  cobranca_descricao: string;
  cliente_nome: string;
  conta_bancaria: number | null;
  conta_nome: string | null;
  origem: "RETORNO" | "API" | "MANUAL";
  origem_label: string;
  data_pagamento: string;
  data_credito: string | null;
  valor: string;
  juros: string;
  multa: string;
  desconto: string;
  abatimento: string;
  tarifa: string;
  valor_liquido: string;
  banco_recebedor: string;
  agencia_recebedora: string;
  observacao: string;
  estornado: boolean;
  estornado_em: string | null;
  motivo_estorno: string;
  criado_em: string;
}

// ─────────────────────────────────────────────────────────────── dashboard
export interface Dashboard {
  referencia: string;
  totais: {
    a_receber: string;
    em_aberto: string;
    vencido: string;
    cancelado: string;
    rejeitado: string;
    vencendo_em_7_dias: string;
    quantidade_aberta: number;
    quantidade_vencida: number;
  };
  recebido: {
    no_mes: string;
    hoje: string;
    total: string;
    tarifas_no_mes: string;
    quantidade_no_mes: number;
  };
  inadimplencia_percentual: number;
  recebimentos_por_mes: { mes: string; valor: string; quantidade: number }[];
  proximos_vencimentos: {
    id: number;
    numero: number;
    cliente: string;
    descricao: string;
    valor: string;
    vencimento: string;
  }[];
}

export interface Conciliacao {
  periodo: { inicio: string; fim: string };
  cobrancas: {
    quantidade: number;
    valor_total: string;
    registrado: string;
    pago: string;
    em_aberto: string;
    vencido: string;
    cancelado: string;
    baixado: string;
    rejeitado: string;
  };
  recebimentos: {
    quantidade: number;
    bruto: string;
    juros: string;
    multa: string;
    desconto: string;
    tarifa: string;
    liquido: string;
  };
  por_status: { status: StatusCobranca; quantidade: number; valor: string }[];
  inadimplencia: { valor: string; percentual: number };
}

export interface Pendencias {
  cobrancas_rejeitadas: number;
  cobrancas_com_erro: number;
  ocorrencias_orfas: number;
  arquivos_com_erro: number;
  arquivos_pendentes: number;
  lotes_com_erro: number;
  lotes_aguardando_envio: number;
  clientes_sem_endereco: number;
}

export interface LogAuditoria {
  id: number;
  empresa: number | null;
  empresa_nome: string | null;
  usuario: number | null;
  usuario_nome: string;
  acao: string;
  modulo: string;
  objeto_tipo: string;
  objeto_id: string;
  objeto_descricao: string;
  descricao: string;
  alteracoes: Record<string, unknown>;
  metadados: Record<string, unknown>;
  ip: string | null;
  user_agent: string;
  criado_em: string;
}

/** Resposta padrão de toda operação que vai para a fila. */
export interface RespostaTarefa {
  tarefa_id: string;
  total?: number;
  mensagem?: string;
}
