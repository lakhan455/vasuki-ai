"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  cancelBackgroundJobV9,
  createBackgroundJobV9,
  fetchPlatformSnapshotV9,
  markAllNotificationsReadV9,
  markNotificationReadV9,
  recordExperimentConversionV9,
  recordExperimentExposureV9,
  type PlatformSnapshotV9,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

async function token() {
  const { data } = await supabase.auth.getSession();
  const value = data.session?.access_token;
  if (!value) throw new Error("Please sign in again.");
  return value;
}

function statusLabel(value: string) {
  return value.replace(/_/g, " ");
}

export default function OperationsPage() {
  const [data, setData] = useState<PlatformSnapshotV9 | null>(null);
  const [prompt, setPrompt] = useState("");
  const [jobKind, setJobKind] = useState("image.generate");
  const [preset, setPreset] = useState("none");
  const [ratio, setRatio] = useState("square");
  const [count, setCount] = useState(2);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const exposureSentRef = useRef("");

  const refreshMs =
    data?.experiments?.operations_refresh_cadence === "fast" ? 3000 : 5000;

  async function load(showError = true) {
    try {
      const accessToken = await token();
      setData(await fetchPlatformSnapshotV9(accessToken, 30));
    } catch (err) {
      if (showError) {
        setError(err instanceof Error ? err.message : "Operations Center could not be loaded.");
      }
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => void load(false), refreshMs);
    return () => window.clearInterval(id);
  }, [refreshMs]);

  useEffect(() => {
    const variant = data?.experiments?.operations_refresh_cadence;
    if (!variant || exposureSentRef.current === variant) return;
    exposureSentRef.current = variant;
    void (async () => {
      try {
        const accessToken = await token();
        await recordExperimentExposureV9(
          accessToken,
          "operations_refresh_cadence",
          variant,
          { surface: "operations_center" },
        );
      } catch {
        return;
      }
    })();
  }, [data?.experiments?.operations_refresh_cadence]);

  const jobs = data?.jobs || [];
  const notifications = data?.notifications?.items || [];
  const activeJobs = jobs.filter((job) => job.status === "pending" || job.status === "running");

  const allowedKinds = useMemo(
    () => new Set(data?.policy?.allowed_background_kinds || []),
    [data?.policy?.allowed_background_kinds],
  );

  async function submitJob() {
    if (!prompt.trim()) return setError("Write an instruction first.");
    setBusy("submit");
    setError("");
    try {
      const accessToken = await token();
      const payload: Record<string, unknown> = {
        prompt: prompt.trim(),
        preset,
        aspect_ratio: ratio,
      };
      if (jobKind === "image.variations") payload.count = count;
      await createBackgroundJobV9(accessToken, jobKind, payload);
      const variant = data?.experiments?.operations_refresh_cadence;
      if (variant) {
        void recordExperimentConversionV9(
          accessToken,
          "operations_refresh_cadence",
          variant,
          { action: "background_job_submitted" },
        );
      }
      setPrompt("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Background job could not be created.");
    } finally {
      setBusy("");
    }
  }

  async function cancel(jobId: string) {
    setBusy(jobId);
    try {
      const accessToken = await token();
      await cancelBackgroundJobV9(accessToken, jobId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Job could not be cancelled.");
    } finally {
      setBusy("");
    }
  }

  async function markRead(notificationId: string) {
    try {
      const accessToken = await token();
      await markNotificationReadV9(accessToken, notificationId);
      await load(false);
    } catch {
      return;
    }
  }

  async function readAll() {
    try {
      const accessToken = await token();
      await markAllNotificationsReadV9(accessToken);
      await load(false);
    } catch {
      return;
    }
  }

  return (
    <main className="pv-v9-ops-page">
      <header className="pv-v9-ops-head">
        <div>
          <p className="pv-v8-kicker">Vasuki AI V9 Phase 4</p>
          <h1>Operations Center</h1>
          <p>Background jobs, progress, notifications, usage and your current plan policy.</p>
        </div>
        <nav>
          <a href="/images">Image Studio</a>
          <a href="/owner">Owner</a>
          <a href="/">Back to chat</a>
        </nav>
      </header>

      {error ? <div className="pv-v8-error pv-v9-ops-error">{error}</div> : null}

      <section className="pv-v9-ops-stats">
        <article><span>Plan</span><strong>{data?.plan?.plan || "-"}</strong></article>
        <article><span>Requests / 30d</span><strong>{data?.usage?.requests ?? 0}</strong></article>
        <article><span>Active jobs</span><strong>{activeJobs.length}</strong></article>
        <article><span>Unread</span><strong>{data?.notifications?.unread ?? 0}</strong></article>
        <article><span>Errors / 30d</span><strong>{data?.usage?.errors ?? 0}</strong></article>
      </section>

      <section className="pv-v9-ops-grid">
        <article className="pv-v9-ops-card">
          <div className="pv-v9-ops-title">
            <div><p className="pv-v8-kicker">Queue</p><h2>Create background job</h2></div>
          </div>
          <label>
            <span>Job</span>
            <select value={jobKind} onChange={(event) => setJobKind(event.target.value)}>
              <option value="image.generate" disabled={data ? !allowedKinds.has("image.generate") : false}>
                Generate image in background
              </option>
              <option value="image.variations" disabled={data ? !allowedKinds.has("image.variations") : false}>
                Image variations in background
              </option>
            </select>
          </label>
          <label>
            <span>Prompt</span>
            <textarea
              rows={5}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Example: Premium NFC business card product photo..."
            />
          </label>
          <div className="pv-v9-ops-fields">
            <label>
              <span>Preset</span>
              <select value={preset} onChange={(event) => setPreset(event.target.value)}>
                {["none", "photo", "cinematic", "product", "poster", "logo", "anime", "3d"].map((item) => (
                  <option value={item} key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Ratio</span>
              <select value={ratio} onChange={(event) => setRatio(event.target.value)}>
                <option value="square">1:1</option>
                <option value="portrait">4:5</option>
                <option value="landscape">16:9</option>
                <option value="story">9:16</option>
                <option value="classic">4:3</option>
              </select>
            </label>
            {jobKind === "image.variations" ? (
              <label>
                <span>Count</span>
                <select value={count} onChange={(event) => setCount(Number(event.target.value))}>
                  {[2, 3, 4].map((item) => (
                    <option
                      value={item}
                      key={item}
                      disabled={item > (data?.policy?.image_variations_max ?? 4)}
                    >
                      {item}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </div>
          <button
            className="pv-v9-primary"
            type="button"
            disabled={busy === "submit" || !prompt.trim()}
            onClick={() => void submitJob()}
          >
            {busy === "submit" ? "Adding..." : "Add to background queue"}
          </button>
          <p className="pv-v9-ops-note">
            Daily limit: {data?.policy?.background_jobs_daily ?? "-"} · Active limit: {data?.policy?.active_background_jobs ?? "-"}
          </p>
        </article>

        <article className="pv-v9-ops-card">
          <div className="pv-v9-ops-title">
            <div><p className="pv-v8-kicker">Live progress</p><h2>Jobs</h2></div>
            <button type="button" onClick={() => void load()}>Refresh</button>
          </div>
          <div className="pv-v9-job-list">
            {!jobs.length ? <div className="pv-v8-empty">No background jobs yet.</div> : null}
            {jobs.map((job) => (
              <article key={job.id} className={`is-${job.status}`}>
                <div className="pv-v9-job-top">
                  <div><strong>{job.kind}</strong><small>{statusLabel(job.status)}</small></div>
                  <strong>{job.progress ?? 0}%</strong>
                </div>
                <div className="pv-v9-progress"><span style={{ width: `${Math.max(0, Math.min(100, job.progress || 0))}%` }} /></div>
                {job.error ? <p className="pv-v9-job-error">{job.error}</p> : null}
                {job.status === "pending" ? (
                  <button type="button" disabled={busy === job.id} onClick={() => void cancel(job.id)}>
                    {busy === job.id ? "Cancelling..." : "Cancel pending job"}
                  </button>
                ) : null}
                {job.status === "succeeded" ? (
                  <a href="/files">Open saved files</a>
                ) : null}
              </article>
            ))}
          </div>
        </article>

        <article className="pv-v9-ops-card">
          <div className="pv-v9-ops-title">
            <div><p className="pv-v8-kicker">Inbox</p><h2>Notifications</h2></div>
            <button type="button" onClick={() => void readAll()}>Mark all read</button>
          </div>
          <div className="pv-v9-notification-list">
            {!notifications.length ? <div className="pv-v8-empty">No notifications yet.</div> : null}
            {notifications.map((item) => (
              <article className={item.read_at ? "" : "is-unread"} key={item.id}>
                <div>
                  <strong>{item.title}</strong>
                  <small>{item.kind || "info"}{item.created_at ? ` · ${new Date(item.created_at).toLocaleString()}` : ""}</small>
                </div>
                <p>{item.body}</p>
                <div className="pv-v9-inline-actions">
                  {!item.read_at ? <button type="button" onClick={() => void markRead(item.id)}>Mark read</button> : null}
                  {item.action_url ? <a href={item.action_url}>Open</a> : null}
                </div>
              </article>
            ))}
          </div>
        </article>

        <article className="pv-v9-ops-card">
          <div className="pv-v9-ops-title">
            <div><p className="pv-v8-kicker">Your activity</p><h2>Usage</h2></div>
          </div>
          <div className="pv-v9-usage-mini">
            <div><span>Requests</span><strong>{data?.usage?.requests ?? 0}</strong></div>
            <div><span>Avg latency</span><strong>{data?.usage?.average_latency_ms ?? "-"} ms</strong></div>
            <div><span>Errors</span><strong>{data?.usage?.errors ?? 0}</strong></div>
            <div><span>429 / quota</span><strong>{data?.usage?.quota_429 ?? 0}</strong></div>
          </div>
          <h3>Feature usage</h3>
          <pre>{JSON.stringify(data?.usage?.features || {}, null, 2)}</pre>
          <h3>Provider usage</h3>
          <pre>{JSON.stringify(data?.usage?.providers || {}, null, 2)}</pre>
          <p className="pv-v9-ops-note">{data?.usage?.cost?.note}</p>
        </article>
      </section>
    </main>
  );
}
