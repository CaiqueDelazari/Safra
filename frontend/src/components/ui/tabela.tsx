import * as React from "react";

import { cn } from "@/lib/utils";

export function Tabela({
  className,
  ...props
}: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full border-collapse text-sm", className)} {...props} />
    </div>
  );
}

export function Cabecalho({
  className,
  ...props
}: React.HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      className={cn("border-b border-borda text-left", className)}
      {...props}
    />
  );
}

export function Corpo({
  className,
  ...props
}: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("divide-y divide-borda", className)} {...props} />;
}

export function Linha({
  className,
  clicavel,
  ...props
}: React.HTMLAttributes<HTMLTableRowElement> & { clicavel?: boolean }) {
  return (
    <tr
      className={cn(
        "transition-colors",
        clicavel && "cursor-pointer hover:bg-superficie-sutil",
        className,
      )}
      {...props}
    />
  );
}

export function Th({
  className,
  ...props
}: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "px-4 py-2.5 text-[12px] font-medium tracking-wide text-texto-tenue uppercase",
        className,
      )}
      {...props}
    />
  );
}

export function Td({
  className,
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-4 py-3 align-middle", className)} {...props} />;
}

export function Vazio({
  colunas,
  titulo = "Nada por aqui",
  descricao,
  acao,
}: {
  colunas: number;
  titulo?: string;
  descricao?: string;
  acao?: React.ReactNode;
}) {
  return (
    <tr>
      <td colSpan={colunas} className="px-4 py-16 text-center">
        <p className="text-sm font-medium text-texto">{titulo}</p>
        {descricao && (
          <p className="mx-auto mt-1 max-w-sm text-[13px] text-texto-suave">
            {descricao}
          </p>
        )}
        {acao && <div className="mt-4 flex justify-center">{acao}</div>}
      </td>
    </tr>
  );
}

export function Esqueleto({
  linhas = 5,
  colunas,
}: {
  linhas?: number;
  colunas: number;
}) {
  return (
    <>
      {Array.from({ length: linhas }).map((_, i) => (
        <tr key={i} className="carregando">
          {Array.from({ length: colunas }).map((__, j) => (
            <td key={j} className="px-4 py-3.5">
              <div className="h-3.5 rounded bg-neutro-suave" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
