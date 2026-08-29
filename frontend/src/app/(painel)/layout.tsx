"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

import { BarraLateral } from "@/components/layout/barra-lateral";
import { BarraSuperior } from "@/components/layout/barra-superior";
import { useSessao } from "@/providers/sessao";

export default function LayoutPainel({
  children,
}: {
  children: React.ReactNode;
}) {
  const { usuario, carregando } = useSessao();
  const router = useRouter();
  const [menuAberto, setMenuAberto] = React.useState(false);

  React.useEffect(() => {
    if (!carregando && !usuario) router.replace("/login");
  }, [carregando, usuario, router]);

  if (carregando || !usuario) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="carregando h-2 w-32 rounded-full bg-neutro-suave" />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <BarraLateral aberta={menuAberto} aoFechar={() => setMenuAberto(false)} />
      <div className="lg:pl-[264px]">
        <BarraSuperior aoAbrirMenu={() => setMenuAberto(true)} />
        <main className="mx-auto w-full max-w-[1400px] px-4 py-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
