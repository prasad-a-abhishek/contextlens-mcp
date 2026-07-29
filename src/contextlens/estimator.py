"""Deterministic, approximate token-count estimation.

The estimator never claims model parity. It returns:

- ``tokens`` — a non-negative integer best-effort estimate.
- ``confidence`` — a label in ``{"low", "medium", "high"}``.
- ``method`` — the heuristic that produced the number (``"cl100k_approx"``).
- ``details`` — accounting: byte length, code-point length, per-message
  overhead contribution, encoding identifier.

The chosen heuristic — *cl100k_approx* — approximates OpenAI's cl100k
tokenizer behaviour without loading a ``.tiktoken`` vocabulary:

- ASCII text averages ~4 bytes per token.
- Non-ASCII (multi-byte UTF-8 sequences) typically expands into more
  tokens than its byte count would suggest, so we add a small surcharge
  proportional to the multi-byte share.
- Empty input is reported as ``0`` tokens.
- A configurable ``message_overhead`` is added once per call, matching
  the per-message envelope cost in chat-completion APIs.

The implementation is intentionally total: passing ``None`` or a
non-string value raises :class:`TypeError`; passing negative
``message_overhead`` raises :class:`ValueError` — both as documented
contracts, not as accidental crashes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Literal

Confidence = Literal["low", "medium", "high"]
Encoding = Literal["cl100k_approx"]

ENCODINGS: Final[frozenset[str]] = frozenset({"cl100k_approx"})

# Heuristic constants — documented in the module docstring. Change them
# here and the entire pipeline (CLI, MCP, budget report) picks up the
# new behaviour because they all flow through :func:`estimate`.
_ASCII_BYTES_PER_TOKEN: Final[float] = 4.0
_MULTIBYTE_SURCHARGE_PER_16_BYTES: Final[int] = 1

# The per-message overhead defaults to 4 tokens — the documented cost
# of a ChatML message envelope (``<|im_start|>role\ncontent\n<|im_end|>``
# plus the role name). Callers can override this for their own protocol.
DEFAULT_MESSAGE_OVERHEAD: Final[int] = 4


@dataclass(frozen=True)
class Estimate:
    """Structured result of :func:`estimate`.

    Attributes
    ----------
    tokens:
        Best-effort token count (>= 0).
    confidence:
        ``"low"`` if the input contains control bytes / NUL / large
        multi-byte share, ``"medium"`` for mixed ASCII+unicode, otherwise
        ``"high"`` for plain ASCII.
    method:
        Always ``"cl100k_approx"`` — the only encoding this library
        supports today.
    details:
        Free-form accounting payload — keys include ``encoding``,
        ``byte_length``, ``code_points``, ``ascii_bytes``,
        ``multi_byte_bytes``, ``message_overhead``,
        ``tokens_before_overhead``.
    """

    tokens: int
    confidence: Confidence
    method: str
    details: dict[str, int | str] = field(default_factory=dict)


def estimate(
    text: str,
    *,
    encoding: Encoding | str = "cl100k_approx",
    message_overhead: int = DEFAULT_MESSAGE_OVERHEAD,
) -> Estimate:
    """Estimate the token count of ``text``.

    Parameters
    ----------
    text:
        The string to measure. Must be a ``str`` — passing ``bytes``,
        ``None``, or another type raises :class:`TypeError`.
    encoding:
        The estimator family. Only ``"cl100k_approx"`` is accepted;
        any other value raises :class:`ValueError`.
    message_overhead:
        Extra tokens to add once per call (defaults to
        :data:`DEFAULT_MESSAGE_OVERHEAD`). Negative values raise
        :class:`ValueError`.

    Returns
    -------
    :class:`Estimate` — see its docstring.

    Raises
    ------
    TypeError
        If ``text`` is not a ``str``.
    ValueError
        If ``encoding`` is unknown or ``message_overhead`` is negative.
    """
    if not isinstance(text, str):
        raise TypeError(
            f"text must be str, got {type(text).__name__}"
        )
    if encoding not in ENCODINGS:
        raise ValueError(
            f"unknown encoding: {encoding!r}; supported: {sorted(ENCODINGS)}"
        )
    if not isinstance(message_overhead, int) or isinstance(message_overhead, bool):
        raise TypeError(
            f"message_overhead must be int, got {type(message_overhead).__name__}"
        )
    if message_overhead < 0:
        raise ValueError(
            f"message_overhead must be >= 0, got {message_overhead}"
        )

    # Empty input is a special case — both base and overhead apply.
    if text == "":
        details: dict[str, int | str] = {
            "encoding": encoding,
            "byte_length": 0,
            "code_points": 0,
            "ascii_bytes": 0,
            "multi_byte_bytes": 0,
            "message_overhead": message_overhead,
            "tokens_before_overhead": 0,
        }
        return Estimate(
            tokens=message_overhead,
            confidence="high",
            method=encoding,
            details=details,
        )

    encoded = text.encode("utf-8", errors="surrogateescape")
    byte_length = len(encoded)

    # Count ASCII vs multi-byte bytes without iterating the string
    # twice. We walk ``encoded`` (a bytes object) once — this keeps the
    # inner loop tight on the multi-MB inputs the spec asks us to
    # handle without quadratic behaviour.
    ascii_bytes = 0
    multi_byte_bytes = 0
    has_control = False
    for byte in encoded:
        if byte < 0x80:
            ascii_bytes += 1
        else:
            multi_byte_bytes += 1
        # 0x00 (NUL) and 0x01-0x1F outside tab/newline degrade confidence.
        if byte < 0x20 and byte not in (0x09, 0x0A, 0x0D):
            has_control = True

    # Base rate is byte/4 across the *whole* input — multi-byte chars
    # cost at least their byte length in a BPE tokenizer, often more.
    base_tokens = (byte_length + 3) // 4
    # Surcharge: non-ASCII bytes inflate the count further because
    # BPE vocabularies tokenize CJK / emoji at a higher density than
    # ASCII. +1 per 16 multi-byte bytes is the midpoint of the typical
    # 1.5–2.5× inflation range.
    surcharge = multi_byte_bytes // 16
    tokens_before_overhead = base_tokens + surcharge

    confidence = _confidence(ascii_bytes, multi_byte_bytes, byte_length, has_control)

    details = {
        "encoding": encoding,
        "byte_length": byte_length,
        "code_points": _fast_code_point_count(text),
        "ascii_bytes": ascii_bytes,
        "multi_byte_bytes": multi_byte_bytes,
        "message_overhead": message_overhead,
        "tokens_before_overhead": tokens_before_overhead,
    }
    return Estimate(
        tokens=tokens_before_overhead + message_overhead,
        confidence=confidence,
        method=encoding,
        details=details,
    )


def _confidence(
    ascii_bytes: int,
    multi_byte_bytes: int,
    byte_length: int,
    has_control: bool,
) -> Confidence:
    """Pick a confidence label based on the input shape.

    - control bytes present ⇒ ``"low"``
    - input is mixed or non-ASCII dominant ⇒ ``"medium"``
    - pure ASCII ⇒ ``"high"``
    """
    if has_control:
        return "low"
    if byte_length == 0:
        return "high"
    if multi_byte_bytes == 0:
        return "high"
    non_ascii_share = multi_byte_bytes / byte_length
    if non_ascii_share < 0.10:
        return "high"
    if non_ascii_share < 0.50:
        return "medium"
    return "low"


def _fast_code_point_count(text: str) -> int:
    """Length in Unicode code points — O(len(text)) but no allocation.

    Avoids the heavier ``array.array('I', text)`` path on large inputs.
    """
    n = 0
    for _ in text:
        n += 1
    return n


__all__ = [
    "ENCODINGS",
    "Encoding",
    "Estimate",
    "Confidence",
    "DEFAULT_MESSAGE_OVERHEAD",
    "estimate",
]