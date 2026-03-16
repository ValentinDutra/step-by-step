# Step-by-Step — Multi-Agent Dev Pipeline

A terminal UI that runs your development tasks through a multi-agent LLM pipeline, inspired by GitHub Actions. Each stage is handled by a specialized Claude agent: planner, decomposer, implementers (parallel workers), QA engineers, code reviewer, technical writer, and a commit/PR bot.

```
Plan ──●── Decomp ──●── Impl ⇶ ──●── Tests ⇶ ──●── Quality ──●── Docs ──●── PR
```

Stages marked with `⇶` run in parallel — your task is split into independent subtasks, each handled by a dedicated worker agent simultaneously.

## Prerequisites

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- **[Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)** — `npm install -g @anthropic-ai/claude-code`
- **[GitHub CLI](https://cli.github.com/)** — required for the Commit & PR stage

## Installation

```bash
git clone <repo>
cd step-by-step
uv sync
```

## Usage

```bash
# Run against the current directory
uv run pipeline

# Run against a specific repo
uv run pipeline /path/to/your/repo

# Load a prompt from a file and start immediately
uv run pipeline /path/to/your/repo -f prompt.txt
```

Paste your task description in the input area and press `Ctrl+Enter` to start.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+Enter` | Submit prompt and run pipeline |
| `Ctrl+L` | Clear activity log |
| `Ctrl+E` | Export log to `pipeline_log_<timestamp>.txt` |
| `Ctrl+C` | Quit |

## Re-running Stages

Once a run completes, every stage pill becomes clickable. Click any pill to re-run from that stage forward, reusing all previous context automatically.

## Pipeline Stages

| Stage | Mode | Description |
|-------|------|-------------|
| **Planning** | Single agent | Senior architect creates a numbered implementation plan |
| **Decomposition** | Manager | Splits the plan into independent parallel subtasks |
| **Implementation** | Parallel workers | Each subtask implemented by a dedicated worker — number of workers decided by Claude |
| **Tests & Validation** | Parallel workers | QA writes tests per subtask; signals issues or done via `## Issues Found` |
| **Code Quality** | Single agent | Reviewer checks for smells, security, and readability |
| **Documentation** | Single agent | Generates README sections, docstrings, and API reference |
| **Commit & PR** | Single agent | Conventional commits + opens a GitHub PR |

### Automatic Refinement Loops

Claude drives both loops — it decides when to stop by reporting `## Issues Found: None` in its output.

- **Test loop** — loops back through Implementation → Tests until Claude reports no issues
- **Quality loop** — re-decomposes and re-implements until Code Quality reports no issues

## UI Layout

- **Stage bar** — horizontal scrollable bar with status icons and elapsed time per stage
- **Streaming pane** — live output from the currently running stage or worker
- **Activity log** — full history of the pipeline run
- **Stats bar** — running total of Claude API calls, cost, and elapsed time

## Project Structure

```
app/
├── __main__.py      Entry point
├── models.py        Shared data classes: Task, WorkerResult, PipelineStats
├── agents.py        Claude CLI invocation and worker coordination
├── stages.py        Stage definitions, prompts, and pipeline config
├── git.py           Git/gh subprocess helpers and Commit & PR stage runner
├── pipeline.py      Stage runners: run_stage() and run_stage_parallel()
├── widgets.py       StagePill TUI widget and stage display constants
├── runner.py        PipelineRunnerMixin: run_pipeline() and rerun_from_stage()
└── tui.py           PipelineApp (Textual App) and main() entry point
```

## Configuration

The pipeline uses `claude --dangerously-skip-permissions` so agents can write files autonomously. Only run it in repos where you trust the output — review the diff before the PR stage commits.

Both the test refinement loop and the quality loop run until Claude reports no issues — there are no hard iteration limits.
