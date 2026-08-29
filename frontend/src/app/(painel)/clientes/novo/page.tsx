"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { FormularioCliente } from "@/components/clientes/formulario";
import { TituloPagina } from "@/components/ui/pagina";

export default function PaginaNovoCliente() {
  return (
    <>
      <Link
        href="/clientes"
        className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-texto-suave hover:text-texto"
      >
        <ArrowLeft className="size-3.5" /> Clientes
      </Link>

      <TituloPagina
        titulo="Novo cliente"
        descricao="Nome, documento e endereço vão impressos no boleto e transmitidos ao banco."
      />

      <FormularioCliente />
    </>
  );
}
