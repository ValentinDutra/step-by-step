"""Pipeline stage definitions and configuration."""

import time
from dataclasses import dataclass, field
from enum import Enum

from app.models import Task


class StageStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Stage:
    name: str
    prompt_template: str
    iterable: bool = False
    parallel: bool = False
    worker_prompt_template: str = ""
    status: StageStatus = StageStatus.PENDING
    elapsed: float = 0.0
    output: str = ""
    error: str = ""
    tasks: list[Task] = field(default_factory=list)
    _start_time: float = 0.0

    def start(self):
        self.status = StageStatus.RUNNING
        self._start_time = time.time()

    def complete(self, output: str):
        self.elapsed = time.time() - self._start_time
        self.output = output
        self.status = StageStatus.COMPLETED

    def fail(self, error: str):
        self.elapsed = time.time() - self._start_time
        self.error = error
        self.status = StageStatus.FAILED


MAX_ITERATIONS = 3
MAX_CONCURRENT_WORKERS = 4

STAGES = [
    Stage(
        name="Planning",
        prompt_template=(
            "You are a senior software architect. Given the following task, create a detailed implementation plan.\n\n"
            "TASK: {prompt}\n\n"
            "{iteration_context}"
            "Create:\n"
            "1. A numbered list of implementation tasks (ordered by dependency)\n"
            "2. For each task: what files to create/modify, key decisions, and acceptance criteria\n"
            "3. Identify risks or ambiguities\n\n"
            "Be specific and actionable. Output the plan in markdown."
        ),
        iterable=True,
    ),
    Stage(
        name="Decomposition",
        prompt_template="",
        parallel=False,
    ),
    Stage(
        name="Implementation",
        prompt_template=(
            "You are a senior software engineer. Implement the following plan.\n\n"
            "ORIGINAL TASK: {prompt}\n\n"
            "PLAN:\n{prev_output}\n\n"
            "{iteration_context}"
            "Write clean, production-ready code. Follow the plan step by step.\n"
            "Use best practices, proper error handling, and clear naming.\n"
            "Output the complete implementation."
        ),
        worker_prompt_template=(
            "You are a senior software engineer working as part of a team.\n"
            "You are responsible for ONE specific subtask.\n\n"
            "ORIGINAL TASK: {prompt}\n\n"
            "YOUR SUBTASK: {task_description}\n"
            "FILES TO WORK ON: {task_files}\n\n"
            "FULL PLAN FOR CONTEXT:\n{prev_output}\n\n"
            "{iteration_context}"
            "Implement ONLY your subtask. Write clean, production-ready code.\n"
            "Use best practices, proper error handling, and clear naming.\n"
            "Output the complete implementation for your subtask."
        ),
        iterable=True,
        parallel=True,
    ),
    Stage(
        name="Tests & Validation",
        prompt_template=(
            "You are a senior QA engineer. Write comprehensive tests for the implementation below.\n\n"
            "ORIGINAL TASK: {prompt}\n\n"
            "IMPLEMENTATION:\n{prev_output}\n\n"
            "{iteration_context}"
            "Create:\n"
            "1. Unit tests covering all functions/methods\n"
            "2. Edge cases and error scenarios\n"
            "3. Integration tests where applicable\n\n"
            "Use the appropriate test framework for the language.\n"
            "At the end, output a section called '## Issues Found' listing any problems.\n"
            "If there are no issues, write '## Issues Found\\nNone — all tests pass.'"
        ),
        worker_prompt_template=(
            "You are a senior QA engineer working as part of a team.\n"
            "You are responsible for testing ONE specific subtask.\n\n"
            "ORIGINAL TASK: {prompt}\n\n"
            "YOUR SUBTASK TO TEST: {task_description}\n"
            "FILES INVOLVED: {task_files}\n\n"
            "IMPLEMENTATION:\n{prev_output}\n\n"
            "{iteration_context}"
            "Create comprehensive tests for your subtask:\n"
            "1. Unit tests covering all functions/methods\n"
            "2. Edge cases and error scenarios\n"
            "3. Integration tests where applicable\n\n"
            "At the end, output a section called '## Issues Found' listing any problems.\n"
            "If there are no issues, write '## Issues Found\\nNone — all tests pass.'"
        ),
        iterable=True,
        parallel=True,
    ),
    Stage(
        name="Code Quality",
        prompt_template=(
            "You are a senior code reviewer. Review the implementation for quality issues.\n\n"
            "ORIGINAL TASK: {prompt}\n\n"
            "IMPLEMENTATION:\n{prev_output}\n\n"
            "Check and fix:\n"
            "1. Technical debt and code smells\n"
            "2. Security vulnerabilities\n"
            "3. Performance issues\n"
            "4. Naming, structure, and readability\n"
            "5. DRY violations\n\n"
            "Output the improved code with explanations of changes."
        ),
    ),
    Stage(
        name="Documentation",
        prompt_template=(
            "You are a technical writer. Generate comprehensive documentation for the implemented feature.\n\n"
            "ORIGINAL TASK: {prompt}\n\n"
            "IMPLEMENTATION:\n{prev_output}\n\n"
            "Produce:\n"
            "1. A README section — what the feature does, usage examples, configuration options\n"
            "2. Inline JSDoc / docstrings for every public function or class (show the updated code)\n"
            "3. API reference if there are new endpoints (method, path, request body, response)\n"
            "4. Migration or setup notes if applicable\n\n"
            "Format everything as markdown. Be concise and developer-friendly."
        ),
    ),
    Stage(
        name="Commit & PR",
        prompt_template=(
            "You are a senior engineer preparing a pull request.\n\n"
            "ORIGINAL TASK: {prompt}\n\n"
            "IMPLEMENTATION SUMMARY:\n{prev_output}\n\n"
            "GIT DIFF STAT:\n{diff_stat}\n\n"
            "Generate conventional commit messages and a PR description.\n"
            "Output ONLY a JSON object — no markdown fences, no extra text:\n"
            "{{\n"
            '  "commits": [\n'
            '    {{"type": "feat|fix|docs|refactor|test|chore", "scope": "module-or-empty", "message": "imperative lowercase description"}}\n'
            "  ],\n"
            '  "pr_title": "type(scope): short description",\n'
            '  "pr_body": "## Summary\\n- bullet\\n\\n## Test Plan\\n- [ ] item"\n'
            "}}\n\n"
            "Conventional commit rules:\n"
            "- feat: new user-visible feature\n"
            "- fix: bug fix\n"
            "- docs: documentation only\n"
            "- refactor: no behaviour change\n"
            "- test: adding or fixing tests\n"
            "- chore: tooling, deps, config\n"
            "- scope: affected module / package (omit if unclear)\n"
            "- message: imperative mood, lowercase, ≤72 chars, no trailing period\n"
            "- Group tightly related file changes into one commit\n"
            "- Separate docs changes into their own docs commit if docs files were modified"
        ),
    ),
]


def create_stages() -> list[Stage]:
    """Create a fresh set of pipeline stages."""
    return [
        Stage(
            name=s.name,
            prompt_template=s.prompt_template,
            iterable=s.iterable,
            parallel=s.parallel,
            worker_prompt_template=s.worker_prompt_template,
        )
        for s in STAGES
    ]


def has_issues(output: str) -> bool:
    """Check if stage output indicates issues that need another iteration."""
    lower = output.lower()
    if "## issues found" in lower:
        idx = lower.index("## issues found")
        section = lower[idx : idx + 200]
        if "none" in section.split("\n", 2)[1] if "\n" in section else False:
            return False
        return True
    return False
