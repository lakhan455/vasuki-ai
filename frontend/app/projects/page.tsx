"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  addProjectDecisionV71,
  addProjectMemory,
  addProjectRepoV71,
  addProjectTaskV71,
  createProject,
  deleteProjectBrainItemV71,
  deleteProjectMemory,
  fetchProjectBrainV71,
  fetchProjectMemories,
  fetchProjects,
  setProjectGoalV71,
  setProjectLastWorkV71,
  updateProjectTaskV71,
  type ProjectBrainSnapshotV71,
  type ProjectMemory,
  type VasukiProject,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  in_progress: "In progress",
  blocked: "Blocked",
  done: "Done",
};

export default function ProjectsPage() {
  const [items, setItems] = useState<VasukiProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [brain, setBrain] = useState<ProjectBrainSnapshotV71 | null>(null);
  const [memories, setMemories] = useState<ProjectMemory[]>([]);
  const [memoryText, setMemoryText] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [goalText, setGoalText] = useState("");
  const [lastWork, setLastWork] = useState("");
  const [nextStep, setNextStep] = useState("");
  const [decisionTitle, setDecisionTitle] = useState("");
  const [decisionReason, setDecisionReason] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [taskPriority, setTaskPriority] = useState("normal");
  const [repoLabel, setRepoLabel] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [brainBusy, setBrainBusy] = useState(false);
  const [memoryBusy, setMemoryBusy] = useState(false);
  const [error, setError] = useState("");

  const activeProject = useMemo(
    () => items.find((item) => item.id === selectedProjectId) || null,
    [items, selectedProjectId],
  );

  async function token() {
    const { data } = await supabase.auth.getSession();
    if (!data.session?.access_token) {
      throw new Error("Please sign in to use Projects.");
    }
    return data.session.access_token;
  }

  async function loadProjects() {
    const projects = await fetchProjects(await token());
    setItems(projects);
    if (!selectedProjectId && projects[0]?.id) {
      setSelectedProjectId(projects[0].id);
    }
  }

  async function loadProjectData(projectId: string) {
    if (!projectId) {
      setBrain(null);
      setMemories([]);
      return;
    }

    try {
      setBrainBusy(true);
      setError("");
      const accessToken = await token();
      const [brainData, memoryData] = await Promise.all([
        fetchProjectBrainV71(accessToken, projectId),
        fetchProjectMemories(accessToken, projectId),
      ]);

      setBrain(brainData);
      setMemories(
        memoryData.filter(
          (memory) => String(memory.source || "").toLowerCase() !== "v71",
        ),
      );
      setGoalText(brainData.goal?.text || "");
      setLastWork(brainData.last_work?.summary || "");
      setNextStep(brainData.last_work?.next_step || "");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Project Brain could not be loaded.",
      );
    } finally {
      setBrainBusy(false);
    }
  }

  async function initialLoad() {
    try {
      setLoading(true);
      setError("");
      await loadProjects();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Projects could not be loaded.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void initialLoad();
  }, []);

  useEffect(() => {
    void loadProjectData(selectedProjectId);
  }, [selectedProjectId]);

  async function submitProject(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;

    try {
      setError("");
      const data = await createProject(await token(), {
        name,
        description,
        instructions,
      });
      const project = data.project as VasukiProject | undefined;

      setName("");
      setDescription("");
      setInstructions("");
      await loadProjects();

      if (project?.id) {
        setSelectedProjectId(project.id);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Project creation failed.",
      );
    }
  }

  async function saveGoal(event: FormEvent) {
    event.preventDefault();
    if (!selectedProjectId || !goalText.trim()) return;

    try {
      setBrainBusy(true);
      await setProjectGoalV71(
        await token(),
        selectedProjectId,
        goalText.trim(),
      );
      await loadProjectData(selectedProjectId);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Project goal could not be saved.",
      );
    } finally {
      setBrainBusy(false);
    }
  }

  async function saveLastWork(event: FormEvent) {
    event.preventDefault();
    if (!selectedProjectId || !lastWork.trim()) return;

    try {
      setBrainBusy(true);
      await setProjectLastWorkV71(
        await token(),
        selectedProjectId,
        lastWork.trim(),
        nextStep.trim(),
      );
      await loadProjectData(selectedProjectId);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Last work checkpoint could not be saved.",
      );
    } finally {
      setBrainBusy(false);
    }
  }

  async function addDecision(event: FormEvent) {
    event.preventDefault();
    if (!selectedProjectId || !decisionTitle.trim()) return;

    try {
      setBrainBusy(true);
      await addProjectDecisionV71(
        await token(),
        selectedProjectId,
        decisionTitle.trim(),
        decisionReason.trim(),
      );
      setDecisionTitle("");
      setDecisionReason("");
      await loadProjectData(selectedProjectId);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Decision could not be saved.",
      );
    } finally {
      setBrainBusy(false);
    }
  }

  async function addTask(event: FormEvent) {
    event.preventDefault();
    if (!selectedProjectId || !taskTitle.trim()) return;

    try {
      setBrainBusy(true);
      await addProjectTaskV71(
        await token(),
        selectedProjectId,
        taskTitle.trim(),
        "pending",
        taskPriority,
      );
      setTaskTitle("");
      setTaskPriority("normal");
      await loadProjectData(selectedProjectId);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Task could not be saved.",
      );
    } finally {
      setBrainBusy(false);
    }
  }

  async function moveTask(taskId: string, status: string) {
    if (!selectedProjectId) return;

    try {
      setBrainBusy(true);
      await updateProjectTaskV71(
        await token(),
        selectedProjectId,
        taskId,
        { status },
      );
      await loadProjectData(selectedProjectId);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Task status could not be updated.",
      );
    } finally {
      setBrainBusy(false);
    }
  }

  async function addRepo(event: FormEvent) {
    event.preventDefault();
    if (!selectedProjectId || !repoUrl.trim()) return;

    try {
      setBrainBusy(true);
      await addProjectRepoV71(
        await token(),
        selectedProjectId,
        repoLabel.trim(),
        repoUrl.trim(),
      );
      setRepoLabel("");
      setRepoUrl("");
      await loadProjectData(selectedProjectId);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Repository link could not be saved.",
      );
    } finally {
      setBrainBusy(false);
    }
  }

  async function removeBrainItem(itemId: string) {
    if (!selectedProjectId) return;

    try {
      setBrainBusy(true);
      await deleteProjectBrainItemV71(
        await token(),
        selectedProjectId,
        itemId,
      );
      await loadProjectData(selectedProjectId);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Project Brain item could not be deleted.",
      );
    } finally {
      setBrainBusy(false);
    }
  }

  async function addMemory(event: FormEvent) {
    event.preventDefault();
    if (!selectedProjectId || !memoryText.trim()) return;

    try {
      setMemoryBusy(true);
      await addProjectMemory(
        await token(),
        selectedProjectId,
        memoryText.trim(),
      );
      setMemoryText("");
      await loadProjectData(selectedProjectId);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Project memory could not be saved.",
      );
    } finally {
      setMemoryBusy(false);
    }
  }

  async function removeMemory(memoryId: string) {
    if (!selectedProjectId) return;

    try {
      await deleteProjectMemory(
        await token(),
        selectedProjectId,
        memoryId,
      );
      await loadProjectData(selectedProjectId);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Project memory could not be deleted.",
      );
    }
  }

  const taskCounts = brain?.task_summary?.counts || {};
  const fileLanguages = brain?.files?.languages || {};

  return (
    <main className="pv-v8-page pv-v71-brain">
      <div className="pv-v8-page-head">
        <div>
          <p className="pv-v8-kicker">Persistent workspace intelligence</p>
          <h1>Project Brain 3.0</h1>
          <p>
            Goals, decisions, tasks, repositories, files and last-work state
            stay attached to the active project.
          </p>
        </div>
        <a className="pv-v8-back" href="/">Back to chat</a>
      </div>

      <form className="pv-v8-form" onSubmit={(event) => void submitProject(event)}>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Project name"
        />
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="Short description"
        />
        <textarea
          value={instructions}
          onChange={(event) => setInstructions(event.target.value)}
          placeholder="Project instructions (optional)"
        />
        <button type="submit">Create project</button>
      </form>

      {error && <div className="pv-v8-error">{error}</div>}
      {loading && <p>Loading projects...</p>}

      <section className="pv-v71-project-shell">
        <aside className="pv-v71-project-list">
          {items.map((item) => (
            <button
              type="button"
              className={selectedProjectId === item.id ? "is-active" : ""}
              key={item.id}
              onClick={() => setSelectedProjectId(item.id)}
            >
              <strong>{item.name}</strong>
              <span>{item.description || "No description"}</span>
            </button>
          ))}
        </aside>

        <div className="pv-v71-workspace">
          {!activeProject ? (
            <div className="pv-v71-empty">
              Create or select a project to open its brain.
            </div>
          ) : (
            <>
              <section className="pv-v71-hero">
                <div>
                  <span>ACTIVE PROJECT</span>
                  <h2>{activeProject.name}</h2>
                  <p>{activeProject.description || "No project description yet."}</p>
                </div>

                <div className="pv-v71-stats">
                  <div>
                    <strong>{brain?.files?.count ?? 0}</strong>
                    <span>Files</span>
                  </div>
                  <div>
                    <strong>{brain?.tasks?.length ?? 0}</strong>
                    <span>Tasks</span>
                  </div>
                  <div>
                    <strong>{brain?.decisions?.length ?? 0}</strong>
                    <span>Decisions</span>
                  </div>
                  <div>
                    <strong>
                      {Math.round(brain?.task_summary?.completion_pct ?? 100)}%
                    </strong>
                    <span>Complete</span>
                  </div>
                </div>
              </section>

              <section className="pv-v71-grid pv-v71-grid--two">
                <article className="pv-v71-card">
                  <div className="pv-v71-card-head">
                    <div>
                      <span>PROJECT NORTH STAR</span>
                      <h3>Goal</h3>
                    </div>
                  </div>

                  <form onSubmit={(event) => void saveGoal(event)}>
                    <textarea
                      value={goalText}
                      onChange={(event) => setGoalText(event.target.value)}
                      placeholder="What must this project ultimately achieve?"
                      rows={5}
                    />
                    <button
                      disabled={brainBusy || !goalText.trim()}
                      type="submit"
                    >
                      Save goal
                    </button>
                  </form>
                </article>

                <article className="pv-v71-card">
                  <div className="pv-v71-card-head">
                    <div>
                      <span>RESUME POINT</span>
                      <h3>Last work checkpoint</h3>
                    </div>
                  </div>

                  <form onSubmit={(event) => void saveLastWork(event)}>
                    <textarea
                      value={lastWork}
                      onChange={(event) => setLastWork(event.target.value)}
                      placeholder="What was completed most recently?"
                      rows={3}
                    />
                    <input
                      value={nextStep}
                      onChange={(event) => setNextStep(event.target.value)}
                      placeholder="Exact next step"
                    />
                    <button
                      disabled={brainBusy || !lastWork.trim()}
                      type="submit"
                    >
                      Save checkpoint
                    </button>
                  </form>
                </article>
              </section>

              <section className="pv-v71-card">
                <div className="pv-v71-card-head">
                  <div>
                    <span>EXECUTION</span>
                    <h3>Task board</h3>
                  </div>

                  <div className="pv-v71-mini-stats">
                    <span>{taskCounts.pending || 0} pending</span>
                    <span>{taskCounts.in_progress || 0} active</span>
                    <span>{taskCounts.blocked || 0} blocked</span>
                    <span>{taskCounts.done || 0} done</span>
                  </div>
                </div>

                <form
                  className="pv-v71-inline-form"
                  onSubmit={(event) => void addTask(event)}
                >
                  <input
                    value={taskTitle}
                    onChange={(event) => setTaskTitle(event.target.value)}
                    placeholder="Add a concrete task"
                  />
                  <select
                    value={taskPriority}
                    onChange={(event) => setTaskPriority(event.target.value)}
                  >
                    <option value="low">Low</option>
                    <option value="normal">Normal</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                  <button
                    disabled={brainBusy || !taskTitle.trim()}
                    type="submit"
                  >
                    Add task
                  </button>
                </form>

                <div className="pv-v71-task-board">
                  {["pending", "in_progress", "blocked", "done"].map((status) => (
                    <div className="pv-v71-task-column" key={status}>
                      <strong>{STATUS_LABELS[status]}</strong>

                      {(brain?.tasks || [])
                        .filter((task) => task.status === status)
                        .map((task) => (
                          <article className="pv-v71-task" key={task.id}>
                            <div>
                              <span
                                className={`pv-v71-priority is-${
                                  task.priority || "normal"
                                }`}
                              >
                                {task.priority || "normal"}
                              </span>
                              <h4>{task.title}</h4>
                              {task.notes ? <p>{task.notes}</p> : null}
                            </div>

                            <div className="pv-v71-task-actions">
                              <select
                                value={task.status || "pending"}
                                onChange={(event) =>
                                  void moveTask(task.id, event.target.value)
                                }
                                disabled={brainBusy}
                              >
                                <option value="pending">Pending</option>
                                <option value="in_progress">In progress</option>
                                <option value="blocked">Blocked</option>
                                <option value="done">Done</option>
                              </select>

                              <button
                                type="button"
                                onClick={() => void removeBrainItem(task.id)}
                                disabled={brainBusy}
                              >
                                Delete
                              </button>
                            </div>
                          </article>
                        ))}
                    </div>
                  ))}
                </div>
              </section>

              <section className="pv-v71-grid pv-v71-grid--two">
                <article className="pv-v71-card">
                  <div className="pv-v71-card-head">
                    <div>
                      <span>WHY WE CHOSE THIS</span>
                      <h3>Decisions</h3>
                    </div>
                  </div>

                  <form onSubmit={(event) => void addDecision(event)}>
                    <input
                      value={decisionTitle}
                      onChange={(event) => setDecisionTitle(event.target.value)}
                      placeholder="Decision"
                    />
                    <textarea
                      value={decisionReason}
                      onChange={(event) => setDecisionReason(event.target.value)}
                      placeholder="Why was this decision made?"
                      rows={2}
                    />
                    <button
                      disabled={brainBusy || !decisionTitle.trim()}
                      type="submit"
                    >
                      Save decision
                    </button>
                  </form>

                  <div className="pv-v71-list">
                    {(brain?.decisions || []).map((decision) => (
                      <article key={decision.id}>
                        <div>
                          <strong>{decision.title}</strong>
                          {decision.rationale ? <p>{decision.rationale}</p> : null}
                        </div>
                        <button
                          type="button"
                          onClick={() => void removeBrainItem(decision.id)}
                        >
                          Delete
                        </button>
                      </article>
                    ))}
                  </div>
                </article>

                <article className="pv-v71-card">
                  <div className="pv-v71-card-head">
                    <div>
                      <span>SOURCE OF TRUTH</span>
                      <h3>Repositories & files</h3>
                    </div>
                  </div>

                  <form
                    className="pv-v71-repo-form"
                    onSubmit={(event) => void addRepo(event)}
                  >
                    <input
                      value={repoLabel}
                      onChange={(event) => setRepoLabel(event.target.value)}
                      placeholder="Repository label"
                    />
                    <input
                      value={repoUrl}
                      onChange={(event) => setRepoUrl(event.target.value)}
                      placeholder="https://github.com/owner/repo"
                    />
                    <button
                      disabled={brainBusy || !repoUrl.trim()}
                      type="submit"
                    >
                      Add repo
                    </button>
                  </form>

                  <div className="pv-v71-list">
                    {(brain?.repos || []).map((repo) => (
                      <article key={repo.id}>
                        <div>
                          <strong>{repo.label || "GitHub repository"}</strong>
                          <a href={repo.url} target="_blank" rel="noreferrer">
                            {repo.url}
                          </a>
                        </div>
                        <button
                          type="button"
                          onClick={() => void removeBrainItem(repo.id)}
                        >
                          Delete
                        </button>
                      </article>
                    ))}
                  </div>

                  <div className="pv-v71-file-summary">
                    <strong>{brain?.files?.count ?? 0} Project KB files</strong>
                    <div>
                      {Object.entries(fileLanguages).map(([language, count]) => (
                        <span key={language}>
                          {language} · {count}
                        </span>
                      ))}
                    </div>
                  </div>
                </article>
              </section>

              <section className="pv-v71-card">
                <div className="pv-v71-card-head">
                  <div>
                    <span>STABLE KNOWLEDGE</span>
                    <h3>Project memory</h3>
                  </div>
                </div>

                <p className="pv-v8-muted">
                  Keep durable requirements, preferences and facts here. Project
                  Brain structured items are stored separately from this readable
                  memory list.
                </p>

                <form
                  className="pv-v8-memory-form"
                  onSubmit={(event) => void addMemory(event)}
                >
                  <textarea
                    value={memoryText}
                    onChange={(event) => setMemoryText(event.target.value)}
                    placeholder="Example: Always use Supabase and a dark premium UI."
                    disabled={!selectedProjectId || memoryBusy}
                  />
                  <button
                    type="submit"
                    disabled={
                      !selectedProjectId || memoryBusy || !memoryText.trim()
                    }
                  >
                    {memoryBusy ? "Saving..." : "Add memory"}
                  </button>
                </form>

                <div className="pv-v8-memory-list">
                  {memories.length === 0 ? (
                    <p className="pv-v8-muted">
                      No regular project memories yet.
                    </p>
                  ) : null}

                  {memories.map((memory) => (
                    <div className="pv-v8-memory-row" key={memory.id}>
                      <span>{memory.memory_text}</span>
                      <button
                        type="button"
                        onClick={() => void removeMemory(memory.id)}
                      >
                        Delete
                      </button>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}

          {brainBusy ? (
            <div className="pv-v71-sync">
              Syncing Project Brain…
            </div>
          ) : null}
        </div>
      </section>
    </main>
  );
}
