"use client";

import * as React from "react";

import { Input } from "@/components/ui/campos";
import { CardIndicador, Filtros, Secao, TituloPagina } from "@/components/ui/pagina";
import { Cabecalho, Corpo, Linha, Tabela, Td, Th } from "@/components/ui/tabela";
import { useRecurso } from "@/lib/hooks";
import type { Conciliacao } from "@/lib/tipos";
import { moeda, numero } from "@/lib/utils";

function primeiroDiaDoMes() {
  const hoje = new Date();
  return new Date(hoje.getFullYear(), hoje.getMonth(), 1).toISOString().slice(0, 10);
}

/**
 * Conciliação: o encontro entre o que se cobrou e o que entrou.
 *
 * As duas colunas usam datas diferentes de propósito — cobrança conta pelo
 * vencimento (quando *deveria* entrar), recebimento conta pelo pagamento
 * (quando entrou). Usar a mesma data nos dois esconderia exatamente o
 * descasamento que se quer enxergar.
 */
export default function PaginaConciliacao() {
  const [inicio, setInicio] = React.useState(primeiroDiaDoMes);
  const [fim, setFim] = React.useState(() => new Date().toISOString().slice(0, 10));

  const { dados, carregando } = useRecurso<Conciliacao>(
    `/reconciliation/?inicio=${inicio}&fim=${fim}`,
  );

  return (
    <>
      <TituloPagina
        titulo="Conciliação"
        descricao="Cobrado, recebido e o que ficou pelo caminho no período."
      />

      <Filtros>
        <Input
          type="date"
          className="w-44"
          value={inicio}
          onChange={(e) => setInicio(e.target.value)}
          aria-label="Início do período"
        />
        <span className="text-[13px] text-texto-tenue">até</span>
        <Input
          type="date"
          className="w-44"
          value={fim}
          onChange={(e) => setFim(e.target.value)}
          aria-label="Fim do período"
        />
      </Filtros>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <CardIndicador
          rotulo="Cobrado no período"
          valor={moeda(dados?.cobrancas.valor_total)}
          detalhe={`${numero(
            dados?.cobrancas.quantidade ?? 0,
          )} títulos com vencimento no período`}
          carregando={carregando}
        />
        <CardIndicador
          rotulo="Recebido"
          valor={moeda(dados?.recebimentos.bruto)}
          detalhe={`líquido de tarifas: ${moeda(dados?.recebimentos.liquido)}`}
          tom="positivo"
          carregando={carregando}
        />
        <CardIndicador
          rotulo="Em aberto"
          valor={moeda(dados?.cobrancas.em_aberto)}
          detalhe="ainda não pago"
          tom="atencao"
          carregando={carregando}
        />
        <CardIndicador
          rotulo="Inadimplência"
          valor={`${dados?.inadimplencia.percentual ?? 0}%`}
          detalhe={`${moeda(dados?.inadimplencia.valor)} vencidos e não pagos`}
          tom="negativo"
          carregando={carregando}
        />
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <Secao titulo="Cobranças por situação">
          <Tabela>
            <Cabecalho>
              <tr>
                <Th>Situação</Th>
                <Th className="text-right">Títulos</Th>
                <Th className="text-right">Valor</Th>
              </tr>
            </Cabecalho>
            <Corpo>
              {(dados?.por_status ?? []).map((linha) => (
                <Linha key={linha.status}>
                  <Td className="text-[13.5px]">
                    {linha.status.charAt(0) +
                      linha.status.slice(1).toLowerCase().replace(/_/g, " ")}
                  </Td>
                  <Td className="text-right text-[13px] tabular">
                    {numero(linha.quantidade)}
                  </Td>
                  <Td className="text-right font-medium tabular">
                    {moeda(linha.valor)}
                  </Td>
                </Linha>
              ))}
            </Corpo>
          </Tabela>
        </Secao>

        <Secao titulo="Composição do recebido">
          <Tabela>
            <Corpo>
              <LinhaValor rotulo="Valor dos títulos" valor={dados?.recebimentos.bruto} />
              <LinhaValor rotulo="Juros recebidos" valor={dados?.recebimentos.juros} />
              <LinhaValor rotulo="Multas recebidas" valor={dados?.recebimentos.multa} />
              <LinhaValor
                rotulo="Descontos concedidos"
                valor={dados?.recebimentos.desconto}
                negativo
              />
              <LinhaValor
                rotulo="Tarifas do banco"
                valor={dados?.recebimentos.tarifa}
                negativo
              />
              <LinhaValor
                rotulo="Líquido na conta"
                valor={dados?.recebimentos.liquido}
                destaque
              />
            </Corpo>
          </Tabela>
        </Secao>
      </div>
    </>
  );
}

function LinhaValor({
  rotulo,
  valor,
  negativo,
  destaque,
}: {
  rotulo: string;
  valor?: string;
  negativo?: boolean;
  destaque?: boolean;
}) {
  return (
    <Linha className={destaque ? "bg-superficie-sutil" : undefined}>
      <Td className={destaque ? "font-medium" : "text-[13.5px] text-texto-suave"}>
        {rotulo}
      </Td>
      <Td
        className={`text-right tabular ${
          destaque ? "font-semibold" : negativo ? "text-negativo" : "font-medium"
        }`}
      >
        {negativo && Number(valor ?? 0) > 0 ? "− " : ""}
        {moeda(valor)}
      </Td>
    </Linha>
  );
}
