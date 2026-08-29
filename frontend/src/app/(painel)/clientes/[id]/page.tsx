"use client";

import { AlertCircle, ArrowLeft, Mail, Pencil, Phone, Plus } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";

import { StatusCobrancaBadge } from "@/components/cobrancas/status";
import { FormularioCliente } from "@/components/clientes/formulario";
import { Badge } from "@/components/ui/badge";
import { Botao } from "@/components/ui/button";
import { CardIndicador, Secao, TituloPagina } from "@/components/ui/pagina";
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
import { useLista, useRecurso } from "@/lib/hooks";
import type { Cliente, CobrancaLista, StatusCobranca } from "@/lib/tipos";
import { data, moeda, numero, telefone } from "@/lib/utils";
import { useSessao } from "@/providers/sessao";

export default function PaginaCliente() {
  const { id } = useParams<{ id: string }>();
  const { pode } = useSessao();
  const [editando, setEditando] = React.useState(false);

  const { dados: cliente } = useRecurso<Cliente>(`/clients/${id}/`);
  const cobrancas = useLista<CobrancaLista>(`/clients/${id}/charges/`);

  if (!cliente) {
    return <div className="carregando h-64 rounded-card bg-neutro-suave" />;
  }

  if (editando) {
    return (
      <>
        <button
          type="button"
          onClick={() => setEditando(false)}
          className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-texto-suave hover:text-texto"
        >
          <ArrowLeft className="size-3.5" /> {cliente.nome}
        </button>
        <TituloPagina titulo="Editar cliente" />
        <FormularioCliente cliente={cliente} />
      </>
    );
  }

  const pagas = cobrancas.dados.filter((c) => c.status === "PAGA");
  const recebido = pagas.reduce((soma, c) => soma + Number(c.valor_pago || 0), 0);

  return (
    <>
      <Link
        href="/clientes"
        className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-texto-suave hover:text-texto"
      >
        <ArrowLeft className="size-3.5" /> Clientes
      </Link>

      <TituloPagina
        titulo={cliente.nome}
        descricao={`Cliente ${cliente.codigo} · ${cliente.documento_formatado}`}
        acoes={
          <>
            {pode("clientes", "update") && (
              <Botao variante="contorno" onClick={() => setEditando(true)}>
                <Pencil /> Editar
              </Botao>
            )}
            {pode("cobrancas", "create") && (
              <Botao asChild>
                <Link href={`/cobrancas/nova?cliente=${cliente.id}`}>
                  <Plus /> Nova cobrança
                </Link>
              </Botao>
            )}
          </>
        }
      />

      {/* O aviso que evita a rejeição do banco: ele fica no topo da ficha,
          não escondido no formulário, porque quem abre esta tela para criar
          uma cobrança precisa saber antes de criá-la. */}
      {!cliente.pronto_para_boleto && (
        <div className="mb-5 flex items-start gap-3 rounded-card border border-atencao/30 bg-atencao-suave px-4 py-3.5">
          <AlertCircle className="mt-0.5 size-4.5 shrink-0 text-atencao" />
          <div>
            <p className="text-[13.5px] font-medium">Endereço incompleto</p>
            <p className="mt-0.5 text-[12.5px] text-texto-suave">
              O banco recusa o registro do título sem logradouro, cidade, UF e
              CEP. A cobrança pode ser criada, mas não entra em nenhum lote até
              o cadastro ser completado.
            </p>
          </div>
          {pode("clientes", "update") && (
            <Botao
              variante="contorno"
              tamanho="sm"
              className="ml-auto shrink-0"
              onClick={() => setEditando(true)}
            >
              Completar
            </Botao>
          )}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <CardIndicador
          rotulo="Em aberto"
          valor={moeda(cliente.valor_em_aberto)}
          detalhe={`${numero(cliente.cobrancas_abertas ?? 0)} títulos`}
          tom={Number(cliente.valor_em_aberto ?? 0) > 0 ? "atencao" : "neutro"}
        />
        <CardIndicador
          rotulo="Já recebido"
          valor={moeda(recebido)}
          detalhe={`${numero(pagas.length)} pagamentos nesta página`}
          tom="positivo"
        />
        <CardIndicador
          rotulo="Situação"
          valor={
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
              {cliente.status.charAt(0) + cliente.status.slice(1).toLowerCase()}
            </Badge>
          }
          detalhe={`Cadastrado em ${data(cliente.criado_em)}`}
        />
        <CardIndicador
          rotulo="Total de cobranças"
          valor={numero(cobrancas.total)}
          detalhe="no histórico"
        />
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_1.6fr]">
        <Secao titulo="Cadastro">
          <dl className="divide-y divide-borda">
            <Dado rotulo="Documento">{cliente.documento_formatado}</Dado>
            {cliente.nome_fantasia && (
              <Dado rotulo="Nome fantasia">{cliente.nome_fantasia}</Dado>
            )}
            <Dado rotulo="E-mail">
              {cliente.email ? (
                <a
                  href={`mailto:${cliente.email}`}
                  className="inline-flex items-center gap-1.5 hover:text-acento"
                >
                  <Mail className="size-3.5" /> {cliente.email}
                </a>
              ) : (
                <span className="text-texto-tenue">não informado</span>
              )}
            </Dado>
            <Dado rotulo="Telefone">
              {cliente.telefone ? (
                <span className="inline-flex items-center gap-1.5">
                  <Phone className="size-3.5" /> {telefone(cliente.telefone)}
                </span>
              ) : (
                <span className="text-texto-tenue">não informado</span>
              )}
            </Dado>
            <Dado rotulo="Endereço">
              {cliente.endereco_completo || (
                <span className="text-texto-tenue">não informado</span>
              )}
              {cliente.cep && (
                <span className="block text-[12.5px] text-texto-tenue">
                  CEP {cliente.cep_formatado}
                </span>
              )}
            </Dado>
            {cliente.codigo_externo && (
              <Dado rotulo="Código externo">{cliente.codigo_externo}</Dado>
            )}
            {cliente.observacoes && (
              <Dado rotulo="Observações">
                <span className="whitespace-pre-wrap">{cliente.observacoes}</span>
              </Dado>
            )}
          </dl>
        </Secao>

        <Secao titulo={`Cobranças (${numero(cobrancas.total)})`}>
          <Tabela>
            <Cabecalho>
              <tr>
                <Th>Cobrança</Th>
                <Th>Vencimento</Th>
                <Th>Situação</Th>
                <Th className="text-right">Valor</Th>
              </tr>
            </Cabecalho>
            <Corpo>
              {cobrancas.carregando ? (
                <Esqueleto colunas={4} />
              ) : cobrancas.dados.length === 0 ? (
                <Vazio
                  colunas={4}
                  titulo="Nenhuma cobrança"
                  descricao="Este cliente ainda não tem títulos."
                />
              ) : (
                cobrancas.dados.map((cobranca) => (
                  <Linha key={cobranca.id}>
                    <Td>
                      <Link
                        href={`/cobrancas/${cobranca.id}`}
                        className="font-medium hover:text-acento"
                      >
                        #{cobranca.numero} · {cobranca.descricao}
                      </Link>
                    </Td>
                    <Td className="text-[13px] text-texto-suave">
                      {data(cobranca.data_vencimento)}
                    </Td>
                    <Td>
                      <StatusCobrancaBadge
                        status={cobranca.status as StatusCobranca}
                        vencida={cobranca.vencida}
                      />
                    </Td>
                    <Td className="text-right font-medium tabular">
                      {moeda(cobranca.valor)}
                    </Td>
                  </Linha>
                ))
              )}
            </Corpo>
          </Tabela>
          <Paginacao
            pagina={cobrancas.pagina}
            paginas={cobrancas.paginas}
            total={cobrancas.total}
            aoMudar={cobrancas.setPagina}
            rotulo="cobranças"
          />
        </Secao>
      </div>
    </>
  );
}

function Dado({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div className="px-5 py-3.5">
      <dt className="text-[12px] tracking-wide text-texto-tenue uppercase">{rotulo}</dt>
      <dd className="mt-1 text-[13.5px]">{children}</dd>
    </div>
  );
}
