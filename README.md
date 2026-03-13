# DevPipeline - LLM Development Pipeline UI

A GitHub Actions-style visual dashboard for LLM-driven development workflows built with Langflow. Enter a task/prompt, watch it flow through stages (code generation, tests, validation, PR creation), with each step receiving full prior context automatically.

## Architecture

```
Task Prompt --> Code Gen Prompt --> Code LLM --> Code Output
                                                     |
                 Test Gen Prompt <-- Code Output --> Test LLM --> Test Output
                                                                      |
                                          Validation <-- Test Output + Code Output
                                               |
                                          Git PR Creator --> PR URL Output
```

**8 nodes, 11 edges** - full context propagation through the pipeline.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- API keys: OpenAI (or compatible), GitHub PAT
- 8GB RAM minimum

## Quick Start

```bash
# 1. Clone and install
git clone <repo-url> && cd step-by-step
uv sync

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Start Langflow
./scripts/start.sh
# Open http://localhost:7860

# 4. Import flow
uv run python scripts/setup_flow.py
```

## Project Structure

```
.
├── components/          # Custom Langflow components
│   ├── validator.py     # Code validation logic
│   └── git_tool.py      # GitHub PR creator
├── prompts/             # Prompt templates (versioned)
│   ├── code_generation.txt
│   ├── test_generation.txt
│   └── review.txt
├── flows/               # Exported Langflow JSON flows
│   └── dev_pipeline.json
├── scripts/
│   ├── start.sh         # Startup script
│   ├── setup_flow.py    # Create flow via API
│   ├── serve_api.py     # API client
│   ├── export_flow.sh   # Backup flow
│   ├── test_components.py  # Offline tests
│   └── test_pipeline.py    # E2E API tests
├── pyproject.toml       # uv project config & dependencies
├── uv.lock              # Locked dependency versions
├── Dockerfile
└── docker-compose.yml
```

## Pipeline Nodes

| Node | Type | Description |
|------|------|-------------|
| Task Prompt | TextInput | Entry point - your development task |
| Code Gen Prompt | Prompt | Template for code generation |
| Code Generator | LLM (GPT-4o) | Generates production-ready code |
| Test Gen Prompt | Prompt | Template for test generation |
| Test Generator | LLM (GPT-4o) | Generates comprehensive tests |
| Code Validator | Custom | Lint, test count, coverage checks |
| GitHub PR Creator | Custom | Creates branch + PR via PyGitHub |
| Pipeline Output | ChatOutput | Displays final PR URL |

## API Usage

After clicking "Serve" in Langflow:

```bash
# List flows
uv run python scripts/serve_api.py --list-flows

# Run pipeline
uv run python scripts/serve_api.py "Implement POST /login endpoint with JWT"

# Or via curl
curl -X POST http://localhost:7860/api/v1/run/{flow_id} \
  -H "Content-Type: application/json" \
  -d '{"input_value": "Your task here", "output_type": "chat", "input_type": "chat"}'
```

## Docker Deployment

```bash
docker compose up -d
# Access at http://localhost:7860
```

## Testing

```bash
# Offline component tests (no server needed)
uv run python scripts/test_components.py

# E2E tests (server must be running)
uv run python scripts/test_pipeline.py
```

## Configuration

All sensitive values via environment variables:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for LLM nodes |
| `GITHUB_TOKEN` | GitHub PAT for PR creation |
| `LANGFLOW_SECRET_KEY` | Server security key |
