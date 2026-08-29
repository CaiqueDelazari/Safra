import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { ThemeProvider } from "next-themes";
import { Toaster } from "sonner";

import { ProvedorSessao } from "@/providers/sessao";

import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Plataforma de Cobranças",
  description:
    "Gestão multiempresa de clientes, cobranças, boletos e retornos bancários.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body className={`${inter.variable} antialiased`}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <ProvedorSessao>{children}</ProvedorSessao>
          <Toaster
            position="bottom-right"
            toastOptions={{
              className:
                "!rounded-lg !border !border-borda !bg-superficie !text-texto !text-[13px]",
            }}
          />
        </ThemeProvider>
      </body>
    </html>
  );
}
