"use client";

import { Save } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Botao } from "@/components/ui/button";
import { AreaTexto, Campo, Input, Selecao } from "@/components/ui/campos";
import { Secao } from "@/components/ui/pagina";
import { api, ApiError } from "@/lib/api";
import type { Cliente } from "@/lib/tipos";

const UFS = [
  "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
  "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
  "SE", "SP", "TO",
];

const VAZIO = {
  nome: "",
  nome_fantasia: "",
  cpf_cnpj: "",
  email: "",
  email_secundario: "",
  telefone: "",
  telefone_secundario: "",
  cep: "",
  logradouro: "",
  numero: "",
  complemento: "",
  bairro: "",
  cidade: "",
  uf: "",
  observacoes: "",
  status: "ATIVO",
  codigo_externo: "",
};

type Campos = typeof VAZIO;

/**
 * Cadastro do sacado.
 *
 * O formulário é mais insistente com endereço do que um cadastro comum
 * porque aqui ele não é dado de contato: vai transmitido ao banco no
 * registro do título. Sem logradouro, cidade, UF e CEP o banco recusa — e a
 * recusa chega no retorno do dia seguinte, quando o boleto já deveria ter
 * sido enviado. O aviso ao pé da seção existe para esse erro custar um
 * segundo aqui em vez de um ciclo de cobrança lá.
 */
export function FormularioCliente({ cliente }: { cliente?: Cliente }) {
  const router = useRouter();
  const [form, setForm] = React.useState<Campos>(() => ({
    ...VAZIO,
    ...(cliente
      ? (Object.fromEntries(
          Object.keys(VAZIO).map((k) => [k, (cliente as never as Campos)[k as keyof Campos] ?? ""]),
        ) as Campos)
      : {}),
  }));
  const [erros, setErros] = React.useState<Record<string, string>>({});
  const [salvando, setSalvando] = React.useState(false);

  function definir(campo: keyof Campos, valor: string) {
    setForm((atual) => ({ ...atual, [campo]: valor }));
    setErros((atual) => {
      const proximo = { ...atual };
      delete proximo[campo];
      return proximo;
    });
  }

  /** Preenche o endereço pelo CEP. Falha em silêncio — é conveniência. */
  async function buscarCep(cep: string) {
    const digitos = cep.replace(/\D/g, "");
    if (digitos.length !== 8) return;
    try {
      const resposta = await fetch(`https://viacep.com.br/ws/${digitos}/json/`);
      const dados = await resposta.json();
      if (dados.erro) return;
      setForm((atual) => ({
        ...atual,
        logradouro: atual.logradouro || dados.logradouro || "",
        bairro: atual.bairro || dados.bairro || "",
        cidade: atual.cidade || dados.localidade || "",
        uf: atual.uf || dados.uf || "",
      }));
    } catch {
      /* sem internet ou serviço fora: o operador digita, como sempre fez */
    }
  }

  async function salvar(evento: React.FormEvent) {
    evento.preventDefault();
    setSalvando(true);
    setErros({});
    try {
      const salvo = cliente
        ? await api.patch<Cliente>(`/clients/${cliente.id}/`, form)
        : await api.post<Cliente>("/clients/", form);
      toast.success(cliente ? "Cliente atualizado." : `Cliente ${salvo.codigo} criado.`);
      router.push(`/clientes/${salvo.id}`);
    } catch (erro) {
      if (erro instanceof ApiError && erro.corpo && typeof erro.corpo === "object") {
        // O backend devolve erro por campo; mostrar cada um ao lado do seu
        // campo evita a caça ao "o que está errado" numa mensagem só.
        const corpo = erro.corpo as Record<string, string[] | string>;
        setErros(
          Object.fromEntries(
            Object.entries(corpo)
              .filter(([chave]) => chave in VAZIO)
              .map(([chave, valor]) => [chave, [valor].flat().join(" ")]),
          ),
        );
      }
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha ao salvar.");
    } finally {
      setSalvando(false);
    }
  }

  const enderecoIncompleto =
    !form.logradouro || !form.cidade || !form.uf || form.cep.replace(/\D/g, "").length !== 8;

  return (
    <form onSubmit={salvar} className="space-y-5">
      <Secao titulo="Identificação">
        <div className="grid gap-4 p-5 sm:grid-cols-2">
          <Campo rotulo="Nome ou razão social" obrigatorio erro={erros.nome}>
            <Input
              value={form.nome}
              onChange={(e) => definir("nome", e.target.value)}
              autoFocus
            />
          </Campo>
          <Campo rotulo="Nome fantasia" erro={erros.nome_fantasia}>
            <Input
              value={form.nome_fantasia}
              onChange={(e) => definir("nome_fantasia", e.target.value)}
            />
          </Campo>
          <Campo
            rotulo="CPF ou CNPJ"
            obrigatorio
            erro={erros.cpf_cnpj}
            dica="Conferido na hora: documento inválido é recusado pelo banco."
          >
            <Input
              value={form.cpf_cnpj}
              onChange={(e) => definir("cpf_cnpj", e.target.value)}
              placeholder="000.000.000-00"
            />
          </Campo>
          <Campo rotulo="Situação" erro={erros.status}>
            <Selecao value={form.status} onChange={(e) => definir("status", e.target.value)}>
              <option value="ATIVO">Ativo</option>
              <option value="INADIMPLENTE">Inadimplente</option>
              <option value="INATIVO">Inativo</option>
              <option value="BLOQUEADO">Bloqueado</option>
            </Selecao>
          </Campo>
        </div>
      </Secao>

      <Secao titulo="Contato">
        <div className="grid gap-4 p-5 sm:grid-cols-2">
          <Campo
            rotulo="E-mail"
            erro={erros.email}
            dica="É por onde o boleto é enviado."
          >
            <Input
              type="email"
              value={form.email}
              onChange={(e) => definir("email", e.target.value)}
            />
          </Campo>
          <Campo rotulo="E-mail secundário" erro={erros.email_secundario}>
            <Input
              type="email"
              value={form.email_secundario}
              onChange={(e) => definir("email_secundario", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Telefone" erro={erros.telefone}>
            <Input
              value={form.telefone}
              onChange={(e) => definir("telefone", e.target.value)}
              placeholder="(14) 99999-9999"
            />
          </Campo>
          <Campo rotulo="Telefone secundário" erro={erros.telefone_secundario}>
            <Input
              value={form.telefone_secundario}
              onChange={(e) => definir("telefone_secundario", e.target.value)}
            />
          </Campo>
        </div>
      </Secao>

      <Secao titulo="Endereço">
        <div className="grid gap-4 p-5 sm:grid-cols-6">
          <Campo rotulo="CEP" className="sm:col-span-2" erro={erros.cep}>
            <Input
              value={form.cep}
              onChange={(e) => definir("cep", e.target.value)}
              onBlur={(e) => buscarCep(e.target.value)}
              placeholder="00000-000"
            />
          </Campo>
          <Campo rotulo="Logradouro" className="sm:col-span-4" erro={erros.logradouro}>
            <Input
              value={form.logradouro}
              onChange={(e) => definir("logradouro", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Número" className="sm:col-span-1" erro={erros.numero}>
            <Input value={form.numero} onChange={(e) => definir("numero", e.target.value)} />
          </Campo>
          <Campo rotulo="Complemento" className="sm:col-span-2" erro={erros.complemento}>
            <Input
              value={form.complemento}
              onChange={(e) => definir("complemento", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Bairro" className="sm:col-span-3" erro={erros.bairro}>
            <Input value={form.bairro} onChange={(e) => definir("bairro", e.target.value)} />
          </Campo>
          <Campo rotulo="Cidade" className="sm:col-span-4" erro={erros.cidade}>
            <Input value={form.cidade} onChange={(e) => definir("cidade", e.target.value)} />
          </Campo>
          <Campo rotulo="UF" className="sm:col-span-2" erro={erros.uf}>
            <Selecao value={form.uf} onChange={(e) => definir("uf", e.target.value)}>
              <option value="">—</option>
              {UFS.map((uf) => (
                <option key={uf} value={uf}>
                  {uf}
                </option>
              ))}
            </Selecao>
          </Campo>
        </div>

        {enderecoIncompleto && (
          <p className="border-t border-borda bg-atencao-suave px-5 py-3 text-[12.5px]">
            Sem <strong>CEP, logradouro, cidade e UF</strong> o banco recusa o
            registro do título — e a recusa só aparece no retorno do dia
            seguinte. O cadastro salva assim mesmo; a cobrança é que não sai.
          </p>
        )}
      </Secao>

      <Secao titulo="Outros">
        <div className="grid gap-4 p-5">
          <Campo
            rotulo="Código no seu sistema"
            erro={erros.codigo_externo}
            dica="Se informado, importar a mesma planilha duas vezes não duplica este cliente."
          >
            <Input
              value={form.codigo_externo}
              onChange={(e) => definir("codigo_externo", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Observações" erro={erros.observacoes}>
            <AreaTexto
              value={form.observacoes}
              onChange={(e) => definir("observacoes", e.target.value)}
            />
          </Campo>
        </div>
      </Secao>

      <div className="flex justify-end gap-2">
        <Botao variante="contorno" asChild>
          <Link href={cliente ? `/clientes/${cliente.id}` : "/clientes"}>Cancelar</Link>
        </Botao>
        <Botao type="submit" carregando={salvando}>
          <Save /> {cliente ? "Salvar alterações" : "Criar cliente"}
        </Botao>
      </div>
    </form>
  );
}
