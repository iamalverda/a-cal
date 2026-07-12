import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "A-Cal — Agentic Calendar",
  description: "An agentic, self-hostable calendar platform that unifies all your accounts.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
