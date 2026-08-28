# Vasuki AI V48 — Unified Tools Hub

V48 does **not** copy proprietary ChatGPT internals. It adds native Vasuki equivalents for the tool categories that can be implemented safely in this stack, and it clearly marks the categories that require external OAuth/MCP/browser infrastructure.

## Added in V48

- Unified `/health/v48` + authenticated `/api/v48/tools` capability registry.
- Safe **Data Analysis** for CSV, TSV, JSON and XLSX.
  - deterministic profiling, missing-value counts, numeric stats, category frequency, preview rows and chart suggestions.
  - no arbitrary server-side Python execution.
- XLSX/TSV support in the existing multimodal/file extraction path.
- Persistent **File Library** using the existing Supabase backend credentials and a private `vasuki-files-v48` Storage bucket.
  - upload, list, signed download and delete.
  - no new SQL migration.
- Full **Scheduled Tasks management** on top of the existing V11 scheduler table.
  - create, list, pause/resume/update and delete.
- New `/tools` frontend page with a ChatGPT-style tools control surface.
- Command palette entry for the Tools Hub.

## Already present before V48 and exposed as part of the hub

- Web Search
- Deep Research
- Image generation
- Image editing / vision
- PDF/DOCX/text/ZIP analysis
- Voice input/output
- Memory
- Projects
- Coding agent / project builder
- GitHub workflows
- Optional video generation
- MCP/A2A hooks through existing configuration

## Deliberately not faked

### Computer Use

ChatGPT's hosted computer-use environment is an OpenAI product capability. Vasuki V48 reports this as `not-enabled` rather than pretending it has the same sandbox. A later version can integrate an explicitly configured remote browser/sandbox provider with approval gates.

### Gmail / Google Calendar / Drive / Slack apps

These require OAuth apps or MCP servers owned/configured by the Vasuki deployment. V48 keeps the connector slot visible but does not invent credentials.

## New dependency

- `openpyxl>=3.1,<4.0` for safe XLSX reading.

## No new credentials required for the V48 core

V48 reuses the existing Supabase backend service-role/secret credentials for the private file library. Existing web/research/image/voice/provider credentials stay unchanged.
