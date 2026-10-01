import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "MatchForge",
  description: "Provider-neutral football fixtures and probabilistic forecasts",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body><AppShell>{children}</AppShell></body>
    </html>
  );
}
