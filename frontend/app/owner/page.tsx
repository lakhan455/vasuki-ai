"use client";

import { useEffect, useState } from "react";

type Snapshot = {
  ok?: boolean;
  persistent?: {
    requests?: number;
    active_users?: number;
    average_latency_ms?: number | null;
    errors?: number;
    quota_429?: number;
    features?: Record<string, number>;
    providers?: Record<string, number>;
  };
  image_provider_health?: Record<string, unknown>;
  chat_provider_health?: Record<string, unknown>;
};

export default function OwnerPage() {
  const [data, setData] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const response = await fetch("/api/owner/analytics/v2?days=7", { credentials: "include" });
        const json = await response.json();
        if (!response.ok) throw new Error(json?.detail || "Failed to load analytics");
        setData(json);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load analytics");
      }
    })();
  }, []);

  return (
    <main style={{ padding: 24, color: "white", background: "#212121", minHeight: "100vh" }}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>Owner Analytics</h1>
      <p style={{ color: "#b4b4b4", marginBottom: 20 }}>Usage, latency, provider health and feature activity.</p>
      {error && <p style={{ color: "#fca5a5" }}>{error}</p>}
      {!data && !error && <p>Loading analytics...</p>}
      {data?.persistent ? (
        <div style={{ display: "grid", gap: 14 }}>
          <div style={{ border: "1px solid #3a3a3a", borderRadius: 14, padding: 16, background: "#171717" }}>
            <div>Total requests: {data.persistent.requests ?? 0}</div>
            <div>Active users: {data.persistent.active_users ?? 0}</div>
            <div>Average latency: {data.persistent.average_latency_ms ?? "-"} ms</div>
            <div>Errors: {data.persistent.errors ?? 0}</div>
            <div>429 / quota events: {data.persistent.quota_429 ?? 0}</div>
          </div>
          <div style={{ border: "1px solid #3a3a3a", borderRadius: 14, padding: 16, background: "#171717" }}>
            <div style={{ fontWeight: 600, marginBottom: 10 }}>Feature usage</div>
            <pre style={{ whiteSpace: "pre-wrap", color: "#d1d5db" }}>{JSON.stringify(data.persistent.features || {}, null, 2)}</pre>
          </div>
          <div style={{ border: "1px solid #3a3a3a", borderRadius: 14, padding: 16, background: "#171717" }}>
            <div style={{ fontWeight: 600, marginBottom: 10 }}>Provider usage</div>
            <pre style={{ whiteSpace: "pre-wrap", color: "#d1d5db" }}>{JSON.stringify(data.persistent.providers || {}, null, 2)}</pre>
          </div>
        </div>
      ) : null}
    </main>
  );
}
