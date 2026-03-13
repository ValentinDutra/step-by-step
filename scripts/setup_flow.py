"""
Setup script to create the DevPipeline flow in Langflow.

This script creates the complete LLM Development Pipeline flow programmatically
by importing a flow definition via Langflow's API.

Usage:
    python scripts/setup_flow.py [--port 7860]

Prerequisites:
    - Langflow server must be running
    - OPENAI_API_KEY env var set (or update the flow after import)
"""

import argparse
import json
import sys
import urllib.request
import urllib.error

# Read prompt templates from files
def read_prompt(filename):
    try:
        with open(f"prompts/{filename}") as f:
            return f.read().strip()
    except FileNotFoundError:
        return f"[Prompt template not found: prompts/{filename}]"


def build_flow():
    """Build the DevPipeline flow definition."""
    code_gen_prompt = read_prompt("code_generation.txt")
    test_gen_prompt = read_prompt("test_generation.txt")

    # Read custom component source code
    with open("components/validator.py") as f:
        validator_code = f.read()
    with open("components/git_tool.py") as f:
        git_tool_code = f.read()

    flow = {
        "name": "DevPipeline",
        "description": "LLM Development Pipeline - GitHub Actions-style visual dashboard for LLM-driven development workflows",
        "data": {
            "nodes": [
                # Node 1: Task Input
                {
                    "id": "TextInput-TaskPrompt",
                    "type": "genericNode",
                    "position": {"x": 0, "y": 200},
                    "data": {
                        "id": "TextInput-TaskPrompt",
                        "display_name": "Task Prompt",
                        "type": "TextInput",
                        "node": {
                            "template": {
                                "input_value": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "Text",
                                    "multiline": True,
                                    "input_types": ["Message"],
                                    "placeholder": "Add user login endpoint with JWT",
                                }
                            },
                            "description": "Enter your development task/prompt here.",
                            "display_name": "Task Prompt",
                            "outputs": [
                                {
                                    "name": "text",
                                    "display_name": "Text",
                                    "types": ["Message"],
                                    "method": "text_response",
                                }
                            ],
                        },
                    },
                },
                # Node 2a: Code Generation Prompt
                {
                    "id": "Prompt-CodeGen",
                    "type": "genericNode",
                    "position": {"x": 400, "y": 100},
                    "data": {
                        "id": "Prompt-CodeGen",
                        "display_name": "Code Gen Prompt",
                        "type": "Prompt",
                        "node": {
                            "template": {
                                "template": {
                                    "type": "str",
                                    "value": code_gen_prompt,
                                    "display_name": "Template",
                                    "multiline": True,
                                }
                            },
                            "description": "Prompt template for code generation.",
                            "display_name": "Code Gen Prompt",
                            "outputs": [
                                {
                                    "name": "prompt",
                                    "display_name": "Prompt Message",
                                    "types": ["Message"],
                                    "method": "build_prompt",
                                }
                            ],
                        },
                    },
                },
                # Node 2b: Code Generation LLM
                {
                    "id": "LLM-CodeGen",
                    "type": "genericNode",
                    "position": {"x": 800, "y": 100},
                    "data": {
                        "id": "LLM-CodeGen",
                        "display_name": "Code Generator",
                        "type": "LanguageModelComponent",
                        "node": {
                            "template": {
                                "model": {
                                    "type": "str",
                                    "value": "gpt-4o",
                                    "display_name": "Model Name",
                                },
                                "api_key": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "OpenAI API Key",
                                    "password": True,
                                },
                                "input_value": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "Input",
                                    "input_types": ["Message"],
                                },
                                "system_message": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "System Message",
                                    "input_types": ["Message"],
                                },
                            },
                            "description": "LLM for code generation.",
                            "display_name": "Code Generator",
                            "outputs": [
                                {
                                    "name": "text_output",
                                    "display_name": "Code Output",
                                    "types": ["Message"],
                                    "method": "text_response",
                                }
                            ],
                        },
                    },
                },
                # Node 3a: Test Generation Prompt
                {
                    "id": "Prompt-TestGen",
                    "type": "genericNode",
                    "position": {"x": 1200, "y": 100},
                    "data": {
                        "id": "Prompt-TestGen",
                        "display_name": "Test Gen Prompt",
                        "type": "Prompt",
                        "node": {
                            "template": {
                                "template": {
                                    "type": "str",
                                    "value": test_gen_prompt,
                                    "display_name": "Template",
                                    "multiline": True,
                                }
                            },
                            "description": "Prompt template for test generation.",
                            "display_name": "Test Gen Prompt",
                            "outputs": [
                                {
                                    "name": "prompt",
                                    "display_name": "Prompt Message",
                                    "types": ["Message"],
                                    "method": "build_prompt",
                                }
                            ],
                        },
                    },
                },
                # Node 3b: Test Generation LLM
                {
                    "id": "LLM-TestGen",
                    "type": "genericNode",
                    "position": {"x": 1600, "y": 100},
                    "data": {
                        "id": "LLM-TestGen",
                        "display_name": "Test Generator",
                        "type": "LanguageModelComponent",
                        "node": {
                            "template": {
                                "model": {
                                    "type": "str",
                                    "value": "gpt-4o",
                                    "display_name": "Model Name",
                                },
                                "api_key": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "OpenAI API Key",
                                    "password": True,
                                },
                                "input_value": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "Input",
                                    "input_types": ["Message"],
                                },
                                "system_message": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "System Message",
                                    "input_types": ["Message"],
                                },
                            },
                            "description": "LLM for test generation.",
                            "display_name": "Test Generator",
                            "outputs": [
                                {
                                    "name": "text_output",
                                    "display_name": "Test Output",
                                    "types": ["Message"],
                                    "method": "text_response",
                                }
                            ],
                        },
                    },
                },
                # Node 4: Validation (Custom Component)
                {
                    "id": "CustomComponent-Validator",
                    "type": "genericNode",
                    "position": {"x": 2000, "y": 200},
                    "data": {
                        "id": "CustomComponent-Validator",
                        "display_name": "Code Validator",
                        "type": "CustomComponent",
                        "node": {
                            "template": {
                                "code": {
                                    "type": "code",
                                    "value": validator_code,
                                    "display_name": "Code",
                                },
                                "code_output": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "Code Output",
                                    "input_types": ["Message"],
                                },
                                "test_output": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "Test Output",
                                    "input_types": ["Message"],
                                },
                            },
                            "description": "Validates generated code and tests.",
                            "display_name": "Code Validator",
                            "outputs": [
                                {
                                    "name": "validation_result",
                                    "display_name": "Validation Result",
                                    "types": ["Message"],
                                    "method": "validate",
                                }
                            ],
                        },
                    },
                },
                # Node 5: GitHub PR Creator (Custom Component)
                {
                    "id": "CustomComponent-GitPR",
                    "type": "genericNode",
                    "position": {"x": 2400, "y": 200},
                    "data": {
                        "id": "CustomComponent-GitPR",
                        "display_name": "GitHub PR Creator",
                        "type": "CustomComponent",
                        "node": {
                            "template": {
                                "code": {
                                    "type": "code",
                                    "value": git_tool_code,
                                    "display_name": "Code",
                                },
                                "task_prompt": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "Task Prompt",
                                    "input_types": ["Message"],
                                },
                                "code_output": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "Code Output",
                                    "input_types": ["Message"],
                                },
                                "test_output": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "Test Output",
                                    "input_types": ["Message"],
                                },
                                "validation_output": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "Validation Output",
                                    "input_types": ["Message"],
                                },
                                "repo_name": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "Repository",
                                },
                                "github_token": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "GitHub Token",
                                    "password": True,
                                },
                            },
                            "description": "Creates a GitHub Pull Request with generated code and tests.",
                            "display_name": "GitHub PR Creator",
                            "outputs": [
                                {
                                    "name": "pr_url",
                                    "display_name": "PR URL",
                                    "types": ["Message"],
                                    "method": "create_pr",
                                }
                            ],
                        },
                    },
                },
                # Output node
                {
                    "id": "ChatOutput-Result",
                    "type": "genericNode",
                    "position": {"x": 2800, "y": 200},
                    "data": {
                        "id": "ChatOutput-Result",
                        "display_name": "Pipeline Output",
                        "type": "ChatOutput",
                        "node": {
                            "template": {
                                "input_value": {
                                    "type": "str",
                                    "value": "",
                                    "display_name": "Text",
                                    "input_types": ["Message"],
                                }
                            },
                            "description": "Displays the final PR URL.",
                            "display_name": "Pipeline Output",
                            "outputs": [
                                {
                                    "name": "message",
                                    "display_name": "Message",
                                    "types": ["Message"],
                                    "method": "message_response",
                                }
                            ],
                        },
                    },
                },
            ],
            "edges": [
                # Task Prompt -> Code Gen LLM (input_value)
                _edge("TextInput-TaskPrompt", "text", "TextInput", ["Message"],
                       "LLM-CodeGen", "input_value", ["Message"]),
                # Code Gen Prompt -> Code Gen LLM (system_message)
                _edge("Prompt-CodeGen", "prompt", "Prompt", ["Message"],
                       "LLM-CodeGen", "system_message", ["Message"]),
                # Code Gen LLM -> Test Gen Prompt (as input for template variable)
                _edge("LLM-CodeGen", "text_output", "LanguageModelComponent", ["Message"],
                       "LLM-TestGen", "input_value", ["Message"]),
                # Test Gen Prompt -> Test Gen LLM (system_message)
                _edge("Prompt-TestGen", "prompt", "Prompt", ["Message"],
                       "LLM-TestGen", "system_message", ["Message"]),
                # Code Gen LLM -> Validator (code_output)
                _edge("LLM-CodeGen", "text_output", "LanguageModelComponent", ["Message"],
                       "CustomComponent-Validator", "code_output", ["Message"]),
                # Test Gen LLM -> Validator (test_output)
                _edge("LLM-TestGen", "text_output", "LanguageModelComponent", ["Message"],
                       "CustomComponent-Validator", "test_output", ["Message"]),
                # Task Prompt -> Git PR (task_prompt)
                _edge("TextInput-TaskPrompt", "text", "TextInput", ["Message"],
                       "CustomComponent-GitPR", "task_prompt", ["Message"]),
                # Code Gen LLM -> Git PR (code_output)
                _edge("LLM-CodeGen", "text_output", "LanguageModelComponent", ["Message"],
                       "CustomComponent-GitPR", "code_output", ["Message"]),
                # Test Gen LLM -> Git PR (test_output)
                _edge("LLM-TestGen", "text_output", "LanguageModelComponent", ["Message"],
                       "CustomComponent-GitPR", "test_output", ["Message"]),
                # Validator -> Git PR (validation_output)
                _edge("CustomComponent-Validator", "validation_result", "CustomComponent", ["Message"],
                       "CustomComponent-GitPR", "validation_output", ["Message"]),
                # Git PR -> Output
                _edge("CustomComponent-GitPR", "pr_url", "CustomComponent", ["Message"],
                       "ChatOutput-Result", "input_value", ["Message"]),
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 0.7},
        },
    }
    return flow


def _edge(source_id, source_name, source_type, source_output_types,
          target_id, target_field, target_input_types):
    """Helper to build an edge definition."""
    oe = "\u0153"  # Langflow uses this character in handle encoding
    return {
        "animated": False,
        "data": {
            "sourceHandle": {
                "dataType": source_type,
                "id": source_id,
                "name": source_name,
                "output_types": source_output_types,
            },
            "targetHandle": {
                "fieldName": target_field,
                "id": target_id,
                "inputTypes": target_input_types,
                "type": "str",
            },
        },
        "id": f"edge_{source_id}_{source_name}_to_{target_id}_{target_field}",
        "source": source_id,
        "sourceHandle": json.dumps({
            "dataType": source_type,
            "id": source_id,
            "name": source_name,
            "output_types": source_output_types,
        }).replace('"', oe),
        "target": target_id,
        "targetHandle": json.dumps({
            "fieldName": target_field,
            "id": target_id,
            "inputTypes": target_input_types,
            "type": "str",
        }).replace('"', oe),
    }


def upload_flow(flow, base_url):
    """Upload the flow to Langflow via API."""
    url = f"{base_url}/api/v1/flows/"
    data = json.dumps(flow).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description="Create DevPipeline flow in Langflow")
    parser.add_argument("--port", type=int, default=7860, help="Langflow server port")
    parser.add_argument("--host", default="localhost", help="Langflow server host")
    parser.add_argument("--export-only", action="store_true", help="Export JSON to flows/ without uploading")
    args = parser.parse_args()

    print("Building DevPipeline flow...")
    flow = build_flow()

    # Always save a local copy
    with open("flows/dev_pipeline.json", "w") as f:
        json.dump(flow, f, indent=2)
    print("Flow saved to flows/dev_pipeline.json")

    if args.export_only:
        print("Export-only mode. Flow not uploaded.")
        return

    base_url = f"http://{args.host}:{args.port}"
    print(f"Uploading flow to {base_url}...")
    try:
        result = upload_flow(flow, base_url)
        flow_id = result.get("id", "unknown")
        print(f"Flow created! ID: {flow_id}")
        print(f"Open: {base_url}/flow/{flow_id}")
    except Exception as e:
        print(f"Upload failed: {e}")
        print("Make sure Langflow is running. You can import flows/dev_pipeline.json manually.")


if __name__ == "__main__":
    main()
