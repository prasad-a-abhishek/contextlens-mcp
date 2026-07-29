# Changelog

## 0.1.0 — 2026-07-29 — initial release

First public release of contextlens.

**Added**

- `estimate(text, *, encoding="cl100k_approx", message_overhead=4)` —
  deterministic token count with confidence label and accounting
  details. Pure-Python, no third-party dependencies.
- `truncate(text, *, max_tokens=4000, strategy="tail", message_overhead=0)` —
  UTF-8-safe truncation with `tail` (keep head) and `head` (keep tail)
  strategies. Never splits a Unicode code point.
- `budget_report(messages, *, limit=8192, message_overhead=4)` —
  multi-message budget report with per-message token counts, remaining
  capacity, overflow flag, and preserved message order.
- JSONL CLI (`python -m contextlens`) — reads requests on stdin,
  emits responses on stdout, handles malformed input gracefully with
  structured error responses.
- MCP stdio server (`python -m contextlens.mcp`) — JSON-RPC 2.0 with
  `initialize`, `ping`, `tools/list`, `tools/call` methods.
  Advertises three tools: `estimate_tokens`, `truncate_text`,
  `context_budget`.
- 176 passing tests, including coverage of all 38 spec acceptance
  criteria and contract guards (type hints, zero runtime deps).

**Known limitations**

- Estimates are approximate, not model-exact (within ±15% of cl100k
  for typical English/code text).
- Single encoding family supported: `cl100k_approx`.
- MCP transport is stdio-only; HTTP/SSE is out of scope.
