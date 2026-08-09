"use client";

import { FormEvent, useEffect, useState } from "react";

type Project = {
  id: string;
  name: string;
  description?: string;
  instructions?: string;
  color?: string;
  archived?: boolean;
};

export default function ProjectsPage() {
  const [items, setItems] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    const response = await fetch("/api/projects", { credentials: "include" });
    const data = await response.json();
    setItems(Array.isArray(data?.projects) ? data.projects : []);
    setLoading(false);
  }

  useEffect(() => { load(); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    await fetch("/api/projects", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    });
    setName("");
    setDescription("");
    load();
  }

  return (
    <main style={{ padding: 24, color: "white", background: "#212121", minHeight: "100vh" }}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>Projects & Workspaces</h1>
      <p style={{ color: "#b4b4b4", marginBottom: 20 }}>Keep chats, files and instructions organized per project.</p>
      <form onSubmit={submit} style={{ display: "grid", gap: 10, maxWidth: 640, marginBottom: 20 }}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Project name" style={{ background: "#171717", border: "1px solid #3a3a3a", borderRadius: 12, padding: 12, color: "white" }} />
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Short description" style={{ background: "#171717", border: "1px solid #3a3a3a", borderRadius: 12, padding: 12, color: "white", minHeight: 100 }} />
        <button type="submit" style={{ background: "#7c3aed", color: "white", border: "none", borderRadius: 12, padding: 12, width: 180 }}>Create project</button>
      </form>
      {loading && <p>Loading projects...</p>}
      <div style={{ display: "grid", gap: 12 }}>
        {items.map((item) => (
          <div key={item.id} style={{ border: "1px solid #3a3a3a", borderRadius: 14, padding: 16, background: "#171717" }}>
            <div style={{ fontWeight: 600 }}>{item.name}</div>
            {item.description ? <div style={{ color: "#d1d5db", marginTop: 6 }}>{item.description}</div> : null}
          </div>
        ))}
      </div>
    </main>
  );
}
