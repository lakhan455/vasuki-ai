"use client";

import { useEffect, useState } from "react";
import {
  fetchConnectionsV65,
  fetchMultimodalCapabilitiesV66,
  type ConnectorV65,
  type MultimodalCapabilitiesV66,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

async function token() {
  const { data } = await supabase.auth.getSession();
  const value = data.session?.access_token;
  if (!value) throw new Error("Please sign in again.");
  return value;
}

function stateLabel(value: string) {
  if (value === "connected") return "Connected";
  if (value === "needs_configuration") return "Needs backend setup";
  if (value === "connection_backend_required") return "Connection backend required";
  return value.replace(/_/g, " ");
}

export default function ConnectionsPage() {
  const [connectors, setConnectors] = useState<ConnectorV65[]>([]);
  const [multimodal, setMultimodal] =
    useState<MultimodalCapabilitiesV66 | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const accessToken = await token();
        const [connectionData, multimodalData] = await Promise.all([
          fetchConnectionsV65(accessToken),
          fetchMultimodalCapabilitiesV66(accessToken),
        ]);
        setConnectors(connectionData.connectors || []);
        setMultimodal(multimodalData.capabilities || null);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Connections could not be loaded.",
        );
      }
    })();
  }, []);

  const active = connectors.filter((item) => item.configured);
  const future = connectors.filter((item) => !item.configured);

  return (
    <main className="pv-connections-page">
      <header className="pv-connections-head">
        <div>
          <p className="pv-v8-kicker">V65 · Connected workspace</p>
          <h1>Connected Apps</h1>
          <p>
            See what Vasuki can access now and what still needs a secure
            connection backend. Unconfigured apps are never shown as connected.
          </p>
        </div>
        <nav>
          <a href="/">Back to chat</a>
          <a href="/account">Account & privacy</a>
        </nav>
      </header>

      {error ? (
        <div className="pv-v8-error pv-connections-error" role="alert">
          {error}
        </div>
      ) : null}

      <section className="pv-connections-summary">
        <article>
          <span>Connected now</span>
          <strong>{active.length}</strong>
        </article>
        <article>
          <span>Ready for future OAuth</span>
          <strong>{future.length}</strong>
        </article>
        <article>
          <span>Write permissions</span>
          <strong>Explicit</strong>
        </article>
      </section>

      <section className="pv-connections-grid">
        {connectors.map((connector) => (
          <article
            className={[
              "pv-connection-card",
              connector.configured ? "is-connected" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            key={connector.id}
          >
            <div className="pv-connection-card-head">
              <div>
                <small>{connector.category}</small>
                <h2>{connector.label}</h2>
              </div>
              <span className="pv-connection-state">
                {stateLabel(connector.state)}
              </span>
            </div>

            <p>{connector.note}</p>

            <div className="pv-connection-capabilities">
              {(connector.capabilities || []).map((capability) => (
                <span key={capability}>
                  {capability.replace(/-/g, " ")}
                </span>
              ))}
            </div>

            <footer>
              <span>
                {connector.read_capable ? "Read" : "No read access"}
              </span>
              <span>
                {connector.write_capable
                  ? connector.permission_required_for_write
                    ? "Write · approval required"
                    : "Write enabled"
                  : "No write access"}
              </span>
            </footer>
          </article>
        ))}
      </section>

      <section className="pv-connections-voice">
        <div>
          <p className="pv-v8-kicker">V66 · Multimodal & voice</p>
          <h2>Built-in capabilities</h2>
          <p>
            Browser voice stays zero-config. Server STT/TTS are optional and
            remain backend-only when configured.
          </p>
        </div>

        <div className="pv-connections-capability-grid">
          <article>
            <span>Image analysis</span>
            <strong>{multimodal?.image_analysis ? "Ready" : "Unavailable"}</strong>
          </article>
          <article>
            <span>PDF / documents</span>
            <strong>{multimodal?.document_analysis ? "Ready" : "Unavailable"}</strong>
          </article>
          <article>
            <span>Browser voice input</span>
            <strong>{multimodal?.browser_voice_input ? "Ready" : "Unavailable"}</strong>
          </article>
          <article>
            <span>Read aloud</span>
            <strong>{multimodal?.browser_read_aloud ? "Ready" : "Unavailable"}</strong>
          </article>
          <article>
            <span>Server transcription</span>
            <strong>
              {multimodal?.audio_upload_transcription
                ? "Configured"
                : "Optional"}
            </strong>
          </article>
          <article>
            <span>Joint multimodal</span>
            <strong>
              {multimodal?.joint_multimodal_endpoint
                ? `Up to ${multimodal.max_joint_files || 8} files`
                : "Unavailable"}
            </strong>
          </article>
        </div>
      </section>
    </main>
  );
}
