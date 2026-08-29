"use client";

import { AlertCircle, Plus, Search, Upload } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { ImportarClientes } from "@/components/clientes/importar";
import { Badge } from "@/components/ui/badge";
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
import { useDebounce, useLista } from "@/lib/hooks";
import type { Cliente } from "@/lib/tipos";
import { moeda, numero, telefone } from "@/lib/utils";
import { useSessao } from "@/providers/sessao";

const SITUACOES = [
  { valor: "", rotulo: "Todos" },
  { valor: "ATIVO", rotulo: "Ativos" },
  { valor: "INADIMPLENTE", rotulo: "Inadimplentes" },
  { valor: "INATIVO", rotulo: "Inativos" },
  { valor: "BLOQUEADO", rotulo: "Bloqueados" },
];

export default function PaginaClientes() {
  const { pode, podeCapacidade } = useSessao();
  const [busca, setBusca] = React.useState("");
  const [status, setStatus] = React.useState("");
  const termo = useDebounce(busca);
  const [importando, setImportando] = React.useState(false);

  const lista = useLista<Cliente>("/clients/", {
    search: termo || undefined,
    status: status || undefined,
  });

  return (
    <>
      <TituloPagina
        titulo="Clientes"
        descricao="O sacado do boleto. Nome, documento e endereço vão impressos no título."
        acoes={
          <>
            {podeCapacidade("importar_clientes") && (
              <Botao variante="contorno" onClick={() => setImportando(true)}>
                <Upload /> Importar planilha
              </Botao>
            )}
            {pode("clientes", "create") && (
              <Botao asChild>
                <Link href="/clientes/novo">
                  <Plus /> Novo cliente
                </Link>
              </Botao>
            )}
          </>
        }
      />

      <Filtros>
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-texto-tenue" />
          <Input
            className="pl-9"
            placeholder="Nome, CPF/CNPJ, e-mail, telefone…"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>
        <Selecao
          className="w-44"
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

      <Secao titulo={`${numero(lista.total)} clientes`}>
        <Tabela>
          <Cabecalho>
            <tr>
              <Th>Cliente</Th>
              <Th>Contato</Th>
              <Th>Cidade</Th>
              <Th>Em aberto</Th>
              <Th>Situação</Th>
            </tr>
          </Cabecalho>
          <Corpo>
            {lista.carregando ? (
              <Esqueleto colunas={5} />
            ) : lista.dados.length === 0 ? (
              <Vazio
                colunas={5}
                titulo="Nenhum cliente"
                descricao="Cadastre um por vez ou importe a carteira inteira de uma planilha."
                acao={
                  podeCapacidade("importar_clientes") ? (
                    <Botao onClick={() => setImportando(true)}>
                      <Upload /> Importar planilha
                    </Botao>
                  ) : undefined
                }
              />
            ) : (
              lista.dados.map((cliente) => (
                <Linha key={cliente.id}>
                  <Td>
                    <Link
                      href={`/clientes/${cliente.id}`}
                      className="font-medium hover:text-acento"
                    >
                      {cliente.nome}
                    </Link>
                    <p className="text-[12.5px] text-texto-tenue">
                      {cliente.codigo} · {cliente.documento_formatado}
                    </p>
                  </Td>
                  <Td className="text-[13px] text-texto-suave">
                    {cliente.email || "—"}
                    {cliente.telefone && (
                      <p className="text-[12.5px] text-texto-tenue">
                        {telefone(cliente.telefone)}
                      </p>
                    )}
                  </Td>
                  <Td className="text-[13px] text-texto-suave">
                    {cliente.cidade ? `${cliente.cidade}/${cliente.uf}` : "—"}
                  </Td>
                  <Td className="text-[13px]">
                    {cliente.cobrancas_abertas ? (
                      <>
                        <span className="font-medium tabular">
                          {moeda(cliente.valor_em_aberto)}
                        </span>
                        <p className="text-[12px] text-texto-tenue">
                          {cliente.cobrancas_abertas} títulos
                        </p>
                      </>
                    ) : (
                      <span className="text-texto-tenue">—</span>
                    )}
                  </Td>
                  <Td>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge
                        tom={
                          cliente.status === "ATIVO"
                            ? "positivo"
                            : cliente.status === "INADIMPLENTE"
                              ? "negativo"
                              : "neutro"
                        }
                        ponto
                      >
                        {cliente.status.charAt(0) +
                          cliente.status.slice(1).toLowerCase()}
                      </Badge>
                      {/* O aviso mais útil da tela: sem endereço completo, o
                          banco recusa o registro do título — e a rejeição só
                          apareceria no retorno do dia seguinte. */}
                      {!cliente.pronto_para_boleto && (
                        <Badge tom="atencao" title="O banco recusa o registro sem endereço completo">
                          <AlertCircle className="size-3" /> sem endereço
                        </Badge>
                      )}
                    </div>
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
          rotulo="clientes"
        />
      </Secao>

      <ImportarClientes
        aberto={importando}
        aoFechar={() => setImportando(false)}
        aoConcluir={lista.recarregar}
      />
    </>
  );
}
