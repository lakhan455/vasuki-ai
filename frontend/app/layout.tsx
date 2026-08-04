import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vasuki AI",
  description:
    "Vasuki AI — chat, live research, coding and image generation.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="hi" translate="no" suppressHydrationWarning>
      <head>
        <script src="https://js.puter.com/v2/" defer />
      </head>
      <body>{children}</body>
    </html>
  );
}
