"use client";

import { ArrowLeft, Ban, Copy, Mail, Receipt, Undo2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { StatusCobrancaBadge } from "@/components/cobrancas/status";
import { Badge } from "@/components/ui/badge";
import { Botao } from "@/components/ui/button";
import { Secao, TituloPagina } from "@/components/ui/pagina";
import { Cabecalho, Corpo, Linha, Tabela, Td, Th, Vazio } from "@/components/ui/tabela";
import { api, ApiError } from "@/lib/api";
import { useRecurso } from "@/lib/hooks";
import type { Cobranca, DadosBoleto, Ocorrencia, Pagamento, Pagina } from "@/lib/tipos";
import { data, dataHora, moeda } from "@/lib/utils";
import { useSessao } from "@/providers/sessao";

export default function PaginaCobranca() {
  const { id } = useParams<{ id: string }>();
  const { podeCapacidade } = useSessao();
  const { dados: cobranca, recarregar } = useRecurso<Cobranca>(`/charges/${id}/`);
  const { dados: ocorrencias } = useRecurso<Pagina<Ocorrencia>>(
    `/bank/occurrences/?cobranca=${id}`,
  );
  const { dados: pagamentos } = useRecurso<Pagina<Pagamento>>(
    `/payments/?search=&cobranca=${id}`,
  );
  const [trabalhando, setTrabalhando] = React.useState(false);

  async function acao(caminho: string, mensagem: string, corpo?: unknown) {
    setTrabalhando(true);
    try {
      await api.post(caminho, corpo);
      toast.success(mensagem);
      recarregar();
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha na operação.");
    } finally {
      setTrabalhando(false);
    }
  }

  if (!cobranca) {
    return <div className="carregando h-64 rounded-card bg-neutro-suave" />;
  }

  const finalizada = ["PAGA", "CANCELADA", "BAIXADA"].includes(cobranca.status);

  return (
    <>
      <Link
        href="/cobrancas"
        className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-texto-suave hover:text-texto"
      >
        <ArrowLeft className="size-3.5" /> Cobranças
      </Link>

      <TituloPagina
        titulo={`#${cobranca.numero} · ${cobranca.descricao}`}
        descricao={`${cobranca.cliente_detalhe.nome} · ${cobranca.cliente_detalhe.documento_formatado}`}
        acoes={
          <>
            {!finalizada && podeCapacidade("baixar_cobranca") && (
              <Botao
                variante="contorno"
                onClick={() =>
                  acao(`/charges/${id}/write-off/`, "Cobrança baixada.", {
                    motivo: "baixa manual pelo painel",
                  })
                }
                carregando={trabalhando}
              >
                <Undo2 /> Baixar
              </Botao>
            )}
            {!finalizada && podeCapacidade("cancelar_cobranca") && (
              <Botao
                variante="perigo"
                onClick={() =>
                  acao(`/charges/${id}/cancel/`, "Cobrança cancelada.", {
                    motivo: "cancelada pelo painel",
                  })
                }
                carregando={trabalhando}
              >
                <Ban /> Cancelar
              </Botao>
            )}
          </>
        }
      />

      {cobranca.mensagem_erro && (
        <div className="mb-5 rounded-card border border-negativo/30 bg-negativo-suave px-4 py-3.5">
          <p className="text-[13px] font-medium text-negativo">
            O banco recusou este título
          </p>
          <p className="mt-1 text-[12.5px] text-texto-suave">
            {cobranca.mensagem_erro}
          </p>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
        <div className="space-y-5">
          <Secao titulo="Situação">
            <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-3">
              <Dado rotulo="Situação">
                <StatusCobrancaBadge status={cobranca.status} vencida={cobranca.vencida} />
              </Dado>
              <Dado rotulo="Valor">
                <span className="text-[15px] font-semibold tabular">
                  {moeda(cobranca.valor)}
                </span>
              </Dado>
              <Dado rotulo="Vencimento">
                {data(cobranca.data_vencimento)}
                {cobranca.dias_em_atraso > 0 && (
                  <span className="ml-1.5 text-[12px] text-negativo">
                    {cobranca.dias_em_atraso} dias
                  </span>
                )}
              </Dado>
              <Dado rotulo="Emissão">{data(cobranca.data_emissao)}</Dado>
              <Dado rotulo="Nosso número">
                <span className="tabular">{cobranca.nosso_numero || "—"}</span>
              </Dado>
              <Dado rotulo="Conta bancária">{cobranca.conta_nome ?? "—"}</Dado>
              {cobranca.status === "PAGA" && (
                <>
                  <Dado rotulo="Pago em">{data(cobranca.data_pagamento)}</Dado>
                  <Dado rotulo="Valor pago">
                    <span className="font-medium text-positivo tabular">
                      {moeda(cobranca.valor_pago)}
                    </span>
                  </Dado>
                  <Dado rotulo="Crédito">{data(cobranca.data_liquidacao)}</Dado>
                </>
              )}
            </div>
          </Secao>

          <Secao titulo="Histórico do banco">
            <Tabela>
              <Cabecalho>
                <tr>
                  <Th>Ocorrência</Th>
                  <Th>Data</Th>
                  <Th>Arquivo</Th>
                  <Th className="text-right">Valor</Th>
                </tr>
              </Cabecalho>
              <Corpo>
                {(ocorrencias?.resultados ?? []).length === 0 ? (
                  <Vazio
                    colunas={4}
                    titulo="Sem movimento do banco"
                    descricao="As ocorrências aparecem quando o retorno é processado."
                  />
                ) : (
                  ocorrencias!.resultados.map((ocorrencia) => (
                    <Linha key={ocorrencia.id}>
                      <Td>
                        <p className="text-[13.5px]">{ocorrencia.tipo_label}</p>
                        <p className="text-[12px] text-texto-tenue">
                          código {ocorrencia.codigo}
                          {ocorrencia.motivos_descricao &&
                            ` · ${ocorrencia.motivos_descricao}`}
                        </p>
                      </Td>
                      <Td className="text-[13px] text-texto-suave">
                        {data(ocorrencia.data_ocorrencia)}
                      </Td>
                      <Td className="text-[12.5px] text-texto-tenue">
                        {ocorrencia.arquivo_nome}
                      </Td>
                      <Td className="text-right tabular">
                        {Number(ocorrencia.valor_pago) > 0
                          ? moeda(ocorrencia.valor_pago)
                          : "—"}
                      </Td>
                    </Linha>
                  ))
                )}
              </Corpo>
            </Tabela>
          </Secao>

          {(pagamentos?.resultados ?? []).length > 0 && (
            <Secao titulo="Pagamentos">
              <Tabela>
                <Cabecalho>
                  <tr>
                    <Th>Pago em</Th>
                    <Th>Origem</Th>
                    <Th className="text-right">Valor</Th>
                    <Th className="text-right">Líquido</Th>
                  </tr>
                </Cabecalho>
                <Corpo>
                  {pagamentos!.resultados.map((pagamento) => (
                    <Linha key={pagamento.id}>
                      <Td className="text-[13px]">{data(pagamento.data_pagamento)}</Td>
                      <Td>
                        <Badge
                          tom={pagamento.origem === "MANUAL" ? "atencao" : "neutro"}
                        >
                          {pagamento.origem_label}
                        </Badge>
                      </Td>
                      <Td className="text-right font-medium tabular">
                        {moeda(pagamento.valor)}
                      </Td>
                      <Td className="text-right text-positivo tabular">
                        {moeda(pagamento.valor_liquido)}
                      </Td>
                    </Linha>
                  ))}
                </Corpo>
              </Tabela>
            </Secao>
          )}
        </div>

        <PainelBoleto cobranca={cobranca} />
      </div>
    </>
  );
}

function PainelBoleto({ cobranca }: { cobranca: Cobranca }) {
  const { podeCapacidade } = useSessao();
  const temBoleto = Boolean(cobranca.nosso_numero && cobranca.conta_bancaria);
  const { dados: boleto } = useRecurso<DadosBoleto>(
    temBoleto ? `/charges/${cobranca.id}/boleto/` : null,
  );
  const [enviando, setEnviando] = React.useState(false);

  async function enviarPorEmail() {
    setEnviando(true);
    try {
      await api.post(`/charges/${cobranca.id}/send/`);
      toast.success("Boleto enviado ao cliente.");
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha ao enviar.");
    } finally {
      setEnviando(false);
    }
  }

  function copiar(valor: string, rotulo: string) {
    navigator.clipboard.writeText(valor);
    toast.success(`${rotulo} copiada.`);
  }

  return (
    <Secao titulo="Boleto">
      <div className="space-y-4 p-5">
        {!temBoleto ? (
          <p className="text-[13px] text-texto-suave">
            O boleto existe depois que a cobrança entra num lote e é enviada ao
            banco. Selecione-a na tela de Cobranças e gere o lote.
          </p>
        ) : !boleto ? (
          <div className="carregando h-28 rounded-lg bg-neutro-suave" />
        ) : (
          <>
            <div>
              <p className="mb-1.5 text-[12px] tracking-wide text-texto-tenue uppercase">
                Linha digitável
              </p>
              <p className="rounded-lg border border-borda bg-superficie-sutil px-3 py-2.5 text-[13px] break-all tabular">
                {boleto.linha_digitavel_formatada}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Botao
                  variante="contorno"
                  tamanho="sm"
                  onClick={() => copiar(boleto.linha_digitavel, "Linha digitável")}
                >
                  <Copy /> Linha digitável
                </Botao>
                <Botao
                  variante="contorno"
                  tamanho="sm"
                  onClick={() => copiar(boleto.codigo_barras, "Código de barras")}
                >
                  <Copy /> Código de barras
                </Botao>
              </div>
            </div>

            {boleto.url_banco && (
              <Botao variante="contorno" asChild className="w-full">
                <a href={boleto.url_banco} target="_blank" rel="noreferrer">
                  <Receipt /> Abrir boleto no banco
                </a>
              </Botao>
            )}

            {podeCapacidade("enviar_boleto_cliente") && (
              <Botao
                className="w-full"
                onClick={enviarPorEmail}
                carregando={enviando}
                disabled={!cobranca.cliente_detalhe.email}
              >
                <Mail /> Enviar por e-mail
              </Botao>
            )}

            {!cobranca.cliente_detalhe.email && (
              <p className="text-[12.5px] text-texto-tenue">
                O cliente não tem e-mail cadastrado.
              </p>
            )}
            {cobranca.enviado_ao_cliente_em && (
              <p className="text-[12.5px] text-texto-tenue">
                Enviado em {dataHora(cobranca.enviado_ao_cliente_em)}.
              </p>
            )}

            {/* O PDF é documento de apresentação — quem diz se está pago é o
                banco, pelo retorno. Deixar isso explícito na tela evita a
                confusão de "mas eu tenho o boleto aqui". */}
            <p className="border-t border-borda pt-3 text-[12px] text-texto-tenue">
              A situação de pagamento vem do retorno do banco, não do boleto.
            </p>
          </>
        )}
      </div>
    </Secao>
  );
}

function Dado({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-[12px] tracking-wide text-texto-tenue uppercase">
        {rotulo}
      </p>
      <div className="text-[13.5px]">{children}</div>
    </div>
  );
}
