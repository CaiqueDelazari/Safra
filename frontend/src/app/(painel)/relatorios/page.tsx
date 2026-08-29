"use client";

import {
  Download,
  FileSpreadsheet,
  FileWarning,
  Receipt,
  Send,
  TrendingDown,
  Wallet,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Botao } from "@/components/ui/button";
import { Input } from "@/components/ui/campos";
import { Filtros, Secao, TituloPagina } from "@/components/ui/pagina";
import { Cabecalho, Corpo, Linha, Tabela, Td, Th, Vazio } from "@/components/ui/tabela";
import { api, armazenamento } from "@/lib/api";
import type { Pagina } from "@/lib/tipos";
import { data, moeda, numero } from "@/lib/utils";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

interface Inadimplente {
  cliente_id: number;
  cliente: string;
  documento: string;
  telefone: string;
  email: string;
  titulos: number;
  valor: string;
  vencimento_mais_antigo: string;
  dias_em_atraso: number;
}

function primeiroDiaDoMes() {
  const hoje = new Date();
  return new Date(hoje.getFullYear(), hoje.getMonth(), 1).toISOString().slice(0, 10);
}

export default function PaginaRelatorios() {
  const [inicio, setInicio] = React.useState(primeiroDiaDoMes);
  const [fim, setFim] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [baixando, setBaixando] = React.useState<string | null>(null);
  const [inadimplentes, setInadimplentes] = React.useState<Inadimplente[] | null>(null);

  /**
   * Baixa um CSV grande sem carregá-lo na memória do navegador de uma vez.
   *
   * O `fetch` normal traz o corpo inteiro antes de qualquer coisa acontecer,
   * e a exportação de cobranças de um ano pode ter centenas de milhares de
   * linhas. Aqui o corpo vira `blob` direto — o navegador escreve em disco
   * conforme chega.
   *
   * O token vai por cabeçalho, então não dá para simplesmente apontar um
   * `<a href>` para a rota: ele não sabe mandar `Authorization`.
   */
  async function baixar(caminho: string, nome: string) {
    setBaixando(nome);
    try {
      const url = new URL(`${BASE}${caminho}`);
      url.searchParams.set("inicio", inicio);
      url.searchParams.set("fim", fim);
      url.searchParams.set("formato", "csv");

      const resposta = await fetch(url.toString(), {
        headers: {
          Authorization: `Bearer ${armazenamento.access ?? ""}`,
          ...(armazenamento.empresa
            ? { "X-Empresa-Id": String(armazenamento.empresa) }
            : {}),
        },
      });
      if (!resposta.ok) throw new Error(`Erro ${resposta.status}`);

      const blob = await resposta.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${nome}-${inicio}-a-${fim}.csv`;
      link.click();
      URL.revokeObjectURL(link.href);
      toast.success("Arquivo baixado.");
    } catch {
      toast.error("Falha ao gerar o relatório.");
    } finally {
      setBaixando(null);
    }
  }

  async function verInadimplencia() {
    setBaixando("inadimplencia");
    try {
      const dados = await api.get<Inadimplente[]>("/reports/inadimplencia/");
      setInadimplentes(dados);
    } catch {
      toast.error("Falha ao carregar a inadimplência.");
    } finally {
      setBaixando(null);
    }
  }

  const relatorios = [
    {
      chave: "cobrancas",
      rotulo: "Cobranças emitidas",
      descricao: "Tudo que venceu no período, com situação e pagamento.",
      icone: Receipt,
      caminho: "/reports/cobrancas/",
    },
    {
      chave: "pagamentos",
      rotulo: "Pagamentos recebidos",
      descricao: "Valor, juros, multa, tarifa e o líquido que entrou.",
      icone: Wallet,
      caminho: "/reports/pagamentos/",
    },
  ];

  return (
    <>
      <TituloPagina
        titulo="Relatórios"
        descricao="Exportação em CSV, pronta para abrir no Excel."
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

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {relatorios.map((relatorio) => (
          <div
            key={relatorio.chave}
            className="flex flex-col rounded-card border border-borda bg-superficie p-5"
          >
            <span className="flex size-9 items-center justify-center rounded-lg bg-acento-suave text-acento">
              <relatorio.icone className="size-4.5" />
            </span>
            <p className="mt-3 text-[14.5px] font-medium">{relatorio.rotulo}</p>
            <p className="mt-1 flex-1 text-[12.5px] text-texto-suave">
              {relatorio.descricao}
            </p>
            <Botao
              variante="contorno"
              className="mt-4 w-full"
              carregando={baixando === relatorio.chave}
              onClick={() => baixar(relatorio.caminho, relatorio.chave)}
            >
              <Download /> Baixar CSV
            </Botao>
          </div>
        ))}

        <div className="flex flex-col rounded-card border border-borda bg-superficie p-5">
          <span className="flex size-9 items-center justify-center rounded-lg bg-negativo-suave text-negativo">
            <TrendingDown className="size-4.5" />
          </span>
          <p className="mt-3 text-[14.5px] font-medium">Inadimplentes</p>
          <p className="mt-1 flex-1 text-[12.5px] text-texto-suave">
            Quem deve, quanto e há quanto tempo — com telefone e e-mail para a
            régua de cobrança. Não usa o período: mostra o que está vencido hoje.
          </p>
          <div className="mt-4 flex gap-2">
            <Botao
              variante="contorno"
              className="flex-1"
              carregando={baixando === "inadimplencia"}
              onClick={verInadimplencia}
            >
              Ver na tela
            </Botao>
            <Botao
              variante="contorno"
              tamanho="icone"
              aria-label="Baixar CSV de inadimplentes"
              onClick={() => baixar("/reports/inadimplencia/", "inadimplentes")}
            >
              <Download />
            </Botao>
          </div>
        </div>

        <AtalhoRelatorio
          icone={Send}
          rotulo="Remessas do período"
          descricao="Os lotes enviados ao banco, com protocolo e situação."
          href="/remessas"
        />
        <AtalhoRelatorio
          icone={FileSpreadsheet}
          rotulo="Retornos do período"
          descricao="Os arquivos recebidos e quantos registros cada um aplicou."
          href="/retornos"
        />
        <AtalhoRelatorio
          icone={FileWarning}
          rotulo="Rejeições do banco"
          descricao="Agrupadas por motivo — é o que faz a taxa de recusa cair."
          href="/pendencias"
        />
      </div>

      {inadimplentes && (
        <Secao
          className="mt-6"
          titulo={`Inadimplentes (${numero(inadimplentes.length)})`}
          acoes={
            <Botao
              variante="fantasma"
              tamanho="sm"
              onClick={() => setInadimplentes(null)}
            >
              fechar
            </Botao>
          }
        >
          <Tabela>
            <Cabecalho>
              <tr>
                <Th>Cliente</Th>
                <Th>Contato</Th>
                <Th>Títulos</Th>
                <Th>Mais antigo</Th>
                <Th className="text-right">Em aberto</Th>
              </tr>
            </Cabecalho>
            <Corpo>
              {inadimplentes.length === 0 ? (
                <Vazio
                  colunas={5}
                  titulo="Ninguém em atraso"
                  descricao="Não há títulos vencidos e não pagos."
                />
              ) : (
                inadimplentes.map((linha) => (
                  <Linha key={linha.cliente_id}>
                    <Td>
                      <p className="font-medium">{linha.cliente}</p>
                      <p className="text-[12.5px] text-texto-tenue">{linha.documento}</p>
                    </Td>
                    <Td className="text-[13px] text-texto-suave">
                      {linha.telefone || "—"}
                      {linha.email && (
                        <p className="text-[12px] text-texto-tenue">{linha.email}</p>
                      )}
                    </Td>
                    <Td className="text-[13px] tabular">{linha.titulos}</Td>
                    <Td className="text-[13px]">
                      {data(linha.vencimento_mais_antigo)}
                      <span className="ml-1.5 text-[12px] text-negativo">
                        {linha.dias_em_atraso}d
                      </span>
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
      )}
    </>
  );
}

function AtalhoRelatorio({
  icone: Icone,
  rotulo,
  descricao,
  href,
}: {
  icone: React.ComponentType<{ className?: string }>;
  rotulo: string;
  descricao: string;
  href: string;
}) {
  return (
    <a
      href={href}
      className="flex flex-col rounded-card border border-borda bg-superficie p-5 transition-colors hover:border-borda-forte"
    >
      <span className="flex size-9 items-center justify-center rounded-lg bg-neutro-suave text-texto-suave">
        <Icone className="size-4.5" />
      </span>
      <p className="mt-3 text-[14.5px] font-medium">{rotulo}</p>
      <p className="mt-1 text-[12.5px] text-texto-suave">{descricao}</p>
    </a>
  );
}
