"use client";

import { ArrowLeft, Download, RefreshCw, Send } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { StatusCobrancaBadge, StatusLoteBadge } from "@/components/cobrancas/status";
import { Botao } from "@/components/ui/button";
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
import { acompanharTarefa, api, ApiError } from "@/lib/api";
import { useLista, useRecursoVivo } from "@/lib/hooks";
import type { CobrancaLista, Lote, RespostaTarefa, StatusCobranca } from "@/lib/tipos";
import { data, dataHora, moeda, numero } from "@/lib/utils";
import { useSessao } from "@/providers/sessao";

export default function PaginaLote() {
  const { id } = useParams<{ id: string }>();
  const { podeCapacidade } = useSessao();

  // Enquanto o worker monta o arquivo, a tela precisa andar sozinha. Fora do
  // trabalho em curso, 30 s é folga suficiente e não gera requisição à toa.
  const { dados: lote, recarregar } = useRecursoVivo<Lote>(
    `/batches/${id}/`,
    {},
    15_000,
  );
  const cobrancas = useLista<CobrancaLista>(`/batches/${id}/charges/`);
  const [trabalhando, setTrabalhando] = React.useState(false);

  const emAndamento = lote
    ? ["MONTANDO", "ENVIANDO"].includes(lote.status)
    : false;

  async function acao(caminho: string, mensagem: string) {
    setTrabalhando(true);
    try {
      const resposta = await api.post<RespostaTarefa>(caminho);
      if (resposta?.tarefa_id) await acompanharTarefa(resposta.tarefa_id);
      toast.success(mensagem);
      recarregar();
      cobrancas.recarregar();
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha na operação.");
    } finally {
      setTrabalhando(false);
    }
  }

  if (!lote) {
    return <div className="carregando h-64 rounded-card bg-neutro-suave" />;
  }

  return (
    <>
      <Link
        href="/lotes"
        className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-texto-suave hover:text-texto"
      >
        <ArrowLeft className="size-3.5" /> Lotes
      </Link>

      <TituloPagina
        titulo={`Lote #${lote.numero}`}
        descricao={`${numero(lote.quantidade)} títulos · ${moeda(
          lote.valor_total,
        )} · ${lote.conta_nome}`}
        acoes={
          <>
            {lote.arquivo?.download && (
              <Botao variante="contorno" asChild>
                <a href={lote.arquivo.download} download>
                  <Download /> Baixar remessa
                </a>
              </Botao>
            )}
            {lote.status === "ERRO" && podeCapacidade("gerar_lote") && (
              <Botao
                variante="contorno"
                onClick={() => acao(`/batches/${id}/rebuild/`, "Arquivo remontado.")}
                carregando={trabalhando}
              >
                <RefreshCw /> Remontar
              </Botao>
            )}
            {lote.status === "PRONTO" && podeCapacidade("enviar_remessa") && (
              <Botao
                onClick={() => acao(`/batches/${id}/submit/`, "Remessa enviada.")}
                carregando={trabalhando}
              >
                <Send /> Enviar ao banco
              </Botao>
            )}
          </>
        }
      />

      {emAndamento && (
        <div className="mb-5 rounded-card border border-borda bg-superficie p-5">
          <div className="mb-2 flex items-center justify-between text-[13px]">
            <span className="font-medium">{lote.etapa || "Processando…"}</span>
            <span className="text-texto-suave tabular">{lote.progresso}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-neutro-suave">
            <div
              className="h-full rounded-full bg-acento transition-[width] duration-500"
              style={{ width: `${Math.max(lote.progresso, 4)}%` }}
            />
          </div>
          <p className="mt-2.5 text-[12.5px] text-texto-tenue">
            Pode fechar esta página: o processamento continua no servidor.
          </p>
        </div>
      )}

      {lote.mensagem_erro && (
        <div className="mb-5 rounded-card border border-negativo/30 bg-negativo-suave px-4 py-3.5">
          <p className="text-[13px] font-medium text-negativo">
            O lote parou com erro
          </p>
          <p className="mt-1 text-[12.5px] whitespace-pre-wrap text-texto-suave">
            {lote.mensagem_erro}
          </p>
        </div>
      )}

      <div className="mb-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Dado rotulo="Situação">
          <StatusLoteBadge status={lote.status} />
        </Dado>
        <Dado rotulo="Arquivo de remessa">
          {lote.arquivo ? (
            <span className="text-[13.5px]">{lote.arquivo.nome_original}</span>
          ) : (
            <span className="text-[13.5px] text-texto-tenue">ainda não gerado</span>
          )}
        </Dado>
        <Dado rotulo="Protocolo do banco">
          <span className="text-[13.5px] break-all">
            {lote.protocolo_banco || "—"}
          </span>
        </Dado>
        <Dado rotulo="Enviado em">
          <span className="text-[13.5px]">
            {lote.enviado_em ? dataHora(lote.enviado_em) : "—"}
          </span>
        </Dado>
      </div>

      <Secao titulo={`Títulos do lote (${numero(cobrancas.total)})`}>
        <Tabela>
          <Cabecalho>
            <tr>
              <Th>Cobrança</Th>
              <Th>Cliente</Th>
              <Th>Nosso número</Th>
              <Th>Vencimento</Th>
              <Th>Situação</Th>
              <Th className="text-right">Valor</Th>
            </tr>
          </Cabecalho>
          <Corpo>
            {cobrancas.carregando ? (
              <Esqueleto colunas={6} />
            ) : cobrancas.dados.length === 0 ? (
              <Vazio colunas={6} titulo="Nenhum título neste lote" />
            ) : (
              cobrancas.dados.map((cobranca) => (
                <Linha key={cobranca.id}>
                  <Td>
                    <Link
                      href={`/cobrancas/${cobranca.id}`}
                      className="font-medium hover:text-acento"
                    >
                      #{cobranca.numero}
                    </Link>
                    <p className="text-[12.5px] text-texto-tenue">
                      {cobranca.descricao}
                    </p>
                  </Td>
                  <Td className="text-[13px]">{cobranca.cliente_nome}</Td>
                  <Td className="text-[13px] tabular">
                    {cobranca.nosso_numero || "—"}
                  </Td>
                  <Td className="text-[13px] text-texto-suave">
                    {data(cobranca.data_vencimento)}
                  </Td>
                  <Td>
                    <StatusCobrancaBadge
                      status={cobranca.status as StatusCobranca}
                      vencida={cobranca.vencida}
                    />
                    {cobranca.mensagem_erro && (
                      <p className="mt-1 max-w-56 text-[12px] text-negativo">
                        {cobranca.mensagem_erro}
                      </p>
                    )}
                  </Td>
                  <Td className="text-right font-medium tabular">
                    {moeda(cobranca.valor)}
                  </Td>
                </Linha>
              ))
            )}
          </Corpo>
        </Tabela>
      </Secao>
    </>
  );
}

function Dado({
  rotulo,
  children,
}: {
  rotulo: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-card border border-borda bg-superficie px-4 py-3.5">
      <p className="mb-1.5 text-[12px] tracking-wide text-texto-tenue uppercase">
        {rotulo}
      </p>
      {children}
    </div>
  );
}
