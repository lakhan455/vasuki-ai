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
  type AutonomousTaskV75,
  cancelAutonomousTaskV75,
  createAutonomousTaskV75,
  fetchAutonomousTasksV75,
  pauseAutonomousTaskV75,
  resumeAutonomousTaskV75,
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
  const [scheduledTasks, setScheduledTasks] = useState<AutonomousTaskV75[]>([]);
  const [taskRuntimeNote, setTaskRuntimeNote] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [taskPrompt, setTaskPrompt] = useState("");
  const [taskMode, setTaskMode] = useState<"chat" | "research" | "multi_agent">("chat");
  const [taskSchedule, setTaskSchedule] = useState("daily");
  const [taskRunAt, setTaskRunAt] = useState("");
  const exposureSentRef = useRef("");

  const refreshMs =
    data?.experiments?.operations_refresh_cadence === "fast" ? 3000 : 5000;

  async function load(showError = true) {
    try {
      const accessToken = await token();
      const [platform, tasks] = await Promise.all([
        fetchPlatformSnapshotV9(accessToken, 30),
        fetchAutonomousTasksV75(accessToken),
      ]);
      setData(platform);
      setScheduledTasks(tasks.tasks);
      setTaskRuntimeNote(
        tasks.runtime && typeof tasks.runtime.note === "string"
          ? tasks.runtime.note
          : "",
      );
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

  function taskSchedulePayload() {
    if (taskSchedule === "once") {
      if (!taskRunAt) throw new Error("Choose a future date and time.");
      const date = new Date(taskRunAt);
      if (Number.isNaN(date.getTime())) throw new Error("Invalid task date/time.");
      return { run_at: date.toISOString(), cron: null };
    }
    if (taskSchedule === "hourly") return { run_at: null, cron: "*/60 * * * *" };
    if (taskSchedule === "six-hourly") return { run_at: null, cron: "*/360 * * * *" };
    return { run_at: null, cron: "0 9 * * *" };
  }

  async function createScheduledTask() {
    if (!taskTitle.trim() || !taskPrompt.trim()) {
      setError("Task title and instruction are required.");
      return;
    }
    setBusy("v75-create");
    setError("");
    try {
      const accessToken = await token();
      const schedule = taskSchedulePayload();
      await createAutonomousTaskV75(accessToken, {
        title: taskTitle.trim(),
        prompt: taskPrompt.trim(),
        mode: taskMode,
        run_at: schedule.run_at,
        cron: schedule.cron,
      });
      setTaskTitle("");
      setTaskPrompt("");
      setTaskRunAt("");
      await load(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Autonomous task could not be created.");
    } finally {
      setBusy("");
    }
  }

  async function pauseScheduledTask(taskId: string) {
    setBusy(`pause-${taskId}`);
    try {
      const accessToken = await token();
      await pauseAutonomousTaskV75(accessToken, taskId);
      await load(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Task could not be paused.");
    } finally {
      setBusy("");
    }
  }

  async function resumeScheduledTask(task: AutonomousTaskV75) {
    setBusy(`resume-${task.id}`);
    try {
      const accessToken = await token();
      let runAt: string | undefined;
      if (!task.cron && task.run_at && new Date(task.run_at).getTime() <= Date.now()) {
        runAt = new Date(Date.now() + 5 * 60 * 1000).toISOString();
      }
      await resumeAutonomousTaskV75(accessToken, task.id, runAt);
      await load(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Task could not be resumed.");
    } finally {
      setBusy("");
    }
  }

  async function cancelScheduledTask(taskId: string) {
    setBusy(`cancel-${taskId}`);
    try {
      const accessToken = await token();
      await cancelAutonomousTaskV75(accessToken, taskId);
      await load(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Task could not be cancelled.");
    } finally {
      setBusy("");
    }
  }

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
            <div><p className="pv-v8-kicker">V75</p><h2>Autonomous tasks</h2></div>
            <button type="button" onClick={() => void load(false)}>Refresh</button>
          </div>

          <label>
            <span>Task title</span>
            <input
              value={taskTitle}
              onChange={(event) => setTaskTitle(event.target.value)}
              placeholder="Example: Daily competitor summary"
            />
          </label>

          <label>
            <span>Instruction</span>
            <textarea
              rows={4}
              value={taskPrompt}
              onChange={(event) => setTaskPrompt(event.target.value)}
              placeholder="What should Vasuki do when this task runs?"
            />
          </label>

          <div className="pv-v9-ops-fields">
            <label>
              <span>Mode</span>
              <select
                value={taskMode}
                onChange={(event) =>
                  setTaskMode(event.target.value as "chat" | "research" | "multi_agent")
                }
              >
                <option value="chat">AI task</option>
                <option value="research">Live research</option>
                <option value="multi_agent">Multi-agent</option>
              </select>
            </label>

            <label>
              <span>Schedule</span>
              <select value={taskSchedule} onChange={(event) => setTaskSchedule(event.target.value)}>
                <option value="daily">Daily at 09:00 UTC</option>
                <option value="hourly">Every hour</option>
                <option value="six-hourly">Every 6 hours</option>
                <option value="once">One time</option>
              </select>
            </label>

            {taskSchedule === "once" ? (
              <label>
                <span>Run at</span>
                <input
                  type="datetime-local"
                  value={taskRunAt}
                  onChange={(event) => setTaskRunAt(event.target.value)}
                />
              </label>
            ) : null}
          </div>

          <button
            className="pv-v9-primary"
            type="button"
            disabled={busy === "v75-create" || !taskTitle.trim() || !taskPrompt.trim()}
            onClick={() => void createScheduledTask()}
          >
            {busy === "v75-create" ? "Creating..." : "Create autonomous task"}
          </button>

          <p className="pv-v9-ops-note">
            {taskRuntimeNote || "Tasks run from the persistent scheduler. Connector event triggers are not enabled yet."}
          </p>

          <div className="pv-v9-job-list">
            {!scheduledTasks.length ? <div className="pv-v8-empty">No autonomous tasks yet.</div> : null}
            {scheduledTasks.map((task) => (
              <article key={task.id} className={`is-${task.status}`}>
                <div className="pv-v9-job-top">
                  <div>
                    <strong>{task.title}</strong>
                    <small>{task.mode.replace(/_/g, " ")} · {statusLabel(task.status)}</small>
                  </div>
                  <strong>{task.cron ? "Recurring" : "One time"}</strong>
                </div>
                <p>{task.prompt}</p>
                <small>
                  Next: {task.run_at ? new Date(task.run_at).toLocaleString() : "-"}
                  {task.last_run_at ? ` · Last: ${new Date(task.last_run_at).toLocaleString()}` : ""}
                </small>
                {task.result && typeof task.result.answer === "string" ? (
                  <p>{String(task.result.answer).slice(0, 320)}</p>
                ) : null}
                <div className="pv-v9-inline-actions">
                  {task.status === "scheduled" ? (
                    <button
                      type="button"
                      disabled={busy === `pause-${task.id}`}
                      onClick={() => void pauseScheduledTask(task.id)}
                    >
                      Pause
                    </button>
                  ) : null}
                  {task.status === "paused" ? (
                    <button
                      type="button"
                      disabled={busy === `resume-${task.id}`}
                      onClick={() => void resumeScheduledTask(task)}
                    >
                      Resume
                    </button>
                  ) : null}
                  {!["completed", "cancelled"].includes(task.status) ? (
                    <button
                      type="button"
                      disabled={busy === `cancel-${task.id}`}
                      onClick={() => void cancelScheduledTask(task.id)}
                    >
                      Cancel
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        </article>
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
