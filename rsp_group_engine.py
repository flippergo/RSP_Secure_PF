from __future__ import annotations

import ast
import builtins
import contextlib
import dataclasses
import json
import numbers
import queue
import re
import subprocess
import sys
import threading
import traceback
import types
import uuid
from pathlib import Path
from typing import Any


TEAM_SIZE = 3
VALID_HANDS = {0, 1, 2}
ALLOWED_IMPORTS = {"numpy", "math", "random", "time", "timeout_decorator"}
BANNED_IMPORTS = {
    "importlib",
    "sys",
    "os",
    "inspect",
    "gc",
    "subprocess",
    "socket",
    "threading",
    "multiprocessing",
    "ctypes",
    "pathlib",
}
BANNED_CALLS = {
    "eval",
    "exec",
    "compile",
    "open",
    "input",
    "globals",
    "locals",
    "vars",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "__import__",
}
EXEMPT_DUNDER_NAMES = {"__init__"}
DEFAULT_TIMEOUT_SECONDS = 1.0


class RSPValidationError(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class GroupFile:
    group: str
    path: Path


@dataclasses.dataclass
class AgentOutcome:
    status: str = "ok"
    reason: str = ""
    score: float = 0.0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    invalid_moves: int = 0
    timeouts: int = 0

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def discover_group_files(group_agents_dir: str | Path) -> list[GroupFile]:
    base = Path(group_agents_dir)
    if not base.exists():
        raise FileNotFoundError(f"group_agents directory not found: {base}")
    pattern = re.compile(r"^rsp_group_(\d+)\.py$")
    found: list[tuple[int, GroupFile]] = []
    for path in base.iterdir():
        if not path.is_file():
            continue
        match = pattern.match(path.name)
        if not match:
            continue
        group = match.group(1)
        found.append((int(group), GroupFile(group=group, path=path.resolve())))
    return [item for _, item in sorted(found, key=lambda x: x[0])]


def judge(hand1: Any, hand2: Any) -> int:
    h1 = normalize_hand(hand1)
    h2 = normalize_hand(hand2)
    if h1 is None:
        h1 = -1
    if h2 is None:
        h2 = -1
    if h1 == h2:
        return -1
    if (h1 == 0 and h2 == 1) or (h1 == 1 and h2 == 2) or (h1 == 2 and h2 == 0) or h2 == -1:
        return 1
    if (h2 == 0 and h1 == 1) or (h2 == 1 and h1 == 2) or (h2 == 2 and h1 == 0) or h1 == -1:
        return 2
    return -1


def normalize_hand(hand: Any) -> int | None:
    if isinstance(hand, bool):
        return None
    if isinstance(hand, numbers.Integral):
        hand = int(hand)
    if isinstance(hand, int) and hand in VALID_HANDS:
        return hand
    return None


def validate_group_file(path: str | Path, team_size: int = TEAM_SIZE) -> None:
    source_path = Path(path)
    source = source_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(source_path))
    except SyntaxError as exc:
        raise RSPValidationError(f"syntax error: {exc}") from exc

    errors: list[str] = []
    _validate_ast_safety(tree, errors)
    _validate_required_agents(tree, team_size, errors)
    if errors:
        raise RSPValidationError("; ".join(errors))


def _validate_ast_safety(tree: ast.AST, errors: list[str]) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                if top not in ALLOWED_IMPORTS:
                    errors.append(f"import not allowed: {alias.name}")
                if top in BANNED_IMPORTS:
                    errors.append(f"banned import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                errors.append("relative import not allowed")
                continue
            module = node.module or ""
            top = module.split(".", 1)[0]
            if top not in ALLOWED_IMPORTS:
                errors.append(f"from import not allowed: {module}")
            if top in BANNED_IMPORTS:
                errors.append(f"banned import: {module}")
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in BANNED_CALLS:
                errors.append(f"call not allowed: {name}")
        elif isinstance(node, ast.Attribute):
            if "__" in node.attr:
                errors.append(f"dunder attribute not allowed: {node.attr}")
            root = _root_name(node.value)
            if root in BANNED_IMPORTS:
                errors.append(f"banned module attribute not allowed: {root}.{node.attr}")
        elif isinstance(node, ast.Name):
            if "__" in node.id and node.id not in EXEMPT_DUNDER_NAMES:
                errors.append(f"dunder name not allowed: {node.id}")
            if node.id in BANNED_CALLS:
                errors.append(f"banned name not allowed: {node.id}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if "__" in node.name and node.name not in EXEMPT_DUNDER_NAMES:
                errors.append(f"dunder definition not allowed: {node.name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "__" in node.value:
                errors.append('string containing "__" not allowed')


def _validate_required_agents(tree: ast.Module, team_size: int, errors: list[str]) -> None:
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    for idx in range(1, team_size + 1):
        class_name = f"RSP_Agent_{idx}"
        cls = classes.get(class_name)
        if cls is None:
            errors.append(f"missing class: {class_name}")
            continue
        methods = {node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)}
        init = methods.get("__init__")
        output_hand = methods.get("output_hand")
        get_hand = methods.get("get_hand")
        if init is None:
            errors.append(f"{class_name} missing __init__")
        elif not _accepts_num_match(init):
            errors.append(f"{class_name}.__init__ must accept num_match")
        if output_hand is None:
            errors.append(f"{class_name} missing output_hand")
        elif not _has_timeout_decorator(output_hand):
            errors.append(f"{class_name}.output_hand must use timeout_decorator.timeout(1)")
        if get_hand is None:
            errors.append(f"{class_name} missing get_hand")
        elif len(get_hand.args.args) < 2:
            errors.append(f"{class_name}.get_hand must accept opponent hand")


def _accepts_num_match(func: ast.FunctionDef) -> bool:
    args = func.args
    names = [arg.arg for arg in args.args]
    if "num_match" in names:
        return True
    return args.vararg is not None or args.kwarg is not None


def _has_timeout_decorator(func: ast.FunctionDef) -> bool:
    for deco in func.decorator_list:
        call = deco if isinstance(deco, ast.Call) else None
        if call is None:
            continue
        name = _call_name(call.func)
        if name not in {"timeout", "timeout_decorator.timeout"}:
            continue
        if call.args and isinstance(call.args[0], ast.Constant) and call.args[0].value == 1:
            return True
        for keyword in call.keywords:
            if keyword.arg == "seconds" and isinstance(keyword.value, ast.Constant) and keyword.value.value == 1:
                return True
    return False


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = _call_name(func.value)
        return f"{base}.{func.attr}" if base else func.attr
    return ""


def _root_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    return ""


def run_group_tournament_from_dir(
    group_agents_dir: str | Path = "group_agents",
    num_match: int = 10000,
    team_size: int = TEAM_SIZE,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    groups = discover_group_files(group_agents_dir)
    return run_group_tournament(groups, num_match=num_match, team_size=team_size, timeout_seconds=timeout_seconds)


def run_group_tournament(
    groups: list[GroupFile],
    num_match: int = 10000,
    team_size: int = TEAM_SIZE,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    import pandas as pd

    agents = [f"agent{group.group}_{idx}" for group in groups for idx in range(1, team_size + 1)]
    scores = pd.DataFrame(0.0, columns=agents, index=agents)
    validation: dict[str, str] = {}
    details: list[dict[str, Any]] = []

    for group in groups:
        try:
            validate_group_file(group.path, team_size=team_size)
        except RSPValidationError as exc:
            validation[group.group] = str(exc)

    for i1 in range(len(groups) - 1):
        for i2 in range(i1 + 1, len(groups)):
            group1 = groups[i1]
            group2 = groups[i2]
            for member_idx in range(1, team_size + 1):
                result1, result2 = _run_member_match(
                    group1,
                    group2,
                    member_idx,
                    num_match,
                    timeout_seconds,
                    validation.get(group1.group),
                    validation.get(group2.group),
                )
                name1 = f"agent{group1.group}_{member_idx}"
                name2 = f"agent{group2.group}_{member_idx}"
                scores.loc[name1, name2] = result1.score
                scores.loc[name2, name1] = result2.score
                details.append(
                    {
                        "group1": group1.group,
                        "group2": group2.group,
                        "agent_index": member_idx,
                        "agent1": name1,
                        "agent2": name2,
                        "agent1_result": result1.as_dict(),
                        "agent2_result": result2.as_dict(),
                    }
                )

    match_columns = list(scores.columns)
    scores["total"] = scores[match_columns].sum(axis=1)
    scores["group"] = [name.split("_", 1)[0][5:] for name in scores.index]
    group_scores = scores[["group", "total"]].groupby("group").sum().sort_values("total", ascending=False)
    return {
        "scores": scores,
        "group_scores": group_scores,
        "details": details,
        "validation_errors": validation,
    }


def _run_member_match(
    group1: GroupFile,
    group2: GroupFile,
    member_idx: int,
    num_match: int,
    timeout_seconds: float,
    validation_error1: str | None,
    validation_error2: str | None,
) -> tuple[AgentOutcome, AgentOutcome]:
    if validation_error1 or validation_error2:
        return _validation_outcome(validation_error1, validation_error2)

    class_name = f"RSP_Agent_{member_idx}"
    worker1 = _AgentWorker(group1.path, class_name, num_match, timeout_seconds)
    worker2 = _AgentWorker(group2.path, class_name, num_match, timeout_seconds)
    result1 = worker1.start()
    result2 = worker2.start()
    if result1 is not None or result2 is not None:
        outcome1 = result1 or AgentOutcome(status="ok", score=1.0)
        outcome2 = result2 or AgentOutcome(status="ok", score=1.0)
        _shutdown_workers(worker1, worker2)
        return _finalize_fault_pair(outcome1, outcome2)

    outcome1 = AgentOutcome()
    outcome2 = AgentOutcome()
    try:
        for _ in range(num_match):
            output_id1 = worker1.request_output_hand()
            output_id2 = worker2.request_output_hand()
            hand1, err1 = worker1.read_value(output_id1)
            hand2, err2 = worker2.read_value(output_id2)
            if err1 or err2:
                _apply_worker_error(outcome1, err1)
                _apply_worker_error(outcome2, err2)
                return _finalize_fault_pair(outcome1, outcome2)

            norm1 = normalize_hand(hand1)
            norm2 = normalize_hand(hand2)
            if norm1 is None:
                outcome1.invalid_moves += 1
            if norm2 is None:
                outcome2.invalid_moves += 1
            win = judge(hand1, hand2)
            if win == 1:
                outcome1.wins += 1
                outcome2.losses += 1
            elif win == 2:
                outcome2.wins += 1
                outcome1.losses += 1
            else:
                outcome1.draws += 1
                outcome2.draws += 1

            get_id1 = worker1.request_get_hand(norm2 if norm2 is not None else -1)
            get_id2 = worker2.request_get_hand(norm1 if norm1 is not None else -1)
            err1 = worker1.read_ack(get_id1)
            err2 = worker2.read_ack(get_id2)
            if err1 or err2:
                _apply_worker_error(outcome1, err1)
                _apply_worker_error(outcome2, err2)
                return _finalize_fault_pair(outcome1, outcome2)
    finally:
        _shutdown_workers(worker1, worker2)

    outcome1.score = outcome1.wins / num_match if num_match else 0.0
    outcome2.score = outcome2.wins / num_match if num_match else 0.0
    return outcome1, outcome2


def _validation_outcome(error1: str | None, error2: str | None) -> tuple[AgentOutcome, AgentOutcome]:
    out1 = AgentOutcome(status="rejected" if error1 else "ok", reason=error1 or "", score=0.0 if error1 else 1.0)
    out2 = AgentOutcome(status="rejected" if error2 else "ok", reason=error2 or "", score=0.0 if error2 else 1.0)
    if error1 and error2:
        out1.score = 0.0
        out2.score = 0.0
    return out1, out2


def _apply_worker_error(outcome: AgentOutcome, error: dict[str, Any] | None) -> None:
    if not error:
        return
    outcome.status = error.get("status", "bug")
    outcome.reason = error.get("reason", "")
    if outcome.status == "timeout":
        outcome.timeouts += 1


def _finalize_fault_pair(outcome1: AgentOutcome, outcome2: AgentOutcome) -> tuple[AgentOutcome, AgentOutcome]:
    bad1 = outcome1.status != "ok"
    bad2 = outcome2.status != "ok"
    if bad1:
        outcome1.score = 0.0
    if bad2:
        outcome2.score = 0.0
    if bad1 and not bad2:
        outcome2.score = 1.0
    if bad2 and not bad1:
        outcome1.score = 1.0
    return outcome1, outcome2


def _shutdown_workers(*workers: "_AgentWorker") -> None:
    for worker in workers:
        worker.close()


class _AgentWorker:
    def __init__(self, path: Path, class_name: str, num_match: int, timeout_seconds: float) -> None:
        self.path = path
        self.class_name = class_name
        self.num_match = num_match
        self.timeout_seconds = timeout_seconds
        self.results: queue.Queue[dict[str, Any]] = queue.Queue()
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                str(Path(__file__).resolve()),
                "--worker",
                str(path),
                class_name,
                str(num_match),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self.stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self.stdout_thread.start()
        self.stderr_thread.start()

    def start(self) -> AgentOutcome | None:
        try:
            boot = self.results.get(timeout=max(5.0, self.timeout_seconds + 2.0))
        except queue.Empty:
            self._terminate()
            return AgentOutcome(status="timeout", reason="worker startup timed out", timeouts=1)
        if boot.get("type") != "boot":
            self._terminate()
            return AgentOutcome(status=boot.get("status", "bug"), reason=boot.get("reason", "worker startup failed"))
        try:
            loaded = self.results.get(timeout=max(10.0, self.timeout_seconds + 2.0))
        except queue.Empty:
            self._terminate()
            return AgentOutcome(status="timeout", reason="module load timed out", timeouts=1)
        if loaded.get("type") != "loaded":
            self._terminate()
            return AgentOutcome(status=loaded.get("status", "bug"), reason=loaded.get("reason", "module load failed"))
        try:
            message = self.results.get(timeout=self.timeout_seconds)
        except queue.Empty:
            self._terminate()
            return AgentOutcome(status="timeout", reason="__init__ timed out", timeouts=1)
        if message.get("type") == "ready":
            return None
        self._terminate()
        return AgentOutcome(status=message.get("status", "bug"), reason=message.get("reason", "worker init failed"))

    def output_hand(self) -> tuple[Any, dict[str, Any] | None]:
        request_id = self.request_output_hand()
        return self.read_value(request_id)

    def get_hand(self, hand: int) -> dict[str, Any] | None:
        request_id = self.request_get_hand(hand)
        return self.read_ack(request_id)

    def request_output_hand(self) -> str:
        request_id = uuid.uuid4().hex
        self._send({"type": "output_hand", "id": request_id})
        return request_id

    def request_get_hand(self, hand: int) -> str:
        request_id = uuid.uuid4().hex
        self._send({"type": "get_hand", "id": request_id, "hand": hand})
        return request_id

    def read_value(self, request_id: str) -> tuple[Any, dict[str, Any] | None]:
        return self._read_response(request_id)

    def read_ack(self, request_id: str) -> dict[str, Any] | None:
        _, error = self._read_response(request_id)
        return error

    def close(self) -> None:
        if self.process.poll() is None:
            self._send({"type": "close"})
            try:
                self.process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass
        self._terminate()

    def _read_response(self, request_id: str) -> tuple[Any, dict[str, Any] | None]:
        try:
            message = self.results.get(timeout=self.timeout_seconds)
        except queue.Empty:
            self._terminate()
            return None, {"status": "timeout", "reason": "operation timed out"}
        if message.get("id") != request_id:
            self._terminate()
            return None, {"status": "bug", "reason": "worker protocol error"}
        if message.get("type") == "ok":
            return message.get("value"), None
        self._terminate()
        return None, {"status": message.get("status", "bug"), "reason": message.get("reason", "worker error")}

    def _send(self, message: dict[str, Any]) -> None:
        if self.process.stdin is None or self.process.poll() is not None:
            return
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def _read_stdout(self) -> None:
        if self.process.stdout is None:
            return
        for line in self.process.stdout:
            try:
                self.results.put(json.loads(line))
            except json.JSONDecodeError:
                self.results.put({"type": "error", "status": "bug", "reason": "worker protocol output was not JSON"})

    def _drain_stderr(self) -> None:
        if self.process.stderr is None:
            return
        for _line in self.process.stderr:
            pass

    def _terminate(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=0.5)
        self._close_pipes()

    def _close_pipes(self) -> None:
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            if pipe is None or pipe.closed:
                continue
            try:
                pipe.close()
            except OSError:
                pass


def _agent_worker_main(path: str, class_name: str, num_match: int) -> None:
    protocol_out = sys.stdout

    def send(message: dict[str, Any]) -> None:
        protocol_out.write(json.dumps(message, ensure_ascii=False) + "\n")
        protocol_out.flush()

    send({"type": "boot"})
    try:
        with contextlib.redirect_stdout(sys.stderr):
            cls = _load_agent_class(Path(path), class_name)
        send({"type": "loaded"})
    except Exception as exc:
        send({"type": "error", "status": "bug", "reason": _short_exception(exc)})
        return

    try:
        with contextlib.redirect_stdout(sys.stderr):
            agent = cls(num_match=num_match)
        send({"type": "ready"})
    except Exception as exc:
        send({"type": "error", "status": "bug", "reason": _short_exception(exc)})
        return

    for line in sys.stdin:
        command = json.loads(line)
        command_type = command.get("type")
        request_id = command.get("id")
        if command_type == "close":
            return
        try:
            with contextlib.redirect_stdout(sys.stderr):
                if command_type == "output_hand":
                    value = _json_safe_value(agent.output_hand())
                    send({"type": "ok", "id": request_id, "value": value})
                elif command_type == "get_hand":
                    agent.get_hand(command.get("hand"))
                    send({"type": "ok", "id": request_id, "value": None})
                else:
                    send({"type": "error", "id": request_id, "status": "bug", "reason": "unknown command"})
        except Exception as exc:
            send({"type": "error", "id": request_id, "status": "bug", "reason": _short_exception(exc)})


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, numbers.Integral) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, bool, float, str)) or value is None:
        return value
    return repr(value)


def _load_agent_class(path: Path, class_name: str) -> Any:
    source = path.read_text(encoding="utf-8")
    module = types.ModuleType(f"_rsp_submission_{path.stem}_{uuid.uuid4().hex}")
    module.__file__ = str(path)
    module.__package__ = ""
    module.__dict__["__builtins__"] = _safe_builtins()
    exec(compile(source, str(path), "exec"), module.__dict__)
    return getattr(module, class_name)


def _safe_builtins() -> dict[str, Any]:
    safe = dict(vars(builtins))
    for name in BANNED_CALLS - {"__import__"}:
        safe.pop(name, None)
    safe["__import__"] = _safe_import
    return safe


def _safe_import(name: str, globals_: Any = None, locals_: Any = None, fromlist: tuple[str, ...] = (), level: int = 0) -> Any:
    if level:
        raise ImportError("relative imports are not allowed")
    top = name.split(".", 1)[0]
    if top not in ALLOWED_IMPORTS:
        raise ImportError(f"import not allowed: {name}")
    if top == "timeout_decorator":
        return _timeout_decorator_module()
    return __import__(name, globals_, locals_, fromlist, level)


def _timeout_decorator_module() -> types.ModuleType:
    module = sys.modules.get("timeout_decorator")
    if module is not None:
        return module
    module = types.ModuleType("timeout_decorator")

    def timeout(_seconds: float = 1, *args: Any, **kwargs: Any) -> Any:
        def decorator(func: Any) -> Any:
            return func

        return decorator

    module.timeout = timeout
    sys.modules["timeout_decorator"] = module
    return module


def _short_exception(exc: BaseException) -> str:
    text = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    return text or exc.__class__.__name__


def print_tournament_summary(result: dict[str, Any]) -> None:
    print("Group scores")
    print(result["group_scores"])
    validation_errors = result.get("validation_errors") or {}
    if validation_errors:
        print("\nValidation errors")
        for group, error in validation_errors.items():
            print(f"group {group}: {error}")


def _main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "--worker":
        if len(sys.argv) != 5:
            raise SystemExit("usage: rsp_group_engine.py --worker PATH CLASS_NAME NUM_MATCH")
        _agent_worker_main(sys.argv[2], sys.argv[3], int(sys.argv[4]))
        return
    result = run_group_tournament_from_dir()
    print_tournament_summary(result)


if __name__ == "__main__":
    _main()
