"use client";

import { ArrowLeft, Repeat, Save, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Botao } from "@/components/ui/button";
import { AreaTexto, Campo, Input, Selecao } from "@/components/ui/campos";
import { Secao, TituloPagina } from "@/components/ui/pagina";
import { acompanharTarefa, api, ApiError } from "@/lib/api";
import { useDebounce, useLista, useRecurso } from "@/lib/hooks";
import type { Cliente, ContaBancaria, Pagina, RespostaTarefa } from "@/lib/tipos";
import { moeda, numero } from "@/lib/utils";

type Modo = "individual" | "recorrente";

const HOJE = new Date().toISOString().slice(0, 10);

export default function PaginaNovaCobranca() {
  const router = useRouter();
  const [modo, setModo] = React.useState<Modo>("individual");

  return (
    <>
      <Link
        href="/cobrancas"
        className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-texto-suave hover:text-texto"
      >
        <ArrowLeft className="size-3.5" /> Cobranças
      </Link>

      <TituloPagina
        titulo="Nova cobrança"
        descricao="Uma cobrança avulsa, ou a mensalidade de uma carteira inteira."
      />

      {/* Dois modos, e o segundo é o que o produto existe para resolver: 500
          mensalidades no dia 10 não se digitam uma a uma. */}
      <div className="mb-5 inline-flex rounded-lg border border-borda bg-superficie p-1">
        <BotaoModo
          ativo={modo === "individual"}
          aoClicar={() => setModo("individual")}
          icone={Save}
          rotulo="Uma cobrança"
        />
        <BotaoModo
          ativo={modo === "recorrente"}
          aoClicar={() => setModo("recorrente")}
          icone={Repeat}
          rotulo="Mensalidade em lote"
        />
      </div>

      {modo === "individual" ? (
        <FormularioIndividual aoSalvar={(id) => router.push(`/cobrancas/${id}`)} />
      ) : (
        <FormularioRecorrente aoConcluir={() => router.push("/cobrancas")} />
      )}
    </>
  );
}

function BotaoModo({
  ativo,
  aoClicar,
  icone: Icone,
  rotulo,
}: {
  ativo: boolean;
  aoClicar: () => void;
  icone: React.ComponentType<{ className?: string }>;
  rotulo: string;
}) {
  return (
    <button
      type="button"
      onClick={aoClicar}
      className={`inline-flex items-center gap-2 rounded-md px-3.5 py-2 text-[13px] font-medium transition-colors ${
        ativo ? "bg-acento text-acento-texto" : "text-texto-suave hover:text-texto"
      }`}
    >
      <Icone className="size-3.5" /> {rotulo}
    </button>
  );
}

function useContas() {
  const { dados } = useRecurso<Pagina<ContaBancaria>>("/bank/accounts/?ativa=true");
  return dados?.resultados ?? [];
}

function SelecaoConta({
  valor,
  aoMudar,
}: {
  valor: string;
  aoMudar: (v: string) => void;
}) {
  const contas = useContas();
  React.useEffect(() => {
    if (!valor && contas.length) {
      aoMudar(String(contas.find((c) => c.padrao)?.id ?? contas[0].id));
    }
  }, [contas, valor, aoMudar]);

  return (
    <Selecao value={valor} onChange={(e) => aoMudar(e.target.value)}>
      <option value="">Definir depois</option>
      {contas.map((conta) => (
        <option key={conta.id} value={conta.id}>
          {conta.nome} — {conta.banco_label}
        </option>
      ))}
    </Selecao>
  );
}

function BuscaCliente({
  selecionado,
  aoSelecionar,
}: {
  selecionado: Cliente | null;
  aoSelecionar: (c: Cliente | null) => void;
}) {
  const [busca, setBusca] = React.useState("");
  const termo = useDebounce(busca);
  const lista = useLista<Cliente>("/clients/", {
    search: termo || undefined,
    page_size: 8,
  });

  if (selecionado) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-lg border border-borda bg-superficie-sutil px-3.5 py-2.5">
        <div>
          <p className="text-[13.5px] font-medium">{selecionado.nome}</p>
          <p className="text-[12.5px] text-texto-tenue">
            {selecionado.documento_formatado}
            {!selecionado.pronto_para_boleto && (
              <span className="ml-2 text-atencao">· endereço incompleto</span>
            )}
          </p>
        </div>
        <Botao variante="fantasma" tamanho="sm" onClick={() => aoSelecionar(null)}>
          trocar
        </Botao>
      </div>
    );
  }

  return (
    <div>
      <Input
        placeholder="Buscar por nome ou CPF/CNPJ…"
        value={busca}
        onChange={(e) => setBusca(e.target.value)}
      />
      {termo && lista.dados.length > 0 && (
        <ul className="mt-1.5 max-h-56 overflow-y-auto rounded-lg border border-borda bg-superficie">
          {lista.dados.map((cliente) => (
            <li key={cliente.id}>
              <button
                type="button"
                onClick={() => aoSelecionar(cliente)}
                className="w-full px-3.5 py-2.5 text-left transition-colors hover:bg-superficie-sutil"
              >
                <p className="text-[13.5px]">{cliente.nome}</p>
                <p className="text-[12.5px] text-texto-tenue">
                  {cliente.documento_formatado}
                </p>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FormularioIndividual({ aoSalvar }: { aoSalvar: (id: number) => void }) {
  const [cliente, setCliente] = React.useState<Cliente | null>(null);
  const [conta, setConta] = React.useState("");
  const [form, setForm] = React.useState({
    descricao: "",
    documento: "",
    valor: "",
    data_emissao: HOJE,
    data_vencimento: "",
    juros_mes_percentual: "",
    multa_percentual: "",
    desconto: "",
    observacoes: "",
  });
  const [salvando, setSalvando] = React.useState(false);

  function definir(campo: string, valor: string) {
    setForm((atual) => ({ ...atual, [campo]: valor }));
  }

  async function salvar() {
    if (!cliente) return toast.error("Escolha o cliente.");
    setSalvando(true);
    try {
      const criada = await api.post<{ id: number; numero: number }>("/charges/", {
        cliente: cliente.id,
        conta_bancaria: conta ? Number(conta) : null,
        ...form,
        juros_mes_percentual: form.juros_mes_percentual || "0",
        multa_percentual: form.multa_percentual || "0",
        desconto: form.desconto || "0",
      });
      toast.success(`Cobrança #${criada.numero} criada.`);
      aoSalvar(criada.id);
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha ao salvar.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Secao titulo="Dados da cobrança">
      <div className="space-y-5 p-5">
        <Campo rotulo="Cliente" obrigatorio>
          <BuscaCliente selecionado={cliente} aoSelecionar={setCliente} />
        </Campo>

        <div className="grid gap-4 sm:grid-cols-2">
          <Campo rotulo="Descrição" obrigatorio>
            <Input
              value={form.descricao}
              onChange={(e) => definir("descricao", e.target.value)}
              placeholder="Mensalidade de setembro"
            />
          </Campo>
          <Campo rotulo="Documento" dica="Aparece no boleto como número do documento.">
            <Input
              value={form.documento}
              onChange={(e) => definir("documento", e.target.value)}
              placeholder="NF-1001"
            />
          </Campo>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <Campo rotulo="Valor" obrigatorio>
            <Input
              type="number"
              step="0.01"
              min="0.01"
              value={form.valor}
              onChange={(e) => definir("valor", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Emissão" obrigatorio>
            <Input
              type="date"
              value={form.data_emissao}
              onChange={(e) => definir("data_emissao", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Vencimento" obrigatorio>
            <Input
              type="date"
              value={form.data_vencimento}
              onChange={(e) => definir("data_vencimento", e.target.value)}
            />
          </Campo>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <Campo rotulo="Conta bancária">
            <SelecaoConta valor={conta} aoMudar={setConta} />
          </Campo>
          <Campo rotulo="Juros ao mês (%)">
            <Input
              type="number"
              step="0.01"
              value={form.juros_mes_percentual}
              onChange={(e) => definir("juros_mes_percentual", e.target.value)}
              placeholder="0"
            />
          </Campo>
          <Campo rotulo="Multa (%)">
            <Input
              type="number"
              step="0.01"
              value={form.multa_percentual}
              onChange={(e) => definir("multa_percentual", e.target.value)}
              placeholder="0"
            />
          </Campo>
        </div>

        <Campo rotulo="Observações">
          <AreaTexto
            value={form.observacoes}
            onChange={(e) => definir("observacoes", e.target.value)}
          />
        </Campo>

        <div className="flex justify-end gap-2 border-t border-borda pt-4">
          <Botao variante="contorno" asChild>
            <Link href="/cobrancas">Cancelar</Link>
          </Botao>
          <Botao onClick={salvar} carregando={salvando}>
            <Save /> Criar cobrança
          </Botao>
        </div>
      </div>
    </Secao>
  );
}

function FormularioRecorrente({ aoConcluir }: { aoConcluir: () => void }) {
  const [selecionados, setSelecionados] = React.useState<Cliente[]>([]);
  const [conta, setConta] = React.useState("");
  const [busca, setBusca] = React.useState("");
  const termo = useDebounce(busca);
  const lista = useLista<Cliente>("/clients/", {
    search: termo || undefined,
    status: "ATIVO",
  });

  const [form, setForm] = React.useState({
    descricao: "",
    valor: "",
    primeiro_vencimento: "",
    parcelas: "1",
    prefixo_chave: "",
  });
  const [gerando, setGerando] = React.useState(false);
  const [progresso, setProgresso] = React.useState(0);

  function definir(campo: string, valor: string) {
    setForm((atual) => ({ ...atual, [campo]: valor }));
  }

  function alternar(cliente: Cliente) {
    setSelecionados((atual) =>
      atual.some((c) => c.id === cliente.id)
        ? atual.filter((c) => c.id !== cliente.id)
        : [...atual, cliente],
    );
  }

  async function gerar() {
    if (selecionados.length === 0) return toast.error("Escolha ao menos um cliente.");
    setGerando(true);
    setProgresso(0);
    try {
      const resposta = await api.post<RespostaTarefa>("/charges/recurring/", {
        clientes: selecionados.map((c) => c.id),
        descricao: form.descricao,
        valor: form.valor,
        primeiro_vencimento: form.primeiro_vencimento,
        parcelas: Number(form.parcelas),
        conta_bancaria_id: conta ? Number(conta) : null,
        prefixo_chave: form.prefixo_chave || undefined,
      });

      const fim = await acompanharTarefa(resposta.tarefa_id, (pct) => setProgresso(pct));
      if (fim.estado === "SUCCESS") {
        const dados = fim.resultado as { criadas: number; duplicadas: number };
        toast.success(`${numero(dados.criadas)} cobranças criadas.`, {
          description: dados.duplicadas
            ? `${dados.duplicadas} já existiam e foram ignoradas.`
            : undefined,
        });
        aoConcluir();
      } else {
        toast.error(fim.erro ?? "A geração não terminou.");
      }
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha ao gerar.");
    } finally {
      setGerando(false);
    }
  }

  const total =
    Number(form.valor || 0) * selecionados.length * Number(form.parcelas || 1);

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_1.1fr]">
      <Secao
        titulo={`Clientes (${numero(selecionados.length)} selecionados)`}
        acoes={
          selecionados.length > 0 ? (
            <Botao
              variante="fantasma"
              tamanho="sm"
              onClick={() => setSelecionados([])}
            >
              limpar
            </Botao>
          ) : (
            <Botao
              variante="fantasma"
              tamanho="sm"
              onClick={() => setSelecionados(lista.dados)}
            >
              <Users /> marcar a página
            </Botao>
          )
        }
      >
        <div className="p-4">
          <Input
            placeholder="Buscar cliente…"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>
        <ul className="max-h-96 divide-y divide-borda overflow-y-auto border-t border-borda">
          {lista.dados.map((cliente) => {
            const marcado = selecionados.some((c) => c.id === cliente.id);
            return (
              <li key={cliente.id}>
                <label className="flex cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors hover:bg-superficie-sutil">
                  <input
                    type="checkbox"
                    checked={marcado}
                    onChange={() => alternar(cliente)}
                    className="size-4 accent-[var(--acento)]"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13.5px]">{cliente.nome}</span>
                    <span className="block text-[12px] text-texto-tenue">
                      {cliente.documento_formatado}
                      {!cliente.pronto_para_boleto && (
                        <span className="ml-1.5 text-atencao">
                          · endereço incompleto
                        </span>
                      )}
                    </span>
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      </Secao>

      <Secao titulo="Cobrança a gerar">
        <div className="space-y-5 p-5">
          <Campo rotulo="Descrição" obrigatorio>
            <Input
              value={form.descricao}
              onChange={(e) => definir("descricao", e.target.value)}
              placeholder="Mensalidade"
            />
          </Campo>

          <div className="grid gap-4 sm:grid-cols-3">
            <Campo rotulo="Valor por cliente" obrigatorio>
              <Input
                type="number"
                step="0.01"
                value={form.valor}
                onChange={(e) => definir("valor", e.target.value)}
              />
            </Campo>
            <Campo rotulo="1º vencimento" obrigatorio>
              <Input
                type="date"
                value={form.primeiro_vencimento}
                onChange={(e) => definir("primeiro_vencimento", e.target.value)}
              />
            </Campo>
            <Campo rotulo="Parcelas" dica="Uma por mês.">
              <Input
                type="number"
                min="1"
                max="120"
                value={form.parcelas}
                onChange={(e) => definir("parcelas", e.target.value)}
              />
            </Campo>
          </div>

          <Campo rotulo="Conta bancária">
            <SelecaoConta valor={conta} aoMudar={setConta} />
          </Campo>

          <Campo
            rotulo="Identificador da geração"
            dica="Preenchido, rodar esta geração duas vezes não cria cobrança repetida. Ex.: mensalidade-2026."
          >
            <Input
              value={form.prefixo_chave}
              onChange={(e) => definir("prefixo_chave", e.target.value)}
            />
          </Campo>

          <div className="rounded-lg border border-borda bg-superficie-sutil px-4 py-3">
            <p className="text-[13px] text-texto-suave">
              {numero(selecionados.length)} clientes ×{" "}
              {numero(Number(form.parcelas || 1))}{" "}
              {Number(form.parcelas || 1) === 1 ? "parcela" : "parcelas"} ={" "}
              <strong>
                {numero(selecionados.length * Number(form.parcelas || 1))} cobranças
              </strong>
            </p>
            <p className="mt-0.5 text-[13px] text-texto-tenue">
              Total de {moeda(total)}
            </p>
          </div>

          {gerando && (
            <div>
              <div className="mb-1.5 flex justify-between text-[12.5px] text-texto-suave">
                <span>Criando as cobranças…</span>
                <span className="tabular">{progresso}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-neutro-suave">
                <div
                  className="h-full rounded-full bg-acento transition-[width] duration-300"
                  style={{ width: `${Math.max(progresso, 4)}%` }}
                />
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2 border-t border-borda pt-4">
            <Botao variante="contorno" asChild>
              <Link href="/cobrancas">Cancelar</Link>
            </Botao>
            <Botao
              onClick={gerar}
              carregando={gerando}
              disabled={selecionados.length === 0}
            >
              <Repeat /> Gerar cobranças
            </Botao>
          </div>
        </div>
      </Secao>
    </div>
  );
}
