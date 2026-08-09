"use client";

import { useMemo, useState } from "react";

const DEFAULT_HTML = `<main class="hero">
  <span class="badge">Vasuki Code Lab</span>
  <h1>Live Preview is ready.</h1>
  <p>Edit HTML, CSS or JavaScript and see the result instantly.</p>
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

const DEFAULT_JS = `document.querySelector("#demo")?.addEventListener("click", () => {
  document.querySelector("h1").textContent = "JavaScript is working 🚀";
});`;

type Tab = "html" | "css" | "js";

export default function CodeLabPage() {
  const [html, setHtml] = useState(DEFAULT_HTML);
  const [css, setCss] = useState(DEFAULT_CSS);
  const [js, setJs] = useState(DEFAULT_JS);
  const [tab, setTab] = useState<Tab>("html");
  const [autoRun, setAutoRun] = useState(true);
  const [revision, setRevision] = useState(0);

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
try {
${js}
} catch (error) {
  document.body.insertAdjacentHTML("beforeend", "<pre style='color:#ff8a8a;padding:16px'>" + String(error) + "</pre>");
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
    setRevision((current) => current + 1);
  }

  async function copyCombined() {
    await navigator.clipboard.writeText(srcDoc);
  }

  function downloadHtml() {
    const blob = new Blob([srcDoc], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "vasuki-code-lab.html";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="pv-code-shell">
      <header className="pv-code-head">
        <div>
          <p className="pv-phase5-kicker">V8 · Phase 5</p>
          <h1>Live Code Lab</h1>
          <p>HTML + CSS + JavaScript preview sandbox.</p>
        </div>
        <div className="pv-code-head-actions">
          <a className="pv-phase5-ghost" href="/">← Chat</a>
          <button className="pv-phase5-ghost" type="button" onClick={reset}>Reset</button>
          <button className="pv-phase5-ghost" type="button" onClick={() => void copyCombined()}>Copy HTML</button>
          <button className="pv-phase5-button" type="button" onClick={downloadHtml}>Download</button>
        </div>
      </header>

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
            {!autoRun ? (
              <button type="button" onClick={() => setRevision((current) => current + 1)}>Run</button>
            ) : null}
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
            <span />
            <span />
            <span />
            <strong>Preview</strong>
          </div>
          <iframe
            key={revision}
            title="Live code preview"
            sandbox="allow-scripts"
            srcDoc={srcDoc}
          />
        </div>
      </section>
    </main>
  );
}
