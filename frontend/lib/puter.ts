import type { ChatMessage } from "@/lib/api";

type PuterAccount = {
  username?: string;
  email?: string;
  uuid?: string;
};

type PuterModel = {
  id?: string;
  aliases?: string[];
};

type PuterChatOptions = {
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
        listModels?: () => Promise<PuterModel[]>;
      };
    };
  }
}

function requirePuter() {
  if (!window.puter) {
    throw new Error(
      "Vasuki Pro failed to load. Refresh the page and try again.",
    );
  }
  return window.puter;
}

function readableError(error: unknown) {
  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }

  if (typeof error === "string" && error.trim()) {
    return error.trim();
  }

  if (error && typeof error === "object") {
    const value = error as Record<string, unknown>;
    const nested =
      value.error && typeof value.error === "object"
        ? (value.error as Record<string, unknown>)
        : null;

    for (const candidate of [
      value.msg,
      value.message,
      value.error_description,
      nested?.msg,
      nested?.message,
      typeof value.error === "string" ? value.error : undefined,
      value.code,
    ]) {
      if (typeof candidate === "string" && candidate.trim()) {
        return candidate.trim();
      }
    }
  }

  return (
    "Vasuki Pro request failed. Check your Puter login and account allowance, " +
    "then try again."
  );
}

export async function connectPuter(): Promise<PuterAccount> {
  const puter = requirePuter();

  try {
    if (!puter.auth.isSignedIn()) {
      return await puter.auth.signIn();
    }
    return await puter.auth.getUser();
  } catch (error) {
    throw new Error(readableError(error));
  }
}

function throwIfAborted(signal?: AbortSignal) {
  if (signal?.aborted) {
    throw new DOMException("Generation stopped.", "AbortError");
  }
}

function looksLikeCoding(messages: ChatMessage[]) {
  const prompt = messages
    .slice(-3)
    .map((message) => message.content)
    .join(" ")
    .toLowerCase();

  return /code|coding|html|css|javascript|typescript|python|java|flutter|react|next\.?js|fastapi|api|sql|debug|error|website|app|backend|frontend|github|powershell|program/i.test(
    prompt,
  );
}

async function availableModels() {
  const puter = requirePuter();
  if (!puter.ai.listModels) return new Set<string>();

  try {
    const models = await puter.ai.listModels();
    const values = new Set<string>();

    for (const model of models || []) {
      if (typeof model.id === "string") values.add(model.id);
      for (const alias of model.aliases || []) {
        if (typeof alias === "string") values.add(alias);
      }
    }

    return values;
  } catch {
    return new Set<string>();
  }
}

function chooseCandidates(
  coding: boolean,
  available: Set<string>,
): Array<string | undefined> {
  const preferred = coding
    ? [
        "claude-sonnet-4-6",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
      ]
    : [
        "gpt-5.4-nano",
        "gemini-3.1-flash-lite",
        "gpt-5.4-mini",
      ];

  const supported =
    available.size > 0
      ? preferred.filter((model) => available.has(model))
      : preferred;

  // undefined means use Puter's current default model.
  return [...new Set([...supported, undefined])];
}

function availabilityError(message: string) {
  return /model|provider|not found|unsupported|unavailable|overloaded|temporar|404|429|503/i.test(
    message,
  );
}

async function consumeChatResponse(
  response: unknown,
  signal: AbortSignal | undefined,
  onToken: (token: string) => void,
) {
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
    throwIfAborted(signal);

    const part = rawPart as {
      type?: string;
      text?: string;
      message?: string;
      error?: unknown;
    };

    if (part.type === "error" || part.error) {
      throw new Error(
        readableError(part.error || part.message || part),
      );
    }

    if (typeof part.text === "string" && part.text) {
      onToken(part.text);
    }
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
      "Connect your Puter account to use Vasuki Pro.",
    );
  }

  throwIfAborted(options.signal);

  const input = [
    { role: "system", content: options.systemContext },
    ...messages.slice(-50),
  ];

  const models = chooseCandidates(
    looksLikeCoding(messages),
    await availableModels(),
  );
  let lastError = "";

  for (const model of models) {
    try {
      const chatOptions: Record<string, unknown> = {
        stream: true,
        compaction: true,
      };
      if (model) chatOptions.model = model;

      const response = await puter.ai.chat(input, chatOptions);
      await consumeChatResponse(
        response,
        options.signal,
        onToken,
      );
      return model || "puter-default";
    } catch (error) {
      throwIfAborted(options.signal);
      const message = readableError(error);
      lastError = message;

      if (!availabilityError(message)) {
        throw new Error(message);
      }
    }
  }

  throw new Error(
    lastError ||
      "No Vasuki Pro AI provider returned a response. Please try again.",
  );
}

function imageUrl(result: unknown) {
  if (typeof result === "string" && result.trim()) {
    return result.trim();
  }

  if (result instanceof HTMLImageElement && result.src) {
    return result.src;
  }

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
      "Connect your Puter account to generate images with Vasuki Pro.",
    );
  }

  let firstError = "";

  try {
    const result = await puter.ai.txt2img(prompt, {
      provider: "gemini",
      quality: "4K",
      ratio: { w: 1, h: 1 },
    });
    const url = imageUrl(result);
    if (url) {
      return { url, provider: "Vasuki Pro · Gemini 4K" };
    }
  } catch (error) {
    firstError = readableError(error);
  }

  try {
    const fallback = await puter.ai.txt2img(prompt, {
      provider: "openai-image-generation",
      model: "gpt-image-2",
      quality: "high",
      ratio: { w: 1, h: 1 },
    });
    const url = imageUrl(fallback);

    if (!url) {
      throw new Error("Image provider returned an empty image.");
    }

    return { url, provider: "Vasuki Pro · GPT Image" };
  } catch (error) {
    throw new Error(
      readableError(error) ||
        firstError ||
        "Vasuki Pro image generation failed.",
    );
  }
}
