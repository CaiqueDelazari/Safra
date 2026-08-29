"use client";

import { AlertTriangle, CheckCircle2, Send } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Botao } from "@/components/ui/button";
import { Campo, Selecao } from "@/components/ui/campos";
import { Dialogo, DialogoConteudo } from "@/components/ui/dialogo";
import { acompanharTarefa, api, ApiError } from "@/lib/api";
import type { ContaBancaria, Lote } from "@/lib/tipos";
import { moeda, numero } from "@/lib/utils";

interface Recusada {
  id: number;
  numero: number | null;
  cliente: string;
  motivo: string;
}

interface Validacao {
  aptas: number;
  recusadas: Recusada[];
  valor_total: string;
}

/**
 * O passo que evita a descoberta tardia.
 *
 * Gerar um lote consome números da faixa contratada com o banco — números que
 * não voltam. Descobrir depois que 40 dos 500 títulos estavam com o cadastro
 * incompleto significa 40 números queimados e um segundo lote para fazer.
 *
 * Por isso o diálogo valida **antes** de criar: mostra quantos entram, quantos
 * ficam de fora e por quê. Só então o botão de gerar aparece.
 */
export function DialogoGerarLote({
  cobrancas,
  contas,
  aberto,
  aoFechar,
  aoConcluir,
}: {
  cobrancas: number[];
  contas: ContaBancaria[];
  aberto: boolean;
  aoFechar: () => void;
  aoConcluir?: () => void;
}) {
  const router = useRouter();
  const [contaId, setContaId] = React.useState<number | null>(null);
  const [validacao, setValidacao] = React.useState<Validacao | null>(null);
  const [validando, setValidando] = React.useState(false);
  const [gerando, setGerando] = React.useState(false);
  const [progresso, setProgresso] = React.useState(0);
  const [etapa, setEtapa] = React.useState("");

  const contasUsaveis = React.useMemo(
    () => contas.filter((c) => c.ativa && c.integrada),
    [contas],
  );

  React.useEffect(() => {
    if (!aberto) return;
    // A abertura inicia uma nova operação de lote.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setValidacao(null);
    setProgresso(0);
    setEtapa("");
    setContaId(
      (atual) =>
        atual ??
        contasUsaveis.find((c) => c.padrao)?.id ??
        contasUsaveis[0]?.id ??
        null,
    );
  }, [aberto, contasUsaveis]);

  // Valida sempre que a conta ou a seleção mudarem: a mesma seleção pode ser
  // aceitável numa conta e recusada em outra.
  React.useEffect(() => {
    if (!aberto || !contaId || cobrancas.length === 0) return;
    let ativo = true;
    // Estado da requisição iniciada por esta sincronização.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setValidando(true);
    api
      .post<Validacao>("/batches/validate/", {
        conta_bancaria: contaId,
        cobrancas,
      })
      .then((resposta) => ativo && setValidacao(resposta))
      .catch((erro) => {
        if (!ativo) return;
        toast.error(erro instanceof ApiError ? erro.detalhe : "Falha ao validar.");
      })
      .finally(() => ativo && setValidando(false));
    return () => {
      ativo = false;
    };
  }, [aberto, contaId, cobrancas]);

  async function gerar(enviar: boolean) {
    if (!contaId) return;
    setGerando(true);
    setProgresso(0);
    try {
      const lote = await api.post<Lote & { tarefa_id: string }>("/batches/", {
        conta_bancaria: contaId,
        cobrancas,
        enviar,
      });

      setEtapa(`Lote #${lote.numero} criado. Montando o arquivo…`);

      // A API responde em milissegundos e o worker monta o arquivo. Acompanhar
      // aqui é o que transforma "clicou e não aconteceu nada" em progresso.
      const fim = await acompanharTarefa(lote.tarefa_id, (pct) => setProgresso(pct));

      if (fim.estado === "SUCCESS") {
        toast.success(`Lote #${lote.numero} pronto.`, {
          description: enviar
            ? "Arquivo montado e enviado ao banco."
            : "Arquivo de remessa disponível para download.",
        });
      } else {
        toast.warning(`Lote #${lote.numero} criado, mas a montagem não terminou.`, {
          description: fim.erro ?? "Abra o lote para ver o que aconteceu.",
        });
      }

      aoConcluir?.();
      aoFechar();
      router.push(`/lotes/${lote.id}`);
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha ao gerar o lote.");
    } finally {
      setGerando(false);
    }
  }

  const semConta = contasUsaveis.length === 0;

  return (
    <Dialogo open={aberto} onOpenChange={(v) => !v && aoFechar()}>
      <DialogoConteudo
        titulo={`Gerar lote com ${numero(cobrancas.length)} ${
          cobrancas.length === 1 ? "cobrança" : "cobranças"
        }`}
        descricao="O sistema confere cada título antes de reservar a numeração do banco."
        largura="max-w-2xl"
        rodape={
          <>
            <Botao variante="contorno" onClick={aoFechar} disabled={gerando}>
              Cancelar
            </Botao>
            <Botao
              variante="contorno"
              onClick={() => gerar(false)}
              disabled={semConta || !validacao?.aptas || gerando}
              carregando={gerando}
            >
              Gerar arquivo
            </Botao>
            <Botao
              onClick={() => gerar(true)}
              disabled={semConta || !validacao?.aptas || gerando}
              carregando={gerando}
            >
              <Send /> Gerar e enviar
            </Botao>
          </>
        }
      >
        {semConta ? (
          <p className="rounded-lg border border-atencao/30 bg-atencao-suave px-4 py-3 text-[13.5px]">
            Nenhuma conta bancária ativa com integração disponível. Cadastre uma
            em <strong>Contas bancárias</strong> antes de gerar o lote.
          </p>
        ) : (
          <div className="space-y-5">
            <Campo
              rotulo="Conta bancária"
              obrigatorio
              dica="Define o convênio, a numeração dos títulos e para onde o dinheiro entra."
            >
              <Selecao
                value={contaId ?? ""}
                onChange={(e) => setContaId(Number(e.target.value))}
              >
                {contasUsaveis.map((conta) => (
                  <option key={conta.id} value={conta.id}>
                    {conta.nome} — {conta.banco_label} · {conta.agencia_conta}
                    {conta.producao ? "" : " (homologação)"}
                  </option>
                ))}
              </Selecao>
            </Campo>

            {contasUsaveis.find((c) => c.id === contaId && !c.producao) && (
              <p className="rounded-lg border border-atencao/30 bg-atencao-suave px-3.5 py-2.5 text-[12.5px]">
                Esta conta aponta para o ambiente de <strong>homologação</strong>.
                Os títulos não serão registrados de verdade.
              </p>
            )}

            {validando ? (
              <div className="carregando h-24 rounded-lg bg-neutro-suave" />
            ) : validacao ? (
              <Resumo validacao={validacao} />
            ) : null}

            {gerando && (
              <div>
                <div className="mb-1.5 flex items-center justify-between text-[12.5px] text-texto-suave">
                  <span>{etapa || "Processando…"}</span>
                  <span className="tabular">{progresso}%</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-neutro-suave">
                  <div
                    className="h-full rounded-full bg-acento transition-[width] duration-300"
                    style={{ width: `${Math.max(progresso, 4)}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </DialogoConteudo>
    </Dialogo>
  );
}

function Resumo({ validacao }: { validacao: Validacao }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 rounded-lg border border-borda bg-superficie-sutil px-4 py-3">
        <CheckCircle2 className="size-5 shrink-0 text-positivo" />
        <div>
          <p className="text-[13.5px] font-medium">
            {numero(validacao.aptas)}{" "}
            {validacao.aptas === 1 ? "título entra" : "títulos entram"} no lote
          </p>
          <p className="text-[12.5px] text-texto-suave">
            Total de {moeda(validacao.valor_total)}
          </p>
        </div>
      </div>

      {validacao.recusadas.length > 0 && (
        <div className="rounded-lg border border-atencao/30 bg-atencao-suave">
          <div className="flex items-center gap-2.5 px-4 py-3">
            <AlertTriangle className="size-4.5 shrink-0 text-atencao" />
            <p className="text-[13px] font-medium">
              {numero(validacao.recusadas.length)}{" "}
              {validacao.recusadas.length === 1
                ? "ficará de fora"
                : "ficarão de fora"}
            </p>
          </div>
          <ul className="max-h-52 overflow-y-auto border-t border-atencao/20 px-4 py-2.5 text-[12.5px]">
            {validacao.recusadas.map((linha) => (
              <li key={linha.id} className="py-1">
                <span className="font-medium">
                  {linha.numero ? `#${linha.numero}` : `id ${linha.id}`}
                </span>
                {linha.cliente && (
                  <span className="text-texto-suave"> · {linha.cliente}</span>
                )}
                <span className="text-texto-suave"> — {linha.motivo}</span>
              </li>
            ))}
          </ul>
          <p className="border-t border-atencao/20 px-4 py-2.5 text-[12px] text-texto-suave">
            Elas continuam disponíveis: corrija o cadastro e gere um novo lote.
          </p>
        </div>
      )}
    </div>
  );
}
