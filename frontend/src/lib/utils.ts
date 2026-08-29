import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const moeda = (valor: number | string | null | undefined) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(
    Number(valor ?? 0),
  );

export const numero = (valor: number | string | null | undefined) =>
  new Intl.NumberFormat("pt-BR").format(Number(valor ?? 0));

export const data = (valor?: string | null) =>
  valor ? new Intl.DateTimeFormat("pt-BR").format(new Date(valor)) : "—";

export const dataHora = (valor?: string | null) =>
  valor
    ? new Intl.DateTimeFormat("pt-BR", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(new Date(valor))
    : "—";

export const iniciais = (nome?: string) =>
  (nome ?? "")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");

export const documento = (valor?: string) => {
  const d = (valor ?? "").replace(/\D/g, "");
  if (d.length === 11) return d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
  if (d.length === 14)
    return d.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5");
  return valor ?? "";
};

export const telefone = (valor?: string) => {
  const d = (valor ?? "").replace(/\D/g, "");
  if (d.length === 11) return d.replace(/(\d{2})(\d{5})(\d{4})/, "($1) $2-$3");
  if (d.length === 10) return d.replace(/(\d{2})(\d{4})(\d{4})/, "($1) $2-$3");
  return valor ?? "";
};
