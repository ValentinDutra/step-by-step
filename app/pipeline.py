"""Pipeline stage definitions and runner."""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum


class StageStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Stage:
    name: str
    prompt_template: str
    status: StageStatus = StageStatus.PENDING
    elapsed: float = 0.0
    output: str = ""
    error: str = ""
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


STAGES = [
    Stage(
        name="Planning",
        prompt_template=(
            "You are a senior software architect. Given the following task, create a detailed implementation plan.\n\n"
            "TASK: {prompt}\n\n"
            "Create:\n"
            "1. A numbered list of implementation tasks (ordered by dependency)\n"
            "2. For each task: what files to create/modify, key decisions, and acceptance criteria\n"
            "3. Identify risks or ambiguities\n\n"
            "Be specific and actionable. Output the plan in markdown."
        ),
    ),
    Stage(
        name="Implementation",
        prompt_template=(
            "You are a senior software engineer. Implement the following plan.\n\n"
            "ORIGINAL TASK: {prompt}\n\n"
            "PLAN:\n{prev_output}\n\n"
            "Write clean, production-ready code. Follow the plan step by step.\n"
            "Use best practices, proper error handling, and clear naming.\n"
            "Output the complete implementation."
        ),
    ),
    Stage(
        name="Tests & Validation",
        prompt_template=(
            "You are a senior QA engineer. Write comprehensive tests for the implementation below.\n\n"
            "ORIGINAL TASK: {prompt}\n\n"
            "IMPLEMENTATION:\n{prev_output}\n\n"
            "Create:\n"
            "1. Unit tests covering all functions/methods\n"
            "2. Edge cases and error scenarios\n"
            "3. Integration tests where applicable\n\n"
            "Use the appropriate test framework for the language."
        ),
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
        name="Docs & Test Run",
        prompt_template=(
            "You are a senior engineer. Finalize documentation and verify tests.\n\n"
            "ORIGINAL TASK: {prompt}\n\n"
            "CURRENT STATE:\n{prev_output}\n\n"
            "Do:\n"
            "1. Add/update docstrings and inline comments where needed\n"
            "2. Run all tests and fix any failures\n"
            "3. Ensure all public APIs are documented\n\n"
            "Output the final code with docs and test results."
        ),
    ),
    Stage(
        name="Review & PR",
        prompt_template=(
            "You are a senior engineer doing a final review before creating a PR.\n\n"
            "ORIGINAL TASK: {prompt}\n\n"
            "FINAL STATE:\n{prev_output}\n\n"
            "Do:\n"
            "1. Final review: check everything is complete and correct\n"
            "2. Write a PR title and description (summary + test plan)\n"
            "3. List all files changed with a one-line description each\n\n"
            "Output the PR description and a summary of all changes."
        ),
    ),
]


def create_stages() -> list[Stage]:
    """Create a fresh set of pipeline stages."""
    return [
        Stage(name=s.name, prompt_template=s.prompt_template)
        for s in STAGES
    ]


async def run_stage(stage: Stage, prompt: str, prev_output: str, working_dir: str) -> str:
    """Run a single pipeline stage using Claude Code CLI."""
    stage.start()

    full_prompt = stage.prompt_template.format(
        prompt=prompt,
        prev_output=prev_output[:8000],  # Truncate to avoid token limits
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            "--print",
            "--dangerously-skip-permissions",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )

        stdout, stderr = await proc.communicate(input=full_prompt.encode())

        if proc.returncode != 0:
            error_msg = stderr.decode().strip() or f"Exit code {proc.returncode}"
            stage.fail(error_msg)
            return ""

        output = stdout.decode().strip()
        stage.complete(output)
        return output

    except FileNotFoundError:
        stage.fail("'claude' CLI not found. Install Claude Code: npm install -g @anthropic-ai/claude-code")
        return ""
    except Exception as e:
        stage.fail(str(e))
        return ""
