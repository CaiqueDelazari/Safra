"use client";

import { KeyRound, Pencil, Plus, ShieldCheck, UserX } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Botao } from "@/components/ui/button";
import { Campo, Input, Selecao } from "@/components/ui/campos";
import { Dialogo, DialogoConteudo } from "@/components/ui/dialogo";
import { Secao, TituloPagina } from "@/components/ui/pagina";
import {
  Cabecalho,
  Corpo,
  Esqueleto,
  Linha,
  Tabela,
  Td,
  Th,
  Vazio,
} from "@/components/ui/tabela";
import { api, ApiError } from "@/lib/api";
import { useLista } from "@/lib/hooks";
import type { Papel, UsuarioEquipe } from "@/lib/tipos";
import { data, numero } from "@/lib/utils";
import { useSessao } from "@/providers/sessao";

/**
 * O que cada papel faz. Aparece no formulário, ao lado da escolha.
 *
 * Escolher papel sem saber o que ele permite é como o acesso indevido
 * começa: na dúvida, todo mundo vira administrador. Descrever ali mesmo
 * custa três linhas e evita isso.
 */
const PAPEIS: { valor: Papel; rotulo: string; descricao: string }[] = [
  {
    valor: "ADMINISTRADOR",
    rotulo: "Administrador",
    descricao:
      "Faz tudo, inclusive cadastrar conta bancária e administrar a equipe.",
  },
  {
    valor: "FINANCEIRO",
    rotulo: "Financeiro",
    descricao:
      "Conduz a cobrança: cria, gera lote, envia remessa, processa retorno e concilia. Não mexe em usuário nem em credencial do banco.",
  },
  {
    valor: "OPERADOR",
    rotulo: "Operador",
    descricao:
      "Alimenta a base: cadastra cliente e cobrança. Não envia nada ao banco e não cancela título registrado.",
  },
  {
    valor: "CONSULTA",
    rotulo: "Consulta",
    descricao: "Só lê. Para contador, auditor ou sócio que acompanha o caixa.",
  },
];

const TOM_DO_PAPEL: Record<Papel, "acento" | "positivo" | "neutro" | "contorno"> = {
  ADMINISTRADOR: "acento",
  FINANCEIRO: "positivo",
  OPERADOR: "neutro",
  CONSULTA: "contorno",
};

export default function PaginaEquipe() {
  const { usuario } = useSessao();
  const lista = useLista<UsuarioEquipe>("/auth/users/");
  const [editando, setEditando] = React.useState<UsuarioEquipe | null>(null);
  const [criando, setCriando] = React.useState(false);
  const [alterando, setAlterando] = React.useState<number | null>(null);

  async function alternar(pessoa: UsuarioEquipe) {
    setAlterando(pessoa.id);
    try {
      await api.post(`/auth/users/${pessoa.id}/toggle-active/`);
      toast.success(
        pessoa.ativo_na_empresa ? "Acesso bloqueado." : "Acesso liberado.",
      );
      lista.recarregar();
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha na operação.");
    } finally {
      setAlterando(null);
    }
  }

  return (
    <>
      <TituloPagina
        titulo="Equipe"
        descricao="Quem tem acesso a esta empresa, e com que papel."
        acoes={
          <Botao onClick={() => setCriando(true)}>
            <Plus /> Adicionar pessoa
          </Botao>
        }
      />

      <Secao titulo={`${numero(lista.total)} pessoas`}>
        <Tabela>
          <Cabecalho>
            <tr>
              <Th>Pessoa</Th>
              <Th>Papel</Th>
              <Th>Segundo fator</Th>
              <Th>Desde</Th>
              <Th className="w-24" />
            </tr>
          </Cabecalho>
          <Corpo>
            {lista.carregando ? (
              <Esqueleto colunas={5} />
            ) : lista.dados.length === 0 ? (
              <Vazio colunas={5} titulo="Ninguém além de você" />
            ) : (
              lista.dados.map((pessoa) => (
                <Linha key={pessoa.id}>
                  <Td>
                    <p className="font-medium">
                      {pessoa.nome_completo}
                      {pessoa.id === usuario?.id && (
                        <span className="ml-1.5 text-[12px] text-texto-tenue">
                          (você)
                        </span>
                      )}
                    </p>
                    <p className="text-[12.5px] text-texto-tenue">{pessoa.email}</p>
                  </Td>
                  <Td>
                    {pessoa.papel ? (
                      <Badge tom={TOM_DO_PAPEL[pessoa.papel]}>
                        {PAPEIS.find((p) => p.valor === pessoa.papel)?.rotulo}
                      </Badge>
                    ) : (
                      <span className="text-[13px] text-texto-tenue">—</span>
                    )}
                    {!pessoa.ativo_na_empresa && (
                      <Badge tom="negativo" className="ml-1.5">
                        bloqueado
                      </Badge>
                    )}
                  </Td>
                  <Td>
                    {pessoa.segundo_fator_ativo ? (
                      <Badge tom="positivo">
                        <ShieldCheck className="size-3" /> ativo
                      </Badge>
                    ) : (
                      <span className="text-[12.5px] text-texto-tenue">
                        não configurado
                      </span>
                    )}
                  </Td>
                  <Td className="text-[13px] text-texto-suave">
                    {data(pessoa.criado_em)}
                  </Td>
                  <Td>
                    <div className="flex justify-end gap-1">
                      <Botao
                        variante="fantasma"
                        tamanho="icone-sm"
                        onClick={() => setEditando(pessoa)}
                        aria-label="Editar"
                      >
                        <Pencil />
                      </Botao>
                      {pessoa.id !== usuario?.id && (
                        <Botao
                          variante="fantasma"
                          tamanho="icone-sm"
                          onClick={() => alternar(pessoa)}
                          carregando={alterando === pessoa.id}
                          title={
                            pessoa.ativo_na_empresa
                              ? "Bloquear acesso a esta empresa"
                              : "Liberar acesso"
                          }
                          aria-label="Alternar acesso"
                        >
                          <UserX />
                        </Botao>
                      )}
                    </div>
                  </Td>
                </Linha>
              ))
            )}
          </Corpo>
        </Tabela>
      </Secao>

      <FormularioPessoa
        pessoa={editando}
        aberto={criando || editando !== null}
        aoFechar={() => {
          setCriando(false);
          setEditando(null);
        }}
        aoSalvar={lista.recarregar}
      />
    </>
  );
}

function FormularioPessoa({
  pessoa,
  aberto,
  aoFechar,
  aoSalvar,
}: {
  pessoa: UsuarioEquipe | null;
  aberto: boolean;
  aoFechar: () => void;
  aoSalvar: () => void;
}) {
  const [form, setForm] = React.useState({
    nome_completo: "",
    email: "",
    telefone: "",
    papel: "CONSULTA" as Papel,
    senha: "",
  });
  const [salvando, setSalvando] = React.useState(false);

  React.useEffect(() => {
    if (!aberto) return;
    // Reinicializa o formulário ao abrir para outra pessoa.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setForm({
      nome_completo: pessoa?.nome_completo ?? "",
      email: pessoa?.email ?? "",
      telefone: pessoa?.telefone ?? "",
      papel: pessoa?.papel ?? "CONSULTA",
      senha: "",
    });
  }, [aberto, pessoa]);

  async function salvar() {
    setSalvando(true);
    try {
      const corpo = { ...form, senha: form.senha || undefined };
      if (pessoa) await api.patch(`/auth/users/${pessoa.id}/`, corpo);
      else await api.post("/auth/users/", corpo);
      toast.success(pessoa ? "Alterações salvas." : "Pessoa adicionada à equipe.");
      aoSalvar();
      aoFechar();
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha ao salvar.");
    } finally {
      setSalvando(false);
    }
  }

  const escolhido = PAPEIS.find((p) => p.valor === form.papel);

  return (
    <Dialogo open={aberto} onOpenChange={(v) => !v && aoFechar()}>
      <DialogoConteudo
        titulo={pessoa ? `Editar ${pessoa.nome_completo}` : "Adicionar à equipe"}
        descricao={
          pessoa
            ? undefined
            : "Se a pessoa já tem conta na plataforma, ela é vinculada a esta empresa — não é criada de novo, e a senha dela não muda."
        }
        rodape={
          <>
            <Botao variante="contorno" onClick={aoFechar} disabled={salvando}>
              Cancelar
            </Botao>
            <Botao onClick={salvar} carregando={salvando}>
              Salvar
            </Botao>
          </>
        }
      >
        <div className="space-y-4">
          <Campo rotulo="Nome completo" obrigatorio>
            <Input
              value={form.nome_completo}
              onChange={(e) => setForm({ ...form, nome_completo: e.target.value })}
            />
          </Campo>
          <Campo rotulo="E-mail" obrigatorio>
            <Input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              disabled={Boolean(pessoa)}
            />
          </Campo>
          <Campo rotulo="Telefone">
            <Input
              value={form.telefone}
              onChange={(e) => setForm({ ...form, telefone: e.target.value })}
            />
          </Campo>

          <Campo rotulo="Papel nesta empresa" obrigatorio dica={escolhido?.descricao}>
            <Selecao
              value={form.papel}
              onChange={(e) => setForm({ ...form, papel: e.target.value as Papel })}
            >
              {PAPEIS.map((papel) => (
                <option key={papel.valor} value={papel.valor}>
                  {papel.rotulo}
                </option>
              ))}
            </Selecao>
          </Campo>

          <Campo
            rotulo="Senha"
            dica={
              pessoa
                ? "Em branco mantém a atual. Quem também acessa outra empresa só pode trocar a própria senha."
                : "Em branco, a conta é criada sem senha utilizável e a pessoa entra por 'Esqueci minha senha'."
            }
          >
            <div className="relative">
              <KeyRound className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-texto-tenue" />
              <Input
                type="password"
                autoComplete="new-password"
                className="pl-9"
                value={form.senha}
                onChange={(e) => setForm({ ...form, senha: e.target.value })}
              />
            </div>
          </Campo>
        </div>
      </DialogoConteudo>
    </Dialogo>
  );
}
