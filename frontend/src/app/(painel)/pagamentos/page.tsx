"use client";

import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/campos";
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
import { useDebounce, useLista } from "@/lib/hooks";
import type { Pagamento } from "@/lib/tipos";
import { data, moeda, numero } from "@/lib/utils";

export default function PaginaPagamentos() {
  const [busca, setBusca] = React.useState("");
  const [de, setDe] = React.useState("");
  const [ate, setAte] = React.useState("");
  const termo = useDebounce(busca);

  const lista = useLista<Pagamento>("/payments/", {
    search: termo || undefined,
    pagamento_de: de || undefined,
    pagamento_ate: ate || undefined,
  });

  return (
    <>
      <TituloPagina
        titulo="Pagamentos"
        descricao="Dinheiro que entrou, com a origem de cada centavo."
      />

      <Filtros>
        <Input
          className="min-w-56 flex-1"
          placeholder="Cliente, cobrança, nosso número…"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
        <Input
          type="date"
          className="w-44"
          value={de}
          onChange={(e) => setDe(e.target.value)}
          aria-label="Pago de"
        />
        <Input
          type="date"
          className="w-44"
          value={ate}
          onChange={(e) => setAte(e.target.value)}
          aria-label="Pago até"
        />
      </Filtros>

      <Secao titulo={`${numero(lista.total)} pagamentos`}>
        <Tabela>
          <Cabecalho>
            <tr>
              <Th>Cliente</Th>
              <Th>Cobrança</Th>
              <Th>Pago em</Th>
              <Th>Crédito</Th>
              <Th>Origem</Th>
              <Th className="text-right">Valor</Th>
              <Th className="text-right">Líquido</Th>
            </tr>
          </Cabecalho>
          <Corpo>
            {lista.carregando ? (
              <Esqueleto colunas={7} />
            ) : lista.dados.length === 0 ? (
              <Vazio
                colunas={7}
                titulo="Nenhum pagamento"
                descricao="Os pagamentos aparecem aqui quando o retorno do banco é processado."
              />
            ) : (
              lista.dados.map((pagamento) => (
                <Linha key={pagamento.id}>
                  <Td className="text-[13.5px]">{pagamento.cliente_nome}</Td>
                  <Td className="text-[13px] text-texto-suave">
                    #{pagamento.cobranca_numero} · {pagamento.cobranca_descricao}
                  </Td>
                  <Td className="text-[13px]">{data(pagamento.data_pagamento)}</Td>
                  <Td className="text-[13px] text-texto-suave">
                    {data(pagamento.data_credito)}
                  </Td>
                  <Td>
                    {/* Baixa manual é dinheiro sem prova documental do banco.
                        Destacá-la é o que permite auditar depois. */}
                    <Badge tom={pagamento.origem === "MANUAL" ? "atencao" : "neutro"}>
                      {pagamento.origem_label}
                    </Badge>
                    {pagamento.estornado && (
                      <Badge tom="negativo" className="ml-1.5">
                        estornado
                      </Badge>
                    )}
                  </Td>
                  <Td className="text-right font-medium tabular">
                    {moeda(pagamento.valor)}
                    {Number(pagamento.juros) > 0 && (
                      <p className="text-[12px] text-texto-tenue">
                        + {moeda(pagamento.juros)} juros
                      </p>
                    )}
                  </Td>
                  <Td className="text-right text-positivo tabular">
                    {moeda(pagamento.valor_liquido)}
                    {Number(pagamento.tarifa) > 0 && (
                      <p className="text-[12px] text-texto-tenue">
                        − {moeda(pagamento.tarifa)} tarifa
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
          rotulo="pagamentos"
        />
      </Secao>
    </>
  );
}
