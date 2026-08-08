"use client";

import {
  ChangeEvent,
  FormEvent,
  KeyboardEvent,
  ReactNode,
  RefObject,
  useEffect,
  useRef,
  useState,
} from "react";
import type { User } from "@supabase/supabase-js";
import ReactMarkdown from "react-markdown";

import MemoryKnowledgePanel from "@/components/MemoryKnowledgePanel";
import SmartFileWorkspace from "@/components/SmartFileWorkspace";
import {
  analyzeAttachment,
  analyzeSmartFiles,
  generateImage,
  streamChat,
  warmBackend,
  type ChatMessage,
  type SmartFileArtifact,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";
import {
  consumePuterImageQuota,
  releasePuterImageQuota,
  fetchAccountPlan,
  fetchPuterContext,
  type AccountPlan,
  type PuterImageQuota,
} from "@/lib/plans";
import {
  connectPuter,
  generatePuterImage4K,
  streamPuterChat,
} from "@/lib/puter";

const VASUKI_LOGO_URL =
  "https://images.jdmagicbox.com/v2/comp/jaipur/a2/0141px141.x141.260404193718.t6a2/catalogue/vasuki-nfc-luniawas-jaipur-printing-services-604tb4s28a.jpg";

const MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024;
const ALLOWED_ATTACHMENT_TYPES = new Set([
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/plain",
  "text/markdown",
]);

const ALLOWED_ATTACHMENT_EXTENSIONS = new Set([
  ".jpg",
  ".jpeg",
  ".png",
  ".webp",
  ".gif",
  ".pdf",
  ".docx",
  ".txt",
  ".md",
]);

type SourceInfo = {
  title?: string;
  url?: string;
  domain?: string;
  published_date?: string;
  source_type?: string;
  document_id?: string;
  page_number?: number;
};

type UiMessage = ChatMessage & {
  id: string;
  imageUrl?: string;
  fileName?: string;
  provider?: string;
  sources?: SourceInfo[];
  artifacts?: SmartFileArtifact[];
};

type StoredMessage = {
  role: "user" | "assistant";
  content: string;
  imageUrl?: string;
  fileName?: string;
  provider?: string;
  sources?: SourceInfo[];
};

type ChatRecord = {
  id: string;
  title: string;
  messages: unknown;
  updated_at: string;
};

type QuotaUiStatus = {
  minuteLimit: number;
  minuteRemaining: number;
  dailyLimit: number;
  dailyRemaining: number;
};

type ChatMessageRow = {
  client_id?: string;
  role?: "user" | "assistant";
  content?: string;
  image_url?: string;
  file_name?: string;
  provider?: string;
  sources?: unknown;
};

type PendingAttachment = {
  file: File;
  previewUrl?: string;
  kind: "image" | "document";
};

type ActionMode = "chat" | "image" | "write" | "web" | "analyze";
type AiEngine = "vasuki" | "puter";

/* VASUKI_VOICE_TYPES_START */
type SpeechRecognitionResultLike = {
  isFinal: boolean;
  0?: {
    transcript?: string;
  };
};

type SpeechRecognitionEventLike = Event & {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
};

type SpeechRecognitionErrorEventLike = Event & {
  error?: string;
};

type BrowserSpeechRecognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type BrowserSpeechRecognitionConstructor =
  new () => BrowserSpeechRecognition;

declare global {
  interface Window {
    SpeechRecognition?: BrowserSpeechRecognitionConstructor;
    webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
  }
}
/* VASUKI_VOICE_TYPES_END */

type ChatResponse = {
  answer?: string;
  sources?: SourceInfo[];
};

type ImageResponse = {
  url?: string;
  provider?: string;
};

type VisionResponse = {
  answer?: string;
  url?: string;
  provider?: string;
  operation?: "analyze" | "edit";
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
];

function makeId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function fileSizeLabel(bytes: number) {
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileToDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Image preview could not be loaded."));
    reader.readAsDataURL(file);
  });
}

/* VASUKI_INLINE_ARTIFACT_FIX_START */
function attachmentExtension(name: string) {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

function wantsDownloadableArtifact(value: string) {
  const normalized = value.toLocaleLowerCase();

  const hasFormat =
    /\b(?:pdf|docx|word\s+(?:file|document)|txt|text\s+file|qr(?:\s+code)?|one[-\s]?sheet|single[-\s]?page|downloadable\s+file)\b/i.test(
      normalized,
    ) ||
    /पीडीएफ|क्यूआर|एक\s*शीट/.test(normalized);

  const hasAction =
    /\b(?:create|make|generate|prepare|export|download|provide|give|convert|save|print|build|banao|bana\s*do|banado|bana|de\s*do|dedo|chahiye|create\s+karo|bana\s+kar\s+do|pdf\s+m(?:e|ein))\b/i.test(
      normalized,
    ) ||
    /बना|बनाओ|दे\s*दो|डाउनलोड|तैयार/.test(normalized);

  return (
    (hasFormat && hasAction) ||
    /\bqr(?:\s+code)?\b[\s\S]{0,120}https?:\/\//i.test(normalized) ||
    /https?:\/\/\S+[\s\S]{0,120}\bqr(?:\s+code)?\b/i.test(normalized)
  );
}
/* VASUKI_INLINE_ARTIFACT_FIX_END */

function normaliseSources(value: unknown): SourceInfo[] {
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
}

function sourceDomain(source: SourceInfo) {
  if (source.source_type === "document" || !source.url) {
    return source.domain?.trim() || "Your document";
  }
  if (source.domain?.trim()) return source.domain.trim().replace(/^www\./, "");
  try {
    return new URL(source.url).hostname.replace(/^www\./, "");
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
  return messages.map(
    ({ role, content, imageUrl, fileName, provider, sources }) => ({
      role,
      content,
      // Large uploaded/generated data URLs are intentionally not stored inside
      // the Supabase JSON row. The answer and file name remain in chat history.
      imageUrl:
        imageUrl && !imageUrl.startsWith("data:") ? imageUrl : undefined,
      fileName,
      provider,
      sources: normaliseSources(sources),
    }),
  );
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
        fileName:
          typeof candidate.fileName === "string"
            ? candidate.fileName
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

function restoreMessageRows(value: unknown): UiMessage[] {
  if (!Array.isArray(value)) return [];

  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const row = item as ChatMessageRow;

    if (
      (row.role !== "user" && row.role !== "assistant") ||
      typeof row.content !== "string"
    ) {
      return [];
    }

    return [
      {
        id:
          typeof row.client_id === "string" && row.client_id
            ? row.client_id
            : makeId(),
        role: row.role,
        content: row.content,
        imageUrl:
          typeof row.image_url === "string" ? row.image_url : undefined,
        fileName:
          typeof row.file_name === "string" ? row.file_name : undefined,
        provider:
          typeof row.provider === "string" ? row.provider : undefined,
        sources: normaliseSources(row.sources),
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
  const [attachment, setAttachment] = useState<PendingAttachment | null>(null);
  const [busy, setBusy] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<ActionMode>("chat");
  const [webEnabled, setWebEnabled] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [knowledgePanelOpen, setKnowledgePanelOpen] = useState(false);
  const [smartFilesOpen, setSmartFilesOpen] = useState(false);
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [documentsEnabled, setDocumentsEnabled] = useState(false);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [streamingStarted, setStreamingStarted] = useState(false);
  const [quotaStatus, setQuotaStatus] = useState<QuotaUiStatus | null>(null);
  const [accountPlan, setAccountPlan] = useState<AccountPlan | null>(null);
  const [aiEngine, setAiEngine] = useState<AiEngine>("vasuki");
  const [puterImageQuota, setPuterImageQuota] = useState<PuterImageQuota | null>(null);
  const [puterAccount, setPuterAccount] = useState("");
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [planBusy, setPlanBusy] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
  const chatLoadTokenRef = useRef("");

  useEffect(() => {
    const wakeBackend = () => {
      void warmBackend();
    };
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        wakeBackend();
      }
    };

    wakeBackend();

    const intervalId = window.setInterval(
      wakeBackend,
      4 * 60 * 1000,
    );

    window.addEventListener("focus", wakeBackend);
    window.addEventListener("online", wakeBackend);
    document.addEventListener(
      "visibilitychange",
      handleVisibility,
    );

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", wakeBackend);
      window.removeEventListener("online", wakeBackend);
      document.removeEventListener(
        "visibilitychange",
        handleVisibility,
      );
    };
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
        setAttachment(null);
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
    void loadChatHistory(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  useEffect(() => {
    if (!user) return;
    void refreshAccountPlan();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function currentAccessToken() {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    const accessToken = session?.access_token;
    if (!accessToken) {
      throw new Error("Login session expired. Please sign in again.");
    }
    return accessToken;
  }

  async function refreshAccountPlan() {
    try {
      const accessToken = await currentAccessToken();
      const nextPlan = await fetchAccountPlan(accessToken);
      setAccountPlan(nextPlan);
      if (!nextPlan.puter_access) {
        setAiEngine("vasuki");
        setPuterAccount("");
      }
    } catch (planError) {
      setAccountPlan(null);
      setAiEngine("vasuki");
      console.error(planError);
    }
  }

  async function selectPuterEngine() {
    if (!accountPlan?.puter_access) {
      setError("Vasuki Pro is currently locked.");
      setModelMenuOpen(false);
      return;
    }

    setPlanBusy(true);
    setError("");

    try {
      const account = await connectPuter();
      setPuterAccount(
        account.username || account.email || "Connected",
      );
      setAiEngine("puter");
      setModelMenuOpen(false);
    } catch (puterError) {
      setError(
        puterError instanceof Error
          ? puterError.message
          : "The Vasuki Pro account could not be connected.",
      );
    } finally {
      setPlanBusy(false);
    }
  }

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
      .order("updated_at", { ascending: false })
      .limit(100);

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
    const loadToken = makeId();
    chatLoadTokenRef.current = loadToken;

    setCurrentChatId(record.id);
    setMessages(restoreMessages(record.messages));
    setAttachment(null);
    setInput("");
    setError("");
    setMode("chat");
    setWebEnabled(false);
    setMobileSidebarOpen(false);

    void (async () => {
      const { data, error: messageError } = await supabase
        .from("user_chat_messages")
        .select(
          "client_id,role,content,image_url,file_name,provider,sources,position",
        )
        .eq("chat_id", record.id)
        .eq("user_id", user?.id ?? "")
        .order("position", { ascending: true });

      if (
        chatLoadTokenRef.current === loadToken &&
        !messageError &&
        Array.isArray(data) &&
        data.length > 0
      ) {
        setMessages(restoreMessageRows(data));
      }
    })();

    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function persistMessageRows(
    chatId: string,
    nextMessages: UiMessage[],
  ) {
    if (!user) return false;

    const now = new Date().toISOString();
    const rows = nextMessages.map((message, position) => ({
      chat_id: chatId,
      user_id: user.id,
      client_id: message.id,
      position,
      role: message.role,
      content: message.content,
      image_url:
        message.imageUrl && !message.imageUrl.startsWith("data:")
          ? message.imageUrl
          : null,
      file_name: message.fileName ?? null,
      provider: message.provider ?? null,
      sources: normaliseSources(message.sources),
      updated_at: now,
    }));

    const { error: rowError } = await supabase
      .from("user_chat_messages")
      .upsert(rows, { onConflict: "chat_id,client_id" });

    return !rowError;
  }

  async function persistChat(
    nextMessages: UiMessage[],
    targetChatId: string | null,
  ) {
    if (!user || nextMessages.length === 0) {
      return targetChatId;
    }

    const now = new Date().toISOString();
    const boundedFallback = storedMessages(nextMessages.slice(-20));
    const payload = {
      user_id: user.id,
      title: chatTitle(nextMessages),
      messages: boundedFallback,
      updated_at: now,
    };

    let chatId = targetChatId;

    if (chatId) {
      const { error: updateError } = await supabase
        .from("user_chats")
        .update(payload)
        .eq("id", chatId)
        .eq("user_id", user.id);

      if (updateError) {
        throw new Error(`Chat save failed: ${updateError.message}`);
      }
    } else {
      const { data, error: insertError } = await supabase
        .from("user_chats")
        .insert(payload)
        .select("id")
        .single();

      if (insertError) {
        throw new Error(`Chat save failed: ${insertError.message}`);
      }

      chatId = String(data.id);
      setCurrentChatId(chatId);
    }

    const rowsSaved = await persistMessageRows(chatId, nextMessages);

    if (!rowsSaved) {
      const { error: fallbackError } = await supabase
        .from("user_chats")
        .update({
          messages: storedMessages(nextMessages),
          updated_at: now,
        })
        .eq("id", chatId)
        .eq("user_id", user.id);

      if (fallbackError) {
        throw new Error(`Chat save failed: ${fallbackError.message}`);
      }
    }

    await loadChatHistory(false);
    return chatId;
  }

  function startNewChat() {
    setCurrentChatId(null);
    setMessages([]);
    setAttachment(null);
    setInput("");
    setError("");
    setMode("chat");
    setWebEnabled(false);
    setMobileSidebarOpen(false);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function deleteChatById(chatId: string, title: string) {
    if (!user || historyBusy) return;

    const confirmed = window.confirm(
      `Delete \"${title || "this chat"}\" permanently?`,
    );
    if (!confirmed) return;

    setHistoryBusy(true);
    setError("");

    const { error: deleteError } = await supabase
      .from("user_chats")
      .delete()
      .eq("id", chatId)
      .eq("user_id", user.id);

    setHistoryBusy(false);

    if (deleteError) {
      setError(`Chat delete failed: ${deleteError.message}`);
      return;
    }

    setChatRecords((current) => current.filter((chat) => chat.id !== chatId));
    if (currentChatId === chatId) {
      startNewChat();
    }
  }

  async function deleteCurrentChat() {
    if (currentChatId) {
      const current = chatRecords.find((chat) => chat.id === currentChatId);
      await deleteChatById(currentChatId, current?.title || "this chat");
      return;
    }

    if (messages.length > 0 && window.confirm("Clear this unsaved chat?")) {
      startNewChat();
    }
  }

  async function chooseAttachment(file: File) {
    setError("");

    const extension = attachmentExtension(file.name);
    if (
      !ALLOWED_ATTACHMENT_TYPES.has(file.type) &&
      !ALLOWED_ATTACHMENT_EXTENSIONS.has(extension)
    ) {
      setError(
        "Only JPG, PNG, WEBP, GIF, PDF, DOCX, TXT and MD files are supported.",
      );
      return;
    }

    if (file.size > MAX_ATTACHMENT_BYTES) {
      setError("File must be 15 MB or smaller.");
      return;
    }

    const isImage = file.type.startsWith("image/");
    const previewUrl = isImage ? await fileToDataUrl(file) : undefined;

    setAttachment({
      file,
      previewUrl,
      kind: isImage ? "image" : "document",
    });
    setMode("chat");
    setWebEnabled(false);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  function selectAction(action: (typeof actionItems)[number]) {
    setMode(action.mode);
    setWebEnabled(action.mode === "web");
    setInput((current) => {
      const isPresetPrompt = actionItems.some(
        (item) => item.prompt && current === item.prompt,
      );
      return !current || isPresetPrompt ? action.prompt : current;
    });
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  function cancelAction(action: (typeof actionItems)[number]) {
    setMode("chat");
    setWebEnabled(false);

    if (action.mode === "analyze") {
      setAttachment(null);
    }

    setInput((current) =>
      action.prompt && current === action.prompt ? "" : current,
    );
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();

    const text = input.trim();
    const selectedAttachment = attachment;

    if ((!text && !selectedAttachment) || busy || !user) return;

    const effectiveText =
      text ||
      (selectedAttachment?.kind === "document"
        ? "Analyze this document in detail. If it is a question paper, answer every question in the correct order."
        : "Analyze this image in detail and explain all important information.");

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

      const requestedDownload = wantsDownloadableArtifact(effectiveText);
      const shouldUseSmartFiles =
        requestedDownload ||
        selectedAttachment?.kind === "document";

      if (shouldUseSmartFiles) {
        const data = await analyzeSmartFiles(
          selectedAttachment ? [selectedAttachment.file] : [],
          effectiveText,
          accessToken,
        );

        if (requestedDownload && data.files.length === 0) {
          throw new Error(
            "A downloadable file was requested, but the file generator returned no file. Please retry once.",
          );
        }

        const previewArtifact = data.files.find((artifact) =>
          artifact.mime_type.toLowerCase().startsWith("image/"),
        );

        finalMessages = [
          ...nextMessages,
          {
            id: makeId(),
            role: "assistant",
            content:
              data.answer.trim() ||
              (data.files.length > 0
                ? "Your requested files are ready below."
                : "The document was analyzed."),
            imageUrl: previewArtifact?.data_url,
            provider: data.provider,
            artifacts: data.files,
          },
        ];
      } else if (selectedAttachment) {
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
        let imageUrl = "";
        let imageProvider = "";
        let imageQuotaText = "";

        if (aiEngine === "puter") {
          if (!accountPlan?.puter_access) {
            throw new Error("Vasuki Pro access required.");
          }

          const quota = await consumePuterImageQuota(accessToken);
          setPuterImageQuota(quota);
          imageQuotaText =
            ` · Today ${quota.daily_remaining}/${quota.daily_limit} left`;

          try {
            const result = await generatePuterImage4K(effectiveText);
            imageUrl = result.url;
            imageProvider = result.provider;
          } catch (puterImageError) {
            try {
              const fallback = (await generateImage(
                effectiveText,
                accessToken,
              )) as ImageResponse;

              imageUrl =
                typeof fallback.url === "string"
                  ? fallback.url.trim()
                  : "";
              imageProvider = fallback.provider
                ? `Vasuki fallback · ${fallback.provider}`
                : "Vasuki fallback";

              if (!imageUrl) {
                throw new Error(
                  "Vasuki fallback returned an empty image.",
                );
              }
            } catch (fallbackError) {
              try {
                const restored =
                  await releasePuterImageQuota(accessToken);
                setPuterImageQuota(restored);
              } catch {
                // The backend will still reset the quota on the next day.
              }

              const puterMessage =
                puterImageError instanceof Error
                  ? puterImageError.message
                  : "Puter image credits unavailable.";
              const fallbackMessage =
                fallbackError instanceof Error
                  ? fallbackError.message
                  : "Vasuki fallback unavailable.";

              throw new Error(
                `${puterMessage} Vasuki fallback also failed: ` +
                  fallbackMessage,
              );
            }
          }
        } else {
          const data = (await generateImage(
            effectiveText,
            accessToken,
          )) as ImageResponse;
          imageUrl =
            typeof data.url === "string" ? data.url.trim() : "";
          imageProvider = data.provider || "";
        }

        if (!imageUrl) {
          throw new Error("Image provider returned an empty image.");
        }

        finalMessages = [
          ...nextMessages,
          {
            id: makeId(),
            role: "assistant",
            content: `Image generated${
              imageProvider ? ` with ${imageProvider}` : ""
            }.${imageQuotaText}`,
            imageUrl,
            provider: imageProvider,
          },
        ];
      } else {
        const requestMessages: ChatMessage[] = nextMessages
          .filter(
            ({ content }) =>
              typeof content === "string" &&
              content.trim().length > 0,
          )
          .slice(-100)
          .map(({ role, content }) => ({
            role,
            content: content.trim(),
          }));
        const assistantId = makeId();
        let streamedAnswer = "";
        let providerName = "";
        let answerSources: SourceInfo[] = [];

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

        const onStreamToken = (token: string) => {
          streamedAnswer += token;
          setStreamingStarted(true);
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? { ...message, content: streamedAnswer }
                : message,
            ),
          );
        };

        if (aiEngine === "puter") {
          if (!accountPlan?.puter_access) {
            throw new Error("Vasuki Pro access required.");
          }

          const puterContext = await fetchPuterContext(
            accessToken,
            memoryEnabled,
          );
          const usedModel = await streamPuterChat(
            requestMessages,
            {
              systemContext: puterContext.system_prompt,
              signal: controller.signal,
            },
            onStreamToken,
          );
          providerName = `vasuki-pro:${usedModel}`;
        } else {
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
            onStreamToken,
          );

          providerName = meta.provider || "";
          answerSources = normaliseSources(meta.sources);

          if (typeof meta.daily_remaining === "number") {
            setQuotaStatus({
              minuteLimit:
                typeof meta.minute_limit === "number"
                  ? meta.minute_limit
                  : 15,
              minuteRemaining:
                typeof meta.minute_remaining === "number"
                  ? meta.minute_remaining
                  : 0,
              dailyLimit:
                typeof meta.daily_limit === "number"
                  ? meta.daily_limit
                  : 250,
              dailyRemaining: meta.daily_remaining,
            });
          }
        }

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
            provider: providerName,
            sources: answerSources,
          },
        ];
      }

      setMessages(finalMessages);
      setAttachment(null);
      setMode("chat");
      await persistChat(finalMessages, currentChatId);
    } catch (caughtError) {
      // Failed streams can leave an empty assistant placeholder in an old
      // chat. Remove it so the next request remains valid.
      setMessages((current) =>
        current.filter(
          (message) =>
            !(
              message.role === "assistant" &&
              !message.content.trim()
            ),
        ),
      );

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
          <p>Securely loading your account…</p>
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
            Sign in with Google to save your chats and access the same
            history on any device.
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
            After signing in, each user can access only their own chats.
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
  const welcomeName =
    profileName.trim().split(/\s+/)[0] || "there";

  const planLabel =
    accountPlan?.plan === "owner"
      ? "OWNER"
      : accountPlan?.plan === "pro"
        ? "PRO"
        : "FREE";

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
            Recent {historyBusy ? "· loading…" : ""}
          </p>

          {chatRecords.length === 0 && !historyBusy ? (
            <p className="pv-empty-history">Abhi koi saved chat nahi hai.</p>
          ) : (
            chatRecords.map((chat) => (
              <div className="pv-recent-row" key={chat.id}>
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
                  onClick={() => openChat(chat)}
                  title={chat.title}
                >
                  {chat.title}
                </button>
                <button
                  type="button"
                  className="pv-recent-delete"
                  aria-label={`Delete ${chat.title}`}
                  title="Delete chat"
                  onClick={() => void deleteChatById(chat.id, chat.title)}
                >
                  <Icon name="trash" />
                </button>
              </div>
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

            <div className="pv-model-switcher">
              <button
                type="button"
                className="pv-model-button"
                onClick={() => setModelMenuOpen((open) => !open)}
                aria-expanded={modelMenuOpen}
              >
                <Logo className="pv-header-logo" />
                <span>
                  {aiEngine === "puter"
                    ? "Vasuki Pro"
                    : "Vasuki AI"}
                </span>
                <Icon name="chevron" />
              </button>

              {modelMenuOpen && (
                <div className="pv-model-menu">
                  <button
                    type="button"
                    className={
                      aiEngine === "vasuki" ? "is-active" : ""
                    }
                    onClick={() => {
                      setAiEngine("vasuki");
                      setModelMenuOpen(false);
                    }}
                  >
                    <strong>Vasuki AI</strong>
                    <small>
                      Normal · Web · Memory · Documents
                    </small>
                  </button>

                  <button
                    type="button"
                    className={
                      aiEngine === "puter" ? "is-active" : ""
                    }
                    disabled={planBusy}
                    onClick={() => void selectPuterEngine()}
                  >
                    <strong>Vasuki Pro</strong>
                    <small>
                      Smart answers · Complete coding · 100 images/day
                    </small>
                  </button>

                  {puterAccount && (
                    <p className="pv-puter-account">
                      Connected: {puterAccount}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="pv-header-right">
            <span
              className={`pv-plan-badge pv-plan-badge--${planLabel.toLowerCase()}`}
              title={
                accountPlan?.pro_expires_at
                  ? `Pro until ${new Date(
                      accountPlan.pro_expires_at,
                    ).toLocaleDateString()}`
                  : planLabel
              }
            >
              {planLabel}
            </span>
            {aiEngine === "puter" && puterImageQuota && (
              <span
                className="pv-quota-indicator"
                title="Vasuki Pro image quota resets daily"
              >
                Images: {puterImageQuota.daily_remaining}/
                {puterImageQuota.daily_limit}
              </span>
            )}
            {quotaStatus && (
              <span
                className="pv-quota-indicator"
                title={`${quotaStatus.minuteRemaining}/${quotaStatus.minuteLimit} requests available this minute`}
              >
                Today: {quotaStatus.dailyRemaining}/{quotaStatus.dailyLimit}
              </span>
            )}
            <span className="pv-saved-indicator">
              {currentChatId ? "Saved" : "New chat"}
            </span>
            {hasMessages && (
              <button
                type="button"
                className="pv-delete-chat-button"
                aria-label="Delete current chat"
                title="Delete current chat"
                onClick={() => void deleteCurrentChat()}
              >
                <Icon name="trash" />
              </button>
            )}
          </div>
        </header>

        {!hasMessages ? (
          <section className="pv-welcome">
            <div className="pv-welcome-inner">
              <Logo className="pv-welcome-logo" />
              <div className="pv-welcome-heading">
                <p>Hi {welcomeName}, welcome</p>
                <h1>How can I help you today?</h1>
              </div>

              <Composer
                input={input}
                setInput={setInput}
                attachment={attachment}
                busy={busy}
                mode={mode}
                textareaRef={textareaRef}
                onAttachmentSelected={chooseAttachment}
                onAttachmentRemoved={() => setAttachment(null)}
                onSubmit={submit}
                onStop={stopStreaming}
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
                    aria-label={
                      mode === action.mode
                        ? `Cancel ${action.label}`
                        : action.label
                    }
                    title={
                      mode === action.mode
                        ? "Cancel and return to normal chat"
                        : action.label
                    }
                    onClick={() =>
                      mode === action.mode
                        ? cancelAction(action)
                        : selectAction(action)
                    }
                  >
                    <Icon name={action.icon} />
                    <span>{action.label}</span>
                    {mode === action.mode && (
                      <span
                        className="pv-action-cancel"
                        aria-hidden="true"
                      >
                        ×
                      </span>
                    )}
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
                              alt="Generated or edited by Vasuki AI"
                            />
                          )}

                          <InlineArtifactDownloads
                            artifacts={message.artifacts}
                          />

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
                        <div className="pv-user-message-stack">
                          {message.imageUrl && (
                            <img
                              className="pv-user-upload-image"
                              src={message.imageUrl}
                              alt={message.fileName || "Uploaded image"}
                            />
                          )}
                          {message.fileName && !message.imageUrl && (
                            <div className="pv-user-file-chip">
                              <Icon name="file" />
                              <span>{message.fileName}</span>
                            </div>
                          )}
                          <div className="pv-user-bubble">
                            {message.content}
                          </div>
                        </div>
                      )}
                    </div>
                  </article>
                ))}

                {busy && !streamingStarted && (
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
                  attachment={attachment}
                  busy={busy}
                  mode={mode}
                  textareaRef={textareaRef}
                  onAttachmentSelected={chooseAttachment}
                  onAttachmentRemoved={() => setAttachment(null)}
                  onSubmit={submit}
                  onStop={stopStreaming}
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

      <SmartFileWorkspace
        open={smartFilesOpen}
        onClose={() => setSmartFilesOpen(false)}
      />

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
  attachment,
  busy,
  mode,
  textareaRef,
  onAttachmentSelected,
  onAttachmentRemoved,
  onSubmit,
  onStop,
  onKeyDown,
  welcome = false,
}: {
  input: string;
  setInput: (value: string) => void;
  attachment: PendingAttachment | null;
  busy: boolean;
  mode: ActionMode;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  onAttachmentSelected: (file: File) => Promise<void>;
  onAttachmentRemoved: () => void;
  onSubmit: (event?: FormEvent<HTMLFormElement>) => Promise<void>;
  onStop: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  welcome?: boolean;
}) {
  const photoInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);


  /* VASUKI_VOICE_LOGIC_START */
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const speechBaseInputRef = useRef("");
  const [isListening, setIsListening] = useState(false);
  const [speechError, setSpeechError] = useState("");

  useEffect(() => {
    return () => {
      const recognition = recognitionRef.current;
      recognitionRef.current = null;
      if (recognition) {
        try {
          recognition.abort();
        } catch {
          // Recognition may already be stopped.
        }
      }
    };
  }, []);

  function voiceErrorMessage(error?: string) {
    switch (error) {
      case "not-allowed":
      case "service-not-allowed":
        return "Microphone permission was denied. Allow microphone access and try again.";
      case "audio-capture":
        return "No working microphone was found on this device.";
      case "no-speech":
        return "No speech was detected. Tap the microphone and speak again.";
      case "network":
        return "Voice recognition could not connect. Check your internet connection.";
      default:
        return "Voice input could not start. Please try again.";
    }
  }

  function endVoiceInput(abort = false) {
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    setIsListening(false);

    if (!recognition) return;

    try {
      if (abort) {
        recognition.abort();
      } else {
        recognition.stop();
      }
    } catch {
      // Recognition may already be stopped.
    }
  }

  function toggleVoiceInput() {
    if (busy) return;

    if (isListening) {
      endVoiceInput(false);
      return;
    }

    const SpeechRecognitionApi =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognitionApi) {
      setSpeechError(
        "Voice typing is not supported in this browser. Open Vasuki AI in Chrome or Edge.",
      );
      return;
    }

    const recognition = new SpeechRecognitionApi();
    const browserLanguage =
      navigator.language || document.documentElement.lang || "en-IN";

    speechBaseInputRef.current = input.trim();
    let finalTranscript = "";

    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = /[\u0900-\u097F]/.test(input)
      ? "hi-IN"
      : browserLanguage;

    recognition.onstart = () => {
      setSpeechError("");
      setIsListening(true);
      void warmBackend();
    };

    recognition.onresult = (event) => {
      let interimTranscript = "";

      for (
        let index = event.resultIndex;
        index < event.results.length;
        index += 1
      ) {
        const result = event.results[index];
        const transcript = result?.[0]?.transcript?.trim() || "";
        if (!transcript) continue;

        if (result.isFinal) {
          finalTranscript = `${finalTranscript} ${transcript}`.trim();
        } else {
          interimTranscript =
            `${interimTranscript} ${transcript}`.trim();
        }
      }

      const spokenText =
        `${finalTranscript} ${interimTranscript}`.trim();
      const originalText = speechBaseInputRef.current;

      setInput(
        originalText && spokenText
          ? `${originalText} ${spokenText}`
          : originalText || spokenText,
      );
    };

    recognition.onerror = (event) => {
      if (event.error !== "aborted") {
        setSpeechError(voiceErrorMessage(event.error));
      }
      setIsListening(false);
      if (recognitionRef.current === recognition) {
        recognitionRef.current = null;
      }
    };

    recognition.onend = () => {
      setIsListening(false);
      if (recognitionRef.current === recognition) {
        recognitionRef.current = null;
      }
      requestAnimationFrame(() => textareaRef.current?.focus());
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();
    } catch {
      recognitionRef.current = null;
      setIsListening(false);
      setSpeechError("Voice input could not start. Please try again.");
    }
  }

  async function handleComposerSubmit(
    event?: FormEvent<HTMLFormElement>,
  ) {
    endVoiceInput(true);
    await onSubmit(event);
  }
  /* VASUKI_VOICE_LOGIC_END */

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    setAttachmentMenuOpen(false);
    if (file) {
      void onAttachmentSelected(file);
    }
  }

  return (
    <div
      className={[
        "pv-composer-frame",
        welcome ? "pv-composer-frame--welcome" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {welcome && (
        <span
          className="pv-composer-light"
          aria-hidden="true"
        />
      )}
      <form
        className={`pv-composer ${
          welcome ? "pv-composer--welcome" : ""
        }`}
        onSubmit={(event) => void handleComposerSubmit(event)}
      >
      <input
        ref={photoInputRef}
        className="pv-file-input"
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif,.jpg,.jpeg,.png,.webp,.gif"
        onChange={handleFileChange}
      />
      <input
        ref={fileInputRef}
        className="pv-file-input"
        type="file"
        accept="application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown,.pdf,.docx,.txt,.md"
        onChange={handleFileChange}
      />

      {attachment && (
        <div className="pv-attachment-preview">
          {attachment.previewUrl ? (
            <img src={attachment.previewUrl} alt={attachment.file.name} />
          ) : (
            <span className="pv-attachment-file-icon">
              <Icon name="file" />
            </span>
          )}
          <span className="pv-attachment-copy">
            <strong>{attachment.file.name}</strong>
            <small>
              {attachment.kind === "image" ? "Image" : "Document"} ·{" "}
              {fileSizeLabel(attachment.file.size)}
            </small>
          </span>
          <button
            type="button"
            className="pv-attachment-remove"
            aria-label="Remove attachment"
            onClick={onAttachmentRemoved}
          >
            <Icon name="close" />
          </button>
        </div>
      )}

      <textarea
        ref={textareaRef}
        rows={2}
        value={input}
        onChange={(event) => setInput(event.target.value)}
        onFocus={() => void warmBackend()}
        onPointerDown={() => void warmBackend()}
        onKeyDown={onKeyDown}
        placeholder={
          attachment
            ? "Ask about this image/file or describe an edit"
            : mode === "image"
              ? "Describe the image you want to create"
              : "Ask Vasuki AI"
        }
      />


      {(isListening || speechError) && (
        <div
          className={[
            "pv-speech-status",
            speechError ? "pv-speech-status--error" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          role="status"
          aria-live="polite"
        >
          {speechError || "Listening… Speak now"}
        </div>
      )}

      <div className="pv-composer-toolbar">
        <div className="pv-composer-tools">
          <div className="pv-attachment-menu-wrap">
            <button
              type="button"
              aria-label="Add photo or file"
              title="Add photo or file"
              aria-expanded={attachmentMenuOpen}
              onClick={() => setAttachmentMenuOpen((open) => !open)}
            >
              <Icon name="plus" />
            </button>

            {attachmentMenuOpen && (
              <div className="pv-attachment-menu" role="menu">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setAttachmentMenuOpen(false);
                    photoInputRef.current?.click();
                  }}
                >
                  <Icon name="image" />
                  <span>Add photo</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setAttachmentMenuOpen(false);
                    fileInputRef.current?.click();
                  }}
                >
                  <Icon name="file" />
                  <span>Add file</span>
                </button>
              </div>
            )}
          </div>

          {attachment ? (
            <span className="pv-active-tool">File attached</span>
          ) : mode !== "chat" ? (
            <span className="pv-active-tool">
              {mode === "image"
                ? "Create image"
                : mode === "write"
                  ? "Write"
                  : mode === "web"
                    ? "Search web"
                    : "Analyze"}
            </span>
          ) : null}
        </div>


        <div className="pv-composer-actions">
          <button
            type="button"
            className={[
              "pv-mic-button",
              isListening ? "pv-mic-button--active" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            disabled={busy}
            aria-label={
              isListening ? "Stop voice input" : "Start voice input"
            }
            aria-pressed={isListening}
            title={
              isListening ? "Stop listening" : "Use microphone"
            }
            onClick={toggleVoiceInput}
          >
            <Icon name="microphone" />
          </button>

          <button
            type={busy ? "button" : "submit"}
            className="pv-send-button"
            disabled={!busy && !input.trim() && !attachment}
            aria-label={busy ? "Stop generation" : "Send message"}
            onClick={busy ? onStop : undefined}
          >
            {busy ? <Icon name="stop" /> : <Icon name="arrowUp" />}
          </button>
        </div>
      </div>
      </form>
    </div>
  );
}

function InlineArtifactDownloads({
  artifacts,
}: {
  artifacts?: SmartFileArtifact[];
}) {
  if (!artifacts || artifacts.length === 0) return null;

  return (
    <div
      className="pv-smart-downloads pv-inline-artifact-downloads"
      aria-label="Download generated files"
    >
      {artifacts.map((artifact) => {
        const lowerName = artifact.name.toLowerCase();
        const label = lowerName.endsWith(".pdf")
          ? "PDF"
          : lowerName.endsWith(".docx")
            ? "DOCX"
            : lowerName.endsWith(".png")
              ? "PNG"
              : "TXT";

        return (
          <a
            className="pv-smart-download"
            href={artifact.data_url}
            download={artifact.name}
            key={`${artifact.name}-${artifact.size_bytes}`}
            aria-label={`Download ${artifact.name}`}
          >
            <span className="pv-smart-download-icon" aria-hidden="true">
              ↓
            </span>
            <span className="pv-smart-download-copy">
              <strong>{artifact.name}</strong>
              <small>
                {label} · {fileSizeLabel(artifact.size_bytes)}
              </small>
            </span>
            <span className="pv-smart-download-action">Download</span>
          </a>
        );
      })}
    </div>
  );
}

function SourceStrip({ sources }: { sources?: SourceInfo[] }) {
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
    | "microphone"
    | "copy"
    | "thumbUp"
    | "thumbDown"
    | "trash"
    | "file"
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
    microphone: (
      <>
        <rect x="9" y="3" width="6" height="12" rx="3" />
        <path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" />
      </>
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
    trash: (
      <>
        <path d="M4 7h16" />
        <path d="M9 7V4h6v3" />
        <path d="m7 7 1 13h8l1-13" />
        <path d="M10 11v5M14 11v5" />
      </>
    ),
    file: (
      <>
        <path d="M6 3h8l4 4v14H6z" />
        <path d="M14 3v5h5" />
        <path d="M9 13h6M9 17h6" />
      </>
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
