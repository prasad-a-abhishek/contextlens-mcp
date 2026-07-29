"""Tests for :func:`contextlens.budget_report` — covers spec criteria 8–11, 35–36."""

from __future__ import annotations

import pytest

from contextlens.budget import BudgetReport, Message, budget_report


def _msg(role: str, content: str, name: str | None = None) -> Message:
    return Message(role=role, content=content, name=name)


# ---------- 8. test_budget_report_sums_messages ----------


def test_budget_report_sums_messages():
    """Spec criterion 8: total_tokens is the sum of per-message tokens."""
    msgs = [_msg("user", "hi"), _msg("assistant", "hello")]
    r = budget_report(msgs, limit=100, message_overhead=0)
    # 1 + 2 = 3 base tokens (no overhead).
    assert r.total_tokens == 3
    assert sum(r.per_message) == r.total_tokens


def test_budget_report_sums_messages_with_default_overhead():
    """Default 4-token overhead per message adds up."""
    msgs = [_msg("user", "hi"), _msg("assistant", "hello")]
    r = budget_report(msgs, limit=100)
    # (1 + 4) + (2 + 4) = 11.
    assert r.total_tokens == 11


def test_budget_report_empty_messages_yields_zero_total():
    """Empty input list → 0 total tokens (and 0 count)."""
    r = budget_report([], limit=100)
    assert r.total_tokens == 0
    assert r.remaining == 100
    assert r.overflow is False
    assert r.per_message == ()
    assert r.details["count"] == 0


# ---------- 9. test_budget_report_reports_remaining_capacity ----------


def test_budget_report_reports_remaining_capacity():
    """Spec criterion 9: ``remaining`` = limit - total, floored at 0."""
    r = budget_report(
        [_msg("user", "a" * 16)], limit=10, message_overhead=0
    )  # 4 base tokens
    assert r.total_tokens == 4
    assert r.remaining == 6
    assert r.overflow is False


def test_budget_report_remaining_floored_at_zero():
    """Spec criterion 9: ``remaining`` never goes negative."""
    r = budget_report(
        [_msg("user", "a" * 100)], limit=1, message_overhead=0
    )
    assert r.overflow is True
    assert r.remaining == 0


# ---------- 10. test_budget_report_flags_overflow ----------


def test_budget_report_flags_overflow():
    """Spec criterion 10: ``overflow`` is True iff total > limit."""
    over = budget_report(
        [_msg("user", "a" * 100)], limit=5, message_overhead=0
    )
    assert over.overflow is True
    under = budget_report(
        [_msg("user", "hi")], limit=100, message_overhead=0
    )
    assert under.overflow is False
    exact = budget_report(
        [_msg("user", "a" * 4)], limit=1, message_overhead=0
    )
    assert exact.overflow is False


def test_budget_report_overflow_exactly_at_limit_is_not_overflow():
    """Boundary: total == limit is *not* overflow."""
    # "abcd" → ceil(4/4)=1 base.
    r = budget_report(
        [_msg("user", "abcd")], limit=1, message_overhead=0
    )
    assert r.overflow is False
    assert r.remaining == 0


# ---------- 11. test_budget_report_preserves_message_order ----------


def test_budget_report_preserves_message_order():
    """Spec criterion 11: per_message and messages track input order."""
    msgs = [
        _msg("system", "You are a helpful assistant."),
        _msg("user", "What is 2+2?"),
        _msg("assistant", "4"),
        _msg("user", "And 3+3?"),
    ]
    r = budget_report(msgs, limit=1000)
    assert [m.role for m in r.messages] == ["system", "user", "assistant", "user"]
    assert [m.content for m in r.messages] == [m.content for m in msgs]
    assert len(r.per_message) == 4


def test_budget_report_messages_tuple_is_immutable_view():
    """Returned messages is a tuple, not a list — order is preserved."""
    r = budget_report([_msg("user", "hi")], limit=10)
    assert isinstance(r.messages, tuple)
    assert isinstance(r.per_message, tuple)


# ---------- 35. test_budget_report_accepts_role_content_messages ----------


def test_budget_report_accepts_role_content_messages():
    """Spec criterion 35: dict-style messages with role+content work."""
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    r = budget_report(msgs, limit=100, message_overhead=0)
    assert r.total_tokens == 3
    assert [m.role for m in r.messages] == ["user", "assistant"]


def test_budget_report_accepts_name_field():
    """Optional ``name`` is preserved in the report."""
    msgs = [{"role": "user", "content": "hi", "name": "alice"}]
    r = budget_report(msgs, limit=100)
    assert r.messages[0].name == "alice"


def test_budget_report_accepts_message_instances_directly():
    """Message instances flow through without re-mapping."""
    msgs = [_msg("user", "hi")]
    r = budget_report(msgs, limit=100)
    assert r.messages[0] is msgs[0]


# ---------- 36. test_budget_report_rejects_missing_content ----------


def test_budget_report_rejects_missing_content():
    """Spec criterion 36: messages without ``content`` raise ValueError."""
    with pytest.raises(ValueError, match="content"):
        budget_report(
            [{"role": "user"}],  # type: ignore[list-item]
            limit=100,
        )


def test_budget_report_rejects_missing_role():
    """Symmetric to #36: missing ``role`` raises ValueError."""
    with pytest.raises(ValueError, match="role"):
        budget_report(
            [{"content": "hi"}],  # type: ignore[list-item]
            limit=100,
        )


def test_budget_report_rejects_non_string_content():
    """Spec criterion 36: non-string ``content`` is rejected."""
    with pytest.raises(ValueError):
        budget_report(
            [{"role": "user", "content": 42}],  # type: ignore[list-item]
            limit=100,
        )


def test_budget_report_rejects_non_string_role():
    with pytest.raises(ValueError):
        budget_report(
            [{"role": 1, "content": "hi"}],  # type: ignore[list-item]
            limit=100,
        )


def test_budget_report_rejects_non_string_name():
    with pytest.raises(ValueError):
        budget_report(
            [{"role": "user", "content": "hi", "name": 5}],  # type: ignore[list-item]
            limit=100,
        )


# ---------- cross-cutting edge cases -------------------------------------


def test_budget_report_dataclass_has_expected_fields():
    r = budget_report([_msg("user", "hi")], limit=10)
    assert isinstance(r, BudgetReport)
    assert hasattr(r, "total_tokens")
    assert hasattr(r, "limit")
    assert hasattr(r, "remaining")
    assert hasattr(r, "overflow")
    assert hasattr(r, "per_message")
    assert hasattr(r, "messages")
    assert hasattr(r, "overhead_per_message")
    assert hasattr(r, "details")


def test_budget_report_rejects_negative_limit():
    with pytest.raises(ValueError):
        budget_report([_msg("user", "hi")], limit=-1)


def test_budget_report_rejects_non_int_limit():
    with pytest.raises(TypeError):
        budget_report([_msg("user", "hi")], limit="100")  # type: ignore[arg-type]


def test_budget_report_rejects_negative_overhead():
    with pytest.raises(ValueError):
        budget_report([_msg("user", "hi")], limit=100, message_overhead=-1)


def test_budget_report_rejects_non_int_overhead():
    with pytest.raises(TypeError):
        budget_report(
            [_msg("user", "hi")], limit=100, message_overhead="4"  # type: ignore[arg-type]
        )


def test_budget_report_rejects_unsupported_message_type():
    with pytest.raises(TypeError):
        budget_report(["not a message"], limit=100)  # type: ignore[list-item]


def test_budget_report_per_message_independently_counted():
    """Per-message counts are not double-counted."""
    msgs = [
        _msg("user", "a" * 4),     # 1 token
        _msg("assistant", "b" * 8),  # 2 tokens
        _msg("user", "c" * 12),    # 3 tokens
    ]
    r = budget_report(msgs, limit=100, message_overhead=0)
    assert r.per_message == (1, 2, 3)
    assert r.total_tokens == 6


def test_budget_report_preserves_role_in_messages():
    msgs = [_msg("system", "x"), _msg("user", "y"), _msg("assistant", "z")]
    r = budget_report(msgs, limit=100)
    assert [m.role for m in r.messages] == ["system", "user", "assistant"]


def test_budget_report_unicode_messages_counted():
    """Spec criterion 3 again: unicode messages count correctly."""
    msgs = [_msg("user", "é" * 8)]  # 16 multi-byte bytes → 4 base + 1 surcharge = 5
    r = budget_report(msgs, limit=100, message_overhead=0)
    assert r.per_message == (5,)


def test_budget_report_limit_zero_always_overflows():
    """Edge: limit=0 with any non-empty content overflows."""
    r = budget_report([_msg("user", "hi")], limit=0)
    assert r.overflow is True
    assert r.remaining == 0


def test_budget_report_message_from_mapping_with_none_name():
    msg = Message.from_mapping({"role": "user", "content": "hi", "name": None})
    assert msg.name is None


def test_budget_report_message_from_mapping_without_name():
    """Missing name field defaults to None."""
    msg = Message.from_mapping({"role": "user", "content": "hi"})
    assert msg.name is None


def test_budget_report_details_count_field_is_correct():
    r = budget_report(
        [_msg("user", "a"), _msg("user", "b"), _msg("user", "c")],
        limit=100,
    )
    assert r.details["count"] == 3


def test_budget_report_iterates_messages_twice_consistently():
    """Re-iterating (a generator-style input) yields the same report."""
    def gen():
        yield _msg("user", "a")
        yield _msg("assistant", "b")

    once = budget_report(gen(), limit=100)
    twice = budget_report(gen(), limit=100)
    assert once.total_tokens == twice.total_tokens
    assert once.per_message == twice.per_message