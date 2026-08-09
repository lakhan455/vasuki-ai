"use client";

import { useEffect, useRef, useState } from "react";

import {
  fetchProjects,
  streamChat,
  type ChatMessage,
  type VasukiProject,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

type ResearchSource = {
  title?: string;
  url?: string;
  domain?: string;
  published_date?: string;
  source_type?: string;
};

export default function ResearchPage() {
  const [ready, setReady] = useState(false);
  const [token, setToken] = useState("");
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [provider, setProvider] = useState("");
  const [sources, setSources] = useState<ResearchSource[]>([]);
  const [projects, setProjects] = useState<VasukiProject[]>([]);
  const [projectId, setProjectId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    void (async () => {
      const { data } = await supabase.auth.getSession();
      const accessToken = data.session?.access_token || "";
      setToken(accessToken);
      if (accessToken) {
        try {
          setProjects((await fetchProjects(accessToken)).filter((item) => !item.archived));
        } catch {
          setProjects([]);
        }
      }
      setReady(true);
    })();
  }, []);

  async function runResearch() {
    const topic = query.trim();
    if (!topic || !token || busy) return;

    setBusy(true);
    setError("");
    setAnswer("");
    setProvider("");
    setSources([]);

    const controller = new AbortController();
    abortRef.current = controller;

    const prompt = [
      "DEEP RESEARCH V2.",
      "Research the topic thoroughly using current web evidence.",
      "Cross-check important claims, prefer authoritative/recent sources,",
      "state uncertainty when evidence conflicts, and finish with a concise conclusion.",
      "Do not invent citations or facts that are not supported by the supplied web context.",
      "",
      `TOPIC: ${topic}`,
    ].join("\n");

    const messages: ChatMessage[] = [{ role: "user", content: prompt }];
    let streamed = "";

    try {
      const meta = await streamChat(
        messages,
        {
          accessToken: token,
          useWeb: true,
          useMemory: true,
          useDocuments: false,
          documentIds: [],
          projectId: projectId || undefined,
          researchMode: true,
          cacheBypass: true,
          signal: controller.signal,
        },
        (chunk) => {
          streamed += chunk;
          setAnswer(streamed);
        },
      );

      setProvider(meta.provider || "");
      setSources(Array.isArray(meta.sources) ? (meta.sources as ResearchSource[]) : []);
    } catch (caught) {
      if (!controller.signal.aborted) {
        setError(caught instanceof Error ? caught.message : "Research failed.");
      }
    } finally {
      abortRef.current = null;
      setBusy(false);
    }
  }

  if (!ready) {
    return <main className="pv-phase5-shell"><section className="pv-phase5-card">Loading Deep Research…</section></main>;
  }

  if (!token) {
    return (
      <main className="pv-phase5-shell">
        <section className="pv-phase5-card">
          <h1>Deep Research V2</h1>
          <p>Please sign in from the main Vasuki AI page first.</p>
          <a className="pv-phase5-button" href="/">Open Vasuki AI</a>
        </section>
      </main>
    );
  }

  return (
    <main className="pv-phase5-shell">
      <section className="pv-phase5-card pv-phase5-wide">
        <div className="pv-phase5-head">
          <div>
            <p className="pv-phase5-kicker">V8 · Phase 5</p>
            <h1>Deep Research V2</h1>
            <p>Strong routing + live web verification + source-aware synthesis.</p>
          </div>
          <a className="pv-phase5-ghost" href="/">← Back to chat</a>
        </div>

        <div className="pv-phase5-controls">
          <select value={projectId} onChange={(event) => setProjectId(event.target.value)}>
            <option value="">No project context</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>{project.name}</option>
            ))}
          </select>
        </div>

        <textarea
          className="pv-phase5-textarea"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Example: Compare the latest confirmed AI coding agents, their strengths, limitations and best use cases."
          rows={6}
        />

        <div className="pv-phase5-actions">
          <button className="pv-phase5-button" type="button" onClick={() => void runResearch()} disabled={busy || !query.trim()}>
            {busy ? "Researching…" : "Run deep research"}
          </button>
          {busy ? (
            <button className="pv-phase5-ghost" type="button" onClick={() => abortRef.current?.abort()}>
              Stop
            </button>
          ) : null}
        </div>

        {error ? <div className="pv-phase5-error">{error}</div> : null}

        {answer ? (
          <section className="pv-phase5-result">
            <div className="pv-phase5-result-head">
              <strong>Research answer</strong>
              <span>{provider || "auto"}</span>
            </div>
            <pre>{answer}</pre>
          </section>
        ) : null}

        {sources.length > 0 ? (
          <section className="pv-phase5-sources">
            <h2>Sources used</h2>
            <div className="pv-phase5-source-grid">
              {sources.map((source, index) => (
                <a
                  key={`${source.url || source.title || "source"}-${index}`}
                  href={source.url || "#"}
                  target="_blank"
                  rel="noreferrer"
                  className="pv-phase5-source"
                >
                  <strong>{source.title || `Source ${index + 1}`}</strong>
                  <span>{source.domain || source.source_type || "web"}</span>
                  {source.published_date ? <small>{source.published_date}</small> : null}
                </a>
              ))}
            </div>
          </section>
        ) : null}
      </section>
    </main>
  );
}
