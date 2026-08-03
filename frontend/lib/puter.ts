import type { ChatMessage } from "@/lib/api";

type PuterAccount = {
  username?: string;
  email?: string;
  uuid?: string;
};

type PuterChatOptions = {
  model: string;
  systemContext: string;
  signal?: AbortSignal;
};

declare global {
  interface Window {
    puter?: {
      auth: {
        isSignedIn: () => boolean;
        signIn: () => Promise<PuterAccount>;
        getUser: () => Promise<PuterAccount>;
        signOut: () => void;
      };
      ai: {
        chat: (messages: unknown, options?: unknown) => Promise<unknown>;
        txt2img: (prompt: string, options?: unknown) => Promise<unknown>;
      };
    };
  }
}

function requirePuter() {
  if (!window.puter) {
    throw new Error(
      "Puter.js load nahi hua. Page refresh karke dobara try karein.",
    );
  }
  return window.puter;
}

export async function connectPuter(): Promise<PuterAccount> {
  const puter = requirePuter();
  if (!puter.auth.isSignedIn()) {
    return puter.auth.signIn();
  }
  return puter.auth.getUser();
}

function throwIfAborted(signal?: AbortSignal) {
  if (signal?.aborted) {
    throw new DOMException("Generation stopped.", "AbortError");
  }
}

export async function streamPuterChat(
  messages: ChatMessage[],
  options: PuterChatOptions,
  onToken: (token: string) => void,
) {
  const puter = requirePuter();
  if (!puter.auth.isSignedIn()) {
    throw new Error(
      "Puter account connect karein, phir Puter Pro model use karein.",
    );
  }

  throwIfAborted(options.signal);
  const input = [
    { role: "system", content: options.systemContext },
    ...messages.slice(-40),
  ];

  const response = await puter.ai.chat(input, {
    model: options.model,
    stream: true,
    compaction: true,
  });

  if (
    !response ||
    typeof (response as AsyncIterable<unknown>)[Symbol.asyncIterator] !==
      "function"
  ) {
    const candidate = response as {
      message?: { content?: string };
      content?: string;
    };
    const text =
      candidate?.message?.content ||
      candidate?.content ||
      String(response || "");
    if (text) onToken(text);
    return;
  }

  for await (const rawPart of response as AsyncIterable<unknown>) {
    throwIfAborted(options.signal);
    const part = rawPart as {
      type?: string;
      text?: string;
      message?: string;
    };
    if (part.type === "error") {
      throw new Error(part.message || "Puter provider failed.");
    }
    if (typeof part.text === "string" && part.text) {
      onToken(part.text);
    }
  }
}

function imageUrl(result: unknown) {
  if (typeof result === "string" && result.trim()) return result.trim();
  if (result instanceof HTMLImageElement && result.src) return result.src;
  const value = result as {
    src?: string;
    url?: string;
    image_url?: { url?: string };
  };
  return value?.src || value?.url || value?.image_url?.url || "";
}

export async function generatePuterImage4K(prompt: string) {
  const puter = requirePuter();
  if (!puter.auth.isSignedIn()) {
    throw new Error(
      "Puter account connect karein, phir Puter image generate karein.",
    );
  }

  try {
    const result = await puter.ai.txt2img(prompt, {
      model: "gemini-3-pro-image",
      quality: "4K",
      ratio: { w: 1, h: 1 },
    });
    const url = imageUrl(result);
    if (url) return { url, provider: "Puter Gemini 4K" };
  } catch {
    // Fallback below.
  }

  const fallback = await puter.ai.txt2img(prompt, {
    model: "gpt-image-1.5",
    quality: "high",
  });
  const url = imageUrl(fallback);
  if (!url) {
    throw new Error("Puter image provider returned an empty image.");
  }
  return { url, provider: "Puter GPT Image" };
}
