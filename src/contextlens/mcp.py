"""MCP (Model Context Protocol) stdio server.

Implements the minimum JSON-RPC 2.0 surface that the MCP spec needs:

- ``initialize`` → handshake; returns protocol version + capabilities.
- ``tools/list``  → enumerates the three tools we ship.
- ``tools/call``  → dispatches to :func:`estimate`, :func:`truncate`,
  or :func:`budget_report`.

Any unknown method produces a JSON-RPC ``-32601 Method not found``
error. Invalid JSON produces ``-32700 Parse error``. We deliberately
do **not** implement notifications / cancellation / progress — the
spec scopes us to a minimal, transport-stdio server.

The protocol implementation lives in :class:`MCPServer`. The module's
``serve_stdio`` function is what ``python -m contextlens.mcp`` invokes.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, TextIO

from contextlens import __version__
from contextlens.budget import Message, budget_report
from contextlens.estimator import estimate
from contextlens.jsonl import handle_request as jsonl_handle_request
from contextlens.truncation import truncate

__all__ = ["MCPServer", "serve_stdio", "PROTOCOL_VERSION", "SERVER_INFO"]


PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {
    "name": "contextlens",
    "version": __version__,
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


TOOL_ESTIMATE = ToolSpec(
    name="estimate_tokens",
    description=(
        "Estimate the token count of a piece of text using the "
        "deterministic cl100k_approx heuristic. Returns the token "
        "count, confidence label, and accounting details."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to estimate. Empty string is allowed.",
            },
            "encoding": {
                "type": "string",
                "enum": ["cl100k_approx"],
                "default": "cl100k_approx",
            },
            "message_overhead": {
                "type": "integer",
                "minimum": 0,
                "default": 4,
                "description": "Per-message overhead tokens.",
            },
        },
        "required": ["text"],
        "additionalProperties": False,
    },
)

TOOL_TRUNCATE = ToolSpec(
    name="truncate_text",
    description=(
        "Truncate text to fit within a token budget. Two strategies: "
        "'tail' keeps the head, 'head' keeps the tail. Never splits a "
        "Unicode code point."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to truncate.",
            },
            "max_tokens": {
                "type": "integer",
                "minimum": 0,
                "default": 4000,
            },
            "strategy": {
                "type": "string",
                "enum": ["head", "tail"],
                "default": "tail",
            },
            "message_overhead": {
                "type": "integer",
                "minimum": 0,
                "default": 0,
            },
        },
        "required": ["text"],
        "additionalProperties": False,
    },
)

TOOL_BUDGET = ToolSpec(
    name="context_budget",
    description=(
        "Sum token estimates across a list of chat messages and report "
        "the remaining capacity against a token limit. Flags overflow "
        "and preserves message order."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string"},
                        "content": {"type": "string"},
                        "name": {
                            "type": ["string", "null"],
                        },
                    },
                    "required": ["role", "content"],
                    "additionalProperties": False,
                },
            },
            "limit": {
                "type": "integer",
                "minimum": 0,
                "default": 8192,
            },
            "message_overhead": {
                "type": "integer",
                "minimum": 0,
                "default": 4,
            },
        },
        "required": ["messages"],
        "additionalProperties": False,
    },
)

TOOLS: tuple[ToolSpec, ...] = (TOOL_ESTIMATE, TOOL_TRUNCATE, TOOL_BUDGET)


class MCPServer:
    """A small JSON-RPC 2.0 dispatcher.

    Holds no state between requests; suitable for a one-process-per-connection
    stdio server. Initialise once, then call :meth:`handle_frame` for each
    incoming line.
    """

    def __init__(self) -> None:
        self._methods: dict[str, Callable[[dict[str, Any] | None, Any], dict[str, Any]]] = {
            "initialize": self._initialize,
            "ping": self._ping,
            "tools/list": self._tools_list,
            "tools/call": self._tools_call,
        }

    # --- public API -----------------------------------------------------

    def handle_frame(self, raw_line: str) -> str | None:
        """Decode one JSON-RPC frame and return its response (or ``None``
        for notifications / void responses).
        """
        stripped = raw_line.strip()
        if not stripped:
            return None
        try:
            frame = json.loads(stripped, strict=False)
        except json.JSONDecodeError as exc:
            return self._error_response(
                None, -32700, f"Parse error: {exc.msg}", {"position": exc.pos}
            )
        if not isinstance(frame, dict):
            return self._error_response(None, -32600, "Invalid Request: frame must be an object")
        request_id = frame.get("id")
        method = frame.get("method")
        params = frame.get("params")
        if not isinstance(method, str):
            return self._error_response(request_id, -32600, "Invalid Request: 'method' must be a string")

        handler = self._methods.get(method)
        if handler is None:
            return self._error_response(request_id, -32601, f"Method not found: {method}")

        try:
            result = handler(params, request_id)
        except (TypeError, ValueError) as exc:
            return self._error_response(request_id, -32602, f"Invalid params: {exc}")
        if result is None:
            return None
        return json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "result": result},
            ensure_ascii=False,
            separators=(",", ":"),
        )

    # --- handlers -------------------------------------------------------

    def _initialize(self, params: dict[str, Any] | None, request_id: Any) -> dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "serverInfo": dict(SERVER_INFO),
            "capabilities": {"tools": {"listChanged": False}},
        }

    def _ping(self, params: dict[str, Any] | None, request_id: Any) -> dict[str, Any]:
        return {}

    def _tools_list(self, params: dict[str, Any] | None, request_id: Any) -> dict[str, Any]:
        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema,
                }
                for tool in TOOLS
            ]
        }

    def _tools_call(self, params: dict[str, Any] | None, request_id: Any) -> dict[str, Any]:
        if not isinstance(params, dict):
            raise ValueError("tools/call params must be an object")
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            raise ValueError("tools/call requires a string 'name'")
        if not isinstance(arguments, dict):
            raise ValueError("tools/call 'arguments' must be an object")

        if name == TOOL_ESTIMATE.name:
            payload = _estimate_to_json(arguments)
        elif name == TOOL_TRUNCATE.name:
            payload = _truncate_to_json(arguments)
        elif name == TOOL_BUDGET.name:
            payload = _budget_to_json(arguments)
        else:
            raise ValueError(f"unknown tool: {name!r}")

        # MCP wraps results in a {"content": [...], "isError": bool} envelope.
        return {"content": [{"type": "json", "data": payload}], "isError": False}

    # --- error helpers --------------------------------------------------

    def _error_response(
        self, request_id: Any, code: int, message: str, data: Any | None = None
    ) -> str:
        err: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "error": err},
            ensure_ascii=False,
            separators=(",", ":"),
        )


# --- per-tool converters --------------------------------------------------


def _estimate_to_json(arguments: dict[str, Any]) -> dict[str, Any]:
    text = arguments.get("text", "")
    encoding = arguments.get("encoding", "cl100k_approx")
    message_overhead = arguments.get("message_overhead", 4)
    est = estimate(
        text,
        encoding=encoding,  # type: ignore[arg-type]
        message_overhead=message_overhead,
    )
    return {
        "op": "estimate",
        "tokens": est.tokens,
        "confidence": est.confidence,
        "method": est.method,
        "details": est.details,
    }


def _truncate_to_json(arguments: dict[str, Any]) -> dict[str, Any]:
    text = arguments.get("text", "")
    max_tokens = arguments.get("max_tokens", 4000)
    strategy = arguments.get("strategy", "tail")
    message_overhead = arguments.get("message_overhead", 0)
    res = truncate(
        text,
        max_tokens=max_tokens,
        strategy=strategy,  # type: ignore[arg-type]
        message_overhead=message_overhead,
    )
    return {
        "op": "truncate",
        "text": res.text,
        "tokens": res.tokens,
        "truncated": res.truncated,
        "strategy": res.strategy,
        "budget": res.budget,
        "original_tokens": res.original_tokens,
    }


def _budget_to_json(arguments: dict[str, Any]) -> dict[str, Any]:
    raw_messages = arguments.get("messages", [])
    if not isinstance(raw_messages, list):
        raise ValueError("'messages' must be a list")
    limit = arguments.get("limit", 8192)
    message_overhead = arguments.get("message_overhead", 4)
    messages = [
        m if isinstance(m, Message) else Message.from_mapping(m)
        for m in raw_messages
    ]
    report = budget_report(
        messages, limit=limit, message_overhead=message_overhead
    )
    return {
        "op": "budget",
        "total_tokens": report.total_tokens,
        "limit": report.limit,
        "remaining": report.remaining,
        "overflow": report.overflow,
        "overhead_per_message": report.overhead_per_message,
        "per_message": list(report.per_message),
        "count": report.details["count"],
    }


# --- stdio driver ---------------------------------------------------------


def serve_stdio(
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Run the MCP server until EOF on stdin. Returns the process exit code."""
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    server = MCPServer()
    for raw in stdin:
        response = server.handle_frame(raw)
        if response is None:
            continue
        stdout.write(response + "\n")
        stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:  # pragma: no cover — script entry
    return serve_stdio()


if __name__ == "__main__":  # pragma: no cover — script entry
    raise SystemExit(main())


# --- re-export so callers can route through the same dispatcher ---------


def handle_request(request: Any) -> str:
    """Pass-through to :func:`contextlens.jsonl.handle_request` for tests."""
    return jsonl_handle_request(request)