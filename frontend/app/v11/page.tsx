"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import {
  fetchV11Capabilities,
  fetchV11Health,
  fetchV11Privacy,
  generateV11ConsistentImage,
  generateV11Video,
  maskedEditV11,
  multimodalV11,
  runV11CodeAgent,
  runV11Research,
} from "@/lib/v11";
import { v11Locale, v11t } from "@/lib/i18n-v11";
import "./v11.css";

type Tab = "overview" | "voice" | "sandbox" | "research" | "code" | "image" | "video" | "multimodal" | "privacy";

type SpeechRecognitionResultEventLike = {
  results?: {
    [index: number]: {
      [index: number]: { transcript?: string };
    };
  };
};

type SpeechRecognitionErrorEventLike = { error?: string };

type SpeechRecognitionInstance = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionResultEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
};

type SpeechRecognitionCtor = new () => SpeechRecognitionInstance;

type V11Capabilities = {
  omniroute?: {
    embedded_knowledge?: string;
    native_provider_count?: number;
    native_provider_total?: number;
    sidecar?: string;
    mcp?: string;
    a2a?: string;
  };
};

type V11Health = {
  slo?: {
    p50_latency_ms?: number | null;
    p95_latency_ms?: number | null;
    p95_first_token_ms?: number | null;
    success_pct?: number | null;
    fallback_pct?: number | null;
  };
};

type MaskEditResult = { url?: string };



function pretty(value: unknown) {
  return JSON.stringify(value, null, 2);
}

export default function V11Page() {
  const [tab, setTab] = useState<Tab>("overview");
  const [locale, setLocale] = useState<ReturnType<typeof v11Locale>>("en");
  const [capabilities, setCapabilities] = useState<V11Capabilities | null>(null);
  const [health, setHealth] = useState<V11Health | null>(null);
  const [privacy, setPrivacy] = useState<unknown>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const [voicePrompt, setVoicePrompt] = useState("");
  const [voiceAnswer, setVoiceAnswer] = useState("");
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);

  const [htmlCode, setHtmlCode] = useState(`<main>
  <h1>Vasuki V11 Sandbox</h1>
  <button onclick="document.querySelector('h1').textContent='Working!'">Test</button>
</main>`);
  const [pythonCode, setPythonCode] = useState(`print("Vasuki V11 Python sandbox ready")`);
  const [pythonOutput, setPythonOutput] = useState("");
  const [sandboxLang, setSandboxLang] = useState<"html" | "python">("html");

  const [researchQuery, setResearchQuery] = useState("");
  const [researchResult, setResearchResult] = useState<unknown>(null);

  const [codeInstruction, setCodeInstruction] = useState("");
  const [codeSnapshot, setCodeSnapshot] = useState(`{"app.py":"def add(a,b):\\n    return a+b\\n"}`);
  const [codeResult, setCodeResult] = useState<unknown>(null);

  const [imagePrompt, setImagePrompt] = useState("");
  const [imageIdentity, setImageIdentity] = useState("");
  const [imageStyle, setImageStyle] = useState("");
  const [imagePose, setImagePose] = useState("");
  const [imageComposition, setImageComposition] = useState("");
  const [imageStrength, setImageStrength] = useState(0.75);
  const [imageReference, setImageReference] = useState<File | null>(null);
  const [imageResult, setImageResult] = useState<unknown>(null);
  const [maskFile, setMaskFile] = useState<File | null>(null);
  const [maskPrompt, setMaskPrompt] = useState("");
  const [maskResult, setMaskResult] = useState<MaskEditResult | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const maskCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawingRef = useRef(false);

  const [videoPrompt, setVideoPrompt] = useState("");
  const [videoResult, setVideoResult] = useState<unknown>(null);

  const [multiPrompt, setMultiPrompt] = useState("");
  const [multiFiles, setMultiFiles] = useState<File[]>([]);
  const [multiResult, setMultiResult] = useState<unknown>(null);

  useEffect(() => {
    setLocale(v11Locale(navigator.language));
    const params = new URLSearchParams(window.location.search);
    const shared = [params.get("title"), params.get("text"), params.get("url")].filter(Boolean).join("\n");
    if (shared) {
      setMultiPrompt(shared);
      setTab("multimodal");
    }
    void Promise.all([fetchV11Capabilities(), fetchV11Health()])
      .then(([caps, liveHealth]) => {
        setCapabilities(caps.capabilities);
        setHealth(liveHealth);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  async function askVoice(text = voicePrompt) {
    if (!text.trim()) return;
    setBusy("voice");
    setError("");
    try {
      const result = await multimodalV11(text.trim(), []);
      setVoiceAnswer(result.answer || "");
      if ("speechSynthesis" in window && result.answer) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(result.answer);
        utterance.lang = navigator.language || "en-IN";
        window.speechSynthesis.speak(utterance);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  }

  function toggleListening() {
    if (listening) {
      recognitionRef.current?.stop?.();
      setListening(false);
      return;
    }
    const Ctor = (window.SpeechRecognition as unknown as SpeechRecognitionCtor | undefined) || (window as typeof window & { webkitSpeechRecognition?: SpeechRecognitionCtor }).webkitSpeechRecognition;
    if (!Ctor) {
      setError("Speech recognition is not supported in this browser. Use Chrome or Edge.");
      return;
    }
    const recognition = new Ctor();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = navigator.language || "en-IN";
    recognition.onresult = (event: SpeechRecognitionResultEventLike) => {
      const text = String(event.results?.[0]?.[0]?.transcript || "").trim();
      setVoicePrompt(text);
      if (text) void askVoice(text);
    };
    recognition.onerror = (event: SpeechRecognitionErrorEventLike) => {
      setError(`Microphone error: ${event.error || "unknown"}`);
      setListening(false);
    };
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    setListening(true);
    recognition.start();
  }

  const srcDoc = useMemo(
    () => `<!doctype html><html><head><meta charset="utf-8"><style>
body{font-family:system-ui;padding:24px;background:#fff;color:#111}button{padding:10px 14px}
</style></head><body>${htmlCode}<script>window.onerror=(m)=>document.body.insertAdjacentHTML('beforeend','<pre>'+m+'</pre>')</script></body></html>`,
    [htmlCode],
  );

  async function runPython() {
    setBusy("python");
    setPythonOutput("Loading isolated Pyodide worker...");
    setError("");
    const workerSource = `
self.onmessage = async (event) => {
  try {
    importScripts("https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.js");
    const pyodide = await loadPyodide();
    let output = [];
    pyodide.setStdout({ batched: (s) => output.push(s) });
    pyodide.setStderr({ batched: (s) => output.push(s) });
    const result = await pyodide.runPythonAsync(event.data.code);
    self.postMessage({ ok: true, output: output.join("\\n") + (result === undefined ? "" : "\\n" + String(result)) });
  } catch (error) {
    self.postMessage({ ok: false, output: String(error?.stack || error) });
  }
};`;
    const blob = new Blob([workerSource], { type: "text/javascript" });
    const worker = new Worker(URL.createObjectURL(blob));
    const timer = window.setTimeout(() => {
      worker.terminate();
      setPythonOutput("Execution stopped after 10 seconds.");
      setBusy("");
    }, 10000);
    worker.onmessage = (event) => {
      window.clearTimeout(timer);
      worker.terminate();
      setPythonOutput(event.data.output || "(no output)");
      setBusy("");
    };
    worker.postMessage({ code: pythonCode });
  }

  async function doResearch() {
    if (!researchQuery.trim()) return;
    setBusy("research");
    setError("");
    try {
      setResearchResult(await runV11Research(researchQuery.trim(), true));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  }

  async function doCode() {
    setBusy("code");
    setError("");
    try {
      const files = JSON.parse(codeSnapshot);
      setCodeResult(await runV11CodeAgent(codeInstruction, files));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  }

  async function doConsistentImage() {
    setBusy("image");
    setError("");
    try {
      setImageResult(await generateV11ConsistentImage({
        prompt: imagePrompt,
        identity_lock: imageIdentity,
        style_reference: imageStyle,
        pose: imagePose,
        composition: imageComposition,
        reference_strength: imageStrength,
        reference_image: imageReference,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  }

  async function loadMaskImage(file: File | null) {
    setMaskFile(file);
    setMaskResult(null);
    if (!file) return;
    const bitmap = await createImageBitmap(file);
    const canvas = canvasRef.current;
    if (!canvas) return;
    const max = 720;
    const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext("2d");
    ctx?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const mask = document.createElement("canvas");
    mask.width = canvas.width;
    mask.height = canvas.height;
    const mctx = mask.getContext("2d");
    if (mctx) {
      mctx.fillStyle = "black";
      mctx.fillRect(0, 0, mask.width, mask.height);
    }
    maskCanvasRef.current = mask;
  }

  function paintMask(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return;
    const canvas = canvasRef.current;
    const mask = maskCanvasRef.current;
    if (!canvas || !mask) return;
    const rect = canvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) * (canvas.width / rect.width);
    const y = (event.clientY - rect.top) * (canvas.height / rect.height);
    const radius = Math.max(8, canvas.width * 0.025);
    const ctx = canvas.getContext("2d");
    const mctx = mask.getContext("2d");
    if (!ctx || !mctx) return;
    ctx.fillStyle = "rgba(255,80,80,.45)";
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
    mctx.fillStyle = "white";
    mctx.beginPath();
    mctx.arc(x, y, radius, 0, Math.PI * 2);
    mctx.fill();
  }

  async function doMaskedEdit() {
    if (!maskFile || !maskCanvasRef.current || !maskPrompt.trim()) return;
    setBusy("mask");
    setError("");
    try {
      const maskBlob = await new Promise<Blob>((resolve, reject) =>
        maskCanvasRef.current!.toBlob((blob) => blob ? resolve(blob) : reject(new Error("Mask could not be created.")), "image/png")
      );
      setMaskResult(await maskedEditV11(maskFile, maskBlob, maskPrompt.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  }

  async function doVideo() {
    setBusy("video");
    setError("");
    try {
      setVideoResult(
        await generateV11Video({
          prompt: videoPrompt,
          duration_seconds: 6,
          aspect_ratio: "16:9",
          camera: "cinematic",
          identity_lock: "",
          style_reference: "",
          pose: "",
          composition: "",
          reference_strength: 0.75,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  }

  async function doMultimodal() {
    setBusy("multi");
    setError("");
    try {
      setMultiResult(await multimodalV11(multiPrompt, multiFiles));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  }

  async function loadPrivacy() {
    setBusy("privacy");
    try {
      setPrivacy(await fetchV11Privacy());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  }

  const tabs: Array<[Tab, string]> = [
    ["overview", v11t(locale, "overview")],
    ["voice", v11t(locale, "voice")],
    ["sandbox", v11t(locale, "sandbox")],
    ["research", v11t(locale, "research")],
    ["code", v11t(locale, "code")],
    ["image", "Image Controls"],
    ["video", v11t(locale, "video")],
    ["multimodal", v11t(locale, "multimodal")],
    ["privacy", v11t(locale, "privacy")],
  ];

  return (
    <main className="v11-shell">
      <header className="v11-head">
        <div>
          <p>Vasuki AI V11</p>
          <h1>{v11t(locale, "title")}</h1>
          <small>No extra sidebar menu is required. This page reads live capabilities from the backend.</small>
        </div>
        <a href="/">Back to chat</a>
      </header>

      <nav className="v11-tabs">
        {tabs.map(([value, label]) => (
          <button key={value} className={tab === value ? "active" : ""} onClick={() => setTab(value)}>
            {label}
          </button>
        ))}
      </nav>

      {error ? <div className="v11-error">{error}</div> : null}

      {tab === "overview" ? (
        <section className="v11-card">
          <h2>Runtime Capability Registry</h2>
          {!capabilities ? <p>Loading capabilities...</p> : (
            <>
              <div className="v11-status-grid">
                <article><strong>Embedded Knowledge</strong><span>{capabilities.omniroute?.embedded_knowledge}</span></article>
                <article><strong>Native Vasuki Providers</strong><span>{capabilities.omniroute?.native_provider_count}/{capabilities.omniroute?.native_provider_total}</span></article>
                <article><strong>OmniRoute Sidecar</strong><span>{capabilities.omniroute?.sidecar}</span></article>
                <article><strong>MCP</strong><span>{capabilities.omniroute?.mcp}</span></article>
                <article><strong>A2A</strong><span>{capabilities.omniroute?.a2a}</span></article>
              </div>
              <h3>Reliability SLO</h3>
              <div className="v11-status-grid">
                <article><strong>p50 latency</strong><span>{health?.slo?.p50_latency_ms ?? "-"} ms</span></article>
                <article><strong>p95 latency</strong><span>{health?.slo?.p95_latency_ms ?? "-"} ms</span></article>
                <article><strong>p95 first token</strong><span>{health?.slo?.p95_first_token_ms ?? "-"} ms</span></article>
                <article><strong>Success</strong><span>{health?.slo?.success_pct ?? "-"}%</span></article>
                <article><strong>Fallback</strong><span>{health?.slo?.fallback_pct ?? "-"}%</span></article>
              </div>
              <pre>{pretty(capabilities)}</pre>
            </>
          )}
        </section>
      ) : null}

      {tab === "voice" ? (
        <section className="v11-card">
          <h2>Speech-to-Speech</h2>
          <textarea value={voicePrompt} onChange={(e) => setVoicePrompt(e.target.value)} placeholder="Speak or type a question" />
          <div className="v11-actions">
            <button onClick={toggleListening}>{listening ? "Stop microphone" : "Start microphone"}</button>
            <button disabled={busy === "voice"} onClick={() => void askVoice()}>{busy === "voice" ? "Thinking..." : "Ask and speak answer"}</button>
          </div>
          {voiceAnswer ? <div className="v11-answer">{voiceAnswer}</div> : null}
        </section>
      ) : null}

      {tab === "sandbox" ? (
        <section className="v11-card">
          <h2>Safe Browser Code Sandbox</h2>
          <div className="v11-actions">
            <button onClick={() => setSandboxLang("html")}>HTML/JS</button>
            <button onClick={() => setSandboxLang("python")}>Python</button>
          </div>
          {sandboxLang === "html" ? (
            <div className="v11-split">
              <textarea value={htmlCode} onChange={(e) => setHtmlCode(e.target.value)} />
              <iframe title="V11 sandbox preview" sandbox="allow-scripts" srcDoc={srcDoc} />
            </div>
          ) : (
            <div className="v11-split">
              <textarea value={pythonCode} onChange={(e) => setPythonCode(e.target.value)} />
              <div>
                <button disabled={busy === "python"} onClick={() => void runPython()}>Run Python isolated</button>
                <pre>{pythonOutput}</pre>
              </div>
            </div>
          )}
        </section>
      ) : null}

      {tab === "research" ? (
        <section className="v11-card">
          <h2>Research Planner V3</h2>
          <textarea value={researchQuery} onChange={(e) => setResearchQuery(e.target.value)} placeholder="Difficult research question" />
          <button disabled={busy === "research"} onClick={() => void doResearch()}>{busy === "research" ? "Planning + searching..." : "Run research"}</button>
          {researchResult ? <pre>{pretty(researchResult)}</pre> : null}
        </section>
      ) : null}

      {tab === "code" ? (
        <section className="v11-card">
          <h2>Autonomous Coding Agent V2</h2>
          <textarea value={codeInstruction} onChange={(e) => setCodeInstruction(e.target.value)} placeholder="What should change?" />
          <label>Project snapshot JSON: path -> complete file content</label>
          <textarea className="tall" value={codeSnapshot} onChange={(e) => setCodeSnapshot(e.target.value)} />
          <button disabled={busy === "code"} onClick={() => void doCode()}>{busy === "code" ? "Analyze -> plan -> patch -> repair..." : "Run coding loop"}</button>
          {codeResult ? <pre>{pretty(codeResult)}</pre> : null}
        </section>
      ) : null}

      {tab === "image" ? (
        <section className="v11-card">
          <h2>Image Consistency + Reference Controls</h2>
          <textarea value={imagePrompt} onChange={(e) => setImagePrompt(e.target.value)} placeholder="Image prompt" />
          <div className="v11-grid2">
            <input value={imageIdentity} onChange={(e) => setImageIdentity(e.target.value)} placeholder="Identity / product / logo lock description" />
            <input value={imageStyle} onChange={(e) => setImageStyle(e.target.value)} placeholder="Style reference" />
            <input value={imagePose} onChange={(e) => setImagePose(e.target.value)} placeholder="Pose" />
            <input value={imageComposition} onChange={(e) => setImageComposition(e.target.value)} placeholder="Composition" />
          </div>
          <label>Optional reference image</label>
          <input type="file" accept="image/*" onChange={(e) => setImageReference(e.target.files?.[0] || null)} />
          <label>Reference strength: {imageStrength.toFixed(2)}</label>
          <input type="range" min="0" max="1" step="0.05" value={imageStrength} onChange={(e) => setImageStrength(Number(e.target.value))} />
          <button disabled={busy === "image"} onClick={() => void doConsistentImage()}>{busy === "image" ? "Generating..." : "Generate consistent image"}</button>
          {imageResult ? <pre>{pretty(imageResult)}</pre> : null}

          <div className="v11-divider" />
          <h2>Mask / Brush Edit</h2>
          <input type="file" accept="image/*" onChange={(e) => void loadMaskImage(e.target.files?.[0] || null)} />
          <p className="v11-note">Brush over the exact area to change. Red overlay = editable mask.</p>
          <canvas
            ref={canvasRef}
            className="v11-mask-canvas"
            onPointerDown={(e) => { drawingRef.current = true; e.currentTarget.setPointerCapture(e.pointerId); paintMask(e); }}
            onPointerMove={paintMask}
            onPointerUp={() => { drawingRef.current = false; }}
            onPointerCancel={() => { drawingRef.current = false; }}
          />
          <textarea value={maskPrompt} onChange={(e) => setMaskPrompt(e.target.value)} placeholder="Replace/remove/edit the brushed area..." />
          <button disabled={busy === "mask" || !maskFile} onClick={() => void doMaskedEdit()}>{busy === "mask" ? "Editing masked area..." : "Apply masked edit"}</button>
          {maskResult?.url ? <img className="v11-result-image" src={maskResult.url} alt="Masked edit result" /> : null}
        </section>
      ) : null}

      {tab === "video" ? (
        <section className="v11-card">
          <h2>Text / Image -> Video Provider Gateway</h2>
          <textarea value={videoPrompt} onChange={(e) => setVideoPrompt(e.target.value)} placeholder="Cinematic video prompt" />
          <button disabled={busy === "video"} onClick={() => void doVideo()}>{busy === "video" ? "Generating..." : "Generate video"}</button>
          <p className="v11-note">This activates only when the backend has an OpenAI-compatible video provider configured.</p>
          {videoResult ? <pre>{pretty(videoResult)}</pre> : null}
        </section>
      ) : null}

      {tab === "multimodal" ? (
        <section className="v11-card">
          <h2>Multimodal Request</h2>
          <textarea value={multiPrompt} onChange={(e) => setMultiPrompt(e.target.value)} placeholder="Ask across all selected files" />
          <input type="file" multiple accept="image/*,audio/*,.pdf,.docx,.txt,.md,.json,.csv" onChange={(e) => setMultiFiles(Array.from(e.target.files || []))} />
          <button disabled={busy === "multi"} onClick={() => void doMultimodal()}>{busy === "multi" ? "Reasoning..." : "Analyze together"}</button>
          {multiResult ? <pre>{pretty(multiResult)}</pre> : null}
        </section>
      ) : null}

      {tab === "privacy" ? (
        <section className="v11-card">
          <h2>Privacy Center</h2>
          <button disabled={busy === "privacy"} onClick={() => void loadPrivacy()}>Load my stored V11 data</button>
          {privacy ? <pre>{pretty(privacy)}</pre> : null}
        </section>
      ) : null}
    </main>
  );
}
