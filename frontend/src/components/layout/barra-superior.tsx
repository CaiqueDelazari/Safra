"use client";

import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  Building2,
  Check,
  ChevronsUpDown,
  LogOut,
  Menu,
  Moon,
  Sun,
  TriangleAlert,
  UserRound,
} from "lucide-react";
import { useTheme } from "next-themes";
import Link from "next/link";
import * as React from "react";

import { BuscaGlobal } from "@/components/layout/busca-global";
import { useRecursoVivo } from "@/lib/hooks";
import type { Pendencias } from "@/lib/tipos";
import { cn, iniciais, numero } from "@/lib/utils";
import { useSessao } from "@/providers/sessao";

const itemMenu =
  "flex w-full cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] text-texto outline-none data-[highlighted]:bg-superficie-sutil";
const conteudoMenu =
  "surgir z-50 min-w-56 rounded-card border border-borda bg-fundo-elevado p-1.5 shadow-xl";

export function BarraSuperior({ aoAbrirMenu }: { aoAbrirMenu: () => void }) {
  return (
    <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-borda bg-fundo/85 px-4 backdrop-blur-md lg:px-6">
      <button
        onClick={aoAbrirMenu}
        className="rounded-md p-2 text-texto-suave hover:bg-neutro-suave lg:hidden"
        aria-label="Abrir menu"
      >
        <Menu className="size-5" />
      </button>

      <BuscaGlobal />

      <div className="ml-auto flex items-center gap-1.5">
        <SeletorEmpresa />
        <SinalDePendencias />
        <AlternarTema />
        <MenuPerfil />
      </div>
    </header>
  );
}

function SeletorEmpresa() {
  const { empresas, empresaAtiva, trocarEmpresa } = useSessao();
  if (empresas.length === 0) return null;

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger className="flex h-9 items-center gap-2 rounded-lg border border-borda px-2.5 text-[13px] transition-colors hover:bg-superficie-sutil">
        <Building2 className="size-4 text-texto-tenue" />
        <span className="hidden max-w-36 truncate sm:inline">
          {empresaAtiva?.nome_fantasia ?? "Selecione"}
        </span>
        <ChevronsUpDown className="size-3.5 text-texto-tenue" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6} className={conteudoMenu}>
          <p className="px-2.5 py-1.5 text-[11px] font-medium tracking-wider text-texto-tenue uppercase">
            Empresa ativa
          </p>
          {empresas.map((empresa) => (
            <DropdownMenu.Item
              key={empresa.id}
              className={itemMenu}
              onSelect={() => trocarEmpresa(empresa.id)}
            >
              <span
                className="size-2 shrink-0 rounded-full"
                style={{ background: empresa.cor_primaria ?? "var(--acento)" }}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate">{empresa.nome_fantasia}</span>
                <span className="block truncate text-[11px] text-texto-tenue tabular">
                  {empresa.cnpj}
                </span>
              </span>
              {empresaAtiva?.id === empresa.id && (
                <Check className="size-3.5 text-acento" />
              )}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

/**
 * O sino que este sistema precisa.
 *
 * O ERP de onde a barra veio tinha notificações; aqui não existem, e um sino
 * que nunca toca é pior que sino nenhum — ensina a pessoa a ignorar aquele
 * canto da tela. O que este sistema tem de urgente é outra coisa: rejeição
 * do banco, retorno que não processou, lote parado esperando envio. Nada
 * disso se resolve sozinho, e todos falham em silêncio.
 *
 * Por isso o contador é de pendências, e ele **some quando não há nenhuma**.
 * Um "0" permanente treinaria o olho a não olhar; a ausência do sinal é a
 * informação de que está tudo em dia.
 */
function SinalDePendencias() {
  const { dados } = useRecursoVivo<Pendencias>(
    "/reconciliation/pendencias/",
    {},
    60_000,
  );

  const itens = dados
    ? [
        { rotulo: "cobranças rejeitadas pelo banco", n: dados.cobrancas_rejeitadas },
        { rotulo: "cobranças com erro", n: dados.cobrancas_com_erro },
        { rotulo: "pagamentos sem cobrança", n: dados.ocorrencias_orfas },
        { rotulo: "arquivos com problema", n: dados.arquivos_com_erro },
        { rotulo: "lotes com erro", n: dados.lotes_com_erro },
        { rotulo: "lotes aguardando envio", n: dados.lotes_aguardando_envio },
        { rotulo: "clientes sem endereço", n: dados.clientes_sem_endereco },
      ].filter((item) => item.n > 0)
    : [];

  const total = itens.reduce((soma, item) => soma + item.n, 0);
  if (total === 0) return null;

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        className="relative flex size-9 items-center justify-center rounded-lg text-atencao transition-colors hover:bg-atencao-suave"
        aria-label={`${total} pendências`}
      >
        <TriangleAlert className="size-4.5" />
        <span className="absolute top-1.5 right-1.5 flex size-4 items-center justify-center rounded-full bg-atencao text-[9.5px] font-semibold text-white">
          {total > 9 ? "9+" : total}
        </span>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          className={cn(conteudoMenu, "w-80 max-w-[calc(100vw-2rem)] p-0")}
        >
          <div className="border-b border-borda px-4 py-3">
            <p className="text-[13px] font-semibold">
              {numero(total)} {total === 1 ? "pendência" : "pendências"}
            </p>
            <p className="mt-0.5 text-[12px] text-texto-suave">
              Nada aqui se resolve sozinho.
            </p>
          </div>
          <ul className="max-h-80 overflow-y-auto py-1">
            {itens.map((item) => (
              <li
                key={item.rotulo}
                className="flex items-baseline gap-2 px-4 py-1.5 text-[12.5px]"
              >
                <span className="font-medium tabular">{item.n}</span>
                <span className="text-texto-suave">{item.rotulo}</span>
              </li>
            ))}
          </ul>
          <div className="border-t border-borda p-1.5">
            <DropdownMenu.Item asChild className={itemMenu}>
              <Link href="/pendencias">Ver todas</Link>
            </DropdownMenu.Item>
          </div>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

const SEM_ASSINATURA = () => () => {};

function AlternarTema() {
  const { resolvedTheme, setTheme } = useTheme();
  // O tema real só existe no navegador. Em vez de um efeito para "já montei",
  // a própria renderização pergunta onde está: false no servidor, true no
  // cliente — sem divergência de hidratação e sem render em cascata.
  const montado = React.useSyncExternalStore(
    SEM_ASSINATURA,
    () => true,
    () => false,
  );

  return (
    <button
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      className="flex size-9 items-center justify-center rounded-lg text-texto-suave transition-colors hover:bg-neutro-suave hover:text-texto"
      aria-label="Alternar tema"
    >
      {montado && resolvedTheme === "dark" ? (
        <Sun className="size-4.5" />
      ) : (
        <Moon className="size-4.5" />
      )}
    </button>
  );
}

function MenuPerfil() {
  const { usuario, sair } = useSessao();

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger className="flex size-9 items-center justify-center rounded-full bg-acento-suave text-[12px] font-semibold text-acento">
        {iniciais(usuario?.nome_completo) || <UserRound className="size-4" />}
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6} className={conteudoMenu}>
          <div className="border-b border-borda px-2.5 pt-1 pb-2.5">
            <p className="truncate text-[13px] font-medium">
              {usuario?.nome_completo}
            </p>
            <p className="truncate text-[11.5px] text-texto-tenue">{usuario?.email}</p>
          </div>
          <DropdownMenu.Item asChild className={cn(itemMenu, "mt-1")}>
            <Link href="/perfil">
              <UserRound className="size-4 text-texto-tenue" />
              Meu perfil
            </Link>
          </DropdownMenu.Item>
          <DropdownMenu.Item
            className={cn(itemMenu, "text-negativo")}
            onSelect={() => sair()}
          >
            <LogOut className="size-4" />
            Sair
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
