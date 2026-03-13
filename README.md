# Dev Pipeline

A terminal UI that runs your development task through a sequential pipeline, each stage powered by Claude Code.

```
○ Planning          →  ◉ Implementation  →  ○ Tests & Validation
○ Code Quality      →  ○ Docs & Test Run →  ○ Review & PR
```

## Quick Start

```bash
uv run pipeline
```

Enter a prompt, press Enter, and watch the stages execute.

## Pipeline Stages

| Stage | What it does |
|-------|-------------|
| Planning | Creates task list + full implementation plan |
| Implementation | Writes code using Claude Code |
| Tests & Validation | Creates tests, validates coverage |
| Code Quality | Fixes technical debt, security, performance |
| Docs & Test Run | Adds documentation, runs and fixes tests |
| Review & PR | Final review, generates PR description |

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI installed (`claude` command)

## Keybindings

| Key | Action |
|-----|--------|
| Enter | Start pipeline |
| Ctrl+L | Clear log |
| Ctrl+C | Quit |
