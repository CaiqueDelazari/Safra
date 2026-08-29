import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const estilos = cva(
  "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[12px] font-medium whitespace-nowrap",
  {
    variants: {
      tom: {
        neutro: "bg-neutro-suave text-texto-suave",
        acento: "bg-acento-suave text-acento",
        positivo: "bg-positivo-suave text-positivo",
        negativo: "bg-negativo-suave text-negativo",
        atencao: "bg-atencao-suave text-atencao",
        contorno: "border border-borda text-texto-suave",
      },
    },
    defaultVariants: { tom: "neutro" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof estilos> {
  ponto?: boolean;
}

export function Badge({ className, tom, ponto, children, ...props }: BadgeProps) {
  return (
    <span className={cn(estilos({ tom }), className)} {...props}>
      {ponto && <span className="size-1.5 rounded-full bg-current opacity-80" />}
      {children}
    </span>
  );
}

/** Semáforo financeiro: é tudo que o perfil Financeiro pode ver. */
export function Semaforo({ pago, rotulo }: { pago: boolean; rotulo?: string }) {
  return (
    <Badge tom={pago ? "positivo" : "negativo"} ponto>
      {rotulo ?? (pago ? "Pago" : "Não pago")}
    </Badge>
  );
}

const TONS_STATUS: Record<string, BadgeProps["tom"]> = {
  ATIVO: "positivo",
  PAGO: "positivo",
  QUITADO: "positivo",
  PENDENTE: "atencao",
  PREVISTO: "neutro",
  VENCIDO: "negativo",
  INADIMPLENTE: "negativo",
  CANCELADA: "neutro",
  CANCELADO: "neutro",
  SUSPENSO: "atencao",
  INATIVO: "neutro",
  ESTORNADO: "atencao",
};

const ROTULOS: Record<string, string> = {
  NAO_ERA_CLIENTE: "Sem cobrança",
  SEM_COBRANCA: "Sem cobrança",
};

/**
 * Status genérico (financeiro, contratos, clientes). Ordem de serviço tem
 * vocabulário próprio em `components/ordens/status` — use `ChipStatus` lá.
 */
export function BadgeStatus({ status }: { status: string }) {
  const rotulo =
    ROTULOS[status] ??
    status.charAt(0) + status.slice(1).toLowerCase().replace(/_/g, " ");
  return (
    <Badge tom={TONS_STATUS[status] ?? "neutro"} ponto>
      {rotulo}
    </Badge>
  );
}
