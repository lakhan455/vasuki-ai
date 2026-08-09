"use client";

import { useEffect, useState } from "react";
import { fetchRecentBranches, type ConversationBranch } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export default function BranchesPage() {
  const [items, setItems] = useState<ConversationBranch[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        const { data } = await supabase.auth.getSession();
        const token = data.session?.access_token;
        if (!token) throw new Error("Please sign in to view branches.");
        setItems(await fetchRecentBranches(token));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Branches could not be loaded.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <main className="pv-v8-page">
      <div className="pv-v8-page-head">
        <div>
          <p className="pv-v8-kicker">Conversation history</p>
          <h1>Branch Explorer</h1>
          <p>Edit & Resend and Regenerate branches from saved chats.</p>
        </div>
        <a className="pv-v8-back" href="/">Back to chat</a>
      </div>

      {loading && <p>Loading branches...</p>}
      {error && <div className="pv-v8-error">{error}</div>}
      {!loading && !items.length && !error && <div className="pv-v8-empty">No branches created yet.</div>}

      <div className="pv-v8-grid">
        {items.map((item) => (
          <article className="pv-v8-card pv-v8-card--block" key={item.id}>
            <div className="pv-v8-branch-meta">
              <strong>{item.note || "Conversation branch"}</strong>
              <small>{item.created_at ? new Date(item.created_at).toLocaleString() : ""}</small>
            </div>
            <div className="pv-v8-branch-compare">
              <div><span>Original</span><p>{item.original_prompt}</p></div>
              <div><span>Branch</span><p>{item.edited_prompt}</p></div>
            </div>
            <small>Conversation: {item.conversation_id}</small>
          </article>
        ))}
      </div>
    </main>
  );
}
