"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import * as React from "react";

import { Badge, type BadgeProps } from "@/components/ui/badge";
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
import type { LogAuditoria } from "@/lib/tipos";
import { dataHora, numero } from "@/lib/utils";

/**
 * Cores por ação — e o critério é "isto move dinheiro ou fala com o banco?".
 *
 * Numa investigação a pergunta nunca é "houve uma edição?". É "quem mandou a
 * remessa, e quando o retorno entrou?". Essas ações têm código próprio no
 * backend justamente para poderem ser encontradas, então aqui elas também
 * se destacam do ruído de criação e edição de cadastro.
 */
const TOM: Record<string, BadgeProps["tom"]> = {
  REMESSA_ENVIADA: "acento",
  REMESSA_GERADA: "acento",
  LOTE_CRIADO: "acento",
  INSTRUCAO_ENVIADA: "acento",
  RETORNO_PROCESSADO: "positivo",
  PAGAMENTO_MANUAL: "atencao",
  COBRANCA_CANCELADA: "negativo",
  COBRANCA_BAIXADA: "atencao",
  EXCLUSAO: "negativo",
  LOGIN_FALHA: "negativo",
  EXPORTACAO: "atencao",
  CRIACAO: "neutro",
  EDICAO: "neutro",
  LOGIN: "neutro",
  LOGOUT: "neutro",
};

const ACOES = [
  { valor: "", rotulo: "Todas as ações" },
  { valor: "REMESSA_ENVIADA", rotulo: "Remessa enviada ao banco" },
  { valor: "RETORNO_PROCESSADO", rotulo: "Retorno processado" },
  { valor: "LOTE_CRIADO", rotulo: "Lote criado" },
  { valor: "COBRANCA_CANCELADA", rotulo: "Cobrança cancelada" },
  { valor: "PAGAMENTO_MANUAL", rotulo: "Baixa manual" },
  { valor: "EXPORTACAO", rotulo: "Exportação de dados" },
  { valor: "LOGIN_FALHA", rotulo: "Falha de login" },
  { valor: "CRIACAO", rotulo: "Criação" },
  { valor: "EDICAO", rotulo: "Edição" },
  { valor: "EXCLUSAO", rotulo: "Exclusão" },
];

export default function PaginaAuditoria() {
  const [busca, setBusca] = React.useState("");
  const [acao, setAcao] = React.useState("");
  const [de, setDe] = React.useState("");
  const [ate, setAte] = React.useState("");
  const termo = useDebounce(busca);

  const lista = useLista<LogAuditoria>("/audit/", {
    search: termo || undefined,
    acao: acao || undefined,
    de: de || undefined,
    ate: ate || undefined,
  });

  return (
    <>
      <TituloPagina
        titulo="Auditoria"
        descricao="Quem fez o quê, quando e de onde. A trilha não se edita nem se apaga."
      />

      <Filtros>
        <Input
          className="min-w-52 flex-1"
          placeholder="Usuário, descrição, IP…"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
        <Selecao className="w-60" value={acao} onChange={(e) => setAcao(e.target.value)}>
          {ACOES.map((opcao) => (
            <option key={opcao.valor} value={opcao.valor}>
              {opcao.rotulo}
            </option>
          ))}
        </Selecao>
        <Input
          type="date"
          className="w-40"
          value={de}
          onChange={(e) => setDe(e.target.value)}
          aria-label="De"
        />
        <Input
          type="date"
          className="w-40"
          value={ate}
          onChange={(e) => setAte(e.target.value)}
          aria-label="Até"
        />
      </Filtros>

      <Secao titulo={`${numero(lista.total)} registros`}>
        <Tabela>
          <Cabecalho>
            <tr>
              <Th className="w-8" />
              <Th>Quando</Th>
              <Th>Quem</Th>
              <Th>O quê</Th>
              <Th>Sobre</Th>
              <Th>Origem</Th>
            </tr>
          </Cabecalho>
          <Corpo>
            {lista.carregando ? (
              <Esqueleto colunas={6} />
            ) : lista.dados.length === 0 ? (
              <Vazio
                colunas={6}
                titulo="Nenhum registro"
                descricao="Ajuste os filtros ou o período."
              />
            ) : (
              lista.dados.map((log) => <LinhaLog key={log.id} log={log} />)
            )}
          </Corpo>
        </Tabela>
        <Paginacao
          pagina={lista.pagina}
          paginas={lista.paginas}
          total={lista.total}
          aoMudar={lista.setPagina}
          rotulo="registros"
        />
      </Secao>
    </>
  );
}

function LinhaLog({ log }: { log: LogAuditoria }) {
  const [aberto, setAberto] = React.useState(false);
  const temDetalhe =
    Object.keys(log.alteracoes ?? {}).length > 0 ||
    Object.keys(log.metadados ?? {}).length > 0;

  return (
    <>
      <Linha clicavel={temDetalhe} onClick={() => temDetalhe && setAberto((v) => !v)}>
        <Td className="pr-0 text-texto-tenue">
          {temDetalhe &&
            (aberto ? (
              <ChevronDown className="size-3.5" />
            ) : (
              <ChevronRight className="size-3.5" />
            ))}
        </Td>
        <Td className="text-[13px] whitespace-nowrap text-texto-suave">
          {dataHora(log.criado_em)}
        </Td>
        <Td className="text-[13px]">{log.usuario_nome || "sistema"}</Td>
        <Td>
          <Badge tom={TOM[log.acao] ?? "neutro"}>
            {log.acao.charAt(0) + log.acao.slice(1).toLowerCase().replace(/_/g, " ")}
          </Badge>
        </Td>
        <Td className="text-[13px]">
          {log.objeto_descricao || log.descricao || "—"}
          {log.modulo && (
            <p className="text-[12px] text-texto-tenue">{log.modulo}</p>
          )}
        </Td>
        <Td className="text-[12.5px] text-texto-tenue tabular">{log.ip ?? "—"}</Td>
      </Linha>

      {aberto && (
        <tr>
          <td colSpan={6} className="bg-superficie-sutil px-4 py-3">
            {log.descricao && (
              <p className="mb-2 text-[13px]">{log.descricao}</p>
            )}
            {Object.keys(log.alteracoes ?? {}).length > 0 && (
              <Alteracoes alteracoes={log.alteracoes} />
            )}
            {Object.keys(log.metadados ?? {}).length > 0 && (
              <pre className="mt-2 overflow-x-auto rounded-lg border border-borda bg-superficie p-3 text-[12px]">
                {JSON.stringify(log.metadados, null, 2)}
              </pre>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

/**
 * O "de → para" de cada campo.
 *
 * O backend grava a criação como `{criado: {...}}` e a edição como
 * `{campo: {de, para}}`. As duas formas caem aqui, e a de edição é a que
 * importa numa investigação: mostrar só o valor final não responde "o que
 * mudou".
 */
function Alteracoes({ alteracoes }: { alteracoes: Record<string, unknown> }) {
  const entradas = Object.entries(alteracoes);

  if (entradas.length === 1 && (entradas[0][0] === "criado" || entradas[0][0] === "removido")) {
    return (
      <pre className="overflow-x-auto rounded-lg border border-borda bg-superficie p-3 text-[12px]">
        {JSON.stringify(entradas[0][1], null, 2)}
      </pre>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-borda bg-superficie">
      <table className="w-full text-[12.5px]">
        <tbody className="divide-y divide-borda">
          {entradas.map(([campo, valor]) => {
            const mudanca = valor as { de?: unknown; para?: unknown };
            return (
              <tr key={campo}>
                <td className="w-40 px-3 py-2 font-medium">{campo}</td>
                <td className="px-3 py-2 text-negativo line-through">
                  {formatar(mudanca?.de)}
                </td>
                <td className="px-3 py-2 text-positivo">{formatar(mudanca?.para)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function formatar(valor: unknown): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  if (typeof valor === "object") return JSON.stringify(valor);
  return String(valor);
}
