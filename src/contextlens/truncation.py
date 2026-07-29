"""UTF-8-safe truncation with two strategies.

The two strategies mirror the conventional "keep the head" / "keep the
tail" choices found in chat-completion clients:

- ``"head"`` — drop characters from the end until the estimate fits.
- ``"tail"`` — drop characters from the start until the estimate fits.

Both strategies operate on the raw string, then re-estimate with
:func:`contextlens.estimator.estimate` so the returned ``tokens`` field
reflects the *actual* measurement of the truncated text rather than the
arithmetic we used to plan the cut.

Truncation is **never allowed to split a Unicode code point**. We walk
the string until the encoded-UTF-8 byte budget would be exceeded, then
back off to the previous code-point boundary. This matters for emoji,
combining marks, and CJK — every code point survives intact or is
removed wholesale.

If the budget is so small that even a single character would exceed
it, the result is the empty string with ``truncated=True``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from contextlens.estimator import estimate

Strategy = Literal["head", "tail"]

STRATEGIES: Final[frozenset[str]] = frozenset({"head", "tail"})

# When the per-call budget is so tight that no single character fits,
# we still need a meaningful "single character" cost so the algorithm
# can decide whether to drop everything. We use the ASCII cost (1/4
# token) as the cheapest possible single-character cost.
_MIN_TOKEN_FRACTION: Final[float] = 0.25


@dataclass(frozen=True)
class TruncateResult:
    """Structured result of :func:`truncate`.

    Attributes
    ----------
    text:
        The truncated (or original, if no cut was needed) text.
    tokens:
        The estimated token count of ``text``.
    truncated:
        ``True`` iff any code points were dropped from the input.
    strategy:
        The strategy that was applied (``"head"`` or ``"tail"``).
    budget:
        The token budget that was enforced.
    original_tokens:
        Estimated tokens *before* truncation.
    """

    text: str
    tokens: int
    truncated: bool
    strategy: str
    budget: int
    original_tokens: int


def truncate(
    text: str,
    *,
    max_tokens: int = 4000,
    strategy: Strategy | str = "tail",
    message_overhead: int = 0,
) -> TruncateResult:
    """Truncate ``text`` to fit within ``max_tokens``.

    Parameters
    ----------
    text:
        The string to truncate. Must be a ``str``.
    max_tokens:
        The inclusive upper bound on tokens. Negative or non-int values
        raise :class:`ValueError` / :class:`TypeError`. A budget of
        ``0`` yields an empty result.
    strategy:
        ``"tail"`` keeps the start, drops the end; ``"head"`` keeps the
        end, drops the start. Any other value raises :class:`ValueError`.
    message_overhead:
        Forwarded to :func:`contextlens.estimator.estimate` so the
        truncated text's reported token count matches what callers will
        see if they re-estimate it on its own.

    Returns
    -------
    :class:`TruncateResult` — see its docstring.

    Raises
    ------
    TypeError
        If ``text`` is not ``str`` or ``max_tokens`` / ``message_overhead``
        are not ``int``.
    ValueError
        If ``max_tokens`` is negative or ``strategy`` is unknown.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
        raise TypeError(f"max_tokens must be int, got {type(max_tokens).__name__}")
    if max_tokens < 0:
        raise ValueError(f"max_tokens must be >= 0, got {max_tokens}")
    if strategy not in STRATEGIES:
        raise ValueError(
            f"unknown strategy: {strategy!r}; supported: {sorted(STRATEGIES)}"
        )
    if isinstance(message_overhead, bool) or not isinstance(message_overhead, int):
        raise TypeError(
            f"message_overhead must be int, got {type(message_overhead).__name__}"
        )
    if message_overhead < 0:
        raise ValueError(
            f"message_overhead must be >= 0, got {message_overhead}"
        )

    original = estimate(
        text, message_overhead=message_overhead
    )
    original_tokens = original.tokens

    if max_tokens == 0:
        return TruncateResult(
            text="",
            tokens=message_overhead,
            truncated=(text != ""),
            strategy=strategy,
            budget=max_tokens,
            original_tokens=original_tokens,
        )

    # Reserve budget for the per-message overhead. The remaining budget
    # is what the content itself may use.
    content_budget = max_tokens - message_overhead
    if content_budget <= 0:
        # Overhead alone fills the budget; drop everything else.
        return TruncateResult(
            text="",
            tokens=message_overhead,
            truncated=(text != ""),
            strategy=strategy,
            budget=max_tokens,
            original_tokens=original_tokens,
        )

    # If the original fits, return it untouched.
    if original_tokens <= max_tokens:
        return TruncateResult(
            text=text,
            tokens=original_tokens,
            truncated=False,
            strategy=strategy,
            budget=max_tokens,
            original_tokens=original_tokens,
        )

    out, was_truncated = _truncate_to_budget(
        text, content_budget=content_budget, strategy=strategy
    )
    out_estimate = estimate(out, message_overhead=message_overhead)
    return TruncateResult(
        text=out,
        tokens=out_estimate.tokens,
        truncated=was_truncated,
        strategy=strategy,
        budget=max_tokens,
        original_tokens=original_tokens,
    )


def _truncate_to_budget(
    text: str,
    *,
    content_budget: int,
    strategy: str,
) -> tuple[str, bool]:
    """Cut ``text`` until its token estimate fits ``content_budget``.

    We work byte-wise over the UTF-8 encoding (constant-time per code
    point) and never split a multi-byte sequence.
    """
    # We treat the byte budget as `4 * content_budget` — matching the
    # estimator's 4-bytes-per-token baseline. The re-estimate at the
    # end corrects any overshoot from non-ASCII text.
    byte_budget = content_budget * 4

    if strategy == "tail":
        # Keep the head — walk forward, drop from the end.
        return _truncate_tail(text, byte_budget)
    return _truncate_head(text, byte_budget)


def _truncate_tail(text: str, byte_budget: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="surrogateescape")
    if len(encoded) <= byte_budget:
        return text, False

    # Walk code points until adding the next one would exceed budget.
    out_chars: list[str] = []
    used = 0
    for ch in text:
        ch_bytes = len(ch.encode("utf-8", errors="surrogateescape"))
        if used + ch_bytes > byte_budget:
            break
        out_chars.append(ch)
        used += ch_bytes
    out = "".join(out_chars)
    return out, (out != text)


def _truncate_head(text: str, byte_budget: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="surrogateescape")
    if len(encoded) <= byte_budget:
        return text, False

    # Keep the tail — drop from the start. We collect code points from
    # the end backwards.
    out_chars: list[str] = []
    used = 0
    for ch in reversed(text):
        ch_bytes = len(ch.encode("utf-8", errors="surrogateescape"))
        if used + ch_bytes > byte_budget:
            break
        out_chars.append(ch)
        used += ch_bytes
    out_chars.reverse()
    out = "".join(out_chars)
    return out, (out != text)


__all__ = [
    "STRATEGIES",
    "Strategy",
    "TruncateResult",
    "truncate",
]