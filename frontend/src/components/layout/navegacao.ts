import {
  Banknote,
  Building2,
  FileInput,
  FileOutput,
  LayoutDashboard,
  Receipt,
  ScaleIcon,
  ScrollText,
  Send,
  TriangleAlert,
  Users,
  UsersRound,
} from "lucide-react";

export interface ItemMenu {
  rotulo: string;
  href: string;
  icone: typeof LayoutDashboard;
  /** Módulo na matriz RBAC — some do menu se o papel não tiver acesso. */
  modulo: string;
}

export interface GrupoMenu {
  titulo?: string;
  itens: ItemMenu[];
}

/**
 * O menu segue o fluxo da regra 23, de cima para baixo: cadastra-se o cliente,
 * cria-se a cobrança, gera-se o lote, envia-se ao banco, processa-se o
 * retorno, concilia-se. Quem abre o sistema pela primeira vez consegue seguir
 * a barra lateral como um roteiro.
 *
 * "Pendências" fica logo abaixo do dashboard porque é a tela que evita o
 * modo de falha silencioso do produto: uma rejeição do banco que ninguém viu
 * é um boleto que o cliente nunca recebeu — e isso só apareceria no telefone,
 * no dia do vencimento.
 */
export const MENU: GrupoMenu[] = [
  {
    itens: [
      {
        rotulo: "Visão geral",
        href: "/dashboard",
        icone: LayoutDashboard,
        modulo: "dashboard",
      },
      {
        rotulo: "Pendências",
        href: "/pendencias",
        icone: TriangleAlert,
        modulo: "conciliacao",
      },
    ],
  },
  {
    titulo: "Cobrança",
    itens: [
      { rotulo: "Clientes", href: "/clientes", icone: Users, modulo: "clientes" },
      { rotulo: "Cobranças", href: "/cobrancas", icone: Receipt, modulo: "cobrancas" },
      { rotulo: "Lotes", href: "/lotes", icone: Send, modulo: "lotes" },
    ],
  },
  {
    titulo: "Banco",
    itens: [
      {
        rotulo: "Retornos",
        href: "/retornos",
        icone: FileInput,
        modulo: "arquivos",
      },
      {
        rotulo: "Remessas",
        href: "/remessas",
        icone: FileOutput,
        modulo: "arquivos",
      },
      {
        rotulo: "Contas bancárias",
        href: "/contas",
        icone: Banknote,
        modulo: "contas_bancarias",
      },
    ],
  },
  {
    titulo: "Financeiro",
    itens: [
      {
        rotulo: "Pagamentos",
        href: "/pagamentos",
        icone: Banknote,
        modulo: "pagamentos",
      },
      {
        rotulo: "Conciliação",
        href: "/conciliacao",
        icone: ScaleIcon,
        modulo: "conciliacao",
      },
      {
        rotulo: "Relatórios",
        href: "/relatorios",
        icone: ScrollText,
        modulo: "relatorios",
      },
    ],
  },
  {
    titulo: "Administração",
    itens: [
      { rotulo: "Empresa", href: "/empresa", icone: Building2, modulo: "empresas" },
      { rotulo: "Equipe", href: "/equipe", icone: UsersRound, modulo: "usuarios" },
      {
        rotulo: "Auditoria",
        href: "/auditoria",
        icone: ScrollText,
        modulo: "auditoria",
      },
    ],
  },
];
