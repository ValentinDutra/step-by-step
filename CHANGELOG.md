# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-06-11

### Added

- **Multi-provider pipeline** — Codex (`codex`) and Gemini (`gemini`) CLI providers alongside Claude, with per-phase `provider`/`model` selection in `step-by-step.toml` (#16).
- **Configurable pipeline** — a `pipeline` array to reorder phases, drop built-ins, or add custom prompt-only phases (`kind = "simple"` with `skill` or `prompt`); per-phase `max_iterations`; fail-fast structural validation (#17).
- **`[limits]` config section** — `provider_timeout_seconds`, `max_ram_pct`, `max_cost_usd`, `default_max_iterations`, and every context-truncation size (`prev_output_chars`, `worker_prev_output_chars`, `evaluation_output_chars`, `commit_context_chars`, `diff_stat_chars`, `feedback_chars`). Unknown keys or out-of-range values abort before the run.
- **Cost cap** — with `max_cost_usd` set, the run stops at the next stage boundary once accumulated cost reaches the cap, and each stage's completion log line shows that stage's cost delta.
- **`pipeline --check`** — config dry-run: validates the TOML and prints the resolved pipeline (phase, kind, provider, model, prompt source), the effective limits, and the provider preflight, without calling any LLM. Exits 0/1.
- **`[confirm]` checkpoints** — `phases` pauses before the listed phases (Commit & PR additionally shows `git status` and `git diff --stat` so you see what will be committed); `review_tasks` opens a checkbox review of the decomposed subtasks before the parallel fan-out; `step` (or the `--step` flag) pauses after every completed stage.
- **`[artifacts]` run persistence** — each run writes `<repo>/.step-by-step/runs/<timestamp>/` with `prompt.txt`, one `NN-<stage>.md` per stage (full output or error; gate re-runs append `-2`, `-3`…), and `run.json` stats.
- **Internal prompt overrides** — the Decomposition prompt accepts the existing `skill`/`prompt` keys, and the quality-gate evaluator accepts `eval_prompt`/`eval_skill` on the gate phase.
- **Per-provider autonomy flags** — `skip_permissions = false` omits `--dangerously-skip-permissions` / `--dangerously-bypass-approvals-and-sandbox` / `--yolo`, and `extra_args` appends raw CLI arguments; both in `[defaults]` or per phase.
- **Ctrl+X** cancels the running pipeline, killing provider subprocesses and leaving every stage re-runnable.
- **CI** — GitHub Actions runs the test suite on every push to `main` and every pull request (#21).

### Changed

- The provider subprocess timeout is configurable (`provider_timeout_seconds`); it was previously fixed at 600 seconds.
- The final status distinguishes intentional stops (`⏹ Stopped` — user checkpoint or cost cap) from real failures (`✗ Failed`).
- With no new config keys, behavior is identical to 0.1.x: every new default equals the previous hardcoded value, and confirmations/artifacts are off by default.

### Removed

- The npm wrapper package. It only delegated to `uvx`/`pipx`, so it required a Python package runner anyway; install from PyPI via `uvx`, `pipx`, or `pip` instead. The package published on the npm registry stays at 0.1.2.

### Fixed

- Confirmation-modal bodies and task-review checkbox labels render raw LLM/git output literally; bracketed text such as `list[int]` is no longer swallowed as style markup.

## [0.1.2] - 2026-03-18

### Fixed

- npm package: include the README in the published package and correct the repository URL format.

## [0.1.0] - 2026-03-13

### Added

- Initial release: Textual TUI running a seven-stage Claude pipeline (Planning, Decomposition, parallel Implementation and Tests & Validation, Code Quality gate, Documentation, Commit & PR) with RAM-aware worker concurrency, live streaming, per-call cost tracking, log export, and click-to-rerun stage pills.
