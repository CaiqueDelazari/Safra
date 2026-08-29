"use client";

import { Download, RefreshCw, Upload } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { StatusArquivoBadge } from "@/components/cobrancas/status";
import { Botao } from "@/components/ui/button";
import { Campo, Selecao } from "@/components/ui/campos";
import { Dialogo, DialogoConteudo } from "@/components/ui/dialogo";
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
import { acompanharTarefa, api, ApiError } from "@/lib/api";
import { useLista, useRecurso } from "@/lib/hooks";
import type { ArquivoBancario, ContaBancaria, Pagina } from "@/lib/tipos";
import { data, dataHora, moeda, numero } from "@/lib/utils";
import { useSessao } from "@/providers/sessao";

export default function PaginaRetornos() {
  const { podeCapacidade } = useSessao();
  const lista = useLista<ArquivoBancario>("/bank/files/", { tipo: "RETORNO" });
  const [envioAberto, setEnvioAberto] = React.useState(false);
  const [reprocessando, setReprocessando] = React.useState<number | null>(null);

  async function reprocessar(arquivo: ArquivoBancario) {
    setReprocessando(arquivo.id);
    try {
      const resposta = await api.post<{ tarefa_id: string }>(
        `/bank/files/${arquivo.id}/reprocess/`,
      );
      await acompanharTarefa(resposta.tarefa_id);
      toast.success("Arquivo reprocessado.", {
        description: "Nenhum pagamento é duplicado: o sistema reconhece o que já aplicou.",
      });
      lista.recarregar();
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha ao reprocessar.");
    } finally {
      setReprocessando(null);
    }
  }

  return (
    <>
      <TituloPagina
        titulo="Retornos bancários"
        descricao="O arquivo do banco entra aqui e baixa os títulos pagos automaticamente."
        acoes={
          podeCapacidade("processar_retorno") ? (
            <Botao onClick={() => setEnvioAberto(true)}>
              <Upload /> Enviar retorno
            </Botao>
          ) : null
        }
      />

      <Secao titulo={`${numero(lista.total)} arquivos`}>
        <Tabela>
          <Cabecalho>
            <tr>
              <Th>Arquivo</Th>
              <Th>Movimento</Th>
              <Th>Registros</Th>
              <Th>Situação</Th>
              <Th className="text-right">Valor</Th>
              <Th className="w-24" />
            </tr>
          </Cabecalho>
          <Corpo>
            {lista.carregando ? (
              <Esqueleto colunas={6} />
            ) : lista.dados.length === 0 ? (
              <Vazio
                colunas={6}
                titulo="Nenhum retorno recebido"
                descricao="Envie o arquivo que o banco disponibiliza, ou configure o SFTP na conta bancária para que ele entre sozinho."
              />
            ) : (
              lista.dados.map((arquivo) => (
                <Linha key={arquivo.id}>
                  <Td>
                    <p className="font-medium">{arquivo.nome_original}</p>
                    <p className="text-[12.5px] text-texto-tenue">
                      {arquivo.conta_nome ?? arquivo.banco_label} ·{" "}
                      {dataHora(arquivo.recebido_em)} · via {arquivo.origem.toLowerCase()}
                    </p>
                  </Td>
                  <Td className="text-[13px] text-texto-suave">
                    {data(arquivo.data_movimento)}
                  </Td>
                  <Td className="text-[13px] tabular">
                    {numero(arquivo.quantidade_processada)} de{" "}
                    {numero(arquivo.quantidade_registros)}
                    {arquivo.quantidade_com_erro > 0 && (
                      <span className="ml-1.5 text-[12px] text-atencao">
                        {arquivo.quantidade_com_erro} pendentes
                      </span>
                    )}
                  </Td>
                  <Td>
                    <StatusArquivoBadge
                      status={arquivo.status}
                      rotulo={arquivo.status_label}
                    />
                    {arquivo.mensagem_erro && (
                      <p
                        className="mt-1 max-w-72 truncate text-[12px] text-texto-suave"
                        title={arquivo.mensagem_erro}
                      >
                        {arquivo.mensagem_erro}
                      </p>
                    )}
                  </Td>
                  <Td className="text-right font-medium tabular">
                    {moeda(arquivo.valor_total)}
                  </Td>
                  <Td>
                    <div className="flex justify-end gap-1">
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
                      {podeCapacidade("processar_retorno") && (
                        <Botao
                          variante="fantasma"
                          tamanho="icone-sm"
                          onClick={() => reprocessar(arquivo)}
                          carregando={reprocessando === arquivo.id}
                          title="Reprocessar — seguro, não duplica pagamento"
                          aria-label="Reprocessar"
                        >
                          <RefreshCw />
                        </Botao>
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
          rotulo="arquivos"
        />
      </Secao>

      <DialogoEnviarRetorno
        aberto={envioAberto}
        aoFechar={() => setEnvioAberto(false)}
        aoConcluir={lista.recarregar}
      />
    </>
  );
}

function DialogoEnviarRetorno({
  aberto,
  aoFechar,
  aoConcluir,
}: {
  aberto: boolean;
  aoFechar: () => void;
  aoConcluir: () => void;
}) {
  const { dados: contas } = useRecurso<Pagina<ContaBancaria>>("/bank/accounts/");
  const [arquivo, setArquivo] = React.useState<File | null>(null);
  const [contaId, setContaId] = React.useState("");
  const [enviando, setEnviando] = React.useState(false);

  async function enviar() {
    if (!arquivo) return;
    setEnviando(true);
    try {
      const corpo = new FormData();
      corpo.append("arquivo", arquivo);
      if (contaId) corpo.append("conta_bancaria", contaId);

      const resposta = await api.upload<
        ArquivoBancario & { tarefa_id?: string; ja_processado: boolean; mensagem: string }
      >("/bank/files/returns/process/", corpo);

      if (resposta.ja_processado) {
        // Não é erro, e a mensagem precisa deixar isso claro: o operador subiu
        // de novo porque não teve certeza, e a resposta certa é tranquilizá-lo.
        toast.info("Este arquivo já havia sido processado.", {
          description: "Nada foi duplicado — o sistema reconhece pelo conteúdo.",
        });
      } else {
        if (resposta.tarefa_id) await acompanharTarefa(resposta.tarefa_id);
        toast.success("Retorno processado.", {
          description: "As cobranças pagas já estão atualizadas.",
        });
      }
      aoConcluir();
      aoFechar();
      setArquivo(null);
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha ao enviar.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Dialogo open={aberto} onOpenChange={(v) => !v && aoFechar()}>
      <DialogoConteudo
        titulo="Enviar arquivo de retorno"
        descricao="O arquivo que o banco disponibiliza (.RET, .TXT). O sistema lê tudo de uma vez."
        rodape={
          <>
            <Botao variante="contorno" onClick={aoFechar} disabled={enviando}>
              Cancelar
            </Botao>
            <Botao onClick={enviar} disabled={!arquivo} carregando={enviando}>
              <Upload /> Processar
            </Botao>
          </>
        }
      >
        <div className="space-y-4">
          <Campo
            rotulo="Arquivo"
            obrigatorio
            dica="Subir o mesmo arquivo duas vezes é seguro: nada é duplicado."
          >
            <input
              type="file"
              accept=".ret,.txt,.crt,.rem"
              onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
              className="w-full rounded-lg border border-borda bg-superficie px-3 py-2 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-neutro-suave file:px-3 file:py-1.5 file:text-[13px]"
            />
          </Campo>

          <Campo
            rotulo="Conta bancária"
            dica="Deixe em branco se a empresa tem uma só conta naquele banco — o sistema identifica sozinho."
          >
            <Selecao value={contaId} onChange={(e) => setContaId(e.target.value)}>
              <option value="">Identificar automaticamente</option>
              {(contas?.resultados ?? []).map((conta) => (
                <option key={conta.id} value={conta.id}>
                  {conta.nome} — {conta.banco_label}
                </option>
              ))}
            </Selecao>
          </Campo>
        </div>
      </DialogoConteudo>
    </Dialogo>
  );
}
