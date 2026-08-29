"use client";

import { Eye, EyeOff, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Botao } from "@/components/ui/button";
import { Campo, Input } from "@/components/ui/campos";
import { ApiError } from "@/lib/api";
import { useSessao } from "@/providers/sessao";

export default function PaginaLogin() {
  const { entrar, usuario, carregando } = useSessao();
  const router = useRouter();
  const [email, setEmail] = React.useState("");
  const [senha, setSenha] = React.useState("");
  const [mostrarSenha, setMostrarSenha] = React.useState(false);
  const [codigo, setCodigo] = React.useState("");
  //: Só aparece depois que o servidor disser que esta conta usa segundo fator.
  const [pedeCodigo, setPedeCodigo] = React.useState(false);
  const [erro, setErro] = React.useState("");
  const [enviando, setEnviando] = React.useState(false);

  // Quem já tem sessão não fica na tela de login: vai direto para a operação.
  React.useEffect(() => {
    if (!carregando && usuario) router.replace("/dashboard");
  }, [carregando, usuario, router]);

  const enviar = async (evento: React.FormEvent) => {
    evento.preventDefault();
    setErro("");
    setEnviando(true);
    try {
      await entrar(email.trim(), senha, codigo.trim() || undefined);
    } catch (e) {
      const motivo =
        e instanceof ApiError
          ? (e.corpo as { codigo?: string } | undefined)?.codigo
          : undefined;
      if (motivo === "segundo_fator_exigido") {
        // A senha estava certa: agora falta o código. Nada de "senha incorreta".
        setPedeCodigo(true);
        setErro("");
      } else if (motivo === "segundo_fator_invalido") {
        setPedeCodigo(true);
        setCodigo("");
        setErro("Código inválido ou já usado. Aguarde o próximo e tente de novo.");
      } else {
        setErro(
          e instanceof ApiError && e.status === 401
            ? "E-mail ou senha incorretos."
            : "Não foi possível entrar. Tente novamente.",
        );
      }
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Painel de marca — some no mobile para não roubar espaço do formulário. */}
      <div className="relative hidden flex-col justify-between bg-[var(--texto)] p-12 text-[var(--fundo)] lg:flex">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-lg bg-white/10">
            <ShieldCheck className="size-5" />
          </div>
          <span className="text-[15px] font-semibold">Plataforma de Cobranças</span>
        </div>
        <div className="max-w-md">
          <h1 className="text-[32px] leading-[1.15] font-semibold tracking-tight">
            Quinhentos boletos em um clique. E o retorno do banco, sozinho.
          </h1>
          <p className="mt-4 text-[15px] leading-relaxed opacity-70">
            Clientes, cobranças e remessa em lote. O retorno bancário entra
            automaticamente e baixa cada título — sem conferir boleto por boleto.
          </p>
        </div>
        <p className="text-[12.5px] opacity-50">
          Dados isolados por empresa · Trilha de auditoria em todas as operações
        </p>
      </div>

      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <div className="flex size-9 items-center justify-center rounded-lg bg-acento text-acento-texto">
              <ShieldCheck className="size-5" />
            </div>
            <span className="text-[15px] font-semibold">Plataforma de Cobranças</span>
          </div>

          <h2 className="text-[22px] font-semibold tracking-tight">Entrar</h2>
          <p className="mt-1.5 text-[13.5px] text-texto-suave">
            Use as credenciais fornecidas pelo administrador.
          </p>

          <form onSubmit={enviar} className="mt-8 space-y-4">
            <Campo rotulo="E-mail" obrigatorio>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="voce@empresa.com.br"
                autoComplete="email"
                required
                autoFocus
              />
            </Campo>

            <Campo rotulo="Senha" obrigatorio>
              <div className="relative">
                <Input
                  type={mostrarSenha ? "text" : "password"}
                  value={senha}
                  onChange={(e) => setSenha(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  required
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setMostrarSenha((v) => !v)}
                  className="absolute top-1/2 right-2.5 -translate-y-1/2 text-texto-tenue hover:text-texto"
                  aria-label={mostrarSenha ? "Ocultar senha" : "Mostrar senha"}
                >
                  {mostrarSenha ? (
                    <EyeOff className="size-4" />
                  ) : (
                    <Eye className="size-4" />
                  )}
                </button>
              </div>
            </Campo>

            {pedeCodigo && (
              <Campo
                rotulo="Código do autenticador"
                obrigatorio
                dica="Seis dígitos do aplicativo. Um código de recuperação também serve."
              >
                <Input
                  value={codigo}
                  onChange={(e) => setCodigo(e.target.value)}
                  placeholder="000000"
                  inputMode="text"
                  autoComplete="one-time-code"
                  autoFocus
                  required
                />
              </Campo>
            )}

            {erro && (
              <div className="rounded-lg bg-negativo-suave px-3.5 py-2.5 text-[13px] text-negativo">
                {erro}
              </div>
            )}

            <Botao type="submit" carregando={enviando} className="w-full" tamanho="lg">
              {pedeCodigo ? "Confirmar código" : "Entrar no painel"}
            </Botao>
          </form>

          <p className="mt-8 text-center text-[12px] text-texto-tenue">
            Acesso monitorado e registrado em auditoria.
          </p>
        </div>
      </div>
    </div>
  );
}
