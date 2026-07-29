"""Multi-message budget reporting.

A :class:`Message` is the smallest unit the budget operates on — a
``role`` (string) and ``content`` (string). Both fields are required
because the spec's acceptance criterion #36 rejects messages that omit
``content``; we treat that as a structured error rather than a silent
default.

:class:`BudgetReport` sums per-message token estimates, reports the
remaining capacity against ``limit``, flags overflow, and preserves the
input order so callers can present a "first-N messages that fit"
view without re-implementing the bookkeeping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from contextlens.estimator import DEFAULT_MESSAGE_OVERHEAD, estimate

__all__ = ["Message", "BudgetReport", "budget_report"]


@dataclass(frozen=True)
class Message:
    """A single chat-style message.

    Attributes
    ----------
    role:
        Sender role — typically ``"system"``, ``"user"``, or
        ``"assistant"``. Free-form so callers can use custom protocol
        markers.
    content:
        Message body. Required — see :func:`budget_report`.
    name:
        Optional author identifier (carried verbatim into the report).
    """

    role: str
    content: str
    name: str | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "Message":
        """Build a :class:`Message` from a dict-like object.

        Raises :class:`ValueError` if a required field is missing or
        the wrong type. ``name`` is optional.
        """
        if "role" not in raw:
            raise ValueError("message is missing required field 'role'")
        role = raw["role"]
        if not isinstance(role, str):
            raise ValueError(
                f"message.role must be str, got {type(role).__name__}"
            )
        if "content" not in raw:
            raise ValueError("message is missing required field 'content'")
        content = raw["content"]
        if not isinstance(content, str):
            raise ValueError(
                f"message.content must be str, got {type(content).__name__}"
            )
        name_raw = raw.get("name")
        name: str | None
        if name_raw is None:
            name = None
        elif isinstance(name_raw, str):
            name = name_raw
        else:
            raise ValueError(
                f"message.name must be str or None, got {type(name_raw).__name__}"
            )
        return cls(role=role, content=content, name=name)


@dataclass(frozen=True)
class BudgetReport:
    """Structured output of :func:`budget_report`.

    Attributes
    ----------
    total_tokens:
        Sum of per-message token estimates (includes the per-message
        overhead for every entry).
    limit:
        The budget cap the caller supplied.
    remaining:
        ``max(0, limit - total_tokens)``.
    overflow:
        ``True`` iff ``total_tokens > limit``.
    per_message:
        Token counts in the same order as the input messages.
    messages:
        The (role, content, name) tuples the report covers, verbatim.
    overhead_per_message:
        The overhead value used for every message.
    """

    total_tokens: int
    limit: int
    remaining: int
    overflow: bool
    per_message: tuple[int, ...]
    messages: tuple[Message, ...]
    overhead_per_message: int
    details: dict[str, int] = field(default_factory=dict)


def budget_report(
    messages: Iterable[Message | Mapping[str, Any]],
    *,
    limit: int = 8192,
    message_overhead: int = DEFAULT_MESSAGE_OVERHEAD,
) -> BudgetReport:
    """Compute a token-budget report for a list of messages.

    Parameters
    ----------
    messages:
        Any iterable yielding :class:`Message` instances or dict-like
        objects compatible with :meth:`Message.from_mapping`. Order is
        preserved in the returned report.
    limit:
        Total token budget. Non-negative ``int``; negative values
        raise :class:`ValueError`.
    message_overhead:
        Per-message overhead added by :func:`estimate`. Defaults to
        :data:`contextlens.estimator.DEFAULT_MESSAGE_OVERHEAD`.

    Returns
    -------
    :class:`BudgetReport`

    Raises
    ------
    TypeError
        If ``messages`` contains an unsupported type or ``limit`` /
        ``message_overhead`` are not ``int``.
    ValueError
        If ``limit`` or ``message_overhead`` is negative, or if a
        mapping-style message is missing ``role`` / ``content``.
    """
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError(f"limit must be int, got {type(limit).__name__}")
    if limit < 0:
        raise ValueError(f"limit must be >= 0, got {limit}")
    if isinstance(message_overhead, bool) or not isinstance(
        message_overhead, int
    ):
        raise TypeError(
            f"message_overhead must be int, got {type(message_overhead).__name__}"
        )
    if message_overhead < 0:
        raise ValueError(
            f"message_overhead must be >= 0, got {message_overhead}"
        )

    normalised: list[Message] = []
    per_message: list[int] = []
    for index, raw in enumerate(messages):
        if isinstance(raw, Message):
            msg = raw
        elif isinstance(raw, Mapping):
            msg = Message.from_mapping(raw)
        else:
            raise TypeError(
                f"messages[{index}] must be Message or Mapping, "
                f"got {type(raw).__name__}"
            )
        normalised.append(msg)
        per_message.append(
            estimate(msg.content, message_overhead=message_overhead).tokens
        )

    total = sum(per_message)
    remaining = max(0, limit - total)
    overflow = total > limit

    return BudgetReport(
        total_tokens=total,
        limit=limit,
        remaining=remaining,
        overflow=overflow,
        per_message=tuple(per_message),
        messages=tuple(normalised),
        overhead_per_message=message_overhead,
        details={"count": len(normalised)},
    )