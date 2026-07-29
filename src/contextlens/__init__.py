"""contextlens — zero-dependency context-window estimation for MCP & LLM tools.

Public API:

- :func:`estimate` — deterministic per-message token estimate.
- :func:`truncate` — text truncation that preserves UTF-8 code points.
- :func:`budget_report` — multi-message budget/overflow report.

CLI surface (see :mod:`contextlens.__main__`):

- ``python -m contextlens`` reads JSON Lines from stdin, emits one JSON
  Line per request to stdout. Three operations are recognised:
  ``estimate``, ``truncate``, ``budget``.

MCP surface (see :mod:`contextlens.mcp`):

- ``python -m contextlens.mcp`` speaks MCP-over-stdio (JSON-RPC 2.0).
  It advertises three tools: ``estimate_tokens``, ``truncate_text``,
  ``context_budget``.
"""

from __future__ import annotations

from contextlens.estimator import (
    ENCODINGS,
    Encoding,
    Estimate,
    estimate,
)
from contextlens.truncation import (
    STRATEGIES,
    Strategy,
    TruncateResult,
    truncate,
)
from contextlens.budget import (
    BudgetReport,
    Message,
    budget_report,
)
from contextlens.errors import (
    ContextlensError,
    InvalidJSON,
    InvalidRequest,
    UnknownOperation,
)

__version__ = "0.1.0"

__all__ = [
    # version
    "__version__",
    # estimator
    "estimate",
    "Estimate",
    "Encoding",
    "ENCODINGS",
    # truncation
    "truncate",
    "TruncateResult",
    "Strategy",
    "STRATEGIES",
    # budget
    "budget_report",
    "BudgetReport",
    "Message",
    # errors
    "ContextlensError",
    "InvalidJSON",
    "InvalidRequest",
    "UnknownOperation",
]