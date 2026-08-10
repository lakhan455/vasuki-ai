"use client";

import { useEffect, useRef, useState } from "react";

type InstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

const commands = [
  { label: "New chat", href: "/", keywords: "new chat home" },
  { label: "Image Studio", href: "/images", keywords: "image generate studio" },
  { label: "Document Intelligence", href: "/documents", keywords: "pdf docx document" },
  { label: "Projects", href: "/projects", keywords: "project workspace code" },
  { label: "Operations Center", href: "/operations", keywords: "jobs notifications usage" },
  { label: "Files", href: "/files", keywords: "downloads artifacts files" },
  { label: "Account & Privacy", href: "/account", keywords: "export delete storage push privacy" },
  { label: "Owner Dashboard", href: "/owner", keywords: "owner cost quota feature flags" },
];

export default function ProductivityShellV9() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [online, setOnline] = useState(true);
  const [installPrompt, setInstallPrompt] = useState<InstallPromptEvent | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setOnline(navigator.onLine);
    const onlineHandler = () => setOnline(true);
    const offlineHandler = () => setOnline(false);
    window.addEventListener("online", onlineHandler);
    window.addEventListener("offline", offlineHandler);

    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker.register("/sw.js");
    }

    const installHandler = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as InstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", installHandler);

    return () => {
      window.removeEventListener("online", onlineHandler);
      window.removeEventListener("offline", offlineHandler);
      window.removeEventListener("beforeinstallprompt", installHandler);
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.isContentEditable;

      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
        return;
      }
      if (event.key === "Escape" && paletteOpen) {
        event.preventDefault();
        setPaletteOpen(false);
        return;
      }
      if (typing) return;
      if (event.altKey && event.key.toLowerCase() === "n") {
        event.preventDefault();
        window.location.assign("/");
      }
      if (event.altKey && event.key.toLowerCase() === "o") {
        event.preventDefault();
        window.location.assign("/operations");
      }
      if (event.altKey && event.key.toLowerCase() === "a") {
        event.preventDefault();
        window.location.assign("/account");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [paletteOpen]);

  useEffect(() => {
    if (paletteOpen) {
      requestAnimationFrame(() => inputRef.current?.focus());
    } else {
      setQuery("");
    }
  }, [paletteOpen]);

  const normalized = query.trim().toLowerCase();
  const visible = commands.filter((command) =>
    !normalized ||
    `${command.label} ${command.keywords}`.toLowerCase().includes(normalized),
  );

  async function installApp() {
    if (!installPrompt) return;
    await installPrompt.prompt();
    await installPrompt.userChoice;
    setInstallPrompt(null);
    setPaletteOpen(false);
  }

  return (
    <>
      <button
        type="button"
        className="pv-v9-command-trigger"
        aria-label="Open command palette"
        title="Command palette · Ctrl/⌘ K"
        onClick={() => setPaletteOpen(true)}
      >
        ⌘K
      </button>

      {!online ? (
        <div className="pv-v9-offline-banner" role="status" aria-live="polite">
          Offline mode · cached pages are available, AI requests need internet.
        </div>
      ) : null}

      {paletteOpen ? (
        <div
          className="pv-v9-palette-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target) setPaletteOpen(false);
          }}
        >
          <section
            className="pv-v9-palette"
            role="dialog"
            aria-modal="true"
            aria-labelledby="pv-v9-palette-title"
          >
            <div className="pv-v9-palette-head">
              <div>
                <p className="pv-v8-kicker">Vasuki AI</p>
                <h2 id="pv-v9-palette-title">Command Palette</h2>
              </div>
              <button type="button" onClick={() => setPaletteOpen(false)} aria-label="Close command palette">
                Esc
              </button>
            </div>
            <label className="pv-sr-only" htmlFor="pv-v9-command-search">Search commands</label>
            <input
              id="pv-v9-command-search"
              ref={inputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search commands..."
              autoComplete="off"
            />
            <div className="pv-v9-command-list" role="listbox" aria-label="Commands">
              {visible.map((command) => (
                <button
                  key={command.href}
                  type="button"
                  role="option"
                  aria-selected="false"
                  onClick={() => window.location.assign(command.href)}
                >
                  <span>{command.label}</span>
                  <small>{command.href}</small>
                </button>
              ))}
              {installPrompt ? (
                <button type="button" role="option" aria-selected="false" onClick={() => void installApp()}>
                  <span>Install Vasuki AI</span>
                  <small>PWA</small>
                </button>
              ) : null}
              {!visible.length ? <p className="pv-v9-command-empty">No matching command.</p> : null}
            </div>
            <footer>
              <span>Ctrl/⌘ K · palette</span>
              <span>Alt N · new chat</span>
              <span>Alt O · operations</span>
              <span>Alt A · account</span>
            </footer>
          </section>
        </div>
      ) : null}
    </>
  );
}
