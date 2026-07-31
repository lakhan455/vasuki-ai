// Browser requests go through the Next.js proxy by default.
const API_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "/backend-api"
).replace(/\/$/, "");

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const RETRYABLE_STATUS = new Set([500, 502, 503, 504]);

function delay(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function parseResponse(response: Response) {
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

async function postJson(
  path: string,
  body: unknown,
  timeoutMilliseconds: number,
) {
  let lastResponse: Response | null = null;
  let lastError: unknown = null;

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(
      () => controller.abort(),
      timeoutMilliseconds,
    );

    try {
      const response = await fetch(`${API_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        cache: "no-store",
        signal: controller.signal,
      });

      lastResponse = response;

      if (!RETRYABLE_STATUS.has(response.status) || attempt === 1) {
        return await parseResponse(response);
      }
    } catch (error) {
      lastError = error;

      if (attempt === 1) {
        if (error instanceof DOMException && error.name === "AbortError") {
          throw new Error(
            "AI response timed out. Please retry once; a faster provider will be used.",
          );
        }

        throw new Error(
          "AI server could not be reached. Please check your internet and retry.",
        );
      }
    } finally {
      window.clearTimeout(timeoutId);
    }

    await delay(1200);
  }

  if (lastResponse) {
    return parseResponse(lastResponse);
  }

  throw lastError instanceof Error
    ? lastError
    : new Error("AI request failed. Please retry.");
}

export async function warmBackend() {
  try {
    await fetch(`${API_URL}/health`, {
      method: "GET",
      cache: "no-store",
    });
  } catch {
    // Warming is best-effort. Chat requests still show a useful error.
  }
}

export async function sendChat(messages: ChatMessage[], useWeb: boolean) {
  return postJson(
    "/api/chat",
    {
      messages,
      provider: "auto",
      use_web: useWeb,
    },
    65000,
  );
}

export async function generateImage(prompt: string) {
  return postJson(
    "/api/image",
    {
      prompt,
      provider: "auto",
    },
    120000,
  );
}
