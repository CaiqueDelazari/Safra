"use client";

import { useRouter } from "next/navigation";
import * as React from "react";

import { api, armazenamento } from "@/lib/api";
import type { Empresa, Usuario } from "@/lib/tipos";

interface Sessao {
  usuario: Usuario | null;
  empresas: Empresa[];
  empresaAtiva: Empresa | null;
  carregando: boolean;
  entrar: (email: string, senha: string, codigo?: string) => Promise<void>;
  sair: () => Promise<void>;
  trocarEmpresa: (id: number) => void;
  /** Relê /auth/me/ — usado quando algo do próprio usuário muda. */
  recarregarUsuario: () => Promise<void>;
  /** Consulta a matriz RBAC devolvida pelo backend — a UI nunca inventa permissão. */
  pode: (modulo: string, acao?: string) => boolean;
  /**
   * Consulta as operações nomeadas (enviar remessa, processar retorno…).
   *
   * Separado de `pode` pelo mesmo motivo que no backend: "gerar lote" não é
   * `create` de coisa nenhuma. Sem isso, a tela mostraria o botão de enviar
   * remessa a um Operador e ele levaria 403 ao clicar — a permissão estaria
   * certa e a interface, mentindo.
   */
  podeCapacidade: (capacidade: string) => boolean;
  veValores: boolean;
}

const Contexto = React.createContext<Sessao | null>(null);

export function ProvedorSessao({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [usuario, setUsuario] = React.useState<Usuario | null>(null);
  const [empresaId, setEmpresaId] = React.useState<number | null>(null);
  const [carregando, setCarregando] = React.useState(true);

  const aplicarUsuario = React.useCallback((dados: Usuario) => {
    setUsuario(dados);
    const atual = armazenamento.empresa;
    const permitidas = dados.empresas.map((e) => e.id);
    const escolhida =
      atual && permitidas.includes(atual)
        ? atual
        : (dados.empresa_padrao ?? permitidas[0] ?? null);
    armazenamento.empresa = escolhida;
    setEmpresaId(escolhida);
  }, []);

  React.useEffect(() => {
    let ativo = true;
    (async () => {
      if (!armazenamento.access) {
        setCarregando(false);
        return;
      }
      try {
        const dados = await api.get<Usuario>("/auth/me/");
        if (ativo) aplicarUsuario(dados);
      } catch {
        armazenamento.limpar();
      } finally {
        if (ativo) setCarregando(false);
      }
    })();
    return () => {
      ativo = false;
    };
  }, [aplicarUsuario]);

  const entrar = React.useCallback(
    async (email: string, senha: string, codigo?: string) => {
      const resposta = await api.post<{
        access: string;
        refresh: string;
        usuario: Usuario;
      }>(
        "/auth/login/",
        // O código do autenticador só vai quando existe: quem não cadastrou
        // segundo fator não deve receber campo nenhum a mais.
        { email, password: senha, ...(codigo ? { codigo } : {}) },
        { semAuth: true },
      );
      armazenamento.salvarTokens(resposta.access, resposta.refresh);
      aplicarUsuario(resposta.usuario);
      router.replace("/dashboard");
    },
    [aplicarUsuario, router],
  );

  const sair = React.useCallback(async () => {
    try {
      await api.post("/auth/logout/", { refresh: armazenamento.refresh });
    } catch {
      /* o token pode já ter expirado — seguimos limpando a sessão */
    }
    armazenamento.limpar();
    setUsuario(null);
    setEmpresaId(null);
    router.replace("/login");
  }, [router]);

  const recarregarUsuario = React.useCallback(async () => {
    try {
      aplicarUsuario(await api.get<Usuario>("/auth/me/"));
    } catch {
      /* sessão perdida: o interceptador do cliente HTTP já trata */
    }
  }, [aplicarUsuario]);

  const trocarEmpresa = React.useCallback((id: number) => {
    armazenamento.empresa = id;
    setEmpresaId(id);
    // Recarrega os dados da rota atual já sob o novo CNPJ.
    window.location.reload();
  }, []);

  const pode = React.useCallback(
    (modulo: string, acao = "list") =>
      Boolean(usuario?.permissoes.modulos[modulo]?.includes(acao)),
    [usuario],
  );

  const podeCapacidade = React.useCallback(
    (capacidade: string) =>
      Boolean(usuario?.permissoes.capacidades?.includes(capacidade)),
    [usuario],
  );

  const valor: Sessao = {
    usuario,
    empresas: usuario?.empresas ?? [],
    empresaAtiva: usuario?.empresas.find((e) => e.id === empresaId) ?? null,
    carregando,
    entrar,
    sair,
    trocarEmpresa,
    recarregarUsuario,
    pode,
    podeCapacidade,
    veValores: Boolean(usuario?.permissoes.ve_valores),
  };

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useSessao() {
  const contexto = React.useContext(Contexto);
  if (!contexto)
    throw new Error("useSessao precisa estar dentro de <ProvedorSessao>.");
  return contexto;
}
