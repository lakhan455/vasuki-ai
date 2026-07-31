export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type ChatMessage = { role: "user" | "assistant"; content: string };

async function parseResponse(response: Response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Request failed");
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
