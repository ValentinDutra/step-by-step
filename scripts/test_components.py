"""
Offline tests for custom components (no Langflow server needed).

Validates the component code can be parsed and basic logic works.

Usage:
    python scripts/test_components.py
"""

import ast
import sys


def test_validator_syntax():
    """Test that validator.py is valid Python."""
    with open("components/validator.py") as f:
        code = f.read()
    try:
        ast.parse(code)
        print("  PASS: validator.py syntax valid")
        return True
    except SyntaxError as e:
        print(f"  FAIL: validator.py syntax error: {e}")
        return False


def test_git_tool_syntax():
    """Test that git_tool.py is valid Python."""
    with open("components/git_tool.py") as f:
        code = f.read()
    try:
        ast.parse(code)
        print("  PASS: git_tool.py syntax valid")
        return True
    except SyntaxError as e:
        print(f"  FAIL: git_tool.py syntax error: {e}")
        return False


def test_prompts_exist():
    """Test that prompt template files exist and are non-empty."""
    files = ["prompts/code_generation.txt", "prompts/test_generation.txt", "prompts/review.txt"]
    all_pass = True
    for f in files:
        try:
            with open(f) as fh:
                content = fh.read().strip()
            if content:
                print(f"  PASS: {f} exists ({len(content)} chars)")
            else:
                print(f"  FAIL: {f} is empty")
                all_pass = False
        except FileNotFoundError:
            print(f"  FAIL: {f} not found")
            all_pass = False
    return all_pass


def test_flow_json():
    """Test that flow JSON is valid and has expected structure."""
    import json
    try:
        with open("flows/dev_pipeline.json") as f:
            flow = json.load(f)

        nodes = flow["data"]["nodes"]
        edges = flow["data"]["edges"]

        expected_nodes = 8
        expected_edges = 11

        if len(nodes) == expected_nodes:
            print(f"  PASS: {len(nodes)} nodes (expected {expected_nodes})")
        else:
            print(f"  FAIL: {len(nodes)} nodes (expected {expected_nodes})")
            return False

        if len(edges) == expected_edges:
            print(f"  PASS: {len(edges)} edges (expected {expected_edges})")
        else:
            print(f"  FAIL: {len(edges)} edges (expected {expected_edges})")
            return False

        # Check all node IDs are unique
        node_ids = [n["id"] for n in nodes]
        if len(node_ids) == len(set(node_ids)):
            print("  PASS: All node IDs unique")
        else:
            print("  FAIL: Duplicate node IDs found")
            return False

        # Check all edge sources/targets reference valid nodes
        for edge in edges:
            if edge["source"] not in node_ids:
                print(f"  FAIL: Edge source {edge['source']} not in nodes")
                return False
            if edge["target"] not in node_ids:
                print(f"  FAIL: Edge target {edge['target']} not in nodes")
                return False
        print("  PASS: All edge references valid")

        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def main():
    print("Running component tests...")
    print()

    results = []

    print("[Validator Component]")
    results.append(test_validator_syntax())

    print("\n[Git Tool Component]")
    results.append(test_git_tool_syntax())

    print("\n[Prompt Templates]")
    results.append(test_prompts_exist())

    print("\n[Flow JSON]")
    results.append(test_flow_json())

    print("\n" + "=" * 40)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} test groups passed")

    if not all(results):
        sys.exit(1)
    print("All tests passed!")


if __name__ == "__main__":
    main()
