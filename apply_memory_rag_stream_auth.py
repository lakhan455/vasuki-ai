from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"

TARGETS = {
    "config": ROOT / "backend" / "app" / "config.py",
    "schemas": ROOT / "backend" / "app" / "schemas.py",
    "main": ROOT / "backend" / "app" / "main.py",
    "chat": ROOT / "backend" / "app" / "services" / "chat.py",
    "requirements": ROOT / "backend" / "requirements.txt",
    "env_example": ROOT / "backend" / ".env.example",
    "api": ROOT / "frontend" / "lib" / "api.ts",
    "chat_app": ROOT / "frontend" / "components" / "ChatApp.tsx",
    "css": ROOT / "frontend" / "app" / "globals.css",
}


def read_asset(name: str) -> str:
    path = ASSETS / name
    if not path.exists():
        raise RuntimeError(f"Installer asset missing: {path}")
    return path.read_text(encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"[OK] Already applied: {label}")
        return text
    if old not in text:
        raise RuntimeError(f"Patch point not found: {label}")
    print(f"[UPDATED] {label}")
    return text.replace(old, new, 1)


def regex_replace_once(
    text: str,
    pattern: str,
    replacement: str,
    label: str,
) -> str:
    compiled = re.compile(pattern, flags=re.S)
    if replacement in text:
        print(f"[OK] Already applied: {label}")
        return text
    if not compiled.search(text):
        raise RuntimeError(f"Regex patch point not found: {label}")
    print(f"[UPDATED] {label}")
    return compiled.sub(lambda _match: replacement, text, count=1)


def backup_files() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ROOT / f"memory-rag-stream-auth-backup-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    for path in TARGETS.values():
        if not path.exists():
            continue
        relative = path.relative_to(ROOT)
        destination = backup_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

    print(f"Backup created: {backup_dir}")
    return backup_dir


def write_replacements() -> None:
    replacements = {
        ROOT / "backend" / "app" / "auth.py": "backend_auth.py",
        ROOT / "backend" / "app" / "services" / "personal_memory.py":
            "backend_personal_memory.py",
        ROOT / "backend" / "app" / "services" / "rag.py": "backend_rag.py",
        TARGETS["config"]: "replacement_config.py",
        TARGETS["schemas"]: "replacement_schemas.py",
        TARGETS["main"]: "replacement_main.py",
        TARGETS["api"]: "replacement_api.ts",
        ROOT / "frontend" / "components" / "MemoryKnowledgePanel.tsx":
            "MemoryKnowledgePanel.tsx",
        ROOT / "supabase" / "vasuki_memory_rag.sql":
            "vasuki_memory_rag.sql",
    }

    for destination, asset_name in replacements.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(read_asset(asset_name), encoding="utf-8")
        print(f"[WRITTEN] {destination.relative_to(ROOT)}")


def patch_chat_stream() -> None:
    path = TARGETS["chat"]
    text = path.read_text(encoding="utf-8-sig")
    marker = "# True token streaming for OpenAI-compatible providers"

    if marker not in text:
        text = text.rstrip() + "\n\n" + read_asset("chat_stream_append.py").strip() + "\n"
        path.write_text(text, encoding="utf-8")
        print("[UPDATED] backend/app/services/chat.py streaming extension")
    else:
        print("[OK] Streaming extension already exists")


def patch_requirements() -> None:
    path = TARGETS["requirements"]
    text = path.read_text(encoding="utf-8-sig").rstrip() + "\n"
    additions = (
        "pypdf>=5.0,<7.0",
        "python-docx>=1.1,<2.0",
    )
    for line in additions:
        if line not in text:
            text += line + "\n"
            print(f"[UPDATED] requirements: {line}")
    path.write_text(text, encoding="utf-8")


def patch_env_example() -> None:
    path = TARGETS["env_example"]
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    block = '''
# Personal memory + document RAG
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
EMBEDDING_DIMENSIONS=768
DOCUMENT_MAX_MB=15
DOCUMENT_MAX_CHUNKS=120
DOCUMENT_MATCH_COUNT=8
'''.strip()

    if "GEMINI_EMBEDDING_MODEL=" not in text:
        text = text.rstrip() + "\n\n" + block + "\n"
        path.write_text(text, encoding="utf-8")
        print("[UPDATED] backend/.env.example RAG settings")
    else:
        print("[OK] RAG env example already exists")


def patch_chat_app() -> None:
    path = TARGETS["chat_app"]
    text = path.read_text(encoding="utf-8-sig")

    text = replace_once(
        text,
        'import ReactMarkdown from "react-markdown";\n\n',
        'import ReactMarkdown from "react-markdown";\n\n'
        'import MemoryKnowledgePanel from "@/components/MemoryKnowledgePanel";\n',
        "MemoryKnowledgePanel import",
    )

    text = replace_once(
        text,
        "  sendChat,\n",
        "  streamChat,\n",
        "Streaming API import",
    )

    old_source_type = '''type SourceInfo = {
  title?: string;
  url?: string;
  domain?: string;
  published_date?: string;
  source_type?: string;
};
'''
    new_source_type = '''type SourceInfo = {
  title?: string;
  url?: string;
  domain?: string;
  published_date?: string;
  source_type?: string;
  document_id?: string;
  page_number?: number;
};
'''
    text = replace_once(
        text,
        old_source_type,
        new_source_type,
        "Document source fields",
    )

    normalise_replacement = r'''function normaliseSources(value: unknown): SourceInfo[] {
  if (!Array.isArray(value)) return [];

  const unique = new Map<string, SourceInfo>();
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const candidate = item as SourceInfo;
    const url = typeof candidate.url === "string" ? candidate.url.trim() : "";
    const isDocument = candidate.source_type === "document";

    if (url && !/^https?:\/\//i.test(url)) continue;
    if (!url && !isDocument) continue;

    const key =
      url ||
      [
        candidate.document_id || "",
        String(candidate.page_number || ""),
        candidate.title || "document",
      ].join(":");

    if (unique.has(key)) continue;

    unique.set(key, {
      title:
        typeof candidate.title === "string" && candidate.title.trim()
          ? candidate.title.trim()
          : undefined,
      url: url || undefined,
      domain:
        typeof candidate.domain === "string" && candidate.domain.trim()
          ? candidate.domain.trim()
          : isDocument
            ? "Your document"
            : undefined,
      published_date:
        typeof candidate.published_date === "string"
          ? candidate.published_date
          : undefined,
      source_type:
        typeof candidate.source_type === "string"
          ? candidate.source_type
          : undefined,
      document_id:
        typeof candidate.document_id === "string"
          ? candidate.document_id
          : undefined,
      page_number:
        typeof candidate.page_number === "number"
          ? candidate.page_number
          : undefined,
    });
  }

  return Array.from(unique.values()).slice(0, 12);
}'''
    text = regex_replace_once(
        text,
        r"function normaliseSources\(value: unknown\): SourceInfo\[\] \{.*?\n\}\n\nfunction sourceDomain",
        normalise_replacement + "\n\nfunction sourceDomain",
        "Document-aware source normalisation",
    )

    source_domain_replacement = r'''function sourceDomain(source: SourceInfo) {
  if (source.source_type === "document" || !source.url) {
    return source.domain?.trim() || "Your document";
  }
  if (source.domain?.trim()) return source.domain.trim().replace(/^www\./, "");
  try {
    return new URL(source.url).hostname.replace(/^www\./, "");
  } catch {
    return "Source";
  }
}'''
    text = regex_replace_once(
        text,
        r"function sourceDomain\(source: SourceInfo\) \{.*?\n\}",
        source_domain_replacement,
        "Document source labels",
    )

    state_marker = '''  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
'''
    state_replacement = '''  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [knowledgePanelOpen, setKnowledgePanelOpen] = useState(false);
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [documentsEnabled, setDocumentsEnabled] = useState(false);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [streamingStarted, setStreamingStarted] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
'''
    text = replace_once(
        text,
        state_marker,
        state_replacement,
        "Memory, RAG and streaming state",
    )

    submit_replacement = r'''  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();

    const text = input.trim();
    const selectedAttachment = attachment;

    if ((!text && !selectedAttachment) || busy || !user) return;

    const effectiveText =
      text ||
      (selectedAttachment?.kind === "pdf"
        ? "Is document ko detail me analyze karo. Agar question paper hai to saare questions ke sahi answers order me do."
        : "Is image ko detail me samjhao aur jo bhi important information hai woh batao.");

    const userMessage: UiMessage = {
      id: makeId(),
      role: "user",
      content: effectiveText,
      imageUrl: selectedAttachment?.previewUrl,
      fileName: selectedAttachment?.file.name,
    };

    const nextMessages = [...messages, userMessage];

    setMessages(nextMessages);
    setInput("");
    setError("");
    setBusy(true);
    setStreamingStarted(false);

    try {
      const {
        data: { session },
      } = await supabase.auth.getSession();

      const accessToken = session?.access_token;
      if (!accessToken) {
        throw new Error("Login session expired. Please sign in again.");
      }

      let finalMessages: UiMessage[];

      if (selectedAttachment) {
        const data = (await analyzeAttachment(
          selectedAttachment.file,
          effectiveText,
          accessToken,
        )) as VisionResponse;

        const answer =
          typeof data.answer === "string" && data.answer.trim()
            ? data.answer.trim()
            : data.url
              ? "Edited image ready."
              : "The image/file could not be analyzed.";

        const outputUrl =
          typeof data.url === "string" ? data.url.trim() : "";

        finalMessages = [
          ...nextMessages,
          {
            id: makeId(),
            role: "assistant",
            content: answer,
            imageUrl: outputUrl || undefined,
            provider: data.provider,
          },
        ];
      } else if (mode === "image") {
        const data = (await generateImage(
          effectiveText,
          accessToken,
        )) as ImageResponse;
        const imageUrl =
          typeof data.url === "string" ? data.url.trim() : "";

        if (!imageUrl) {
          throw new Error("Image provider returned an empty image.");
        }

        finalMessages = [
          ...nextMessages,
          {
            id: makeId(),
            role: "assistant",
            content: `Image generated${
              data.provider ? ` with ${data.provider}` : ""
            }.`,
            imageUrl,
            provider: data.provider,
          },
        ];
      } else {
        const requestMessages: ChatMessage[] = nextMessages.map(
          ({ role, content }) => ({ role, content }),
        );
        const assistantId = makeId();
        let streamedAnswer = "";

        setMessages([
          ...nextMessages,
          {
            id: assistantId,
            role: "assistant",
            content: "",
          },
        ]);

        const controller = new AbortController();
        streamAbortRef.current = controller;

        const meta = await streamChat(
          requestMessages,
          {
            accessToken,
            useWeb: webEnabled || mode === "web",
            useMemory: memoryEnabled,
            useDocuments: documentsEnabled,
            documentIds: selectedDocumentIds,
            signal: controller.signal,
          },
          (token) => {
            streamedAnswer += token;
            setStreamingStarted(true);
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? { ...message, content: streamedAnswer }
                  : message,
              ),
            );
          },
        );

        const answer = streamedAnswer.trim();
        if (!answer) {
          throw new Error("The AI returned an empty response.");
        }

        finalMessages = [
          ...nextMessages,
          {
            id: assistantId,
            role: "assistant",
            content: answer,
            provider: meta.provider,
            sources: normaliseSources(meta.sources),
          },
        ];
      }

      setMessages(finalMessages);
      setAttachment(null);
      setMode("chat");
      await persistChat(finalMessages, currentChatId);
    } catch (caughtError) {
      const stopped =
        streamAbortRef.current?.signal.aborted ||
        (
          caughtError instanceof DOMException &&
          caughtError.name === "AbortError"
        );

      setError(
        stopped
          ? "Generation stopped."
          : caughtError instanceof Error
            ? caughtError.message
            : "Something went wrong. Please try again.",
      );
    } finally {
      streamAbortRef.current = null;
      setStreamingStarted(false);
      setBusy(false);
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  }

  function stopStreaming() {
    streamAbortRef.current?.abort();
  }
'''
    text = regex_replace_once(
        text,
        r"  async function submit\(event\?: FormEvent<HTMLFormElement>\) \{.*?\n  \}\n\n  function handleKeyDown",
        submit_replacement + "\n  function handleKeyDown",
        "Authenticated token streaming submit flow",
    )

    nav_old = '''          <button
            type="button"
            className="pv-nav-button"
            onClick={startNewChat}
          >
            <Icon name="plus" />
            <span>New chat</span>
          </button>
        </nav>
'''
    nav_new = '''          <button
            type="button"
            className="pv-nav-button"
            onClick={startNewChat}
          >
            <Icon name="plus" />
            <span>New chat</span>
          </button>

          <button
            type="button"
            className="pv-nav-button"
            onClick={() => setKnowledgePanelOpen(true)}
          >
            <span className="pv-nav-symbol" aria-hidden="true">🧠</span>
            <span>Memory & documents</span>
          </button>
        </nav>
'''
    text = replace_once(
        text,
        nav_old,
        nav_new,
        "Memory and documents sidebar button",
    )

    text = text.replace(
        "                onSubmit={submit}\n                onKeyDown={handleKeyDown}",
        "                onSubmit={submit}\n"
        "                onStop={stopStreaming}\n"
        "                onKeyDown={handleKeyDown}",
    )

    text = replace_once(
        text,
        "                {busy && (\n                  <article className=\"pv-message pv-message--assistant\">",
        "                {busy && !streamingStarted && (\n"
        "                  <article className=\"pv-message pv-message--assistant\">",
        "Hide typing dots after first streamed token",
    )

    panel_marker = '''      </section>
    </main>
  );
}
'''
    panel_replacement = '''      </section>

      <MemoryKnowledgePanel
        open={knowledgePanelOpen}
        onClose={() => setKnowledgePanelOpen(false)}
        memoryEnabled={memoryEnabled}
        onMemoryEnabledChange={setMemoryEnabled}
        documentsEnabled={documentsEnabled}
        onDocumentsEnabledChange={setDocumentsEnabled}
        selectedDocumentIds={selectedDocumentIds}
        onSelectedDocumentIdsChange={setSelectedDocumentIds}
      />
    </main>
  );
}
'''
    text = replace_once(
        text,
        panel_marker,
        panel_replacement,
        "Memory and knowledge panel render",
    )

    text = replace_once(
        text,
        '''  onSubmit,
  onKeyDown,
  welcome = false,
''',
        '''  onSubmit,
  onStop,
  onKeyDown,
  welcome = false,
''',
        "Composer stop handler destructuring",
    )

    text = replace_once(
        text,
        '''  onSubmit: (event?: FormEvent<HTMLFormElement>) => Promise<void>;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
''',
        '''  onSubmit: (event?: FormEvent<HTMLFormElement>) => Promise<void>;
  onStop: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
''',
        "Composer stop handler type",
    )

    old_send = '''        <button
          type="submit"
          className="pv-send-button"
          disabled={busy || (!input.trim() && !attachment)}
          aria-label="Send message"
        >
          {busy ? <Icon name="stop" /> : <Icon name="arrowUp" />}
        </button>
'''
    new_send = '''        <button
          type={busy ? "button" : "submit"}
          className="pv-send-button"
          disabled={!busy && !input.trim() && !attachment}
          aria-label={busy ? "Stop generation" : "Send message"}
          onClick={busy ? onStop : undefined}
        >
          {busy ? <Icon name="stop" /> : <Icon name="arrowUp" />}
        </button>
'''
    text = replace_once(
        text,
        old_send,
        new_send,
        "Working stop-generation button",
    )

    source_strip = r'''function SourceStrip({ sources }: { sources?: SourceInfo[] }) {
  const items = normaliseSources(sources);
  if (items.length === 0) return null;

  const preview = items.slice(0, 3);
  const keyFor = (source: SourceInfo, index: number) =>
    source.url ||
    `${source.document_id || "document"}-${source.page_number || index}`;

  return (
    <div className="pv-source-strip">
      <div className="pv-source-chip-row" aria-label="Answer sources">
        {preview.map((source, index) =>
          source.url ? (
            <a
              className="pv-source-chip"
              href={source.url}
              target="_blank"
              rel="noreferrer"
              key={keyFor(source, index)}
              title={source.title || sourceDomain(source)}
            >
              <span className="pv-source-number">{index + 1}</span>
              <img
                src={sourceFavicon(source)}
                alt=""
                loading="lazy"
                onError={(event) => {
                  event.currentTarget.style.display = "none";
                }}
              />
              <span>{sourceDomain(source)}</span>
            </a>
          ) : (
            <span
              className="pv-source-chip pv-source-chip--document"
              key={keyFor(source, index)}
              title={source.title || "Your document"}
            >
              <span className="pv-source-number">{index + 1}</span>
              <span aria-hidden="true">📄</span>
              <span>{source.title || "Your document"}</span>
            </span>
          ),
        )}
        {items.length > preview.length && (
          <span className="pv-source-more">+{items.length - preview.length}</span>
        )}
      </div>

      <details className="pv-sources-details">
        <summary>
          <strong>Sources</strong>
          <span>{items.length}</span>
        </summary>

        <div className="pv-source-list">
          {items.map((source, index) =>
            source.url ? (
              <a
                className="pv-source-card"
                href={source.url}
                target="_blank"
                rel="noreferrer"
                key={keyFor(source, index)}
              >
                <span className="pv-source-card-number">{index + 1}</span>
                <img src={sourceFavicon(source)} alt="" loading="lazy" />
                <span className="pv-source-card-copy">
                  <strong>{source.title || sourceDomain(source)}</strong>
                  <small>
                    {sourceDomain(source)}
                    {source.published_date
                      ? ` · ${source.published_date}`
                      : ""}
                  </small>
                </span>
                <span className="pv-source-open" aria-hidden="true">↗</span>
              </a>
            ) : (
              <div
                className="pv-source-card pv-source-card--document"
                key={keyFor(source, index)}
              >
                <span className="pv-source-card-number">{index + 1}</span>
                <span className="pv-document-source-icon" aria-hidden="true">
                  📄
                </span>
                <span className="pv-source-card-copy">
                  <strong>{source.title || "Your document"}</strong>
                  <small>{sourceDomain(source)}</small>
                </span>
              </div>
            ),
          )}
        </div>
      </details>
    </div>
  );
}'''
    text = regex_replace_once(
        text,
        r"function SourceStrip\(\{ sources \}: \{ sources\?: SourceInfo\[\] \}\) \{.*?\n\}\n\nfunction GoogleIcon",
        source_strip + "\n\nfunction GoogleIcon",
        "Document-aware source cards",
    )

    path.write_text(text, encoding="utf-8")


def patch_css() -> None:
    path = TARGETS["css"]
    text = path.read_text(encoding="utf-8-sig")
    marker = "/* Vasuki private memory and document knowledge panel */"

    if marker in text:
        print("[OK] Memory/RAG CSS already exists")
        return

    css = read_asset("memory_rag_styles.css")
    path.write_text(text.rstrip() + "\n\n" + css.strip() + "\n", encoding="utf-8")
    print("[UPDATED] frontend/app/globals.css memory/RAG styles")


def main() -> None:
    missing = [
        str(path)
        for path in TARGETS.values()
        if not path.exists() and path.name != ".env.example"
    ]
    if missing:
        raise SystemExit(
            "Project files were not found. Put this installer in the project root:\n"
            + "\n".join(missing)
        )

    backup_files()
    write_replacements()
    patch_chat_stream()
    patch_requirements()
    patch_env_example()
    patch_chat_app()
    patch_css()

    print("\nSUCCESS: Memory, RAG, streaming and backend auth patch applied.")
    print("\nNext commands:")
    print("  git add backend frontend supabase")
    print('  git commit -m "Add streaming auth personal memory and document RAG"')
    print("  git push origin main")
    print("\nIMPORTANT:")
    print("1. Run supabase/vasuki_memory_rag.sql in Supabase SQL Editor.")
    print("2. Keep SUPABASE secret/service-role key only on Render.")
    print("3. Do not put the service-role key in Vercel or frontend files.")


if __name__ == "__main__":
    main()
