"use client";

import * as React from "react";

import { api } from "@/lib/api";
import type { Pagina } from "@/lib/tipos";

type Params = Record<string, string | number | boolean | undefined | null>;

/**
 * Todos os hooks de busca seguem a mesma ideia: o estado guarda **qual pedido**
 * produziu os dados em mãos. "Carregando" deixa de ser um sinalizador mantido
 * na unha e passa a ser derivado — é carregamento enquanto o que está na tela
 * não corresponde ao que foi pedido.
 *
 * Isso também elimina a corrida entre respostas: uma resposta atrasada carrega
 * a chave do pedido dela, então nunca se passa pela resposta do pedido atual.
 */

/** Lista paginada com busca e filtros — usada por todas as telas de listagem. */
export function useLista<T>(caminho: string, params: Params = {}) {
  const chave = JSON.stringify(params);

  // A página pertence ao conjunto de filtros: quando os filtros mudam ela
  // volta para 1 por derivação, sem efeito de sincronização.
  const [paginacao, setPaginacao] = React.useState({ chave, pagina: 1 });
  const pagina = paginacao.chave === chave ? paginacao.pagina : 1;
  const setPagina = React.useCallback(
    (nova: number) => setPaginacao({ chave, pagina: nova }),
    [chave],
  );

  const [resultado, setResultado] = React.useState({
    pedido: "",
    dados: [] as T[],
    total: 0,
    paginas: 1,
    erro: null as string | null,
  });

  const pedido = `${caminho}|${chave}|${pagina}`;
  const carregando = resultado.pedido !== pedido;

  const carregar = React.useCallback(async () => {
    const atual = `${caminho}|${chave}|${pagina}`;
    // Fora do try fica tudo que é síncrono — o parse dos filtros e o disparo
    // da requisição. Assim o bloco protegido começa no `await`: nenhum caminho
    // de erro consegue gravar estado ainda dentro do efeito, o que provocaria
    // renderização em cascata.
    const filtros = JSON.parse(chave) as Params;
    const requisicao = api.get<Pagina<T>>(caminho, { ...filtros, page: pagina });
    try {
      const resposta = await requisicao;
      setResultado({
        pedido: atual,
        dados: resposta.resultados,
        total: resposta.total,
        paginas: resposta.paginas,
        erro: null,
      });
    } catch (e) {
      setResultado(() => ({
        pedido: atual,
        dados: [],
        total: 0,
        paginas: 1,
        erro: e instanceof Error ? e.message : "Falha ao carregar.",
      }));
    }
  }, [caminho, chave, pagina]);

  React.useEffect(() => {
    carregar();
  }, [carregar]);

  return {
    dados: resultado.dados,
    total: resultado.total,
    pagina,
    paginas: resultado.paginas,
    setPagina,
    carregando,
    erro: resultado.erro,
    recarregar: carregar,
  };
}

/** Busca de um único recurso. */
export function useRecurso<T>(caminho: string | null) {
  const [resultado, setResultado] = React.useState({
    pedido: "",
    dados: null as T | null,
    erro: null as string | null,
  });

  const carregando = Boolean(caminho) && resultado.pedido !== caminho;

  const carregar = React.useCallback(async () => {
    if (!caminho) return;
    try {
      const dados = await api.get<T>(caminho);
      setResultado({ pedido: caminho, dados, erro: null });
    } catch (e) {
      // Erro em uma releitura não apaga o que já estava na tela.
      setResultado((atual) => ({
        pedido: caminho,
        dados: atual.dados,
        erro: e instanceof Error ? e.message : "Falha ao carregar.",
      }));
    }
  }, [caminho]);

  React.useEffect(() => {
    carregar();
  }, [carregar]);

  return { dados: resultado.dados, carregando, erro: resultado.erro, recarregar: carregar };
}

/**
 * Recurso que se atualiza sozinho, para telas de acompanhamento.
 *
 * A releitura periódica é silenciosa — como "carregando" é derivado do pedido,
 * uma atualização que não muda os filtros nunca faz a tela piscar. A janela
 * pausa quando a aba sai de foco: ninguém precisa de dados frescos de uma tela
 * que não está sendo vista.
 */
export function useRecursoVivo<T>(
  caminho: string,
  params: Params = {},
  intervalo = 30_000,
) {
  const chave = JSON.stringify(params);
  const pedido = `${caminho}|${chave}`;

  const [resultado, setResultado] = React.useState({
    pedido: "",
    dados: null as T | null,
    erro: null as string | null,
    atualizadoEm: null as Date | null,
  });

  const carregando = resultado.pedido !== pedido;

  const buscar = React.useCallback(async () => {
    const atual = `${caminho}|${chave}`;
    const filtros = JSON.parse(chave) as Params;
    try {
      const dados = await api.get<T>(caminho, filtros);
      setResultado({ pedido: atual, dados, erro: null, atualizadoEm: new Date() });
    } catch (e) {
      setResultado((anterior) => ({
        pedido: atual,
        dados: anterior.dados,
        erro: e instanceof Error ? e.message : "Falha ao carregar.",
        atualizadoEm: anterior.atualizadoEm,
      }));
    }
  }, [caminho, chave]);

  React.useEffect(() => {
    buscar();
  }, [buscar]);

  React.useEffect(() => {
    if (!intervalo) return;
    const aoVoltar = () => {
      if (document.visibilityState === "visible") buscar();
    };
    const timer = setInterval(aoVoltar, intervalo);
    document.addEventListener("visibilitychange", aoVoltar);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", aoVoltar);
    };
  }, [buscar, intervalo]);

  return {
    dados: resultado.dados,
    carregando,
    erro: resultado.erro,
    atualizadoEm: resultado.atualizadoEm,
    recarregar: buscar,
  };
}

/** Atrasa a propagação do texto digitado para não disparar uma busca por tecla. */
export function useDebounce<T>(valor: T, atraso = 350) {
  const [adiado, setAdiado] = React.useState(valor);
  React.useEffect(() => {
    const timer = setTimeout(() => setAdiado(valor), atraso);
    return () => clearTimeout(timer);
  }, [valor, atraso]);
  return adiado;
}

// ------------------------------------------------------- preferências locais
const ouvintes = new Set<() => void>();

function assinarPreferencias(aoMudar: () => void) {
  ouvintes.add(aoMudar);
  return () => ouvintes.delete(aoMudar);
}

/**
 * Preferência de interface guardada no navegador (a visão escolhida na Central,
 * por exemplo). Lida como fonte externa: nada de efeito para sincronizar, e o
 * servidor renderiza sempre o padrão — sem divergência na hidratação.
 */
export function usePreferencia(chave: string, padrao: string) {
  const valor = React.useSyncExternalStore(
    assinarPreferencias,
    () => localStorage.getItem(chave) ?? padrao,
    () => padrao,
  );

  const definir = React.useCallback(
    (novo: string) => {
      localStorage.setItem(chave, novo);
      ouvintes.forEach((avisar) => avisar());
    },
    [chave],
  );

  return [valor, definir] as const;
}
