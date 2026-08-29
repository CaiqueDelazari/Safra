"use client";

import { Slot, Slottable } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

const estilos = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium whitespace-nowrap transition-all disabled:pointer-events-none disabled:opacity-45 [&_svg]:shrink-0",
  {
    variants: {
      variante: {
        primario:
          "bg-acento text-acento-texto hover:brightness-110 active:brightness-95 shadow-[0_1px_2px_rgba(0,0,0,0.06)]",
        contorno:
          "border border-borda bg-superficie text-texto hover:bg-superficie-sutil hover:border-borda-forte",
        sutil: "bg-neutro-suave text-texto hover:bg-borda",
        fantasma: "text-texto-suave hover:bg-neutro-suave hover:text-texto",
        perigo: "bg-negativo text-white hover:brightness-110",
        link: "text-acento underline-offset-4 hover:underline",
      },
      tamanho: {
        sm: "h-8 px-3 text-[13px] [&_svg]:size-3.5",
        md: "h-9.5 px-4 text-sm [&_svg]:size-4",
        lg: "h-11 px-5 text-[15px] [&_svg]:size-4.5",
        icone: "size-9 [&_svg]:size-4",
        "icone-sm": "size-8 [&_svg]:size-3.5",
      },
    },
    defaultVariants: { variante: "primario", tamanho: "md" },
  },
);

export interface BotaoProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof estilos> {
  asChild?: boolean;
  carregando?: boolean;
}

export const Botao = React.forwardRef<HTMLButtonElement, BotaoProps>(
  (
    { className, variante, tamanho, asChild, carregando, children, disabled, ...props },
    ref,
  ) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(estilos({ variante, tamanho }), className)}
        disabled={disabled || carregando}
        {...props}
      >
        {carregando ? <Loader2 className="animate-spin" /> : null}
        {/* Com `asChild`, o Slot exige saber qual filho é o elemento a ser
            fundido. Sem o Slottable, o spinner vira um segundo filho e o
            Radix derruba a árvore inteira ("Expected a single React element
            child"). Fora do asChild, o Slottable é transparente. */}
        <Slottable>{children}</Slottable>
      </Comp>
    );
  },
);
Botao.displayName = "Botao";
