"use client";

import { AlertCircle, Building2, CheckCircle2, Save } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Botao } from "@/components/ui/button";
import { Campo, Input, Selecao } from "@/components/ui/campos";
import { CardIndicador, Secao, TituloPagina } from "@/components/ui/pagina";
import { api, ApiError } from "@/lib/api";
import { useRecurso } from "@/lib/hooks";
import type { EmpresaCompleta } from "@/lib/tipos";
import { numero } from "@/lib/utils";
import { useSessao } from "@/providers/sessao";

const UFS = [
  "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS",
  "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC",
  "SE", "SP", "TO",
];

interface Prontidao {
  apta_a_emitir: boolean;
  pendencias_cadastro: string[];
  contas_bancarias: number;
  contas_com_transmissao: number;
  clientes: number;
  clientes_prontos_para_boleto: number;
}

export default function PaginaEmpresa() {
  const { empresaAtiva, pode, recarregarUsuario } = useSessao();
  const id = empresaAtiva?.id;

  const { dados: empresa, recarregar } = useRecurso<EmpresaCompleta>(
    id ? `/companies/${id}/` : null,
  );
  const { dados: prontidao } = useRecurso<Prontidao>(
    id ? `/companies/${id}/readiness/` : null,
  );

  const [form, setForm] = React.useState<Record<string, string>>({});
  const [salvando, setSalvando] = React.useState(false);

  React.useEffect(() => {
    if (!empresa) return;
    // Espelha no formulário o recurso que chegou de forma assíncrona.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setForm(
      Object.fromEntries(
        [
          "cnpj", "razao_social", "nome_fantasia", "inscricao_estadual",
          "inscricao_municipal", "cep", "logradouro", "numero", "complemento",
          "bairro", "cidade", "uf", "telefone", "email", "email_cobranca",
        ].map((campo) => [campo, String(empresa[campo as keyof EmpresaCompleta] ?? "")]),
      ),
    );
  }, [empresa]);

  const somenteLeitura = !pode("empresas", "update");

  async function salvar(evento: React.FormEvent) {
    evento.preventDefault();
    setSalvando(true);
    try {
      await api.patch(`/companies/${id}/`, form);
      toast.success("Dados da empresa salvos.");
      recarregar();
      // O nome e a cor aparecem na barra lateral: sem isto, a tela salva e
      // o topo continua mostrando o nome antigo até um recarregamento.
      recarregarUsuario();
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha ao salvar.");
    } finally {
      setSalvando(false);
    }
  }

  if (!empresa) {
    return <div className="carregando h-64 rounded-card bg-neutro-suave" />;
  }

  return (
    <>
      <TituloPagina
        titulo="Empresa"
        descricao="Estes dados vão impressos no boleto e transmitidos ao banco como beneficiário."
      />

      {/* A lista do que falta vem antes do formulário porque é a resposta
          para "por que meu lote não sai?" — e essa pergunta chega antes de
          qualquer vontade de editar cadastro. */}
      {prontidao && !prontidao.apta_a_emitir && (
        <div className="mb-5 flex items-start gap-3 rounded-card border border-negativo/30 bg-negativo-suave px-4 py-3.5">
          <AlertCircle className="mt-0.5 size-4.5 shrink-0 text-negativo" />
          <div>
            <p className="text-[13.5px] font-medium">
              A empresa ainda não pode emitir títulos
            </p>
            <p className="mt-0.5 text-[12.5px] text-texto-suave">
              Falta: {prontidao.pendencias_cadastro.join(", ")}. O banco recusa a
              remessa inteira quando o cadastro do beneficiário está incompleto —
              não um título, o arquivo todo.
            </p>
          </div>
        </div>
      )}

      {prontidao && (
        <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <CardIndicador
            rotulo="Cadastro"
            valor={
              prontidao.apta_a_emitir ? (
                <span className="inline-flex items-center gap-2 text-[20px] text-positivo">
                  <CheckCircle2 className="size-5" /> Completo
                </span>
              ) : (
                <span className="text-[20px] text-negativo">Incompleto</span>
              )
            }
            detalhe="Exigido pelo banco no registro do título"
            icone={Building2}
          />
          <CardIndicador
            rotulo="Contas bancárias"
            valor={numero(prontidao.contas_bancarias)}
            detalhe={`${numero(prontidao.contas_com_transmissao)} com envio automático`}
          />
          <CardIndicador
            rotulo="Clientes"
            valor={numero(prontidao.clientes)}
            detalhe={`${numero(prontidao.clientes_prontos_para_boleto)} com endereço completo`}
            tom={
              prontidao.clientes > prontidao.clientes_prontos_para_boleto
                ? "atencao"
                : "neutro"
            }
          />
          {empresa.plano_label && (
            <CardIndicador
              rotulo="Plano"
              valor={empresa.plano_label}
              detalhe={
                empresa.limite_titulos_mes
                  ? `${numero(empresa.titulos_no_mes ?? 0)} de ${numero(
                      empresa.limite_titulos_mes,
                    )} títulos no mês`
                  : "sem limite de títulos"
              }
            />
          )}
        </div>
      )}

      <form onSubmit={salvar} className="space-y-5">
        <Secao titulo="Beneficiário">
          <div className="grid gap-4 p-5 sm:grid-cols-6">
            <Campo rotulo="CNPJ" obrigatorio className="sm:col-span-2">
              <Input
                value={form.cnpj ?? ""}
                onChange={(e) => setForm({ ...form, cnpj: e.target.value })}
                disabled={somenteLeitura}
              />
            </Campo>
            <Campo rotulo="Razão social" obrigatorio className="sm:col-span-4">
              <Input
                value={form.razao_social ?? ""}
                onChange={(e) => setForm({ ...form, razao_social: e.target.value })}
                disabled={somenteLeitura}
              />
            </Campo>
            <Campo rotulo="Nome fantasia" className="sm:col-span-3">
              <Input
                value={form.nome_fantasia ?? ""}
                onChange={(e) => setForm({ ...form, nome_fantasia: e.target.value })}
                disabled={somenteLeitura}
              />
            </Campo>
            <Campo rotulo="Inscrição estadual" className="sm:col-span-3">
              <Input
                value={form.inscricao_estadual ?? ""}
                onChange={(e) =>
                  setForm({ ...form, inscricao_estadual: e.target.value })
                }
                disabled={somenteLeitura}
              />
            </Campo>
          </div>
        </Secao>

        <Secao titulo="Endereço">
          <div className="grid gap-4 p-5 sm:grid-cols-6">
            <Campo rotulo="CEP" obrigatorio className="sm:col-span-2">
              <Input
                value={form.cep ?? ""}
                onChange={(e) => setForm({ ...form, cep: e.target.value })}
                disabled={somenteLeitura}
              />
            </Campo>
            <Campo rotulo="Logradouro" obrigatorio className="sm:col-span-4">
              <Input
                value={form.logradouro ?? ""}
                onChange={(e) => setForm({ ...form, logradouro: e.target.value })}
                disabled={somenteLeitura}
              />
            </Campo>
            <Campo rotulo="Número" className="sm:col-span-1">
              <Input
                value={form.numero ?? ""}
                onChange={(e) => setForm({ ...form, numero: e.target.value })}
                disabled={somenteLeitura}
              />
            </Campo>
            <Campo rotulo="Complemento" className="sm:col-span-2">
              <Input
                value={form.complemento ?? ""}
                onChange={(e) => setForm({ ...form, complemento: e.target.value })}
                disabled={somenteLeitura}
              />
            </Campo>
            <Campo rotulo="Bairro" className="sm:col-span-3">
              <Input
                value={form.bairro ?? ""}
                onChange={(e) => setForm({ ...form, bairro: e.target.value })}
                disabled={somenteLeitura}
              />
            </Campo>
            <Campo rotulo="Cidade" obrigatorio className="sm:col-span-4">
              <Input
                value={form.cidade ?? ""}
                onChange={(e) => setForm({ ...form, cidade: e.target.value })}
                disabled={somenteLeitura}
              />
            </Campo>
            <Campo rotulo="UF" obrigatorio className="sm:col-span-2">
              <Selecao
                value={form.uf ?? ""}
                onChange={(e) => setForm({ ...form, uf: e.target.value })}
                disabled={somenteLeitura}
              >
                <option value="">—</option>
                {UFS.map((uf) => (
                  <option key={uf} value={uf}>
                    {uf}
                  </option>
                ))}
              </Selecao>
            </Campo>
          </div>
        </Secao>

        <Secao titulo="Contato">
          <div className="grid gap-4 p-5 sm:grid-cols-3">
            <Campo rotulo="Telefone">
              <Input
                value={form.telefone ?? ""}
                onChange={(e) => setForm({ ...form, telefone: e.target.value })}
                disabled={somenteLeitura}
              />
            </Campo>
            <Campo rotulo="E-mail">
              <Input
                type="email"
                value={form.email ?? ""}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                disabled={somenteLeitura}
              />
            </Campo>
            <Campo
              rotulo="E-mail de cobrança"
              dica="Remetente e caixa de resposta dos boletos enviados ao sacado."
            >
              <Input
                type="email"
                value={form.email_cobranca ?? ""}
                onChange={(e) => setForm({ ...form, email_cobranca: e.target.value })}
                disabled={somenteLeitura}
              />
            </Campo>
          </div>
        </Secao>

        {!somenteLeitura && (
          <div className="flex justify-end gap-2">
            <Botao variante="contorno" asChild>
              <Link href="/dashboard">Cancelar</Link>
            </Botao>
            <Botao type="submit" carregando={salvando}>
              <Save /> Salvar
            </Botao>
          </div>
        )}
      </form>
    </>
  );
}
