"""stdio JSON-RPC entry-point for the ``contextlens`` CLI.

Each line on stdin is a JSON object:

- ``{"op": "estimate", "text": "...", "encoding": "cl100k_approx"}``
- ``{"op": "truncate", "text": "...", "max_tokens": 4000}``
- ``{"op": "budget", "messages": [...], "limit": 8192}``

The CLI is intentionally total: a single malformed request does not
crash the process; it produces a structured error response so the
caller can keep streaming.

Stdout purity matters because clients (CI pipelines, our own tests)
parse stdout as JSON Lines. We therefore write every diagnostic to
stderr — ``print(..., file=sys.stderr)`` — and let ``log`` /
``logging`` default to stderr too. A ``--quiet`` flag additionally
suppresses stderr output for one-off use.
"""

from __future__ import annotations

import argparse
import sys

from contextlens import __version__
from contextlens.jsonl import handle_raw_line


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contextlens",
        description=(
            "Deterministic, zero-dependency context-window utilities. "
            "Reads JSON Lines requests on stdin, emits JSON Lines "
            "responses on stdout."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"contextlens {__version__}",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all diagnostic output (stderr).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return run(sys.stdin, sys.stdout, sys.stderr, quiet=args.quiet)


def run(stdin, stdout, stderr, *, quiet: bool = False) -> int:
    """Process stdin line-by-line, write responses to stdout.

    Returns ``0`` on success, ``1`` if any input frame was malformed.
    A malformed frame still produces its structured error response on
    stdout before the process exits.
    """
    error_count = 0
    for line in stdin:
        response = handle_raw_line(line)
        if not response:
            continue
        stdout.write(response)
        stdout.write("\n")
        stdout.flush()
        # We count malformed frames as a non-zero exit so CI can spot
        # regressions. ``handle_raw_line`` already wrote the structured
        # error — we just tally.
        if '"ok":false' in response:
            error_count += 1
    if error_count and not quiet:
        print(
            f"contextlens: {error_count} malformed request(s) on stdin",
            file=stderr,
        )
    return 1 if error_count else 0


if __name__ == "__main__":  # pragma: no cover — script entry
    raise SystemExit(main())