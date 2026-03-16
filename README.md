# Dev Pipeline

A terminal UI that runs your development task through a sequential multi-agent pipeline, each stage powered by Claude Code.

```
○ Plan  →  ○ Decomp  →  ○ Impl ⋮  →  ○ Tests ⋮  →  ○ Quality  →  ○ Docs  →  ○ PR
```

Stages marked with `⋮` run in parallel across subtasks automatically decomposed from your prompt.

## Quick Start

```bash
uv run pipeline
```

Paste your task or prompt, press `Ctrl+Enter`, and watch the stages execute live.

## Pipeline Stages

| Stage | What it does |
|-------|-------------|
| **Planning** | Senior architect creates a numbered implementation plan with tasks, decisions, and risks. Retries up to 3× if issues are found. |
| **Decomposition** | Breaks the plan into independent parallel subtasks for Implementation and Tests. |
| **Implementation** | Parallel workers write production-ready code — one per subtask. |
| **Tests & Validation** | Parallel workers write unit, edge-case, and integration tests per subtask. Retries on failures. |
| **Code Quality** | Reviews the implementation for technical debt, security, performance, and readability. |
| **Documentation** | Generates README sections, docstrings, API reference, and migration notes. |
| **Commit & PR** | Produces conventional commits and a GitHub PR description as structured JSON, then commits and opens the PR. |

## UI Layout

- **Stage pills bar** — horizontal scrollable bar showing each stage with status icon and elapsed time
- **Streaming pane** — live output from the currently running stage
- **Cost bar** — running total of Claude API cost and number of calls

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI installed (`claude` command)

## Keybindings

| Key | Action |
|-----|--------|
| `Ctrl+Enter` | Run pipeline |
| `Ctrl+L` | Clear log |
| `Ctrl+C` | Quit |
