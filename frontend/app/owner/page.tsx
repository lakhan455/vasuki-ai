"use client";

import { useEffect, useState } from "react";
import { fetchOwnerAnalytics, type OwnerAnalytics } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export default function OwnerPage() {
  const [data, setData] = useState<OwnerAnalytics | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const { data: auth } = await supabase.auth.getSession();
        const token = auth.session?.access_token;
        if (!token) throw new Error("Please sign in.");
        setData(await fetchOwnerAnalytics(token, 7));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Analytics could not be loaded.");
      }
    })();
  }, []);

  const p = data?.persistent;
  return (
    <main className="pv-v8-page">
      <div className="pv-v8-page-head">
        <div><p className="pv-v8-kicker">Owner only</p><h1>Owner Analytics</h1><p>Usage, latency, failures, quota events and provider health.</p></div>
        <a className="pv-v8-back" href="/">Back to chat</a>
      </div>
      {error && <div className="pv-v8-error">{error}</div>}
      {!data && !error && <p>Loading analytics...</p>}
      {p ? (
        <>
          <section className="pv-v8-stat-grid">
            <div className="pv-v8-stat"><span>Requests</span><strong>{p.requests ?? 0}</strong></div>
            <div className="pv-v8-stat"><span>Active users</span><strong>{p.active_users ?? 0}</strong></div>
            <div className="pv-v8-stat"><span>Avg latency</span><strong>{p.average_latency_ms ?? "-"} ms</strong></div>
            <div className="pv-v8-stat"><span>Errors</span><strong>{p.errors ?? 0}</strong></div>
            <div className="pv-v8-stat"><span>429 / quota</span><strong>{p.quota_429 ?? 0}</strong></div>
          </section>
          <div className="pv-v8-grid">
            <article className="pv-v8-card pv-v8-card--block"><strong>Feature usage</strong><pre>{JSON.stringify(p.features || {}, null, 2)}</pre></article>
            <article className="pv-v8-card pv-v8-card--block"><strong>Provider usage</strong><pre>{JSON.stringify(p.providers || {}, null, 2)}</pre></article>
            <article className="pv-v8-card pv-v8-card--block"><strong>Chat provider health</strong><pre>{JSON.stringify(data.chat_provider_health || {}, null, 2)}</pre></article>
            <article className="pv-v8-card pv-v8-card--block"><strong>Image provider health</strong><pre>{JSON.stringify(data.image_provider_health || {}, null, 2)}</pre></article>
          </div>
        </>
      ) : null}
    </main>
  );
}
