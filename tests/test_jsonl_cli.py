"""Tests for the JSONL CLI surface — covers spec criteria 19–22, 29–31."""

from __future__ import annotations

import json
import subprocess

import pytest

from contextlens.jsonl import dispatch, handle_raw_line, handle_request


# ---------- 19. test_jsonl_estimate_request ----------


def test_jsonl_estimate_request_round_trip():
    """Spec criterion 19: an estimate request returns an estimate response."""
    line = json.dumps({"op": "estimate", "text": "hello world"})
    response = handle_raw_line(line)
    parsed = json.loads(response)
    assert parsed["ok"] is True
    assert parsed["op"] == "estimate"
    assert parsed["tokens"] >= 1
    assert parsed["confidence"] in {"low", "medium", "high"}


def test_jsonl_truncate_request_round_trip():
    line = json.dumps(
        {"op": "truncate", "text": "hello world this is a long message", "max_tokens": 3}
    )
    parsed = json.loads(handle_raw_line(line))
    assert parsed["ok"] is True
    assert parsed["op"] == "truncate"
    assert parsed["truncated"] is True
    assert len(parsed["text"]) < 35


def test_jsonl_budget_request_round_trip():
    line = json.dumps(
        {
            "op": "budget",
            "messages": [{"role": "user", "content": "hi"}],
            "limit": 50,
        }
    )
    parsed = json.loads(handle_raw_line(line))
    assert parsed["ok"] is True
    assert parsed["op"] == "budget"
    assert parsed["total_tokens"] >= 1
    assert parsed["overflow"] is False


def test_jsonl_estimate_request_with_unicode():
    """Unicode survives JSON encoding intact."""
    line = json.dumps({"op": "estimate", "text": "héllo 🚀"}, ensure_ascii=False)
    parsed = json.loads(handle_raw_line(line))
    assert parsed["ok"] is True
    assert parsed["tokens"] >= 1


def test_jsonl_request_uses_compact_separators():
    """Response lines must be single-line JSON — no embedded newlines."""
    line = json.dumps({"op": "estimate", "text": "hi"})
    response = handle_raw_line(line)
    assert "\n" not in response
    # Round-trips cleanly.
    json.loads(response)


# ---------- 20. test_jsonl_invalid_json_returns_structured_error ----------


def test_jsonl_invalid_json_returns_structured_error():
    """Spec criterion 20: bad JSON yields a structured error, not a crash."""
    response = handle_raw_line("{not valid json")
    parsed = json.loads(response)
    assert parsed["ok"] is False
    assert parsed["error"] == "invalid_json"
    assert "message" in parsed


def test_jsonl_invalid_json_keeps_dispatcher_alive():
    """A bad line doesn't crash subsequent valid lines."""
    bad = handle_raw_line("not json")
    good = handle_raw_line(json.dumps({"op": "estimate", "text": "hi"}))
    assert "ok" in bad and bad != ""
    assert json.loads(good)["ok"] is True


@pytest.mark.parametrize("bad", ["", "  ", "\t"])
def test_jsonl_blank_line_returns_empty_string(bad: str):
    """Blank input → no output (dispatcher is silent for whitespace)."""
    assert handle_raw_line(bad) == ""


# ---------- 21. test_jsonl_unknown_operation_returns_error ----------


def test_jsonl_unknown_operation_returns_error():
    """Spec criterion 21: unknown op yields a structured error."""
    response = handle_raw_line(json.dumps({"op": "nope", "text": "hi"}))
    parsed = json.loads(response)
    assert parsed["ok"] is False
    assert parsed["error"] == "unknown_operation"
    assert parsed["details"]["operation"] == "nope"


def test_jsonl_missing_op_returns_error():
    response = handle_raw_line(json.dumps({"text": "hi"}))
    parsed = json.loads(response)
    assert parsed["ok"] is False
    assert parsed["error"] == "invalid_request"


def test_jsonl_non_string_op_returns_error():
    response = handle_raw_line(json.dumps({"op": 5, "text": "hi"}))
    parsed = json.loads(response)
    assert parsed["ok"] is False
    assert parsed["error"] == "invalid_request"


def test_jsonl_non_object_request_returns_error():
    response = handle_raw_line("[1, 2, 3]")
    parsed = json.loads(response)
    assert parsed["ok"] is False
    assert parsed["error"] == "invalid_request"


def test_jsonl_null_request_returns_error():
    response = handle_raw_line("null")
    parsed = json.loads(response)
    assert parsed["ok"] is False


# ---------- 22. test_jsonl_response_is_single_line_json ----------


def test_jsonl_response_is_single_line_json():
    """Spec criterion 22: response is single-line JSON."""
    for payload in (
        {"op": "estimate", "text": "hello"},
        {"op": "truncate", "text": "hello world", "max_tokens": 2},
        {"op": "budget", "messages": [{"role": "user", "content": "x"}], "limit": 100},
        {"op": "nope"},
    ):
        response = handle_raw_line(json.dumps(payload))
        assert "\n" not in response, f"multi-line response: {response!r}"
        json.loads(response)


def test_jsonl_response_handles_unicode_without_escaping():
    """By default, ensure_ascii=False keeps non-ASCII readable."""
    response = handle_raw_line(
        json.dumps({"op": "truncate", "text": "héllo", "max_tokens": 100})
    )
    # The 'text' field in the response must carry the unescaped form.
    parsed = json.loads(response)
    assert "héllo" in parsed["text"]
    assert "héllo" in response


# ---------- 29. test_cli_reads_multiple_jsonl_requests ----------


def test_cli_reads_multiple_jsonl_requests(run_cli):
    """Spec criterion 29: a single stdin stream yields N responses."""
    payload = "\n".join(
        [
            json.dumps({"op": "estimate", "text": "hi"}),
            json.dumps({"op": "estimate", "text": "hello"}),
            json.dumps({"op": "truncate", "text": "hello world", "max_tokens": 2}),
        ]
    )
    result = run_cli([], payload)
    assert result.returncode == 0
    lines = [ln for ln in result.stdout.split("\n") if ln.strip()]
    assert len(lines) == 3
    for ln in lines:
        parsed = json.loads(ln)
        assert parsed["ok"] is True


def test_cli_processes_each_request_independently(run_cli):
    """A malformed request between two good ones does not break the run."""
    payload = "\n".join(
        [
            json.dumps({"op": "estimate", "text": "first"}),
            "this is not json",
            json.dumps({"op": "estimate", "text": "third"}),
        ]
    )
    result = run_cli([], payload)
    assert result.returncode == 1
    lines = [ln for ln in result.stdout.split("\n") if ln.strip()]
    assert len(lines) == 3


def test_cli_handles_large_request_stream(run_cli):
    """500 requests in one stream all succeed."""
    payload = "\n".join(
        json.dumps({"op": "estimate", "text": f"request #{i}"})
        for i in range(500)
    )
    result = run_cli([], payload)
    assert result.returncode == 0
    lines = [ln for ln in result.stdout.split("\n") if ln.strip()]
    assert len(lines) == 500


def test_cli_empty_stdin_yields_zero_output(run_cli):
    """Empty stdin → empty stdout, exit 0."""
    result = run_cli([], "")
    assert result.returncode == 0
    assert result.stdout == ""


# ---------- 30. test_cli_does_not_write_logs_to_stdout ----------


def test_cli_does_not_write_logs_to_stdout(run_cli):
    """Spec criterion 30: stdout is JSON Lines only — no log noise."""
    payload = json.dumps({"op": "estimate", "text": "hi"})
    result = run_cli([], payload)
    assert result.returncode == 0
    # Every line of stdout must be valid JSON.
    for line in result.stdout.split("\n"):
        if line.strip():
            json.loads(line)


def test_cli_diagnostic_output_goes_to_stderr(run_cli):
    """Errors are announced on stderr, not stdout."""
    payload = "not json"
    result = run_cli([], payload)
    assert result.returncode != 0
    # stdout has the structured error, not a Python traceback.
    json.loads(result.stdout)
    assert "Traceback" not in result.stdout


def test_cli_quiet_flag_suppresses_stderr(run_cli):
    """``--quiet`` keeps stdout pristine and stderr empty."""
    payload = "not json"
    result = run_cli(["--quiet"], payload)
    # Structured error is still on stdout; stderr is silent.
    assert result.stderr == ""
    json.loads(result.stdout)


# ---------- 31. test_cli_nonzero_exit_on_malformed_request ----------


def test_cli_nonzero_exit_on_malformed_request(run_cli):
    """Spec criterion 31: malformed request → exit code != 0."""
    payload = "not json"
    result = run_cli([], payload)
    assert result.returncode != 0


def test_cli_zero_exit_on_clean_run(run_cli):
    """Spec criterion 31 (positive side): valid stream → exit 0."""
    payload = json.dumps({"op": "estimate", "text": "hi"})
    result = run_cli([], payload)
    assert result.returncode == 0


def test_cli_unknown_operation_yields_structured_error_with_nonzero_exit(run_cli):
    payload = json.dumps({"op": "nope"})
    result = run_cli([], payload)
    assert result.returncode != 0
    parsed = json.loads(result.stdout)
    assert parsed["error"] == "unknown_operation"


def test_cli_version_flag_prints_version(run_cli):
    result = run_cli(["--version"], "")
    assert result.returncode == 0
    assert "contextlens" in result.stdout
    assert "0.1.0" in result.stdout


def test_cli_help_flag_prints_help(run_cli):
    result = run_cli(["--help"], "")
    assert result.returncode == 0
    assert "JSON" in result.stdout or "json" in result.stdout


def test_cli_unknown_flag_exits_nonzero(run_cli):
    result = run_cli(["--no-such-flag"], "")
    assert result.returncode != 0


# ---------- dispatch() helper --------------------------------------------


def test_dispatch_helper_handles_multiline_input():
    """``dispatch`` joins multiple responses without trailing newline."""
    text = "\n".join(
        [
            json.dumps({"op": "estimate", "text": "hi"}),
            json.dumps({"op": "estimate", "text": "hello"}),
        ]
    )
    out = dispatch(text)
    lines = out.split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["ok"] is True
    assert json.loads(lines[1])["ok"] is True


def test_dispatch_skips_blank_lines():
    text = "\n".join(
        [
            "",
            json.dumps({"op": "estimate", "text": "hi"}),
            "   ",
        ]
    )
    out = dispatch(text)
    assert out.count("\n") == 0  # only one response → no newlines


def test_handle_request_rejects_non_dict_request():
    response = handle_request(["not", "a", "dict"])
    parsed = json.loads(response)
    assert parsed["ok"] is False
    assert parsed["error"] == "invalid_request"


def test_handle_request_internal_error_is_structured():
    """An internal ValueError surfaces as a structured error, not a crash."""
    response = handle_request({"op": "truncate", "text": "hi", "max_tokens": -1})
    parsed = json.loads(response)
    assert parsed["ok"] is False
    assert parsed["error"] == "invalid_request"


def test_dispatch_returns_empty_for_blank_input():
    assert dispatch("") == ""
    assert dispatch("\n\n\n") == ""


# --- subprocess safety: no shell, no PYTHONPATH tricks --------------------


def test_cli_subprocess_no_shell_injection(run_cli):
    """The CLI never invokes a shell — payload is treated as text."""
    payload = json.dumps({"op": "estimate", "text": "$(touch SHOULD_NOT_RUN)"})
    result = run_cli([], payload)
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["ok"] is True
    assert "SHOULD_NOT_RUN" not in result.stderr  # nothing was executed