"use client";

import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import { generateImage, sendChat, type ChatMessage } from "@/lib/api";

type UiMessage = ChatMessage & {
  id: string;
  imageUrl?: string;
  provider?: string;
};

type ActionMode = "chat" | "image" | "write" | "web" | "analyze";

type ChatResponse = {
  answer?: string;
  sources?: Array<{ title?: string; url?: string }>;
};

type ImageResponse = {
  url?: string;
  provider?: string;
};

const recentChats = [
  "Latest India updates",
  "Create a cinematic image",
  "Build a modern portfolio",
  "Debug a Next.js application",
];

const actionItems: Array<{
  mode: ActionMode;
  label: string;
  prompt: string;
  icon: "image" | "write" | "web" | "analyze";
}> = [
  {
    mode: "image",
    label: "Create an image",
    prompt: "Create an image of ",
    icon: "image",
  },
  {
    mode: "write",
    label: "Write or edit",
    prompt: "Help me write ",
    icon: "write",
  },
  {
    mode: "web",
    label: "Search the web",
    prompt: "Search the web for ",
    icon: "web",
  },
  {
    mode: "analyze",
    label: "Analyze data",
    prompt: "Analyze this data: ",
    icon: "analyze",
  },
];

function makeId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function ChatApp() {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<ActionMode>("chat");
  const [webEnabled, setWebEnabled] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  function startNewChat() {
    setMessages([]);
    setInput("");
    setError("");
    setMode("chat");
    setWebEnabled(false);
    setMobileSidebarOpen(false);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  function selectAction(action: (typeof actionItems)[number]) {
    setMode(action.mode);
    setWebEnabled(action.mode === "web");
    setInput((current) => current || action.prompt);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();

    const text = input.trim();
    if (!text || busy) return;

    const userMessage: UiMessage = {
      id: makeId(),
      role: "user",
      content: text,
    };

    const nextMessages = [...messages, userMessage];

    setMessages(nextMessages);
    setInput("");
    setError("");
    setBusy(true);

    try {
      if (mode === "image") {
        const data = (await generateImage(text)) as ImageResponse;
        const imageUrl = typeof data.url === "string" ? data.url.trim() : "";

        if (!imageUrl) {
          throw new Error("Image provider returned an empty image.");
        }

        setMessages((current) => [
          ...current,
          {
            id: makeId(),
            role: "assistant",
            content: `Image generated${data.provider ? ` with ${data.provider}` : ""}.`,
            imageUrl,
            provider: data.provider,
          },
        ]);
      } else {
        const requestMessages: ChatMessage[] = nextMessages.map(
          ({ role, content }) => ({ role, content }),
        );

        const data = (await sendChat(
          requestMessages,
          webEnabled || mode === "web",
        )) as ChatResponse;

        let answer =
          typeof data.answer === "string" ? data.answer.trim() : "";

        if (!answer) {
          throw new Error("The AI returned an empty response.");
        }

        const validSources = Array.isArray(data.sources)
          ? data.sources.filter(
              (source) =>
                typeof source?.url === "string" &&
                source.url.trim().length > 0,
            )
          : [];

        if (validSources.length > 0) {
          answer +=
            "\n\n### Sources\n" +
            validSources
              .map((source, index) => {
                const title =
                  typeof source.title === "string" && source.title.trim()
                    ? source.title.trim()
                    : `Source ${index + 1}`;
                return `${index + 1}. [${title}](${source.url})`;
              })
              .join("\n");
        }

        setMessages((current) => [
          ...current,
          {
            id: makeId(),
            role: "assistant",
            content: answer,
          },
        ]);
      }
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Something went wrong. Please try again.",
      );
    } finally {
      setBusy(false);
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  }

  const hasMessages = messages.length > 0;

  return (
    <main className="pv-app">
      {mobileSidebarOpen && (
        <button
          type="button"
          className="pv-sidebar-backdrop"
          aria-label="Close sidebar"
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}

      <aside
        className={[
          "pv-sidebar",
          sidebarCollapsed ? "pv-sidebar--collapsed" : "",
          mobileSidebarOpen ? "pv-sidebar--mobile-open" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <div className="pv-sidebar-top">
          <button
            type="button"
            className="pv-brand-button"
            onClick={startNewChat}
          >
            <span className="pv-logo">V</span>
            <span className="pv-brand-text">Power Vasuki AI</span>
          </button>

          <button
            type="button"
            className="pv-icon-button pv-desktop-only"
            aria-label="Collapse sidebar"
            onClick={() => setSidebarCollapsed(true)}
          >
            <Icon name="sidebar" />
          </button>

          <button
            type="button"
            className="pv-icon-button pv-mobile-only"
            aria-label="Close sidebar"
            onClick={() => setMobileSidebarOpen(false)}
          >
            <Icon name="close" />
          </button>
        </div>

        <nav className="pv-sidebar-nav">
          <button
            type="button"
            className="pv-nav-button"
            onClick={startNewChat}
          >
            <Icon name="plus" />
            <span>New chat</span>
          </button>

          <button type="button" className="pv-nav-button">
            <Icon name="search" />
            <span>Search chats</span>
          </button>
        </nav>

        <div className="pv-recent">
          <p className="pv-section-label">Recent</p>
          {recentChats.map((chat) => (
            <button type="button" className="pv-recent-button" key={chat}>
              {chat}
            </button>
          ))}
        </div>

        <div className="pv-profile">
          <span className="pv-profile-avatar">LP</span>
          <span className="pv-profile-copy">
            <strong>Lakhan Prajapat</strong>
            <small>Power Vasuki AI</small>
          </span>
        </div>
      </aside>

      <section className="pv-main">
        <header className="pv-header">
          <div className="pv-header-left">
            <button
              type="button"
              className="pv-icon-button pv-mobile-only"
              aria-label="Open sidebar"
              onClick={() => setMobileSidebarOpen(true)}
            >
              <Icon name="menu" />
            </button>

            {sidebarCollapsed && (
              <button
                type="button"
                className="pv-icon-button pv-desktop-only"
                aria-label="Restore sidebar"
                onClick={() => setSidebarCollapsed(false)}
              >
                <Icon name="sidebar" />
              </button>
            )}

            <button type="button" className="pv-model-button">
              <span>Power Vasuki AI</span>
              <Icon name="chevron" />
            </button>
          </div>

          <button type="button" className="pv-share-button">
            Share
          </button>
        </header>

        {!hasMessages ? (
          <section className="pv-welcome">
            <div className="pv-welcome-inner">
              <h1>Where should we begin?</h1>

              <Composer
                input={input}
                setInput={setInput}
                busy={busy}
                mode={mode}
                textareaRef={textareaRef}
                onSubmit={submit}
                onKeyDown={handleKeyDown}
                welcome
              />

              <div className="pv-actions">
                {actionItems.map((action) => (
                  <button
                    type="button"
                    key={action.mode}
                    className={[
                      "pv-action-button",
                      mode === action.mode ? "pv-action-button--active" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    onClick={() => selectAction(action)}
                  >
                    <Icon name={action.icon} />
                    <span>{action.label}</span>
                  </button>
                ))}
              </div>
            </div>
          </section>
        ) : (
          <>
            <section className="pv-conversation">
              <div className="pv-message-list">
                {messages.map((message) => (
                  <article
                    key={message.id}
                    className={`pv-message pv-message--${message.role}`}
                  >
                    {message.role === "assistant" && (
                      <div className="pv-assistant-avatar">V</div>
                    )}

                    <div className="pv-message-body">
                      {message.role === "assistant" ? (
                        <>
                          <div className="pv-markdown">
                            <ReactMarkdown>{message.content}</ReactMarkdown>
                          </div>

                          {message.imageUrl && (
                            <img
                              className="pv-generated-image"
                              src={message.imageUrl}
                              alt="Generated by Power Vasuki AI"
                            />
                          )}

                          <div className="pv-message-actions">
                            <button
                              type="button"
                              aria-label="Copy response"
                              onClick={() =>
                                navigator.clipboard?.writeText(message.content)
                              }
                            >
                              <Icon name="copy" />
                            </button>
                            <button type="button" aria-label="Good response">
                              <Icon name="thumbUp" />
                            </button>
                            <button type="button" aria-label="Bad response">
                              <Icon name="thumbDown" />
                            </button>
                          </div>
                        </>
                      ) : (
                        <div className="pv-user-bubble">{message.content}</div>
                      )}
                    </div>
                  </article>
                ))}

                {busy && (
                  <article className="pv-message pv-message--assistant">
                    <div className="pv-assistant-avatar">V</div>
                    <div className="pv-typing" aria-label="Thinking">
                      <span />
                      <span />
                      <span />
                    </div>
                  </article>
                )}

                {error && <div className="pv-error">{error}</div>}
                <div ref={endRef} />
              </div>
            </section>

            <div className="pv-composer-dock">
              <div className="pv-composer-dock-inner">
                <Composer
                  input={input}
                  setInput={setInput}
                  busy={busy}
                  mode={mode}
                  textareaRef={textareaRef}
                  onSubmit={submit}
                  onKeyDown={handleKeyDown}
                />
                <p className="pv-disclaimer">
                  Power Vasuki AI can make mistakes. Verify important
                  information.
                </p>
              </div>
            </div>
          </>
        )}
      </section>
    </main>
  );
}

function Composer({
  input,
  setInput,
  busy,
  mode,
  textareaRef,
  onSubmit,
  onKeyDown,
  welcome = false,
}: {
  input: string;
  setInput: (value: string) => void;
  busy: boolean;
  mode: ActionMode;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  onSubmit: (event?: FormEvent<HTMLFormElement>) => Promise<void>;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  welcome?: boolean;
}) {
  return (
    <form
      className={`pv-composer ${welcome ? "pv-composer--welcome" : ""}`}
      onSubmit={(event) => void onSubmit(event)}
    >
      <textarea
        ref={textareaRef}
        rows={2}
        value={input}
        onChange={(event) => setInput(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder={
          mode === "image"
            ? "Describe the image you want to create"
            : "Ask Power Vasuki AI"
        }
      />

      <div className="pv-composer-toolbar">
        <div className="pv-composer-tools">
          <button type="button" aria-label="Attach file">
            <Icon name="plus" />
          </button>

          {mode !== "chat" && (
            <span className="pv-active-tool">
              {mode === "image"
                ? "Create image"
                : mode === "write"
                  ? "Write"
                  : mode === "web"
                    ? "Search web"
                    : "Analyze"}
            </span>
          )}
        </div>

        <button
          type="submit"
          className="pv-send-button"
          disabled={busy || !input.trim()}
          aria-label="Send message"
        >
          {busy ? <Icon name="stop" /> : <Icon name="arrowUp" />}
        </button>
      </div>
    </form>
  );
}

function Icon({
  name,
}: {
  name:
    | "menu"
    | "close"
    | "sidebar"
    | "plus"
    | "search"
    | "chevron"
    | "image"
    | "write"
    | "web"
    | "analyze"
    | "arrowUp"
    | "stop"
    | "copy"
    | "thumbUp"
    | "thumbDown";
}) {
  const common = {
    viewBox: "0 0 24 24",
    width: 20,
    height: 20,
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  const paths: Record<typeof name, React.ReactNode> = {
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    sidebar: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M9 4v16" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    search: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5" />
      </>
    ),
    chevron: <path d="m8 10 4 4 4-4" />,
    image: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <circle cx="8.5" cy="9" r="1.5" />
        <path d="m21 15-5-5L5 20" />
      </>
    ),
    write: (
      <>
        <path d="m4 20 4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20Z" />
        <path d="m14 7 3 3" />
      </>
    ),
    web: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" />
      </>
    ),
    analyze: <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />,
    arrowUp: <path d="M12 19V5M6.5 10.5 12 5l5.5 5.5" />,
    stop: <rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" stroke="none" />,
    copy: (
      <>
        <rect x="8" y="8" width="11" height="11" rx="2" />
        <path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" />
      </>
    ),
    thumbUp: <path d="M7 10v10H4V10h3Zm0 9h9.1a2 2 0 0 0 1.9-1.4l1.5-5A2 2 0 0 0 17.6 10H14l.8-3.2A2.3 2.3 0 0 0 12.6 4L7 10Z" />,
    thumbDown: <path d="M7 14V4H4v10h3Zm0-9h9.1A2 2 0 0 1 18 6.4l1.5 5a2 2 0 0 1-1.9 2.6H14l.8 3.2a2.3 2.3 0 0 1-2.2 2.8L7 14Z" />,
  };

  return <svg {...common}>{paths[name]}</svg>;
}
