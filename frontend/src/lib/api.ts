/**
 * Cliente HTTP único do painel.
 *
 * Injeta o JWT, o header X-Empresa-Id (isolamento multiempresa) e renova o
 * access token automaticamente quando ele expira. Também é aqui que mora o
 * acompanhamento de tarefa de fila, que é o padrão de toda operação pesada
 * deste sistema: a API responde 202 com um id e a tela pergunta o andamento.
 */
const BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// Chaves próprias: o sistema anterior roda em outro domínio, mas os dois
// podem conviver no mesmo navegador durante a transição, e sessão de um não
// pode ser lida como sessão do outro.
const CHAVE_ACCESS = "cobrancas.access";
const CHAVE_REFRESH = "cobrancas.refresh";
const CHAVE_EMPRESA = "cobrancas.empresa";

export const armazenamento = {
  get access() {
    return typeof window === "undefined" ? null : localStorage.getItem(CHAVE_ACCESS);
  },
  get refresh() {
    return typeof window === "undefined" ? null : localStorage.getItem(CHAVE_REFRESH);
  },
  get empresa() {
    if (typeof window === "undefined") return null;
    const valor = localStorage.getItem(CHAVE_EMPRESA);
    return valor ? Number(valor) : null;
  },
  set empresa(id: number | null) {
    if (typeof window === "undefined") return;
    if (id === null) localStorage.removeItem(CHAVE_EMPRESA);
    else localStorage.setItem(CHAVE_EMPRESA, String(id));
  },
  salvarTokens(access: string, refresh?: string) {
    localStorage.setItem(CHAVE_ACCESS, access);
    if (refresh) localStorage.setItem(CHAVE_REFRESH, refresh);
  },
  limpar() {
    localStorage.removeItem(CHAVE_ACCESS);
    localStorage.removeItem(CHAVE_REFRESH);
    localStorage.removeItem(CHAVE_EMPRESA);
  },
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public detalhe: string,
    public corpo?: unknown,
  ) {
    super(detalhe);
  }
}

let renovando: Promise<string | null> | null = null;

async function renovarToken(): Promise<string | null> {
  const refresh = armazenamento.refresh;
  if (!refresh) return null;
  if (!renovando) {
    renovando = fetch(`${BASE}/auth/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    })
      .then(async (r) => {
        if (!r.ok) return null;
        const dados = await r.json();
        armazenamento.salvarTokens(dados.access, dados.refresh);
        return dados.access as string;
      })
      .catch(() => null)
      .finally(() => {
        renovando = null;
      });
  }
  return renovando;
}

interface Opcoes extends Omit<RequestInit, "body"> {
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined | null>;
  semAuth?: boolean;
}

async function requisitar<T>(caminho: string, opcoes: Opcoes = {}): Promise<T> {
  const { body, params, semAuth, headers, ...resto } = opcoes;

  const url = new URL(`${BASE}${caminho}`);
  if (params) {
    Object.entries(params).forEach(([chave, valor]) => {
      if (valor !== undefined && valor !== null && valor !== "")
        url.searchParams.set(chave, String(valor));
    });
  }

  const montarHeaders = (token?: string | null): HeadersInit => {
    const base: Record<string, string> = {
      "Content-Type": "application/json",
      ...(headers as Record<string, string>),
    };
    if (!semAuth && token) base.Authorization = `Bearer ${token}`;
    const empresa = armazenamento.empresa;
    if (empresa) base["X-Empresa-Id"] = String(empresa);
    return base;
  };

  const executar = (token?: string | null) =>
    fetch(url.toString(), {
      ...resto,
      headers: montarHeaders(token),
      body: body === undefined ? undefined : JSON.stringify(body),
    });

  let resposta = await executar(armazenamento.access);

  if (resposta.status === 401 && !semAuth) {
    const novo = await renovarToken();
    if (novo) {
      resposta = await executar(novo);
    } else if (typeof window !== "undefined") {
      armazenamento.limpar();
      // Sessão perdida: aqui o recarregamento completo é o objetivo, não um
      // efeito colateral. Navegar pelo router preservaria em memória o estado
      // do usuário anterior — dados de outra sessão dentro da nova.
      if (!window.location.pathname.startsWith("/login"))
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.href = "/login";
    }
  }

  if (resposta.status === 204) return undefined as T;

  const texto = await resposta.text();
  const dados = texto ? JSON.parse(texto) : null;

  if (!resposta.ok) {
    const detalhe =
      dados?.detail ??
      (dados && typeof dados === "object"
        ? Object.entries(dados)
            .map(([campo, msgs]) => `${campo}: ${[msgs].flat().join(", ")}`)
            .join(" · ")
        : "Falha na requisição");
    throw new ApiError(resposta.status, String(detalhe), dados);
  }
  return dados as T;
}

/** Envio de arquivo: o corpo é FormData, então o Content-Type é do browser. */
async function enviarArquivo<T>(caminho: string, dados: FormData): Promise<T> {
  const executar = (token?: string | null) => {
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const empresa = armazenamento.empresa;
    if (empresa) headers["X-Empresa-Id"] = String(empresa);
    return fetch(`${BASE}${caminho}`, { method: "POST", headers, body: dados });
  };

  let resposta = await executar(armazenamento.access);
  if (resposta.status === 401) {
    const novo = await renovarToken();
    if (novo) resposta = await executar(novo);
  }

  const texto = await resposta.text();
  const corpo = texto ? JSON.parse(texto) : null;
  if (!resposta.ok)
    throw new ApiError(
      resposta.status,
      String(corpo?.detail ?? "Falha ao enviar o arquivo"),
      corpo,
    );
  return corpo as T;
}

export const api = {
  get: <T>(caminho: string, params?: Opcoes["params"]) =>
    requisitar<T>(caminho, { method: "GET", params }),
  upload: enviarArquivo,
  post: <T>(caminho: string, body?: unknown, opcoes?: Opcoes) =>
    requisitar<T>(caminho, { ...opcoes, method: "POST", body }),
  patch: <T>(caminho: string, body?: unknown) =>
    requisitar<T>(caminho, { method: "PATCH", body }),
  put: <T>(caminho: string, body?: unknown) =>
    requisitar<T>(caminho, { method: "PUT", body }),
  // DELETE com corpo: desativar o segundo fator exige a senha, e ela não
  // pode viajar na URL (fica em log de servidor e no histórico).
  delete: <T>(caminho: string, body?: unknown) =>
    requisitar<T>(caminho, { method: "DELETE", body }),
};

/**
 * Acompanha uma tarefa de fila até o fim.
 *
 * Toda operação pesada do sistema responde 202 com um `tarefa_id` — gerar
 * lote, importar planilha, processar retorno. Esta função é o outro lado
 * disso: pergunta o andamento, chama `aoProgredir` a cada passo e resolve
 * quando termina.
 *
 * O intervalo cresce (1s, 1.5s, 2s… até 5s) porque as tarefas curtas
 * terminam nos primeiros segundos e as longas não ganham nada com perguntas
 * de segundo em segundo — só geram requisição à toa numa VPS pequena.
 */
export async function acompanharTarefa(
  id: string,
  aoProgredir?: (progresso: number, estado: string) => void,
  limiteMs = 15 * 60_000,
): Promise<{ estado: string; resultado?: unknown; erro?: string }> {
  const inicio = Date.now();
  let espera = 1000;

  for (;;) {
    const status = await api.get<{
      estado: string;
      progresso: number;
      resultado?: unknown;
      erro?: string;
    }>(`/tarefas/${id}/`);

    aoProgredir?.(status.progresso ?? 0, status.estado);

    if (["SUCCESS", "FAILURE", "REVOKED"].includes(status.estado)) return status;
    if (Date.now() - inicio > limiteMs)
      return { estado: "TIMEOUT", erro: "A tarefa demorou mais que o esperado." };

    await new Promise((r) => setTimeout(r, espera));
    espera = Math.min(espera * 1.5, 5000);
  }
}
