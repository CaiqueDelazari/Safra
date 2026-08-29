"use client";

import { Download, Upload } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Botao } from "@/components/ui/button";
import { Campo } from "@/components/ui/campos";
import { Dialogo, DialogoConteudo } from "@/components/ui/dialogo";
import { acompanharTarefa, api, ApiError } from "@/lib/api";
import { numero } from "@/lib/utils";

interface ErroLinha {
  linha: number;
  erro: string;
  nome?: string;
  documento?: string;
}

interface Resultado {
  criados: number;
  atualizados: number;
  ignorados: number;
  erros: ErroLinha[];
  total: number;
  colunas_reconhecidas: Record<string, string>;
  colunas_ignoradas: string[];
}

/**
 * Importação de carteira.
 *
 * Uma planilha nunca vem limpa. A escolha aqui é importar o que dá e devolver
 * o relatório do resto com o número da linha — recusar o arquivo inteiro por
 * três CPFs errados é o que faz alguém desistir do sistema no primeiro dia.
 *
 * Reenviar a planilha corrigida é seguro: quem já entrou é reconhecido pelo
 * documento e atualizado, não duplicado.
 */
export function ImportarClientes({
  aberto,
  aoFechar,
  aoConcluir,
}: {
  aberto: boolean;
  aoFechar: () => void;
  aoConcluir: () => void;
}) {
  const [arquivo, setArquivo] = React.useState<File | null>(null);
  const [atualizar, setAtualizar] = React.useState(true);
  const [enviando, setEnviando] = React.useState(false);
  const [progresso, setProgresso] = React.useState(0);
  const [resultado, setResultado] = React.useState<Resultado | null>(null);

  function reiniciar() {
    setArquivo(null);
    setResultado(null);
    setProgresso(0);
  }

  async function enviar() {
    if (!arquivo) return;
    setEnviando(true);
    setResultado(null);
    try {
      const corpo = new FormData();
      corpo.append("arquivo", arquivo);
      corpo.append("atualizar_existentes", String(atualizar));

      const inicio = await api.upload<{
        tarefa_id: string;
        linhas: number;
        colunas_reconhecidas: Record<string, string>;
        colunas_ignoradas: string[];
      }>("/clients/import/", corpo);

      const fim = await acompanharTarefa(inicio.tarefa_id, (pct) => setProgresso(pct));

      if (fim.estado === "SUCCESS") {
        const dados = fim.resultado as Resultado;
        setResultado(dados);
        toast.success(
          `${numero(dados.criados)} criados, ${numero(dados.atualizados)} atualizados.`,
        );
        aoConcluir();
      } else {
        toast.error(fim.erro ?? "A importação não terminou.");
      }
    } catch (erro) {
      if (erro instanceof ApiError && erro.corpo) {
        const corpo = erro.corpo as { faltando?: string[]; detail?: string };
        toast.error(corpo.detail ?? erro.detalhe, {
          description: corpo.faltando
            ? `Colunas obrigatórias ausentes: ${corpo.faltando.join(", ")}`
            : undefined,
        });
      } else {
        toast.error("Falha ao importar.");
      }
    } finally {
      setEnviando(false);
    }
  }

  function baixarModelo() {
    const csv =
      "nome;cpf_cnpj;email;telefone;cep;logradouro;numero;bairro;cidade;uf\n" +
      "Empresa Exemplo LTDA;12345678000195;contato@exemplo.com.br;1133334444;" +
      "01310100;Avenida Paulista;1000;Bela Vista;São Paulo;SP\n";
    const url = URL.createObjectURL(
      new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "modelo-clientes.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Dialogo
      open={aberto}
      onOpenChange={(v) => {
        if (!v) {
          aoFechar();
          reiniciar();
        }
      }}
    >
      <DialogoConteudo
        titulo="Importar clientes"
        descricao="CSV ou Excel. O sistema reconhece os cabeçalhos mais comuns sozinho."
        largura="max-w-2xl"
        rodape={
          resultado ? (
            <Botao
              onClick={() => {
                aoFechar();
                reiniciar();
              }}
            >
              Fechar
            </Botao>
          ) : (
            <>
              <Botao variante="contorno" onClick={baixarModelo}>
                <Download /> Modelo
              </Botao>
              <Botao onClick={enviar} disabled={!arquivo} carregando={enviando}>
                <Upload /> Importar
              </Botao>
            </>
          )
        }
      >
        {resultado ? (
          <RelatorioImportacao resultado={resultado} />
        ) : (
          <div className="space-y-4">
            <Campo
              rotulo="Planilha"
              obrigatorio
              dica="Colunas obrigatórias: nome e CPF/CNPJ. As demais são opcionais — mas sem endereço o banco recusa o boleto."
            >
              <input
                type="file"
                accept=".csv,.xlsx,.xls,.txt"
                onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
                className="w-full rounded-lg border border-borda bg-superficie px-3 py-2 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-neutro-suave file:px-3 file:py-1.5 file:text-[13px]"
              />
            </Campo>

            <label className="flex cursor-pointer items-start gap-2.5">
              <input
                type="checkbox"
                checked={atualizar}
                onChange={(e) => setAtualizar(e.target.checked)}
                className="mt-0.5 size-4 accent-[var(--acento)]"
              />
              <span className="text-[13px]">
                Atualizar quem já está cadastrado
                <span className="block text-[12px] text-texto-tenue">
                  Só sobrescreve o que vier preenchido na planilha — colunas
                  ausentes não apagam o que já existe.
                </span>
              </span>
            </label>

            {enviando && (
              <div>
                <div className="mb-1.5 flex justify-between text-[12.5px] text-texto-suave">
                  <span>Gravando…</span>
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

function RelatorioImportacao({ resultado }: { resultado: Resultado }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Numero rotulo="Criados" valor={resultado.criados} tom="text-positivo" />
        <Numero rotulo="Atualizados" valor={resultado.atualizados} />
        <Numero
          rotulo="Com erro"
          valor={resultado.erros.length}
          tom={resultado.erros.length ? "text-negativo" : undefined}
        />
      </div>

      {resultado.colunas_ignoradas.length > 0 && (
        <p className="rounded-lg border border-borda bg-superficie-sutil px-3.5 py-2.5 text-[12.5px] text-texto-suave">
          Colunas que o sistema não reconheceu e ignorou:{" "}
          {resultado.colunas_ignoradas.join(", ")}.
        </p>
      )}

      {resultado.erros.length > 0 && (
        <div className="rounded-lg border border-negativo/25 bg-negativo-suave">
          <p className="px-4 py-2.5 text-[13px] font-medium">
            Linhas que ficaram de fora
          </p>
          <ul className="max-h-64 overflow-y-auto border-t border-negativo/20 px-4 py-2 text-[12.5px]">
            {resultado.erros.map((erro, i) => (
              <li key={i} className="py-1">
                <span className="font-medium">linha {erro.linha}</span>
                {erro.nome && <span className="text-texto-suave"> · {erro.nome}</span>}
                <span className="text-texto-suave"> — {erro.erro}</span>
              </li>
            ))}
          </ul>
          <p className="border-t border-negativo/20 px-4 py-2.5 text-[12px] text-texto-suave">
            Corrija na planilha e importe de novo: quem já entrou é reconhecido
            pelo documento, não duplicado.
          </p>
        </div>
      )}
    </div>
  );
}

function Numero({
  rotulo,
  valor,
  tom,
}: {
  rotulo: string;
  valor: number;
  tom?: string;
}) {
  return (
    <div className="rounded-lg border border-borda bg-superficie px-4 py-3">
      <p className="text-[12px] text-texto-tenue">{rotulo}</p>
      <p className={`mt-1 text-[22px] leading-none font-semibold tabular ${tom ?? ""}`}>
        {numero(valor)}
      </p>
    </div>
  );
}
