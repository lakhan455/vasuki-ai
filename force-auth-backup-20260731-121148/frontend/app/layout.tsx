import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Power Vasuki AI",
  description: "Fast multi-provider AI assistant by Vasuki",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="hi" translate="no" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}

