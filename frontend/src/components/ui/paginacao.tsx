"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";

import { Botao } from "@/components/ui/button";
import { numero } from "@/lib/utils";

export function Paginacao({
  pagina,
  paginas,
  total,
  aoMudar,
  rotulo = "registros",
}: {
  pagina: number;
  paginas: number;
  total: number;
  aoMudar: (p: number) => void;
  rotulo?: string;
}) {
  if (total === 0) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-borda px-5 py-3.5">
      <p className="text-[12.5px] text-texto-tenue">
        {numero(total)} {rotulo} · página {pagina} de {paginas}
      </p>
      <div className="flex items-center gap-1.5">
        <Botao
          variante="contorno"
          tamanho="icone-sm"
          disabled={pagina <= 1}
          onClick={() => aoMudar(pagina - 1)}
          aria-label="Página anterior"
        >
          <ChevronLeft />
        </Botao>
        <Botao
          variante="contorno"
          tamanho="icone-sm"
          disabled={pagina >= paginas}
          onClick={() => aoMudar(pagina + 1)}
          aria-label="Próxima página"
        >
          <ChevronRight />
        </Botao>
      </div>
    </div>
  );
}
