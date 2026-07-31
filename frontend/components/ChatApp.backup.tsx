"use client";

import { FormEvent, useRef, useState } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import { generateImage, sendChat, type ChatMessage } from "@/lib/api";

const starter: ChatMessage[] = [
  {
    role: "assistant",
    content:
      "नमस्ते Papa! मैं **Power Vasuki AI** हूँ। आप मुझसे latest research, coding, image generation और general questions पूछ सकते हैं।",
  },
];

/**
 * react-markdown blocks data: URLs by default. Our backend returns generated
 * images as base64 data URLs, so allow only common raster image formats.
 * SVG data URLs stay blocked for safety.
 */
function safeMarkdownUrlTransform(url: string): string {
  const normalizedUrl = url.trim();

  if (/^data:image\/(?:png|jpe?g|webp|gif);base64,/i.test(normalizedUrl)) {
    return normalizedUrl;
  }

  return defaultUrlTransform(normalizedUrl);
}

export default function ChatApp() {
  const [messages, setMessages] = useState<ChatMessage[]>(starter);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [web, setWeb] = useState(true);
  const [mode, setMode] = useState<"chat" | "image">("chat");
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || busy) return;

    setInput("");
    setError("");

    const next = [
      ...messages,
      { role: "user", content: text } as ChatMessage,
    ];

    setMessages(next);
    setBusy(true);

    try {
      if (mode === "image") {
        const data = await generateImage(text);
        const imageUrl =
          typeof data?.url === "string" ? data.url.trim() : "";

        if (!imageUrl) {
          throw new Error(
            "Image provider ne valid image URL return nahi kiya. Backend logs check karein.",
          );
        }

        const provider =
          typeof data?.provider === "string" && data.provider.trim()
            ? data.provider.trim()
            : "image provider";

        setMessages([
          ...next,
          {
            role: "assistant",
            content: `Image generated with **${provider}**:\n\n![Generated image](${imageUrl})`,
          },
        ]);
      } else {
        const data = await sendChat(next, web);
        let content = data.answer;

        if (data.sources?.length) {
          content +=
            "\n\n### Sources\n" +
            data.sources
              .map(
                (source: { title: string; url: string }, index: number) =>
                  `${index + 1}. [${source.title}](${source.url})`,
              )
              .join("\n");
        }

        setMessages([...next, { role: "assistant", content }]);
      }

      requestAnimationFrame(() =>
        endRef.current?.scrollIntoView({ behavior: "smooth" }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">⚡ Power Vasuki AI</div>
        <p>Multi-provider smart assistant</p>
        <button
          className={mode === "chat" ? "active" : ""}
          onClick={() => setMode("chat")}
        >
          💬 Chat & Research
        </button>
        <button
          className={mode === "image" ? "active" : ""}
          onClick={() => setMode("image")}
        >
          🎨 Image Generator
        </button>
        <div className="sideBottom">
          Created for Vasuki
          <br />
          by Lakhan Prajapat
        </div>
      </aside>

      <section className="workspace">
        <header>
          <div>
            <strong>{mode === "chat" ? "Power Chat" : "AI Image Studio"}</strong>
            <span>{busy ? "Thinking…" : "Online"}</span>
          </div>
          {mode === "chat" && (
            <label className="toggle">
              <input
                type="checkbox"
                checked={web}
                onChange={(event) => setWeb(event.target.checked)}
              />
              Live web research
            </label>
          )}
        </header>

        <div className="messages">
          {messages.map((message, index) => (
            <article key={index} className={`message ${message.role}`}>
              <div className="avatar">
                {message.role === "assistant" ? "V" : "U"}
              </div>
              <div className="bubble">
                <ReactMarkdown
                  urlTransform={safeMarkdownUrlTransform}
                  components={{
                    img({ src, alt, title }) {
                      if (typeof src !== "string" || !src.trim()) {
                        return null;
                      }

                      return (
                        <img
                          src={src}
                          alt={alt || "Generated image"}
                          title={title}
                          loading="lazy"
                        />
                      );
                    },
                  }}
                >
                  {message.content}
                </ReactMarkdown>
              </div>
            </article>
          ))}

          {busy && (
            <article className="message assistant">
              <div className="avatar">V</div>
              <div className="bubble typing">● ● ●</div>
            </article>
          )}
          <div ref={endRef} />
        </div>

        <form onSubmit={submit}>
          {error && <div className="error">{error}</div>}
          <div className="composer">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={
                mode === "chat"
                  ? "Power Vasuki AI से कुछ पूछें…"
                  : "अपनी image का detailed prompt लिखें…"
              }
              rows={2}
            />
            <button disabled={busy || !input.trim()} aria-label="Send">
              ➤
            </button>
          </div>
          <small>
            AI गलतियाँ कर सकता है। महत्वपूर्ण जानकारी verify करें। API keys केवल
            backend environment में रखें।
          </small>
        </form>
      </section>
    </main>
  );
}
