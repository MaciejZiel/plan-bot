from __future__ import annotations

import json
import logging

import pytest

from plan_bot.logging_setup import JsonFormatter, RedactSecrets, TextFormatter, configure_logging

TOKEN = "123456789:AAH-secret_token_value_0123456789"


def record(msg: str = "hello", **extra: object) -> logging.LogRecord:
    rec = logging.LogRecord("plan_bot.x", logging.INFO, __file__, 1, msg, None, None)
    rec.__dict__.update(extra)
    return rec


def test_json_lines_include_extra_fields() -> None:
    line = JsonFormatter().format(record("command", command="next", platform="telegram"))
    data = json.loads(line)
    assert data["msg"] == "command"
    assert data["level"] == "INFO"
    assert data["command"] == "next"
    assert data["ts"].endswith("+00:00")


def test_json_includes_exceptions() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())
    assert "ValueError: boom" in json.loads(JsonFormatter().format(rec))["exc"]


def test_text_format_appends_extras() -> None:
    assert TextFormatter().format(record("x", job="refresh")).endswith("x job=refresh")


def test_tokens_are_redacted() -> None:
    rec = record(f"GET https://api.telegram.org/bot{TOKEN}/getMe failed")
    assert RedactSecrets().filter(rec)
    assert TOKEN not in rec.getMessage()
    assert "<redacted-token>" in rec.getMessage()


def test_configure_logging_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", "json")
    logging.getLogger("plan_bot.test").info("started", extra={"adapters": "telegram"})
    err = capsys.readouterr().err
    assert json.loads(err.strip().splitlines()[-1])["adapters"] == "telegram"
    configure_logging("WARNING", "text")
    assert logging.getLogger().level == logging.WARNING


@pytest.mark.parametrize("formatter", [JsonFormatter(), TextFormatter()])
def test_tokens_are_redacted_in_tracebacks_and_extras(formatter: logging.Formatter) -> None:
    import sys

    try:
        raise RuntimeError(f"POST https://api.telegram.org/bot{TOKEN}/sendMessage")
    except RuntimeError:
        rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())
    rec.__dict__["url"] = f"https://api.telegram.org/bot{TOKEN}/getMe"
    line = formatter.format(rec)
    assert "RuntimeError" in line
    assert TOKEN not in line
    assert "<redacted-token>" in line
