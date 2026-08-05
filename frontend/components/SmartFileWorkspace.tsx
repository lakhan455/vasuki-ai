"use client";

import { ChangeEvent, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import {
  analyzeSmartFiles,
  type SmartFileArtifact,
  type SmartFileResponse,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

const MAX_FILES = 8;
const MAX_FILE_BYTES = 15 * 1024 * 1024;
const MAX_TOTAL_BYTES = 50 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = new Set([
  ".pdf",
  ".docx",
  ".txt",
  ".md",
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".gif",
]);

function extension(name: string) {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index).toLowerCase() : "";
}

function sizeLabel(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function DownloadCard({ artifact }: { artifact: SmartFileArtifact }) {
  const label = artifact.name.toLowerCase().endsWith(".pdf")
    ? "PDF"
    : artifact.name.toLowerCase().endsWith(".docx")
      ? "DOCX"
      : artifact.name.toLowerCase().endsWith(".png")
        ? "PNG"
        : "TXT";

  return (
    <a
      className="pv-smart-download"
      href={artifact.data_url}
      download={artifact.name}
      aria-label={`Download ${artifact.name}`}
    >
      <span className="pv-smart-download-icon">↓</span>
      <span className="pv-smart-download-copy">
        <strong>{artifact.name}</strong>
        <small>{label} · {sizeLabel(artifact.size_bytes)}</small>
      </span>
      <span className="pv-smart-download-action">Download</span>
    </a>
  );
}

export default function SmartFileWorkspace({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<SmartFileResponse | null>(null);

  const totalBytes = useMemo(
    () => files.reduce((sum, file) => sum + file.size, 0),
    [files],
  );

  if (!open) return null;

  function addFiles(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.target.files || []);
    event.target.value = "";
    if (selected.length === 0) return;

    const next = [...files];
    const errors: string[] = [];
    for (const file of selected) {
      if (!ACCEPTED_EXTENSIONS.has(extension(file.name))) {
        errors.push(`${file.name}: unsupported type`);
        continue;
      }
      if (file.size > MAX_FILE_BYTES) {
        errors.push(`${file.name}: larger than 15 MB`);
        continue;
      }
      const duplicate = next.some(
        (item) =>
          item.name === file.name &&
          item.size === file.size &&
          item.lastModified === file.lastModified,
      );
      if (!duplicate) next.push(file);
    }

    const limited = next.slice(0, MAX_FILES);
    const limitedBytes = limited.reduce((sum, file) => sum + file.size, 0);
    if (next.length > MAX_FILES) errors.push(`Only ${MAX_FILES} files can be used at once.`);
    if (limitedBytes > MAX_TOTAL_BYTES) {
      errors.push("Combined file size must be 50 MB or smaller.");
      return setError(errors.join(" | "));
    }

    setFiles(limited);
    setError(errors.join(" | "));
    setResult(null);
  }

  async function submit() {
    const instruction = prompt.trim();
    if (!instruction || busy) return;

    setBusy(true);
    setError("");
    setResult(null);

    try {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session?.access_token) {
        throw new Error("Login session expired. Please sign in again.");
      }
      const response = await analyzeSmartFiles(
        files,
        instruction,
        session.access_token,
      );
      setResult(response);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Smart file processing failed. Please retry.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pv-smart-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="pv-smart-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Smart files"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="pv-smart-header">
          <div>
            <span className="pv-smart-eyebrow">VASUKI AI</span>
            <h2>Smart files</h2>
            <p>Analyze multiple documents, solve question papers and create downloadable files.</p>
          </div>
          <button type="button" className="pv-smart-close" onClick={onClose} aria-label="Close smart files">×</button>
        </header>

        <div className="pv-smart-body">
          <div className="pv-smart-upload-zone">
            <input
              ref={inputRef}
              type="file"
              multiple
              className="pv-file-input"
              accept=".pdf,.docx,.txt,.md,.jpg,.jpeg,.png,.webp,.gif"
              onChange={addFiles}
            />
            <button type="button" onClick={() => inputRef.current?.click()}>
              <span aria-hidden="true">＋</span>
              Add PDF, DOCX, TXT, notes or images
            </button>
            <small>Up to 8 files · 15 MB each · 50 MB combined</small>
          </div>

          {files.length > 0 && (
            <div className="pv-smart-file-list">
              {files.map((file, index) => (
                <div className="pv-smart-file-chip" key={`${file.name}-${file.size}-${file.lastModified}`}>
                  <span className="pv-smart-file-type">{extension(file.name).replace(".", "").toUpperCase()}</span>
                  <span className="pv-smart-file-copy">
                    <strong>{file.name}</strong>
                    <small>{sizeLabel(file.size)}</small>
                  </span>
                  <button
                    type="button"
                    aria-label={`Remove ${file.name}`}
                    onClick={() => {
                      setFiles((current) => current.filter((_item, itemIndex) => itemIndex !== index));
                      setResult(null);
                    }}
                  >
                    ×
                  </button>
                </div>
              ))}
              <div className="pv-smart-total">{files.length}/{MAX_FILES} files · {sizeLabel(totalBytes)}</div>
            </div>
          )}

          <label className="pv-smart-prompt">
            <span>What should Vasuki AI do?</span>
            <textarea
              rows={5}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Example: Answer every question in this PDF in order, then create a downloadable PDF."
            />
          </label>

          <div className="pv-smart-suggestions">
            {[
              "Answer every question in this question paper in order.",
              "Combine these notes into one printable one-sheet PDF.",
              "Compare all uploaded files and create revision notes.",
              "Create a QR image and PDF for https://vasukinfc.in",
            ].map((suggestion) => (
              <button type="button" key={suggestion} onClick={() => setPrompt(suggestion)}>{suggestion}</button>
            ))}
          </div>

          <div className="pv-smart-submit-row">
            <button
              type="button"
              className="pv-smart-clear"
              onClick={() => {
                setFiles([]);
                setPrompt("");
                setResult(null);
                setError("");
              }}
            >
              Clear
            </button>
            <button
              type="button"
              className="pv-smart-submit"
              disabled={!prompt.trim() || busy}
              onClick={() => void submit()}
            >
              {busy ? "Analyzing…" : "Analyze with Vasuki AI"}
            </button>
          </div>

          {error && <div className="pv-smart-error">{error}</div>}

          {result && (
            <section className="pv-smart-result">
              <div className="pv-smart-result-title">
                <div>
                  <span>RESULT</span>
                  <h3>Vasuki AI response</h3>
                </div>
                {result.processed_files.length > 0 && (
                  <small>{result.processed_files.length} file{result.processed_files.length === 1 ? "" : "s"} analyzed</small>
                )}
              </div>
              <div className="pv-smart-markdown">
                <ReactMarkdown>{result.answer}</ReactMarkdown>
              </div>
              {result.files.length > 0 && (
                <div className="pv-smart-downloads">
                  {result.files.map((artifact) => (
                    <DownloadCard artifact={artifact} key={`${artifact.name}-${artifact.size_bytes}`} />
                  ))}
                </div>
              )}
              {result.warnings.length > 0 && (
                <details className="pv-smart-warnings">
                  <summary>File warnings</summary>
                  {result.warnings.map((warning) => <p key={warning}>{warning}</p>)}
                </details>
              )}
            </section>
          )}

          <p className="pv-smart-privacy">Files are processed for this request. A downloadable file is created only when your instruction explicitly asks for one.</p>
        </div>
      </section>
    </div>
  );
}
