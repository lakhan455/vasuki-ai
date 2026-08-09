"use client";

import { ChangeEvent, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  askDocumentsV3,
  compareDocumentsV3,
  extractDocumentsV3,
  ocrDocumentV3,
  type DocumentIntelligenceV3,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

const MAX_FILES = 8;
const MAX_FILE = 15 * 1024 * 1024;
const MAX_TOTAL = 50 * 1024 * 1024;

async function token() {
  const { data } = await supabase.auth.getSession();
  const value = data.session?.access_token;
  if (!value) throw new Error("Please sign in again.");
  return value;
}

function sizeLabel(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentsPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [prompt, setPrompt] = useState("Summarize the most important information and cite every important claim.");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<DocumentIntelligenceV3 | null>(null);

  const totalBytes = useMemo(() => files.reduce((sum, file) => sum + file.size, 0), [files]);

  function chooseFiles(event: ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(event.target.files || []);
    event.target.value = "";
    const next = [...files];
    const messages: string[] = [];
    for (const file of picked) {
      if (file.size > MAX_FILE) {
        messages.push(`${file.name}: larger than 15 MB`);
        continue;
      }
      if (!next.some((item) => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified)) {
        next.push(file);
      }
    }
    const limited = next.slice(0, MAX_FILES);
    const total = limited.reduce((sum, file) => sum + file.size, 0);
    if (next.length > MAX_FILES) messages.push(`Only ${MAX_FILES} files can be used at once.`);
    if (total > MAX_TOTAL) {
      setError("Combined file size must be 50 MB or smaller.");
      return;
    }
    setFiles(limited);
    setError(messages.join(" | "));
    setResult(null);
  }

  async function run(mode: "extract" | "ocr" | "ask" | "compare") {
    if (!files.length) return setError("Upload at least one document.");
    if (mode === "compare" && files.length < 2) return setError("Upload at least two documents to compare.");
    setBusy(mode);
    setError("");
    setResult(null);
    try {
      const accessToken = await token();
      if (mode === "extract") {
        setResult(await extractDocumentsV3(accessToken, files));
      } else if (mode === "ocr") {
        setResult(await ocrDocumentV3(accessToken, files[0]));
      } else if (mode === "compare") {
        setResult(await compareDocumentsV3(accessToken, files, prompt));
      } else {
        if (!prompt.trim()) throw new Error("Write a question first.");
        setResult(await askDocumentsV3(accessToken, files, prompt));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Document processing failed.");
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="pv-v9-doc-page">
      <header className="pv-v9-studio-head">
        <div>
          <p className="pv-v8-kicker">Vasuki AI V9 Phase 3</p>
          <h1>Document Intelligence</h1>
          <p>OCR V2, structured extraction, page/section citations and multi-document comparison.</p>
        </div>
        <nav className="pv-v9-studio-nav">
          <a href="/images">Image Studio</a>
          <a href="/">Back to chat</a>
        </nav>
      </header>

      <section className="pv-v9-doc-grid">
        <div className="pv-v9-control-card">
          <label className="pv-v9-file-picker">
            <span>Add PDF, DOCX, TXT, MD or images</span>
            <input
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.md,.jpg,.jpeg,.png,.webp,.gif"
              onChange={chooseFiles}
            />
          </label>
          <small>{files.length}/{MAX_FILES} files · {sizeLabel(totalBytes)} / 50 MB</small>

          <div className="pv-v9-doc-file-list">
            {files.map((file, index) => (
              <div key={`${file.name}-${file.size}-${file.lastModified}`}>
                <div><strong>{file.name}</strong><small>{sizeLabel(file.size)}</small></div>
                <button type="button" onClick={() => setFiles((current) => current.filter((_item, itemIndex) => itemIndex !== index))}>Remove</button>
              </div>
            ))}
          </div>

          <label>
            <span>Question / compare focus</span>
            <textarea
              rows={6}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Example: Compare all price, date and policy changes and cite each source."
            />
          </label>

          <div className="pv-v9-doc-actions">
            <button type="button" disabled={Boolean(busy)} onClick={() => void run("ask")}>
              {busy === "ask" ? "Answering..." : "Ask with citations"}
            </button>
            <button type="button" disabled={Boolean(busy)} onClick={() => void run("compare")}>
              {busy === "compare" ? "Comparing..." : "Compare documents"}
            </button>
            <button type="button" disabled={Boolean(busy)} onClick={() => void run("extract")}>
              {busy === "extract" ? "Extracting..." : "Structured extract"}
            </button>
            <button type="button" disabled={Boolean(busy)} onClick={() => void run("ocr")}>
              {busy === "ocr" ? "Reading..." : "OCR first file"}
            </button>
          </div>

          <p className="pv-v9-fineprint">
            Native PDF text gets page citations. DOCX/TXT gets section or line citations. A scanned-PDF vision fallback may not have reliable page boundaries.
          </p>
          {error ? <div className="pv-v8-error">{error}</div> : null}
        </div>

        <div className="pv-v9-doc-result">
          <h2>Document result</h2>
          {!result ? <div className="pv-v8-empty">Upload files and choose an action.</div> : null}

          {result?.answer ? (
            <div className="pv-v9-doc-answer"><ReactMarkdown>{result.answer}</ReactMarkdown></div>
          ) : null}

          {result?.text ? (
            <pre className="pv-v9-ocr-text">{result.text}</pre>
          ) : null}

          {result?.comparison ? (
            <section className="pv-v9-compare-box">
              <h3>Deterministic comparison</h3>
              <p><strong>{result.comparison.left}</strong> vs <strong>{result.comparison.right}</strong></p>
              <p>Text similarity: <strong>{result.comparison.similarity_percent ?? 0}%</strong></p>
              {(result.comparison.added_samples || []).length ? (
                <details><summary>Added / new samples</summary>{result.comparison.added_samples?.map((item) => <p key={item}>{item}</p>)}</details>
              ) : null}
              {(result.comparison.removed_samples || []).length ? (
                <details><summary>Removed / old samples</summary>{result.comparison.removed_samples?.map((item) => <p key={item}>{item}</p>)}</details>
              ) : null}
            </section>
          ) : null}

          {(result?.citations || []).length ? (
            <section className="pv-v9-citations">
              <h3>Citations</h3>
              {result?.citations?.map((citation) => (
                <article key={citation.citation_id}>
                  <strong>[{citation.citation_id}] {citation.document}</strong>
                  <small>
                    {citation.page ? `Page ${citation.page}` : citation.section || "Document section"}
                    {citation.kind ? ` · ${citation.kind}` : ""}
                  </small>
                  <p>{citation.excerpt}</p>
                </article>
              ))}
            </section>
          ) : null}

          {(result?.documents || (result?.document ? [result.document] : [])).map((document) => (
            <details className="pv-v9-structure" key={document.source_id}>
              <summary>{document.source_id} · {document.name} · {document.blocks.length} blocks</summary>
              {document.blocks.slice(0, 30).map((block) => (
                <article key={block.citation_id}>
                  <strong>[{block.citation_id}]</strong>
                  <small>{block.page ? `Page ${block.page}` : block.section || block.kind}</small>
                  <p>{block.text}</p>
                </article>
              ))}
            </details>
          ))}

          {(result?.warnings || []).length ? (
            <details className="pv-smart-warnings">
              <summary>Warnings</summary>
              {result?.warnings?.map((warning) => <p key={warning}>{warning}</p>)}
            </details>
          ) : null}
        </div>
      </section>
    </main>
  );
}
