"use client";

import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CircleDollarSign,
  TrendingDown,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { StatusCobrancaBadge } from "@/components/cobrancas/status";
import { Botao } from "@/components/ui/button";
import { CardIndicador, Secao, TituloPagina } from "@/components/ui/pagina";
import { Cabecalho, Corpo, Linha, Tabela, Td, Th, Vazio } from "@/components/ui/tabela";
import { useRecursoVivo } from "@/lib/hooks";
import type { Dashboard, Pendencias } from "@/lib/tipos";
import { data, moeda, numero } from "@/lib/utils";

export default function PaginaDashboard() {
  // Atualização de 60 em 60 segundos: o retorno bancário é processado por um
  // worker, e sem isto o operador ficaria recarregando a página para saber se
  // os pagamentos entraram.
  const { dados, carregando } = useRecursoVivo<Dashboard>("/dashboard/", {}, 60_000);
  const { dados: pendencias } = useRecursoVivo<Pendencias>(
    "/reconciliation/pendencias/",
    {},
    60_000,
  );

  const total = pendencias
    ? Object.values(pendencias).reduce((soma, n) => soma + n, 0)
    : 0;

  const serie = (dados?.recebimentos_por_mes ?? []).map((linha) => ({
    mes: linha.mes.slice(5) + "/" + linha.mes.slice(2, 4),
    valor: Number(linha.valor),
    quantidade: linha.quantidade,
  }));

  return (
    <>
      <TituloPagina
        titulo="Visão geral"
        descricao={
          dados
            ? `Posição de ${data(dados.referencia)}`
            : "Carregando a posição da carteira…"
        }
        acoes={
          <Botao variante="contorno" asChild>
            <Link href="/cobrancas">
              Cobranças <ArrowRight />
            </Link>
          </Botao>
        }
      />

      {total > 0 && <FaixaPendencias pendencias={pendencias!} total={total} />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <CardIndicador
          rotulo="A receber"
          valor={moeda(dados?.totais.a_receber)}
          detalhe={`${numero(dados?.totais.quantidade_aberta ?? 0)} títulos em aberto`}
          icone={CircleDollarSign}
          tom="acento"
          carregando={carregando}
        />
        <CardIndicador
          rotulo="Recebido no mês"
          valor={moeda(dados?.recebido.no_mes)}
          detalhe={`${numero(dados?.recebido.quantidade_no_mes ?? 0)} pagamentos · ${moeda(
            dados?.recebido.tarifas_no_mes,
          )} em tarifas`}
          icone={Wallet}
          tom="positivo"
          carregando={carregando}
        />
        <CardIndicador
          rotulo="Vencido"
          valor={moeda(dados?.totais.vencido)}
          detalhe={`${numero(dados?.totais.quantidade_vencida ?? 0)} títulos · ${
            dados?.inadimplencia_percentual ?? 0
          }% da carteira`}
          icone={TrendingDown}
          tom="negativo"
          carregando={carregando}
        />
        <CardIndicador
          rotulo="Vence em 7 dias"
          valor={moeda(dados?.totais.vencendo_em_7_dias)}
          detalhe="O que entra na próxima semana"
          icone={CalendarClock}
          tom="atencao"
          carregando={carregando}
        />
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <Secao titulo="Recebimentos por mês">
          <div className="h-72 px-3 py-4">
            {serie.length === 0 ? (
              <div className="flex h-full items-center justify-center">
                <p className="text-[13px] text-texto-tenue">
                  Sem recebimentos registrados ainda.
                </p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={serie}>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    vertical={false}
                    stroke="var(--borda)"
                  />
                  <XAxis
                    dataKey="mes"
                    tickLine={false}
                    axisLine={false}
                    tick={{ fontSize: 12, fill: "var(--texto-tenue)" }}
                  />
                  <YAxis
                    tickLine={false}
                    axisLine={false}
                    width={70}
                    tick={{ fontSize: 12, fill: "var(--texto-tenue)" }}
                    tickFormatter={(v: number) =>
                      v >= 1000 ? `${Math.round(v / 1000)}k` : String(v)
                    }
                  />
                  <Tooltip
                    cursor={{ fill: "var(--neutro-suave)" }}
                    contentStyle={{
                      borderRadius: 10,
                      border: "1px solid var(--borda)",
                      background: "var(--fundo-elevado)",
                      fontSize: 13,
                    }}
                    formatter={(valor: number, _nome, item) => [
                      `${moeda(valor)} · ${item.payload.quantidade} pagamentos`,
                      "Recebido",
                    ]}
                  />
                  <Bar dataKey="valor" fill="var(--acento)" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Secao>

        <Secao
          titulo="Próximos vencimentos"
          acoes={
            <Link
              href="/cobrancas?vencidas=false"
              className="text-[13px] text-acento hover:underline"
            >
              ver todas
            </Link>
          }
        >
          <Tabela>
            <Cabecalho>
              <tr>
                <Th>Cliente</Th>
                <Th>Vence</Th>
                <Th className="text-right">Valor</Th>
              </tr>
            </Cabecalho>
            <Corpo>
              {(dados?.proximos_vencimentos ?? []).length === 0 ? (
                <Vazio
                  colunas={3}
                  titulo="Nada vencendo"
                  descricao="Não há títulos com vencimento nos próximos 7 dias."
                />
              ) : (
                dados!.proximos_vencimentos.map((linha) => (
                  <Linha key={linha.id}>
                    <Td>
                      <Link
                        href={`/cobrancas/${linha.id}`}
                        className="font-medium hover:text-acento"
                      >
                        {linha.cliente}
                      </Link>
                      <p className="text-[12.5px] text-texto-tenue">
                        #{linha.numero} · {linha.descricao}
                      </p>
                    </Td>
                    <Td className="text-[13px] text-texto-suave">
                      {data(linha.vencimento)}
                    </Td>
                    <Td className="text-right font-medium tabular">
                      {moeda(linha.valor)}
                    </Td>
                  </Linha>
                ))
              )}
            </Corpo>
          </Tabela>
        </Secao>
      </div>
    </>
  );
}

/**
 * A faixa de pendências só aparece quando existe pendência — e some sozinha
 * quando não existe.
 *
 * Um painel que mostra "0 rejeições" todo dia treina a pessoa a não olhar para
 * aquele canto da tela. No dia em que aparecer 12, ninguém vai ver.
 */
function FaixaPendencias({
  pendencias,
  total,
}: {
  pendencias: Pendencias;
  total: number;
}) {
  const itens = [
    { rotulo: "cobranças rejeitadas pelo banco", n: pendencias.cobrancas_rejeitadas },
    { rotulo: "pagamentos sem cobrança correspondente", n: pendencias.ocorrencias_orfas },
    { rotulo: "arquivos com erro", n: pendencias.arquivos_com_erro },
    { rotulo: "lotes com erro", n: pendencias.lotes_com_erro },
    { rotulo: "lotes aguardando envio", n: pendencias.lotes_aguardando_envio },
    { rotulo: "clientes sem endereço completo", n: pendencias.clientes_sem_endereco },
  ].filter((item) => item.n > 0);

  return (
    <Link
      href="/pendencias"
      className="mb-5 flex items-start gap-3 rounded-card border border-atencao/30 bg-atencao-suave px-4 py-3.5 transition-colors hover:border-atencao/60"
    >
      <AlertTriangle className="mt-0.5 size-4.5 shrink-0 text-atencao" />
      <div className="min-w-0 flex-1">
        <p className="text-[13.5px] font-medium text-texto">
          {numero(total)} {total === 1 ? "pendência" : "pendências"} precisam de você
        </p>
        <p className="mt-0.5 text-[12.5px] text-texto-suave">
          {itens.map((item) => `${item.n} ${item.rotulo}`).join(" · ")}
        </p>
      </div>
      <ArrowRight className="mt-0.5 size-4 shrink-0 text-texto-tenue" />
    </Link>
  );
}
