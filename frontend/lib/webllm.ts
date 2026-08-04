import type { ChatMessage } from "@/lib/api";

export type LocalChatProgress = {
  phase: "idle" | "loading" | "ready" | "generating" | "error";
  text: string;
  progress?: number;
  model?: string;
};

type LocalEngine = {
  chat: {
    completions: {
      create: (options: Record<string, unknown>) => Promise<unknown>;
    };
  };
  interruptGenerate?: () => void;
};

type ModelRecord = {
  model_id?: string;
  vram_required_MB?: number;
};

let engine: LocalEngine | null = null;
let engineModel = "";
let engineLoading: Promise<{
  engine: LocalEngine;
  model: string;
}> | null = null;

export function supportsWebLLM() {
  return (
    typeof window !== "undefined" &&
    typeof navigator !== "undefined" &&
    "gpu" in navigator
  );
}

async function hasShaderF16() {
  try {
    const gpu = (
      navigator as Navigator & {
        gpu?: {
          requestAdapter: () => Promise<{
            features?: { has: (name: string) => boolean };
          } | null>;
        };
      }
    ).gpu;
    const adapter = await gpu?.requestAdapter();
    return adapter?.features?.has("shader-f16") === true;
  } catch {
    return false;
  }
}

function scoreModel(
  record: ModelRecord,
  preferred: string[],
) {
  const id = record.model_id || "";
  const exactIndex = preferred.indexOf(id);
  if (exactIndex >= 0) return exactIndex;

  let score = 1000;
  if (/instruct/i.test(id)) score -= 300;
  if (/qwen/i.test(id)) score -= 80;
  if (/llama-3\.2-1b/i.test(id)) score -= 70;
  if (/0\.5b|0\.6b|1b|1\.5b/i.test(id)) score -= 100;
  if (/7b|8b|13b|14b|32b|70b/i.test(id)) score += 900;

  const vram = Number(record.vram_required_MB || 99999);
  score += Math.min(800, Math.round(vram / 10));
  return score;
}

async function chooseModel(
  records: ModelRecord[],
) {
  const f16 = await hasShaderF16();
  const memory = (
    navigator as Navigator & { deviceMemory?: number }
  ).deviceMemory || 4;

  const preferred = f16
    ? memory >= 6
      ? [
          "Qwen2.5-1.5B-Instruct-q4f16_1-MLC",
          "Llama-3.2-1B-Instruct-q4f16_1-MLC",
          "Qwen2.5-0.5B-Instruct-q4f16_1-MLC",
        ]
      : [
          "Llama-3.2-1B-Instruct-q4f16_1-MLC",
          "Qwen2.5-0.5B-Instruct-q4f16_1-MLC",
        ]
    : [
        "Llama-3.2-1B-Instruct-q4f32_1-MLC",
        "Qwen2.5-0.5B-Instruct-q4f32_1-MLC",
        "Llama-3.2-1B-Instruct-q4f16_1-MLC",
      ];

  const availableIds = new Set(
    records
      .map((record) => record.model_id)
      .filter((id): id is string => Boolean(id)),
  );

  for (const id of preferred) {
    if (availableIds.has(id)) return id;
  }

  const safe = records
    .filter((record) => {
      const id = record.model_id || "";
      const vram = Number(record.vram_required_MB || 99999);
      return (
        /instruct/i.test(id) &&
        !/7b|8b|13b|14b|32b|70b/i.test(id) &&
        vram <= (memory >= 8 ? 3600 : 2200)
      );
    })
    .sort(
      (a, b) =>
        scoreModel(a, preferred) - scoreModel(b, preferred),
    );

  const selected = safe[0]?.model_id;
  if (!selected) {
    throw new Error(
      "Is browser/device ke liye compatible local model nahi mila.",
    );
  }
  return selected;
}

async function loadEngine(
  onProgress: (progress: LocalChatProgress) => void,
) {
  if (engine && engineModel) {
    return { engine, model: engineModel };
  }

  if (engineLoading) return engineLoading;

  engineLoading = (async () => {
    if (!supportsWebLLM()) {
      throw new Error(
        "WebGPU supported browser/device required. Chrome ya Edge update karein.",
      );
    }

    const webllm = await import("@mlc-ai/web-llm");
    const records = (
      webllm.prebuiltAppConfig.model_list || []
    ) as ModelRecord[];
    const model = await chooseModel(records);

    onProgress({
      phase: "loading",
      text:
        "Local AI model pehli baar download ho raha hai. " +
        "Tab band na karein.",
      progress: 0,
      model,
    });

    const selectedEngine = (await webllm.CreateMLCEngine(
      model,
      {
        appConfig: {
          ...webllm.prebuiltAppConfig,
          cacheBackend: "indexeddb",
        },
        initProgressCallback: (report: unknown) => {
          const value = report as {
            text?: string;
            progress?: number;
          };
          const progress =
            typeof value.progress === "number"
              ? Math.max(0, Math.min(1, value.progress))
              : undefined;

          onProgress({
            phase: "loading",
            text:
              value.text ||
              "Local AI model download/load ho raha hai.",
            progress,
            model,
          });
        },
      },
    )) as unknown as LocalEngine;

    engine = selectedEngine;
    engineModel = model;

    onProgress({
      phase: "ready",
      text: "Local AI model ready hai.",
      progress: 1,
      model,
    });

    return { engine: selectedEngine, model };
  })();

  try {
    return await engineLoading;
  } catch (error) {
    engineLoading = null;
    engine = null;
    engineModel = "";
    throw error;
  }
}

function contentFromChunk(chunk: unknown) {
  if (!chunk || typeof chunk !== "object") return "";
  const value = chunk as {
    choices?: Array<{
      delta?: { content?: string };
      message?: { content?: string };
      text?: string;
    }>;
  };

  return (
    value.choices?.[0]?.delta?.content ||
    value.choices?.[0]?.message?.content ||
    value.choices?.[0]?.text ||
    ""
  );
}

export async function streamWebLLMChat(
  messages: ChatMessage[],
  options: {
    systemContext: string;
    signal?: AbortSignal;
    onProgress: (progress: LocalChatProgress) => void;
  },
  onToken: (token: string) => void,
) {
  const loaded = await loadEngine(options.onProgress);
  const localEngine = loaded.engine;

  const interrupt = () => {
    try {
      localEngine.interruptGenerate?.();
    } catch {
      // Best-effort interruption.
    }
  };

  options.signal?.addEventListener("abort", interrupt, {
    once: true,
  });

  try {
    options.onProgress({
      phase: "generating",
      text: "Vasuki Pro aapke device par answer bana raha hai.",
      progress: 1,
      model: loaded.model,
    });

    const response = await localEngine.chat.completions.create({
      messages: [
        {
          role: "system",
          content: options.systemContext,
        },
        ...messages.slice(-40),
      ],
      stream: true,
      temperature: 0.25,
      top_p: 0.9,
      max_tokens: 3072,
    });

    if (
      response &&
      typeof (response as AsyncIterable<unknown>)[
        Symbol.asyncIterator
      ] === "function"
    ) {
      for await (const chunk of response as AsyncIterable<unknown>) {
        if (options.signal?.aborted) {
          interrupt();
          throw new DOMException(
            "Generation stopped.",
            "AbortError",
          );
        }
        const token = contentFromChunk(chunk);
        if (token) onToken(token);
      }
    } else {
      const token = contentFromChunk(response);
      if (token) onToken(token);
    }

    options.onProgress({
      phase: "ready",
      text: "Local AI model ready hai.",
      progress: 1,
      model: loaded.model,
    });

    return { model: loaded.model };
  } catch (error) {
    options.onProgress({
      phase: "error",
      text:
        error instanceof Error
          ? error.message
          : "Local AI generation fail hui.",
      model: loaded.model,
    });
    throw error;
  } finally {
    options.signal?.removeEventListener("abort", interrupt);
  }
}

export async function resetWebLLM() {
  try {
    engine?.interruptGenerate?.();
  } catch {
    // Ignore.
  }
  engine = null;
  engineModel = "";
  engineLoading = null;
}
