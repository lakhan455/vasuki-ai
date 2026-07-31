"use client";

import {
  FormEvent,
  KeyboardEvent,
  ReactNode,
  useEffect,
  useRef,
  useState,
} from "react";

type Role = "user" | "assistant";

type Message = {
  id: string;
  role: Role;
  content: string;
};

type ToolMode = "image" | "write" | "web" | "analyze" | null;

type ChatApiResponse = {
  answer?: string;
  detail?: string;
  message?: string;
};

const CHAT_API_URL =
  process.env.NEXT_PUBLIC_CHAT_API_URL || "/backend-api/api/chat";

const starterActions: Array<{
  label: string;
  mode: Exclude<ToolMode, null>;
  icon: ReactNode;
}> = [
  {
    label: "Create an image",
    mode: "image",
    icon: <ImageIcon />,
  },
  {
    label: "Write or edit",
    mode: "write",
    icon: <PenIcon />,
  },
  {
    label: "Search the web",
    mode: "web",
    icon: <GlobeIcon />,
  },
  {
    label: "Analyze data",
    mode: "analyze",
    icon: <ChartIcon />,
  },
];

const sampleChats = [
  "Build a modern portfolio",
  "Latest India updates",
  "Generate a cinematic image",
  "Debug my Next.js app",
];

export default function ChatApp() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [toolMode, setToolMode] = useState<ToolMode>(null);
  const [error, setError] = useState("");

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending]);

  function createId() {
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }

  function resetChat() {
    setMessages([]);
    setInput("");
    setToolMode(null);
    setError("");
    setMobileSidebarOpen(false);
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  function chooseAction(mode: Exclude<ToolMode, null>) {
    setToolMode(mode);

    const prompts: Record<Exclude<ToolMode, null>, string> = {
      image: "Create an image of ",
      write: "Help me write ",
      web: "Search the web for ",
      analyze: "Analyze this data: ",
    };

    setInput((current) => current || prompts[mode]);
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  async function sendMessage() {
    const prompt = input.trim();

    if (!prompt || isSending) {
      return;
    }

    const userMessage: Message = {
      id: createId(),
      role: "user",
      content: prompt,
    };

    const nextMessages = [...messages, userMessage];

    setMessages(nextMessages);
    setInput("");
    setError("");
    setIsSending(true);

    try {
      const response = await fetch(CHAT_API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          messages: nextMessages.map(({ role, content }) => ({
            role,
            content,
          })),
          provider: "auto",
          use_web: toolMode === "web",
        }),
      });

      const rawText = await response.text();

      let data: ChatApiResponse = {};
      try {
        data = rawText ? JSON.parse(rawText) : {};
      } catch {
        data = { detail: rawText };
      }

      if (!response.ok) {
        throw new Error(
          data.detail ||
            data.message ||
            `Request failed with status ${response.status}`,
        );
      }

      const answer = data.answer?.trim();

      if (!answer) {
        throw new Error("The AI returned an empty response.");
      }

      setMessages((current) => [
        ...current,
        {
          id: createId(),
          role: "assistant",
          content: answer,
        },
      ]);
    } catch (requestError) {
      const message =
        requestError instanceof Error
          ? requestError.message
          : "Unable to connect to Power Vasuki AI.";

      setError(message);
    } finally {
      setIsSending(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendMessage();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  }

  return (
    <main
      className="flex h-screen overflow-hidden bg-[#212121] text-white"
      style={{
        fontFamily:
          "'Söhne', ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }}
    >
      {/* Mobile sidebar backdrop */}
      {mobileSidebarOpen && (
        <button
          type="button"
          aria-label="Close sidebar"
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}

      <Sidebar
        collapsed={sidebarCollapsed}
        mobileOpen={mobileSidebarOpen}
        onToggleCollapse={() => setSidebarCollapsed((value) => !value)}
        onCloseMobile={() => setMobileSidebarOpen(false)}
        onNewChat={resetChat}
      />

      <section className="relative flex min-w-0 flex-1 flex-col bg-[#212121]">
        <Header
          onOpenMobileSidebar={() => setMobileSidebarOpen(true)}
          sidebarCollapsed={sidebarCollapsed}
          onRestoreSidebar={() => setSidebarCollapsed(false)}
        />

        {messages.length === 0 ? (
          <WelcomeScreen
            input={input}
            setInput={setInput}
            inputRef={inputRef}
            isSending={isSending}
            toolMode={toolMode}
            onChooseAction={chooseAction}
            onSubmit={handleSubmit}
            onKeyDown={handleKeyDown}
          />
        ) : (
          <Conversation
            messages={messages}
            isSending={isSending}
            error={error}
            input={input}
            setInput={setInput}
            inputRef={inputRef}
            toolMode={toolMode}
            onChooseAction={chooseAction}
            onSubmit={handleSubmit}
            onKeyDown={handleKeyDown}
            messagesEndRef={messagesEndRef}
          />
        )}
      </section>
    </main>
  );
}

function Sidebar({
  collapsed,
  mobileOpen,
  onToggleCollapse,
  onCloseMobile,
  onNewChat,
}: {
  collapsed: boolean;
  mobileOpen: boolean;
  onToggleCollapse: () => void;
  onCloseMobile: () => void;
  onNewChat: () => void;
}) {
  return (
    <aside
      className={[
        "fixed inset-y-0 left-0 z-50 flex flex-col border-r border-white/5 bg-[#2f2f2f] transition-all duration-300 md:relative md:z-20",
        mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        collapsed ? "md:w-0 md:overflow-hidden md:border-r-0" : "w-[280px]",
      ].join(" ")}
    >
      <div className="flex h-14 items-center justify-between px-3">
        <button
          type="button"
          onClick={onNewChat}
          className="flex min-w-0 items-center gap-2 rounded-lg px-2 py-2 text-sm font-medium transition hover:bg-white/10"
        >
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-white text-xs font-black text-[#212121]">
            V
          </span>
          <span className="truncate">Power Vasuki AI</span>
        </button>

        <button
          type="button"
          aria-label="Close sidebar"
          onClick={onCloseMobile}
          className="grid h-9 w-9 place-items-center rounded-lg text-gray-300 hover:bg-white/10 md:hidden"
        >
          <CloseIcon />
        </button>

        <button
          type="button"
          aria-label="Collapse sidebar"
          onClick={onToggleCollapse}
          className="hidden h-9 w-9 place-items-center rounded-lg text-gray-300 hover:bg-white/10 md:grid"
        >
          <SidebarIcon />
        </button>
      </div>

      <div className="px-3 pb-2">
        <button
          type="button"
          onClick={onNewChat}
          className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition hover:bg-white/10"
        >
          <PlusIcon />
          <span>New chat</span>
        </button>

        <button
          type="button"
          className="mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition hover:bg-white/10"
        >
          <SearchIcon />
          <span>Search chats</span>
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        <p className="px-3 pb-2 text-xs font-medium text-gray-400">Recent</p>

        <div className="space-y-1">
          {sampleChats.map((chat) => (
            <button
              type="button"
              key={chat}
              className="w-full truncate rounded-lg px-3 py-2 text-left text-sm text-gray-200 transition hover:bg-white/10"
            >
              {chat}
            </button>
          ))}
        </div>
      </div>

      <div className="border-t border-white/5 p-3">
        <button
          type="button"
          className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left transition hover:bg-white/10"
        >
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-blue-400 to-purple-500 text-sm font-semibold">
            LP
          </span>

          <span className="min-w-0">
            <span className="block truncate text-sm font-medium">
              Lakhan Prajapat
            </span>
            <span className="block truncate text-xs text-gray-400">
              Power Vasuki AI
            </span>
          </span>
        </button>
      </div>
    </aside>
  );
}

function Header({
  onOpenMobileSidebar,
  sidebarCollapsed,
  onRestoreSidebar,
}: {
  onOpenMobileSidebar: () => void;
  sidebarCollapsed: boolean;
  onRestoreSidebar: () => void;
}) {
  return (
    <header className="absolute inset-x-0 top-0 z-30 flex h-14 items-center justify-between px-3 md:px-4">
      <div className="flex items-center gap-1">
        <button
          type="button"
          aria-label="Open sidebar"
          onClick={onOpenMobileSidebar}
          className="grid h-10 w-10 place-items-center rounded-lg text-gray-200 hover:bg-[#2f2f2f] md:hidden"
        >
          <MenuIcon />
        </button>

        {sidebarCollapsed && (
          <button
            type="button"
            aria-label="Restore sidebar"
            onClick={onRestoreSidebar}
            className="hidden h-10 w-10 place-items-center rounded-lg text-gray-200 hover:bg-[#2f2f2f] md:grid"
          >
            <SidebarIcon />
          </button>
        )}

        <button
          type="button"
          className="flex items-center gap-2 rounded-lg px-2 py-2 text-sm font-semibold hover:bg-[#2f2f2f]"
        >
          Power Vasuki AI
          <ChevronDownIcon />
        </button>
      </div>

      <button
        type="button"
        className="rounded-full border border-white/15 px-3 py-1.5 text-xs font-medium text-gray-200 transition hover:bg-[#2f2f2f]"
      >
        Share
      </button>
    </header>
  );
}

function WelcomeScreen({
  input,
  setInput,
  inputRef,
  isSending,
  toolMode,
  onChooseAction,
  onSubmit,
  onKeyDown,
}: ComposerProps & {
  onChooseAction: (mode: Exclude<ToolMode, null>) => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto px-4 pb-8 pt-20 sm:px-6">
      <div className="w-full max-w-[768px] -translate-y-4">
        <h1 className="mb-8 text-center text-[30px] font-semibold tracking-[-0.02em] text-white sm:text-[34px]">
          Where should we begin?
        </h1>

        <Composer
          input={input}
          setInput={setInput}
          inputRef={inputRef}
          isSending={isSending}
          toolMode={toolMode}
          onSubmit={onSubmit}
          onKeyDown={onKeyDown}
          large
        />

        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {starterActions.map((action) => (
            <ActionButton
              key={action.mode}
              active={toolMode === action.mode}
              label={action.label}
              icon={action.icon}
              onClick={() => onChooseAction(action.mode)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function Conversation({
  messages,
  isSending,
  error,
  input,
  setInput,
  inputRef,
  toolMode,
  onSubmit,
  onKeyDown,
  messagesEndRef,
}: ComposerProps & {
  messages: Message[];
  error: string;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
}) {
  return (
    <>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-44 pt-20 sm:px-6">
        <div className="mx-auto w-full max-w-[768px]">
          <div className="space-y-8">
            {messages.map((message) =>
              message.role === "user" ? (
                <div key={message.id} className="flex justify-end">
                  <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-[#2f2f2f] px-4 py-2.5 text-[15px] leading-6 text-white sm:max-w-[75%]">
                    {message.content}
                  </div>
                </div>
              ) : (
                <div key={message.id} className="flex justify-start">
                  <div className="flex max-w-full gap-3">
                    <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-white text-[11px] font-black text-[#212121]">
                      V
                    </div>
                    <div className="min-w-0 whitespace-pre-wrap pt-0.5 text-[15px] leading-7 text-gray-100">
                      {message.content}
                    </div>
                  </div>
                </div>
              ),
            )}

            {isSending && (
              <div className="flex justify-start">
                <div className="flex items-center gap-3">
                  <div className="grid h-7 w-7 place-items-center rounded-full bg-white text-[11px] font-black text-[#212121]">
                    V
                  </div>
                  <TypingDots />
                </div>
              </div>
            )}

            {error && (
              <div className="rounded-xl border border-red-400/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                {error}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-[#212121] via-[#212121] to-transparent px-4 pb-3 pt-12 sm:px-6">
        <div className="pointer-events-auto mx-auto w-full max-w-[768px]">
          <Composer
            input={input}
            setInput={setInput}
            inputRef={inputRef}
            isSending={isSending}
            toolMode={toolMode}
            onSubmit={onSubmit}
            onKeyDown={onKeyDown}
          />

          <p className="mt-2 text-center text-[11px] text-gray-500">
            Power Vasuki AI can make mistakes. Verify important information.
          </p>
        </div>
      </div>
    </>
  );
}

type ComposerProps = {
  input: string;
  setInput: (value: string) => void;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  isSending: boolean;
  toolMode: ToolMode;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  large?: boolean;
};

function Composer({
  input,
  setInput,
  inputRef,
  isSending,
  toolMode,
  onSubmit,
  onKeyDown,
  large = false,
}: ComposerProps) {
  return (
    <form
      onSubmit={onSubmit}
      className={[
        "relative overflow-hidden rounded-[26px] border border-white/15 bg-[#2f2f2f] shadow-[0_0_0_1px_rgba(255,255,255,0.02)] transition focus-within:border-white/25",
        large ? "min-h-[116px]" : "min-h-[104px]",
      ].join(" ")}
    >
      <textarea
        ref={inputRef}
        value={input}
        onChange={(event) => setInput(event.target.value)}
        onKeyDown={onKeyDown}
        rows={2}
        placeholder="Ask Power Vasuki AI"
        className="max-h-48 min-h-[54px] w-full resize-none bg-transparent px-5 pt-4 text-[16px] leading-6 text-white outline-none placeholder:text-gray-400"
      />

      <div className="flex items-center justify-between gap-3 px-3 pb-3">
        <div className="flex min-w-0 items-center gap-1">
          <button
            type="button"
            aria-label="Add attachment"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-gray-300 transition hover:bg-white/10"
          >
            <PlusIcon />
          </button>

          {toolMode && (
            <span className="truncate rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-gray-200">
              {toolModeLabel(toolMode)}
            </span>
          )}
        </div>

        <button
          type="submit"
          disabled={!input.trim() || isSending}
          aria-label="Send message"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#4f86f7] text-white transition hover:bg-[#6698ff] disabled:cursor-not-allowed disabled:bg-gray-600 disabled:text-gray-400"
        >
          {isSending ? <StopIcon /> : <ArrowUpIcon />}
        </button>
      </div>
    </form>
  );
}

function ActionButton({
  label,
  icon,
  active,
  onClick,
}: {
  label: string;
  icon: ReactNode;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "flex items-center gap-2 rounded-full border px-3.5 py-2 text-sm transition",
        active
          ? "border-blue-400/50 bg-blue-500/10 text-blue-200"
          : "border-white/10 bg-transparent text-gray-300 hover:bg-[#2f2f2f]",
      ].join(" ")}
    >
      <span className="text-gray-300">{icon}</span>
      {label}
    </button>
  );
}

function toolModeLabel(mode: Exclude<ToolMode, null>) {
  const labels: Record<Exclude<ToolMode, null>, string> = {
    image: "Create image",
    write: "Write",
    web: "Search web",
    analyze: "Analyze",
  };

  return labels[mode];
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1 py-2">
      {[0, 1, 2].map((item) => (
        <span
          key={item}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400"
          style={{ animationDelay: `${item * 120}ms` }}
        />
      ))}
    </div>
  );
}

function IconBase({
  children,
  className = "h-5 w-5",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

function MenuIcon() {
  return (
    <IconBase>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </IconBase>
  );
}

function CloseIcon() {
  return (
    <IconBase>
      <path d="m6 6 12 12M18 6 6 18" />
    </IconBase>
  );
}

function SidebarIcon() {
  return (
    <IconBase>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16" />
    </IconBase>
  );
}

function PlusIcon() {
  return (
    <IconBase>
      <path d="M12 5v14M5 12h14" />
    </IconBase>
  );
}

function SearchIcon() {
  return (
    <IconBase>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </IconBase>
  );
}

function ChevronDownIcon() {
  return (
    <IconBase className="h-4 w-4">
      <path d="m8 10 4 4 4-4" />
    </IconBase>
  );
}

function ArrowUpIcon() {
  return (
    <IconBase>
      <path d="M12 19V5M6.5 10.5 12 5l5.5 5.5" />
    </IconBase>
  );
}

function StopIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill="currentColor"
      aria-hidden="true"
    >
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}

function ImageIcon() {
  return (
    <IconBase className="h-4 w-4">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="8.5" cy="9" r="1.5" />
      <path d="m21 15-5-5L5 20" />
    </IconBase>
  );
}

function PenIcon() {
  return (
    <IconBase className="h-4 w-4">
      <path d="m4 20 4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20Z" />
      <path d="m14 7 3 3" />
    </IconBase>
  );
}

function GlobeIcon() {
  return (
    <IconBase className="h-4 w-4">
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" />
    </IconBase>
  );
}

function ChartIcon() {
  return (
    <IconBase className="h-4 w-4">
      <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />
    </IconBase>
  );
}
