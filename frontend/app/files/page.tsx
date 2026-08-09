"use client";

import { useEffect, useState } from "react";

type Item = {
  id: string;
  name: string;
  artifact_type: string;
  mime_type: string;
  provider?: string;
  created_at?: string;
  download_url?: string;
};

export default function FilesPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    try {
      setLoading(true);
      setError("");
      const response = await fetch("/api/files", { credentials: "include" });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || "Failed to load files");
      setItems(Array.isArray(data?.files) ? data.files : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load files");
    } finally {
      setLoading(false);
    }
  }

  async function removeFile(id: string) {
    await fetch(`/api/files/${id}`, { method: "DELETE", credentials: "include" });
    load();
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <main style={{ padding: 24, color: "white", background: "#212121", minHeight: "100vh" }}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>My Files</h1>
      <p style={{ color: "#b4b4b4", marginBottom: 20 }}>Generated PDFs, QR files, DOCX, TXT and other artifacts.</p>
      {loading && <p>Loading files...</p>}
      {error && <p style={{ color: "#fca5a5" }}>{error}</p>}
      {!loading && !items.length && <p style={{ color: "#b4b4b4" }}>No files found yet.</p>}
      <div style={{ display: "grid", gap: 12 }}>
        {items.map((item) => (
          <div key={item.id} style={{ border: "1px solid #3a3a3a", borderRadius: 14, padding: 16, background: "#171717" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
              <div>
                <div style={{ fontWeight: 600 }}>{item.name}</div>
                <div style={{ color: "#9ca3af", fontSize: 13 }}>{item.mime_type} • {item.artifact_type}</div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                {item.download_url ? (
                  <a href={item.download_url} target="_blank" rel="noreferrer" style={{ color: "#c4b5fd" }}>Download</a>
                ) : null}
                <button onClick={() => removeFile(item.id)} style={{ background: "transparent", color: "#fca5a5", border: "1px solid #7f1d1d", borderRadius: 10, padding: "6px 10px" }}>Delete</button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
