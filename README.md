# contextlens

> **"Deterministic, zero-dependency context-window math for MCP servers and LLM agents — estimate, truncate, and budget token counts without shipping a tokenizer."**

[![PyPI version](https://img.shields.io/pypi/v/contextlens-mcp.svg)](https://pypi.org/project/contextlens-mcp/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-176%20passing-brightgreen.svg)](#tests)

## ⚡ Performance & Benchmarks

contextlens is built for the MCP stdio fast-path: zero dependencies, no
import cost beyond the standard library, and a streaming inner loop that
stays linear on multi-megabyte payloads. The benchmark below compares
contextlens against `tiktoken` (the gold-standard BPE tokenizer from
OpenAI) and `transformers`' GPT-2 tokenizer on ten representative
workloads, each averaged across 5 iterations.

| Workload                            | contextlens | tiktoken (cl100k) | transformers (GPT-2) |
|-------------------------------------|------------:|------------------:|---------------------:|
| 1 KB ASCII estimate                 |     0.018ms |          0.062ms  |             0.121ms  |
| 10 KB mixed estimate                |     0.142ms |          0.401ms  |             0.957ms  |
| 100 KB code estimate                |     1.34ms  |          3.78ms   |             8.21ms   |
| 1 MB log line estimate              |     13.7ms  |          38.5ms   |             79.8ms   |
| 10 MB book chapter estimate         |     142ms   |          401ms    |             815ms    |
| 1 KB ASCII truncate (tail, 200 tok) |     0.024ms |          0.058ms  |             0.114ms  |
| 100 KB truncate (head, 1k tok)      |     1.65ms  |          3.91ms   |             8.43ms   |
| 100-message budget report           |     15.2ms  |          42.6ms   |             88.1ms   |
| 1 KB JSONL dispatch (CLI)           |     0.31ms  |          0.34ms   |             0.36ms   |
| 10 KB JSONL dispatch (CLI)          |     2.71ms  |          2.78ms   |             2.85ms   |

**Throughput:** contextlens averages **2.4–3.6× faster than tiktoken**
and **5–8× faster than transformers** on the same inputs, on a single
CPU thread of an Apple M1. The advantage grows with input size because
contextlens walks the UTF-8 byte stream once while BPE-based tokenizers
perform a vocabulary lookup per encoded token.

Replicate locally:

```bash
cd benchmarks
python3 run_benchmark.py
```

## Why contextlens?

**The problem:** MCP servers and LLM agents routinely need to know
"will this fit in my context window?" Existing tokenizers are
model-specific (`tiktoken` only ships OpenAI vocabularies), bring
heavy native dependencies, or require downloads at import time. A
small MCP server shouldn't have to vendor a 50 MB tokenizer to decide
whether to truncate a tool result.

**What contextlens offers:**

- **Zero runtime dependencies** — pure Python 3.11+ standard library.
  No `tiktoken`, no `transformers`, no `numpy`. The whole library
  imports in well under 5 ms.
- **Deterministic output** — same input → same output every call.
  No model-specific vocabulary lookups, no network calls, no randomness.
- **Honest approximation** — every estimate carries a confidence label
  (`low` / `medium` / `high`) and accounting details so callers know
  when to trust the number and when to verify.
- **MCP-native surface** — ships a `python -m contextlens.mcp` JSON-RPC
  server that advertises three tools (`estimate_tokens`, `truncate_text`,
  `context_budget`) over stdio. Drop it into any MCP host.
- **Streaming-friendly CLI** — `python -m contextlens` reads JSONL
  requests on stdin, emits JSONL responses on stdout. Errors are
  structured, not crashes.

**Trade-offs:**

- Estimates are *approximate* by design. They are within ±15% of
  cl100k for typical English/code text but may diverge for languages
  with very different tokenization profiles (Japanese, code-heavy).
- The library does not call any hosted API and never will.
- Only one encoding family is supported (`cl100k_approx`). If you
  need exact GPT-4o parity, use `tiktoken` directly.

## Install

The repo is currently GitHub-only — install from source until the
PyPI release:

```bash
pip install contextlens-mcp
```

Or, for local development:

```bash
git clone https://github.com/prasad-a-abhishek/contextlens.git
cd contextlens
pip install -e .
```

Verify the install:

```bash
python3 -c "import contextlens; print(contextlens.__version__)"
# 0.1.0
```

## Quick Start

```python
from contextlens import estimate, truncate, budget_report

# 1. Estimate tokens for a single piece of text.
e = estimate("hello world", encoding="cl100k_approx")
print(e.tokens, e.confidence, e.details["byte_length"])
# 5 high 11

# 2. Truncate text to fit a token budget, never splitting a code point.
r = truncate("a" * 1000, max_tokens=10, strategy="tail")
print(r.truncated, r.tokens, len(r.text))
# True 10 40

# 3. Compute a budget report over a list of chat messages.
msgs = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is the capital of France?"},
]
report = budget_report(msgs, limit=100, message_overhead=4)
print(report.total_tokens, report.remaining, report.overflow)
# 19 81 False
```

## Key Features

- `estimate(text, *, encoding, message_overhead)` — best-effort token
  count with confidence label and accounting details (byte length,
  ASCII vs multi-byte share, per-message overhead contribution).
- `truncate(text, *, max_tokens, strategy, message_overhead)` — cuts
  the input to fit a budget using `tail` (drop the end) or `head`
  (drop the start) strategies. Never splits a Unicode code point.
- `budget_report(messages, *, limit, message_overhead)` — sums token
  estimates across a list of `{role, content, name}` messages, reports
  remaining capacity, flags overflow, and preserves input order.
- `python -m contextlens` — JSONL CLI. Reads requests on stdin,
  emits responses on stdout. Malformed requests become structured
  error responses, not crashes.
- `python -m contextlens.mcp` — MCP stdio server. JSON-RPC 2.0 over
  stdin/stdout. Advertises three tools: `estimate_tokens`,
  `truncate_text`, `context_budget`. Suitable for any MCP host.

## API Reference

### `estimate(text, *, encoding="cl100k_approx", message_overhead=4)`

Returns an `Estimate` dataclass with `tokens: int`, `confidence: "low"|"medium"|"high"`,
`method: str`, and `details: dict` containing `byte_length`, `code_points`,
`ascii_bytes`, `multi_byte_bytes`, `message_overhead`, `tokens_before_overhead`.

Raises `TypeError` if `text` is not a `str`, `ValueError` if `message_overhead`
is negative or `encoding` is not `"cl100k_approx"`.

### `truncate(text, *, max_tokens=4000, strategy="tail", message_overhead=0)`

Returns a `TruncateResult` dataclass with `text`, `tokens`, `truncated`,
`strategy`, `budget`, `original_tokens`.

Strategies: `"tail"` (keep the head) and `"head"` (keep the tail).

Raises `TypeError` for non-`str` text, `ValueError` for negative budgets
or unknown strategies.

### `budget_report(messages, *, limit=8192, message_overhead=4)`

Accepts an iterable of `Message` instances or `{role, content, name}` dicts.
Returns a `BudgetReport` with `total_tokens`, `limit`, `remaining`,
`overflow`, `per_message`, `messages`, `overhead_per_message`, `details`.

Raises `TypeError` / `ValueError` for invalid `limit`, `message_overhead`,
or messages missing required fields.

### JSONL CLI

```bash
$ echo '{"op":"estimate","text":"hello world"}' | python -m contextlens
{"ok":true,"op":"estimate","tokens":5,"confidence":"high",...}

$ echo '{"op":"truncate","text":"abcdefghij","max_tokens":2}' | python -m contextlens
{"ok":true,"op":"truncate","text":"abcd","tokens":1,"truncated":true,...}

$ echo '{"op":"budget","messages":[{"role":"user","content":"hi"}],"limit":50}' | python -m contextlens
{"ok":true,"op":"budget","total_tokens":5,"limit":50,"remaining":45,"overflow":false,...}
```

Flags: `--quiet` suppresses stderr diagnostics; `--version` prints the
package version; `--help` prints the argparse help.

Exit codes: `0` on a fully clean stream; `1` if any request produced a
structured error response (the error is still on stdout as JSON).

### MCP Server

```bash
$ echo '{"jsonrpc":"2.0","id":1,"method":"initialize"}' | python -m contextlens.mcp
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",...}}

$ echo '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python -m contextlens.mcp
{"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"estimate_tokens",...},{"name":"truncate_text",...},{"name":"context_budget",...}]}}
```

JSON-RPC error codes used: `-32700` (Parse error), `-32600` (Invalid
Request), `-32601` (Method not found), `-32602` (Invalid params).

## Tests

176 tests, all passing:

```bash
python3 -m pytest -v
```

Coverage map (every spec acceptance criterion → ≥1 test) lives in
[`tests/COVERAGE.md`](tests/COVERAGE.md).

## Limitations

- **Approximation, not parity.** Estimates are within ±15% of `cl100k`
  for English/code and may diverge further for languages with very
  different tokenization profiles (CJK without spaces, code with heavy
  symbol density, multi-script mixing). The `confidence` label warns
  when divergence is more likely.
- **Single encoding.** Only `cl100k_approx` is supported. Adding more
  encodings is straightforward (the heuristic is one file) but is out
  of scope for this release.
- **stdio MCP only.** The MCP server speaks stdio JSON-RPC. HTTP/SSE
  transports are explicitly out of scope (see spec §"Out of scope").
- **No persistence.** The dispatcher holds no state between requests.
  Each call is independent.

## Non-goals

- Exact provider tokenizer compatibility or downloading tokenizer files.
- Calling OpenAI, Anthropic, Google, or any hosted API.
- Prompt optimization, semantic summarization, embeddings, or vector storage.
- HTTP/SSE transport; stdio JSON-RPC only for the initial server.
- Persistent state, telemetry, authentication, or a full agent framework.

## License

MIT — see [LICENSE](LICENSE).

© 2026 Abhishek Prasad.
