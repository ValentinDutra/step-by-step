"""
End-to-end test script for the DevPipeline flow.

Tests the pipeline via Langflow's API with multiple task types.
Requires Langflow server running with the DevPipeline flow loaded.

Usage:
    python scripts/test_pipeline.py [--port 7860] [--flow-id FLOW_ID]
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error


TEST_PROMPTS = [
    {
        "name": "REST Endpoint",
        "prompt": "Implement POST /login endpoint returning JWT token",
    },
    {
        "name": "CRUD Operations",
        "prompt": "Create a CRUD API for managing blog posts with title, content, author",
    },
    {
        "name": "Middleware",
        "prompt": "Add rate limiting middleware that limits to 100 requests per minute per IP",
    },
    {
        "name": "Error Handling",
        "prompt": "",  # Empty task - should handle gracefully
    },
]


def run_flow(base_url, flow_id, task_prompt):
    """Run the pipeline with a given task prompt."""
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
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            elapsed = time.time() - start
            return {"success": True, "result": result, "elapsed": elapsed}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        elapsed = time.time() - start
        return {"success": False, "error": f"HTTP {e.code}: {body}", "elapsed": elapsed}
    except Exception as e:
        elapsed = time.time() - start
        return {"success": False, "error": str(e), "elapsed": elapsed}


def list_flows(base_url):
    """List available flows."""
    url = f"{base_url}/api/v1/flows/"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Failed to list flows: {e}", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser(description="Test DevPipeline flow")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--flow-id", default=None, help="Flow ID (auto-detected if not provided)")
    parser.add_argument("--quick", action="store_true", help="Run only first test")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    # Find flow
    flow_id = args.flow_id
    if not flow_id:
        print("Detecting flow ID...")
        flows = list_flows(base_url)
        for flow in flows:
            if flow.get("name") == "DevPipeline":
                flow_id = flow["id"]
                break
        if not flow_id:
            print("DevPipeline flow not found. Run setup_flow.py first or provide --flow-id.")
            sys.exit(1)

    print(f"Testing flow: {flow_id}")
    print(f"Server: {base_url}")
    print("=" * 60)

    tests = TEST_PROMPTS[:1] if args.quick else TEST_PROMPTS
    passed = 0
    failed = 0

    for test in tests:
        print(f"\nTest: {test['name']}")
        print(f"Prompt: {test['prompt'][:60]}...")
        result = run_flow(base_url, flow_id, test["prompt"])

        if result["success"]:
            print(f"  PASS ({result['elapsed']:.1f}s)")
            passed += 1
        else:
            print(f"  FAIL ({result['elapsed']:.1f}s): {result['error'][:100]}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
