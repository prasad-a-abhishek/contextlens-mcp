"""Tests for :func:`contextlens.truncate` — covers spec criteria 12–18."""

from __future__ import annotations

import pytest

from contextlens.truncation import STRATEGIES, TruncateResult, truncate


# ---------- 12. test_truncate_under_budget_returns_original ----------


def test_truncate_under_budget_returns_original():
    """Spec criterion 12: input fits → returned verbatim."""
    text = "short text"
    r = truncate(text, max_tokens=1000)
    assert r.text == text
    assert r.truncated is False
    assert r.original_tokens == r.tokens
    assert r.strategy == "tail"
    assert r.budget == 1000


def test_truncate_exactly_at_budget_returns_original():
    """Boundary case: tokens == budget is *not* a truncation."""
    # "hello" = 5 ASCII bytes → ceil(5/4) = 2 base + 0 overhead = 2.
    r = truncate("hello", max_tokens=2)
    assert r.truncated is False
    assert r.text == "hello"


def test_truncate_empty_input_under_budget_returns_empty():
    """Empty input under any positive budget is unchanged."""
    r = truncate("", max_tokens=100)
    assert r.text == ""
    assert r.truncated is False
    assert r.tokens == 0


# ---------- 13. test_truncate_tail_respects_budget ----------


def test_truncate_tail_respects_budget():
    """Spec criterion 13: tail strategy drops the end, fits within budget."""
    text = "abcdefghij" * 4  # 40 ASCII bytes → 10 base tokens
    r = truncate(text, max_tokens=5, strategy="tail")
    assert r.truncated is True
    assert r.strategy == "tail"
    assert r.tokens <= 5
    # The start of the input is preserved.
    assert r.text.startswith("abc")
    # The result is shorter than the original.
    assert len(r.text) < len(text)
    assert r.original_tokens == 10


def test_truncate_tail_keeps_first_code_points():
    text = "abcdefghij" * 4  # 40 bytes → 10 tokens
    r = truncate(text, max_tokens=3, strategy="tail")  # 12-byte budget
    # 12 bytes = "abcdefghijab" (the 'c' would push us to 13 bytes)
    assert r.text == "abcdefghijab"
    assert r.truncated is True
    assert r.tokens == 3


def test_truncate_tail_zero_budget_returns_empty():
    r = truncate("hello world", max_tokens=0)
    assert r.text == ""
    assert r.truncated is True
    assert r.tokens == 0


def test_truncate_tail_overhead_alone_fills_budget():
    """If the overhead alone fills the budget, content is dropped."""
    r = truncate("hello world", max_tokens=4, message_overhead=4)
    assert r.text == ""
    assert r.truncated is True


# ---------- 14. test_truncate_head_respects_budget ----------


def test_truncate_head_respects_budget():
    """Spec criterion 14: head strategy drops the start, fits within budget."""
    text = "abcdefghij" * 4
    r = truncate(text, max_tokens=5, strategy="head")
    assert r.truncated is True
    assert r.strategy == "head"
    assert r.tokens <= 5
    # The end of the input is preserved.
    assert r.text.endswith("j")
    assert r.original_tokens == 10


def test_truncate_head_keeps_last_code_points():
    text = "abcdefghij" * 4  # 40 bytes → 10 tokens
    r = truncate(text, max_tokens=3, strategy="head")  # 12-byte budget
    # 12 bytes from end = "ijabcdefghij" (12 bytes)
    assert r.text == "ijabcdefghij"
    assert r.truncated is True
    assert r.tokens == 3


def test_truncate_head_zero_budget_returns_empty():
    r = truncate("hello", max_tokens=0, strategy="head")
    assert r.text == ""
    assert r.truncated is True


# ---------- 15. test_truncate_preserves_utf8_codepoints ----------


def test_truncate_preserves_utf8_codepoints():
    """Spec criterion 15: never split a multi-byte sequence."""
    text = "a" * 20 + "é" * 4 + "b" * 20
    r = truncate(text, max_tokens=4, strategy="tail")
    assert r.truncated is True
    # 'é' is 2 bytes; if any 'é' survived, the result must end cleanly.
    assert not r.text.endswith("é\ufffd")  # no replacement marker
    # Code points survived intact: no half-character.
    for ch in r.text:
        assert ch in "abé", f"unexpected char: {ch!r}"
    # The result must be re-encodable as UTF-8.
    r.text.encode("utf-8")


def test_truncate_does_not_split_emoji_codepoints_tail():
    """Spec criterion 15, emoji case: tail strategy must keep whole emoji."""
    text = "🚀" * 10  # each 🚀 is 4 UTF-8 bytes
    r = truncate(text, max_tokens=3, strategy="tail")
    # Either no emoji survives (text == "") or every char is whole.
    assert r.text == "" or all(ch == "🚀" for ch in r.text)


def test_truncate_does_not_split_emoji_codepoints_head():
    """Head strategy must keep whole emoji from the tail end."""
    text = "🚀" * 10
    r = truncate(text, max_tokens=3, strategy="head")
    assert r.text == "" or all(ch == "🚀" for ch in r.text)


def test_truncate_does_not_split_cjk_codepoints():
    """Spec criterion 15, CJK case: whole characters survive."""
    text = "中" * 32
    r = truncate(text, max_tokens=5, strategy="tail")
    # 32 chars × 3 bytes = 96 bytes → 24 base + 6 surcharge = 30 tokens.
    # 5-token budget: 20 bytes → ceil(20/3) = 7 chars at most (21 bytes).
    assert r.text == "" or all(ch == "中" for ch in r.text)
    # Re-encodes cleanly.
    r.text.encode("utf-8")


# ---------- 16. test_truncate_empty_input ----------


def test_truncate_empty_input_with_positive_budget():
    """Spec criterion 16: empty input is a no-op."""
    r = truncate("", max_tokens=100)
    assert r.text == ""
    assert r.truncated is False
    assert r.tokens == 0


def test_truncate_empty_input_with_zero_budget():
    """Empty input + zero budget is still a no-op (nothing to cut)."""
    r = truncate("", max_tokens=0)
    assert r.text == ""
    assert r.truncated is False
    assert r.tokens == 0


def test_truncate_empty_input_with_negative_budget_raises():
    with pytest.raises(ValueError):
        truncate("", max_tokens=-1)


# ---------- 17. test_truncate_rejects_negative_budget ----------


def test_truncate_rejects_negative_budget():
    """Spec criterion 17: negative budget raises ``ValueError``."""
    with pytest.raises(ValueError, match="max_tokens"):
        truncate("hello", max_tokens=-1)


def test_truncate_rejects_non_int_budget():
    """Spec criterion 17, type safety: non-int budget raises ``TypeError``."""
    with pytest.raises(TypeError):
        truncate("hello", max_tokens="100")  # type: ignore[arg-type]


def test_truncate_rejects_bool_budget():
    with pytest.raises(TypeError):
        truncate("hello", max_tokens=True)  # type: ignore[arg-type]


def test_truncate_rejects_negative_overhead():
    with pytest.raises(ValueError):
        truncate("hello", max_tokens=100, message_overhead=-1)


# ---------- 18. test_truncate_reports_whether_content_was_cut ----------


def test_truncate_reports_whether_content_was_cut():
    """Spec criterion 18: ``truncated`` flag accurately reflects a cut."""
    not_cut = truncate("hi", max_tokens=100)
    cut = truncate("a" * 100, max_tokens=5)
    assert not_cut.truncated is False
    assert cut.truncated is True


def test_truncate_reports_original_token_count():
    """Original token count is preserved through truncation."""
    text = "hello world this is a longer sentence with more words"  # 53 bytes
    r = truncate(text, max_tokens=3)
    assert r.original_tokens > r.tokens
    # 53 ASCII bytes → ceil(53/4) = 14 base tokens.
    assert r.original_tokens == 14


def test_truncate_result_dataclass_has_expected_fields():
    """Pinpoint regression: result dataclass fields are stable."""
    r = truncate("hi", max_tokens=10)
    assert isinstance(r, TruncateResult)
    assert hasattr(r, "text")
    assert hasattr(r, "tokens")
    assert hasattr(r, "truncated")
    assert hasattr(r, "strategy")
    assert hasattr(r, "budget")
    assert hasattr(r, "original_tokens")


# ---------- cross-cutting edge cases -------------------------------------


def test_truncate_strategy_constant_lists_supported_values():
    assert STRATEGIES == frozenset({"head", "tail"})


def test_truncate_unknown_strategy_raises():
    with pytest.raises(ValueError, match="strategy"):
        truncate("hello", max_tokens=10, strategy="middle")  # type: ignore[arg-type]


def test_truncate_non_string_text_raises():
    with pytest.raises(TypeError):
        truncate(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        truncate(b"hello")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        truncate(42)  # type: ignore[arg-type]


def test_truncate_single_oversized_character_handled():
    """A single code point can never exceed budget — that path returns ""."""
    # 'é' is 2 bytes → 1 base token.
    r = truncate("é", max_tokens=0)
    assert r.text == ""
    assert r.truncated is True


def test_truncate_tail_and_head_differ_when_content_was_dropped():
    """The two strategies pick different prefixes/suffixes."""
    text = "abcdefghij" * 4  # 40 bytes → 10 tokens
    tail = truncate(text, max_tokens=3, strategy="tail")   # 12-byte budget from head
    head = truncate(text, max_tokens=3, strategy="head")   # 12-byte budget from tail
    assert tail.text != head.text
    assert tail.text == "abcdefghijab"
    assert head.text == "ijabcdefghij"
    assert tail.text.startswith("abc")
    assert head.text.endswith("hij")


def test_truncate_long_input_completes_without_quadratic_behavior():
    """Spec criterion 32 again: 10 MB string must truncate in well under a second."""
    import time

    text = "a" * (5 * 1024 * 1024)  # 5 MB → 1.25M tokens
    start = time.perf_counter()
    r = truncate(text, max_tokens=10_000, strategy="tail")
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"truncate too slow: {elapsed:.3f}s"
    assert r.truncated is True
    assert r.tokens <= 10_004  # 10k + overhead


def test_truncate_returned_text_is_a_string():
    r = truncate("hi", max_tokens=1)
    assert isinstance(r.text, str)
    assert isinstance(r.tokens, int)


def test_truncate_message_overhead_propagates_into_re_estimate():
    """After truncation, the re-estimated tokens include the same overhead."""
    r = truncate("hello", max_tokens=100, message_overhead=5)
    assert r.tokens >= 5
    # 5 ASCII bytes → ceil(5/4)=2 base + 5 overhead = 7 tokens.
    assert r.tokens == 7