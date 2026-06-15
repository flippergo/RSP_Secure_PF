import tempfile
import textwrap
import unittest
from pathlib import Path

from rsp_group_engine import RSPValidationError, run_group_tournament_from_dir, validate_group_file


def write_group(base: Path, number: int, body: str) -> Path:
    path = base / f"rsp_group_{number}.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def valid_group_source(output_expr: str = "0", get_hand_body: str = "self.cnt += 1\n        self.oppo_hands.append(oppo_hand)") -> str:
    get_hand_lines = "\n".join(f"        {line.strip()}" for line in get_hand_body.splitlines())
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
        hand = {output_expr}
        self.my_hands.append(hand)
        return hand

    def get_hand(self, oppo_hand):
{get_hand_lines}
            """
        )
    return "import timeout_decorator\n\n" + "\n".join(classes)


class RSPGroupEngineTests(unittest.TestCase):
    def test_validation_rejects_frame_and_module_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_group(
                Path(tmp),
                1,
                """
                import inspect
                import timeout_decorator

                class RSP_Agent_1:
                    def __init__(self, num_match=10000): pass
                    @timeout_decorator.timeout(1)
                    def output_hand(self):
                        return inspect.currentframe()
                    def get_hand(self, oppo_hand): pass

                class RSP_Agent_2(RSP_Agent_1): pass
                class RSP_Agent_3(RSP_Agent_1): pass
                """,
            )
            with self.assertRaises(RSPValidationError) as ctx:
                validate_group_file(path)
            message = str(ctx.exception)
            self.assertIn("import not allowed: inspect", message)
            self.assertIn("inspect.currentframe", message)

    def test_validation_rejects_sys_and_importlib(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_group(
                Path(tmp),
                1,
                "import sys\nimport importlib\n" + valid_group_source("0"),
            )
            with self.assertRaises(RSPValidationError) as ctx:
                validate_group_file(path)
            message = str(ctx.exception)
            self.assertIn("import not allowed: sys", message)
            self.assertIn("import not allowed: importlib", message)

    def test_invalid_moves_lose_round_without_crashing_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_group(base, 1, valid_group_source("True"))
            write_group(base, 2, valid_group_source("0"))

            result = run_group_tournament_from_dir(base, num_match=1, timeout_seconds=1)

            self.assertEqual(result["scores"].loc["agent1_1", "agent2_1"], 0.0)
            self.assertEqual(result["scores"].loc["agent2_1", "agent1_1"], 1.0)
            invalid_counts = [d["agent1_result"]["invalid_moves"] for d in result["details"]]
            self.assertEqual(invalid_counts, [1, 1, 1])

    def test_get_hand_failure_marks_only_faulty_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_group(base, 1, valid_group_source("0", "raise RuntimeError('bad get_hand')"))
            write_group(base, 2, valid_group_source("1"))

            result = run_group_tournament_from_dir(base, num_match=1, timeout_seconds=1)

            detail = result["details"][0]
            self.assertEqual(detail["agent1_result"]["status"], "bug")
            self.assertEqual(detail["agent1_result"]["score"], 0.0)
            self.assertEqual(detail["agent2_result"]["status"], "ok")
            self.assertEqual(detail["agent2_result"]["score"], 1.0)

    def test_agents_are_recreated_for_each_group_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            stateful = valid_group_source("0 if self.cnt == 0 else 1")
            write_group(base, 1, stateful)
            write_group(base, 2, valid_group_source("1"))
            write_group(base, 3, valid_group_source("1"))

            result = run_group_tournament_from_dir(base, num_match=1, timeout_seconds=1)

            self.assertEqual(result["scores"].loc["agent1_1", "agent2_1"], 1.0)
            self.assertEqual(result["scores"].loc["agent1_1", "agent3_1"], 1.0)
            self.assertEqual(result["group_scores"].loc["1", "total"], 6.0)


if __name__ == "__main__":
    unittest.main()
