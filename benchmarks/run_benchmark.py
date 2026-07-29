"""Head-to-head benchmark: contextlens vs tiktoken vs transformers.

Self-contained — no third-party deps required to *run* the benchmark
itself (the competitors are loaded lazily and skipped with a clear
message if they're missing). Run from the repo root:

    python3 benchmarks/run_benchmark.py

Produces a Markdown table on stdout suitable for pasting into
`benchmarks/BENCHMARK.md` and `README.md`. The table reports the mean
elapsed milliseconds across 5 iterations for each of 10 workloads.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from contextlens import budget_report, estimate, truncate  # noqa: E402

# When this script runs inside its own .benchvenv (which has tiktoken /
# transformers but not the editable install of contextlens), the CLI
# subprocess for JSONL dispatch must use the *system* Python where
# contextlens is installed.
SYSTEM_PYTHON = sys.executable

# Workloads: (label, factory_callable_returning_input)
def _ascii(n_bytes: int) -> str:
    return "a" * n_bytes


def _mixed(n_bytes: int) -> str:
    # Mix ASCII and multi-byte to exercise the multibyte surcharge.
    chunk = "héllo世界! "
    repeats = (n_bytes // len(chunk.encode("utf-8"))) + 1
    return (chunk * repeats)[:n_bytes]


def _code(n_bytes: int) -> str:
    snippet = "def f(x):\n    return x * 2\n\n"
    repeats = (n_bytes // len(snippet.encode("utf-8"))) + 1
    return (snippet * repeats)[:n_bytes]


def _chat(n_messages: int) -> list:
    return [
        {"role": "system", "content": "You are a helpful assistant. " * 5},
        {"role": "user", "content": "Hi there, can you help me with something?"},
        {"role": "assistant", "content": "Of course! What would you like to know?"},
    ] * (n_messages // 3)


WORKLOADS = [
    ("1 KB ASCII estimate",       lambda: ("estimate",   _ascii(1024))),
    ("10 KB mixed estimate",      lambda: ("estimate",   _mixed(10 * 1024))),
    ("100 KB code estimate",      lambda: ("estimate",   _code(100 * 1024))),
    ("1 MB log line estimate",    lambda: ("estimate",   _ascii(1024 * 1024))),
    ("10 MB book chapter estimate", lambda: ("estimate", _ascii(10 * 1024 * 1024))),
    ("1 KB ASCII truncate",       lambda: ("truncate",   _ascii(1024), 200, "tail")),
    ("100 KB truncate (head, 1k)", lambda: ("truncate",  _mixed(100 * 1024), 1000, "head")),
    ("100-message budget report", lambda: ("budget",     _chat(100), 4096)),
    ("1 KB JSONL dispatch (CLI)",  lambda: ("jsonl",      _ascii(1024))),
    ("10 KB JSONL dispatch (CLI)", lambda: ("jsonl",      _ascii(10 * 1024))),
]

ITERATIONS = 5


def _bench_callable(fn, iterations: int) -> float:
    """Return median milliseconds across ``iterations`` runs of ``fn``."""
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return statistics.median(samples)


def _bench_contextlens() -> list[float]:
    results = []
    for label, factory in WORKLOADS:
        def call():
            args = factory()
            op = args[0]
            if op == "estimate":
                text = args[1]
                estimate(text, message_overhead=0)
            elif op == "truncate":
                text, budget, strategy = args[1], args[2], args[3]
                truncate(text, max_tokens=budget, strategy=strategy, message_overhead=0)
            elif op == "budget":
                msgs, limit = args[1], args[2]
                budget_report(msgs, limit=limit, message_overhead=0)
            elif op == "jsonl":
                # Use the system Python (where contextlens is installed)
                # for a true subprocess measurement.
                text = args[1]
                payload = json.dumps({"op": "estimate", "text": text})
                subprocess.run(
                    [SYSTEM_PYTHON, "-m", "contextlens"],
                    input=payload,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
        results.append(_bench_callable(call, ITERATIONS))
    return results


def _bench_tiktoken() -> list[float] | None:
    try:
        import tiktoken
    except ImportError:
        return None

    enc = tiktoken.get_encoding("cl100k_base")

    def do_estimate(text: str) -> None:
        enc.encode(text)

    def do_truncate(text: str, budget: int, strategy: str) -> None:
        ids = enc.encode(text)
        if strategy == "tail":
            ids = ids[:budget]
        else:
            ids = ids[-budget:]
        enc.decode(ids)

    def do_budget(msgs, limit: int) -> None:
        ids = enc.encode("\n".join(m["content"] for m in msgs))
        if len(ids) > limit:
            ids = ids[:limit]

    results = []
    for label, factory in WORKLOADS:
        def call():
            args = factory()
            op = args[0]
            if op == "estimate":
                do_estimate(args[1])
            elif op == "truncate":
                do_truncate(args[1], args[2], args[3])
            elif op == "budget":
                do_budget(args[1], args[2])
            elif op == "jsonl":
                payload = json.dumps({"op": "estimate", "text": args[1]})
                subprocess.run(
                    [sys.executable, "-m", "contextlens"],
                    input=payload,
                    capture_output=True,
                    text=True,
                    check=True,
                )
        results.append(_bench_callable(call, ITERATIONS))
    return results


def _bench_transformers() -> list[float] | None:
    try:
        from transformers import GPT2TokenizerFast
    except ImportError:
        return None

    tok = GPT2TokenizerFast.from_pretrained("gpt2")

    def do_estimate(text: str) -> None:
        tok.encode(text)

    def do_truncate(text: str, budget: int, strategy: str) -> None:
        ids = tok.encode(text)
        if strategy == "tail":
            ids = ids[:budget]
        else:
            ids = ids[-budget:]
        tok.decode(ids)

    def do_budget(msgs, limit: int) -> None:
        ids = tok.encode("\n".join(m["content"] for m in msgs))
        if len(ids) > limit:
            ids = ids[:limit]

    results = []
    for label, factory in WORKLOADS:
        def call():
            args = factory()
            op = args[0]
            if op == "estimate":
                do_estimate(args[1])
            elif op == "truncate":
                do_truncate(args[1], args[2], args[3])
            elif op == "budget":
                do_budget(args[1], args[2])
            elif op == "jsonl":
                payload = json.dumps({"op": "estimate", "text": args[1]})
                subprocess.run(
                    [sys.executable, "-m", "contextlens"],
                    input=payload,
                    capture_output=True,
                    text=True,
                    check=True,
                )
        results.append(_bench_callable(call, ITERATIONS))
    return results


def main() -> int:
    print(f"Running benchmark with {ITERATIONS} iterations per workload...\n")

    ours = _bench_contextlens()
    tiktok = _bench_tiktoken()
    transf = _bench_transformers()

    # Emit markdown table.
    print("| Workload                            | contextlens | tiktoken (cl100k) | transformers (GPT-2) |")
    print("|-------------------------------------|------------:|------------------:|---------------------:|")
    for (label, _), ms_ours, ms_tt, ms_tf in zip(WORKLOADS, ours, tiktok or [None] * len(ours), transf or [None] * len(ours)):
        col1 = f"{ms_ours:>10.3f}ms"
        col2 = f"{ms_tt:>16.3f}ms" if ms_tt is not None else "             n/a   "
        col3 = f"{ms_tf:>19.3f}ms" if ms_tf is not None else "                  n/a"
        print(f"| {label:<35} | {col1} | {col2} | {col3} |")

    print()
    if tiktok is not None:
        speedups = [t / o for t, o in zip(tiktok, ours)]
        print(f"Average speedup vs tiktoken:       {statistics.mean(speedups):.2f}×")
    if transf is not None:
        speedups = [t / o for t, o in zip(transf, ours)]
        print(f"Average speedup vs transformers:   {statistics.mean(speedups):.2f}×")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
