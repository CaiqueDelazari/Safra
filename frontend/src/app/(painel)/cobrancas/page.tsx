"use client";

import { Download, Plus, Search, Send, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { DialogoGerarLote } from "@/components/cobrancas/gerar-lote";
import { StatusCobrancaBadge } from "@/components/cobrancas/status";
import { Botao } from "@/components/ui/button";
import { Input, Selecao } from "@/components/ui/campos";
import { Filtros, Secao, TituloPagina } from "@/components/ui/pagina";
import { Paginacao } from "@/components/ui/paginacao";
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
import { useDebounce, useLista, useRecurso } from "@/lib/hooks";
import type { CobrancaLista, ContaBancaria, Pagina, StatusCobranca } from "@/lib/tipos";
import { data, moeda, numero } from "@/lib/utils";
import { useSessao } from "@/providers/sessao";

const STATUS: { valor: string; rotulo: string }[] = [
  { valor: "", rotulo: "Todas as situações" },
  { valor: "PENDENTE", rotulo: "Pendentes" },
  { valor: "ENVIADA_AO_BANCO", rotulo: "Enviadas ao banco" },
  { valor: "REGISTRADA", rotulo: "Registradas" },
  { valor: "PAGA", rotulo: "Pagas" },
  { valor: "VENCIDA", rotulo: "Vencidas" },
  { valor: "REJEITADA", rotulo: "Rejeitadas" },
  { valor: "CANCELADA", rotulo: "Canceladas" },
  { valor: "BAIXADA", rotulo: "Baixadas" },
];

/** Teto de uma seleção "todas as filtradas". Acima disso, o lote é dividido. */
const MAX_SELECAO = 20_000;
const PAGINA_BUSCA_IDS = 200;

export default function PaginaCobrancas() {
  const { podeCapacidade } = useSessao();
  const [busca, setBusca] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [semLote, setSemLote] = React.useState(false);
  const [de, setDe] = React.useState("");
  const [ate, setAte] = React.useState("");
  const termo = useDebounce(busca);

  const filtros = React.useMemo(
    () => ({
      search: termo || undefined,
      status: status || undefined,
      sem_lote: semLote ? "true" : undefined,
      vencimento_de: de || undefined,
      vencimento_ate: ate || undefined,
    }),
    [termo, status, semLote, de, ate],
  );

  const lista = useLista<CobrancaLista>("/charges/", filtros);
  const { dados: contas } = useRecurso<Pagina<ContaBancaria>>("/bank/accounts/");

  const [selecionadas, setSelecionadas] = React.useState<Set<number>>(new Set());
  const [selecionandoTudo, setSelecionandoTudo] = React.useState(false);
  const [loteAberto, setLoteAberto] = React.useState(false);

  // A seleção pertence ao conjunto de filtros: mudou o filtro, a seleção
  // anterior deixou de fazer sentido. Mantê-la faria o operador gerar um lote
  // com títulos que ele nem está vendo na tela.
  const chaveFiltros = JSON.stringify(filtros);
  const chaveAnterior = React.useRef(chaveFiltros);
  React.useEffect(() => {
    if (chaveAnterior.current !== chaveFiltros) {
      chaveAnterior.current = chaveFiltros;
      setSelecionadas(new Set());
    }
  }, [chaveFiltros]);

  const idsDaPagina = lista.dados.map((c) => c.id);
  const todasDaPaginaMarcadas =
    idsDaPagina.length > 0 && idsDaPagina.every((id) => selecionadas.has(id));

  function alternar(id: number) {
    setSelecionadas((atual) => {
      const proximo = new Set(atual);
      if (proximo.has(id)) proximo.delete(id);
      else proximo.add(id);
      return proximo;
    });
  }

  function alternarPagina() {
    setSelecionadas((atual) => {
      const proximo = new Set(atual);
      if (todasDaPaginaMarcadas) idsDaPagina.forEach((id) => proximo.delete(id));
      else idsDaPagina.forEach((id) => proximo.add(id));
      return proximo;
    });
  }

  /**
   * Seleciona tudo que o filtro alcança, e não só a página.
   *
   * É o "selecionei 500 cobranças" do enunciado: ninguém marca 500 caixas em
   * 20 páginas. Os ids vêm em blocos de 200 porque a API pagina — e paginar é
   * o certo: a alternativa seria uma rota que devolve 50 mil ids num JSON.
   */
  async function selecionarTodasFiltradas() {
    setSelecionandoTudo(true);
    try {
      const ids: number[] = [];
      let pagina = 1;
      for (;;) {
        const resposta = await api.get<Pagina<CobrancaLista>>("/charges/", {
          ...filtros,
          page: pagina,
          page_size: PAGINA_BUSCA_IDS,
        });
        ids.push(...resposta.resultados.map((c) => c.id));
        if (pagina >= resposta.paginas || ids.length >= MAX_SELECAO) break;
        pagina += 1;
      }
      if (ids.length > MAX_SELECAO) {
        toast.warning(
          `A seleção foi limitada a ${numero(MAX_SELECAO)} títulos. Gere em lotes menores.`,
        );
      }
      setSelecionadas(new Set(ids.slice(0, MAX_SELECAO)));
    } catch (erro) {
      toast.error(
        erro instanceof ApiError ? erro.detalhe : "Falha ao selecionar as cobranças.",
      );
    } finally {
      setSelecionandoTudo(false);
    }
  }

  return (
    <>
      <TituloPagina
        titulo="Cobranças"
        descricao="Selecione os títulos e gere o lote de remessa numa operação só."
        acoes={
          <>
            <Botao variante="contorno" asChild>
              <Link href="/relatorios">
                <Download /> Exportar
              </Link>
            </Botao>
            <Botao asChild>
              <Link href="/cobrancas/nova">
                <Plus /> Nova cobrança
              </Link>
            </Botao>
          </>
        }
      />

      <Filtros>
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-texto-tenue" />
          <Input
            className="pl-9"
            placeholder="Cliente, documento, nosso número…"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>
        <Selecao
          className="w-52"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {STATUS.map((opcao) => (
            <option key={opcao.valor} value={opcao.valor}>
              {opcao.rotulo}
            </option>
          ))}
        </Selecao>
        <Input
          type="date"
          className="w-40"
          value={de}
          onChange={(e) => setDe(e.target.value)}
          aria-label="Vencimento de"
        />
        <Input
          type="date"
          className="w-40"
          value={ate}
          onChange={(e) => setAte(e.target.value)}
          aria-label="Vencimento até"
        />
        <Botao
          variante={semLote ? "primario" : "contorno"}
          tamanho="sm"
          onClick={() => setSemLote((v) => !v)}
        >
          Fora de lote
        </Botao>
      </Filtros>

      {selecionadas.size > 0 && (
        <BarraSelecao
          quantidade={selecionadas.size}
          total={lista.total}
          selecionandoTudo={selecionandoTudo}
          podeGerar={podeCapacidade("gerar_lote")}
          aoSelecionarTudo={selecionarTodasFiltradas}
          aoLimpar={() => setSelecionadas(new Set())}
          aoGerar={() => setLoteAberto(true)}
        />
      )}

      <Secao titulo={`${numero(lista.total)} cobranças`}>
        <Tabela>
          <Cabecalho>
            <tr>
              <Th className="w-10 pr-0">
                <input
                  type="checkbox"
                  className="size-4 cursor-pointer accent-[var(--acento)]"
                  checked={todasDaPaginaMarcadas}
                  onChange={alternarPagina}
                  aria-label="Selecionar a página"
                />
              </Th>
              <Th>Cobrança</Th>
              <Th>Cliente</Th>
              <Th>Vencimento</Th>
              <Th>Situação</Th>
              <Th className="text-right">Valor</Th>
            </tr>
          </Cabecalho>
          <Corpo>
            {lista.carregando ? (
              <Esqueleto colunas={6} />
            ) : lista.dados.length === 0 ? (
              <Vazio
                colunas={6}
                titulo="Nenhuma cobrança"
                descricao="Ajuste os filtros ou crie a primeira cobrança."
                acao={
                  <Botao asChild>
                    <Link href="/cobrancas/nova">
                      <Plus /> Nova cobrança
                    </Link>
                  </Botao>
                }
              />
            ) : (
              lista.dados.map((cobranca) => (
                <Linha key={cobranca.id}>
                  <Td className="pr-0">
                    <input
                      type="checkbox"
                      className="size-4 cursor-pointer accent-[var(--acento)]"
                      checked={selecionadas.has(cobranca.id)}
                      onChange={() => alternar(cobranca.id)}
                      aria-label={`Selecionar cobrança ${cobranca.numero}`}
                    />
                  </Td>
                  <Td>
                    <Link
                      href={`/cobrancas/${cobranca.id}`}
                      className="font-medium hover:text-acento"
                    >
                      #{cobranca.numero} · {cobranca.descricao}
                    </Link>
                    <p className="text-[12.5px] text-texto-tenue">
                      {cobranca.nosso_numero
                        ? `Nosso número ${cobranca.nosso_numero}`
                        : "Sem número do banco"}
                      {cobranca.lote ? ` · lote #${cobranca.lote}` : ""}
                    </p>
                  </Td>
                  <Td>
                    <p className="text-[13.5px]">{cobranca.cliente_nome}</p>
                    <p className="text-[12.5px] text-texto-tenue">
                      {cobranca.cliente_documento}
                    </p>
                  </Td>
                  <Td className="text-[13px] text-texto-suave">
                    {data(cobranca.data_vencimento)}
                    {cobranca.dias_em_atraso > 0 && (
                      <span className="ml-1.5 text-[12px] text-negativo">
                        {cobranca.dias_em_atraso}d
                      </span>
                    )}
                  </Td>
                  <Td>
                    <StatusCobrancaBadge
                      status={cobranca.status as StatusCobranca}
                      vencida={cobranca.vencida}
                    />
                    {cobranca.mensagem_erro && (
                      <p
                        className="mt-1 max-w-56 truncate text-[12px] text-negativo"
                        title={cobranca.mensagem_erro}
                      >
                        {cobranca.mensagem_erro}
                      </p>
                    )}
                  </Td>
                  <Td className="text-right">
                    <span className="font-medium tabular">{moeda(cobranca.valor)}</span>
                    {cobranca.status === "PAGA" && (
                      <p className="text-[12px] text-positivo tabular">
                        pago {moeda(cobranca.valor_pago)}
                      </p>
                    )}
                  </Td>
                </Linha>
              ))
            )}
          </Corpo>
        </Tabela>
        <Paginacao
          pagina={lista.pagina}
          paginas={lista.paginas}
          total={lista.total}
          aoMudar={lista.setPagina}
          rotulo="cobranças"
        />
      </Secao>

      <DialogoGerarLote
        cobrancas={[...selecionadas]}
        contas={contas?.resultados ?? []}
        aberto={loteAberto}
        aoFechar={() => setLoteAberto(false)}
        aoConcluir={() => {
          setSelecionadas(new Set());
          lista.recarregar();
        }}
      />
    </>
  );
}

function BarraSelecao({
  quantidade,
  total,
  selecionandoTudo,
  podeGerar,
  aoSelecionarTudo,
  aoLimpar,
  aoGerar,
}: {
  quantidade: number;
  total: number;
  selecionandoTudo: boolean;
  podeGerar: boolean;
  aoSelecionarTudo: () => void;
  aoLimpar: () => void;
  aoGerar: () => void;
}) {
  return (
    <div className="sticky top-16 z-20 mb-4 flex flex-wrap items-center gap-3 rounded-card border border-acento/30 bg-acento-suave px-4 py-3">
      <p className="text-[13.5px] font-medium">
        {numero(quantidade)} {quantidade === 1 ? "selecionada" : "selecionadas"}
      </p>

      {quantidade < total && (
        <Botao
          variante="link"
          tamanho="sm"
          onClick={aoSelecionarTudo}
          carregando={selecionandoTudo}
        >
          selecionar as {numero(total)} do filtro
        </Botao>
      )}

      <div className="ml-auto flex items-center gap-2">
        <Botao variante="fantasma" tamanho="sm" onClick={aoLimpar}>
          <X /> Limpar
        </Botao>
        {podeGerar && (
          <Botao tamanho="sm" onClick={aoGerar}>
            <Send /> Gerar lote
          </Botao>
        )}
      </div>
    </div>
  );
}
