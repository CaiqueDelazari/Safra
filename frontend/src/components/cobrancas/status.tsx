import { Badge, type BadgeProps } from "@/components/ui/badge";
import type { StatusCobranca, StatusLote } from "@/lib/tipos";

/**
 * A cor de um status é informação, não decoração.
 *
 * O critério aqui é uma pergunta só: *isto exige alguém?* Verde é dinheiro que
 * entrou; vermelho é dinheiro que não vai entrar se ninguém agir; âmbar é o
 * que está andando e pode travar; cinza é o que acabou sem drama.
 *
 * Repare que REGISTRADA e DISPONÍVEL são cinza-acento, não verde: o título
 * existe no banco, mas ninguém pagou nada ainda. Pintá-los de verde faria o
 * operador ler a tela como "recebido" — é o erro que a cor tem de impedir,
 * não causar.
 */
const TONS: Record<StatusCobranca, BadgeProps["tom"]> = {
  RASCUNHO: "neutro",
  PENDENTE: "atencao",
  ENVIADA_AO_BANCO: "acento",
  REGISTRADA: "acento",
  DISPONIVEL: "acento",
  PAGA: "positivo",
  VENCIDA: "negativo",
  CANCELADA: "neutro",
  BAIXADA: "neutro",
  REJEITADA: "negativo",
  ERRO: "negativo",
};

const ROTULOS: Record<StatusCobranca, string> = {
  RASCUNHO: "Rascunho",
  PENDENTE: "Pendente",
  ENVIADA_AO_BANCO: "Enviada ao banco",
  REGISTRADA: "Registrada",
  DISPONIVEL: "Disponível",
  PAGA: "Paga",
  VENCIDA: "Vencida",
  CANCELADA: "Cancelada",
  BAIXADA: "Baixada",
  REJEITADA: "Rejeitada",
  ERRO: "Erro",
};

export function StatusCobrancaBadge({
  status,
  vencida,
}: {
  status: StatusCobranca;
  vencida?: boolean;
}) {
  // Entre a virada da meia-noite e a rotina que marca os vencidos existe uma
  // janela em que o banco de dados diz REGISTRADA e o calendário diz vencida.
  // A tela mostra o calendário: é o que o operador precisa saber.
  const efetivo: StatusCobranca =
    vencida && !["PAGA", "CANCELADA", "BAIXADA"].includes(status)
      ? "VENCIDA"
      : status;

  return (
    <Badge tom={TONS[efetivo] ?? "neutro"} ponto>
      {ROTULOS[efetivo] ?? efetivo}
    </Badge>
  );
}

const TONS_LOTE: Record<StatusLote, BadgeProps["tom"]> = {
  RASCUNHO: "neutro",
  MONTANDO: "atencao",
  PRONTO: "acento",
  ENVIANDO: "atencao",
  ENVIADO: "acento",
  CONFIRMADO: "positivo",
  PARCIAL: "atencao",
  ERRO: "negativo",
  CANCELADO: "neutro",
};

export function StatusLoteBadge({ status }: { status: StatusLote }) {
  const rotulos: Record<StatusLote, string> = {
    RASCUNHO: "Rascunho",
    MONTANDO: "Montando",
    PRONTO: "Pronto para envio",
    ENVIANDO: "Enviando",
    ENVIADO: "Enviado",
    CONFIRMADO: "Confirmado",
    PARCIAL: "Com rejeições",
    ERRO: "Erro",
    CANCELADO: "Cancelado",
  };
  return (
    <Badge tom={TONS_LOTE[status] ?? "neutro"} ponto>
      {rotulos[status] ?? status}
    </Badge>
  );
}

const TONS_ARQUIVO: Record<string, BadgeProps["tom"]> = {
  PENDENTE: "atencao",
  PROCESSANDO: "atencao",
  PROCESSADO: "positivo",
  PROCESSADO_COM_ERROS: "atencao",
  ERRO: "negativo",
};

export function StatusArquivoBadge({
  status,
  rotulo,
}: {
  status: string;
  rotulo?: string;
}) {
  return (
    <Badge tom={TONS_ARQUIVO[status] ?? "neutro"} ponto>
      {rotulo ?? status}
    </Badge>
  );
}
