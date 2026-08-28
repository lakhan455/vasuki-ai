import { supabase } from "@/lib/supabase";

const API = (process.env.NEXT_PUBLIC_API_BASE_URL || "/backend-api").replace(/\/$/, "");

async function authFetch(path: string, init: RequestInit = {}) {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error("Please sign in again.");
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
  return response.json();
}

export const fetchV48Tools = () => authFetch("/api/v48/tools");

export function analyzeV48Data(file: File) {
  const form = new FormData();
  form.set("file", file);
  return authFetch("/api/v48/data/analyze", { method: "POST", body: form });
}

export function uploadV48LibraryFile(file: File) {
  const form = new FormData();
  form.set("file", file);
  return authFetch("/api/v48/library/files", { method: "POST", body: form });
}

export const listV48LibraryFiles = () => authFetch("/api/v48/library/files");

export async function downloadV48LibraryFile(path: string) {
  const form = new FormData();
  form.set("path", path);
  return authFetch("/api/v48/library/download", { method: "POST", body: form });
}

export function deleteV48LibraryFile(path: string) {
  return authFetch(`/api/v48/library/files?path=${encodeURIComponent(path)}`, { method: "DELETE" });
}

export const listV48Tasks = () => authFetch("/api/v48/tasks");

export function createV48Task(payload: { title: string; prompt: string; run_at?: string; cron?: string }) {
  return authFetch("/api/v48/tasks", { method: "POST", body: JSON.stringify(payload) });
}

export function updateV48Task(taskId: string, payload: Record<string, unknown>) {
  return authFetch(`/api/v48/tasks/${encodeURIComponent(taskId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteV48Task(taskId: string) {
  return authFetch(`/api/v48/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
}
