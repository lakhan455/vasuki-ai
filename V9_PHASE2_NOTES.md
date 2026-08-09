# Vasuki AI V9 Phase 2 — Project Knowledge + Coding Agent

This phase implements:

- Project Knowledge Base V2 with user/project scoped file snapshots.
- Cross-file codebase map (languages, symbols, imports, routes, relationships).
- AI Code Patch Mode with complete-file changes and unified diffs.
- Multi-file patch plans and Project KB apply flow with previous-version snapshots.
- Browser Code Execution Sandbox for HTML/CSS/JavaScript using a sandboxed iframe.
- Test Generation mode.
- Automatic Debug mode using project files + error logs.

Security choice: arbitrary server-side code execution is intentionally NOT enabled. The browser sandbox is isolated with `sandbox="allow-scripts"`. A future container/WASM executor can be added only with hard OS/network/resource isolation.
