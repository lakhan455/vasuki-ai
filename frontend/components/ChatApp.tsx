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
  cancelCodeBuildJobV17,
  createConversationBranch,
  startCodeBuildJobV17,
  startCodeModifyJobV17,
  waitForCodeBuildJobV17,
  type CodeBuildJobStatus,
  extractProjectMemories,
  fetchProjects,
  generateImage,
  searchChatHistory,
  streamChat,
  submitResponseFeedback,
  warmBackend,
  type ChatMessage,
  type ChatSearchResult,
  type SmartFileArtifact,
  type VasukiProject,
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
  "application/zip",
  "application/x-zip-compressed",
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
  ".zip",
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
  project_id?: string | null;
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

type ActionMode = "chat" | "image" | "write" | "web" | "analyze" | "research";
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
  icon: "image" | "write" | "web" | "analyze" | "research";
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
    mode: "research",
    label: "Deep research",
    prompt: "",
    icon: "research",
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
    /à¤ªà¥€à¤¡à¥€à¤à¤«|à¤•à¥à¤¯à¥‚à¤†à¤°|à¤à¤•\s*à¤¶à¥€à¤Ÿ/.test(normalized);

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

function isIdentityCriticalImageRequest(value: string) {
  const normalized = value.toLowerCase();
  const exactLanguage =
    /\b(?:exact|canonical|accurate|same character|specific model|identity|do not change|don't change)\b/i.test(
      normalized,
    );
  const namedVehicleOrProduct =
    /\b(?:bmw|mercedes(?:-benz)?|audi|porsche|tesla|ferrari|lamborghini|bugatti|toyota|honda|ford|volkswagen|tata|mahindra|iphone|ipad|macbook|galaxy|pixel|playstation|xbox)\s+[a-z0-9][a-z0-9.+-]*/i.test(
      normalized,
    );
  const knownCharacter =
    /\b(?:minato|naruto|sasuke|itachi|kakashi|goku|vegeta|gojo|luffy|zoro|doraemon|akatsuki|hokage|shinobi)\b/i.test(
      normalized,
    );
  const properNamedSubject =
    /\b[A-Z][A-Za-z'-]{2,}\s+[A-Z][A-Za-z'-]{2,}\b/.test(value);

  return (
    exactLanguage ||
    namedVehicleOrProduct ||
    knownCharacter ||
    properNamedSubject
  );
}

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


/* VASUKI_INLINE_CODE_WORKSPACE_START */
type CodeWorkspaceTab = "code" | "preview";

type InlineCodeSnapshot = {
  code: string;
  language: string;
  previewDoc: string;
};

function isLikelyCodeRequest(value: string) {
  const text = value.toLowerCase();
  const explicitCode =
    /\b(code|coding|html|css|javascript|typescript|jsx|tsx|react|next\.?js|python|java|c\+\+|c#|php|sql|program|script)\b/i.test(
      text,
    );
  const webBuild =
    /\b(website|webpage|web page|landing page|frontend|component)\b/i.test(
      text,
    );
  const action =
    /\b(write|create|build|make|generate|fix|debug|refactor|implement|develop|likh|likho|bana|banao|banado|karo)\b/i.test(
      text,
    ) || /kar\s+do/i.test(text);

  return /\bcode\b/i.test(text) || ((explicitCode || webBuild) && action);
}

/* VASUKI_V43_INSTANT_INTENT_START */
function instantIntentStatus(
  value: string,
  currentMode: ActionMode,
  attachmentKind?: PendingAttachment["kind"],
) {
  const text = value.toLowerCase();

  if (attachmentKind === "image") return "Intent: Image analysis · starting…";
  if (attachmentKind === "document") return "Intent: Document analysis · starting…";

  if (currentMode === "image") return "Intent: Image creation · starting…";
  if (currentMode === "research") return "Intent: Deep research · starting…";
  if (currentMode === "web") return "Intent: Live web search · starting…";
  if (currentMode === "write") return "Intent: Writing · starting…";
  if (currentMode === "analyze") return "Intent: Analysis · starting…";

  if (
    /\b(weather|mausam|temperature|forecast|rain|barish|aqi|air quality|sunrise|sunset|moonrise|moonset|timezone|humidity|wind)\b/i.test(
      text,
    )
  ) {
    return "Intent: Live weather · starting…";
  }

  if (
    /\b(create|generate|make|draw|design|render)\b.{0,30}\b(image|photo|poster|picture|logo|visual|wallpaper)\b/i.test(
      text,
    )
  ) {
    return "Intent: Image creation · starting…";
  }

  if (isLikelyCodeRequest(value) || isLikelyProjectBuildRequest(value)) {
    return "Intent: Coding · starting…";
  }

  if (
    /\b(research|latest|current|today|news|verify|source|citation|compare)\b/i.test(
      text,
    )
  ) {
    return "Intent: Research · starting…";
  }

  if (/\b(calculate|solve|equation|proof|logic|reason|math|ganit)\b/i.test(text)) {
    return "Intent: Reasoning · starting…";
  }

  return "Intent: Chat · starting…";
}
/* VASUKI_V43_INSTANT_INTENT_END */

/* VASUKI_V15_PROJECT_INTENT_START */
function isLikelyProjectBuildRequest(value: string) {
  const text = value.toLowerCase();
  const buildAction =
    /\b(create|build|make|generate|develop|bana|banao|banado|create\s+karo|bana\s+do)\b/i.test(
      text,
    );
  const projectNoun =
    /\b(website|web\s*app|mobile\s*app|android\s*app|ios\s*app|desktop\s*app|software|project|dashboard|admin\s*panel|saas|ecommerce|e-commerce|marketplace|api|backend|frontend|full\s*stack|ai\s*(?:app|tool|assistant|agent)|jarvis|chatbot|automation)\b/i.test(
      text,
    );
  const completeness =
    /\b(complete|fully|full|production|end[-\s]?to[-\s]?end|all\s*files|zip|download|file\s*de|files\s*de|ready\s*project|working\s*app)\b/i.test(
      text,
    );

  return (buildAction && projectNoun) ||
    (projectNoun && completeness);
}
/* VASUKI_V15_PROJECT_INTENT_END */

function normaliseInlineCodeLanguage(value: string) {
  const language = value.trim().toLowerCase().split(/\s+/)[0] || "code";
  if (["html", "htm"].includes(language)) return "html";
  if (language === "css") return "css";
  if (["js", "javascript", "jsx"].includes(language)) return "javascript";
  if (["ts", "typescript", "tsx"].includes(language)) return language;
  return language;
}

function buildInlinePreviewDoc(html: string, css: string, javascript: string) {
  const style = css ? `<style>\n${css}\n</style>` : "";
  const safeJavascript = javascript.replace(/<\/script/gi, "<\\/script");
  const script = javascript
    ? `<script>\n${safeJavascript}\n<\\/script>`
    : "";

  if (html && /<!doctype|<html[\s>]/i.test(html)) {
    let documentText = html;

    if (style) {
      documentText = /<\/head>/i.test(documentText)
        ? documentText.replace(/<\/head>/i, `${style}\n</head>`)
        : `${style}\n${documentText}`;
    }

    if (script) {
      documentText = /<\/body>/i.test(documentText)
        ? documentText.replace(/<\/body>/i, `${script}\n</body>`)
        : `${documentText}\n${script}`;
    }

    return documentText;
  }

  return `<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
${style}
</head>
<body>
${html || '<div id="app"></div>'}
${script}
</body>
</html>`;
}

function extractInlineCode(markdown: string): InlineCodeSnapshot | null {
  const blocks: Array<{ language: string; code: string }> = [];
  const fencePattern = /```([^\n`]*)\n([\s\S]*?)(?:```|$)/g;

  let match: RegExpExecArray | null;
  while ((match = fencePattern.exec(markdown)) !== null) {
    const code = (match[2] || "").replace(/\s+$/, "");
    if (!code.trim()) continue;
    blocks.push({
      language: normaliseInlineCodeLanguage(match[1] || ""),
      code,
    });
  }

  if (blocks.length === 0) return null;

  const html = blocks.find((block) => block.language === "html")?.code || "";
  const css = blocks.find((block) => block.language === "css")?.code || "";
  const javascript =
    blocks.find((block) => block.language === "javascript")?.code || "";

  const primary = blocks[0];
  const displayCode =
    blocks.length === 1
      ? primary.code
      : blocks
          .map(
            (block) =>
              `/* ${block.language || "code"} */\n${block.code}`,
          )
          .join("\n\n");

  const previewDoc =
    html || css || javascript
      ? buildInlinePreviewDoc(html, css, javascript)
      : "";

  return {
    code: displayCode,
    language: primary.language || "code",
    previewDoc,
  };
}
/* VASUKI_INLINE_CODE_WORKSPACE_END */


/* VASUKI_HIDE_CODE_FROM_CHAT_START */
function chatTextWithoutCodeBlocks(value: string) {
  return value
    .replace(/```[^\n`]*\n[\s\S]*?(?:```|$)/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
/* VASUKI_HIDE_CODE_FROM_CHAT_END */

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
  const [instantIntent, setInstantIntent] = useState("");
  const [, setQuotaStatus] = useState<QuotaUiStatus | null>(null);
  const [accountPlan, setAccountPlan] = useState<AccountPlan | null>(null);
  const [aiEngine, setAiEngine] = useState<AiEngine>("vasuki");
  const [, setPuterImageQuota] = useState<PuterImageQuota | null>(null);
  const [puterAccount, setPuterAccount] = useState("");
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [planBusy, setPlanBusy] = useState(false);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [feedbackById, setFeedbackById] = useState<Record<string, "up" | "down">>({});
  const [projects, setProjects] = useState<VasukiProject[]>([]);
  const [activeProjectId, setActiveProjectId] = useState("");
  const [historyQuery, setHistoryQuery] = useState("");
  const [historySearchOpen, setHistorySearchOpen] = useState(false);
  const [historySearchResults, setHistorySearchResults] = useState<ChatSearchResult[]>([]);
  const [historySearchBusy, setHistorySearchBusy] = useState(false);
  const [codeWorkspaceOpen, setCodeWorkspaceOpen] = useState(false);
  const [codeWorkspaceTab, setCodeWorkspaceTab] = useState<CodeWorkspaceTab>("code");
  const [codeWorkspaceSnapshot, setCodeWorkspaceSnapshot] = useState<InlineCodeSnapshot | null>(null);
  const [codeBuildStatus, setCodeBuildStatus] = useState<CodeBuildJobStatus | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const historySearchInputRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const streamAbortRef = useRef<AbortController | null>(null);
  const chatLoadTokenRef = useRef("");
  const codeIntentRef = useRef(false);
  const activeCodeJobRef = useRef<{
    jobId: string;
    accessToken: string;
  } | null>(null);

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
    if (!user) return;
    void (async () => {
      try {
        const accessToken = await currentAccessToken();
        setProjects((await fetchProjects(accessToken)).filter((project) => !project.archived));
      } catch (projectError) {
        console.error(projectError);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  useEffect(() => {
    if (!user || historyQuery.trim().length < 2) {
      setHistorySearchResults([]);
      setHistorySearchBusy(false);
      return;
    }
    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          setHistorySearchBusy(true);
          const accessToken = await currentAccessToken();
          setHistorySearchResults(await searchChatHistory(accessToken, historyQuery.trim()));
        } catch (searchError) {
          console.error(searchError);
          setHistorySearchResults([]);
        } finally {
          setHistorySearchBusy(false);
        }
      })();
    }, 350);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyQuery, user?.id]);

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

  function openHistorySearch() {
    setHistorySearchOpen(true);
    requestAnimationFrame(() => historySearchInputRef.current?.focus());
  }

  function closeHistorySearch() {
    setHistorySearchOpen(false);
    setHistoryQuery("");
    setHistorySearchResults([]);
    setHistorySearchBusy(false);
  }

  async function openSearchResult(result: ChatSearchResult) {
    if (!user) return;
    const local = chatRecords.find((chat) => chat.id === result.chat_id);
    if (local) {
      openChat(local);
      closeHistorySearch();
      return;
    }
    const { data, error: searchOpenError } = await supabase
      .from("user_chats")
      .select("id,title,messages,updated_at,project_id")
      .eq("id", result.chat_id)
      .eq("user_id", user.id)
      .single();
    if (searchOpenError || !data) {
      setError(searchOpenError?.message || "Chat could not be opened.");
      return;
    }
    openChat(data as ChatRecord);
    closeHistorySearch();
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
      .select("id,title,messages,updated_at,project_id")
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
    setActiveProjectId(record.project_id || "");
    setMessages(restoreMessages(record.messages));
    setAttachment(null);
    setInput("");
    setError("");
    setInstantIntent("");
    setMode("chat");
    setWebEnabled(false);
    setEditingMessageId(null);
    setCodeWorkspaceOpen(false);
    setCodeWorkspaceTab("code");
    setCodeWorkspaceSnapshot(null);
    setCodeBuildStatus(null);
    activeCodeJobRef.current = null;
    codeIntentRef.current = false;
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
      project_id: activeProjectId || null,
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
    setEditingMessageId(null);
    setCodeWorkspaceOpen(false);
    setCodeWorkspaceTab("code");
    setCodeWorkspaceSnapshot(null);
    setCodeBuildStatus(null);
    activeCodeJobRef.current = null;
    codeIntentRef.current = false;
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

  async function chooseAttachment(file: File) {
    setError("");

    const extension = attachmentExtension(file.name);
    if (
      !ALLOWED_ATTACHMENT_TYPES.has(file.type) &&
      !ALLOWED_ATTACHMENT_EXTENSIONS.has(extension)
    ) {
      setError(
        "Only JPG, PNG, WEBP, GIF, PDF, DOCX, TXT, MD and ZIP project files are supported.",
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
    setWebEnabled(action.mode === "web" || action.mode === "research");
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

    const editingIndex = editingMessageId
      ? messages.findIndex((message) => message.id === editingMessageId)
      : -1;
    const originalEditedMessage =
      editingIndex >= 0 && messages[editingIndex]?.role === "user"
        ? messages[editingIndex]
        : null;

    const effectiveText =
      text ||
      (selectedAttachment?.kind === "document"
        ? "Analyze this document in detail. If it is a question paper, answer every question in the correct order."
        : "Analyze this image in detail and explain all important information.");

    const instantStatus = instantIntentStatus(
      effectiveText,
      mode,
      selectedAttachment?.kind,
    );
    setInstantIntent(instantStatus);

    const codingRequest = isLikelyCodeRequest(effectiveText);
    const projectBuildRequest = isLikelyProjectBuildRequest(effectiveText);
    const zipProjectAttachment = Boolean(
      selectedAttachment && /\.zip$/i.test(selectedAttachment.file.name),
    );
    codeIntentRef.current = codingRequest;
    if (codingRequest) {
      setCodeWorkspaceOpen(true);
      setCodeWorkspaceTab("code");
      setCodeWorkspaceSnapshot(null);
      setCodeBuildStatus(null);
    }

    const userMessage: UiMessage = {
      id: makeId(),
      role: "user",
      content: effectiveText,
      imageUrl: selectedAttachment?.previewUrl,
      fileName: selectedAttachment?.file.name,
    };

    const baseMessages =
      originalEditedMessage && editingIndex >= 0
        ? messages.slice(0, editingIndex)
        : messages;
    const nextMessages = [...baseMessages, userMessage];

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

      if (originalEditedMessage) {
        void createConversationBranch(accessToken, {
          conversation_id: currentChatId || `unsaved-${user.id}`,
          source_message_id: originalEditedMessage.id,
          original_prompt: originalEditedMessage.content,
          edited_prompt: effectiveText,
          note: "Edit & Resend branch",
        }).catch((branchError) => console.error("Branch metadata save failed", branchError));
      }

      let finalMessages: UiMessage[] = nextMessages;

const requestedDownload =
        wantsDownloadableArtifact(effectiveText);
      const shouldUseCodeProject =
        codingRequest &&
        (
          projectBuildRequest ||
          zipProjectAttachment ||
          requestedDownload
        );
      const shouldUseSmartFiles =
        !shouldUseCodeProject &&
        (
          requestedDownload ||
          selectedAttachment?.kind === "document"
        );

/* VASUKI_V17_PROJECT_JOB_FLOW */
if (shouldUseCodeProject) {
  const controller = new AbortController();
  streamAbortRef.current = controller;

  const started =
    zipProjectAttachment && selectedAttachment
      ? await startCodeModifyJobV17(
          selectedAttachment.file,
          effectiveText,
          accessToken,
        )
      : await startCodeBuildJobV17(
          effectiveText,
          accessToken,
        );

  activeCodeJobRef.current = {
    jobId: started.job_id,
    accessToken,
  };
  setCodeBuildStatus(started);

  const data = await waitForCodeBuildJobV17(
    started.job_id,
    accessToken,
    (status) => {
      setCodeBuildStatus(status);
      setInstantIntent("");
      setStreamingStarted(true);
    },
    controller.signal,
  );

  const primaryCode =
    data.primary_code?.trim() || "";
  if (primaryCode) {
    setCodeWorkspaceSnapshot({
      code: primaryCode,
      language:
        data.primary_language || "code",
      previewDoc:
        data.preview_doc || "",
    });
    setCodeWorkspaceOpen(true);
    setCodeWorkspaceTab(
      data.preview_doc ? "preview" : "code",
    );
  }

  finalMessages = [
    ...nextMessages,
    {
      id: makeId(),
      role: "assistant",
      content:
        data.answer.trim() ||
        `Your ${
          data.project_name || "project"
        } is ready.`,
      provider: data.provider,
      artifacts: data.files,
    },
  ];
} else if (shouldUseSmartFiles) {

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
        const identityCriticalImage =
          isIdentityCriticalImageRequest(effectiveText);
        const autoProForIdentity =
          identityCriticalImage &&
          aiEngine === "vasuki" &&
          Boolean(accountPlan?.puter_access) &&
          Boolean(puterAccount);

        if (aiEngine === "puter" || autoProForIdentity) {
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
            imageProvider = autoProForIdentity
              ? `Vasuki auto-exact · ${result.provider}`
              : result.provider;
          } catch (puterImageError) {
            if (identityCriticalImage) {
              try {
                const restored =
                  await releasePuterImageQuota(accessToken);
                setPuterImageQuota(restored);
              } catch {
                // Persistent quota resets automatically.
              }

              const identityError =
                puterImageError instanceof Error
                  ? puterImageError.message
                  : "Strong image provider unavailable.";

              throw new Error(
                `${identityError} Exact-identity mode did not use the ` +
                  "native approximate fallback, so the requested model or " +
                  "character is not silently replaced.",
              );
            }

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
          const quota =
            await consumePuterImageQuota(
              accessToken,
            );

          setPuterImageQuota(quota);

          if (!quota.allowed) {
            throw new Error(
              `Daily image limit reached (${quota.daily_limit}/day).`,
            );
          }

          imageQuotaText =
            ` · Today ${quota.daily_remaining}/${quota.daily_limit} left`;

          try {
            const data = (await generateImage(
              effectiveText,
              accessToken,
            )) as ImageResponse;

            imageUrl =
              typeof data.url === "string"
                ? data.url.trim()
                : "";

            imageProvider =
              data.provider || "";
          } catch (nativeImageError) {
            try {
              const restored =
                await releasePuterImageQuota(
                  accessToken,
                );

              setPuterImageQuota(
                restored,
              );
            } catch {
              // Persistent quota resets automatically.
            }

            throw nativeImageError;
          }
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
          setInstantIntent("");
          streamedAnswer += token;
          const inlineCodeSnapshot = extractInlineCode(streamedAnswer);
          if (inlineCodeSnapshot) {
            codeIntentRef.current = true;
            setCodeWorkspaceSnapshot(inlineCodeSnapshot);
            setCodeWorkspaceOpen(true);
          }
          setStreamingStarted(true);
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId
                ? { ...message, content: streamedAnswer }
                : message,
            ),
          );
        };

        if (aiEngine === "puter" && mode !== "research") {
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
              useWeb: webEnabled || mode === "web" || mode === "research",
              useMemory: memoryEnabled,
              useDocuments: documentsEnabled,
              documentIds: selectedDocumentIds,
              projectId: activeProjectId || undefined,
              researchMode: mode === "research",
              cacheBypass: mode === "research",
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
                  : 0,
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
      setEditingMessageId(null);
      await persistChat(
        finalMessages,
        originalEditedMessage && currentChatId ? null : currentChatId,
      );

      if (activeProjectId) {
        const memoryMessages: ChatMessage[] = finalMessages
          .filter((message) => message.content.trim())
          .slice(-16)
          .map(({ role, content }) => ({ role, content: content.trim() }));
        void extractProjectMemories(accessToken, activeProjectId, memoryMessages)
          .catch((memoryError) => console.error("Automatic project memory capture failed", memoryError));
      }
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
      activeCodeJobRef.current = null;
      setInstantIntent("");
      setStreamingStarted(false);
      setBusy(false);
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  }


  function beginEditMessage(message: UiMessage) {
    if (busy || message.role !== "user") return;
    setEditingMessageId(message.id);
    setAttachment(null);
    setMode("chat");
    setWebEnabled(false);
    setInput(message.content);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  function cancelEditMessage() {
    setEditingMessageId(null);
    setInput("");
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function sendFeedback(message: UiMessage, rating: "up" | "down") {
    if (message.role !== "assistant") return;
    try {
      const accessToken = await currentAccessToken();
      await submitResponseFeedback(accessToken, {
        rating,
        category: rating === "up" ? "helpful" : "incorrect",
        message_id: message.id,
        metadata: { provider: message.provider || "", chat_id: currentChatId || "" },
      });
      setFeedbackById((current) => ({ ...current, [message.id]: rating }));
    } catch (feedbackError) {
      setError(feedbackError instanceof Error ? feedbackError.message : "Feedback could not be saved.");
    }
  }

  async function regenerateAssistant(messageId: string) {
    if (busy || !user) return;
    const assistantIndex = messages.findIndex(
      (message) => message.id === messageId && message.role === "assistant",
    );
    if (assistantIndex < 0) return;

    const priorProviderRaw = String(messages[assistantIndex]?.provider || "")
      .replace(/^cache:/i, "")
      .trim();
    const priorProvider = [
      "groq", "groq_fast", "sambanova", "cerebras", "gemini", "openrouter", "mistral",
    ].includes(priorProviderRaw) ? priorProviderRaw : undefined;

    const priorMessages = messages.slice(0, assistantIndex);
    const lastUser = [...priorMessages].reverse().find(
      (message) => message.role === "user" && message.content.trim(),
    );
    if (!lastUser) return;

    setBusy(true);
    setStreamingStarted(false);
    setError("");

    const assistantId = makeId();
    let streamedAnswer = "";

    try {
      const accessToken = await currentAccessToken();
      const nonce = makeId();

      if (currentChatId) {
        void createConversationBranch(accessToken, {
          conversation_id: currentChatId,
          source_message_id: lastUser.id,
          original_prompt: lastUser.content,
          edited_prompt: lastUser.content,
          note: "Regenerate answer branch",
        }).catch((branchError) => console.error("Regenerate branch save failed", branchError));
      }

      const requestMessages: ChatMessage[] = priorMessages
        .filter((message) => message.content.trim())
        .slice(-98)
        .map(({ role, content }) => ({ role, content: content.trim() }));

      requestMessages.push({
        role: "user",
        content:
          "Answer the immediately preceding user request again from scratch. " +
          "Use a fresh approach, do not mention this regeneration instruction, " +
          `and ignore cached wording. Internal fresh request ${nonce}.`,
      });

      setMessages([...priorMessages, { id: assistantId, role: "assistant", content: "" }]);
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
          projectId: activeProjectId || undefined,
          cacheBypass: true,
          excludeProvider: priorProvider,
          signal: controller.signal,
        },
        (token) => {
          streamedAnswer += token;
          const inlineCodeSnapshot = extractInlineCode(streamedAnswer);
          if (inlineCodeSnapshot) {
            codeIntentRef.current = true;
            setCodeWorkspaceSnapshot(inlineCodeSnapshot);
            setCodeWorkspaceOpen(true);
          }
          setStreamingStarted(true);
          setMessages((current) =>
            current.map((message) =>
              message.id === assistantId ? { ...message, content: streamedAnswer } : message,
            ),
          );
        },
      );

      const answer = streamedAnswer.trim();
      if (!answer) throw new Error("The AI returned an empty regenerated response.");

      const finalMessages: UiMessage[] = [
        ...priorMessages,
        {
          id: assistantId,
          role: "assistant",
          content: answer,
          provider: meta.provider || "",
          sources: normaliseSources(meta.sources),
        },
      ];
      setMessages(finalMessages);
      await persistChat(finalMessages, currentChatId ? null : currentChatId);
    } catch (regenerateError) {
      setMessages(messages);
      setError(regenerateError instanceof Error ? regenerateError.message : "Regeneration failed. Please retry.");
    } finally {
      streamAbortRef.current = null;
      setStreamingStarted(false);
      setBusy(false);
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  }

  function stopStreaming() {
    streamAbortRef.current?.abort();
    const activeJob = activeCodeJobRef.current;
    if (activeJob) {
      void cancelCodeBuildJobV17(
        activeJob.jobId,
        activeJob.accessToken,
      ).catch((cancelError) =>
        console.error("Build cancellation failed", cancelError),
      );
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
  const activeProject = projects.find(
    (project) => project.id === activeProjectId,
  );

  return (
    <main className={codeWorkspaceOpen ? "pv-app pv-app--code-open" : "pv-app"}>
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

          <div className="pv-sidebar-top-actions">
            <button
              type="button"
              className={[
                "pv-icon-button",
                "pv-sidebar-search-trigger",
                historySearchOpen ? "is-active" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              aria-label={historySearchOpen ? "Close chat search" : "Search chats"}
              title="Search chats"
              aria-expanded={historySearchOpen}
              onClick={() =>
                historySearchOpen ? closeHistorySearch() : openHistorySearch()
              }
            >
              <Icon name="search" />
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
        </div>

        {historySearchOpen && (
          <div className="pv-history-search pv-history-search--header">
            <span className="pv-history-search-icon" aria-hidden="true">
              <Icon name="search" />
            </span>
            <input
              ref={historySearchInputRef}
              value={historyQuery}
              onChange={(event) => setHistoryQuery(event.target.value)}
              placeholder="Search chats"
              aria-label="Search chat history"
            />
            <button
              type="button"
              className="pv-history-search-close"
              aria-label="Close chat search"
              title="Close search"
              onClick={closeHistorySearch}
            >
              <Icon name="close" />
            </button>
          </div>
        )}

        <nav className="pv-sidebar-nav">
          <button
            type="button"
            className="pv-nav-button"
            onClick={startNewChat}
          >
            <Icon name="plus" />
            <span>New chat</span>
          </button>
          <a className="pv-nav-button" href="/projects"><Icon name="project" /><span>Projects</span></a>
          <a className="pv-nav-button" href="/files"><Icon name="file" /><span>My Files</span></a>
          <a className="pv-nav-button" href="/images"><Icon name="image" /><span>Image History</span></a>
          {accountPlan?.plan === "owner" && (
            <a className="pv-nav-button" href="/owner"><Icon name="analytics" /><span>Owner Analytics</span></a>
          )}

        </nav>

        <div className="pv-recent">
          <p className="pv-section-label">
            {historyQuery.trim().length >= 2 ? "Search results" : "Recent"}{" "}
            {(historyBusy || historySearchBusy) ? "· loading…" : ""}
          </p>

          {historyQuery.trim().length >= 2 ? (
            historySearchResults.length === 0 && !historySearchBusy ? (
              <p className="pv-empty-history">No matching chats.</p>
            ) : (
              historySearchResults.map((result) => (
                <div className="pv-recent-row" key={result.chat_id}>
                  <button
                    type="button"
                    className="pv-recent-button"
                    onClick={() => void openSearchResult(result)}
                    title={result.snippet || result.title}
                  >
                    <span>{result.title}</span>
                    {result.snippet ? <small className="pv-search-snippet">{result.snippet}</small> : null}
                  </button>
                </div>
              ))
            )
          ) : chatRecords.length === 0 && !historyBusy ? (
            <p className="pv-empty-history">No saved chats yet.</p>
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
                      V40 Creator · Advanced Code · Advanced Images · Web · Memory
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
                      Smart answers · Complete coding · 50 images/day
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

            {activeProject ? (
              <div
                className="pv-project-context pv-desktop-only"
                title="Project memory is active"
              >
                <span>PROJECT</span>
                <strong>{activeProject.name}</strong>
              </div>
            ) : null}
          </div>

        </header>

        {!hasMessages ? (
          <section className="pv-welcome">
            <div className="pv-welcome-inner">
              <Logo className="pv-welcome-logo" />
              <div className="pv-welcome-heading">
                <p>Vasuki Core · V40 Advanced Creator Runtime · online</p>
                <h1>Turn intent into working systems.</h1>
                <div className="pv-welcome-subline">
                  Build software, investigate the web, create media and move
                  projects forward with reflection, goal awareness and calibrated intuition.
                </div>
              </div>

              <div className="pv-command-rail" aria-label="Quick starts">
                <button
                  type="button"
                  onClick={() =>
                    setInput("Build a complete production-ready web app for ")
                  }
                >
                  <strong>Build software</strong>
                  <small>Architecture · code · ZIP · runbook</small>
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setInput("Fix and improve this project: ")
                  }
                >
                  <strong>Repair a project</strong>
                  <small>Upload ZIP · inspect · patch · validate</small>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMode("research");
                    setWebEnabled(true);
                    setInput("Research and verify ");
                  }}
                >
                  <strong>Investigate</strong>
                  <small>Live web · evidence · synthesis</small>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMode("image");
                    setInput("Create a premium visual of ");
                  }}
                >
                  <strong>Create visual</strong>
                  <small>Image studio · identity-aware</small>
                </button>
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
                onSelectAction={selectAction}
                onCancelAction={cancelAction}
                welcome
              />

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
                    className={[
                      "pv-message",
                      `pv-message--${message.role}`,
                      message.role === "assistant" &&
                      !message.content.trim() &&
                      busy &&
                      !streamingStarted
                        ? "pv-message--pending-placeholder"
                        : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    {message.role === "assistant" && (
                      <Logo className="pv-assistant-logo" />
                    )}

                    <div className="pv-message-body">
                      {message.role === "assistant" ? (
                        <>
                          {chatTextWithoutCodeBlocks(message.content) ? (
                            <div className="pv-markdown">
                              <ReactMarkdown>
                                {chatTextWithoutCodeBlocks(message.content)}
                              </ReactMarkdown>
                            </div>
                          ) : null}

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
                                  chatTextWithoutCodeBlocks(message.content),
                                )
                              }
                            >
                              <Icon name="copy" />
                            </button>
                            <button
                              type="button"
                              aria-label="Good response"
                              aria-pressed={feedbackById[message.id] === "up"}
                              onClick={() => void sendFeedback(message, "up")}
                            >
                              <Icon name="thumbUp" />
                            </button>
                            <button
                              type="button"
                              aria-label="Bad response"
                              aria-pressed={feedbackById[message.id] === "down"}
                              onClick={() => void sendFeedback(message, "down")}
                            >
                              <Icon name="thumbDown" />
                            </button>
                            {message.id === messages[messages.length - 1]?.id &&
                              !message.imageUrl &&
                              !message.artifacts?.length && (
                                <button
                                  type="button"
                                  aria-label="Regenerate answer"
                                  title="Regenerate answer in a new branch"
                                  disabled={busy}
                                  onClick={() => void regenerateAssistant(message.id)}
                                >
                                  <Icon name="regenerate" />
                                </button>
                              )}
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
                          <div className="pv-message-actions pv-user-message-actions">
                            <button
                              type="button"
                              aria-label="Edit and resend"
                              title="Edit & Resend in a new branch"
                              disabled={busy}
                              onClick={() => beginEditMessage(message)}
                            >
                              <Icon name="edit" />
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </article>
                ))}

                {busy && !streamingStarted && (
                  <article
                    className="pv-message pv-message--assistant"
                    aria-live="polite"
                  >
                    <Logo className="pv-assistant-logo" />
                    <div className="pv-message-body">
                      {instantIntent ? (
                        <div className="pv-markdown">
                          <p>{instantIntent}</p>
                        </div>
                      ) : null}
                      <div className="pv-typing" aria-label="Starting response">
                        <span />
                        <span />
                        <span />
                      </div>
                    </div>
                  </article>
                )}

                {error && <div className="pv-error">{error}</div>}
                <div ref={endRef} />
              </div>
            </section>

            <div className="pv-composer-dock">
              <div className="pv-composer-dock-inner">
                {editingMessageId && (
                  <div className="pv-editing-banner">
                    <span>Editing an earlier prompt · resend creates a new branch</span>
                    <button type="button" onClick={cancelEditMessage}>Cancel</button>
                  </div>
                )}
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
                  onSelectAction={selectAction}
                  onCancelAction={cancelAction}
                />
                <p className="pv-disclaimer">
                  Vasuki AI can make mistakes. Verify important information.
                </p>
              </div>
            </div>
          </>
        )}
      </section>

      <InlineCodeWorkspace
        open={codeWorkspaceOpen}
        tab={codeWorkspaceTab}
        snapshot={codeWorkspaceSnapshot}
        busy={busy && codeIntentRef.current}
        buildStatus={codeBuildStatus}
        onTabChange={setCodeWorkspaceTab}
        onClose={() => setCodeWorkspaceOpen(false)}
      />

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


/* VASUKI_V17_CODE_WORKSPACE_COMPONENT */
function InlineCodeWorkspace({
  open,
  tab,
  snapshot,
  busy,
  buildStatus,
  onTabChange,
  onClose,
}: {
  open: boolean;
  tab: CodeWorkspaceTab;
  snapshot: InlineCodeSnapshot | null;
  busy: boolean;
  buildStatus: CodeBuildJobStatus | null;
  onTabChange: (tab: CodeWorkspaceTab) => void;
  onClose: () => void;
}) {
  const codeRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (tab !== "code") return;
    const node = codeRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [snapshot?.code, tab]);

  if (!open) return null;

  const stageLabel = (() => {
    const stage = buildStatus?.stage || "";
    if (stage === "planning") return "Architecting";
    if (stage === "building") return "Forging files";
    if (stage === "validating") return "Validating";
    if (stage === "repairing") return "Self-repair";
    if (stage === "sandbox") return "Safe check";
    if (stage === "packaging") return "Packaging";
    if (stage === "ready") return "Ready";
    if (stage === "cancelled") return "Stopped";
    return busy ? "Starting" : "Ready";
  })();

  return (
    <aside className="pv-inline-code-workspace" aria-label="Vasuki build forge">
      <header className="pv-inline-code-head">
        <div className="pv-inline-code-title">
          <span className={busy ? "is-live" : ""} aria-hidden="true" />
          <div>
            <strong>Vasuki Forge</strong>
            <small>
              {busy
                ? stageLabel
                : snapshot?.language
                  ? snapshot.language.toUpperCase()
                  : "Build surface"}
            </small>
          </div>
        </div>

        <button
          type="button"
          className="pv-inline-code-close"
          aria-label="Close build forge"
          title="Close build forge"
          onClick={onClose}
        >
          ×
        </button>
      </header>

      {buildStatus && buildStatus.status !== "succeeded" ? (
        <div className="pv-build-monitor" aria-live="polite">
          <div className="pv-build-monitor-top">
            <strong>{stageLabel}</strong>
            <span>{Math.max(0, Math.min(100, buildStatus.progress || 0))}%</span>
          </div>
          <div className="pv-build-track" aria-hidden="true">
            <span
              style={{
                width: `${Math.max(
                  2,
                  Math.min(100, buildStatus.progress || 0),
                )}%`,
              }}
            />
          </div>
          <p className="pv-build-message">
            {buildStatus.message || "Working on your project…"}
          </p>
        </div>
      ) : null}

      <div className="pv-inline-code-tabs" role="tablist" aria-label="Build output view">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "code"}
          className={tab === "code" ? "is-active" : ""}
          onClick={() => onTabChange("code")}
        >
          Code
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "preview"}
          className={tab === "preview" ? "is-active" : ""}
          onClick={() => onTabChange("preview")}
        >
          Preview
        </button>
      </div>

      <div className="pv-inline-code-body">
        {tab === "code" ? (
          <pre ref={codeRef} className="pv-inline-code-editor">
            <code>
              {snapshot?.code ||
                (busy
                  ? `// Vasuki Forge · ${stageLabel}\n// ${buildStatus?.message || "Preparing project…"}`
                  : "Your project source appears here when a build finishes.")}
            </code>
          </pre>
        ) : snapshot?.previewDoc ? (
          <iframe
            className="pv-inline-code-preview"
            title="Vasuki project preview"
            sandbox="allow-scripts"
            srcDoc={snapshot.previewDoc}
          />
        ) : (
          <div className="pv-inline-code-empty">
            <strong>Preview surface</strong>
            <p>
              Web builds open here automatically when a safe preview is available.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}

/* VASUKI_INLINE_CODE_WORKSPACE_COMPONENT_END */

function Logo({ className }: { className: string }) {
  const [source, setSource] = useState(VASUKI_LOGO_URL);
  const [failed, setFailed] = useState(false);

  if (failed) {
    return <span className={`${className} pv-logo-fallback`}>V</span>;
  }

  return (
    <img
      className={className}
      src={source}
      alt="Vasuki AI logo"
      referrerPolicy="no-referrer"
      onError={() => {
        if (source !== "/vasuki-pwa.svg") {
          setSource("/vasuki-pwa.svg");
          return;
        }
        setFailed(true);
      }}
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
  onSelectAction,
  onCancelAction,
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
  onSelectAction: (action: (typeof actionItems)[number]) => void;
  onCancelAction: (action: (typeof actionItems)[number]) => void;
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
        accept="application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/zip,application/x-zip-compressed,text/plain,text/markdown,.pdf,.docx,.txt,.md,.zip"
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
              : mode === "research"
                ? "What would you like me to research deeply?"
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
                <div className="pv-plus-menu-separator" role="separator" />

                {actionItems.map((action) => (
                  <button
                    type="button"
                    role="menuitem"
                    key={action.mode}
                    className={mode === action.mode ? "is-active" : ""}
                    onClick={() => {
                      setAttachmentMenuOpen(false);
                      if (mode === action.mode) {
                        onCancelAction(action);
                      } else {
                        onSelectAction(action);
                      }
                    }}
                  >
                    <Icon name={action.icon} />
                    <span>{action.label}</span>
                    {mode === action.mode ? (
                      <span className="pv-plus-menu-check" aria-hidden="true"><Icon name="check" /></span>
                    ) : null}
                  </button>
                ))}

                <div className="pv-plus-menu-separator" role="separator" />

                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setAttachmentMenuOpen(false);
                    window.location.assign("/branches");
                  }}
                >
                  <Icon name="branch" />
                  <span>Branch Explorer</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setAttachmentMenuOpen(false);
                    window.location.assign("/operations");
                  }}
                >
                  <Icon name="file" />
                  <span>Operations Center</span>
                </button>

                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setAttachmentMenuOpen(false);
                    window.location.assign("/account");
                  }}
                >
                  <Icon name="file" />
                  <span>Account & privacy</span>
                </button>

                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setAttachmentMenuOpen(false);
                    window.location.assign("/security");
                  }}
                >
                  <Icon name="file" />
                  <span>Security Center</span>
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
                    : mode === "research"
                      ? "Deep research"
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
              <Icon name="download" />
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
              <span aria-hidden="true"><Icon name="file" /></span>
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
                <span className="pv-source-open" aria-hidden="true"><Icon name="external" /></span>
              </a>
            ) : (
              <div
                className="pv-source-card pv-source-card--document"
                key={keyFor(source, index)}
              >
                <span className="pv-source-card-number">{index + 1}</span>
                <span className="pv-document-source-icon" aria-hidden="true">
                  <Icon name="file" />
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
    | "search"
    | "chevron"
    | "image"
    | "write"
    | "web"
    | "research"
    | "branch"
    | "analyze"
    | "arrowUp"
    | "stop"
    | "microphone"
    | "copy"
    | "thumbUp"
    | "thumbDown"
    | "trash"
    | "file"
    | "logout"
    | "project"
    | "code"
    | "analytics"
    | "regenerate"
    | "check"
    | "download"
    | "external"
    | "edit";
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
    search: (
      <>
        <circle cx="11" cy="11" r="6" />
        <path d="m16 16 4 4" />
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
    research: (
      <>
        <circle cx="10.5" cy="10.5" r="5.5" />
        <path d="m14.5 14.5 4 4" />
        <path d="M18 4v4M16 6h4" />
      </>
    ),
    branch: (
      <>
        <circle cx="6" cy="5" r="2" />
        <circle cx="18" cy="7" r="2" />
        <circle cx="18" cy="18" r="2" />
        <path d="M8 5h3a5 5 0 0 1 5 5v6M8 5v10a3 3 0 0 0 3 3h5" />
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
    project: (
      <>
        <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
        <path d="M3 10h18" />
      </>
    ),
    code: (
      <>
        <path d="m8 8-4 4 4 4" />
        <path d="m16 8 4 4-4 4" />
        <path d="m14 5-4 14" />
      </>
    ),
    analytics: (
      <>
        <path d="M4 20V10" />
        <path d="M10 20V4" />
        <path d="M16 20v-7" />
        <path d="M22 20H2" />
      </>
    ),
    regenerate: (
      <>
        <path d="M20 7v5h-5" />
        <path d="M18.5 16A8 8 0 1 1 20 12" />
      </>
    ),
    edit: (
      <>
        <path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3Z" />
        <path d="m14 8 3 3" />
      </>
    ),
    check: <path d="m5 12.5 4.2 4.2L19 7" />,
    download: (
      <>
        <path d="M12 4v11" />
        <path d="m7.5 11 4.5 4.5 4.5-4.5" />
        <path d="M5 20h14" />
      </>
    ),
    external: (
      <>
        <path d="M14 5h5v5" />
        <path d="m19 5-9 9" />
        <path d="M18 13v6H5V6h6" />
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
