"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

const base =
  "w-full rounded-lg border border-borda bg-superficie px-3 text-sm text-texto placeholder:text-texto-tenue transition-colors hover:border-borda-forte focus:border-acento focus:outline-none focus:ring-4 focus:ring-[var(--anel)] disabled:cursor-not-allowed disabled:opacity-55";

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input ref={ref} className={cn(base, "h-9.5", className)} {...props} />
));
Input.displayName = "Input";

export const AreaTexto = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(base, "min-h-24 resize-y py-2.5 leading-relaxed", className)}
    {...props}
  />
));
AreaTexto.displayName = "AreaTexto";

export const Selecao = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      base,
      "h-9.5 cursor-pointer appearance-none bg-[length:16px] bg-[right_0.6rem_center] bg-no-repeat pr-9",
      "bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 fill=%22none%22 stroke=%22%23888%22 stroke-width=%222%22 viewBox=%220 0 24 24%22><path d=%22m6 9 6 6 6-6%22/></svg>')]",
      className,
    )}
    {...props}
  >
    {children}
  </select>
));
Selecao.displayName = "Selecao";

export function Rotulo({
  className,
  obrigatorio,
  children,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement> & { obrigatorio?: boolean }) {
  return (
    <label
      className={cn("mb-1.5 block text-[13px] font-medium text-texto-suave", className)}
      {...props}
    >
      {children}
      {obrigatorio && <span className="ml-0.5 text-negativo">*</span>}
    </label>
  );
}

export function Campo({
  rotulo,
  erro,
  dica,
  obrigatorio,
  className,
  children,
}: {
  rotulo?: string;
  erro?: string;
  dica?: string;
  obrigatorio?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={className}>
      {rotulo && <Rotulo obrigatorio={obrigatorio}>{rotulo}</Rotulo>}
      {children}
      {erro ? (
        <p className="mt-1.5 text-[12px] text-negativo">{erro}</p>
      ) : dica ? (
        <p className="mt-1.5 text-[12px] text-texto-tenue">{dica}</p>
      ) : null}
    </div>
  );
}
