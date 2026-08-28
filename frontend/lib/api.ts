// Vasuki AI authenticated API client with true SSE streaming.
const PROXY_API_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "/backend-api"
).replace(/\/$/, "");

const DIRECT_API_URL = (
  process.env.NEXT_PUBLIC_IMAGE_API_BASE_URL ||
  "https://vasuki-ai.onrender.com"
).replace(/\/$/, "");

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type StreamChatMeta = {
  provider?: string;
  provider_model?: string;
  first_token_ms?: number;
  duration_ms?: number;
  attempt_count?: number;
  adaptive_routing?: boolean;
  sources?: unknown[];
  request_id?: string;
  context_trimmed?: boolean;
  original_context_chars?: number;
  used_context_chars?: number;
  minute_limit?: number;
  minute_remaining?: number;
  daily_limit?: number;
  daily_remaining?: number;
};

export type MemoryItem = {
  id: string;
  memory_text: string;
  category?: string;
  created_at?: string;
  updated_at?: string;
};

export type KnowledgeDocument = {
  id: string;
  name: string;
  mime_type?: string;
  size_bytes?: number;
  status?: "processing" | "ready" | "failed";
  chunk_count?: number;
  created_at?: string;
  updated_at?: string;
};

const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);

function delay(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function authHeaders(accessToken?: string, json = false): HeadersInit {
  const headers: Record<string, string> = {};
  if (json) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  return headers;
}

async function readResponse(response: Response) {
  const raw = await response.text();
  let data: Record<string, unknown> = {};

  if (raw) {
    try {
      data = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      data = { detail: raw };
    }
  }

  if (!response.ok) {
    const rawDetail = data.detail;
    let detail = `Request failed (${response.status})`;

    if (typeof rawDetail === "string" && rawDetail.trim()) {
      detail = rawDetail.trim();
    } else if (Array.isArray(rawDetail)) {
      const messages = rawDetail
        .map((item) => {
          if (!item || typeof item !== "object") return "";
          const value = item as {
            msg?: unknown;
            loc?: unknown;
          };
          const message =
            typeof value.msg === "string" ? value.msg : "";
          const location = Array.isArray(value.loc)
            ? value.loc.map(String).join(".")
            : "";
          return [location, message].filter(Boolean).join(": ");
        })
        .filter(Boolean);

      if (messages.length > 0) {
        detail = messages.join(" | ");
      }
    }

    throw new Error(detail);
  }

  return data;
}

async function postJsonAt(
  baseUrl: string,
  path: string,
  body: unknown,
  timeoutMilliseconds: number,
  attempts: number,
  accessToken?: string,
) {
  let lastError: unknown = null;

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(
      () => controller.abort(),
      timeoutMilliseconds,
    );

    try {
      const response = await fetch(`${baseUrl}${path}`, {
        method: "POST",
        headers: authHeaders(accessToken, true),
        body: JSON.stringify(body),
        cache: "no-store",
        signal: controller.signal,
      });

      if (response.ok) {
        return await readResponse(response);
      }

      const status = response.status;
      try {
        await readResponse(response);
      } catch (error) {
        lastError = error;
      }

      if (!RETRYABLE_STATUS.has(status) || attempt >= attempts - 1) {
        throw lastError instanceof Error
          ? lastError
          : new Error(`Request failed (${status})`);
      }
    } catch (error) {
      lastError = error;
      const isAbort =
        error instanceof DOMException && error.name === "AbortError";

      if (attempt >= attempts - 1) {
        if (isAbort) {
          throw new Error("AI request timed out. Please retry once.");
        }
        throw error instanceof Error
          ? error
          : new Error("AI service connection failed.");
      }
    } finally {
      window.clearTimeout(timeoutId);
    }

    await delay([1200, 2400, 4000][Math.min(attempt, 2)]);
  }

  throw lastError instanceof Error
    ? lastError
    : new Error("AI request failed.");
}

async function postFormAt(
  baseUrl: string,
  path: string,
  makeForm: () => FormData,
  timeoutMilliseconds: number,
  attempts: number,
  accessToken?: string,
) {
  let lastError: unknown = null;

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(
      () => controller.abort(),
      timeoutMilliseconds,
    );

    try {
      const response = await fetch(`${baseUrl}${path}`, {
        method: "POST",
        headers: authHeaders(accessToken),
        body: makeForm(),
        cache: "no-store",
        signal: controller.signal,
      });

      if (response.ok) {
        return await readResponse(response);
      }

      const status = response.status;
      try {
        await readResponse(response);
      } catch (error) {
        lastError = error;
      }

      if (!RETRYABLE_STATUS.has(status) || attempt >= attempts - 1) {
        throw lastError instanceof Error
          ? lastError
          : new Error(`Upload failed (${status})`);
      }
    } catch (error) {
      lastError = error;
      const isAbort =
        error instanceof DOMException && error.name === "AbortError";

      if (attempt >= attempts - 1) {
        if (isAbort) {
          throw new Error(
            "Image/file processing timed out. Please retry with a smaller file.",
          );
        }
        throw error instanceof Error
          ? error
          : new Error("File service connection failed.");
      }
    } finally {
      window.clearTimeout(timeoutId);
    }

    await delay([1200, 2400, 4000][Math.min(attempt, 2)]);
  }

  throw lastError instanceof Error
    ? lastError
    : new Error("File request failed.");
}

async function getAt(
  baseUrl: string,
  path: string,
  accessToken: string,
) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: "GET",
    headers: authHeaders(accessToken),
    cache: "no-store",
  });
  return readResponse(response);
}

async function patchJsonAt(
  baseUrl: string,
  path: string,
  body: unknown,
  accessToken: string,
) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: "PATCH",
    headers: authHeaders(accessToken, true),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  return readResponse(response);
}

async function deleteAt(
  baseUrl: string,
  path: string,
  accessToken: string,
) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: "DELETE",
    headers: authHeaders(accessToken),
    cache: "no-store",
  });
  return readResponse(response);
}

export async function warmBackend() {
  const targets = [
    `${DIRECT_API_URL}/health`,
    `${PROXY_API_URL}/health`,
  ];

  await Promise.allSettled(
    targets.map((url) =>
      fetch(url, {
        method: "GET",
        cache: "no-store",
      }),
    ),
  );
}

type StreamOptions = {
  accessToken: string;
  useWeb: boolean;
  useMemory: boolean;
  useDocuments: boolean;
  documentIds: string[];
  projectId?: string;
  researchMode?: boolean;
  cacheBypass?: boolean;
  excludeProvider?: string;
  signal?: AbortSignal;
};

function parseEventBlock(block: string) {
  let event = "message";
  const dataLines: string[] = [];

  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  const raw = dataLines.join("\n");
  let data: Record<string, unknown> = {};
  if (raw) {
    try {
      data = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      data = { token: raw };
    }
  }

  return { event, data };
}

async function streamAt(
  baseUrl: string,
  messages: ChatMessage[],
  options: StreamOptions,
  onToken: (token: string) => void,
): Promise<StreamChatMeta> {
  const response = await fetch(`${baseUrl}/api/chat/stream`, {
    method: "POST",
    headers: authHeaders(options.accessToken, true),
    body: JSON.stringify({
      messages,
      provider: "auto",
      use_web: options.useWeb,
      use_memory: options.useMemory,
      use_documents: options.useDocuments,
      document_ids: options.documentIds,
      project_id: options.projectId || null,
      research_mode: Boolean(options.researchMode),
      cache_bypass: Boolean(options.cacheBypass),
      exclude_provider: options.excludeProvider || null,
    }),
    cache: "no-store",
    signal: options.signal,
  });

  if (!response.ok) {
    await readResponse(response);
  }

  if (!response.body) {
    throw new Error("Streaming response body is unavailable.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let meta: StreamChatMeta = {};

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    while (true) {
      const boundary = buffer.indexOf("\n\n");
      if (boundary < 0) break;

      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseEventBlock(block);

      if (parsed.event === "ready") {
        meta = {
          ...meta,
          ...(parsed.data as StreamChatMeta),
        };
      } else if (parsed.event === "token") {
        const token =
          typeof parsed.data.token === "string"
            ? parsed.data.token
            : "";
        if (token) onToken(token);
      } else if (parsed.event === "provider") {
        meta = {
          ...meta,
          ...(parsed.data as StreamChatMeta),
        };
        if (typeof parsed.data.provider_model === "string") {
          meta.provider_model = parsed.data.provider_model;
        }
        if (typeof parsed.data.first_token_ms === "number") {
          meta.first_token_ms = parsed.data.first_token_ms;
        }
      } else if (parsed.event === "meta") {
        meta = {
          ...meta,
          ...(parsed.data as StreamChatMeta),
        };
      } else if (parsed.event === "error") {
        const detail =
          typeof parsed.data.detail === "string"
            ? parsed.data.detail
            : "AI streaming failed.";
        throw new Error(detail);
      }
    }
  }

  return meta;
}

export async function streamChat(
  messages: ChatMessage[],
  options: StreamOptions,
  onToken: (token: string) => void,
): Promise<StreamChatMeta> {
  let emittedToken = false;

  const trackedToken = (token: string) => {
    if (token) {
      emittedToken = true;
    }
    onToken(token);
  };

  try {
    return await streamAt(
      DIRECT_API_URL,
      messages,
      options,
      trackedToken,
    );
  } catch (firstError) {
    if (
      options.signal?.aborted ||
      (
        firstError instanceof DOMException &&
        firstError.name === "AbortError"
      )
    ) {
      throw firstError;
    }

    const firstMessage =
      firstError instanceof Error
        ? firstError.message
        : "Streaming connection failed.";

    const retryable =
      /failed to fetch|network|connection|provider failed|provider.*unavailable|temporarily busy|temporarily failed|empty response|streaming failed/i.test(
        firstMessage,
      );

    if (!retryable || emittedToken) {
      throw firstError;
    }

    // The backend marks failed providers unhealthy before
    // this retry, so a fresh request prefers another provider.
    await delay(120);

    try {
      return await streamAt(
        PROXY_API_URL,
        messages,
        {
          ...options,
          cacheBypass: true,
        },
        trackedToken,
      );
    } catch (secondError) {
      if (
        options.signal?.aborted ||
        (
          secondError instanceof DOMException &&
          secondError.name === "AbortError"
        )
      ) {
        throw secondError;
      }

      const secondMessage =
        secondError instanceof Error
          ? secondError.message
          : "AI providers are temporarily unavailable.";

      const providerFailure =
        /provider failed|provider.*unavailable|temporarily busy|temporarily failed|all.*providers|empty response|streaming failed/i.test(
          secondMessage,
        );

      if (!emittedToken && providerFailure) {
        trackedToken(
          "Vasuki AI ne available AI providers automatically try kiye, " +
          "lekin is waqt upstream providers temporarily busy hain. " +
          "Aapka chat quota unlimited hai aur message safe hai. " +
          "Please send the message again in a few seconds.",
        );

        return {
          provider: "vasuki-resilience",
          daily_limit: 0,
          daily_remaining: -1,
        };
      }

      throw secondError;
    }
  }
}

export async function sendChat(
  messages: ChatMessage[],
  useWeb: boolean,
  accessToken: string,
  useMemory = true,
  useDocuments = false,
  documentIds: string[] = [],
) {
  return postJsonAt(
    DIRECT_API_URL,
    "/api/chat",
    {
      messages,
      provider: "auto",
      use_web: useWeb,
      use_memory: useMemory,
      use_documents: useDocuments,
      document_ids: documentIds,
    },
    65000,
    1,
    accessToken,
  );
}

export async function analyzeAttachment(
  file: File,
  prompt: string,
  accessToken: string,
) {
  const bases = Array.from(new Set([DIRECT_API_URL, PROXY_API_URL]));
  const errors: string[] = [];

  for (const baseUrl of bases) {
    try {
      return await postFormAt(
        baseUrl,
        "/api/vision",
        () => {
          const form = new FormData();
          form.append("file", file, file.name);
          form.append("prompt", prompt);
          form.append("operation", "auto");
          return form;
        },
        180000,
        2,
        accessToken,
      );
    } catch (error) {
      errors.push(
        error instanceof Error ? error.message : "Unknown vision service error",
      );
    }
  }

  throw new Error(
    errors.at(-1) ||
      "Image/file analysis failed after automatic retries.",
  );
}

/* VASUKI_SMART_FILES_API_START */
export type SmartFileArtifact = {
  name: string;
  mime_type: string;
  size_bytes: number;
  data_url: string;
};

export type SmartFileResponse = {
  answer: string;
  provider?: string;
  files: SmartFileArtifact[];
  processed_files: string[];
  warnings: string[];
};

export async function analyzeSmartFiles(
  files: File[],
  prompt: string,
  accessToken: string,
): Promise<SmartFileResponse> {
  const bases = Array.from(new Set([DIRECT_API_URL, PROXY_API_URL]));
  const errors: string[] = [];

  for (const baseUrl of bases) {
    try {
      const data = await postFormAt(
        baseUrl,
        "/api/smart-files/v2",
        () => {
          const form = new FormData();
          form.append("prompt", prompt);
          for (const file of files) {
            form.append("files", file, file.name);
          }
          return form;
        },
        240000,
        1,
        accessToken,
      );

      return {
        answer: typeof data.answer === "string" ? data.answer : "",
        provider: typeof data.provider === "string" ? data.provider : undefined,
        files: Array.isArray(data.files)
          ? (data.files as SmartFileArtifact[])
          : [],
        processed_files: Array.isArray(data.processed_files)
          ? data.processed_files.map(String)
          : [],
        warnings: Array.isArray(data.warnings)
          ? data.warnings.map(String)
          : [],
      };
    } catch (error) {
      errors.push(
        error instanceof Error
          ? error.message
          : "Unknown smart-file service error",
      );
    }
  }

  throw new Error(
    errors.at(-1) || "Smart file processing failed after automatic fallback.",
  );
}
/* VASUKI_SMART_FILES_API_END */

export async function generateImage(
  prompt: string,
  accessToken: string,
) {
  const body = {
    prompt,
    provider: "auto",
  };
  const bases = Array.from(new Set([DIRECT_API_URL, PROXY_API_URL]));
  const errors: string[] = [];

  for (const baseUrl of bases) {
    try {
      return await postJsonAt(
        baseUrl,
        "/api/image/v2",
        body,
        150000,
        3,
        accessToken,
      );
    } catch (error) {
      errors.push(
        error instanceof Error ? error.message : "Unknown image service error",
      );
    }
  }

  throw new Error(
    errors.at(-1) ||
      "Image generation failed after automatic retries.",
  );
}

export async function fetchMemory(accessToken: string) {
  const data = await getAt(DIRECT_API_URL, "/api/memory", accessToken);
  return {
    enabled: data.enabled !== false,
    memories: Array.isArray(data.memories)
      ? (data.memories as MemoryItem[])
      : [],
  };
}

export async function addMemory(
  accessToken: string,
  memoryText: string,
) {
  return postJsonAt(
    DIRECT_API_URL,
    "/api/memory",
    {
      memory_text: memoryText,
      category: "preference",
    },
    20000,
    1,
    accessToken,
  );
}

export async function updateMemoryEnabled(
  accessToken: string,
  enabled: boolean,
) {
  return patchJsonAt(
    DIRECT_API_URL,
    "/api/memory/settings",
    { enabled },
    accessToken,
  );
}

export async function removeMemory(
  accessToken: string,
  memoryId: string,
) {
  return deleteAt(
    DIRECT_API_URL,
    `/api/memory/${encodeURIComponent(memoryId)}`,
    accessToken,
  );
}

export async function fetchDocuments(accessToken: string) {
  const data = await getAt(DIRECT_API_URL, "/api/documents", accessToken);
  return Array.isArray(data.documents)
    ? (data.documents as KnowledgeDocument[])
    : [];
}

export async function uploadKnowledgeDocument(
  accessToken: string,
  file: File,
) {
  return postFormAt(
    DIRECT_API_URL,
    "/api/documents",
    () => {
      const form = new FormData();
      form.append("file", file, file.name);
      return form;
    },
    180000,
    1,
    accessToken,
  );
}

export async function removeKnowledgeDocument(
  accessToken: string,
  documentId: string,
) {
  return deleteAt(
    DIRECT_API_URL,
    `/api/documents/${encodeURIComponent(documentId)}`,
    accessToken,
  );
}

/* VASUKI_V8_PHASE3_PART2_API_START */
export type GeneratedArtifact = {
  id: string;
  name: string;
  artifact_type: string;
  mime_type: string;
  provider?: string;
  prompt?: string;
  created_at?: string;
  expires_at?: string;
  download_url?: string;
};

export type VasukiProject = {
  id: string;
  name: string;
  description?: string;
  instructions?: string;
  color?: string;
  archived?: boolean;
  created_at?: string;
  updated_at?: string;
};

export type OwnerAnalytics = {
  ok?: boolean;
  persistent?: {
    requests?: number;
    active_users?: number;
    average_latency_ms?: number | null;
    errors?: number;
    quota_429?: number;
    features?: Record<string, number>;
    providers?: Record<string, number>;
  };
  chat_provider_health?: Record<string, unknown>;
  image_provider_health?: Record<string, unknown>;
  cache?: Record<string, unknown>;
};

export async function fetchMyFiles(accessToken: string): Promise<GeneratedArtifact[]> {
  const data = await getAt(DIRECT_API_URL, "/api/files", accessToken);
  return Array.isArray(data.files) ? (data.files as GeneratedArtifact[]) : [];
}

export async function deleteMyFile(accessToken: string, artifactId: string) {
  return deleteAt(DIRECT_API_URL, `/api/files/${encodeURIComponent(artifactId)}`, accessToken);
}

export async function fetchImageHistory(accessToken: string): Promise<GeneratedArtifact[]> {
  const data = await getAt(DIRECT_API_URL, "/api/images/history", accessToken);
  return Array.isArray(data.images) ? (data.images as GeneratedArtifact[]) : [];
}

export async function fetchOwnerAnalytics(accessToken: string, days = 7): Promise<OwnerAnalytics> {
  return (await getAt(
    DIRECT_API_URL,
    `/api/owner/analytics/v2?days=${Math.max(1, Math.min(days, 90))}`,
    accessToken,
  )) as OwnerAnalytics;
}

export async function fetchProjects(accessToken: string): Promise<VasukiProject[]> {
  const data = await getAt(DIRECT_API_URL, "/api/projects", accessToken);
  return Array.isArray(data.projects) ? (data.projects as VasukiProject[]) : [];
}

export async function createProject(
  accessToken: string,
  payload: { name: string; description?: string; instructions?: string; color?: string },
) {
  return postJsonAt(DIRECT_API_URL, "/api/projects", payload, 20000, 1, accessToken);
}

export async function submitResponseFeedback(
  accessToken: string,
  payload: {
    rating: "up" | "down";
    category: string;
    message_id?: string;
    comment?: string;
    metadata?: Record<string, unknown>;
  },
) {
  return postJsonAt(DIRECT_API_URL, "/api/feedback", payload, 15000, 1, accessToken);
}

export async function createConversationBranch(
  accessToken: string,
  payload: {
    conversation_id: string;
    source_message_id?: string;
    original_prompt: string;
    edited_prompt: string;
    note?: string;
  },
) {
  return postJsonAt(DIRECT_API_URL, "/api/chat/branch", payload, 15000, 1, accessToken);
}
/* VASUKI_V8_PHASE3_PART2_API_END */

/* VASUKI_V8_PHASE4_API_START */
export type ProjectMemory = {
  id: string;
  project_id: string;
  memory_text: string;
  normalized_text?: string;
  source?: string;
  confidence?: number;
  created_at?: string;
  updated_at?: string;
};

export type ChatSearchResult = {
  chat_id: string;
  title: string;
  snippet?: string;
  updated_at?: string;
  project_id?: string;
  score?: number;
};

export type ConversationBranch = {
  id: string;
  conversation_id: string;
  source_message_id?: string;
  original_prompt: string;
  edited_prompt: string;
  note?: string;
  created_at?: string;
};

export async function fetchProjectMemories(accessToken: string, projectId: string): Promise<ProjectMemory[]> {
  const data = await getAt(DIRECT_API_URL, `/api/projects/${encodeURIComponent(projectId)}/memories`, accessToken);
  return Array.isArray(data.memories) ? (data.memories as ProjectMemory[]) : [];
}

export async function addProjectMemory(accessToken: string, projectId: string, memoryText: string) {
  return postJsonAt(
    DIRECT_API_URL,
    `/api/projects/${encodeURIComponent(projectId)}/memories`,
    { memory_text: memoryText },
    20000,
    1,
    accessToken,
  );
}

export async function deleteProjectMemory(accessToken: string, projectId: string, memoryId: string) {
  return deleteAt(
    DIRECT_API_URL,
    `/api/projects/${encodeURIComponent(projectId)}/memories/${encodeURIComponent(memoryId)}`,
    accessToken,
  );
}

export async function searchChatHistory(accessToken: string, query: string): Promise<ChatSearchResult[]> {
  const data = await getAt(
    DIRECT_API_URL,
    `/api/chat/search?q=${encodeURIComponent(query)}&limit=24`,
    accessToken,
  );
  return Array.isArray(data.results) ? (data.results as ChatSearchResult[]) : [];
}

export async function fetchRecentBranches(accessToken: string): Promise<ConversationBranch[]> {
  const data = await getAt(DIRECT_API_URL, "/api/chat/branches/recent?limit=120", accessToken);
  return Array.isArray(data.branches) ? (data.branches as ConversationBranch[]) : [];
}
/* VASUKI_V8_PHASE4_API_END */

/* VASUKI_V8_PHASE5_API_START */
export async function extractProjectMemories(
  accessToken: string,
  projectId: string,
  messages: ChatMessage[],
) {
  return postJsonAt(
    DIRECT_API_URL,
    `/api/projects/${encodeURIComponent(projectId)}/memories/auto-extract`,
    { messages: messages.slice(-24) },
    20000,
    1,
    accessToken,
  );
}
/* VASUKI_V8_PHASE5_API_END */

/* VASUKI_V9_PHASE2_API_START */
export type ProjectKbFile = {
  id: string;
  project_id: string;
  path: string;
  name: string;
  mime_type?: string;
  size_bytes?: number;
  language?: string;
  content_sha256?: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type ProjectCodeChange = {
  path: string;
  action: "update" | "create" | "delete";
  reason?: string;
  content: string;
  diff?: string;
};

export type ProjectCodeResult = {
  ok?: boolean;
  mode?: "patch" | "tests" | "debug";
  provider?: string;
  context_files?: string[];
  diff?: string;
  plan?: {
    summary?: string;
    changes?: ProjectCodeChange[];
    tests?: string[];
    risk_notes?: string[];
  };
};

export async function fetchProjectKbFiles(
  accessToken: string,
  projectId: string,
): Promise<ProjectKbFile[]> {
  const data = await getAt(
    DIRECT_API_URL,
    `/api/projects/${encodeURIComponent(projectId)}/kb/files`,
    accessToken,
  );
  return Array.isArray(data.files) ? (data.files as ProjectKbFile[]) : [];
}

export async function uploadProjectKbFiles(
  accessToken: string,
  projectId: string,
  files: File[],
) {
  return postFormAt(
    DIRECT_API_URL,
    `/api/projects/${encodeURIComponent(projectId)}/kb/files`,
    () => {
      const form = new FormData();
      for (const file of files) {
        form.append("files", file, file.name);
        form.append("paths", file.webkitRelativePath || file.name);
      }
      return form;
    },
    180000,
    1,
    accessToken,
  );
}

export async function deleteProjectKbFile(
  accessToken: string,
  projectId: string,
  path: string,
) {
  return deleteAt(
    DIRECT_API_URL,
    `/api/projects/${encodeURIComponent(projectId)}/kb/files?path=${encodeURIComponent(path)}`,
    accessToken,
  );
}

export async function fetchProjectCodebaseMap(
  accessToken: string,
  projectId: string,
) {
  return getAt(
    DIRECT_API_URL,
    `/api/projects/${encodeURIComponent(projectId)}/kb/map`,
    accessToken,
  );
}

export async function generateProjectPatch(
  accessToken: string,
  projectId: string,
  instruction: string,
): Promise<ProjectCodeResult> {
  return (await postJsonAt(
    DIRECT_API_URL,
    `/api/projects/${encodeURIComponent(projectId)}/code/patch`,
    { instruction, target_paths: [] },
    120000,
    1,
    accessToken,
  )) as ProjectCodeResult;
}

export async function generateProjectTests(
  accessToken: string,
  projectId: string,
  instruction: string,
): Promise<ProjectCodeResult> {
  return (await postJsonAt(
    DIRECT_API_URL,
    `/api/projects/${encodeURIComponent(projectId)}/tests/generate`,
    { instruction, target_paths: [] },
    120000,
    1,
    accessToken,
  )) as ProjectCodeResult;
}

export async function generateProjectDebugPlan(
  accessToken: string,
  projectId: string,
  instruction: string,
  errorLog: string,
): Promise<ProjectCodeResult> {
  return (await postJsonAt(
    DIRECT_API_URL,
    `/api/projects/${encodeURIComponent(projectId)}/debug`,
    { instruction, error_log: errorLog, target_paths: [] },
    120000,
    1,
    accessToken,
  )) as ProjectCodeResult;
}

export async function applyProjectCodePlan(
  accessToken: string,
  projectId: string,
  changes: ProjectCodeChange[],
) {
  return postJsonAt(
    DIRECT_API_URL,
    `/api/projects/${encodeURIComponent(projectId)}/code/apply`,
    {
      changes: changes.map((change) => ({
        path: change.path,
        action: change.action,
        content: change.content,
      })),
    },
    60000,
    1,
    accessToken,
  );
}
/* VASUKI_V9_PHASE2_API_END */

/* VASUKI_V9_PHASE3_API_START */
export type ImageStudioResult = {
  ok?: boolean;
  url?: string;
  provider?: string;
  preset?: string;
  aspect_ratio?: string;
  width?: number;
  height?: number;
  operation?: string;
  error?: string;
  index?: number;
  artifact?: GeneratedArtifact | null;
};

export type DocumentCitationV3 = {
  citation_id?: string;
  document?: string;
  page?: number | null;
  section?: string | null;
  kind?: string;
  excerpt?: string;
};

export type DocumentBlockV3 = {
  citation_id: string;
  source_id: string;
  page?: number | null;
  section?: string | null;
  kind?: string;
  text: string;
  word_count?: number;
};

export type StructuredDocumentV3 = {
  source_id: string;
  name: string;
  type: string;
  pages?: number | null;
  blocks: DocumentBlockV3[];
  warnings?: string[];
  ocr_provider?: string;
};

export type DocumentIntelligenceV3 = {
  ok?: boolean;
  answer?: string;
  provider?: string;
  citations?: DocumentCitationV3[];
  evidence?: DocumentCitationV3[];
  documents?: StructuredDocumentV3[];
  warnings?: string[];
  total_blocks?: number;
  text?: string;
  document?: StructuredDocumentV3;
  comparison?: {
    left?: string;
    right?: string;
    similarity_percent?: number;
    added_samples?: string[];
    removed_samples?: string[];
  };
};

export async function generateImageStudio(
  accessToken: string,
  prompt: string,
  preset: string,
  aspectRatio: string,
): Promise<ImageStudioResult> {
  return await postJsonAt(
    DIRECT_API_URL,
    "/api/image/v3/generate",
    { prompt, preset, aspect_ratio: aspectRatio },
    180000,
    1,
    accessToken,
  ) as ImageStudioResult;
}

export async function generateImageVariations(
  accessToken: string,
  prompt: string,
  preset: string,
  aspectRatio: string,
  count: number,
): Promise<{ ok?: boolean; items: ImageStudioResult[]; requested?: number; succeeded?: number; failed?: number }> {
  const data = await postJsonAt(
    DIRECT_API_URL,
    "/api/image/v3/variations",
    { prompt, preset, aspect_ratio: aspectRatio, count },
    300000,
    1,
    accessToken,
  );
  return {
    ok: data.ok !== false,
    items: Array.isArray(data.items) ? data.items as ImageStudioResult[] : [],
    requested: typeof data.requested === "number" ? data.requested : undefined,
    succeeded: typeof data.succeeded === "number" ? data.succeeded : undefined,
    failed: typeof data.failed === "number" ? data.failed : undefined,
  };
}

export async function editImageStudio(
  accessToken: string,
  file: File,
  prompt: string,
  preset: string,
  aspectRatio: string,
): Promise<ImageStudioResult> {
  return await postFormAt(
    DIRECT_API_URL,
    "/api/image/v3/edit",
    () => {
      const form = new FormData();
      form.append("file", file, file.name);
      form.append("prompt", prompt);
      form.append("preset", preset);
      form.append("aspect_ratio", aspectRatio);
      return form;
    },
    240000,
    1,
    accessToken,
  ) as ImageStudioResult;
}

export async function enhanceImageStudio(
  accessToken: string,
  file: File,
  scale: number,
): Promise<ImageStudioResult> {
  return await postFormAt(
    DIRECT_API_URL,
    "/api/image/v3/enhance",
    () => {
      const form = new FormData();
      form.append("file", file, file.name);
      form.append("scale", String(scale));
      return form;
    },
    120000,
    1,
    accessToken,
  ) as ImageStudioResult;
}

function v3DocumentForm(files: File[], prompt?: string) {
  const form = new FormData();
  if (typeof prompt === "string") form.append("prompt", prompt);
  for (const file of files) form.append("files", file, file.name);
  return form;
}

export async function extractDocumentsV3(
  accessToken: string,
  files: File[],
): Promise<DocumentIntelligenceV3> {
  return await postFormAt(
    DIRECT_API_URL,
    "/api/documents/v3/extract",
    () => v3DocumentForm(files),
    240000,
    1,
    accessToken,
  ) as DocumentIntelligenceV3;
}

export async function askDocumentsV3(
  accessToken: string,
  files: File[],
  prompt: string,
): Promise<DocumentIntelligenceV3> {
  return await postFormAt(
    DIRECT_API_URL,
    "/api/documents/v3/ask",
    () => v3DocumentForm(files, prompt),
    300000,
    1,
    accessToken,
  ) as DocumentIntelligenceV3;
}

export async function compareDocumentsV3(
  accessToken: string,
  files: File[],
  prompt: string,
): Promise<DocumentIntelligenceV3> {
  return await postFormAt(
    DIRECT_API_URL,
    "/api/documents/v3/compare",
    () => v3DocumentForm(files, prompt),
    300000,
    1,
    accessToken,
  ) as DocumentIntelligenceV3;
}

export async function ocrDocumentV3(
  accessToken: string,
  file: File,
): Promise<DocumentIntelligenceV3> {
  return await postFormAt(
    DIRECT_API_URL,
    "/api/documents/v3/ocr",
    () => {
      const form = new FormData();
      form.append("file", file, file.name);
      return form;
    },
    240000,
    1,
    accessToken,
  ) as DocumentIntelligenceV3;
}
/* VASUKI_V9_PHASE3_API_END */

/* VASUKI_V9_PHASE4_API_START */
export type BackgroundJobV9 = {
  id: string;
  kind: string;
  status: "pending" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  error?: string | null;
  attempts?: number;
  created_at?: string;
  updated_at?: string;
  finished_at?: string | null;
};

export type NotificationV9 = {
  id: string;
  title: string;
  body: string;
  kind?: string;
  action_url?: string | null;
  metadata?: Record<string, unknown>;
  read_at?: string | null;
  created_at?: string;
};

export type UsageSnapshotV9 = {
  period_days?: number;
  requests?: number;
  features?: Record<string, number>;
  providers?: Record<string, number>;
  statuses?: Record<string, number>;
  average_latency_ms?: number | null;
  errors?: number;
  quota_429?: number;
  daily?: Array<{ date: string; requests: number }>;
  cost?: {
    reported_cost_usd?: number;
    estimated_cost_usd?: number;
    reported_cost_events?: number;
    estimated_cost_events?: number;
    unpriced_events?: number;
    by_provider?: Record<string, {
      reported_cost_usd?: number;
      estimated_cost_usd?: number;
      events?: number;
    }>;
    note?: string;
  };
};

export type PlanPolicyV3 = {
  plan?: string;
  background_jobs_daily?: number;
  active_background_jobs?: number;
  image_variations_max?: number;
  allowed_background_kinds?: string[];
};

export type FeatureAssignmentV9 = {
  enabled?: boolean;
  rollout_percent?: number;
  bucket?: number;
  variant?: string | null;
  description?: string;
  source?: string;
};

export type PlatformSnapshotV9 = {
  ok?: boolean;
  plan?: {
    plan?: string;
    is_owner?: boolean;
    puter_access?: boolean;
    pro_expires_at?: string | null;
  };
  policy?: PlanPolicyV3;
  usage?: UsageSnapshotV9;
  jobs?: BackgroundJobV9[];
  notifications?: {
    items?: NotificationV9[];
    unread?: number;
  };
  features?: Record<string, FeatureAssignmentV9>;
  experiments?: Record<string, string>;
};

export type OwnerPlatformV9 = {
  ok?: boolean;
  period_days?: number;
  usage?: UsageSnapshotV9 & { active_users?: number };
  jobs?: {
    total?: number;
    statuses?: Record<string, number>;
    kinds?: Record<string, number>;
  };
  experiments?: Record<string, Record<string, { exposure?: number; conversion?: number }>>;
  feature_flags?: Record<string, {
    enabled?: boolean;
    rollout_percent?: number;
    variants?: Record<string, number>;
    description?: string;
    source?: string;
  }>;
};

export async function fetchPlatformSnapshotV9(
  accessToken: string,
  days = 30,
): Promise<PlatformSnapshotV9> {
  return await getAt(
    DIRECT_API_URL,
    `/api/platform/v9/snapshot?days=${encodeURIComponent(days)}`,
    accessToken,
  ) as PlatformSnapshotV9;
}

export async function createBackgroundJobV9(
  accessToken: string,
  kind: string,
  payload: Record<string, unknown>,
) {
  return postJsonAt(
    DIRECT_API_URL,
    "/api/jobs/v9",
    { kind, payload },
    30000,
    1,
    accessToken,
  );
}

export async function cancelBackgroundJobV9(
  accessToken: string,
  jobId: string,
) {
  return deleteAt(
    DIRECT_API_URL,
    `/api/jobs/v9/${encodeURIComponent(jobId)}`,
    accessToken,
  );
}

export async function markNotificationReadV9(
  accessToken: string,
  notificationId: string,
) {
  return patchJsonAt(
    DIRECT_API_URL,
    `/api/notifications/v9/${encodeURIComponent(notificationId)}/read`,
    {},
    accessToken,
  );
}

export async function markAllNotificationsReadV9(accessToken: string) {
  return postJsonAt(
    DIRECT_API_URL,
    "/api/notifications/v9/read-all",
    {},
    20000,
    1,
    accessToken,
  );
}

export async function recordExperimentExposureV9(
  accessToken: string,
  experiment: string,
  variant: string,
  metadata: Record<string, unknown> = {},
) {
  return postJsonAt(
    DIRECT_API_URL,
    `/api/experiments/v9/${encodeURIComponent(experiment)}/exposure`,
    { variant, metadata },
    20000,
    1,
    accessToken,
  );
}

export async function recordExperimentConversionV9(
  accessToken: string,
  experiment: string,
  variant: string,
  metadata: Record<string, unknown> = {},
) {
  return postJsonAt(
    DIRECT_API_URL,
    `/api/experiments/v9/${encodeURIComponent(experiment)}/conversion`,
    { variant, metadata },
    20000,
    1,
    accessToken,
  );
}

export async function fetchOwnerPlatformV9(
  accessToken: string,
  days = 30,
): Promise<OwnerPlatformV9> {
  return await getAt(
    DIRECT_API_URL,
    `/api/owner/platform/v9?days=${encodeURIComponent(days)}`,
    accessToken,
  ) as OwnerPlatformV9;
}

export async function updateOwnerFeatureFlagV9(
  accessToken: string,
  key: string,
  value: {
    enabled: boolean;
    rollout_percent: number;
    variants?: Record<string, number>;
    description?: string;
  },
) {
  return patchJsonAt(
    DIRECT_API_URL,
    `/api/owner/features/v9/${encodeURIComponent(key)}`,
    value,
    accessToken,
  );
}
/* VASUKI_V9_PHASE4_API_END */

/* VASUKI_V9_PHASE5_API_START */
export type AccountChatV9 = {
  id: string;
  title?: string;
  updated_at?: string;
  project_id?: string | null;
};

export type StorageSnapshotV9 = {
  ok?: boolean;
  plan?: string;
  quota_bytes?: number;
  used_bytes?: number;
  remaining_bytes?: number;
  percent_used?: number;
  breakdown?: {
    generated_artifacts?: number;
    knowledge_documents?: number;
    project_files?: number;
  };
};

export type PushConfigV9 = {
  ok?: boolean;
  configured?: boolean;
  public_key?: string;
  subject?: string;
};

export async function fetchAccountChatsV9(
  accessToken: string,
): Promise<{ chats?: AccountChatV9[] }> {
  return await getAt(
    DIRECT_API_URL,
    "/api/account/v9/chats?limit=300",
    accessToken,
  ) as { chats?: AccountChatV9[] };
}

export async function exportChatV9(
  accessToken: string,
  chatId: string,
  format: "markdown" | "json",
): Promise<{ filename?: string; mime_type?: string; content?: string }> {
  return await getAt(
    DIRECT_API_URL,
    `/api/account/v9/export/chat/${encodeURIComponent(chatId)}?format=${encodeURIComponent(format)}`,
    accessToken,
  ) as { filename?: string; mime_type?: string; content?: string };
}

export async function exportFullAccountV9(
  accessToken: string,
): Promise<{ filename?: string; mime_type?: string; data?: Record<string, unknown> }> {
  return await getAt(
    DIRECT_API_URL,
    "/api/account/v9/export/full",
    accessToken,
  ) as { filename?: string; mime_type?: string; data?: Record<string, unknown> };
}

export async function fetchStorageV9(
  accessToken: string,
): Promise<StorageSnapshotV9> {
  return await getAt(
    DIRECT_API_URL,
    "/api/storage/v9",
    accessToken,
  ) as StorageSnapshotV9;
}

export async function cleanupStorageV9(
  accessToken: string,
) {
  return postJsonAt(
    DIRECT_API_URL,
    "/api/storage/v9/cleanup",
    {},
    30000,
    1,
    accessToken,
  );
}

export async function fetchPushConfigV9(
  accessToken: string,
): Promise<PushConfigV9> {
  return await getAt(
    DIRECT_API_URL,
    "/api/push/v9/config",
    accessToken,
  ) as PushConfigV9;
}

export async function subscribePushV9(
  accessToken: string,
  subscription: unknown,
) {
  return postJsonAt(
    DIRECT_API_URL,
    "/api/push/v9/subscribe",
    { subscription },
    30000,
    1,
    accessToken,
  );
}

export async function unsubscribePushV9(
  accessToken: string,
  endpoint: string,
) {
  const response = await fetch(
    `${DIRECT_API_URL}/api/push/v9/subscribe`,
    {
      method: "DELETE",
      headers: authHeaders(accessToken, true),
      body: JSON.stringify({ endpoint }),
      cache: "no-store",
    },
  );
  return readResponse(response);
}

export async function deleteAccountV9(
  accessToken: string,
  confirmEmail: string,
  confirmation: string,
) {
  const response = await fetch(
    `${DIRECT_API_URL}/api/account/v9`,
    {
      method: "DELETE",
      headers: authHeaders(accessToken, true),
      body: JSON.stringify({
        confirm_email: confirmEmail,
        confirmation,
      }),
      cache: "no-store",
    },
  );
  return readResponse(response);
}
/* VASUKI_V9_PHASE5_API_END */

/* VASUKI_V9_PHASE6_API_START */
export type SecurityCenterV9 = { ok?: boolean; security?: { score?: number; grade?: string; findings?: Array<{ severity?: string; check?: string; detail?: string }>; secret_inventory?: Array<{ name?: string; configured?: boolean; fingerprint?: string | null }> }; audit_logs?: Array<Record<string, unknown>>; errors?: { total?: number; unresolved?: number; recent?: Array<Record<string, unknown>> }; backups?: Array<Record<string, unknown>>; evals?: Array<Record<string, unknown>>; release_health?: Record<string, unknown> };
export async function fetchSecurityCenterV9(accessToken: string): Promise<SecurityCenterV9> { return await getAt(DIRECT_API_URL, "/api/owner/security-center/v9?days=7", accessToken) as SecurityCenterV9; }
export async function createBackupV9(accessToken: string, note = "") { return postJsonAt(DIRECT_API_URL, "/api/owner/backups/v9", { note }, 120000, 1, accessToken); }
export async function restoreBackupV9(accessToken: string, backupId: string, apply: boolean, confirmation = "") { return postJsonAt(DIRECT_API_URL, `/api/owner/backups/v9/${encodeURIComponent(backupId)}/restore`, { apply, confirmation }, 120000, 1, accessToken); }
export async function resolveErrorV9(accessToken: string, errorId: number) { return patchJsonAt(DIRECT_API_URL, `/api/owner/errors/v9/${errorId}/resolve`, {}, accessToken); }
export async function recordSecretRotationV9(accessToken: string, secretName: string, previousFingerprint: string, note = "") { return postJsonAt(DIRECT_API_URL, "/api/owner/secrets/v9/rotation", { secret_name: secretName, previous_fingerprint: previousFingerprint, note }, 30000, 1, accessToken); }
/* VASUKI_V9_PHASE6_API_END */


/* VASUKI_V12_CORE_API */
export type V12ReliabilitySnapshot = {
  ok?: boolean;
  version?: string;
  slo?: {
    samples?: number;
    chat_samples?: number;
    p50_latency_ms?: number | null;
    p95_latency_ms?: number | null;
    p50_first_token_ms?: number | null;
    p95_first_token_ms?: number | null;
    success_pct?: number;
    fallback_pct?: number;
    error_pct?: number;
  };
  capabilities?: Record<string, string>;
  sandbox?: {
    available?: boolean;
    engine?: string | null;
    network?: string;
    filesystem?: string;
    memory_mb?: number;
    cpu_limit?: number;
    pids_limit?: number;
  };
  providers?: Record<string, {
    configured?: boolean;
    tasks?: Record<string, {
      score?: number;
      feedback_quality?: number;
      benchmark_quality?: number;
      success_rate?: number;
      speed?: number;
    }>;
  }>;
};

export async function fetchOwnerReliabilityV12(
  accessToken: string,
): Promise<V12ReliabilitySnapshot> {
  return await getAt(
    DIRECT_API_URL,
    "/api/owner/v12/reliability",
    accessToken,
  ) as V12ReliabilitySnapshot;
}

/* VASUKI_V15_CODE_PROJECT_API_START */
export type CodeProjectSpec = {
  project_name: string;
  summary?: string;
  language?: string;
  framework?: string;
  files: Array<{ path: string; content: string }>;
  powershell?: string[];
  run_commands?: string[];
  notes?: string[];
};

export type CodeProjectResponse = SmartFileResponse & {
  version?: string;
  project_name: string;
  summary?: string;
  language?: string;
  framework?: string;
  tree?: string;
  powershell?: string[];
  primary_file?: string;
  primary_language?: string;
  primary_code?: string;
  preview_doc?: string;
};

function normalizeCodeProjectResponse(
  data: Record<string, unknown>,
): CodeProjectResponse {
  return {
    answer: typeof data.answer === "string" ? data.answer : "",
    provider:
      typeof data.provider === "string" ? data.provider : undefined,
    files: Array.isArray(data.files)
      ? (data.files as SmartFileArtifact[])
      : [],
    processed_files: Array.isArray(data.processed_files)
      ? data.processed_files.map(String)
      : [],
    warnings: Array.isArray(data.warnings)
      ? data.warnings.map(String)
      : [],
    version:
      typeof data.version === "string" ? data.version : undefined,
    project_name:
      typeof data.project_name === "string"
        ? data.project_name
        : "vasuki-project",
    summary:
      typeof data.summary === "string" ? data.summary : undefined,
    language:
      typeof data.language === "string" ? data.language : undefined,
    framework:
      typeof data.framework === "string"
        ? data.framework
        : undefined,
    tree: typeof data.tree === "string" ? data.tree : undefined,
    powershell: Array.isArray(data.powershell)
      ? data.powershell.map(String)
      : [],
    primary_file:
      typeof data.primary_file === "string"
        ? data.primary_file
        : undefined,
    primary_language:
      typeof data.primary_language === "string"
        ? data.primary_language
        : undefined,
    primary_code:
      typeof data.primary_code === "string"
        ? data.primary_code
        : undefined,
    preview_doc:
      typeof data.preview_doc === "string"
        ? data.preview_doc
        : undefined,
  };
}

export function parseCodeProjectSpec(
  raw: string,
): CodeProjectSpec {
  let text = raw.trim();
  text = text
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/, "");

  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start >= 0 && end > start) {
    text = text.slice(start, end + 1);
  }

  const parsed = JSON.parse(text) as Record<string, unknown>;
  const rawFiles = Array.isArray(parsed.files)
    ? parsed.files
    : [];
  const files = rawFiles.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const value = item as Record<string, unknown>;
    if (
      typeof value.path !== "string" ||
      typeof value.content !== "string" ||
      !value.path.trim()
    ) {
      return [];
    }
    return [{
      path: value.path.trim(),
      content: value.content,
    }];
  });

  if (files.length === 0) {
    throw new Error(
      "Vasuki Pro returned no project files.",
    );
  }

  return {
    project_name:
      typeof parsed.project_name === "string"
        ? parsed.project_name
        : "vasuki-project",
    summary:
      typeof parsed.summary === "string" ? parsed.summary : "",
    language:
      typeof parsed.language === "string"
        ? parsed.language
        : "mixed",
    framework:
      typeof parsed.framework === "string"
        ? parsed.framework
        : "custom",
    files,
    powershell: Array.isArray(parsed.powershell)
      ? parsed.powershell.map(String)
      : [],
    run_commands: Array.isArray(parsed.run_commands)
      ? parsed.run_commands.map(String)
      : [],
    notes: Array.isArray(parsed.notes)
      ? parsed.notes.map(String)
      : [],
  };
}

export async function buildCodeProject(
  prompt: string,
  accessToken: string,
): Promise<CodeProjectResponse> {
  const bases = Array.from(
    new Set([DIRECT_API_URL, PROXY_API_URL]),
  );
  const errors: string[] = [];

  for (const baseUrl of bases) {
    try {
      const data = await postJsonAt(
        baseUrl,
        "/api/v15/code/project",
        { prompt },
        240000,
        1,
        accessToken,
      );
      return normalizeCodeProjectResponse(data);
    } catch (error) {
      errors.push(
        error instanceof Error
          ? error.message
          : "V15 project build failed.",
      );
    }
  }

  throw new Error(
    errors.at(-1) ||
      "V15 project builder is temporarily unavailable.",
  );
}

export async function modifyCodeProject(
  file: File,
  prompt: string,
  accessToken: string,
): Promise<CodeProjectResponse> {
  const bases = Array.from(
    new Set([DIRECT_API_URL, PROXY_API_URL]),
  );
  const errors: string[] = [];

  for (const baseUrl of bases) {
    try {
      const data = await postFormAt(
        baseUrl,
        "/api/v15/code/modify",
        () => {
          const form = new FormData();
          form.append("prompt", prompt);
          form.append("file", file, file.name);
          return form;
        },
        300000,
        1,
        accessToken,
      );
      return normalizeCodeProjectResponse(data);
    } catch (error) {
      errors.push(
        error instanceof Error
          ? error.message
          : "V15 project modification failed.",
      );
    }
  }

  throw new Error(
    errors.at(-1) ||
      "V15 project modifier is temporarily unavailable.",
  );
}

export async function packageCodeProject(
  spec: CodeProjectSpec,
  accessToken: string,
): Promise<CodeProjectResponse> {
  const data = await postJsonAt(
    DIRECT_API_URL,
    "/api/v15/code/package",
    spec,
    60000,
    2,
    accessToken,
  );
  return normalizeCodeProjectResponse(data);
}
/* VASUKI_V15_CODE_PROJECT_API_END */

/* VASUKI_V16_AUTONOMOUS_BUILDER_API_START */
export async function buildCodeProjectV16(
  prompt: string,
  accessToken: string,
): Promise<CodeProjectResponse> {
  const bases = Array.from(
    new Set([DIRECT_API_URL, PROXY_API_URL]),
  );
  const errors: string[] = [];

  for (const baseUrl of bases) {
    try {
      const data = await postJsonAt(
        baseUrl,
        "/api/v16/code/project",
        { prompt },
        360000,
        1,
        accessToken,
      );
      return normalizeCodeProjectResponse(data);
    } catch (error) {
      errors.push(
        error instanceof Error
          ? error.message
          : "V16 autonomous project build failed.",
      );
    }
  }

  throw new Error(
    errors.at(-1) ||
      "V16 autonomous project builder is temporarily unavailable.",
  );
}

export async function modifyCodeProjectV16(
  file: File,
  prompt: string,
  accessToken: string,
): Promise<CodeProjectResponse> {
  const bases = Array.from(
    new Set([DIRECT_API_URL, PROXY_API_URL]),
  );
  const errors: string[] = [];

  for (const baseUrl of bases) {
    try {
      const data = await postFormAt(
        baseUrl,
        "/api/v16/code/modify",
        () => {
          const form = new FormData();
          form.append("prompt", prompt);
          form.append("file", file, file.name);
          return form;
        },
        420000,
        1,
        accessToken,
      );
      return normalizeCodeProjectResponse(data);
    } catch (error) {
      errors.push(
        error instanceof Error
          ? error.message
          : "V16 project modification failed.",
      );
    }
  }

  throw new Error(
    errors.at(-1) ||
      "V16 autonomous project modifier is temporarily unavailable.",
  );
}
/* VASUKI_V16_AUTONOMOUS_BUILDER_API_END */

/* VASUKI_V17_ASYNC_CODE_JOBS_START */
export type CodeBuildJobStatus = {
  ok?: boolean;
  job_id: string;
  status:
    | "queued"
    | "running"
    | "succeeded"
    | "failed"
    | "cancelled";
  stage: string;
  progress: number;
  message: string;
  error?: string | null;
  result?: CodeProjectResponse;
};

async function getCodeJobAt(
  baseUrl: string,
  jobId: string,
  accessToken: string,
): Promise<CodeBuildJobStatus> {
  return (await getAt(
    baseUrl,
    `/api/v17/code/jobs/${encodeURIComponent(jobId)}`,
    accessToken,
  )) as CodeBuildJobStatus;
}

export async function startCodeBuildJobV17(
  prompt: string,
  accessToken: string,
): Promise<CodeBuildJobStatus> {
  let directError: unknown = null;
  try {
    return (await postJsonAt(
      DIRECT_API_URL,
      "/api/v17/code/jobs",
      { prompt },
      30000,
      2,
      accessToken,
    )) as CodeBuildJobStatus;
  } catch (error) {
    directError = error;
  }

  try {
    return (await postJsonAt(
      PROXY_API_URL,
      "/api/v17/code/jobs",
      { prompt },
      30000,
      1,
      accessToken,
    )) as CodeBuildJobStatus;
  } catch {
    throw directError instanceof Error
      ? directError
      : new Error("Vasuki Forge could not start the build.");
  }
}

export async function startCodeModifyJobV17(
  file: File,
  prompt: string,
  accessToken: string,
): Promise<CodeBuildJobStatus> {
  return (await postFormAt(
    DIRECT_API_URL,
    "/api/v17/code/jobs/modify",
    () => {
      const form = new FormData();
      form.append("prompt", prompt);
      form.append("file", file, file.name);
      return form;
    },
    60000,
    2,
    accessToken,
  )) as CodeBuildJobStatus;
}

export async function waitForCodeBuildJobV17(
  jobId: string,
  accessToken: string,
  onProgress?: (job: CodeBuildJobStatus) => void,
  signal?: AbortSignal,
): Promise<CodeProjectResponse> {
  const startedAt = Date.now();
  const maxWaitMs = 15 * 60 * 1000;

  while (Date.now() - startedAt < maxWaitMs) {
    if (signal?.aborted) {
      throw new DOMException("Build stopped", "AbortError");
    }

    let state: CodeBuildJobStatus;
    try {
      state = await getCodeJobAt(
        DIRECT_API_URL,
        jobId,
        accessToken,
      );
    } catch (directError) {
      try {
        state = await getCodeJobAt(
          PROXY_API_URL,
          jobId,
          accessToken,
        );
      } catch {
        throw directError instanceof Error
          ? directError
          : new Error("Build status could not be loaded.");
      }
    }

    onProgress?.(state);

    if (state.status === "succeeded") {
      if (!state.result) {
        throw new Error(
          "Build completed, but the project package was missing.",
        );
      }
      return normalizeCodeProjectResponse(
        state.result as unknown as Record<string, unknown>,
      );
    }

    if (state.status === "failed") {
      throw new Error(
        state.message ||
          state.error ||
          `Build failed during ${state.stage}.`,
      );
    }

    if (state.status === "cancelled") {
      throw new DOMException("Build cancelled", "AbortError");
    }

    await delay(1200);
  }

  throw new Error(
    "The project build is still running after 15 minutes. " +
      "Please retry with a smaller first version, then ask Vasuki to expand it.",
  );
}

export async function cancelCodeBuildJobV17(
  jobId: string,
  accessToken: string,
) {
  return deleteAt(
    DIRECT_API_URL,
    `/api/v17/code/jobs/${encodeURIComponent(jobId)}`,
    accessToken,
  );
}
/* VASUKI_V17_ASYNC_CODE_JOBS_END */
