# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

When cutting a release, rename `[Unreleased]` to the version and date, then start
a fresh `[Unreleased]` section above it.

## [Unreleased]

### Added
- Codex CLI and Gemini CLI as alternative provider backends alongside Claude (#16).
- Per-phase provider and model selection via a `step-by-step.toml` config
  (`[defaults]` and `[phases."<Name>"]`), resolved with precedence
  `--config PATH` > project `step-by-step.toml` > `~/.config/step-by-step/config.toml`
  > built-in all-Claude default.
- `--config PATH` flag to point at an explicit config file.
- Provider binary preflight: a missing `claude`/`codex`/`gemini` CLI is reported
  before the first stage instead of mid-run.
- Fail-fast validation of unknown provider or phase names in the config.

### Changed
- Stage execution runs through an `LLMProvider` abstraction (`app/providers/`)
  instead of a single hardcoded `claude` call. With no config present, behavior is
  unchanged — every stage runs on Claude with cost reporting.
- The cost display tolerates providers that report no dollar figure (Codex, Gemini):
  the stats bar shows e.g. `$0.4200 (+2 n/a)`.

### Notes
- Codex runs through `codex exec`, which is rejected by ChatGPT-account models. Its
  success-path parser is derived from OpenAI's documented event schema and is not yet
  verified end-to-end against a live run; the error path and Gemini/Claude are verified.
- All providers run fully autonomous (no sandbox, no approval prompts). Run the
  pipeline on a throwaway branch or an isolated clone.

## [0.1.2]

- Baseline release: Claude-only multi-agent pipeline (Plan, Decompose, Implement,
  Test, Quality, Docs, Commit & PR).
