"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

export const Dialogo = Dialog.Root;
export const DialogoGatilho = Dialog.Trigger;
export const DialogoFechar = Dialog.Close;

export function DialogoConteudo({
  titulo,
  descricao,
  children,
  rodape,
  largura = "max-w-lg",
}: {
  titulo: string;
  descricao?: string;
  children: React.ReactNode;
  rodape?: React.ReactNode;
  largura?: string;
}) {
  return (
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-50 bg-black/35 backdrop-blur-[2px] data-[state=open]:animate-[surgir_0.2s_ease]" />
      <Dialog.Content
        className={cn(
          "fixed top-1/2 left-1/2 z-50 w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2",
          "rounded-card border border-borda bg-fundo-elevado shadow-2xl",
          "max-h-[88vh] overflow-y-auto data-[state=open]:animate-[surgir_0.22s_cubic-bezier(0.16,1,0.3,1)]",
          largura,
        )}
      >
        <div className="flex items-start justify-between gap-4 px-6 pt-6 pb-4">
          <div>
            <Dialog.Title className="text-base font-semibold text-texto">
              {titulo}
            </Dialog.Title>
            {descricao && (
              <Dialog.Description className="mt-1 text-[13px] text-texto-suave">
                {descricao}
              </Dialog.Description>
            )}
          </div>
          <Dialog.Close className="rounded-md p-1.5 text-texto-tenue transition-colors hover:bg-neutro-suave hover:text-texto">
            <X className="size-4" />
          </Dialog.Close>
        </div>
        <div className="px-6 pb-6">{children}</div>
        {rodape && (
          <div className="flex justify-end gap-2 border-t border-borda px-6 py-4">
            {rodape}
          </div>
        )}
      </Dialog.Content>
    </Dialog.Portal>
  );
}
