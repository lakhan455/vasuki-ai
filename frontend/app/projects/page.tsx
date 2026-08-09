"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  addProjectMemory,
  createProject,
  deleteProjectMemory,
  fetchProjectMemories,
  fetchProjects,
  type ProjectMemory,
  type VasukiProject,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

export default function ProjectsPage() {
  const [items, setItems] = useState<VasukiProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [memories, setMemories] = useState<ProjectMemory[]>([]);
  const [memoryText, setMemoryText] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [loading, setLoading] = useState(true);
  const [memoryBusy, setMemoryBusy] = useState(false);
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
      const projects = await fetchProjects(await token());
      setItems(projects);
      if (!selectedProjectId && projects[0]?.id) setSelectedProjectId(projects[0].id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Projects could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  async function loadMemories(projectId: string) {
    if (!projectId) {
      setMemories([]);
      return;
    }
    try {
      setMemoryBusy(true);
      setMemories(await fetchProjectMemories(await token(), projectId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project memories could not be loaded.");
    } finally {
      setMemoryBusy(false);
    }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => { void loadMemories(selectedProjectId); }, [selectedProjectId]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      const data = await createProject(await token(), { name, description, instructions });
      const project = data.project as VasukiProject | undefined;
      setName(""); setDescription(""); setInstructions("");
      await load();
      if (project?.id) setSelectedProjectId(project.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project creation failed.");
    }
  }

  async function addMemory(event: FormEvent) {
    event.preventDefault();
    if (!selectedProjectId || !memoryText.trim()) return;
    try {
      setMemoryBusy(true);
      await addProjectMemory(await token(), selectedProjectId, memoryText.trim());
      setMemoryText("");
      await loadMemories(selectedProjectId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project memory could not be saved.");
    } finally {
      setMemoryBusy(false);
    }
  }

  async function removeMemory(memoryId: string) {
    if (!selectedProjectId) return;
    try {
      await deleteProjectMemory(await token(), selectedProjectId, memoryId);
      await loadMemories(selectedProjectId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Project memory could not be deleted.");
    }
  }

  return (
    <main className="pv-v8-page">
      <div className="pv-v8-page-head">
        <div>
          <p className="pv-v8-kicker">Phase 4 workspace intelligence</p>
          <h1>Projects & Project Memory</h1>
          <p>Project instructions and memories are injected only when that project is active in chat.</p>
        </div>
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

      <section className="pv-v8-project-layout">
        <div className="pv-v8-grid">
          {items.map((item) => (
            <button
              type="button"
              className={`pv-v8-project-select ${selectedProjectId === item.id ? "is-active" : ""}`}
              key={item.id}
              onClick={() => setSelectedProjectId(item.id)}
            >
              <strong>{item.name}</strong>
              <span>{item.description || "No description"}</span>
            </button>
          ))}
        </div>

        <div className="pv-v8-card pv-v8-card--block">
          <strong>Project Memory</strong>
          <p className="pv-v8-muted">Save stable project facts, decisions, requirements and preferences here.</p>
          <form className="pv-v8-memory-form" onSubmit={(event) => void addMemory(event)}>
            <textarea
              value={memoryText}
              onChange={(event) => setMemoryText(event.target.value)}
              placeholder={selectedProjectId ? "Example: Always use Supabase and blue theme for this project." : "Select a project first"}
              disabled={!selectedProjectId || memoryBusy}
            />
            <button type="submit" disabled={!selectedProjectId || memoryBusy || !memoryText.trim()}>
              {memoryBusy ? "Saving..." : "Add memory"}
            </button>
          </form>

          <div className="pv-v8-memory-list">
            {memoryBusy && memories.length === 0 ? <p>Loading memories...</p> : null}
            {!memoryBusy && selectedProjectId && memories.length === 0 ? <p className="pv-v8-muted">No project memories yet.</p> : null}
            {memories.map((memory) => (
              <div className="pv-v8-memory-row" key={memory.id}>
                <span>{memory.memory_text}</span>
                <button type="button" onClick={() => void removeMemory(memory.id)}>Delete</button>
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
