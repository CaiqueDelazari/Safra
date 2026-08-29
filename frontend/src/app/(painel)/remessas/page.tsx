"use client";

import { Download } from "lucide-react";
import Link from "next/link";

import { StatusArquivoBadge } from "@/components/cobrancas/status";
import { Botao } from "@/components/ui/button";
import { Secao, TituloPagina } from "@/components/ui/pagina";
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
import type { ArquivoBancario } from "@/lib/tipos";
import { dataHora, moeda, numero } from "@/lib/utils";

export default function PaginaRemessas() {
  const lista = useLista<ArquivoBancario>("/bank/files/", { tipo: "REMESSA" });

  return (
    <>
      <TituloPagina
        titulo="Remessas"
        descricao="Os arquivos enviados ao banco, guardados com hash — para o dia em que o banco e o sistema discordarem."
      />

      <Secao titulo={`${numero(lista.total)} arquivos`}>
        <Tabela>
          <Cabecalho>
            <tr>
              <Th>Arquivo</Th>
              <Th>Conta</Th>
              <Th>Títulos</Th>
              <Th>Situação</Th>
              <Th className="text-right">Valor</Th>
              <Th className="w-16" />
            </tr>
          </Cabecalho>
          <Corpo>
            {lista.carregando ? (
              <Esqueleto colunas={6} />
            ) : lista.dados.length === 0 ? (
              <Vazio
                colunas={6}
                titulo="Nenhuma remessa gerada"
                descricao="As remessas aparecem aqui quando um lote é montado."
                acao={
                  <Botao asChild>
                    <Link href="/cobrancas">Ir para cobranças</Link>
                  </Botao>
                }
              />
            ) : (
              lista.dados.map((arquivo) => (
                <Linha key={arquivo.id}>
                  <Td>
                    <p className="font-medium">{arquivo.nome_original}</p>
                    <p className="text-[12.5px] text-texto-tenue">
                      {dataHora(arquivo.recebido_em)}
                    </p>
                  </Td>
                  <Td className="text-[13px] text-texto-suave">
                    {arquivo.conta_nome ?? arquivo.banco_label}
                  </Td>
                  <Td className="text-[13px] tabular">
                    {numero(arquivo.quantidade_processada)}
                    {arquivo.quantidade_com_erro > 0 && (
                      <span className="ml-1.5 text-[12px] text-negativo">
                        {arquivo.quantidade_com_erro} fora
                      </span>
                    )}
                  </Td>
                  <Td>
                    <StatusArquivoBadge
                      status={arquivo.status}
                      rotulo={arquivo.status_label}
                    />
                  </Td>
                  <Td className="text-right font-medium tabular">
                    {moeda(arquivo.valor_total)}
                  </Td>
                  <Td>
                    {arquivo.download && (
                      <Botao
                        variante="fantasma"
                        tamanho="icone-sm"
                        asChild
                        aria-label="Baixar arquivo"
                      >
                        <a href={arquivo.download} download>
                          <Download />
                        </a>
                      </Botao>
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
          rotulo="remessas"
        />
      </Secao>
    </>
  );
}
