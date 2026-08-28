"use client";

import { useEffect, useMemo, useState } from "react";
import {
  analyzeV48Data,
  createV48Task,
  deleteV48LibraryFile,
  deleteV48Task,
  downloadV48LibraryFile,
  fetchV48Tools,
  listV48LibraryFiles,
  listV48Tasks,
  updateV48Task,
  uploadV48LibraryFile,
} from "@/lib/v48";

type ToolItem = { id: string; name: string; status: string; native?: boolean };
type LibraryItem = { name?: string; path?: string; created_at?: string; metadata?: { size?: number; mimetype?: string } };
type TaskItem = { id: string; title?: string; prompt?: string; run_at?: string; cron?: string; status?: string };

type Hub = { tools?: ToolItem[]; notes?: Record<string, string> };

const links: Record<string, string> = {
  "web-search": "/",
  "deep-research": "/research",
  "image-generation": "/images",
  "image-editing": "/images",
  "file-analysis": "/documents",
  voice: "/v11",
  memory: "/projects",
  projects: "/projects",
  "coding-agent": "/code",
  github: "/branches",
  video: "/v11",
};

function pretty(value: unknown) {
  return JSON.stringify(value, null, 2);
}

export default function ToolsHubV48() {
  const [hub, setHub] = useState<Hub | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [analysis, setAnalysis] = useState<unknown>(null);
  const [library, setLibrary] = useState<LibraryItem[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [taskTitle, setTaskTitle] = useState("");
  const [taskPrompt, setTaskPrompt] = useState("");
  const [taskRunAt, setTaskRunAt] = useState("");
  const [taskCron, setTaskCron] = useState("");

  async function refresh() {
    setError("");
    try {
      const [tools, files, scheduled] = await Promise.all([
        fetchV48Tools(),
        listV48LibraryFiles().catch(() => ({ files: [] })),
        listV48Tasks().catch(() => ({ tasks: [] })),
      ]);
      setHub(tools);
      setLibrary(Array.isArray(files.files) ? files.files : []);
      setTasks(Array.isArray(scheduled.tasks) ? scheduled.tasks : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "V48 tools could not be loaded.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const readyCount = useMemo(
    () => (hub?.tools || []).filter((tool) => tool.status === "ready").length,
    [hub],
  );

  async function analyze(file?: File) {
    if (!file) return;
    setBusy("analysis");
    setError("");
    try {
      setAnalysis(await analyzeV48Data(file));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Data analysis failed.");
    } finally {
      setBusy("");
    }
  }

  async function upload(file?: File) {
    if (!file) return;
    setBusy("library");
    setError("");
    try {
      await uploadV48LibraryFile(file);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "File upload failed.");
    } finally {
      setBusy("");
    }
  }

  async function createTask() {
    if (!taskTitle.trim() || !taskPrompt.trim() || (!taskRunAt && !taskCron)) return;
    setBusy("tasks");
    setError("");
    try {
      await createV48Task({
        title: taskTitle.trim(),
        prompt: taskPrompt.trim(),
        run_at: taskRunAt || undefined,
        cron: taskCron.trim() || undefined,
      });
      setTaskTitle("");
      setTaskPrompt("");
      setTaskRunAt("");
      setTaskCron("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Task could not be created.");
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="pv-v48-page">
      <section className="pv-v48-hero">
        <p>VASUKI AI V48</p>
        <h1>Unified Tools Hub</h1>
        <span>{readyCount} tools ready · ChatGPT-style tool categories, Vasuki-native execution.</span>
      </section>

      {error ? <div className="pv-v48-error">{error}</div> : null}

      <section className="pv-v48-grid">
        {(hub?.tools || []).map((tool) => (
          <button
            className="pv-v48-tool-card"
            key={tool.id}
            type="button"
            onClick={() => links[tool.id] && window.location.assign(links[tool.id])}
            disabled={!links[tool.id] && tool.id !== "data-analysis" && tool.id !== "file-library" && tool.id !== "scheduled-tasks"}
          >
            <div>
              <strong>{tool.name}</strong>
              <small>{tool.native ? "Vasuki native" : "External/optional"}</small>
            </div>
            <span data-status={tool.status}>{tool.status}</span>
          </button>
        ))}
      </section>

      <section className="pv-v48-panel">
        <div className="pv-v48-panel-head">
          <div><p>DATA ANALYSIS</p><h2>CSV · TSV · JSON · XLSX</h2></div>
          <label className="pv-v48-file-button">
            {busy === "analysis" ? "Analyzing…" : "Choose data file"}
            <input type="file" accept=".csv,.tsv,.json,.xlsx" onChange={(event) => void analyze(event.target.files?.[0])} />
          </label>
        </div>
        {analysis ? <pre className="pv-v48-output">{pretty(analysis)}</pre> : <p className="pv-v48-muted">Safe deterministic profiling: numeric statistics, missing values, top categories, preview and chart suggestions.</p>}
      </section>

      <section className="pv-v48-panel">
        <div className="pv-v48-panel-head">
          <div><p>FILE LIBRARY</p><h2>Persistent Supabase storage</h2></div>
          <label className="pv-v48-file-button">
            {busy === "library" ? "Uploading…" : "Upload file"}
            <input type="file" onChange={(event) => void upload(event.target.files?.[0])} />
          </label>
        </div>
        <div className="pv-v48-list">
          {library.map((item) => (
            <div key={item.path}>
              <div><strong>{item.name || "File"}</strong><small>{item.created_at || ""}</small></div>
              <div className="pv-v48-actions">
                <button type="button" onClick={async () => {
                  if (!item.path) return;
                  const result = await downloadV48LibraryFile(item.path);
                  if (result.url) window.open(result.url, "_blank", "noopener,noreferrer");
                }}>Open</button>
                <button type="button" onClick={async () => {
                  if (!item.path) return;
                  await deleteV48LibraryFile(item.path);
                  await refresh();
                }}>Delete</button>
              </div>
            </div>
          ))}
          {!library.length ? <p className="pv-v48-muted">No saved files yet.</p> : null}
        </div>
      </section>

      <section className="pv-v48-panel">
        <div className="pv-v48-panel-head"><div><p>SCHEDULED TASKS</p><h2>One-time or recurring</h2></div></div>
        <div className="pv-v48-task-form">
          <input placeholder="Task title" value={taskTitle} onChange={(event) => setTaskTitle(event.target.value)} />
          <textarea placeholder="What should Vasuki do?" value={taskPrompt} onChange={(event) => setTaskPrompt(event.target.value)} />
          <input type="datetime-local" value={taskRunAt} onChange={(event) => setTaskRunAt(event.target.value ? new Date(event.target.value).toISOString() : "")} />
          <input placeholder="or cron: */60 * * * *" value={taskCron} onChange={(event) => setTaskCron(event.target.value)} />
          <button type="button" onClick={() => void createTask()} disabled={busy === "tasks"}>{busy === "tasks" ? "Saving…" : "Schedule"}</button>
        </div>
        <div className="pv-v48-list">
          {tasks.map((task) => (
            <div key={task.id}>
              <div><strong>{task.title || "Task"}</strong><small>{task.status} · {task.run_at || task.cron || ""}</small></div>
              <div className="pv-v48-actions">
                <button type="button" onClick={async () => { await updateV48Task(task.id, { status: task.status === "paused" ? "scheduled" : "paused" }); await refresh(); }}>{task.status === "paused" ? "Resume" : "Pause"}</button>
                <button type="button" onClick={async () => { await deleteV48Task(task.id); await refresh(); }}>Delete</button>
              </div>
            </div>
          ))}
          {!tasks.length ? <p className="pv-v48-muted">No scheduled tasks yet.</p> : null}
        </div>
      </section>

      <section className="pv-v48-note">
        <strong>Computer Use & connected apps</strong>
        <p>V48 does not fake proprietary browser infrastructure or OAuth credentials. Computer-use remains disabled until a sandbox/remote-browser provider is explicitly connected; Gmail, Drive, Calendar and Slack require OAuth/MCP configuration.</p>
      </section>
    </main>
  );
}
