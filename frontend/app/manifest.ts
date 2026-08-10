import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Vasuki AI",
    short_name: "Vasuki AI",
    description: "AI chat, research, coding, documents and image generation.",
    start_url: "/",
    display: "standalone",
    background_color: "#171717",
    theme_color: "#212121",
    orientation: "any",
    icons: [
      {
        src: "/vasuki-pwa-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/vasuki-pwa-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/vasuki-pwa-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
