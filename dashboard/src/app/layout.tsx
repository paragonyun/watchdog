import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Portfolio Watchdog",
  description: "Private portfolio dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
