import os

from lfx.custom import Component
from lfx.io import MessageTextInput, Output, SecretStrInput
from langflow.schema.message import Message


class GitPRCreator(Component):
    display_name = "GitHub PR Creator"
    description = "Creates a GitHub Pull Request with generated code, tests, and validation results."

    inputs = [
        MessageTextInput(
            name="task_prompt",
            display_name="Task Prompt",
            info="The original task description.",
            required=True,
        ),
        MessageTextInput(
            name="code_output",
            display_name="Code Output",
            info="The generated code.",
            required=True,
        ),
        MessageTextInput(
            name="test_output",
            display_name="Test Output",
            info="The generated tests.",
            required=True,
        ),
        MessageTextInput(
            name="validation_output",
            display_name="Validation Output",
            info="The validation results.",
            required=True,
        ),
        MessageTextInput(
            name="repo_name",
            display_name="Repository",
            info="GitHub repository in format 'owner/repo'.",
            required=True,
        ),
        SecretStrInput(
            name="github_token",
            display_name="GitHub Token",
            info="GitHub Personal Access Token. Uses GITHUB_TOKEN env var if empty.",
            required=False,
        ),
    ]

    outputs = [
        Output(display_name="PR URL", name="pr_url", method="create_pr"),
    ]

    def create_pr(self) -> Message:
        token = self.github_token or os.environ.get("GITHUB_TOKEN", "")
        if not token:
            return Message(text="Error: No GitHub token provided. Set GITHUB_TOKEN env var or provide in node config.")

        try:
            from github import Github
        except ImportError:
            return Message(text="Error: PyGithub not installed. Run: pip install PyGithub")

        task = self.task_prompt
        code = self.code_output
        tests = self.test_output
        validation = self.validation_output

        g = Github(token)
        repo = g.get_repo(self.repo_name)

        branch_slug = task[:30].replace(" ", "-").lower()
        branch_slug = "".join(c for c in branch_slug if c.isalnum() or c == "-")
        branch_name = f"feature/auto-{branch_slug}"

        main_sha = repo.get_branch("main").commit.sha
        repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=main_sha)

        # Parse code blocks and create files
        files_created = self._parse_and_create_files(repo, branch_name, code, tests)

        pr_body = (
            f"## Task\n{task}\n\n"
            f"## Generated Code\n```\n{code}\n```\n\n"
            f"## Tests\n```\n{tests}\n```\n\n"
            f"## Validation\n{validation}\n\n"
            f"## Files Created\n" + "\n".join(f"- `{f}`" for f in files_created)
        )

        pr = repo.create_pull(
            title=f"Auto: {task}",
            body=pr_body,
            head=branch_name,
            base="main",
        )

        return Message(text=pr.html_url)

    def _parse_and_create_files(self, repo, branch_name, code, tests):
        files_created = []
        for content, prefix in [(code, ""), (tests, "")]:
            lines = content.split("\n")
            current_file = None
            current_content = []
            in_code_block = False

            for line in lines:
                if line.startswith("```") and not in_code_block:
                    if current_file and current_content:
                        file_content = "\n".join(current_content)
                        try:
                            repo.create_file(
                                current_file,
                                f"Auto: add {current_file}",
                                file_content,
                                branch=branch_name,
                            )
                            files_created.append(current_file)
                        except Exception:
                            pass
                        current_content = []
                    in_code_block = True
                elif line.startswith("```") and in_code_block:
                    in_code_block = False
                elif in_code_block:
                    current_content.append(line)
                elif "/" in line and ("." in line.split("/")[-1]):
                    current_file = prefix + line.strip()
                    current_content = []

            if current_file and current_content:
                file_content = "\n".join(current_content)
                try:
                    repo.create_file(
                        current_file,
                        f"Auto: add {current_file}",
                        file_content,
                        branch=branch_name,
                    )
                    files_created.append(current_file)
                except Exception:
                    pass

        return files_created
