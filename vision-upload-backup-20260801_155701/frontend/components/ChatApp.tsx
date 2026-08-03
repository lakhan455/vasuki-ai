"use client";

import {
  FormEvent,
  KeyboardEvent,
  ReactNode,
  useEffect,
  useRef,
  useState,
} from "react";
import type { User } from "@supabase/supabase-js";
import ReactMarkdown from "react-markdown";

import { generateImage, sendChat, warmBackend, type ChatMessage } from "@/lib/api";
import { supabase } from "@/lib/supabase";

const VASUKI_LOGO_URL =
  "https://images.jdmagicbox.com/v2/comp/jaipur/a2/0141px141.x141.260404193718.t6a2/catalogue/vasuki-nfc-luniawas-jaipur-printing-services-604tb4s28a.jpg";

type SourceInfo = {
  title?: string;
  url?: string;
  domain?: string;
  published_date?: string;
  source_type?: string;
};

type UiMessage = ChatMessage & {
  id: string;
  imageUrl?: string;
  provider?: string;
  sources?: SourceInfo[];
};

type StoredMessage = {
  role: "user" | "assistant";
  content: string;
  imageUrl?: string;
  provider?: string;
  sources?: SourceInfo[];
};

type ChatRecord = {
  id: string;
  title: string;
  messages: unknown;
  updated_at: string;
};

type ActionMode = "chat" | "image" | "write" | "web" | "analyze";

type ChatResponse = {
  answer?: string;
  sources?: SourceInfo[];
};

type ImageResponse = {
  url?: string;
  provider?: string;
};

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


function normaliseSources(value: unknown): SourceInfo[] {
  if (!Array.isArray(value)) return [];

  const unique = new Map<string, SourceInfo>();
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const candidate = item as SourceInfo;
    const url = typeof candidate.url === "string" ? candidate.url.trim() : "";
    if (!/^https?:\/\//i.test(url) || unique.has(url)) continue;

    unique.set(url, {
      title:
        typeof candidate.title === "string" && candidate.title.trim()
          ? candidate.title.trim()
          : undefined,
      url,
      domain:
        typeof candidate.domain === "string" && candidate.domain.trim()
          ? candidate.domain.trim()
          : undefined,
      published_date:
        typeof candidate.published_date === "string"
          ? candidate.published_date
          : undefined,
      source_type:
        typeof candidate.source_type === "string"
          ? candidate.source_type
          : undefined,
    });
  }

  return Array.from(unique.values()).slice(0, 12);
}

function sourceDomain(source: SourceInfo) {
  if (source.domain?.trim()) return source.domain.trim().replace(/^www\./, "");
  try {
    return new URL(source.url || "").hostname.replace(/^www\./, "");
  } catch {
    return "Source";
  }
}

function sourceFavicon(source: SourceInfo) {
  const domain = sourceDomain(source);
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(
    domain,
  )}&sz=64`;
}

function storedMessages(messages: UiMessage[]): StoredMessage[] {
  return messages.map(({ role, content, imageUrl, provider, sources }) => ({
    role,
    content,
    // Base64 images can be several megabytes. Keep hosted URLs, but avoid
    // filling the database with large data URLs.
    imageUrl:
      imageUrl && !imageUrl.startsWith("data:") ? imageUrl : undefined,
    provider,
    sources: normaliseSources(sources),
  }));
}

function restoreMessages(value: unknown): UiMessage[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }

    const candidate = item as Partial<StoredMessage>;
    if (
      (candidate.role !== "user" && candidate.role !== "assistant") ||
      typeof candidate.content !== "string"
    ) {
      return [];
    }

    return [
      {
        id: makeId(),
        role: candidate.role,
        content: candidate.content,
        imageUrl:
          typeof candidate.imageUrl === "string"
            ? candidate.imageUrl
            : undefined,
        provider:
          typeof candidate.provider === "string"
            ? candidate.provider
            : undefined,
        sources: normaliseSources(candidate.sources),
      },
    ];
  });
}

function chatTitle(messages: UiMessage[]) {
  const firstUserMessage = messages.find(
    (message) => message.role === "user",
  )?.content;

  const title = firstUserMessage?.replace(/\s+/g, " ").trim();
  return title ? title.slice(0, 60) : "New Chat";
}

function initials(user: User) {
  const displayName =
    user.user_metadata?.full_name ||
    user.user_metadata?.name ||
    user.email ||
    "User";

  return displayName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part: string) => part[0]?.toUpperCase())
    .join("");
}

export default function ChatApp() {
  const [authReady, setAuthReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [chatRecords, setChatRecords] = useState<ChatRecord[]>([]);
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);

  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<ActionMode>("chat");
  const [webEnabled, setWebEnabled] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void warmBackend();

    const intervalId = window.setInterval(() => {
      void warmBackend();
    }, 10 * 60 * 1000);

    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    let mounted = true;

    void supabase.auth.getSession().then(({ data, error: sessionError }) => {
      if (!mounted) return;

      if (sessionError) {
        setError(sessionError.message);
      }

      setUser(data.session?.user ?? null);
      setAuthReady(true);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!mounted) return;

      setUser(session?.user ?? null);
      setAuthReady(true);

      if (!session?.user) {
        setMessages([]);
        setChatRecords([]);
        setCurrentChatId(null);
      }
    });

    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!user) return;
    void loadChatHistory(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function signInWithGoogle() {
    setError("");

    const { error: signInError } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: window.location.origin,
      },
    });

    if (signInError) {
      setError(signInError.message);
    }
  }

  async function signOut() {
    setError("");
    const { error: signOutError } = await supabase.auth.signOut();

    if (signOutError) {
      setError(signOutError.message);
    }
  }

  async function loadChatHistory(openLatest: boolean) {
    if (!user) return;

    setHistoryBusy(true);
    const { data, error: historyError } = await supabase
      .from("user_chats")
      .select("id,title,messages,updated_at")
      .eq("user_id", user.id)
      .order("updated_at", { ascending: false });

    setHistoryBusy(false);

    if (historyError) {
      setError(historyError.message);
      return;
    }

    const records = (data ?? []) as ChatRecord[];
    setChatRecords(records);

    if (openLatest && records.length > 0) {
      openChat(records[0]);
    }
  }

  function openChat(record: ChatRecord) {
    setCurrentChatId(record.id);
    setMessages(restoreMessages(record.messages));
    setInput("");
    setError("");
    setMode("chat");
    setWebEnabled(false);
    setMobileSidebarOpen(false);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function persistChat(
    nextMessages: UiMessage[],
    targetChatId: string | null,
  ) {
    if (!user || nextMessages.length === 0) {
      return targetChatId;
    }

    const payload = {
      user_id: user.id,
      title: chatTitle(nextMessages),
      messages: storedMessages(nextMessages),
    };

    if (targetChatId) {
      const { error: updateError } = await supabase
        .from("user_chats")
        .update(payload)
        .eq("id", targetChatId)
        .eq("user_id", user.id);

      if (updateError) {
        throw new Error(`Chat save failed: ${updateError.message}`);
      }

      await loadChatHistory(false);
      return targetChatId;
    }

    const { data, error: insertError } = await supabase
      .from("user_chats")
      .insert(payload)
      .select("id")
      .single();

    if (insertError) {
      throw new Error(`Chat save failed: ${insertError.message}`);
    }

    const newId = String(data.id);
    setCurrentChatId(newId);
    await loadChatHistory(false);
    return newId;
  }

  function startNewChat() {
    setCurrentChatId(null);
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
    if (!text || busy || !user) return;

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
      let finalMessages: UiMessage[];

      if (mode === "image") {
        const data = (await generateImage(text)) as ImageResponse;
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

        const data = (await sendChat(
          requestMessages,
          webEnabled || mode === "web",
        )) as ChatResponse;

        const answer =
          typeof data.answer === "string" ? data.answer.trim() : "";

        if (!answer) {
          throw new Error("The AI returned an empty response.");
        }

        const validSources = normaliseSources(data.sources);

        finalMessages = [
          ...nextMessages,
          {
            id: makeId(),
            role: "assistant",
            content: answer,
            sources: validSources,
          },
        ];
      }

      setMessages(finalMessages);
      await persistChat(finalMessages, currentChatId);
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

  if (!authReady) {
    return (
      <main className="pv-auth-screen">
        <div className="pv-auth-card">
          <Logo className="pv-auth-logo" />
          <h1>Vasuki AI</h1>
          <p>Securely loading your accountâ€¦</p>
          <div className="pv-auth-spinner" />
        </div>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="pv-auth-screen">
        <section className="pv-auth-card">
          <Logo className="pv-auth-logo" />
          <h1>Welcome to Vasuki AI</h1>
          <p>
            Google se login karke apni chats save karein aur kisi bhi device
            par wahi history wapas paayein.
          </p>

          <button
            type="button"
            className="pv-google-button"
            onClick={() => void signInWithGoogle()}
          >
            <GoogleIcon />
            Continue with Google
          </button>

          {error && <div className="pv-auth-error">{error}</div>}

          <small>
            Login ke baad har user sirf apni chats dekh sakta hai.
          </small>
        </section>
      </main>
    );
  }

  const hasMessages = messages.length > 0;
  const profileName =
    user.user_metadata?.full_name ||
    user.user_metadata?.name ||
    user.email ||
    "Vasuki AI User";
  const profileImage =
    typeof user.user_metadata?.avatar_url === "string"
      ? user.user_metadata.avatar_url
      : "";

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
            <Logo className="pv-brand-logo" />
            <span className="pv-brand-text">Vasuki AI</span>
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
        </nav>

        <div className="pv-recent">
          <p className="pv-section-label">
            Recent {historyBusy ? "Â· loadingâ€¦" : ""}
          </p>

          {chatRecords.length === 0 && !historyBusy ? (
            <p className="pv-empty-history">Abhi koi saved chat nahi hai.</p>
          ) : (
            chatRecords.map((chat) => (
              <button
                type="button"
                className={[
                  "pv-recent-button",
                  currentChatId === chat.id
                    ? "pv-recent-button--active"
                    : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                key={chat.id}
                onClick={() => openChat(chat)}
                title={chat.title}
              >
                {chat.title}
              </button>
            ))
          )}
        </div>

        <div className="pv-profile">
          {profileImage ? (
            <img
              className="pv-profile-image"
              src={profileImage}
              alt={profileName}
              referrerPolicy="no-referrer"
            />
          ) : (
            <span className="pv-profile-avatar">{initials(user)}</span>
          )}

          <span className="pv-profile-copy">
            <strong>{profileName}</strong>
            <small>{user.email}</small>
          </span>

          <button
            type="button"
            className="pv-logout-button"
            aria-label="Logout"
            title="Logout"
            onClick={() => void signOut()}
          >
            <Icon name="logout" />
          </button>
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
              <Logo className="pv-header-logo" />
              <span>Vasuki AI</span>
              <Icon name="chevron" />
            </button>
          </div>

          <span className="pv-saved-indicator">
            {currentChatId ? "Saved" : "New chat"}
          </span>
        </header>

        {!hasMessages ? (
          <section className="pv-welcome">
            <div className="pv-welcome-inner">
              <Logo className="pv-welcome-logo" />
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
                      mode === action.mode
                        ? "pv-action-button--active"
                        : "",
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

              {error && <div className="pv-error pv-error--welcome">{error}</div>}
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
                      <Logo className="pv-assistant-logo" />
                    )}

                    <div className="pv-message-body">
                      {message.role === "assistant" ? (
                        <>
                          <div className="pv-markdown">
                            <ReactMarkdown>{message.content}</ReactMarkdown>
                          </div>

                          <SourceStrip sources={message.sources} />

                          {message.imageUrl && (
                            <img
                              className="pv-generated-image"
                              src={message.imageUrl}
                              alt="Generated by Vasuki AI"
                            />
                          )}

                          <div className="pv-message-actions">
                            <button
                              type="button"
                              aria-label="Copy response"
                              onClick={() =>
                                navigator.clipboard?.writeText(
                                  message.content,
                                )
                              }
                            >
                              <Icon name="copy" />
                            </button>
                            <button
                              type="button"
                              aria-label="Good response"
                            >
                              <Icon name="thumbUp" />
                            </button>
                            <button
                              type="button"
                              aria-label="Bad response"
                            >
                              <Icon name="thumbDown" />
                            </button>
                          </div>
                        </>
                      ) : (
                        <div className="pv-user-bubble">
                          {message.content}
                        </div>
                      )}
                    </div>
                  </article>
                ))}

                {busy && (
                  <article className="pv-message pv-message--assistant">
                    <Logo className="pv-assistant-logo" />
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
                  Vasuki AI can make mistakes. Verify important information.
                </p>
              </div>
            </div>
          </>
        )}
      </section>
    </main>
  );
}

function Logo({ className }: { className: string }) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return <span className={`${className} pv-logo-fallback`}>V</span>;
  }

  return (
    <img
      className={className}
      src={VASUKI_LOGO_URL}
      alt="Vasuki AI logo"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
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
      className={`pv-composer ${
        welcome ? "pv-composer--welcome" : ""
      }`}
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
            : "Ask Vasuki AI"
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


function SourceStrip({ sources }: { sources?: SourceInfo[] }) {
  const items = normaliseSources(sources);
  if (items.length === 0) return null;

  const preview = items.slice(0, 3);

  return (
    <div className="pv-source-strip">
      <div className="pv-source-chip-row" aria-label="Answer sources">
        {preview.map((source, index) => (
          <a
            className="pv-source-chip"
            href={source.url}
            target="_blank"
            rel="noreferrer"
            key={source.url}
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
        ))}
        {items.length > preview.length && (
          <span className="pv-source-more">+{items.length - preview.length}</span>
        )}
      </div>

      <details className="pv-sources-details">
        <summary>
          <span className="pv-source-stack" aria-hidden="true">
            {preview.slice(0, 2).map((source) => (
              <img key={source.url} src={sourceFavicon(source)} alt="" />
            ))}
          </span>
          <strong>Sources</strong>
          <span>{items.length}</span>
        </summary>

        <div className="pv-source-list">
          {items.map((source, index) => (
            <a
              className="pv-source-card"
              href={source.url}
              target="_blank"
              rel="noreferrer"
              key={source.url}
            >
              <span className="pv-source-card-number">{index + 1}</span>
              <img src={sourceFavicon(source)} alt="" loading="lazy" />
              <span className="pv-source-card-copy">
                <strong>{source.title || sourceDomain(source)}</strong>
                <small>
                  {sourceDomain(source)}
                  {source.published_date ? ` · ${source.published_date}` : ""}
                </small>
              </span>
              <span className="pv-source-open" aria-hidden="true">↗</span>
            </a>
          ))}
        </div>
      </details>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M21.6 12.23c0-.71-.06-1.4-.18-2.07H12v3.91h5.38a4.6 4.6 0 0 1-2 3.02v2.54h3.24c1.9-1.75 2.98-4.33 2.98-7.4Z"
      />
      <path
        fill="#34A853"
        d="M12 22c2.7 0 4.97-.9 6.63-2.43l-3.24-2.54c-.9.6-2.05.96-3.39.96-2.61 0-4.82-1.76-5.61-4.13H3.04v2.62A10 10 0 0 0 12 22Z"
      />
      <path
        fill="#FBBC05"
        d="M6.39 13.86A6 6 0 0 1 6.08 12c0-.65.11-1.28.31-1.86V7.52H3.04A10 10 0 0 0 2 12c0 1.61.39 3.14 1.04 4.48l3.35-2.62Z"
      />
      <path
        fill="#EA4335"
        d="M12 6.01c1.47 0 2.79.51 3.82 1.5l2.87-2.87A9.64 9.64 0 0 0 12 2a10 10 0 0 0-8.96 5.52l3.35 2.62C7.18 7.77 9.39 6.01 12 6.01Z"
      />
    </svg>
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
    | "chevron"
    | "image"
    | "write"
    | "web"
    | "analyze"
    | "arrowUp"
    | "stop"
    | "copy"
    | "thumbUp"
    | "thumbDown"
    | "logout";
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

  const paths: Record<typeof name, ReactNode> = {
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    sidebar: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M9 4v16" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
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
    stop: (
      <rect
        x="7"
        y="7"
        width="10"
        height="10"
        rx="1.5"
        fill="currentColor"
        stroke="none"
      />
    ),
    copy: (
      <>
        <rect x="8" y="8" width="11" height="11" rx="2" />
        <path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" />
      </>
    ),
    thumbUp: (
      <path d="M7 10v10H4V10h3Zm0 9h9.1a2 2 0 0 0 1.9-1.4l1.5-5A2 2 0 0 0 17.6 10H14l.8-3.2A2.3 2.3 0 0 0 12.6 4L7 10Z" />
    ),
    thumbDown: (
      <path d="M7 14V4H4v10h3Zm0-9h9.1A2 2 0 0 1 18 6.4l1.5 5a2 2 0 0 1-1.9 2.6H14l.8 3.2a2.3 2.3 0 0 1-2.2 2.8L7 14Z" />
    ),
    logout: (
      <>
        <path d="M10 17l5-5-5-5" />
        <path d="M15 12H3" />
        <path d="M14 4h4a3 3 0 0 1 3 3v10a3 3 0 0 1-3 3h-4" />
      </>
    ),
  };

  return <svg {...common}>{paths[name]}</svg>;
}

