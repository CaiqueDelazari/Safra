"use client";

import { KeyRound, Save, ShieldCheck, ShieldOff } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Botao } from "@/components/ui/button";
import { Campo, Input } from "@/components/ui/campos";
import { Secao, TituloPagina } from "@/components/ui/pagina";
import { api, ApiError } from "@/lib/api";
import { useSessao } from "@/providers/sessao";

export default function PaginaPerfil() {
  const { usuario, recarregarUsuario } = useSessao();

  if (!usuario) {
    return <div className="carregando h-64 rounded-card bg-neutro-suave" />;
  }

  return (
    <>
      <TituloPagina titulo="Meu perfil" descricao={usuario.email} />

      <div className="grid gap-5 lg:grid-cols-2">
        <DadosPessoais aoSalvar={recarregarUsuario} />
        <div className="space-y-5">
          <TrocarSenha />
          <SegundoFator ativo={usuario.segundo_fator_ativo} aoMudar={recarregarUsuario} />
        </div>
      </div>
    </>
  );
}

function DadosPessoais({ aoSalvar }: { aoSalvar: () => void }) {
  const { usuario, empresas } = useSessao();
  const [form, setForm] = React.useState({
    nome_completo: usuario?.nome_completo ?? "",
    telefone: usuario?.telefone ?? "",
    empresa_padrao: usuario?.empresa_padrao ?? null,
  });
  const [salvando, setSalvando] = React.useState(false);

  async function salvar(evento: React.FormEvent) {
    evento.preventDefault();
    setSalvando(true);
    try {
      await api.patch("/auth/me/", form);
      toast.success("Perfil atualizado.");
      aoSalvar();
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha ao salvar.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Secao titulo="Dados">
      <form onSubmit={salvar} className="space-y-4 p-5">
        <Campo rotulo="Nome completo" obrigatorio>
          <Input
            value={form.nome_completo}
            onChange={(e) => setForm({ ...form, nome_completo: e.target.value })}
          />
        </Campo>
        <Campo rotulo="E-mail" dica="O e-mail é o seu login e não muda por aqui.">
          <Input value={usuario?.email ?? ""} disabled />
        </Campo>
        <Campo rotulo="Telefone">
          <Input
            value={form.telefone}
            onChange={(e) => setForm({ ...form, telefone: e.target.value })}
          />
        </Campo>

        {empresas.length > 1 && (
          <Campo
            rotulo="Empresa que abre ao entrar"
            dica="Você acessa mais de uma. Esta é a que aparece primeiro."
          >
            <select
              value={form.empresa_padrao ?? ""}
              onChange={(e) =>
                setForm({
                  ...form,
                  empresa_padrao: e.target.value ? Number(e.target.value) : null,
                })
              }
              className="h-9.5 w-full cursor-pointer rounded-lg border border-borda bg-superficie px-3 text-sm"
            >
              {empresas.map((empresa) => (
                <option key={empresa.id} value={empresa.id}>
                  {empresa.nome_fantasia}
                </option>
              ))}
            </select>
          </Campo>
        )}

        <div className="rounded-lg border border-borda bg-superficie-sutil px-3.5 py-3">
          <p className="text-[12px] tracking-wide text-texto-tenue uppercase">
            Seu acesso
          </p>
          <ul className="mt-2 space-y-1.5">
            {empresas.map((empresa) => (
              <li key={empresa.id} className="flex items-center justify-between gap-2">
                <span className="truncate text-[13px]">{empresa.nome_fantasia}</span>
                <Badge tom="contorno">
                  {empresa.papel
                    ? empresa.papel.charAt(0) + empresa.papel.slice(1).toLowerCase()
                    : "—"}
                </Badge>
              </li>
            ))}
          </ul>
          {empresas.length > 1 && (
            <p className="mt-2.5 text-[12px] text-texto-tenue">
              O seu papel é de cada empresa, não da conta — por isso ele pode
              ser diferente em cada linha.
            </p>
          )}
        </div>

        <div className="flex justify-end">
          <Botao type="submit" carregando={salvando}>
            <Save /> Salvar
          </Botao>
        </div>
      </form>
    </Secao>
  );
}

function TrocarSenha() {
  const [form, setForm] = React.useState({ senha_atual: "", nova_senha: "", repetir: "" });
  const [salvando, setSalvando] = React.useState(false);

  async function trocar(evento: React.FormEvent) {
    evento.preventDefault();
    if (form.nova_senha !== form.repetir) {
      toast.error("A nova senha e a repetição não conferem.");
      return;
    }
    setSalvando(true);
    try {
      await api.post("/auth/change-password/", {
        senha_atual: form.senha_atual,
        nova_senha: form.nova_senha,
      });
      toast.success("Senha alterada.");
      setForm({ senha_atual: "", nova_senha: "", repetir: "" });
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha ao trocar a senha.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Secao titulo="Senha">
      <form onSubmit={trocar} className="space-y-4 p-5">
        <Campo rotulo="Senha atual" obrigatorio>
          <Input
            type="password"
            autoComplete="current-password"
            value={form.senha_atual}
            onChange={(e) => setForm({ ...form, senha_atual: e.target.value })}
          />
        </Campo>
        <Campo rotulo="Nova senha" obrigatorio dica="Mínimo de 10 caracteres.">
          <Input
            type="password"
            autoComplete="new-password"
            value={form.nova_senha}
            onChange={(e) => setForm({ ...form, nova_senha: e.target.value })}
          />
        </Campo>
        <Campo rotulo="Repita a nova senha" obrigatorio>
          <Input
            type="password"
            autoComplete="new-password"
            value={form.repetir}
            onChange={(e) => setForm({ ...form, repetir: e.target.value })}
          />
        </Campo>
        <div className="flex justify-end">
          <Botao
            type="submit"
            variante="contorno"
            carregando={salvando}
            disabled={!form.senha_atual || !form.nova_senha}
          >
            <KeyRound /> Trocar senha
          </Botao>
        </div>
      </form>
    </Secao>
  );
}

/**
 * Segundo fator.
 *
 * Vale insistir com quem administra a conta: essa pessoa cadastra a conta
 * bancária, e a conta bancária é para onde o dinheiro vai. Senha vazada num
 * outro site, reaproveitada aqui, é o caminho mais curto entre um vazamento
 * qualquer e a cobrança da empresa indo para outro lugar.
 */
function SegundoFator({ ativo, aoMudar }: { ativo: boolean; aoMudar: () => void }) {
  const [cadastro, setCadastro] = React.useState<{
    qr_svg: string;
    segredo: string;
  } | null>(null);
  const [codigo, setCodigo] = React.useState("");
  const [senha, setSenha] = React.useState("");
  const [codigos, setCodigos] = React.useState<string[] | null>(null);
  const [ocupado, setOcupado] = React.useState(false);

  async function iniciar() {
    setOcupado(true);
    try {
      setCadastro(await api.post("/auth/two-factor/"));
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha ao iniciar.");
    } finally {
      setOcupado(false);
    }
  }

  async function confirmar() {
    setOcupado(true);
    try {
      const resposta = await api.put<{ codigos_recuperacao: string[] }>(
        "/auth/two-factor/",
        { codigo },
      );
      setCodigos(resposta.codigos_recuperacao);
      setCadastro(null);
      setCodigo("");
      toast.success("Segundo fator ativado.");
      aoMudar();
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Código inválido.");
    } finally {
      setOcupado(false);
    }
  }

  async function desligar() {
    setOcupado(true);
    try {
      await api.delete("/auth/two-factor/", { senha });
      setSenha("");
      toast.success("Segundo fator desativado.");
      aoMudar();
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Senha incorreta.");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Secao titulo="Segundo fator">
      <div className="space-y-4 p-5">
        {codigos && (
          <div className="rounded-lg border border-atencao/30 bg-atencao-suave p-4">
            <p className="text-[13px] font-medium">
              Guarde estes códigos de recuperação
            </p>
            <p className="mt-0.5 text-[12px] text-texto-suave">
              Eles aparecem uma vez só. São o que devolve o seu acesso se você
              perder o celular.
            </p>
            <ul className="mt-3 grid grid-cols-2 gap-1.5 font-mono text-[13px]">
              {codigos.map((c) => (
                <li key={c} className="rounded bg-superficie px-2 py-1 text-center">
                  {c}
                </li>
              ))}
            </ul>
            <Botao
              variante="contorno"
              tamanho="sm"
              className="mt-3 w-full"
              onClick={() => {
                navigator.clipboard.writeText(codigos.join("\n"));
                toast.success("Códigos copiados.");
              }}
            >
              Copiar
            </Botao>
          </div>
        )}

        {ativo ? (
          <>
            <Badge tom="positivo" ponto>
              <ShieldCheck className="size-3" /> Ativo
            </Badge>
            <p className="text-[13px] text-texto-suave">
              A entrada pede o código do aplicativo autenticador além da senha.
            </p>
            <Campo rotulo="Para desligar, confirme a senha">
              <Input
                type="password"
                autoComplete="current-password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
              />
            </Campo>
            <Botao
              variante="perigo"
              onClick={desligar}
              disabled={!senha}
              carregando={ocupado}
            >
              <ShieldOff /> Desativar
            </Botao>
          </>
        ) : cadastro ? (
          <>
            <p className="text-[13px]">
              Leia o código no seu aplicativo autenticador e digite os seis
              dígitos que ele mostrar.
            </p>
            <div
              className="mx-auto w-48 rounded-lg bg-white p-3"
              dangerouslySetInnerHTML={{ __html: cadastro.qr_svg }}
            />
            <p className="text-center text-[12px] text-texto-tenue">
              Não consegue ler? Digite:{" "}
              <span className="font-mono">{cadastro.segredo}</span>
            </p>
            <Campo rotulo="Código do aplicativo" obrigatorio>
              <Input
                inputMode="numeric"
                maxLength={8}
                value={codigo}
                onChange={(e) => setCodigo(e.target.value)}
              />
            </Campo>
            <div className="flex gap-2">
              <Botao variante="contorno" onClick={() => setCadastro(null)}>
                Cancelar
              </Botao>
              <Botao onClick={confirmar} disabled={!codigo} carregando={ocupado}>
                Confirmar
              </Botao>
            </div>
          </>
        ) : (
          <>
            <p className="text-[13px] text-texto-suave">
              Um código de seis dígitos além da senha. Vale especialmente para
              quem administra a conta: é essa pessoa que cadastra a conta
              bancária, e a conta bancária é para onde o dinheiro vai.
            </p>
            <Botao onClick={iniciar} carregando={ocupado}>
              <ShieldCheck /> Ativar
            </Botao>
          </>
        )}
      </div>
    </Secao>
  );
}
