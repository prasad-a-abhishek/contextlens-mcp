# contextlens — Specification (cycle 10)

## Problem
MCP and LLM applications routinely need to decide whether a prompt, tool result, or conversation will fit a model's context window. Existing tokenizers are model-specific, dependency-heavy, or unavailable in minimal MCP deployments. Developers therefore guess token counts, truncate blindly, and discover overflow only after a remote API failure. A small standard-library tool can provide deterministic estimates, budgets, truncation, and explainable reports without embedding a model SDK.

## Evidence of need
- MCP server ecosystem discussion/issues repeatedly request lightweight, composable servers and better interoperability around tool output; the official MCP specification is a live protocol reference: https://modelcontextprotocol.io/specification/2025-06-18 (fetched 2026-07-29).
- MCP servers tracker issue discussing operational gaps and server usability: https://github.com/modelcontextprotocol/servers/issues/1160 (HTTP 200, fetched 2026-07-29).
- MCP specification repository issue concerning protocol behavior and implementer needs: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/206 (HTTP 200, fetched 2026-07-29).

## Proposed solution
A zero-dependency Python package and stdio MCP server exposing deterministic context utilities:

```python
from contextlens import estimate, truncate, budget_report
estimate("hello world", encoding="cl100k_approx")
truncate(text, max_tokens=4000, strategy="tail")
budget_report(messages, limit=8192)
```

The CLI accepts JSON Lines requests and emits JSON Lines responses; MCP mode exposes `estimate_tokens`, `truncate_text`, and `context_budget`. Estimation uses documented UTF-8 byte/character heuristics and optional per-message overhead, never claims exact model-token parity, and returns confidence plus accounting details.

## Target user
Developers building small MCP servers or LLM agents who need predictable context budgeting without installing a tokenizer or provider SDK.

## Repo metadata
- language: python
- name: contextlens
- pypi_name: contextlens (verified available: PyPI HTTP 404)
- npm_name: @prasadaabhishek/contextlens
- one-line description: Zero-dependency context-window estimation, truncation, and budgeting for MCP and LLM tools.
- deps: []
- types: type hints for Python 3.11+
- scope: both
- size budget: ≤700 LOC + tests

## Acceptance criteria (testable)
1. test_estimate_empty_text_returns_zero
2. test_estimate_ascii_is_deterministic
3. test_estimate_unicode_accounts_for_utf8
4. test_estimate_emoji_is_deterministic
5. test_estimate_returns_confidence_and_method
6. test_estimate_rejects_negative_overhead
7. test_message_overhead_is_applied
8. test_budget_report_sums_messages
9. test_budget_report_reports_remaining_capacity
10. test_budget_report_flags_overflow
11. test_budget_report_preserves_message_order
12. test_truncate_under_budget_returns_original
13. test_truncate_tail_respects_budget
14. test_truncate_head_respects_budget
15. test_truncate_preserves_utf8_codepoints
16. test_truncate_empty_input
17. test_truncate_rejects_negative_budget
18. test_truncate_reports_whether_content_was_cut
19. test_jsonl_estimate_request
20. test_jsonl_invalid_json_returns_structured_error
21. test_jsonl_unknown_operation_returns_error
22. test_jsonl_response_is_single_line_json
23. test_mcp_tool_list_contains_three_tools
24. test_mcp_estimate_tokens_tool_schema
25. test_mcp_truncate_text_tool_schema
26. test_mcp_context_budget_tool_schema
27. test_mcp_initialize_handshake
28. test_mcp_unknown_method_returns_jsonrpc_error
29. test_cli_reads_multiple_jsonl_requests
30. test_cli_does_not_write_logs_to_stdout
31. test_cli_nonzero_exit_on_malformed_request
32. test_long_input_completes_without_quadratic_behavior
33. test_null_character_is_counted
34. test_newline_and_tab_are_counted
35. test_budget_report_accepts_role_content_messages
36. test_budget_report_rejects_missing_content
37. test_public_functions_have_type_hints
38. test_module_imports_without_third_party_packages

## Out of scope
- Exact provider tokenizer compatibility or downloading tokenizer files.
- Calling OpenAI, Anthropic, Google, or any hosted API.
- Prompt optimization, semantic summarization, embeddings, or vector storage.
- HTTP/SSE transport; stdio JSON-RPC only for the initial server.
- Persistent state, telemetry, authentication, or a full agent framework.

## Competitive landscape
- tiktoken/tokenizers: more exact for selected models but require native/heavy dependencies and model vocabulary data; contextlens is portable and explicit about approximation.
- litellm and provider SDKs: broad API orchestration with substantial dependency and configuration surface; contextlens is an offline utility suitable for minimal MCP processes.
- MCP reference servers: provide domain tools but generally leave context accounting to each client; contextlens offers a reusable, protocol-native budgeting tool.

## Risk callouts
- Estimates must be labeled approximate; never promise API acceptance.
- JSON-RPC framing and stdout purity are critical because MCP clients parse stdout.
- Truncation must not split Unicode code points and should define behavior for a single oversized message.
- Keep protocol implementation minimal and standards-based; test malformed requests and IDs.
- Evidence is strongest for the broad MCP implementation need; exact demand for this particular estimator should be validated after release.
