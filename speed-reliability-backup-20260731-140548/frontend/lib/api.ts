// Browser requests now go to the Next.js server first. Next.js securely proxies
// /backend-api/* to the FastAPI backend configured through BACKEND_URL.
const API_URL = "/backend-api";

export type ChatMessage = { role: "user" | "assistant"; content: string };

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
    const detail = typeof data.detail === "string" ? data.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }

  return data;
}

export async function sendChat(messages: ChatMessage[], useWeb: boolean) {
  const response = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, provider: "auto", use_web: useWeb }),
  });
  return parseResponse(response);
}

export async function generateImage(prompt: string) {
  const response = await fetch(`${API_URL}/api/image`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, provider: "auto" }),
  });
  return parseResponse(response);
}
