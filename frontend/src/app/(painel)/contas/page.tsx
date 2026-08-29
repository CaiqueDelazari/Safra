"use client";

import { KeyRound, Pencil, Plus, ShieldCheck, TriangleAlert } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Botao } from "@/components/ui/button";
import { AreaTexto, Campo, Input, Selecao } from "@/components/ui/campos";
import { Dialogo, DialogoConteudo } from "@/components/ui/dialogo";
import { Secao, TituloPagina } from "@/components/ui/pagina";
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
import { api, ApiError } from "@/lib/api";
import { useLista } from "@/lib/hooks";
import type { ContaBancaria } from "@/lib/tipos";
import { numero } from "@/lib/utils";
import { useSessao } from "@/providers/sessao";

export default function PaginaContas() {
  const { podeCapacidade } = useSessao();
  const lista = useLista<ContaBancaria>("/bank/accounts/");
  const [editando, setEditando] = React.useState<ContaBancaria | null>(null);
  const [criando, setCriando] = React.useState(false);

  const podeAdministrar = podeCapacidade("administrar_integracao_bancaria");

  return (
    <>
      <TituloPagina
        titulo="Contas bancárias"
        descricao="O convênio de cobrança. É ele que define a numeração dos títulos e para onde o dinheiro entra."
        acoes={
          podeAdministrar ? (
            <Botao onClick={() => setCriando(true)}>
              <Plus /> Nova conta
            </Botao>
          ) : null
        }
      />

      <Secao titulo={`${numero(lista.total)} contas`}>
        <Tabela>
          <Cabecalho>
            <tr>
              <Th>Conta</Th>
              <Th>Agência / conta</Th>
              <Th>Numeração</Th>
              <Th>Integração</Th>
              <Th className="w-16" />
            </tr>
          </Cabecalho>
          <Corpo>
            {lista.carregando ? (
              <Esqueleto colunas={5} />
            ) : lista.dados.length === 0 ? (
              <Vazio
                colunas={5}
                titulo="Nenhuma conta bancária"
                descricao="Sem uma conta não há como registrar título nenhum."
                acao={
                  podeAdministrar ? (
                    <Botao onClick={() => setCriando(true)}>
                      <Plus /> Cadastrar conta
                    </Botao>
                  ) : undefined
                }
              />
            ) : (
              lista.dados.map((conta) => (
                <Linha key={conta.id}>
                  <Td>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{conta.nome}</span>
                      {conta.padrao && <Badge tom="acento">padrão</Badge>}
                      {!conta.ativa && <Badge tom="neutro">inativa</Badge>}
                      {/* Homologação é a informação mais importante da linha:
                          nela, nenhum título é registrado de verdade. */}
                      {!conta.producao && (
                        <Badge tom="atencao" ponto>
                          homologação
                        </Badge>
                      )}
                    </div>
                    <p className="text-[12.5px] text-texto-tenue">
                      {conta.banco_label} · carteira {conta.carteira}
                    </p>
                  </Td>
                  <Td className="text-[13px] tabular">{conta.agencia_conta}</Td>
                  <Td className="text-[13px]">
                    <FaixaNumeracao conta={conta} />
                  </Td>
                  <Td>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tom="neutro">{conta.meio_integracao}</Badge>
                      {conta.transmissao_automatica ? (
                        <Badge tom="positivo">
                          <ShieldCheck className="size-3" /> automática
                        </Badge>
                      ) : (
                        <Badge tom="contorno" title="A remessa fica para download">
                          manual
                        </Badge>
                      )}
                    </div>
                  </Td>
                  <Td>
                    {podeAdministrar && (
                      <Botao
                        variante="fantasma"
                        tamanho="icone-sm"
                        onClick={() => setEditando(conta)}
                        aria-label="Editar conta"
                      >
                        <Pencil />
                      </Botao>
                    )}
                  </Td>
                </Linha>
              ))
            )}
          </Corpo>
        </Tabela>
      </Secao>

      <FormularioConta
        conta={editando}
        aberto={criando || editando !== null}
        aoFechar={() => {
          setCriando(false);
          setEditando(null);
        }}
        aoSalvar={lista.recarregar}
      />
    </>
  );
}

/**
 * A faixa de "nosso número" é finita e contratada com o banco. Quando ela
 * acaba, a remessa passa a ser recusada — e o aviso precisa chegar antes,
 * não no dia.
 */
function FaixaNumeracao({ conta }: { conta: ContaBancaria }) {
  const restante = conta.nosso_numero_maximo - conta.proximo_nosso_numero;
  const acabando = restante < 1000;

  return (
    <div>
      <span className="tabular">{numero(conta.proximo_nosso_numero)}</span>
      <p
        className={`text-[12px] ${acabando ? "font-medium text-negativo" : "text-texto-tenue"}`}
      >
        {acabando && <TriangleAlert className="mr-1 inline size-3" />}
        {numero(restante)} restantes
      </p>
    </div>
  );
}

const VAZIA = {
  nome: "",
  banco: "422",
  meio_integracao: "CNAB400",
  agencia: "",
  agencia_dv: "",
  conta: "",
  conta_dv: "",
  carteira: "1",
  codigo_cedente: "",
  especie_titulo: "DS",
  nosso_numero_maximo: 99999999,
  dias_protesto: 0,
  juros_mes_percentual: "0",
  multa_percentual: "0",
  instrucoes_boleto: "",
  sftp_host: "",
  sftp_porta: 22,
  sftp_usuario: "",
  sftp_senha: "",
  api_client_id: "",
  api_client_secret: "",
  api_certificado: "",
  api_chave_privada: "",
  producao: false,
  ativa: true,
  padrao: false,
};

function FormularioConta({
  conta,
  aberto,
  aoFechar,
  aoSalvar,
}: {
  conta: ContaBancaria | null;
  aberto: boolean;
  aoFechar: () => void;
  aoSalvar: () => void;
}) {
  const [form, setForm] = React.useState<Record<string, unknown>>(VAZIA);
  const [salvando, setSalvando] = React.useState(false);

  React.useEffect(() => {
    if (!aberto) return;
    // Cada abertura precisa nascer dos dados atuais e com os segredos vazios;
    // manter o estado anterior poderia enviar a chave de outra conta.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setForm(conta ? { ...VAZIA, ...conta } : VAZIA);
  }, [aberto, conta]);

  function definir(campo: string, valor: unknown) {
    setForm((atual) => ({ ...atual, [campo]: valor }));
  }

  async function salvar() {
    setSalvando(true);
    try {
      if (conta) await api.patch(`/bank/accounts/${conta.id}/`, form);
      else await api.post("/bank/accounts/", form);
      toast.success(conta ? "Conta atualizada." : "Conta cadastrada.");
      aoSalvar();
      aoFechar();
    } catch (erro) {
      toast.error(erro instanceof ApiError ? erro.detalhe : "Falha ao salvar.");
    } finally {
      setSalvando(false);
    }
  }

  const usaApi = form.meio_integracao === "API";

  return (
    <Dialogo open={aberto} onOpenChange={(v) => !v && aoFechar()}>
      <DialogoConteudo
        titulo={conta ? `Editar ${conta.nome}` : "Nova conta bancária"}
        descricao="Os dados vêm do contrato de cobrança. Confirme carteira e código do cedente com o gerente."
        largura="max-w-3xl"
        rodape={
          <>
            <Botao variante="contorno" onClick={aoFechar} disabled={salvando}>
              Cancelar
            </Botao>
            <Botao onClick={salvar} carregando={salvando}>
              Salvar
            </Botao>
          </>
        }
      >
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo rotulo="Nome da conta" obrigatorio>
              <Input
                value={String(form.nome ?? "")}
                onChange={(e) => definir("nome", e.target.value)}
                placeholder="Safra — Matriz"
              />
            </Campo>
            <Campo rotulo="Banco" obrigatorio>
              <Selecao
                value={String(form.banco ?? "")}
                onChange={(e) => definir("banco", e.target.value)}
              >
                <option value="422">422 — Banco Safra</option>
              </Selecao>
            </Campo>
          </div>

          <div className="grid gap-4 sm:grid-cols-4">
            <Campo rotulo="Agência" obrigatorio>
              <Input
                value={String(form.agencia ?? "")}
                onChange={(e) => definir("agencia", e.target.value)}
              />
            </Campo>
            <Campo rotulo="Dígito">
              <Input
                maxLength={1}
                value={String(form.agencia_dv ?? "")}
                onChange={(e) => definir("agencia_dv", e.target.value)}
              />
            </Campo>
            <Campo rotulo="Conta" obrigatorio>
              <Input
                value={String(form.conta ?? "")}
                onChange={(e) => definir("conta", e.target.value)}
              />
            </Campo>
            <Campo rotulo="Dígito">
              <Input
                maxLength={1}
                value={String(form.conta_dv ?? "")}
                onChange={(e) => definir("conta_dv", e.target.value)}
              />
            </Campo>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <Campo rotulo="Carteira" obrigatorio dica="Definida no contrato.">
              <Input
                value={String(form.carteira ?? "")}
                onChange={(e) => definir("carteira", e.target.value)}
              />
            </Campo>
            <Campo
              rotulo="Código do cedente"
              dica="O banco fornece na abertura. Sem ele o sistema deduz — e deduzir falha em silêncio."
              className="sm:col-span-2"
            >
              <Input
                value={String(form.codigo_cedente ?? "")}
                onChange={(e) => definir("codigo_cedente", e.target.value)}
              />
            </Campo>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <Campo rotulo="Espécie do título">
              <Selecao
                value={String(form.especie_titulo ?? "")}
                onChange={(e) => definir("especie_titulo", e.target.value)}
              >
                <option value="DS">DS — Duplicata de serviço</option>
                <option value="DM">DM — Duplicata mercantil</option>
                <option value="ME">ME — Mensalidade escolar</option>
                <option value="RC">RC — Recibo</option>
                <option value="OU">OU — Outros</option>
              </Selecao>
            </Campo>
            <Campo rotulo="Juros ao mês (%)">
              <Input
                type="number"
                step="0.01"
                value={String(form.juros_mes_percentual ?? "0")}
                onChange={(e) => definir("juros_mes_percentual", e.target.value)}
              />
            </Campo>
            <Campo rotulo="Multa (%)">
              <Input
                type="number"
                step="0.01"
                value={String(form.multa_percentual ?? "0")}
                onChange={(e) => definir("multa_percentual", e.target.value)}
              />
            </Campo>
          </div>

          <Campo
            rotulo="Meio de integração"
            dica="CNAB 400 gera o arquivo de remessa. API registra título a título — exige credencial do banco."
          >
            <Selecao
              value={String(form.meio_integracao ?? "")}
              onChange={(e) => definir("meio_integracao", e.target.value)}
            >
              <option value="CNAB400">Arquivo CNAB 400</option>
              <option value="API">API REST</option>
            </Selecao>
          </Campo>

          <fieldset className="rounded-lg border border-borda p-4">
            <legend className="flex items-center gap-1.5 px-1.5 text-[12.5px] font-medium text-texto-suave">
              <KeyRound className="size-3.5" /> Credenciais
            </legend>
            <p className="mb-3 text-[12px] text-texto-tenue">
              Guardadas cifradas no banco de dados e nunca devolvidas pela API.
              Deixar em branco ao editar mantém o que já está gravado.
            </p>

            {usaApi ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <Campo
                  rotulo="Identificador da API (client_id)"
                  dica="Fornecido pelo Safra ao habilitar a API de cobrança."
                >
                  <Input
                    type="password"
                    autoComplete="off"
                    placeholder={conta?.api_configurada ? "•••• já cadastrado" : ""}
                    value={String(form.api_client_id ?? "")}
                    onChange={(e) => definir("api_client_id", e.target.value)}
                  />
                </Campo>
                <Campo
                  rotulo="Chave da API (client_secret)"
                  dica="É a key secreta da integração; nunca volta da nossa API."
                >
                  <Input
                    type="password"
                    autoComplete="off"
                    placeholder={conta?.api_configurada ? "•••• já cadastrado" : ""}
                    value={String(form.api_client_secret ?? "")}
                    onChange={(e) => definir("api_client_secret", e.target.value)}
                  />
                </Campo>
                <Campo
                  rotulo="Certificado mTLS (PEM)"
                  dica="Cole o conteúdo completo, incluindo BEGIN CERTIFICATE."
                  className="sm:col-span-2"
                >
                  <AreaTexto
                    spellCheck={false}
                    autoComplete="off"
                    placeholder={
                      conta?.certificado_configurado
                        ? "•••• certificado já cadastrado"
                        : "-----BEGIN CERTIFICATE-----"
                    }
                    value={String(form.api_certificado ?? "")}
                    onChange={(e) => definir("api_certificado", e.target.value)}
                  />
                </Campo>
                <Campo
                  rotulo="Chave privada do certificado (PEM)"
                  dica="Cole o conteúdo completo. Ela é cifrada antes de chegar ao banco de dados."
                  className="sm:col-span-2"
                >
                  <AreaTexto
                    spellCheck={false}
                    autoComplete="off"
                    placeholder={
                      conta?.certificado_configurado
                        ? "•••• chave privada já cadastrada"
                        : "-----BEGIN PRIVATE KEY-----"
                    }
                    value={String(form.api_chave_privada ?? "")}
                    onChange={(e) => definir("api_chave_privada", e.target.value)}
                  />
                </Campo>
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                <Campo
                  rotulo="Host SFTP"
                  dica="Opcional. Sem ele, a remessa fica para download e alguém a leva ao banco."
                  className="sm:col-span-2"
                >
                  <Input
                    value={String(form.sftp_host ?? "")}
                    onChange={(e) => definir("sftp_host", e.target.value)}
                    placeholder="sftp.banco.com.br"
                  />
                </Campo>
                <Campo rotulo="Usuário SFTP">
                  <Input
                    value={String(form.sftp_usuario ?? "")}
                    onChange={(e) => definir("sftp_usuario", e.target.value)}
                  />
                </Campo>
                <Campo rotulo="Senha SFTP">
                  <Input
                    type="password"
                    autoComplete="off"
                    placeholder={conta?.sftp_configurado ? "•••• já cadastrada" : ""}
                    value={String(form.sftp_senha ?? "")}
                    onChange={(e) => definir("sftp_senha", e.target.value)}
                  />
                </Campo>
                <Campo rotulo="Diretório de remessa">
                  <Input
                    value={String(form.sftp_dir_remessa ?? "")}
                    onChange={(e) => definir("sftp_dir_remessa", e.target.value)}
                  />
                </Campo>
                <Campo rotulo="Diretório de retorno">
                  <Input
                    value={String(form.sftp_dir_retorno ?? "")}
                    onChange={(e) => definir("sftp_dir_retorno", e.target.value)}
                  />
                </Campo>
              </div>
            )}
          </fieldset>

          <div className="flex flex-wrap gap-5">
            <Alternador
              rotulo="Ambiente de produção"
              dica="Desligado, nenhum título é registrado de verdade."
              valor={Boolean(form.producao)}
              aoMudar={(v) => definir("producao", v)}
            />
            <Alternador
              rotulo="Conta ativa"
              valor={Boolean(form.ativa)}
              aoMudar={(v) => definir("ativa", v)}
            />
            <Alternador
              rotulo="Conta padrão"
              dica="Sugerida ao criar cobrança."
              valor={Boolean(form.padrao)}
              aoMudar={(v) => definir("padrao", v)}
            />
          </div>
        </div>
      </DialogoConteudo>
    </Dialogo>
  );
}

function Alternador({
  rotulo,
  dica,
  valor,
  aoMudar,
}: {
  rotulo: string;
  dica?: string;
  valor: boolean;
  aoMudar: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5">
      <input
        type="checkbox"
        checked={valor}
        onChange={(e) => aoMudar(e.target.checked)}
        className="mt-0.5 size-4 accent-[var(--acento)]"
      />
      <span className="text-[13px]">
        {rotulo}
        {dica && <span className="block text-[12px] text-texto-tenue">{dica}</span>}
      </span>
    </label>
  );
}
