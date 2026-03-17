#!/usr/bin/env node

const { execFileSync, spawnSync } = require("child_process");

const args = process.argv.slice(2);

function has(cmd) {
  try {
    execFileSync(cmd, ["--version"], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

if (has("uvx")) {
  const result = spawnSync("uvx", ["step-by-step-cli", ...args], { stdio: "inherit" });
  process.exit(result.status ?? 1);
} else if (has("pipx")) {
  const result = spawnSync("pipx", ["run", "step-by-step-cli", ...args], { stdio: "inherit" });
  process.exit(result.status ?? 1);
} else {
  console.error(
    "Error: requires 'uvx' or 'pipx'.\n" +
    "Install uv: https://docs.astral.sh/uv/getting-started/installation/"
  );
  process.exit(1);
}
