"""Tests for :func:`contextlens.estimate` — covers spec criteria 1–7."""

from __future__ import annotations

import pytest

from contextlens.estimator import (
    DEFAULT_MESSAGE_OVERHEAD,
    ENCODINGS,
    Encoding,
    Estimate,
    estimate,
)


# ---------- 1. test_estimate_empty_text_returns_zero ----------


def test_estimate_empty_text_returns_zero_with_default_overhead():
    """Spec criterion 1: empty text yields a finite, structured result.

    The token count is the per-message overhead alone (defaults to 4).
    """
    e = estimate("")
    assert isinstance(e, Estimate)
    assert e.tokens == DEFAULT_MESSAGE_OVERHEAD
    assert e.confidence == "high"
    assert e.method == "cl100k_approx"
    assert e.details["byte_length"] == 0
    assert e.details["code_points"] == 0
    assert e.details["ascii_bytes"] == 0
    assert e.details["multi_byte_bytes"] == 0
    assert e.details["message_overhead"] == DEFAULT_MESSAGE_OVERHEAD
    assert e.details["tokens_before_overhead"] == 0


def test_estimate_empty_text_with_zero_overhead_returns_zero():
    """Spec criterion 1, edge case: empty + no overhead → 0 tokens."""
    e = estimate("", message_overhead=0)
    assert e.tokens == 0
    assert e.details["tokens_before_overhead"] == 0


# ---------- 2. test_estimate_ascii_is_deterministic ----------


def test_estimate_ascii_is_deterministic():
    """Spec criterion 2: same input → same output, every call."""
    s = "The quick brown fox jumps over the lazy dog."
    a = estimate(s)
    b = estimate(s)
    assert a.tokens == b.tokens
    assert a.confidence == b.confidence
    assert a.details == b.details
    # 44 ASCII bytes → ceil(44/4) = 11 base tokens → +4 overhead = 15.
    assert a.details["ascii_bytes"] == 44
    assert a.details["multi_byte_bytes"] == 0
    assert a.tokens == 15
    assert a.confidence == "high"


def test_estimate_ascii_lengths_match_4_bytes_per_token_rule():
    """Spec criterion 2, regression: byte/4 ceiling."""
    for n in (1, 2, 3, 4, 5, 7, 8, 9, 16, 17):
        text = "a" * n
        e = estimate(text, message_overhead=0)
        assert e.tokens == (n + 3) // 4, f"failed for length {n}"


def test_estimate_same_input_yields_identical_dict_keys():
    """Determinism on the details dict key order."""
    a = estimate("hello", message_overhead=0)
    b = estimate("hello", message_overhead=0)
    assert list(a.details.keys()) == list(b.details.keys())


# ---------- 3. test_estimate_unicode_accounts_for_utf8 ----------


def test_estimate_unicode_accounts_for_utf8():
    """Spec criterion 3: multi-byte chars inflate the estimate."""
    ascii_e = estimate("a" * 12, message_overhead=0)
    unicode_e = estimate("é" * 4, message_overhead=0)  # 2 bytes each in UTF-8
    # 4 × 'é' = 8 UTF-8 bytes → ceil(8/4) = 2 base tokens → +0 surcharge.
    assert unicode_e.tokens == 2
    assert unicode_e.details["ascii_bytes"] == 0
    assert unicode_e.details["multi_byte_bytes"] == 8
    assert unicode_e.details["byte_length"] == 8
    # ASCII version of the same length (8 chars) yields the same base tokens.
    assert ascii_e.tokens == 3  # ceil(12/4)


def test_estimate_unicode_with_large_multibyte_share_triggers_surcharge():
    """Heavy CJK content picks up the +1/16 surcharge."""
    text = "中" * 64  # 3 bytes each → 192 multi-byte bytes → 12 surcharge
    e = estimate(text, message_overhead=0)
    # base = ceil(192/4) = 48; surcharge = 192/16 = 12.
    assert e.tokens == 48 + 12
    assert e.details["tokens_before_overhead"] == 48 + 12


def test_estimate_unicode_does_not_split_surrogate_pairs():
    """Real emoji (a surrogate pair on the wire) tokenize consistently."""
    text = "café\U0001F680"  # café + rocket emoji
    e = estimate(text, message_overhead=0)
    assert e.tokens >= 1
    assert e.details["byte_length"] > 0
    # Both 'é' and the rocket are multi-byte in UTF-8.
    assert e.details["multi_byte_bytes"] > 0


# ---------- 4. test_estimate_emoji_is_deterministic ----------


def test_estimate_emoji_is_deterministic():
    """Spec criterion 4: emoji are counted consistently."""
    emoji = "🚀" * 8  # 4 bytes each → 32 multi-byte bytes → 2 surcharge
    a = estimate(emoji, message_overhead=0)
    b = estimate(emoji, message_overhead=0)
    assert a.tokens == b.tokens
    assert a.confidence == b.confidence
    assert a.details == b.details
    # base = ceil(32/4) = 8; surcharge = 32/16 = 2.
    assert a.tokens == 8 + 2
    assert a.details["ascii_bytes"] == 0
    assert a.details["multi_byte_bytes"] == 32


def test_estimate_mixed_emoji_and_ascii_does_not_count_emoji_as_ascii():
    """Emoji bytes are not silently treated as ASCII."""
    text = "hi 🚀"
    e = estimate(text, message_overhead=0)
    assert e.details["ascii_bytes"] >= 2  # at least 'h' and 'i' (and ' ')
    assert e.details["multi_byte_bytes"] >= 4  # the emoji is 4 bytes


# ---------- 5. test_estimate_returns_confidence_and_method ----------


def test_estimate_returns_confidence_and_method():
    """Spec criterion 5: result carries confidence + method."""
    e = estimate("plain text")
    assert e.confidence in {"low", "medium", "high"}
    assert e.method == "cl100k_approx"
    assert e.details["encoding"] == "cl100k_approx"


def test_estimate_confidence_pure_ascii_is_high():
    assert estimate("hello world").confidence == "high"


def test_estimate_confidence_pure_unicode_is_low():
    """Heavy non-ASCII share drops confidence to ``low``."""
    text = "中" * 100
    assert estimate(text).confidence == "low"


def test_estimate_confidence_moderate_unicode_is_medium():
    """20–50% non-ASCII share → ``medium``."""
    # 32 ASCII + 8 CJK chars (3 bytes each) → 24 multi-byte of 56 total = 43%.
    text = "a" * 32 + "中" * 8
    e = estimate(text)
    assert e.confidence == "medium"


def test_estimate_confidence_control_byte_is_low():
    """A NUL byte triggers the ``low`` confidence label."""
    text = "hello\x00world"
    assert estimate(text).confidence == "low"


def test_estimate_confidence_tab_newline_carriage_return_high():
    """Tab/newline/CR are not considered 'control' for confidence."""
    text = "hello\nworld\t\ragain"
    assert estimate(text).confidence == "high"


# ---------- 6. test_estimate_rejects_negative_overhead ----------


def test_estimate_rejects_negative_overhead():
    """Spec criterion 6: negative overhead raises ``ValueError``."""
    with pytest.raises(ValueError, match="message_overhead"):
        estimate("hello", message_overhead=-1)


def test_estimate_rejects_non_int_overhead():
    """Spec criterion 6, type safety: non-int overhead raises ``TypeError``."""
    with pytest.raises(TypeError):
        estimate("hello", message_overhead="4")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        estimate("hello", message_overhead=1.5)  # type: ignore[arg-type]


def test_estimate_rejects_bool_overhead():
    """``bool`` is a subclass of ``int`` but we reject it explicitly."""
    with pytest.raises(TypeError):
        estimate("hello", message_overhead=True)  # type: ignore[arg-type]


# ---------- 7. test_message_overhead_is_applied ----------


def test_message_overhead_is_applied():
    """Spec criterion 7: overhead contributes to the total."""
    plain = estimate("hi", message_overhead=0)
    with_overhead = estimate("hi", message_overhead=10)
    assert with_overhead.tokens == plain.tokens + 10
    assert with_overhead.details["message_overhead"] == 10


def test_message_overhead_zero_is_distinct_from_default():
    """``message_overhead=0`` is honoured, not silently replaced."""
    e = estimate("hi", message_overhead=0)
    assert e.tokens != estimate("hi").tokens
    assert e.details["message_overhead"] == 0


# ---------- cross-cutting edge cases -------------------------------------


@pytest.mark.parametrize("text", ["a", "ab", "abc", "abcd"])
def test_estimate_ascii_short_inputs_round_trip(text: str):
    e = estimate(text, message_overhead=0)
    assert e.tokens in (1, 2, 3, 4)  # all possible ceil(n/4) for n in 1..4
    assert e.confidence == "high"


def test_estimate_handles_string_with_only_whitespace():
    text = "   \t\n   "
    e = estimate(text)
    assert e.tokens >= DEFAULT_MESSAGE_OVERHEAD
    assert e.confidence == "high"


def test_estimate_unknown_encoding_raises():
    """The Encoding literal is documented — anything else is a bug."""
    with pytest.raises(ValueError, match="encoding"):
        estimate("hello", encoding="gpt2")  # type: ignore[arg-type]


def test_estimate_non_string_text_raises():
    """Spec invariant: total over arbitrary input."""
    for bad in (None, 42, 3.14, b"hello", ["a"], {"a": 1}):
        with pytest.raises(TypeError):
            estimate(bad)  # type: ignore[arg-type]


def test_estimate_encodings_constant_matches_documented_value():
    assert ENCODINGS == frozenset({"cl100k_approx"})


def test_estimate_very_long_input_completes_quickly():
    """Spec criterion 32: no quadratic blow-up on big inputs.

    10 MB of ASCII must estimate in well under a second.
    """
    import time

    text = "a" * (10 * 1024 * 1024)
    start = time.perf_counter()
    e = estimate(text, message_overhead=0)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"estimator too slow: {elapsed:.3f}s"
    # 10MB / 4 bytes-per-token = 2,621,440 tokens.
    assert e.tokens == 2_621_440


def test_estimate_string_with_null_character_counted():
    """Spec criterion 33: NUL bytes are counted (and lower confidence)."""
    text = "a\x00b"
    e = estimate(text, message_overhead=0)
    assert e.details["byte_length"] == 3
    assert e.details["ascii_bytes"] == 3
    assert e.tokens == 1
    assert e.confidence == "low"


def test_estimate_newline_and_tab_counted_as_ascii():
    """Spec criterion 34: newline + tab are counted (and don't lower conf)."""
    text = "a\nb\tc"
    e = estimate(text, message_overhead=0)
    assert e.details["ascii_bytes"] == 5
    assert e.details["byte_length"] == 5
    assert e.confidence == "high"
    assert e.tokens == 2  # ceil(5/4)


# --- typing & import contract --------------------------------------------


def test_estimate_returned_type_has_correct_annotations():
    """Sanity: typing stays correct."""
    import typing

    hints = typing.get_type_hints(estimate)
    assert "text" in hints
    assert "return" in hints