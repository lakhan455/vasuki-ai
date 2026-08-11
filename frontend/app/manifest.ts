import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  const value = {
    name: "Vasuki AI",
    short_name: "Vasuki AI",
    description: "AI chat, research, coding, documents, image, voice and multimodal generation.",
    start_url: "/",
    display: "standalone",
    background_color: "#171717",
    theme_color: "#212121",
    orientation: "any",
    share_target: {
      action: "/v11?shared=1",
      method: "GET",
      params: { title: "title", text: "text", url: "url" },
    },
    file_handlers: [
      {
        action: "/v11?file-open=1",
        accept: {
          "application/pdf": [".pdf"],
          "text/plain": [".txt", ".md"],
          "image/png": [".png"],
          "image/jpeg": [".jpg", ".jpeg"],
        },
      },
    ],
    icons: [
      { src: "/vasuki-pwa-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/vasuki-pwa-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/vasuki-pwa-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
  return value as MetadataRoute.Manifest;
}
