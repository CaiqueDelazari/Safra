"use client";

import { ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { MENU } from "@/components/layout/navegacao";
import { cn } from "@/lib/utils";
import { useSessao } from "@/providers/sessao";

const ROTULO_PAPEL: Record<string, string> = {
  ADMINISTRADOR: "Administrador",
  FINANCEIRO: "Financeiro",
  OPERADOR: "Operador",
  CONSULTA: "Consulta",
};

export function BarraLateral({
  aberta,
  aoFechar,
}: {
  aberta: boolean;
  aoFechar: () => void;
}) {
  const caminho = usePathname();
  const { pode, usuario, empresaAtiva } = useSessao();

  const grupos = MENU.map((grupo) => ({
    ...grupo,
    itens: grupo.itens.filter((item) => pode(item.modulo)),
  })).filter((grupo) => grupo.itens.length > 0);

  return (
    <>
      {aberta && (
        <div
          className="fixed inset-0 z-30 bg-black/30 lg:hidden"
          onClick={aoFechar}
          aria-hidden
        />
      )}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[264px] flex-col border-r border-borda bg-fundo-elevado",
          "transition-transform duration-200 lg:translate-x-0",
          aberta ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-16 items-center gap-2.5 border-b border-borda px-5">
          <div className="flex size-8.5 items-center justify-center rounded-lg bg-acento text-acento-texto">
            <ShieldCheck className="size-4.5" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[14px] leading-tight font-semibold">
              {empresaAtiva?.nome_fantasia ?? "Plataforma de Cobranças"}
            </p>
            <p className="truncate text-[11px] text-texto-tenue">
              Cobranças e boletos
            </p>
          </div>
          <button
            onClick={aoFechar}
            className="rounded-md p-1 text-texto-tenue hover:bg-neutro-suave lg:hidden"
            aria-label="Fechar menu"
          >
            <X className="size-4" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4">
          {grupos.map((grupo, indice) => (
            <div key={grupo.titulo ?? indice} className={indice > 0 ? "mt-6" : ""}>
              {grupo.titulo && (
                <p className="mb-1.5 px-3 text-[11px] font-medium tracking-wider text-texto-tenue uppercase">
                  {grupo.titulo}
                </p>
              )}
              <ul className="space-y-0.5">
                {grupo.itens.map((item) => {
                  const ativo =
                    caminho === item.href || caminho.startsWith(`${item.href}/`);
                  const Icone = item.icone;
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        onClick={aoFechar}
                        className={cn(
                          "flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] transition-colors",
                          ativo
                            ? "bg-acento-suave font-medium text-acento"
                            : "text-texto-suave hover:bg-neutro-suave hover:text-texto",
                        )}
                      >
                        <Icone
                          className={cn(
                            "size-4 shrink-0",
                            ativo ? "opacity-100" : "opacity-70",
                          )}
                        />
                        {item.rotulo}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="border-t border-borda p-3">
          <div className="rounded-lg bg-superficie-sutil px-3 py-2.5">
            <p className="truncate text-[13px] font-medium">
              {usuario?.nome_completo}
            </p>
            <p className="text-[11.5px] text-texto-tenue">
              {/* O papel é da EMPRESA ATIVA, não do usuário: a mesma pessoa
                  pode ser administradora aqui e consulta na empresa do
                  cliente dela. Trocar de empresa no seletor muda este texto. */}
              {usuario?.plataforma_admin
                ? "Suporte da plataforma"
                : (ROTULO_PAPEL[usuario?.papel ?? ""] ?? usuario?.papel ?? "—")}
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}
