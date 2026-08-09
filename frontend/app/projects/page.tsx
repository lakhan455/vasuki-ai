"use client";

import { FormEvent, useEffect, useState } from "react";
import { createProject, fetchProjects, type VasukiProject } from "@/lib/api";
import { supabase } from "@/lib/supabase";

export default function ProjectsPage() {
  const [items, setItems] = useState<VasukiProject[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function token() {
    const { data } = await supabase.auth.getSession();
    if (!data.session?.access_token) throw new Error("Please sign in to use Projects.");
    return data.session.access_token;
  }

  async function load() {
    try {
      setLoading(true);
      setError("");
      setItems(await fetchProjects(await token()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Projects could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      await createProject(await token(), { name, description, instructions });
      setName(""); setDescription(""); setInstructions("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project creation failed.");
    }
  }

  return (
    <main className="pv-v8-page">
      <div className="pv-v8-page-head">
        <div><p className="pv-v8-kicker">Workspace foundation</p><h1>Projects & Workspaces</h1><p>Organize project instructions and future project-specific chats/files.</p></div>
        <a className="pv-v8-back" href="/">Back to chat</a>
      </div>
      <form className="pv-v8-form" onSubmit={(event) => void submit(event)}>
        <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Project name" />
        <textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Short description" />
        <textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} placeholder="Project instructions (optional)" />
        <button type="submit">Create project</button>
      </form>
      {error && <div className="pv-v8-error">{error}</div>}
      {loading && <p>Loading projects...</p>}
      <div className="pv-v8-grid">
        {items.map((item) => (
          <article className="pv-v8-card pv-v8-card--block" key={item.id}>
            <strong>{item.name}</strong>
            {item.description ? <p>{item.description}</p> : null}
            {item.instructions ? <small>Instructions saved</small> : null}
          </article>
        ))}
      </div>
    </main>
  );
}
