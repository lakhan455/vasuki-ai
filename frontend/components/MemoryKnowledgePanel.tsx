"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";

import {
  addMemory,
  fetchDocuments,
  fetchMemory,
  removeKnowledgeDocument,
  removeMemory,
  updateMemoryEnabled,
  uploadKnowledgeDocument,
  type KnowledgeDocument,
  type MemoryItem,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

type Props = {
  open: boolean;
  onClose: () => void;
  memoryEnabled: boolean;
  onMemoryEnabledChange: (enabled: boolean) => void;
  documentsEnabled: boolean;
  onDocumentsEnabledChange: (enabled: boolean) => void;
  selectedDocumentIds: string[];
  onSelectedDocumentIdsChange: (ids: string[]) => void;
};

function formatBytes(value?: number) {
  const bytes = Number(value || 0);
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

async function accessToken() {
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session?.access_token) {
    throw new Error("Login session expired. Please sign in again.");
  }

  return session.access_token;
}

export default function MemoryKnowledgePanel({
  open,
  onClose,
  memoryEnabled,
  onMemoryEnabledChange,
  documentsEnabled,
  onDocumentsEnabledChange,
  selectedDocumentIds,
  onSelectedDocumentIdsChange,
}: Props) {
  const [tab, setTab] = useState<"memory" | "documents">("memory");
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [memoryText, setMemoryText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;

    let active = true;
    setError("");
    setBusy(true);

    void (async () => {
      try {
        const token = await accessToken();
        const [memoryData, documentData] = await Promise.all([
          fetchMemory(token),
          fetchDocuments(token),
        ]);

        if (!active) return;
        setMemories(memoryData.memories);
        setDocuments(documentData);
        onMemoryEnabledChange(memoryData.enabled);
      } catch (caughtError) {
        if (!active) return;
        setError(
          caughtError instanceof Error
            ? caughtError.message
            : "Memory and documents could not be loaded.",
        );
      } finally {
        if (active) setBusy(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [open, onMemoryEnabledChange]);

  useEffect(() => {
    if (!open) return;

    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  async function toggleMemory(enabled: boolean) {
    setError("");
    onMemoryEnabledChange(enabled);

    try {
      const token = await accessToken();
      await updateMemoryEnabled(token, enabled);
    } catch (caughtError) {
      onMemoryEnabledChange(!enabled);
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Memory setting could not be updated.",
      );
    }
  }

  async function saveMemory() {
    const value = memoryText.trim();
    if (!value || busy) return;

    setBusy(true);
    setError("");

    try {
      const token = await accessToken();
      await addMemory(token, value);
      const data = await fetchMemory(token);
      setMemories(data.memories);
      setMemoryText("");
      onMemoryEnabledChange(true);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Memory could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function deleteMemory(id: string) {
    setBusy(true);
    setError("");

    try {
      const token = await accessToken();
      await removeMemory(token, id);
      setMemories((current) =>
        current.filter((memory) => memory.id !== id),
      );
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Memory could not be deleted.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function uploadDocument(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || busy) return;

    setBusy(true);
    setError("");

    try {
      const token = await accessToken();
      await uploadKnowledgeDocument(token, file);
      const updated = await fetchDocuments(token);
      setDocuments(updated);
      onDocumentsEnabledChange(true);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Document could not be uploaded.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function deleteDocument(id: string) {
    setBusy(true);
    setError("");

    try {
      const token = await accessToken();
      await removeKnowledgeDocument(token, id);
      setDocuments((current) =>
        current.filter((document) => document.id !== id),
      );
      onSelectedDocumentIdsChange(
        selectedDocumentIds.filter((documentId) => documentId !== id),
      );
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Document could not be deleted.",
      );
    } finally {
      setBusy(false);
    }
  }

  function toggleDocument(id: string) {
    const readyIds = documents
      .filter((document) => document.status === "ready")
      .map((document) => document.id);

    if (selectedDocumentIds.length === 0) {
      onSelectedDocumentIdsChange(
        readyIds.filter((documentId) => documentId !== id),
      );
      return;
    }

    const exists = selectedDocumentIds.includes(id);
    const next = exists
      ? selectedDocumentIds.filter((documentId) => documentId !== id)
      : [...selectedDocumentIds, id];

    onSelectedDocumentIdsChange(
      next.length === readyIds.length ? [] : next,
    );
  }

  return (
    <div
      className="pv-knowledge-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="pv-knowledge-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Memory and document knowledge"
      >
        <header className="pv-knowledge-header">
          <div>
            <strong>Vasuki Memory & Knowledge</strong>
            <small>Private to your Google account</small>
          </div>
          <button
            type="button"
            className="pv-knowledge-close"
            onClick={onClose}
            aria-label="Close"
          >
            Ã—
          </button>
        </header>

        <div className="pv-knowledge-tabs">
          <button
            type="button"
            className={tab === "memory" ? "active" : ""}
            onClick={() => setTab("memory")}
          >
            ðŸ§  Personal memory
          </button>
          <button
            type="button"
            className={tab === "documents" ? "active" : ""}
            onClick={() => setTab("documents")}
          >
            ðŸ“š Documents
          </button>
        </div>

        {error && <div className="pv-knowledge-error">{error}</div>}

        <div className="pv-knowledge-body">
          {tab === "memory" ? (
            <>
              <label className="pv-toggle-row">
                <span>
                  <strong>Use personal memory</strong>
                  <small>
                    Saved preferences will personalize future answers.
                  </small>
                </span>
                <input
                  type="checkbox"
                  checked={memoryEnabled}
                  onChange={(event) =>
                    void toggleMemory(event.target.checked)
                  }
                />
              </label>

              <div className="pv-memory-add">
                <textarea
                  rows={3}
                  value={memoryText}
                  maxLength={600}
                  onChange={(event) => setMemoryText(event.target.value)}
                  placeholder="Example: I prefer short, concise answers."
                />
                <button
                  type="button"
                  onClick={() => void saveMemory()}
                  disabled={busy || !memoryText.trim()}
                >
                  Save memory
                </button>
              </div>

              <p className="pv-panel-note">
                Passwords, API keys, OTPs, Aadhaar numbers, and other sensitive information
                are not saved to memory.
              </p>

              <div className="pv-memory-list">
                {memories.length === 0 && !busy ? (
                  <p className="pv-panel-empty">
                    No personal memories saved yet.
                  </p>
                ) : (
                  memories.map((memory) => (
                    <div className="pv-memory-row" key={memory.id}>
                      <span>{memory.memory_text}</span>
                      <button
                        type="button"
                        onClick={() => void deleteMemory(memory.id)}
                        disabled={busy}
                        aria-label="Delete memory"
                      >
                        Delete
                      </button>
                    </div>
                  ))
                )}
              </div>
            </>
          ) : (
            <>
              <label className="pv-toggle-row">
                <span>
                  <strong>Use document knowledge in chat</strong>
                  <small>
                    Vasuki AI will retrieve relevant passages before answering.
                  </small>
                </span>
                <input
                  type="checkbox"
                  checked={documentsEnabled}
                  onChange={(event) =>
                    onDocumentsEnabledChange(event.target.checked)
                  }
                />
              </label>

              <input
                ref={fileInputRef}
                className="pv-file-input"
                type="file"
                accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
                onChange={(event) => void uploadDocument(event)}
              />

              <button
                type="button"
                className="pv-document-upload"
                onClick={() => fileInputRef.current?.click()}
                disabled={busy}
              >
                {busy ? "Processingâ€¦" : "Upload PDF, DOCX, TXT or MD"}
              </button>

              <p className="pv-panel-note">
                Document text is split into private searchable chunks. Maximum
                15 MB; scanned PDFs need readable OCR text.
              </p>

              {documents.length > 0 && (
                <button
                  type="button"
                  className="pv-use-all-docs"
                  onClick={() => onSelectedDocumentIdsChange([])}
                >
                  Use all ready documents
                </button>
              )}

              <div className="pv-document-list">
                {documents.length === 0 && !busy ? (
                  <p className="pv-panel-empty">
                    No documents in the knowledge base yet.
                  </p>
                ) : (
                  documents.map((document) => {
                    const selected =
                      document.status === "ready" &&
                      (
                        selectedDocumentIds.length === 0 ||
                        selectedDocumentIds.includes(document.id)
                      );

                    return (
                      <div className="pv-document-row" key={document.id}>
                        <input
                          type="checkbox"
                          checked={selected}
                          disabled={document.status !== "ready"}
                          onChange={() => toggleDocument(document.id)}
                        />
                        <span className="pv-document-copy">
                          <strong>{document.name}</strong>
                          <small>
                            {formatBytes(document.size_bytes)} Â·{" "}
                            {document.status || "processing"} Â·{" "}
                            {document.chunk_count || 0} chunks
                          </small>
                        </span>
                        <button
                          type="button"
                          onClick={() => void deleteDocument(document.id)}
                          disabled={busy}
                        >
                          Delete
                        </button>
                      </div>
                    );
                  })
                )}
              </div>
            </>
          )}
        </div>

        <footer className="pv-knowledge-footer">
          <span>
            {busy ? "Please waitâ€¦" : "Changes save automatically."}
          </span>
          <button type="button" onClick={onClose}>
            Done
          </button>
        </footer>
      </section>
    </div>
  );
}
