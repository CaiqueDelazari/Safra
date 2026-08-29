"use client";

import Link from "next/link";
import * as React from "react";

import { StatusLoteBadge } from "@/components/cobrancas/status";
import { Selecao } from "@/components/ui/campos";
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
import { useLista } from "@/lib/hooks";
import type { Lote } from "@/lib/tipos";
import { dataHora, moeda, numero } from "@/lib/utils";

const SITUACOES = [
  { valor: "", rotulo: "Todos os lotes" },
  { valor: "PRONTO", rotulo: "Prontos para envio" },
  { valor: "ENVIADO", rotulo: "Enviados" },
  { valor: "CONFIRMADO", rotulo: "Confirmados" },
  { valor: "PARCIAL", rotulo: "Com rejeições" },
  { valor: "ERRO", rotulo: "Com erro" },
];

export default function PaginaLotes() {
  const [status, setStatus] = React.useState("");
  const lista = useLista<Lote>("/batches/", { status: status || undefined });

  return (
    <>
      <TituloPagina
        titulo="Lotes de remessa"
        descricao="Cada lote é um envio ao banco. Aqui se acompanha o que já foi e o que travou."
      />

      <Filtros>
        <Selecao
          className="w-56"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {SITUACOES.map((opcao) => (
            <option key={opcao.valor} value={opcao.valor}>
              {opcao.rotulo}
            </option>
          ))}
        </Selecao>
      </Filtros>

      <Secao titulo={`${numero(lista.total)} lotes`}>
        <Tabela>
          <Cabecalho>
            <tr>
              <Th>Lote</Th>
              <Th>Conta</Th>
              <Th>Títulos</Th>
              <Th>Situação</Th>
              <Th>Enviado</Th>
              <Th className="text-right">Valor</Th>
            </tr>
          </Cabecalho>
          <Corpo>
            {lista.carregando ? (
              <Esqueleto colunas={6} />
            ) : lista.dados.length === 0 ? (
              <Vazio
                colunas={6}
                titulo="Nenhum lote"
                descricao="Selecione cobranças na tela de Cobranças e gere o primeiro lote."
              />
            ) : (
              lista.dados.map((lote) => (
                <Linha key={lote.id}>
                  <Td>
                    <Link
                      href={`/lotes/${lote.id}`}
                      className="font-medium hover:text-acento"
                    >
                      Lote #{lote.numero}
                    </Link>
                    <p className="text-[12.5px] text-texto-tenue">
                      {lote.criado_por_nome ?? "sistema"} · {dataHora(lote.criado_em)}
                    </p>
                  </Td>
                  <Td className="text-[13px] text-texto-suave">{lote.conta_nome}</Td>
                  <Td className="text-[13px]">
                    <span className="tabular">{numero(lote.quantidade)}</span>
                    {lote.quantidade_rejeitada > 0 && (
                      <span className="ml-1.5 text-[12px] text-negativo">
                        {lote.quantidade_rejeitada} rejeitados
                      </span>
                    )}
                  </Td>
                  <Td>
                    <StatusLoteBadge status={lote.status} />
                    {["MONTANDO", "ENVIANDO"].includes(lote.status) && (
                      <p className="mt-1 text-[12px] text-texto-tenue tabular">
                        {lote.progresso}% · {lote.etapa}
                      </p>
                    )}
                  </Td>
                  <Td className="text-[13px] text-texto-suave">
                    {lote.enviado_em ? dataHora(lote.enviado_em) : "—"}
                  </Td>
                  <Td className="text-right font-medium tabular">
                    {moeda(lote.valor_total)}
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
          rotulo="lotes"
        />
      </Secao>
    </>
  );
}
