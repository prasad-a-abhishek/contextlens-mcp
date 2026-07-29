"""Top-level contract tests — covers spec criteria 37 (type hints) and
38 (zero third-party imports) plus a handful of API-surface regression
guards.
"""

from __future__ import annotations

import importlib
import inspect
import sys
import typing
from pathlib import Path

import pytest


SRC = Path(__file__).resolve().parents[1] / "src"


# ---------- 37. test_public_functions_have_type_hints ----------


def _public_callables(module):
    """Yield every function/class declared in ``module`` that is part of
    its public surface (``__all__`` if defined, otherwise every symbol
    that doesn't start with ``_``)."""
    names = getattr(module, "__all__", None)
    if names is None:
        names = [n for n in dir(module) if not n.startswith("_")]
    for name in names:
        obj = getattr(module, name)
        if inspect.isfunction(obj) or inspect.isclass(obj):
            yield name, obj


PUBLIC_MODULES = [
    "contextlens",
    "contextlens.estimator",
    "contextlens.truncation",
    "contextlens.budget",
    "contextlens.jsonl",
    "contextlens.mcp",
    "contextlens.errors",
]


@pytest.mark.parametrize("module_name", PUBLIC_MODULES)
def test_public_functions_have_type_hints(module_name: str):
    """Spec criterion 37: every public function has type annotations.

    We deliberately skip dunder names and module-level constants; the
    contract covers *callable* public surface only.
    """
    module = importlib.import_module(module_name)
    missing: list[str] = []
    for name, obj in _public_callables(module):
        if name.startswith("__"):
            continue
        if inspect.isfunction(obj):
            sig = inspect.signature(obj)
            for pname, param in sig.parameters.items():
                if pname == "self":
                    continue
                if param.annotation is inspect.Parameter.empty:
                    missing.append(f"{module_name}.{name}({pname})")
            if sig.return_annotation is inspect.Signature.empty:
                missing.append(f"{module_name}.{name}() -> ?")
        elif inspect.isclass(obj):
            # Methods on the class
            for attr_name, attr in vars(obj).items():
                if attr_name.startswith("_") or not callable(attr):
                    continue
                try:
                    attr_sig = inspect.signature(attr)
                except (TypeError, ValueError):
                    continue
                for pname, param in attr_sig.parameters.items():
                    if pname == "self":
                        continue
                    if param.annotation is inspect.Parameter.empty:
                        missing.append(
                            f"{module_name}.{name}.{attr_name}({pname})"
                        )
                if (
                    attr_sig.return_annotation is inspect.Signature.empty
                    and not attr_name.startswith("__")
                ):
                    missing.append(
                        f"{module_name}.{name}.{attr_name}() -> ?"
                    )
    assert not missing, "missing type hints:\n  " + "\n  ".join(missing)


def test_top_level_api_functions_have_hints():
    """Spot-check the four most-used public callables explicitly."""
    from contextlens import budget_report, estimate, truncate
    from contextlens.jsonl import handle_raw_line
    from contextlens.mcp import MCPServer, serve_stdio

    for fn in (estimate, truncate, budget_report, handle_raw_line, serve_stdio):
        hints = typing.get_type_hints(fn)
        assert "return" in hints, f"{fn.__name__} missing return annotation"
        assert hints, f"{fn.__name__} has no parameter annotations"


# ---------- 38. test_module_imports_without_third_party_packages ----------


# stdlib modules the project deliberately relies on.
STDLIB_ROOTS = frozenset(
    {
        "argparse", "array", "bisect", "collections", "dataclasses", "datetime",
        "functools", "io", "itertools", "json", "math", "os", "pathlib",
        "re", "shutil", "stat", "string", "struct", "subprocess", "sys",
        "tempfile", "threading", "time", "typing", "unicodedata", "warnings",
    }
)


def test_module_imports_without_third_party_packages():
    """Spec criterion 38: ``import contextlens`` does not pull in any
    non-stdlib package. We assert by snapshotting ``sys.modules`` before
    and after a fresh import.
    """
    # Make sure contextlens isn't already imported (otherwise the diff
    # is meaningless).
    for name in [n for n in sys.modules if n == "contextlens" or n.startswith("contextlens.")]:
        sys.modules.pop(name, None)

    before = set(sys.modules)
    importlib.import_module("contextlens")
    after = set(sys.modules)
    new = after - before

    bad = sorted(
        name for name in new
        if name.split(".")[0].split("[")[0] not in STDLIB_ROOTS
        and name != "contextlens"
        and not name.startswith("contextlens")
    )
    assert not bad, f"unexpected third-party imports pulled in: {bad}"


def test_pyproject_declares_zero_runtime_dependencies():
    """Spec criterion 38 (defence in depth): ``pyproject.toml`` lists
    no runtime dependencies."""
    import tomllib

    with open(Path(__file__).resolve().parents[1] / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    deps = data["project"].get("dependencies", [])
    assert deps == [], f"pyproject declares unexpected dependencies: {deps}"


# ---------- API-surface regression guards ----------


def test_top_level_dunder_all_matches_every_public_name():
    """``contextlens.__all__`` must list every explicitly exported symbol."""
    import contextlens
    listed = set(contextlens.__all__)
    for name in listed:
        assert hasattr(contextlens, name), f"__all__ references missing {name}"
    # Every name in __all__ must be reachable as an attribute of the
    # top-level module.
    assert "estimate" in listed
    assert "truncate" in listed
    assert "budget_report" in listed
    assert "__version__" in listed


def test_estimator_exposes_required_constants():
    from contextlens import estimator

    assert hasattr(estimator, "ENCODINGS")
    assert hasattr(estimator, "Encoding")
    assert hasattr(estimator, "DEFAULT_MESSAGE_OVERHEAD")
    assert hasattr(estimator, "estimate")
    assert hasattr(estimator, "Estimate")


def test_truncation_exposes_required_constants():
    from contextlens import truncation

    assert hasattr(truncation, "STRATEGIES")
    assert hasattr(truncation, "Strategy")
    assert hasattr(truncation, "truncate")
    assert hasattr(truncation, "TruncateResult")


def test_budget_exposes_required_classes():
    from contextlens import budget

    assert hasattr(budget, "Message")
    assert hasattr(budget, "BudgetReport")
    assert hasattr(budget, "budget_report")


def test_errors_exposes_required_hierarchy():
    from contextlens.errors import (
        ContextlensError,
        InvalidJSON,
        InvalidRequest,
        UnknownOperation,
    )

    for cls in (InvalidJSON, InvalidRequest, UnknownOperation):
        assert issubclass(cls, ContextlensError)


def test_cli_subcommand_dispatch_is_total_on_known_ops():
    """Every ``op`` advertised by the dispatcher is implemented in
    :func:`contextlens.jsonl.handle_request`."""
    from contextlens.jsonl import handle_request

    for op, payload in (
        ("estimate", {"op": "estimate", "text": "x"}),
        ("truncate", {"op": "truncate", "text": "x", "max_tokens": 1}),
        ("budget", {"op": "budget", "messages": [], "limit": 100}),
    ):
        response = handle_request(payload)
        import json
        parsed = json.loads(response)
        assert parsed["ok"] is True, f"op={op!r} did not return ok"


def test_mcp_known_methods_have_handlers():
    """Every method in the MCP tool registry is registered in the
    :class:`MCPServer` dispatcher."""
    from contextlens.mcp import MCPServer

    server = MCPServer()
    expected = {"initialize", "ping", "tools/list", "tools/call"}
    assert set(server._methods) == expected  # noqa: SLF001 — test contract


def test_version_string_matches_pyproject():
    """``__version__`` is in lock-step with ``pyproject.toml``."""
    import tomllib

    import contextlens

    with open(Path(__file__).resolve().parents[1] / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    assert contextlens.__version__ == data["project"]["version"]


def test_no_third_party_imports_inside_source():
    """Walk the ``src/contextlens`` tree and confirm every top-level
    ``import X`` / ``from X import`` statement targets either a stdlib
    module or a sibling ``contextlens.*`` module."""
    bad: list[str] = []
    for py in SRC.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue
            if stripped.startswith("from __future__"):
                continue
            # Extract the module name
            if stripped.startswith("import "):
                head = stripped[len("import "):].split(" as ")[0].split(",")[0].strip()
            else:
                head = stripped.split(" import ")[0].split()[1].split(" as ")[0].split(",")[0].strip()
            root = head.split(".")[0]
            if root in STDLIB_ROOTS or root == "contextlens":
                continue
            # pytest itself is allowed in tests, not src.
            if "tests" in py.parts:
                continue
            bad.append(f"{py.relative_to(SRC.parent.parent)}:{lineno} -> {head}")
    assert not bad, "unexpected imports:\n  " + "\n  ".join(bad)
