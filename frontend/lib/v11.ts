import { supabase } from "@/lib/supabase";

const API = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

async function accessToken() {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error("Please sign in again.");
  return token;
}

async function authFetch(path: string, init: RequestInit = {}) {
  const token = await accessToken();
  const headers = new Headers(init.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message = body.detail || body.error || message;
    } catch {}
    throw new Error(message);
  }
  const type = response.headers.get("content-type") || "";
  return type.includes("application/json") ? response.json() : response;
}

export const fetchV11Capabilities = () => authFetch("/api/v11/capabilities");
export const fetchV11Health = () => authFetch("/health/v11");
export const fetchV11Privacy = () => authFetch("/api/v11/privacy");
export const fetchV11Sandbox = () => authFetch("/api/v11/code/sandbox");

export function runV11Research(query: string, saveToKb = false) {
  return authFetch("/api/v11/research/plan-run", {
    method: "POST",
    body: JSON.stringify({ query, save_to_kb: saveToKb, title: query.slice(0, 100) }),
  });
}

export function runV11CodeAgent(instruction: string, files: Record<string, string>, testErrors = "") {
  return authFetch("/api/v11/code/agent", {
    method: "POST",
    body: JSON.stringify({
      instruction,
      files,
      max_repair_attempts: 3,
      test_errors: testErrors,
    }),
  });
}

export function generateV11Video(payload: Record<string, unknown>) {
  return authFetch("/api/v11/video/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function multimodalV11(prompt: string, files: File[]) {
  const form = new FormData();
  form.set("prompt", prompt);
  files.forEach((file) => form.append("files", file));
  return authFetch("/api/v11/multimodal", { method: "POST", body: form });
}


export function generateV11ConsistentImage(payload: {
  prompt: string;
  identity_lock?: string;
  style_reference?: string;
  pose?: string;
  composition?: string;
  reference_strength?: number;
  reference_image?: File | null;
}) {
  const form = new FormData();
  for (const [key, value] of Object.entries(payload)) {
    if (key === "reference_image") continue;
    form.set(key, String(value ?? ""));
  }
  if (payload.reference_image) form.set("reference_image", payload.reference_image);
  return authFetch("/api/v11/image/consistency", { method: "POST", body: form });
}

export function maskedEditV11(image: File, mask: Blob, prompt: string) {
  const form = new FormData();
  form.set("image", image);
  form.set("mask", new File([mask], "mask.png", { type: "image/png" }));
  form.set("prompt", prompt);
  return authFetch("/api/v11/image/masked-edit", { method: "POST", body: form });
}
