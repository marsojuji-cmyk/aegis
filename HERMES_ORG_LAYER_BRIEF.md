# Hermes Organization Layer — Cursor Task Brief

## Objective

Advance Hermes’s local-first organization capabilities (file/note indexing, search, project context) under the existing AEGIS gate, without changing billing, models, or the AEGIS gate configuration.

## Scope

Hermes is the reasoning/organization layer; AEGIS is the authority layer. Enforce: input normalization → AEGIS policy check → redaction → capability/risk decision → execution only if allowed → immutable audit log.

Repo: `/Users/a100/Projects/aegis`  
Vault: `/Users/a100/Library/Mobile Documents/iCloud~md~obsidian/Documents/AGIS`  
Memory Utility Labs (approved corpus): `AEGIS/05-Memory-Utility-Labs`  
Workspace: `/Users/ektar/workspace` (Hermes brain folder; empty)

## Constraints

- Plugin: `aegis-gate` enabled (`allow_tool_override=false`). Do not disable or alter.
- Shadow mode: on. Thresholds unchanged.
- No Hermes-agent source edits; enable/disable only via `hermes plugins`.
- No billing or provider changes. No model probing.
- Unknown tools fail closed; empty `guard_allowed_domains` still denies.

## Catalogued Hermes org tools (D-020)

- `memory` — write-only (`memory.write`: add/replace/remove). Hermes memory is not domain-scoped to `guard_allowed_domains` (R-015).
- `session_search` — search current session context
- `todo` — task tracking
- `skills_list` / `skill_view` / `skill_manage` — skill introspection and management
- `project_list` / `project_create` / `project_switch` — project context management

## Recommended next capabilities

### 1. File indexing for `/Users/ektar/workspace`

Build a lightweight indexer that:
- Recursively scans `/Users/ektar/workspace` (respecting `.gitignore` and common ignores)
- Extracts: path, type, size, modified time, optional text preview (first N lines for text files)
- Stores results in a structured index (JSON or SQLite) under `~/.aegis/hermes_index/`
- Provides a query interface (by path, type, modified date, content keyword)

AEGIS considerations:
- File reads must pass the gate (`read_file` allowed, as proven in D-017)
- Index writes should be logged as `fs.write` operations with scope validation
- Redact or exclude sensitive paths if configured

### 2. Note linking and graph

Extend the index to:
- Parse Markdown notes for frontmatter (tags, projects, dates) and internal links (`[[...]]`)
- Build a simple note graph (nodes = notes, edges = links)
- Enable queries like “notes linked to X”, “notes tagged Y”, “orphaned notes”

AEGIS considerations:
- Treat note parsing as read-only; graph writes are `fs.write` under `~/.aegis/`
- Validate that note paths are within allowed scopes

### 3. Project context loader

Implement a `project_context` tool that:
- Loads project metadata from `project_list` / `project_switch`
- Reads a `PROJECT.md` or similar manifest in the project root
- Surfaces key context (goals, constraints, recent decisions) to Hermes sessions

AEGIS considerations:
- Manifest reads must pass the gate
- Project metadata should be treated as session-scoped, not persisted to Hermes memory unless explicitly written via `memory.write`

### 4. Search integration

Combine file index + note graph + project context into a unified `search` tool:
- Accept natural-language queries
- Return ranked results from files, notes, and project manifests
- Optionally filter by type, tag, date range, or project

AEGIS considerations:
- Search is read-only; no execution risk
- Ensure query normalization and redaction before passing to any external search APIs (if added later)

## Implementation plan

1. **Define data structures** for file index, note graph, and project context (JSON schemas or SQLite tables)
2. **Implement indexer** as a standalone script or Hermes skill, with AEGIS gate validation for file reads
3. **Add note parser** to extract links and frontmatter
4. **Build query interfaces** for each data source
5. **Integrate into Hermes** as new skills (`file_index`, `note_graph`, `project_context`, `unified_search`)
6. **Test under AEGIS** to ensure all file reads pass the gate and are logged correctly

## Success criteria

- Hermes can index `/Users/ektar/workspace` and answer queries about files, notes, and projects
- All file reads pass through the AEGIS gate and are logged
- No changes to billing, models, or gate configuration
- New skills are catalogued in the AEGIS risk register (R-015 update if needed)

## Next step

Start with the file indexer: define the schema and implement a basic recursive scan of `/Users/ektar/workspace` that outputs a JSON index to `~/.aegis/hermes_index/files.json`.
