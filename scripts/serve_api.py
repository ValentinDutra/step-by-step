"""
API client for the DevPipeline flow.

Demonstrates how to call the pipeline as an API after clicking "Serve" in Langflow.

Usage:
    python scripts/serve_api.py --flow-id FLOW_ID "Your task prompt here"
    python scripts/serve_api.py --flow-id FLOW_ID --list-flows
"""

import argparse
import json
import sys
import urllib.request
import urllib.error


def run_pipeline(base_url, flow_id, task_prompt):
    """Call the pipeline API endpoint."""
    url = f"{base_url}/api/v1/run/{flow_id}"
    payload = {
        "input_value": task_prompt,
        "output_type": "chat",
        "input_type": "chat",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def list_flows(base_url):
    """List all available flows."""
    url = f"{base_url}/api/v1/flows/"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req) as resp:
        flows = json.loads(resp.read().decode())
    for flow in flows:
        print(f"  {flow['id']}: {flow['name']}")
    return flows


def main():
    parser = argparse.ArgumentParser(description="DevPipeline API Client")
    parser.add_argument("prompt", nargs="?", help="Task prompt to run")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--flow-id", required=False, help="Flow ID")
    parser.add_argument("--list-flows", action="store_true", help="List available flows")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    if args.list_flows:
        print("Available flows:")
        list_flows(base_url)
        return

    if not args.prompt:
        parser.error("Please provide a task prompt or use --list-flows")

    flow_id = args.flow_id
    if not flow_id:
        # Auto-detect
        url = f"{base_url}/api/v1/flows/"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req) as resp:
            flows = json.loads(resp.read().decode())
        for flow in flows:
            if flow.get("name") == "DevPipeline":
                flow_id = flow["id"]
                break
        if not flow_id:
            print("DevPipeline flow not found. Use --flow-id or import the flow first.")
            sys.exit(1)

    print(f"Running pipeline with: {args.prompt}")
    print(f"Flow: {flow_id}")
    print("-" * 40)

    try:
        result = run_pipeline(base_url, flow_id, args.prompt)
        print(json.dumps(result, indent=2))
    except urllib.error.HTTPError as e:
        print(f"Error: HTTP {e.code}")
        print(e.read().decode())
        sys.exit(1)


if __name__ == "__main__":
    main()
