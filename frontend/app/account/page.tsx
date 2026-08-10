"use client";

import { useEffect, useMemo, useState } from "react";
import {
  cleanupStorageV9,
  deleteAccountV9,
  exportChatV9,
  exportFullAccountV9,
  fetchAccountChatsV9,
  fetchPushConfigV9,
  fetchStorageV9,
  subscribePushV9,
  unsubscribePushV9,
  type AccountChatV9,
  type PushConfigV9,
  type StorageSnapshotV9,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

async function token() {
  const { data } = await supabase.auth.getSession();
  const value = data.session?.access_token;
  if (!value) throw new Error("Please sign in again.");
  return value;
}

function bytes(value?: number) {
  const amount = Math.max(0, Number(value || 0));
  if (amount < 1024 * 1024) return `${Math.round(amount / 1024)} KB`;
  if (amount < 1024 * 1024 * 1024) return `${(amount / (1024 * 1024)).toFixed(1)} MB`;
  return `${(amount / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function downloadText(filename: string, mime: string, content: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || "vasuki-export.txt";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function base64UrlToUint8Array(value: string) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const normalized = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(normalized);
  return Uint8Array.from([...raw].map((char) => char.charCodeAt(0)));
}

export default function AccountPage() {
  const [chats, setChats] = useState<AccountChatV9[]>([]);
  const [storage, setStorage] = useState<StorageSnapshotV9 | null>(null);
  const [push, setPush] = useState<PushConfigV9 | null>(null);
  const [selectedChat, setSelectedChat] = useState("");
  const [format, setFormat] = useState<"markdown" | "json">("markdown");
  const [confirmEmail, setConfirmEmail] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    setError("");
    try {
      const accessToken = await token();
      const [{ data: session }, chatsData, storageData, pushData] = await Promise.all([
        supabase.auth.getSession(),
        fetchAccountChatsV9(accessToken),
        fetchStorageV9(accessToken),
        fetchPushConfigV9(accessToken),
      ]);
      setEmail(session.session?.user.email || "");
      setChats(chatsData.chats || []);
      setStorage(storageData);
      setPush(pushData);
      setSelectedChat((current) => current || chatsData.chats?.[0]?.id || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Account tools could not be loaded.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const storageWidth = useMemo(
    () => `${Math.max(0, Math.min(100, storage?.percent_used || 0))}%`,
    [storage?.percent_used],
  );

  async function exportOneChat() {
    if (!selectedChat) return;
    setBusy("chat");
    setError("");
    try {
      const accessToken = await token();
      const result = await exportChatV9(accessToken, selectedChat, format);
      downloadText(
        result.filename || `vasuki-chat.${format === "json" ? "json" : "md"}`,
        result.mime_type || "text/plain",
        result.content || "",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chat export failed.");
    } finally {
      setBusy("");
    }
  }

  async function exportEverything() {
    setBusy("full");
    setError("");
    try {
      const accessToken = await token();
      const result = await exportFullAccountV9(accessToken);
      downloadText(
        result.filename || "vasuki-ai-account-export.json",
        result.mime_type || "application/json",
        JSON.stringify(result.data || {}, null, 2),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Account export failed.");
    } finally {
      setBusy("");
    }
  }

  async function cleanup() {
    setBusy("cleanup");
    setError("");
    try {
      const accessToken = await token();
      await cleanupStorageV9(accessToken);
      setMessage("Expired generated files were cleaned up.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cleanup failed.");
    } finally {
      setBusy("");
    }
  }

  async function enablePush() {
    setBusy("push");
    setError("");
    setMessage("");
    try {
      if (!push?.configured || !push.public_key) {
        throw new Error("Browser push is not configured on the backend yet.");
      }
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
        throw new Error("This browser does not support Web Push.");
      }
      const permission = await Notification.requestPermission();
      if (permission !== "granted") throw new Error("Notification permission was not granted.");
      const registration = await navigator.serviceWorker.ready;
      const existing = await registration.pushManager.getSubscription();
      const subscription =
        existing ||
        await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: base64UrlToUint8Array(push.public_key),
        });
      const accessToken = await token();
      await subscribePushV9(accessToken, subscription.toJSON());
      setMessage("Browser notifications are enabled.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Push notifications could not be enabled.");
    } finally {
      setBusy("");
    }
  }

  async function disablePush() {
    setBusy("push");
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();
      if (subscription) {
        const accessToken = await token();
        await unsubscribePushV9(accessToken, subscription.endpoint);
        await subscription.unsubscribe();
      }
      setMessage("Browser notifications are disabled on this device.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Push notifications could not be disabled.");
    } finally {
      setBusy("");
    }
  }

  async function removeAccount() {
    if (!window.confirm("This permanently deletes your Vasuki AI account and user data. Continue?")) return;
    setBusy("delete");
    setError("");
    try {
      const accessToken = await token();
      await deleteAccountV9(accessToken, confirmEmail, confirmation);
      await supabase.auth.signOut();
      window.location.assign("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Account deletion failed.");
      setBusy("");
    }
  }

  return (
    <main className="pv-v9-account-page">
      <header className="pv-v9-account-head">
        <div>
          <p className="pv-v8-kicker">V9 Phase 5</p>
          <h1>Account, Privacy & Storage</h1>
          <p>Export your data, manage storage and browser notifications, or permanently delete your account.</p>
        </div>
        <nav>
          <a href="/">Back to chat</a>
          <a href="/operations">Operations</a>
        </nav>
      </header>

      {error ? <div className="pv-v8-error pv-v9-account-alert" role="alert">{error}</div> : null}
      {message ? <div className="pv-v9-account-success" role="status">{message}</div> : null}

      <section className="pv-v9-account-grid">
        <article className="pv-v9-account-card">
          <p className="pv-v8-kicker">Export</p>
          <h2>Chat export</h2>
          <label>
            <span>Chat</span>
            <select value={selectedChat} onChange={(event) => setSelectedChat(event.target.value)}>
              {!chats.length ? <option value="">No saved chats</option> : null}
              {chats.map((chat) => (
                <option value={chat.id} key={chat.id}>
                  {chat.title || "Untitled chat"}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Format</span>
            <select value={format} onChange={(event) => setFormat(event.target.value as "markdown" | "json")}>
              <option value="markdown">Markdown</option>
              <option value="json">JSON</option>
            </select>
          </label>
          <button type="button" disabled={!selectedChat || busy === "chat"} onClick={() => void exportOneChat()}>
            {busy === "chat" ? "Preparing..." : "Download chat"}
          </button>

          <div className="pv-v9-account-divider" />
          <h2>Full account export</h2>
          <p>Downloads a JSON package of your Vasuki AI account data. Derived embeddings and secret-like fields are excluded.</p>
          <button type="button" disabled={busy === "full"} onClick={() => void exportEverything()}>
            {busy === "full" ? "Preparing export..." : "Download full account export"}
          </button>
        </article>

        <article className="pv-v9-account-card">
          <p className="pv-v8-kicker">Quota</p>
          <h2>Storage</h2>
          <div className="pv-v9-storage-numbers">
            <strong>{bytes(storage?.used_bytes)}</strong>
            <span>of {bytes(storage?.quota_bytes)} · {storage?.plan || "-"} plan</span>
          </div>
          <div className="pv-v9-storage-bar" aria-label={`${storage?.percent_used || 0}% storage used`}>
            <span style={{ width: storageWidth }} />
          </div>
          <dl>
            <div><dt>Generated files</dt><dd>{bytes(storage?.breakdown?.generated_artifacts)}</dd></div>
            <div><dt>Knowledge documents</dt><dd>{bytes(storage?.breakdown?.knowledge_documents)}</dd></div>
            <div><dt>Project files</dt><dd>{bytes(storage?.breakdown?.project_files)}</dd></div>
          </dl>
          <button type="button" disabled={busy === "cleanup"} onClick={() => void cleanup()}>
            {busy === "cleanup" ? "Cleaning..." : "Clean expired generated files"}
          </button>
          <p className="pv-v9-account-note">Expired artifacts are also cleaned automatically by backend maintenance.</p>
        </article>

        <article className="pv-v9-account-card">
          <p className="pv-v8-kicker">PWA</p>
          <h2>Browser notifications</h2>
          <p>
            Vasuki AI can notify this device when supported background work finishes.
            {!push?.configured ? " Backend VAPID keys still need to be configured." : ""}
          </p>
          <div className="pv-v9-account-actions">
            <button type="button" disabled={busy === "push" || !push?.configured} onClick={() => void enablePush()}>
              Enable notifications
            </button>
            <button type="button" disabled={busy === "push"} onClick={() => void disablePush()}>
              Disable on this device
            </button>
          </div>
          <p className="pv-v9-account-note">The installable PWA and cached offline shell are registered automatically in supported browsers.</p>
        </article>

        <article className="pv-v9-account-card pv-v9-danger-card">
          <p className="pv-v8-kicker">Danger zone</p>
          <h2>Delete account</h2>
          <p>This permanently deletes your authentication account and user-scoped Vasuki AI data. Owner accounts are protected from self-service deletion.</p>
          <label>
            <span>Confirm email ({email || "your account email"})</span>
            <input value={confirmEmail} onChange={(event) => setConfirmEmail(event.target.value)} />
          </label>
          <label>
            <span>Type DELETE MY ACCOUNT</span>
            <input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
          </label>
          <button
            type="button"
            disabled={busy === "delete" || confirmation !== "DELETE MY ACCOUNT" || confirmEmail.trim().toLowerCase() !== email.trim().toLowerCase()}
            onClick={() => void removeAccount()}
          >
            {busy === "delete" ? "Deleting..." : "Permanently delete account"}
          </button>
        </article>
      </section>
    </main>
  );
}
