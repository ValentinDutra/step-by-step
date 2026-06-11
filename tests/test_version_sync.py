import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_pyproject_and_npm_versions_match():
    with open(REPO_ROOT / "pyproject.toml", "rb") as handle:
        python_version = tomllib.load(handle)["project"]["version"]
    npm_version = json.loads((REPO_ROOT / "npm" / "package.json").read_text())["version"]
    assert python_version == npm_version
