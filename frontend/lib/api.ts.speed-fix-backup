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

    if (RETRYABLE_STATUS.has(response.status)) {
      throw new Error(
        "AI server is waking up or temporarily busy. Please retry in a few seconds.",
      );
    }

    throw new Error(detail);
  }

  return data;
}

async function postJson(path: string, body: unknown) {
  let lastResponse: Response | null = null;

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const response = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });

    lastResponse = response;

    if (!RETRYABLE_STATUS.has(response.status) || attempt === 1) {
      return parseResponse(response);
    }

    await delay(1200);
  }

  return parseResponse(lastResponse as Response);
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
  return postJson("/api/chat", {
    messages,
    provider: "auto",
    use_web: useWeb,
  });
}

export async function generateImage(prompt: string) {
  return postJson("/api/image", {
    prompt,
    provider: "auto",
  });
}
