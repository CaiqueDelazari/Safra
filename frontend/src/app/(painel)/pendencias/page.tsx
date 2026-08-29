"use client";

import {
  ArrowRight,
  Ban,
  CheckCircle2,
  FileWarning,
  MapPinOff,
  Send,
  TriangleAlert,
  Users,
} from "lucide-react";
import Link from "next/link";

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
import { useLista, useRecursoVivo } from "@/lib/hooks";
import type { Ocorrencia, Pendencias } from "@/lib/tipos";
import { data, moeda, numero } from "@/lib/utils";

/**
 * A tela que evita o modo de falha silencioso do produto.
 *
 * Um sistema de cobrança quebra sem dar erro: a remessa é recusada, o boleto
 * nunca chega ao sacado, e ninguém descobre até o telefone tocar no dia do
 * vencimento. Tudo que precisa de gente está reunido aqui, e a tela some do
 * caminho quando não há nada — um painel que mostra zero todo dia deixa de
 * ser lido.
 */
export default function PaginaPendencias() {
  const { dados, carregando } = useRecursoVivo<Pendencias>(
    "/reconciliation/pendencias/",
    {},
    60_000,
  );
  const orfas = useLista<Ocorrencia>("/bank/occurrences/", { orfas: "true" });

  const cartoes = [
    {
      rotulo: "Cobranças rejeitadas pelo banco",
      valor: dados?.cobrancas_rejeitadas ?? 0,
      icone: Ban,
      href: "/cobrancas?status=REJEITADA",
      explicacao:
        "O banco recusou o registro. O motivo está em cada cobrança — quase sempre cadastro incompleto.",
    },
    {
      rotulo: "Cobranças com erro de geração",
      valor: dados?.cobrancas_com_erro ?? 0,
      icone: FileWarning,
      href: "/cobrancas?status=ERRO",
      explicacao: "Não entraram no arquivo de remessa. Corrija e gere um lote novo.",
    },
    {
      rotulo: "Lotes aguardando envio",
      valor: dados?.lotes_aguardando_envio ?? 0,
      icone: Send,
      href: "/lotes?status=PRONTO",
      explicacao:
        "O arquivo está pronto e o banco ainda não o recebeu. Nenhum boleto é cobrável até isso acontecer.",
    },
    {
      rotulo: "Lotes com erro",
      valor: dados?.lotes_com_erro ?? 0,
      icone: TriangleAlert,
      href: "/lotes?status=ERRO",
      explicacao: "A montagem ou o envio falhou. Abra o lote para ver o motivo.",
    },
    {
      rotulo: "Arquivos de retorno com problema",
      valor: (dados?.arquivos_com_erro ?? 0) + (dados?.arquivos_pendentes ?? 0),
      icone: FileWarning,
      href: "/retornos",
      explicacao:
        "Retorno que não foi lido inteiro. Reprocessar é seguro — não duplica pagamento.",
    },
    {
      rotulo: "Clientes sem endereço completo",
      valor: dados?.clientes_sem_endereco ?? 0,
      icone: MapPinOff,
      href: "/clientes",
      explicacao:
        "O banco exige endereço no registro do título. Sem ele, a cobrança é recusada.",
    },
  ].filter((item) => item.valor > 0);

  const tudoLimpo = !carregando && cartoes.length === 0 && orfas.total === 0;

  return (
    <>
      <TituloPagina
        titulo="Pendências"
        descricao="O que precisa de uma pessoa. Nada aqui se resolve sozinho."
      />

      {tudoLimpo ? (
        <div className="rounded-card border border-borda bg-superficie px-6 py-16 text-center">
          <CheckCircle2 className="mx-auto size-8 text-positivo" />
          <p className="mt-3 text-[15px] font-medium">Nada pendente</p>
          <p className="mx-auto mt-1 max-w-sm text-[13px] text-texto-suave">
            Toda cobrança está registrada, todo retorno foi lido e todo pagamento
            encontrou o título dele.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {cartoes.map((item) => (
            <Link
              key={item.rotulo}
              href={item.href}
              className="group rounded-card border border-borda bg-superficie p-5 transition-colors hover:border-borda-forte"
            >
              <div className="flex items-start justify-between gap-3">
                <p className="text-[13px] font-medium text-texto-suave">
                  {item.rotulo}
                </p>
                <span className="flex size-8 items-center justify-center rounded-lg bg-atencao-suave text-atencao">
                  <item.icone className="size-4" />
                </span>
              </div>
              <p className="mt-2.5 text-[28px] leading-none font-semibold tabular">
                {numero(item.valor)}
              </p>
              <p className="mt-2 text-[12.5px] text-texto-tenue">{item.explicacao}</p>
              <span className="mt-3 inline-flex items-center gap-1 text-[12.5px] text-acento opacity-0 transition-opacity group-hover:opacity-100">
                resolver <ArrowRight className="size-3" />
              </span>
            </Link>
          ))}
        </div>
      )}

      {orfas.total > 0 && (
        <Secao
          className="mt-6"
          titulo={`Pagamentos sem cobrança correspondente (${numero(orfas.total)})`}
        >
          <p className="border-b border-borda px-5 py-3 text-[12.5px] text-texto-suave">
            O banco informou movimento em títulos que não existem aqui. Acontece
            com boleto emitido direto no internet banking, ou quando a cobrança
            foi cadastrada depois do retorno chegar — neste caso,{" "}
            <Link href="/retornos" className="text-acento hover:underline">
              reprocessar o arquivo
            </Link>{" "}
            resolve sozinho.
          </p>
          <Tabela>
            <Cabecalho>
              <tr>
                <Th>Nosso número</Th>
                <Th>Ocorrência</Th>
                <Th>Data</Th>
                <Th>Arquivo</Th>
                <Th className="text-right">Valor pago</Th>
              </tr>
            </Cabecalho>
            <Corpo>
              {orfas.carregando ? (
                <Esqueleto colunas={5} />
              ) : orfas.dados.length === 0 ? (
                <Vazio colunas={5} titulo="Nenhuma" />
              ) : (
                orfas.dados.map((ocorrencia) => (
                  <Linha key={ocorrencia.id}>
                    <Td className="text-[13px] tabular">
                      {ocorrencia.nosso_numero || ocorrencia.seu_numero || "—"}
                    </Td>
                    <Td className="text-[13px]">
                      {ocorrencia.tipo_label}
                      <p className="text-[12px] text-texto-tenue">
                        código {ocorrencia.codigo}
                      </p>
                    </Td>
                    <Td className="text-[13px] text-texto-suave">
                      {data(ocorrencia.data_ocorrencia)}
                    </Td>
                    <Td className="text-[12.5px] text-texto-tenue">
                      {ocorrencia.arquivo_nome}
                    </Td>
                    <Td className="text-right font-medium tabular">
                      {moeda(ocorrencia.valor_pago)}
                    </Td>
                  </Linha>
                ))
              )}
            </Corpo>
          </Tabela>
        </Secao>
      )}
    </>
  );
}
