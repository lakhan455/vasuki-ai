import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";
import ProductivityShellV9 from "@/components/ProductivityShellV9";

export const metadata: Metadata = {
  title: "Vasuki AI",
  description:
    "Vasuki AI ? chat, live research, coding and image generation.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/vasuki-pwa-192.png", apple: "/vasuki-pwa-192.png" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" translate="no" suppressHydrationWarning>
      <head>
        <link
          rel="preconnect"
          href="https://vasuki-ai.onrender.com"
          crossOrigin="anonymous"
        />
        <link
          rel="dns-prefetch"
          href="https://vasuki-ai.onrender.com"
        />
        <Script
          src="https://js.puter.com/v2/"
          strategy="afterInteractive"
        />
      </head>
      <body>
        <a className="pv-skip-link" href="#main-content">
          Skip to main content
        </a>
        <ProductivityShellV9 />
        <div id="main-content" tabIndex={-1}>
          {children}
        </div>
      </body>
    </html>
  );
}
