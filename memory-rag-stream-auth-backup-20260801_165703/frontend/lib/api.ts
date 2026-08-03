// Chat uses the Vercel proxy. Large media responses try Render directly
// first so multi-megabyte payloads do not depend on the Vercel rewrite.
const PROXY_API_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "/backend-api"
).replace(/\/$/, "");

const DIRECT_MEDIA_API_URL = (
  process.env.NEXT_PUBLIC_IMAGE_API_BASE_URL ||
  "https://vasuki-ai.onrender.com"
).replace(/\/$/, "");

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);

function delay(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
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
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : `Request failed (${response.status})`;
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
        headers: { "Content-Type": "application/json" },
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

    await delay([1500, 3000, 5000][Math.min(attempt, 2)]);
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
            "Image/file analysis timed out. Please retry with a smaller file.",
          );
        }
        throw error instanceof Error
          ? error
          : new Error("Image/file service connection failed.");
      }
    } finally {
      window.clearTimeout(timeoutId);
    }

    await delay([1500, 3000, 5000][Math.min(attempt, 2)]);
  }

  throw lastError instanceof Error
    ? lastError
    : new Error("Image/file request failed.");
}

export async function warmBackend() {
  const targets = [
    `${DIRECT_MEDIA_API_URL}/health`,
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

export async function sendChat(messages: ChatMessage[], useWeb: boolean) {
  const body = {
    messages,
    provider: "auto",
    use_web: useWeb,
  };

  try {
    return await postJsonAt(
      DIRECT_MEDIA_API_URL,
      "/api/chat",
      body,
      65000,
      1,
    );
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "AI service connection failed.";

    if (/failed to fetch|network|connection/i.test(message)) {
      return postJsonAt(
        PROXY_API_URL,
        "/api/chat",
        body,
        65000,
        1,
      );
    }

    throw error;
  }
}

export async function analyzeAttachment(file: File, prompt: string) {
  const bases = Array.from(
    new Set([DIRECT_MEDIA_API_URL, PROXY_API_URL]),
  );
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

export async function generateImage(prompt: string) {
  const body = {
    prompt,
    provider: "auto",
  };

  const bases = Array.from(
    new Set([DIRECT_MEDIA_API_URL, PROXY_API_URL]),
  );

  const errors: string[] = [];

  for (const baseUrl of bases) {
    try {
      return await postJsonAt(
        baseUrl,
        "/api/image",
        body,
        150000,
        3,
      );
    } catch (error) {
      errors.push(
        error instanceof Error ? error.message : "Unknown image service error",
      );
    }
  }

  throw new Error(
    errors.find((message) => message.includes("Cloudflare")) ||
      errors.find((message) => message.includes("providers")) ||
      errors.at(-1) ||
      "Image generation failed after automatic retries.",
  );
}
