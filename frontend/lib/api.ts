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
        if (typeof parsed.data.provider === "string") {
          meta.provider = parsed.data.provider;
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
  try {
    return await streamAt(
      DIRECT_API_URL,
      messages,
      options,
      onToken,
    );
  } catch (error) {
    if (
      options.signal?.aborted ||
      (error instanceof DOMException && error.name === "AbortError")
    ) {
      throw error;
    }

    const message =
      error instanceof Error ? error.message : "Streaming connection failed.";

    if (/failed to fetch|network|connection/i.test(message)) {
      return streamAt(
        PROXY_API_URL,
        messages,
        options,
        onToken,
      );
    }

    throw error;
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
        "/api/smart-files",
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
        "/api/image",
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
