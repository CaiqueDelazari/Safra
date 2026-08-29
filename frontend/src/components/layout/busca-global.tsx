"use client";

import { FileSignature, Receipt, Search, Users, Wrench } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import { api } from "@/lib/api";
import { useDebounce } from "@/lib/hooks";
import { cn } from "@/lib/utils";

interface Resultado {
  tipo: "cliente" | "ordem" | "contrato" | "cobranca";
  id: number;
  titulo: string;
  subtitulo: string;
  url: string;
  status: string;
}

const ICONES = {
  cliente: Users,
  ordem: Wrench,
  contrato: FileSignature,
  cobranca: Receipt,
};

const GRUPOS: Record<Resultado["tipo"], string> = {
  cliente: "Clientes",
  ordem: "Ordens de serviço",
  contrato: "Contratos",
  cobranca: "Cobranças",
};

export function BuscaGlobal() {
  const router = useRouter();
  const [termo, setTermo] = React.useState("");
  const [aberto, setAberto] = React.useState(false);
  const [destaque, setDestaque] = React.useState(0);
  const container = React.useRef<HTMLDivElement>(null);
  const entrada = React.useRef<HTMLInputElement>(null);

  // Menos de dois caracteres não é consulta — é gente ainda digitando.
  const digitado = useDebounce(termo.trim(), 260);
  const consulta = digitado.length >= 2 ? digitado : "";

  const [resposta, setResposta] = React.useState({
    consulta: "",
    itens: [] as Resultado[],
  });

  // "Buscando" é derivado: vale enquanto o que está em mãos não é a resposta
  // da consulta atual.
  const buscando = consulta !== "" && resposta.consulta !== consulta;
  const resultados = resposta.consulta === consulta ? resposta.itens : [];

  React.useEffect(() => {
    if (!consulta) return;
    api
      .get<{ resultados: Resultado[] }>("/busca/", { q: consulta })
      .then((dados) => {
        setResposta({ consulta, itens: dados.resultados });
        setDestaque(0);
        setAberto(true);
      })
      .catch(() => setResposta({ consulta, itens: [] }));
  }, [consulta]);

  React.useEffect(() => {
    const fora = (e: MouseEvent) => {
      if (!container.current?.contains(e.target as Node)) setAberto(false);
    };
    const atalho = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        entrada.current?.focus();
      }
    };
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", atalho);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", atalho);
    };
  }, []);

  const abrir = (resultado: Resultado) => {
    setAberto(false);
    setTermo("");
    router.push(resultado.url);
  };

  const teclado = (e: React.KeyboardEvent) => {
    if (!aberto || resultados.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setDestaque((d) => (d + 1) % resultados.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setDestaque((d) => (d - 1 + resultados.length) % resultados.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      abrir(resultados[destaque]);
    } else if (e.key === "Escape") {
      setAberto(false);
    }
  };

  const agrupados = resultados.reduce<Record<string, Resultado[]>>((acc, item) => {
    (acc[item.tipo] ??= []).push(item);
    return acc;
  }, {});

  return (
    <div ref={container} className="relative w-full max-w-md">
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-texto-tenue" />
      <input
        ref={entrada}
        value={termo}
        onChange={(e) => setTermo(e.target.value)}
        onFocus={() => resultados.length && setAberto(true)}
        onKeyDown={teclado}
        placeholder="Buscar cliente, telefone, OS, endereço…"
        className="h-9.5 w-full rounded-lg border border-borda bg-superficie-sutil pr-3 pl-9 text-sm placeholder:text-texto-tenue focus:border-acento focus:bg-superficie focus:ring-4 focus:ring-[var(--anel)] focus:outline-none sm:pr-14"
      />
      {/* No celular não há teclado com Ctrl: o atalho só atrapalharia o texto. */}
      <kbd className="pointer-events-none absolute top-1/2 right-3 hidden -translate-y-1/2 rounded border border-borda px-1.5 py-0.5 text-[10.5px] text-texto-tenue sm:block">
        Ctrl K
      </kbd>

      {aberto && (
        <div className="surgir absolute top-[calc(100%+6px)] left-0 z-50 max-h-[70vh] w-full overflow-y-auto rounded-card border border-borda bg-fundo-elevado py-1.5 shadow-xl">
          {buscando && resultados.length === 0 ? (
            <p className="px-4 py-6 text-center text-[13px] text-texto-tenue">
              Buscando…
            </p>
          ) : resultados.length === 0 ? (
            <p className="px-4 py-6 text-center text-[13px] text-texto-tenue">
              Nenhum resultado para “{termo}”.
            </p>
          ) : (
            Object.entries(agrupados).map(([tipo, itens]) => (
              <div key={tipo}>
                <p className="px-3 py-1.5 text-[11px] font-medium tracking-wider text-texto-tenue uppercase">
                  {GRUPOS[tipo as Resultado["tipo"]]}
                </p>
                {itens.map((item) => {
                  const Icone = ICONES[item.tipo];
                  const indice = resultados.indexOf(item);
                  return (
                    <button
                      key={`${item.tipo}-${item.id}`}
                      onClick={() => abrir(item)}
                      onMouseEnter={() => setDestaque(indice)}
                      className={cn(
                        "flex w-full items-center gap-3 px-3 py-2 text-left",
                        indice === destaque && "bg-superficie-sutil",
                      )}
                    >
                      <Icone className="size-4 shrink-0 text-texto-tenue" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13.5px] text-texto">
                          {item.titulo}
                        </span>
                        <span className="block truncate text-[12px] text-texto-tenue">
                          {item.subtitulo}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
