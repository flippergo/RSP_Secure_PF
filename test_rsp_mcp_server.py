import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from rsp_mcp_server import handle_request


def write_group(base: Path, number: int, hand: int) -> None:
    classes = []
    for idx in range(1, 4):
        classes.append(
            f"""
class RSP_Agent_{idx}:
    def __init__(self, num_match=10000):
        self.cnt = 0
        self.my_hands = []
        self.oppo_hands = []
        self.num_match = num_match

    @timeout_decorator.timeout(1)
    def output_hand(self):
        self.my_hands.append({hand})
        return {hand}

    def get_hand(self, oppo_hand):
        self.cnt += 1
        self.oppo_hands.append(oppo_hand)
"""
        )
    (base / f"rsp_group_{number}.py").write_text("import timeout_decorator\n" + "\n".join(classes), encoding="utf-8")


class RSPMCPServerTests(unittest.TestCase):
    def test_tools_list_contains_group_tournament_tools(self):
        response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(response["id"], 1)
        tool_names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("list_rsp_group_agents", tool_names)
        self.assertIn("validate_rsp_group_agents", tool_names)
        self.assertIn("run_rsp_group_tournament_from_dir", tool_names)

    def test_tool_call_returns_markdown_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_group(base, 1, 0)
            write_group(base, 2, 1)
            response = handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "run_rsp_group_tournament_from_dir",
                        "arguments": {
                            "group_agents_dir": str(base),
                            "num_match": 1,
                            "include_score_matrix": False,
                            "include_details": False,
                        },
                    },
                }
            )
        result = response["result"]
        self.assertFalse(result["isError"])
        self.assertIn("# RSP Group Tournament Result", result["content"][0]["text"])
        self.assertIn("## All Agent Ranking", result["content"][0]["text"])
        payload = json.loads(result["content"][1]["text"])
        self.assertEqual(payload["group_ranking"][0]["group"], "1")
        self.assertIn("agent_ranking", payload)
        self.assertIn("member_ranking", payload)
        self.assertEqual(payload["agent_ranking"], payload["member_ranking"])
        self.assertEqual(len(payload["agent_ranking"]), 6)
        self.assertEqual(set(payload["agent_ranking"][0]), {"rank", "agent", "group", "total"})
        totals = [row["total"] for row in payload["agent_ranking"]]
        self.assertEqual(totals, sorted(totals, reverse=True))

    def test_stdio_server_responds_to_tools_list(self):
        request = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}) + "\n"
        completed = subprocess.run(
            [sys.executable, "rsp_mcp_server.py"],
            input=request,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        response = json.loads(completed.stdout.splitlines()[0])
        self.assertEqual(response["id"], 3)
        self.assertIn("tools", response["result"])


if __name__ == "__main__":
    unittest.main()
