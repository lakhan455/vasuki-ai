"use client";

import { useEffect, useState } from "react";
import { deleteMyFile, fetchMyFiles, type GeneratedArtifact } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export default function FilesPage() {
  const [items, setItems] = useState<GeneratedArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function token() {
    const { data } = await supabase.auth.getSession();
    if (!data.session?.access_token) throw new Error("Please sign in to view My Files.");
    return data.session.access_token;
  }

  async function load() {
    try {
      setLoading(true);
      setError("");
      setItems(await fetchMyFiles(await token()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load files.");
    } finally {
      setLoading(false);
    }
  }

  async function removeFile(id: string) {
    try {
      await deleteMyFile(await token(), id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "File delete failed.");
    }
  }

  useEffect(() => { void load(); }, []);

  return (
    <main className="pv-v8-page">
      <div className="pv-v8-page-head">
        <div><p className="pv-v8-kicker">Vasuki AI</p><h1>My Files</h1><p>Generated PDFs, DOCX, TXT, QR codes and saved artifacts.</p></div>
        <a className="pv-v8-back" href="/">Back to chat</a>
      </div>
      {loading && <p>Loading files...</p>}
      {error && <div className="pv-v8-error">{error}</div>}
      {!loading && !items.length && !error && <div className="pv-v8-empty">No generated files yet.</div>}
      <div className="pv-v8-grid">
        {items.map((item) => (
          <article className="pv-v8-card" key={item.id}>
            <div><strong>{item.name}</strong><small>{item.mime_type} · {item.artifact_type}</small></div>
            <div className="pv-v8-card-actions">
              {item.download_url ? <a href={item.download_url} target="_blank" rel="noreferrer">Open</a> : null}
              <button type="button" onClick={() => void removeFile(item.id)}>Delete</button>
            </div>
          </article>
        ))}
      </div>
    </main>
  );
}
