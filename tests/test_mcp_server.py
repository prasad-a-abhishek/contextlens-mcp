"""Tests for the MCP stdio server — covers spec criteria 23–28."""

from __future__ import annotations

import json

from contextlens.mcp import (
    MCPServer,
    PROTOCOL_VERSION,
    SERVER_INFO,
    TOOLS,
    ToolSpec,
    handle_request,
    serve_stdio,
)


def _server() -> MCPServer:
    return MCPServer()


def _call(server: MCPServer, raw: str) -> str:
    response = server.handle_frame(raw)
    assert response is not None
    # Return the raw JSON-RPC string; callers json.loads themselves.
    return response


def _call_parsed(server: MCPServer, raw: str) -> dict:
    return json.loads(_call(server, raw))


# ---------- 23. test_mcp_tool_list_contains_three_tools ----------


def test_mcp_tool_list_contains_three_tools():
    """Spec criterion 23: exactly three tools are advertised."""
    server = _server()
    response = _call_parsed(
        server,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
    )
    tools = response["result"]["tools"]
    names = sorted(t["name"] for t in tools)
    assert names == ["context_budget", "estimate_tokens", "truncate_text"]
    assert len(tools) == 3


def test_mcp_tool_list_includes_descriptions_and_schemas():
    """Every tool advertises a description and an inputSchema."""
    server = _server()
    response = _call_parsed(
        server,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
    )
    for tool in response["result"]["tools"]:
        assert "description" in tool
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"


def test_mcp_tools_constant_has_three_entries():
    assert len(TOOLS) == 3
    assert {t.name for t in TOOLS} == {
        "estimate_tokens",
        "truncate_text",
        "context_budget",
    }
    for tool in TOOLS:
        assert isinstance(tool, ToolSpec)


# ---------- 24. test_mcp_estimate_tokens_tool_schema ----------


def test_mcp_estimate_tokens_tool_schema():
    """Spec criterion 24: ``estimate_tokens`` advertises the expected schema."""
    server = _server()
    response = _call_parsed(
        server,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
    )
    tool = next(
        t for t in response["result"]["tools"] if t["name"] == "estimate_tokens"
    )
    schema = tool["inputSchema"]
    props = schema["properties"]
    assert "text" in props
    assert props["text"]["type"] == "string"
    assert "encoding" in props
    assert props["encoding"]["enum"] == ["cl100k_approx"]
    assert "message_overhead" in props
    assert props["message_overhead"]["minimum"] == 0
    assert schema["required"] == ["text"]
    assert schema["additionalProperties"] is False


def test_mcp_estimate_tokens_tool_call_returns_structured_payload():
    """Calling ``estimate_tokens`` returns the token count + confidence."""
    server = _server()
    response = _call_parsed(
        server,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "estimate_tokens",
                    "arguments": {"text": "hello world"},
                },
            }
        ),
    )
    result = response["result"]
    assert result["isError"] is False
    content = result["content"]
    assert len(content) == 1
    assert content[0]["type"] == "json"
    payload = content[0]["data"]
    assert payload["op"] == "estimate"
    assert payload["tokens"] >= 1
    assert payload["confidence"] in {"low", "medium", "high"}


# ---------- 25. test_mcp_truncate_text_tool_schema ----------


def test_mcp_truncate_text_tool_schema():
    """Spec criterion 25: ``truncate_text`` schema is correct."""
    server = _server()
    response = _call_parsed(
        server,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
    )
    tool = next(
        t for t in response["result"]["tools"] if t["name"] == "truncate_text"
    )
    schema = tool["inputSchema"]
    props = schema["properties"]
    assert props["text"]["type"] == "string"
    assert props["max_tokens"]["type"] == "integer"
    assert props["max_tokens"]["minimum"] == 0
    assert props["strategy"]["enum"] == ["head", "tail"]
    assert schema["required"] == ["text"]
    assert schema["additionalProperties"] is False


def test_mcp_truncate_text_tool_call_returns_truncated_payload():
    server = _server()
    response = _call_parsed(
        server,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "truncate_text",
                    "arguments": {
                        "text": "a" * 100,
                        "max_tokens": 5,
                        "strategy": "tail",
                    },
                },
            }
        ),
    )
    payload = response["result"]["content"][0]["data"]
    assert payload["op"] == "truncate"
    assert payload["truncated"] is True
    assert payload["strategy"] == "tail"
    assert payload["tokens"] <= 5


# ---------- 26. test_mcp_context_budget_tool_schema ----------


def test_mcp_context_budget_tool_schema():
    """Spec criterion 26: ``context_budget`` schema is correct."""
    server = _server()
    response = _call_parsed(
        server,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
    )
    tool = next(
        t for t in response["result"]["tools"] if t["name"] == "context_budget"
    )
    schema = tool["inputSchema"]
    props = schema["properties"]
    assert props["messages"]["type"] == "array"
    item_schema = props["messages"]["items"]
    assert item_schema["required"] == ["role", "content"]
    assert props["limit"]["type"] == "integer"
    assert props["limit"]["minimum"] == 0
    assert schema["required"] == ["messages"]


def test_mcp_context_budget_tool_call_returns_report_payload():
    server = _server()
    response = _call_parsed(
        server,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "context_budget",
                    "arguments": {
                        "messages": [{"role": "user", "content": "hi"}],
                        "limit": 50,
                    },
                },
            }
        ),
    )
    payload = response["result"]["content"][0]["data"]
    assert payload["op"] == "budget"
    assert payload["total_tokens"] >= 1
    assert payload["overflow"] is False
    assert payload["count"] == 1


# ---------- 27. test_mcp_initialize_handshake ----------


def test_mcp_initialize_handshake():
    """Spec criterion 27: ``initialize`` returns the protocol handshake."""
    server = _server()
    response = _call_parsed(
        server,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "clientInfo": {"name": "test"},
                    "capabilities": {},
                },
            }
        ),
    )
    result = response["result"]
    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert result["serverInfo"] == SERVER_INFO
    assert "capabilities" in result
    assert "tools" in result["capabilities"]


def test_mcp_initialize_with_no_params():
    """``initialize`` tolerates empty params."""
    server = _server()
    response = _call_parsed(
        server,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
    )
    assert "result" in response


def test_mcp_ping_returns_empty_object():
    server = _server()
    response = _call_parsed(
        server,
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
    )
    assert response["result"] == {}


# ---------- 28. test_mcp_unknown_method_returns_jsonrpc_error ----------


def test_mcp_unknown_method_returns_jsonrpc_error():
    """Spec criterion 28: unknown method → -32601 Method not found."""
    server = _server()
    response = _call_parsed(
        server,
        json.dumps({"jsonrpc": "2.0", "id": 42, "method": "no/such/method"}),
    )
    assert "error" in response
    assert response["error"]["code"] == -32601
    assert "no/such/method" in response["error"]["message"]
    # The id is preserved in the error.
    assert response["id"] == 42


def test_mcp_invalid_json_returns_parse_error():
    """Malformed JSON yields -32700 Parse error."""
    server = _server()
    parsed = _call_parsed(server, "{not valid json at all")
    assert parsed["error"]["code"] == -32700
    assert "Parse error" in parsed["error"]["message"]


def test_mcp_invalid_jsonrpc_returns_invalid_request():
    """Frame that isn't a JSON object → -32600 Invalid Request."""
    server = _server()
    parsed = _call_parsed(server, "[1, 2, 3]")
    assert parsed["error"]["code"] == -32600


def test_mcp_missing_method_returns_invalid_request():
    server = _server()
    parsed = _call_parsed(
        server, json.dumps({"jsonrpc": "2.0", "id": 1, "params": {}})
    )
    assert parsed["error"]["code"] == -32600


def test_mcp_invalid_params_return_invalid_params():
    server = _server()
    parsed = _call_parsed(
        server,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": "not an object",
            }
        ),
    )
    assert parsed["error"]["code"] == -32602
    assert "params" in parsed["error"]["message"]


def test_mcp_unknown_tool_returns_invalid_params():
    server = _server()
    parsed = _call_parsed(
        server,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "no/such/tool", "arguments": {}},
            }
        ),
    )
    assert parsed["error"]["code"] == -32602


def test_mcp_id_preserved_in_error_response():
    server = _server()
    parsed = _call_parsed(
        server,
        json.dumps({"jsonrpc": "2.0", "id": "string-id", "method": "nope"}),
    )
    assert parsed["id"] == "string-id"


# ---------- subprocess integration ---------------------------------------


def test_mcp_subprocess_serves_full_session(run_mcp):
    """Spec criteria 23–28 covered via the actual CLI subprocess."""
    payload = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "estimate_tokens",
                        "arguments": {"text": "hi"},
                    },
                }
            ),
            json.dumps({"jsonrpc": "2.0", "id": 4, "method": "no/such"}),
        ]
    )
    result = run_mcp(payload)
    assert result.returncode == 0
    lines = [ln for ln in result.stdout.split("\n") if ln.strip()]
    assert len(lines) == 4
    # Every response is valid JSON-RPC.
    for ln in lines:
        parsed = json.loads(ln)
        assert parsed["jsonrpc"] == "2.0"
        assert "id" in parsed
        # Each request id appears exactly once in the output.
    ids = [json.loads(ln)["id"] for ln in lines]
    assert ids == [1, 2, 3, 4]


def test_mcp_subprocess_handles_malformed_then_valid(run_mcp):
    """A parse error followed by a valid request still serves both."""
    payload = "\n".join(
        [
            "{garbage",
            json.dumps({"jsonrpc": "2.0", "id": 9, "method": "ping"}),
        ]
    )
    result = run_mcp(payload)
    assert result.returncode == 0
    lines = [ln for ln in result.stdout.split("\n") if ln.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["error"]["code"] == -32700
    assert json.loads(lines[1])["id"] == 9


def test_mcp_serve_stdio_drives_until_eof():
    """serve_stdio handles all frames and returns 0."""
    import io

    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"
    )
    stdout = io.StringIO()
    rc = serve_stdio(stdin, stdout)
    assert rc == 0
    assert json.loads(stdout.getvalue().strip())["result"] == {}


def test_mcp_handle_request_passthrough_returns_jsonl_response():
    """The module-level handle_request passthrough routes to JSONL."""
    response = handle_request({"op": "estimate", "text": "hi"})
    parsed = json.loads(response)
    assert parsed["ok"] is True
    assert parsed["op"] == "estimate"


# ---------- typing & import contract --------------------------------------


def test_mcp_protocol_version_is_a_string():
    assert isinstance(PROTOCOL_VERSION, str)
    assert PROTOCOL_VERSION == "2024-11-05"


def test_mcp_server_info_carries_name_and_version():
    assert SERVER_INFO["name"] == "contextlens"
    assert SERVER_INFO["version"] == "0.1.0"