"use client";

import { useEffect, useState } from "react";

type ImageItem = {
  id: string;
  name: string;
  download_url?: string;
  created_at?: string;
  prompt?: string;
  provider?: string;
};

export default function ImagesPage() {
  const [items, setItems] = useState<ImageItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const response = await fetch("/api/images/history", { credentials: "include" });
        const data = await response.json();
        setItems(Array.isArray(data?.images) ? data.images : []);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <main style={{ padding: 24, color: "white", background: "#212121", minHeight: "100vh" }}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>Image History</h1>
      <p style={{ color: "#b4b4b4", marginBottom: 20 }}>Previously generated images and prompts.</p>
      {loading && <p>Loading images...</p>}
      {!loading && !items.length && <p style={{ color: "#b4b4b4" }}>No generated images yet.</p>}
      <div style={{ display: "grid", gap: 14 }}>
        {items.map((item) => (
          <div key={item.id} style={{ border: "1px solid #3a3a3a", borderRadius: 14, padding: 16, background: "#171717" }}>
            <div style={{ fontWeight: 600 }}>{item.name}</div>
            <div style={{ color: "#9ca3af", fontSize: 13, margin: "4px 0 8px" }}>{item.provider || "image provider"}</div>
            {item.prompt ? <div style={{ color: "#d1d5db", fontSize: 14, marginBottom: 10 }}>{item.prompt}</div> : null}
            {item.download_url ? <a href={item.download_url} target="_blank" rel="noreferrer" style={{ color: "#c4b5fd" }}>Open image</a> : null}
          </div>
        ))}
      </div>
    </main>
  );
}
