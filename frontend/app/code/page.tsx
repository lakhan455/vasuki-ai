"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  applyProjectCodePlan,
  deleteProjectKbFile,
  fetchProjectCodebaseMap,
  fetchProjectKbFiles,
  fetchProjects,
  generateProjectDebugPlan,
  generateProjectPatch,
  generateProjectTests,
  uploadProjectKbFiles,
  type ProjectCodeResult,
  type ProjectKbFile,
  type VasukiProject,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

const DEFAULT_HTML = `<main class="hero">
  <span class="badge">Vasuki Code Sandbox</span>
  <h1>Live Preview is ready.</h1>
  <p>Edit HTML, CSS or JavaScript and run it inside the sandboxed iframe.</p>
  <button id="demo">Click me</button>
</main>`;

const DEFAULT_CSS = `body {
  margin: 0;
  font-family: Inter, system-ui, sans-serif;
  background: #101114;
  color: #f7f7f8;
}
.hero {
  min-height: 100vh;
  display: grid;
  place-content: center;
  gap: 14px;
  padding: 32px;
  text-align: center;
}
.badge {
  width: max-content;
  margin: 0 auto;
  padding: 7px 12px;
  border: 1px solid #3a3d45;
  border-radius: 999px;
}
button {
  width: max-content;
  margin: 0 auto;
  padding: 10px 16px;
  border: 0;
  border-radius: 12px;
  cursor: pointer;
}`;

const DEFAULT_JS = `console.log("Sandbox started");
document.querySelector("#demo")?.addEventListener("click", () => {
  document.querySelector("h1").textContent = "JavaScript is working ðŸš€";
  console.log("Demo button clicked");
});`;

type Tab = "html" | "css" | "js";

export default function CodeLabPage() {
  const [projects, setProjects] = useState<VasukiProject[]>([]);
  const [projectId, setProjectId] = useState("");
  const [kbFiles, setKbFiles] = useState<ProjectKbFile[]>([]);
  const [mapText, setMapText] = useState("");
  const [instruction, setInstruction] = useState("");
  const [debugLog, setDebugLog] = useState("");
  const [agentResult, setAgentResult] = useState<ProjectCodeResult | null>(null);
  const [agentBusy, setAgentBusy] = useState(false);
  const [error, setError] = useState("");

  const [html, setHtml] = useState(DEFAULT_HTML);
  const [css, setCss] = useState(DEFAULT_CSS);
  const [js, setJs] = useState(DEFAULT_JS);
  const [tab, setTab] = useState<Tab>("html");
  const [autoRun, setAutoRun] = useState(true);
  const [revision, setRevision] = useState(0);
  const [consoleLines, setConsoleLines] = useState<string[]>([]);

  async function token() {
    const { data } = await supabase.auth.getSession();
    if (!data.session?.access_token) throw new Error("Please sign in to use Coding Agent.");
    return data.session.access_token;
  }

  async function loadProjects() {
    try {
      const rows = await fetchProjects(await token());
      setProjects(rows);
      if (!projectId && rows[0]?.id) setProjectId(rows[0].id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Projects could not be loaded.");
    }
  }

  async function loadKb(project: string) {
    if (!project) {
      setKbFiles([]);
      return;
    }
    try {
      setKbFiles(await fetchProjectKbFiles(await token(), project));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project KB could not be loaded.");
    }
  }

  useEffect(() => {
    void loadProjects();
  }, []);

  useEffect(() => {
    void loadKb(projectId);
    setMapText("");
    setAgentResult(null);
  }, [projectId]);

  useEffect(() => {
    const handler = (event: MessageEvent) => {
      const data = event.data as { source?: string; type?: string; value?: string };
      if (data?.source !== "vasuki-sandbox") return;
      const line = `[${data.type || "log"}] ${data.value || ""}`;
      setConsoleLines((current) => [...current.slice(-99), line]);
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  async function uploadFiles(fileList: FileList | null) {
    if (!projectId || !fileList?.length) return;
    setAgentBusy(true);
    setError("");
    try {
      await uploadProjectKbFiles(await token(), projectId, Array.from(fileList));
      await loadKb(projectId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setAgentBusy(false);
    }
  }

  async function removeKbFile(path: string) {
    if (!projectId) return;
    setAgentBusy(true);
    try {
      await deleteProjectKbFile(await token(), projectId, path);
      await loadKb(projectId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "File could not be removed.");
    } finally {
      setAgentBusy(false);
    }
  }

  async function analyzeCodebase() {
    if (!projectId) return;
    setAgentBusy(true);
    setError("");
    try {
      const result = await fetchProjectCodebaseMap(await token(), projectId);
      setMapText(JSON.stringify(result.map ?? result, null, 2));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Codebase analysis failed.");
    } finally {
      setAgentBusy(false);
    }
  }

  async function runAgent(mode: "patch" | "tests" | "debug") {
    if (!projectId || !instruction.trim()) return;
    setAgentBusy(true);
    setError("");
    setAgentResult(null);
    try {
      const accessToken = await token();
      const result =
        mode === "tests"
          ? await generateProjectTests(accessToken, projectId, instruction)
          : mode === "debug"
            ? await generateProjectDebugPlan(accessToken, projectId, instruction, debugLog)
            : await generateProjectPatch(accessToken, projectId, instruction);
      setAgentResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Coding Agent failed.");
    } finally {
      setAgentBusy(false);
    }
  }

  async function applyPlan() {
    if (!projectId || !agentResult?.plan?.changes?.length) return;
    if (!window.confirm("Apply these generated changes to the Project KB snapshot? Previous versions are saved.")) return;
    setAgentBusy(true);
    setError("");
    try {
      await applyProjectCodePlan(await token(), projectId, agentResult.plan.changes);
      await loadKb(projectId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Patch could not be applied.");
    } finally {
      setAgentBusy(false);
    }
  }

  const srcDoc = useMemo(() => {
    void revision;
    return `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<style>${css}</style>
</head>
<body>
${html}
<script>
(() => {
  const send = (type, values) => parent.postMessage({
    source: "vasuki-sandbox",
    type,
    value: values.map(v => {
      try { return typeof v === "string" ? v : JSON.stringify(v); }
      catch { return String(v); }
    }).join(" ")
  }, "*");
  ["log","warn","error","info"].forEach(type => {
    const original = console[type];
    console[type] = (...values) => { send(type, values); original.apply(console, values); };
  });
  window.addEventListener("error", e => send("error", [e.message]));
  window.addEventListener("unhandledrejection", e => send("error", [String(e.reason)]));
})();
try {
${js}
} catch (error) {
  console.error(error);
}
<\/script>
</body>
</html>`;
  }, [html, css, js, revision]);

  const value = tab === "html" ? html : tab === "css" ? css : js;
  const setValue = (next: string) => {
    if (tab === "html") setHtml(next);
    if (tab === "css") setCss(next);
    if (tab === "js") setJs(next);
    if (autoRun) setRevision((current) => current + 1);
  };

  function reset() {
    setHtml(DEFAULT_HTML);
    setCss(DEFAULT_CSS);
    setJs(DEFAULT_JS);
    setConsoleLines([]);
    setRevision((current) => current + 1);
  }

  async function copyDiff() {
    await navigator.clipboard.writeText(agentResult?.diff || "");
  }

  return (
    <main className="pv-code-shell">
      <header className="pv-code-head">
        <div>
          <p className="pv-phase5-kicker">V9 Â· Phase 2</p>
          <h1>Project Coding Agent</h1>
          <p>Project KB V2, cross-file understanding, multi-file patches, tests, debug and browser sandbox.</p>
        </div>
        <div className="pv-code-head-actions">
          <Link className="pv-phase5-ghost" href="/">â† Chat</Link>
          <Link className="pv-phase5-ghost" href="/projects">Projects</Link>
        </div>
      </header>

      <section className="pv-agent-grid">
        <div className="pv-agent-card">
          <strong>1. Project Knowledge Base V2</strong>
          <select value={projectId} onChange={(event) => setProjectId(event.target.value)}>
            <option value="">Select project</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>{project.name}</option>
            ))}
          </select>
          <label className="pv-agent-upload">
            Add project files
            <input
              type="file"
              multiple
              disabled={!projectId || agentBusy}
              onChange={(event) => void uploadFiles(event.target.files)}
            />
          </label>
          <button type="button" onClick={() => void analyzeCodebase()} disabled={!projectId || agentBusy}>
            Analyze codebase
          </button>
          <div className="pv-agent-file-list">
            {kbFiles.map((file) => (
              <div key={file.id}>
                <span><b>{file.path}</b><small>{file.language || "text"}</small></span>
                <button type="button" onClick={() => void removeKbFile(file.path)} disabled={agentBusy}>Ã—</button>
              </div>
            ))}
            {projectId && kbFiles.length === 0 ? <p>No Project KB files yet.</p> : null}
          </div>
        </div>

        <div className="pv-agent-card pv-agent-card--wide">
          <strong>2. Patch / Test / Debug Agent</strong>
          <textarea
            className="pv-agent-instruction"
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
            placeholder="Example: Add proper validation to the login API and update all affected tests."
          />
          <textarea
            value={debugLog}
            onChange={(event) => setDebugLog(event.target.value)}
            placeholder="Optional error/stack trace for Automatic Debug Mode"
          />
          <div className="pv-agent-actions">
            <button type="button" onClick={() => void runAgent("patch")} disabled={!projectId || !instruction.trim() || agentBusy}>
              Generate patch
            </button>
            <button type="button" onClick={() => void runAgent("tests")} disabled={!projectId || !instruction.trim() || agentBusy}>
              Generate tests
            </button>
            <button type="button" onClick={() => void runAgent("debug")} disabled={!projectId || !instruction.trim() || !debugLog.trim() || agentBusy}>
              Auto debug
            </button>
          </div>
          {agentBusy ? <p>Vasuki Coding Agent is workingâ€¦</p> : null}
          {error ? <div className="pv-v8-error">{error}</div> : null}
        </div>
      </section>

      {mapText ? (
        <section className="pv-agent-output">
          <div className="pv-agent-output-head">
            <strong>Cross-file Codebase Map</strong>
            <button type="button" onClick={() => setMapText("")}>Close</button>
          </div>
          <pre>{mapText}</pre>
        </section>
      ) : null}

      {agentResult ? (
        <section className="pv-agent-output">
          <div className="pv-agent-output-head">
            <div>
              <strong>{agentResult.plan?.summary || "Generated coding plan"}</strong>
              <small>{agentResult.provider ? `Provider: ${agentResult.provider}` : ""}</small>
            </div>
            <div>
              <button type="button" onClick={() => void copyDiff()}>Copy diff</button>
              <button type="button" onClick={() => void applyPlan()} disabled={agentBusy}>Apply to Project KB</button>
            </div>
          </div>
          <pre>{agentResult.diff || JSON.stringify(agentResult.plan, null, 2)}</pre>
        </section>
      ) : null}

      <section className="pv-code-sandbox-head">
        <div>
          <p className="pv-phase5-kicker">Browser Code Execution Sandbox</p>
          <h2>HTML + CSS + JavaScript</h2>
          <p>Execution stays inside an iframe with <code>sandbox=&quot;allow-scripts&quot;</code>; arbitrary server-side code execution is disabled.</p>
        </div>
        <div className="pv-code-head-actions">
          <button className="pv-phase5-ghost" type="button" onClick={reset}>Reset</button>
          <button className="pv-phase5-button" type="button" onClick={() => {
            setConsoleLines([]);
            setRevision((current) => current + 1);
          }}>Run</button>
        </div>
      </section>

      <section className="pv-code-grid">
        <div className="pv-code-editor">
          <div className="pv-code-tabs">
            {(["html", "css", "js"] as Tab[]).map((item) => (
              <button
                key={item}
                type="button"
                className={tab === item ? "is-active" : ""}
                onClick={() => setTab(item)}
              >
                {item.toUpperCase()}
              </button>
            ))}
            <label>
              <input
                type="checkbox"
                checked={autoRun}
                onChange={(event) => setAutoRun(event.target.checked)}
              />
              Auto-run
            </label>
          </div>
          <textarea
            value={value}
            onChange={(event) => setValue(event.target.value)}
            spellCheck={false}
            aria-label={`${tab} editor`}
          />
        </div>

        <div className="pv-code-preview">
          <div className="pv-code-preview-bar">
            <span /><span /><span /><strong>Sandbox Preview</strong>
          </div>
          <iframe
            key={revision}
            title="Live code preview"
            sandbox="allow-scripts"
            srcDoc={srcDoc}
          />
          <div className="pv-agent-console">
            <strong>Console</strong>
            <pre>{consoleLines.join("\n") || "No console output yet."}</pre>
          </div>
        </div>
      </section>
    </main>
  );
}

