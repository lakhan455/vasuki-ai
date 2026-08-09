"use client";

import { useEffect, useState } from "react";
import { fetchImageHistory, type GeneratedArtifact } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export default function ImagesPage() {
  const [items, setItems] = useState<GeneratedArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const { data } = await supabase.auth.getSession();
        const token = data.session?.access_token;
        if (!token) throw new Error("Please sign in to view Image History.");
        setItems(await fetchImageHistory(token));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load image history.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <main className="pv-v8-page">
      <div className="pv-v8-page-head">
        <div><p className="pv-v8-kicker">Vasuki AI</p><h1>Image History</h1><p>Your generated images, prompts and providers.</p></div>
        <a className="pv-v8-back" href="/">Back to chat</a>
      </div>
      {loading && <p>Loading images...</p>}
      {error && <div className="pv-v8-error">{error}</div>}
      {!loading && !items.length && !error && <div className="pv-v8-empty">No generated images yet.</div>}
      <div className="pv-v8-image-grid">
        {items.map((item) => (
          <article className="pv-v8-image-card" key={item.id}>
            {item.download_url ? <img src={item.download_url} alt={item.name} loading="lazy" /> : <div className="pv-v8-image-placeholder">Image</div>}
            <div className="pv-v8-image-copy">
              <strong>{item.name}</strong>
              {item.prompt ? <p>{item.prompt}</p> : null}
              <small>{item.provider || "Vasuki image router"}</small>
              {item.download_url ? <a href={item.download_url} target="_blank" rel="noreferrer">Open image</a> : null}
            </div>
          </article>
        ))}
      </div>
    </main>
  );
}
