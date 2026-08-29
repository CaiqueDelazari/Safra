import * as React from "react";

import { cn } from "@/lib/utils";

export function TituloPagina({
  titulo,
  descricao,
  acoes,
  className,
}: {
  titulo: string;
  descricao?: string;
  acoes?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mb-6 flex flex-wrap items-end justify-between gap-4",
        className,
      )}
    >
      <div>
        <h1 className="text-[26px] leading-tight font-semibold tracking-tight">
          {titulo}
        </h1>
        {descricao && (
          <p className="mt-1.5 text-[13.5px] text-texto-suave">{descricao}</p>
        )}
      </div>
      {acoes && <div className="flex items-center gap-2">{acoes}</div>}
    </div>
  );
}

/** Cartão de indicador do dashboard. */
export function CardIndicador({
  rotulo,
  valor,
  detalhe,
  icone: Icone,
  tom = "neutro",
  carregando,
}: {
  rotulo: string;
  valor: React.ReactNode;
  detalhe?: string;
  icone?: React.ComponentType<{ className?: string }>;
  tom?: "neutro" | "positivo" | "negativo" | "acento" | "atencao";
  carregando?: boolean;
}) {
  const tons = {
    neutro: "bg-neutro-suave text-texto-suave",
    positivo: "bg-positivo-suave text-positivo",
    negativo: "bg-negativo-suave text-negativo",
    acento: "bg-acento-suave text-acento",
    atencao: "bg-atencao-suave text-atencao",
  };

  return (
    <div className="rounded-card border border-borda bg-superficie p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[13px] font-medium text-texto-suave">{rotulo}</p>
        {Icone && (
          <span
            className={cn(
              "flex size-8 items-center justify-center rounded-lg",
              tons[tom],
            )}
          >
            <Icone className="size-4" />
          </span>
        )}
      </div>
      {carregando ? (
        <div className="carregando mt-3 h-8 w-24 rounded bg-neutro-suave" />
      ) : (
        <p className="mt-2.5 text-[28px] leading-none font-semibold tracking-tight tabular">
          {valor}
        </p>
      )}
      {detalhe && <p className="mt-2 text-[12.5px] text-texto-tenue">{detalhe}</p>}
    </div>
  );
}

export function Secao({
  titulo,
  acoes,
  children,
  className,
}: {
  titulo: string;
  acoes?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-card border border-borda bg-superficie", className)}>
      <div className="flex items-center justify-between gap-4 border-b border-borda px-5 py-4">
        <h2 className="text-[14.5px] font-semibold">{titulo}</h2>
        {acoes}
      </div>
      {children}
    </section>
  );
}

export function Filtros({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2.5">{children}</div>
  );
}
