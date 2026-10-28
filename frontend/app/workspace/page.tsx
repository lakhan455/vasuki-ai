"use client";

import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  createWorkspaceV76,
  deleteWorkspaceV76,
  fetchWorkspaceV76,
  fetchWorkspacesV76,
  saveWorkspaceV76,
  type WorkspaceItemV76,
  type WorkspaceKindV76,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";
import styles from "./page.module.css";

const DEFAULTS: Record<WorkspaceKindV76, string> = {
  document: "Start writing here...",
  markdown: "# New document\n\nStart writing here.",
  code: "// Start coding here\n",
  html: "<!doctype html>\n<html>\n  <body>\n    <h1>Hello Vasuki</h1>\n  </body>\n</html>\n",
  spreadsheet: "Item,Quantity,Amount\nExample,1,100\n",
};

const EXTENSIONS: Record<WorkspaceKindV76, string> = {
  document: "txt",
  markdown: "md",
  code: "txt",
  html: "html",
  spreadsheet: "csv",
};

async function accessToken() {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error("Please sign in again.");
  return token;
}

function cleanFileName(value: string) {
  return (
    value
      .trim()
      .replace(/[^\w.-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 80) || "vasuki-workspace"
  );
}

function csvRows(value: string) {
  return value
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .slice(0, 25)
    .map((line) => line.split(",").slice(0, 12));
}

export default function WorkspacePage() {
  const [items, setItems] = useState<WorkspaceItemV76[]>([]);
  const [active, setActive] = useState<WorkspaceItemV76 | null>(null);
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState<WorkspaceKindV76>("document");
  const [language, setLanguage] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [savedVersion, setSavedVersion] = useState(0);
  const [dirty, setDirty] = useState(false);

  const rows = useMemo(
    () => (kind === "spreadsheet" ? csvRows(content) : []),
    [kind, content],
  );

  async function openItem(item: WorkspaceItemV76) {
    setBusy("open");
    setError("");
    try {
      const token = await accessToken();
      const full = await fetchWorkspaceV76(token, item.id);
      setActive(full);
      setTitle(full.title);
      setKind(full.kind);
      setLanguage(full.language || "");
      setContent(full.content || "");
      setSavedVersion(full.version);
      setDirty(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Workspace could not be opened.");
    } finally {
      setBusy("");
    }
  }

  async function loadList(selectId?: string) {
    const token = await accessToken();
    const response = await fetchWorkspacesV76(token);
    setItems(response.items);
    if (selectId) {
      const chosen = response.items.find((item) => item.id === selectId);
      if (chosen) await openItem(chosen);
    }
  }

  useEffect(() => {
    void (async () => {
      setBusy("list");
      try {
        await loadList();
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Workspace could not be loaded.");
      } finally {
        setBusy("");
      }
    })();
  }, []);

  async function create(kindValue: WorkspaceKindV76) {
    setBusy("create");
    setError("");
    try {
      const token = await accessToken();
      const created = await createWorkspaceV76(token, {
        title: `New ${kindValue}`,
        kind: kindValue,
        language: kindValue === "code" ? "typescript" : "",
        content: DEFAULTS[kindValue],
      });
      await loadList(created.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Workspace could not be created.");
    } finally {
      setBusy("");
    }
  }

  async function save() {
    if (!active) return;
    setBusy("save");
    setError("");
    try {
      const token = await accessToken();
      const updated = await saveWorkspaceV76(token, active.id, {
        title,
        kind,
        language,
        content,
        expected_version: savedVersion,
      });
      setActive(updated);
      setSavedVersion(updated.version);
      setDirty(false);
      setItems((current) =>
        current
          .map((item) => (item.id === updated.id ? updated : item))
          .sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || ""))),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Workspace could not be saved.");
    } finally {
      setBusy("");
    }
  }

  async function remove() {
    if (!active) return;
    if (!window.confirm(`Delete "${active.title}"?`)) return;
    setBusy("delete");
    setError("");
    try {
      const token = await accessToken();
      await deleteWorkspaceV76(token, active.id);
      setItems((current) => current.filter((item) => item.id !== active.id));
      setActive(null);
      setTitle("");
      setContent("");
      setSavedVersion(0);
      setDirty(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Workspace could not be deleted.");
    } finally {
      setBusy("");
    }
  }

  function exportFile() {
    const ext =
      kind === "code" && language
        ? language.replace(/[^a-z0-9]/gi, "").toLowerCase() || "txt"
        : EXTENSIONS[kind];
    const blob = new Blob([content], {
      type:
        kind === "html"
          ? "text/html"
          : kind === "spreadsheet"
            ? "text/csv"
            : "text/plain",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${cleanFileName(title)}.${ext}`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brandRow}>
          <a href="/" className={styles.back}>← Chat</a>
          <strong>Live Workspace</strong>
        </div>

        <div className={styles.createGrid}>
          {(["document", "markdown", "code", "html", "spreadsheet"] as WorkspaceKindV76[]).map((value) => (
            <button key={value} onClick={() => void create(value)} disabled={Boolean(busy)}>
              + {value}
            </button>
          ))}
        </div>

        <div className={styles.list}>
          {busy === "list" ? <p className={styles.muted}>Loading…</p> : null}
          {!busy && items.length === 0 ? <p className={styles.muted}>No workspaces yet.</p> : null}
          {items.map((item) => (
            <button
              key={item.id}
              className={active?.id === item.id ? styles.activeItem : styles.item}
              onClick={() => void openItem(item)}
            >
              <span>{item.title}</span>
              <small>{item.kind} · v{item.version}</small>
            </button>
          ))}
        </div>
      </aside>

      <section className={styles.main}>
        {!active ? (
          <div className={styles.empty}>
            <h1>Artifacts / Live Workspace</h1>
            <p>Create an editable document, markdown note, code file, HTML preview, or CSV spreadsheet.</p>
          </div>
        ) : (
          <>
            <header className={styles.toolbar}>
              <input
                className={styles.title}
                value={title}
                onChange={(event) => {
                  setTitle(event.target.value);
                  setDirty(true);
                }}
                aria-label="Workspace title"
              />
              <select
                value={kind}
                onChange={(event) => {
                  setKind(event.target.value as WorkspaceKindV76);
                  setDirty(true);
                }}
              >
                <option value="document">Document</option>
                <option value="markdown">Markdown</option>
                <option value="code">Code</option>
                <option value="html">HTML</option>
                <option value="spreadsheet">Spreadsheet (CSV)</option>
              </select>
              {kind === "code" ? (
                <input
                  className={styles.language}
                  value={language}
                  onChange={(event) => {
                    setLanguage(event.target.value);
                    setDirty(true);
                  }}
                  placeholder="language"
                />
              ) : null}
              <button onClick={() => void save()} disabled={!dirty || Boolean(busy)}>
                {busy === "save" ? "Saving…" : dirty ? "Save" : "Saved"}
              </button>
              <button onClick={exportFile}>Export</button>
              <button className={styles.danger} onClick={() => void remove()} disabled={Boolean(busy)}>
                Delete
              </button>
            </header>

            {error ? <div className={styles.error}>{error}</div> : null}

            <div className={styles.versionBar}>
              <span>Version {savedVersion}</span>
              <span>{dirty ? "Unsaved changes" : "Synced"}</span>
              <span>{new Blob([content]).size.toLocaleString()} bytes</span>
            </div>

            <div className={styles.workspace}>
              <section className={styles.editorPane}>
                <div className={styles.paneLabel}>Editor</div>
                <textarea
                  value={content}
                  onChange={(event) => {
                    setContent(event.target.value);
                    setDirty(true);
                  }}
                  spellCheck={kind === "document" || kind === "markdown"}
                  aria-label="Workspace editor"
                />
              </section>

              <section className={styles.previewPane}>
                <div className={styles.paneLabel}>Live preview</div>
                <div className={styles.preview}>
                  {kind === "markdown" || kind === "document" ? (
                    <ReactMarkdown>{content}</ReactMarkdown>
                  ) : kind === "html" ? (
                    <iframe
                      title="HTML preview"
                      sandbox=""
                      srcDoc={content}
                      className={styles.frame}
                    />
                  ) : kind === "spreadsheet" ? (
                    rows.length ? (
                      <div className={styles.tableWrap}>
                        <table>
                          <tbody>
                            {rows.map((row, rowIndex) => (
                              <tr key={rowIndex}>
                                {row.map((cell, cellIndex) =>
                                  rowIndex === 0 ? (
                                    <th key={cellIndex}>{cell}</th>
                                  ) : (
                                    <td key={cellIndex}>{cell}</td>
                                  ),
                                )}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className={styles.muted}>Add CSV rows to preview them.</p>
                    )
                  ) : (
                    <pre><code>{content}</code></pre>
                  )}
                </div>
              </section>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
