# Step-by-Step

A terminal UI that runs your development tasks through a structured multi-agent pipeline. You describe what you want to build; a team of specialized Claude agents plans, implements, tests, reviews, and opens a pull request — autonomously.

![Step-by-Step in action](assets/screenshot.png)

---

## How it works

Step-by-Step models software delivery as a linear pipeline of specialized agents, each owning a single responsibility. Stages that can be parallelized fan out into independent worker agents that run concurrently, then merge their results before the next stage begins.

```
Plan ──● Decomp ──● Impl ⇶ ──● Tests ⇶ ──● Quality ──● Docs ──● PR
```

`⇶` = parallel workers · `●` = single agent

### Pipeline stages

| Stage | Mode | What it does |
|---|---|---|
| **Planning** | Single agent | Senior architect reads your codebase and produces a concrete, numbered implementation plan |
| **Decomposition** | Manager agent | Splits the plan into independent subtasks that can be worked on simultaneously |
| **Implementation** | Parallel workers | Each subtask is handed to a dedicated worker agent; all workers run concurrently |
| **Tests & Validation** | Parallel workers | QA agents write and run tests per subtask; surface failures via `## Issues Found` |
| **Code Quality** | Single agent | Reviewer checks for code smells, security issues, and readability |
| **Documentation** | Single agent | Generates or updates README sections, docstrings, and API reference |
| **Commit & PR** | Single agent | Writes conventional commits and opens a GitHub Pull Request |

### Refinement loops

Claude drives two autonomous feedback loops — it decides when to stop by reporting `## Issues Found: None`.

- **Test loop** — cycles through Implementation → Tests & Validation until no issues remain
- **Quality loop** — re-decomposes and re-implements until Code Quality is satisfied

### RAM-based flow control

Worker concurrency is not capped by a fixed number. Instead, the pipeline uses TCP-style flow control: a new worker starts only when system RAM is below a threshold (75% by default, configurable via `[limits].max_ram_pct`). Starts are serialized and include a post-start delay so the OS can register each new process's footprint before the next candidate is evaluated. When RAM is high, new workers queue up and resume as running workers release memory.

### Cost control & checkpoints

The pipeline is autonomous by default, but every expensive decision can be bounded or gated:

- **Cost cap** — set `[limits] max_cost_usd` and the run stops at the next stage boundary once accumulated cost reaches it; the activity log shows each stage's cost delta. See [Limits](#limits).
- **Checkpoints** — pause before chosen phases (with a git status + diff preview before Commit & PR), review and exclude subtasks before the parallel fan-out, or step through the whole run stage by stage. See [Confirmations](#confirmations).
- **Config dry-run** — `pipeline --check` validates your TOML and prints the resolved pipeline without calling any LLM.
- **Run artifacts** — persist each run's prompts, full per-stage outputs, and stats to disk for later inspection. See [Run artifacts](#run-artifacts).
- **Cancel anytime** — `Ctrl+X` stops the run, kills provider subprocesses, and leaves every stage re-runnable.

---

## Requirements

- **Python 3.13+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- **[Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)** — `npm install -g @anthropic-ai/claude-code`
- **[GitHub CLI](https://cli.github.com/)** — required for the Commit & PR stage (`gh auth login`)
- **[Codex CLI](https://developers.openai.com/codex)** *(optional)* — `npm install -g @openai/codex`; only needed if a phase uses `provider = "codex"`
- **[Gemini CLI](https://github.com/google-gemini/gemini-cli)** *(optional)* — `npm install -g @google/gemini-cli`; only needed if a phase uses `provider = "gemini"`

---

## Installation

**Via uv (recommended):**
```bash
uvx --from step-by-step-cli pipeline
```

**Via pip:**
```bash
pip install step-by-step-cli
pipeline
```

**From source:**
```bash
git clone https://github.com/ValentinDutra/step-by-step-cli.git
cd step-by-step-cli
uv sync
```

---

## Configuration

By default every stage runs on Claude. To run specific phases on a different CLI, create a `step-by-step.toml`. Resolution order (first found wins): `--config PATH`, then `step-by-step.toml` in the target repo, then `~/.config/step-by-step/config.toml`. With no config, behavior is unchanged (all Claude).

```toml
[defaults]
provider = "claude"        # claude | codex | gemini
model = ""                 # empty = the CLI's default model

[phases."Code Quality"]
provider = "codex"
model = "gpt-5.1-codex"

[phases.Planning]
provider = "gemini"
model = "gemini-3.5-flash"
```

Phase names match the pipeline stages: `Planning`, `Decomposition`, `Implementation`, `Tests & Validation`, `Code Quality`, `Documentation`, `Commit & PR`. Any phase you do not list falls back to `[defaults]`. Models are passed through to the CLI as-is. An unknown provider aborts before the run with a clear message, and a missing provider CLI is reported before stage 1.

Each provider handles its own authentication: `claude` (Claude Code login), `codex` (`codex login` or `OPENAI_API_KEY`), `gemini` (`gemini` login or `GEMINI_API_KEY`).

### Customizing the pipeline

By default the seven phases run in their listed order. Set a `pipeline` array to reorder phases, drop built-ins (e.g. omit `"Tests & Validation"`), or add your own prompt-only phases. With no `pipeline` key, the default seven run unchanged.

```toml
pipeline = ["Research", "Planning", "Decomposition", "Implementation", "Tests & Validation", "Commit & PR"]

[phases."Research"]          # a custom phase
kind = "simple"
skill = "research"           # -> .step-by-step/skills/research/SKILL.md

[phases."Code Quality"]
max_iterations = 3           # cap the quality gate's re-run loop (default 3)
```

Each phase has a `kind`:

| `kind` | behavior | built-ins |
|---|---|---|
| `simple` | one prompt -> one output | Planning, Documentation |
| `decompose` | splits the plan into parallel subtasks | Decomposition |
| `parallel` | fans out one worker per subtask | Implementation, Tests & Validation |
| `gate` | reviews, then loops back to re-run (capped by `max_iterations`, default 3) | Code Quality |
| `commit_pr` | creates the branch and the PR | Commit & PR |

Custom phases must be `kind = "simple"` — the other kinds are reserved for the built-ins. A `simple` phase declares its prompt with either `skill = "name"` (a folder containing `SKILL.md`, resolved from `<repo>/.step-by-step/skills/` then `~/.config/step-by-step/skills/`) or an inline `prompt = "..."` — exactly one. A built-in phase may override its prompt the same way.

The pipeline is validated before the run: an empty pipeline, duplicate names, a `parallel` phase with no preceding `decompose`, more than one `commit_pr` or `gate`, a custom phase that isn't `simple`, or one missing both `skill` and `prompt` all abort with a clear message. A `[phases.X]` table for a phase that isn't in the pipeline is ignored.

### Limits

All runtime limits live in an optional `[limits]` table. Defaults match the values the pipeline always used; unknown keys or out-of-range values abort before the run with a clear message:

```toml
[limits]
provider_timeout_seconds = 600   # per provider subprocess call
max_ram_pct = 75.0               # worker fan-out RAM threshold
max_cost_usd = 5.0               # absent = no cap
default_max_iterations = 3       # gate re-run cap (a phase's max_iterations wins)
prev_output_chars = 8000         # context passed to single-agent stages
worker_prev_output_chars = 6000  # context passed to each parallel worker
evaluation_output_chars = 4000   # stage output shown to the quality-gate evaluator
commit_context_chars = 3000      # context for the commit/PR generator
diff_stat_chars = 1500           # diff stat shown to the commit/PR generator
feedback_chars = 3000            # gate feedback injected into the re-run
```

When `max_cost_usd` is set, accumulated cost is checked at every stage boundary and before each gate loop-back; the run stops with "Cost cap reached" once it is hit. A parallel fan-out can overshoot the cap before the next boundary check — the cap bounds stage starts, not in-flight workers. Each stage's completion line in the activity log shows that stage's cost delta.

### Confirmations

The `[confirm]` table adds user checkpoints to an otherwise fully autonomous run:

```toml
[confirm]
phases = ["Commit & PR"]   # pause before these phases; Commit & PR shows git status + diff stat
review_tasks = true        # review/exclude subtasks after Decomposition, before the worker fan-out
step = false               # pause after every completed stage (same as the --step flag)
```

Cancelling at any checkpoint stops the run. Stage pills stay clickable, so you can resume from the stopped phase.

### Overriding the internal prompts

Besides the per-stage `skill`/`prompt` overrides, the two internal agents accept custom prompts:

- **Decomposition** — `skill`/`prompt` on `[phases.Decomposition]`. The template receives `{prompt}` (the task) and `{prev_output}` (the plan) and must keep the JSON-array output contract (`id`, `description`, `files`); non-JSON output falls back to a single subtask.
- **Quality-gate evaluator** — `eval_prompt` or `eval_skill` (exactly one, only on the gate phase). The template receives the stage output as `{prev_output}` and must answer only `yes` (iterate) or `no` (proceed).

```toml
[phases."Code Quality"]
eval_prompt = "Does this output contain blocking bugs? Answer only yes or no.\n\n{prev_output}"
```

### Full example

```toml
pipeline = ["Planning", "Decomposition", "Implementation", "Tests & Validation", "Code Quality", "Commit & PR"]

[defaults]
provider = "claude"
model = ""
skip_permissions = true

[limits]
provider_timeout_seconds = 900
max_cost_usd = 10.0

[confirm]
phases = ["Commit & PR"]
review_tasks = true

[artifacts]
enabled = true

[phases."Code Quality"]
provider = "codex"
model = "gpt-5.1-codex"
max_iterations = 2
eval_prompt = "Real blocking issues? Answer only yes or no.\n\n{prev_output}"
```

### Run artifacts

Set `[artifacts] enabled = true` to persist every run to disk for later inspection — the full output of each stage (not just the 300-char log preview), the original prompt, and the run stats:

```toml
[artifacts]
enabled = true               # default: false
dir = ".step-by-step/runs"   # relative to the target repo (default)
```

Each run writes `<repo>/.step-by-step/runs/<timestamp>/` containing `prompt.txt`, one `NN-<stage>.md` per stage (provider, model, status, elapsed, full output or error; gate re-runs of a stage append `-2`, `-3`…), and `run.json` (calls, cost, stage time, outcome: completed/failed/stopped). Add `.step-by-step/runs/` to the target repo's `.gitignore`.

### Safety

By default the pipeline runs every provider fully autonomous — no sandbox, no approval prompts (`--dangerously-skip-permissions` for Claude, `--dangerously-bypass-approvals-and-sandbox` for Codex, `--yolo` for Gemini). With a multi-provider config that is up to three agents with full read/write/execute access to the target repository. Run it on a throwaway branch or an isolated clone.

Both behaviors are configurable, in `[defaults]` or per phase (the phase table wins):

```toml
[defaults]
skip_permissions = false   # omit the autonomy flag: the CLI runs in its own approval/sandbox mode
extra_args = []            # raw arguments appended to the provider command

[phases.Implementation]
skip_permissions = true    # this phase keeps full autonomy
```

With `skip_permissions = false` the provider CLI falls back to its own approval or sandbox mode. The pipeline runs non-interactively, so there is no terminal to approve actions on — a supervised run may be unable to edit files. Defaults are unchanged: without these keys, every provider runs fully autonomous as before.

---

## Usage

**pip install:**
```bash
# Run against the current directory
pipeline

# Run against a specific repository
pipeline /path/to/your/repo

# Load a prompt from a file and start immediately
pipeline /path/to/your/repo -f prompt.txt

# Validate the config and print the resolved pipeline, without running anything
pipeline /path/to/your/repo --check

# Step mode: pause after each completed stage until you confirm
pipeline /path/to/your/repo --step
```

**uvx (no install):**
```bash
uvx --from step-by-step-cli pipeline
uvx --from step-by-step-cli pipeline /path/to/your/repo
```

**From source:**
```bash
uv run pipeline
uv run pipeline /path/to/your/repo
uv run pipeline /path/to/your/repo -f prompt.txt
```

Type your task in the input area at the bottom and press `Ctrl+Enter` to start.

### Keyboard shortcuts

| Key | Action |
|---|---|
| `Ctrl+Enter` | Submit prompt and run the pipeline |
| `Ctrl+L` | Clear the activity log |
| `Ctrl+E` | Export log to `pipeline_log_<timestamp>.txt` |
| `Ctrl+X` | Cancel the running pipeline |
| `Ctrl+C` | Quit |

### Re-running from a specific stage

Once a run completes, every stage pill in the header becomes clickable. Click any stage to **re-run from that point forward**, reusing all prior context — useful for retrying a failed stage or iterating on implementation without re-planning.

---

## UI layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Plan  │  Decomp  │  Impl ⇶  │  Tests ⇶  │  Quality  │  PR    │  ← stage bar
├─────────────────────────────────────────────────────────────────┤
│  > Describe your task…                                          │  ← prompt input
├──────────────────────────────┬──────────────────────────────────┤
│  ● Planning                  │                                  │
│                              │         Activity log             │
│      Streaming pane          │   (full chronological history)   │
│  (live output from active    │                                  │
│   stage or worker)           │                                  │
├──────────────────────────────┴──────────────────────────────────┤
│  ^p palette  ^l Clear Log  ctrl+↵ Run  ^e Export Log  ^m Monitor  ^x Cancel        Calls: 4  |  Cost: $0.0234  |  Time: 1m 20s  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project structure

```
app/
├── __main__.py      Entry point
├── tui.py           PipelineApp (Textual App), CLI flags (--check, --step), main()
├── runner.py        PipelineRunnerMixin: dispatch loop, reruns, checkpoints, cost cap
├── pipeline.py      Stage runners: run_stage() and run_stage_parallel()
├── stages.py        Stage dataclass and the built-in stage registry
├── agents.py        Decomposition manager agent
├── evaluation.py    Quality-gate evaluator
├── workers.py       Parallel workers and RAM-aware concurrency control
├── git.py           Git/gh subprocess helpers and Commit & PR stage runner
├── config.py        TOML config: providers, pipeline, [limits], [confirm], [artifacts]
├── skills.py        SKILL.md resolution and prompt-token rendering
├── prompts.py       Stage and internal-agent prompt templates
├── check.py         `pipeline --check` config dry-run
├── confirm.py       Confirmation and subtask-review modals
├── artifacts.py     Per-run artifacts under .step-by-step/runs/
├── models.py        Shared data classes (Task, WorkerResult, PipelineStats)
├── widgets.py       StagePill and SystemMonitor TUI widgets
└── providers/       claude / codex / gemini CLI adapters
```

---

## Safety

By default the pipeline invokes each provider with its autonomy flag (e.g. `claude --dangerously-skip-permissions`) so agents can read and write files unattended — this is configurable per provider via `skip_permissions` (see [Safety](#safety) under Configuration). **Only point it at repositories where you trust the output.** Review the diff before the PR stage commits, or enable a `[confirm]` checkpoint on `Commit & PR` to see it in-app.

Each subprocess runs with a timeout (10 minutes by default, `[limits].provider_timeout_seconds`) and is cleaned up unconditionally on exit — even on errors or cancellation — so stalled provider processes do not accumulate.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

---

## License

MIT © Valentin Dutra — see [LICENSE](LICENSE)
