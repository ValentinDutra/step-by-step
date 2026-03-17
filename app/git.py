"""Git and GitHub CLI helpers for the Commit & PR stage."""

import asyncio
import json

from app.claude import call_claude
from app.stages import Stage


async def _git(working_dir: str, *args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=working_dir,
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode().strip(), err.decode().strip()


async def _gh(working_dir: str, *args: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "gh", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=working_dir,
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode().strip(), err.decode().strip()


async def create_branch(
    prompt: str,
    working_dir: str,
    on_log=None,
) -> str:
    """Ask Claude to pick a branch name based on the task and create it."""
    branch_prompt = (
        "Given the following task, output ONLY a git branch name — no explanation, no punctuation, nothing else.\n"
        "Rules:\n"
        "- Format: type/short-kebab-description\n"
        "- type: feat, fix, docs, refactor, test, or chore\n"
        "- Max 50 chars total, lowercase, hyphens only (no extra slashes)\n"
        "- Example: feat/add-user-authentication\n\n"
        f"TASK: {prompt}"
    )

    success, output, _ = await call_claude(branch_prompt, working_dir)
    if not success:
        return ""

    branch_name = output.strip().strip("`").split("\n")[0].strip()

    rc, _, err = await _git(working_dir, "checkout", "-b", branch_name)
    if rc != 0:
        if on_log:
            on_log(f"git checkout -b failed: {err}")
        return ""

    if on_log:
        on_log(f"branch: {branch_name}")
    return branch_name


async def run_commit_pr_stage(
    stage: Stage,
    prompt: str,
    prev_output: str,
    working_dir: str,
    on_stream=None,
    on_log=None,
) -> str:
    """Commit changes with conventional commits and open a GitHub PR."""
    stage.start()
    lines: list[str] = []

    def _log(msg: str) -> None:
        lines.append(msg)
        if on_log:
            on_log(msg)

    _, diff_stat, _ = await _git(working_dir, "diff", "HEAD", "--stat")
    if not diff_stat:
        _, diff_stat, _ = await _git(working_dir, "diff", "--stat")
    if not diff_stat:
        _, diff_stat, _ = await _git(working_dir, "status", "--short")

    _, current_branch, _ = await _git(working_dir, "rev-parse", "--abbrev-ref", "HEAD")

    conv_prompt = stage.prompt_template.format(
        prompt=prompt,
        prev_output=prev_output[:3000],
        diff_stat=diff_stat[:1500] if diff_stat else "No changes detected yet",
    )

    success, conv_output, _ = await call_claude(conv_prompt, working_dir, on_stream=on_stream)
    if not success:
        stage.fail(f"Failed to generate commit info: {conv_output}")
        return ""

    try:
        text = conv_output.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        pr_data = json.loads(text)
        commits: list[dict] = pr_data.get("commits", [])
        pr_title: str = pr_data.get("pr_title", f"feat: {prompt[:60]}")
        pr_body: str = pr_data.get("pr_body", f"## Summary\n- {prompt}\n\n## Test Plan\n- [ ] Manual testing")
    except (json.JSONDecodeError, KeyError, TypeError):
        commits = [{"type": "feat", "scope": "", "message": prompt[:60]}]
        pr_title = f"feat: {prompt[:60]}"
        pr_body = f"## Summary\n- {prompt}\n\n## Test Plan\n- [ ] Manual testing"

    rc, _, err = await _git(working_dir, "add", "-A")
    if rc != 0:
        stage.fail(f"git add failed: {err}")
        return ""

    _, status_out, _ = await _git(working_dir, "status", "--porcelain")
    if status_out:
        for c in commits:
            ctype = c.get("type", "feat").strip()
            scope = c.get("scope", "").strip()
            msg = c.get("message", "update").strip()
            commit_msg = f"{ctype}({scope}): {msg}" if scope else f"{ctype}: {msg}"

            rc, _, err = await _git(working_dir, "commit", "-m", commit_msg)
            if rc != 0 and "nothing to commit" not in err and "nothing added" not in err:
                stage.fail(f"git commit failed: {err}")
                return "\n".join(lines)
            _log(f"commit: {commit_msg}")
    else:
        _log("nothing to commit — working tree clean")

    rc, pr_url, err = await _gh(
        working_dir,
        "pr", "create",
        "--title", pr_title,
        "--body", pr_body,
    )
    if rc != 0:
        if "already exists" in err.lower() or "pull request" in err.lower():
            _log(f"PR already exists for branch '{current_branch}'")
        else:
            stage.fail(f"gh pr create failed: {err}")
            return "\n".join(lines)
    else:
        _log(f"PR created: {pr_url}")

    result = "\n".join(lines)
    stage.complete(result)
    return result
