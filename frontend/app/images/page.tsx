"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import {
  editImageStudio,
  enhanceImageStudio,
  fetchImageHistory,
  generateImageStudio,
  generateImageVariations,
  type GeneratedArtifact,
  type ImageStudioResult,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

const PRESETS = [
  ["none", "Auto"],
  ["photo", "Photo"],
  ["cinematic", "Cinematic"],
  ["product", "Product"],
  ["poster", "Poster"],
  ["logo", "Logo"],
  ["anime", "Anime"],
  ["3d", "3D"],
];

const RATIOS = [
  ["square", "1:1"],
  ["portrait", "4:5"],
  ["landscape", "16:9"],
  ["story", "9:16"],
  ["classic", "4:3"],
];

async function token() {
  const { data } = await supabase.auth.getSession();
  const value = data.session?.access_token;
  if (!value) throw new Error("Please sign in again.");
  return value;
}

export default function ImagesPage() {
  const [items, setItems] = useState<GeneratedArtifact[]>([]);
  const [results, setResults] = useState<ImageStudioResult[]>([]);
  const [prompt, setPrompt] = useState("");
  const [preset, setPreset] = useState("none");
  const [ratio, setRatio] = useState("square");
  const [variationCount, setVariationCount] = useState(4);
  const [editFile, setEditFile] = useState<File | null>(null);
  const [scale, setScale] = useState(2);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function loadHistory() {
    try {
      const accessToken = await token();
      setItems(await fetchImageHistory(accessToken));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load image history.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadHistory();
  }, []);

  const preview = useMemo(
    () => editFile ? URL.createObjectURL(editFile) : "",
    [editFile],
  );

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  function pickFile(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] || null;
    event.target.value = "";
    setEditFile(next);
    setError("");
  }

  async function runGenerate(variations = false) {
    if (!prompt.trim()) return setError("Write an image prompt first.");
    setBusy(variations ? "variations" : "generate");
    setError("");
    try {
      const accessToken = await token();
      if (variations) {
        const response = await generateImageVariations(
          accessToken,
          prompt.trim(),
          preset,
          ratio,
          variationCount,
        );
        setResults(response.items);
      } else {
        setResults([
          await generateImageStudio(accessToken, prompt.trim(), preset, ratio),
        ]);
      }
      await loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Image generation failed.");
    } finally {
      setBusy("");
    }
  }

  async function runEdit() {
    if (!editFile) return setError("Choose an image first.");
    if (!prompt.trim()) return setError("Write the edit instruction first.");
    setBusy("edit");
    setError("");
    try {
      const accessToken = await token();
      setResults([
        await editImageStudio(
          accessToken,
          editFile,
          prompt.trim(),
          preset,
          ratio,
        ),
      ]);
      await loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Image edit failed.");
    } finally {
      setBusy("");
    }
  }

  async function runEnhance() {
    if (!editFile) return setError("Choose an image first.");
    setBusy("enhance");
    setError("");
    try {
      const accessToken = await token();
      setResults([await enhanceImageStudio(accessToken, editFile, scale)]);
      await loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enhancement failed.");
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="pv-v9-studio-page">
      <header className="pv-v9-studio-head">
        <div>
          <p className="pv-v8-kicker">Vasuki AI V9 Phase 3</p>
          <h1>Image Studio</h1>
          <p>Presets, aspect ratios, variations, image editing and high-quality enhancement.</p>
        </div>
        <nav className="pv-v9-studio-nav">
          <a href="/documents">Document Intelligence</a>
          <a href="/">Back to chat</a>
        </nav>
      </header>

      <section className="pv-v9-studio-grid">
        <div className="pv-v9-control-card">
          <label>
            <span>Prompt / edit instruction</span>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              rows={5}
              placeholder="Example: Premium NFC business card product photo on a dark studio desk..."
            />
          </label>

          <div className="pv-v9-choice-row">
            <label>
              <span>Preset</span>
              <select value={preset} onChange={(event) => setPreset(event.target.value)}>
                {PRESETS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
              </select>
            </label>
            <label>
              <span>Aspect ratio</span>
              <select value={ratio} onChange={(event) => setRatio(event.target.value)}>
                {RATIOS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
              </select>
            </label>
            <label>
              <span>Variations</span>
              <select value={variationCount} onChange={(event) => setVariationCount(Number(event.target.value))}>
                {[2, 3, 4].map((count) => <option value={count} key={count}>{count}</option>)}
              </select>
            </label>
          </div>

          <div className="pv-v9-action-row">
            <button type="button" disabled={Boolean(busy)} onClick={() => void runGenerate(false)}>
              {busy === "generate" ? "Generating..." : "Generate"}
            </button>
            <button type="button" disabled={Boolean(busy)} onClick={() => void runGenerate(true)}>
              {busy === "variations" ? "Creating..." : "Create variations"}
            </button>
          </div>

          <div className="pv-v9-divider" />

          <label className="pv-v9-file-picker">
            <span>Edit / enhance an existing image</span>
            <input type="file" accept="image/*" onChange={pickFile} />
          </label>

          {preview ? (
            <div className="pv-v9-edit-preview"><img src={preview} alt="Selected image preview" /></div>
          ) : null}

          <div className="pv-v9-choice-row">
            <label>
              <span>Enhance scale</span>
              <select value={scale} onChange={(event) => setScale(Number(event.target.value))}>
                <option value={1.5}>1.5x</option>
                <option value={2}>2x</option>
                <option value={3}>3x</option>
                <option value={4}>4x</option>
              </select>
            </label>
          </div>

          <div className="pv-v9-action-row">
            <button type="button" disabled={Boolean(busy) || !editFile} onClick={() => void runEdit()}>
              {busy === "edit" ? "Editing..." : "Edit image"}
            </button>
            <button type="button" disabled={Boolean(busy) || !editFile} onClick={() => void runEnhance()}>
              {busy === "enhance" ? "Enhancing..." : "Enhance / upscale"}
            </button>
          </div>

          <p className="pv-v9-fineprint">
            Enhance/upscale uses local high-quality resampling and sharpening up to 4096 px long edge. It is not generative super-resolution.
          </p>
          {error ? <div className="pv-v8-error">{error}</div> : null}
        </div>

        <div className="pv-v9-results-card">
          <h2>Latest result</h2>
          {!results.length ? <div className="pv-v8-empty">Your generated or edited images will appear here.</div> : null}
          <div className="pv-v9-result-grid">
            {results.map((result, index) => (
              <article key={`${result.index ?? index}-${result.url ?? result.error ?? index}`}>
                {result.url ? <img src={result.url} alt={`Vasuki result ${index + 1}`} /> : null}
                {result.error ? <div className="pv-v8-error">{result.error}</div> : null}
                <div className="pv-v9-result-meta">
                  <strong>{result.operation || (result.index ? `Variation ${result.index}` : "Generated image")}</strong>
                  <small>
                    {[result.provider, result.preset, result.aspect_ratio, result.width && result.height ? `${result.width}x${result.height}` : ""]
                      .filter(Boolean)
                      .join(" · ")}
                  </small>
                  {result.url ? <a href={result.url} target="_blank" rel="noreferrer">Open image</a> : null}
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="pv-v9-history-card">
        <div className="pv-v9-section-title">
          <div><p className="pv-v8-kicker">Saved artifacts</p><h2>Image History</h2></div>
          <button type="button" onClick={() => void loadHistory()}>Refresh</button>
        </div>
        {loading && <p>Loading images...</p>}
        {!loading && !items.length && !error && <div className="pv-v8-empty">No generated images yet.</div>}
        <div className="pv-v8-image-grid">
          {items.map((item) => (
            <article className="pv-v8-image-card" key={item.id}>
              {item.download_url ? <img src={item.download_url} alt={item.name} loading="lazy" /> : <div className="pv-v8-image-placeholder">Image</div>}
              <div className="pv-v8-image-copy">
                <strong>{item.name}</strong>
                {item.prompt ? <p>{item.prompt}</p> : null}
                <small>{item.provider || "Vasuki image router"}</small>
                {item.download_url ? <a href={item.download_url} target="_blank" rel="noreferrer">Open image</a> : null}
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
