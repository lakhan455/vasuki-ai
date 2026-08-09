"use client";

import { useEffect, useState } from "react";
import {
  fetchOwnerPlatformV9,
  updateOwnerFeatureFlagV9,
  type OwnerPlatformV9,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

async function token() {
  const { data } = await supabase.auth.getSession();
  const value = data.session?.access_token;
  if (!value) throw new Error("Please sign in.");
  return value;
}

export default function OwnerPage() {
  const [data, setData] = useState<OwnerPlatformV9 | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  async function load() {
    try {
      const accessToken = await token();
      setData(await fetchOwnerPlatformV9(accessToken, 30));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Owner dashboard could not be loaded.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function toggleFlag(key: string, enabled: boolean) {
    const current = data?.feature_flags?.[key];
    if (!current) return;
    setBusy(key);
    setError("");
    try {
      const accessToken = await token();
      await updateOwnerFeatureFlagV9(accessToken, key, {
        enabled,
        rollout_percent: current.rollout_percent ?? 100,
        variants: current.variants || {},
        description: current.description || "",
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Feature flag could not be updated.");
    } finally {
      setBusy("");
    }
  }

  const usage = data?.usage;
  const cost = usage?.cost;

  return (
    <main className="pv-v9-owner-page">
      <header className="pv-v9-ops-head">
        <div>
          <p className="pv-v8-kicker">Owner only · V9 Phase 4</p>
          <h1>Owner Platform Dashboard</h1>
          <p>Usage, quota failures, reported cost signals, background jobs, experiments and feature controls.</p>
        </div>
        <nav>
          <a href="/operations">Operations Center</a>
          <a href="/">Back to chat</a>
        </nav>
      </header>

      {error ? <div className="pv-v8-error pv-v9-ops-error">{error}</div> : null}
      {!data && !error ? <p>Loading owner dashboard...</p> : null}

      {data ? (
        <>
          <section className="pv-v9-ops-stats">
            <article><span>Requests / 30d</span><strong>{usage?.requests ?? 0}</strong></article>
            <article><span>Active users</span><strong>{usage?.active_users ?? 0}</strong></article>
            <article><span>Errors</span><strong>{usage?.errors ?? 0}</strong></article>
            <article><span>429 / quota</span><strong>{usage?.quota_429 ?? 0}</strong></article>
            <article><span>Background jobs</span><strong>{data.jobs?.total ?? 0}</strong></article>
          </section>

          <section className="pv-v9-owner-grid">
            <article className="pv-v9-ops-card">
              <h2>Cost signals</h2>
              <div className="pv-v9-cost-grid">
                <div><span>Reported cost</span><strong>${(cost?.reported_cost_usd ?? 0).toFixed(4)}</strong></div>
                <div><span>Estimated cost</span><strong>${(cost?.estimated_cost_usd ?? 0).toFixed(4)}</strong></div>
                <div><span>Priced events</span><strong>{(cost?.reported_cost_events ?? 0) + (cost?.estimated_cost_events ?? 0)}</strong></div>
                <div><span>Unpriced events</span><strong>{cost?.unpriced_events ?? 0}</strong></div>
              </div>
              <p className="pv-v9-ops-note">{cost?.note}</p>
              <pre>{JSON.stringify(cost?.by_provider || {}, null, 2)}</pre>
            </article>

            <article className="pv-v9-ops-card">
              <h2>Jobs / quota health</h2>
              <h3>Status</h3>
              <pre>{JSON.stringify(data.jobs?.statuses || {}, null, 2)}</pre>
              <h3>Kinds</h3>
              <pre>{JSON.stringify(data.jobs?.kinds || {}, null, 2)}</pre>
              <h3>Provider usage</h3>
              <pre>{JSON.stringify(usage?.providers || {}, null, 2)}</pre>
            </article>

            <article className="pv-v9-ops-card">
              <h2>A/B experiments</h2>
              {!Object.keys(data.experiments || {}).length ? <div className="pv-v8-empty">No experiment events yet.</div> : null}
              <pre>{JSON.stringify(data.experiments || {}, null, 2)}</pre>
            </article>

            <article className="pv-v9-ops-card">
              <h2>Feature flags</h2>
              <div className="pv-v9-flag-list">
                {Object.entries(data.feature_flags || {}).map(([key, flag]) => (
                  <article key={key}>
                    <div>
                      <strong>{key}</strong>
                      <small>{flag.rollout_percent ?? 100}% rollout · {flag.source || "default"}</small>
                      {flag.description ? <p>{flag.description}</p> : null}
                    </div>
                    <button
                      type="button"
                      disabled={busy === key}
                      className={flag.enabled ? "is-on" : ""}
                      onClick={() => void toggleFlag(key, !flag.enabled)}
                    >
                      {busy === key ? "Saving..." : flag.enabled ? "Enabled" : "Disabled"}
                    </button>
                  </article>
                ))}
              </div>
            </article>
          </section>
        </>
      ) : null}
    </main>
  );
}
