from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

from rsp_group_engine import (
    TEAM_SIZE,
    RSPValidationError,
    discover_group_files,
    run_group_tournament_from_dir,
    validate_group_file,
)


SERVER_INFO = {
    "name": "rsp-secure-pf",
    "version": "0.1.0",
}


def list_rsp_group_agents(group_agents_dir: str = "group_agents", team_size: int = TEAM_SIZE) -> dict[str, Any]:
    groups = discover_group_files(group_agents_dir)
    items: list[dict[str, Any]] = []
    for group in groups:
        validation_error = None
        try:
            validate_group_file(group.path, team_size=team_size)
        except RSPValidationError as exc:
            validation_error = str(exc)
        items.append(
            {
                "group": group.group,
                "file": str(group.path),
                "agent_classes": [f"RSP_Agent_{idx}" for idx in range(1, team_size + 1)],
                "valid": validation_error is None,
                "validation_error": validation_error,
            }
        )
    return {
        "group_agents_dir": str(Path(group_agents_dir).resolve()),
        "team_size": team_size,
        "groups": items,
        "count": len(items),
        "markdown": _groups_markdown(items),
    }


def validate_rsp_group_agents(group_agents_dir: str = "group_agents", team_size: int = TEAM_SIZE) -> dict[str, Any]:
    listing = list_rsp_group_agents(group_agents_dir=group_agents_dir, team_size=team_size)
    invalid = [item for item in listing["groups"] if not item["valid"]]
    return {
        **listing,
        "valid": not invalid,
        "invalid_count": len(invalid),
    }


def run_rsp_group_tournament_from_dir(
    group_agents_dir: str = "group_agents",
    num_match: int = 10000,
    team_size: int = TEAM_SIZE,
    timeout_seconds: float = 1.0,
    include_score_matrix: bool = True,
    include_details: bool = True,
) -> dict[str, Any]:
    result = run_group_tournament_from_dir(
        group_agents_dir,
        num_match=num_match,
        team_size=team_size,
        timeout_seconds=timeout_seconds,
    )
    group_ranking = _ranking_records(result["group_scores"], key_name="group")
    agent_ranking = _agent_ranking_records(result["scores"])
    response: dict[str, Any] = {
        "group_agents_dir": str(Path(group_agents_dir).resolve()),
        "num_match": num_match,
        "team_size": team_size,
        "timeout_seconds": timeout_seconds,
        "validation_errors": result["validation_errors"],
        "group_ranking": group_ranking,
        "agent_ranking": agent_ranking,
        "member_ranking": agent_ranking,
        "group_score_chart": _bar_chart(group_ranking),
        "markdown": _tournament_markdown(group_ranking, agent_ranking, result["validation_errors"]),
    }
    if include_score_matrix:
        response["score_matrix"] = result["scores"].reset_index(names="agent").to_dict(orient="records")
    if include_details:
        response["details"] = result["details"]
    return response


TOOLS = [
    {
        "name": "list_rsp_group_agents",
        "description": "List rsp_group_<n>.py files under group_agents and validate the expected RSP_Agent classes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "group_agents_dir": {"type": "string", "default": "group_agents"},
                "team_size": {"type": "integer", "default": TEAM_SIZE, "minimum": 1},
            },
        },
    },
    {
        "name": "validate_rsp_group_agents",
        "description": "Validate all rsp_group_<n>.py submissions before running a tournament.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "group_agents_dir": {"type": "string", "default": "group_agents"},
                "team_size": {"type": "integer", "default": TEAM_SIZE, "minimum": 1},
            },
        },
    },
    {
        "name": "run_rsp_group_tournament_from_dir",
        "description": "Run the secure group tournament and return group rankings, all-agent rankings, score tables, and visual Markdown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "group_agents_dir": {"type": "string", "default": "group_agents"},
                "num_match": {"type": "integer", "default": 10000, "minimum": 1},
                "team_size": {"type": "integer", "default": TEAM_SIZE, "minimum": 1},
                "timeout_seconds": {"type": "number", "default": 1.0, "minimum": 0.1},
                "include_score_matrix": {"type": "boolean", "default": True},
                "include_details": {"type": "boolean", "default": True},
            },
        },
    },
]


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    try:
        if method == "initialize":
            return _result(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return _result(request_id, {})
        if method == "tools/list":
            return _result(request_id, {"tools": TOOLS})
        if method == "tools/call":
            params = request.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            return _result(request_id, _call_tool(name, arguments))
        if method == "resources/list":
            return _result(request_id, {"resources": []})
        if method == "prompts/list":
            return _result(request_id, {"prompts": []})
        return _error(request_id, -32601, f"method not found: {method}")
    except Exception as exc:
        print(traceback.format_exc(), file=sys.stderr)
        return _error(request_id, -32000, str(exc))


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, f"parse error: {exc}")
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def _call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "list_rsp_group_agents":
        payload = list_rsp_group_agents(**arguments)
    elif name == "validate_rsp_group_agents":
        payload = validate_rsp_group_agents(**arguments)
    elif name == "run_rsp_group_tournament_from_dir":
        payload = run_rsp_group_tournament_from_dir(**arguments)
    else:
        return {
            "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
            "isError": True,
        }
    return _tool_result(payload)


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload.get("markdown") or json.dumps(payload, ensure_ascii=False, indent=2)
    return {
        "content": [
            {"type": "text", "text": text},
            {"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)},
        ],
        "isError": False,
    }


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _ranking_records(df: Any, key_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ranked = df.sort_values("total", ascending=False).reset_index()
    for index, row in ranked.iterrows():
        rows.append(
            {
                "rank": index + 1,
                key_name: str(row[key_name]),
                "total": round(float(row["total"]), 6),
            }
        )
    return rows


def _agent_ranking_records(scores: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ranked = scores[["group", "total"]].copy()
    ranked["agent"] = ranked.index
    ranked = ranked.sort_values("total", ascending=False).reset_index(drop=True)
    for index, row in ranked.iterrows():
        rows.append(
            {
                "rank": index + 1,
                "agent": str(row["agent"]),
                "group": str(row["group"]),
                "total": round(float(row["total"]), 6),
            }
        )
    return rows


def _groups_markdown(groups: list[dict[str, Any]]) -> str:
    lines = ["# RSP Group Agents", "", "| group | file | valid |", "|---:|---|:---:|"]
    for item in groups:
        valid = "OK" if item["valid"] else "NG"
        lines.append(f"| {item['group']} | `{item['file']}` | {valid} |")
    invalid = [item for item in groups if not item["valid"]]
    if invalid:
        lines.extend(["", "## Validation Errors"])
        for item in invalid:
            lines.append(f"- group {item['group']}: {item['validation_error']}")
    return "\n".join(lines)


def _tournament_markdown(
    group_ranking: list[dict[str, Any]],
    agent_ranking: list[dict[str, Any]],
    validation_errors: dict[str, str],
) -> str:
    lines = ["# RSP Group Tournament Result", "", "## Group Ranking", ""]
    lines.extend(_table(["rank", "group", "total"], group_ranking))
    lines.extend(["", "## Group Score Chart", "", "```text", _bar_chart(group_ranking), "```", "", "## All Agent Ranking", ""])
    lines.extend(_table(["rank", "agent", "group", "total"], agent_ranking))
    if validation_errors:
        lines.extend(["", "## Validation Errors"])
        for group, error in validation_errors.items():
            lines.append(f"- group {group}: {error}")
    return "\n".join(lines)


def _table(headers: list[str], rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    return lines


def _bar_chart(group_ranking: list[dict[str, Any]]) -> str:
    if not group_ranking:
        return ""
    max_score = max(row["total"] for row in group_ranking) or 1.0
    lines = []
    for row in group_ranking:
        width = int((row["total"] / max_score) * 30)
        bar = "#" * max(width, 1 if row["total"] > 0 else 0)
        lines.append(f"group {row['group']:>4}: {bar:<30} {row['total']:.4f}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
