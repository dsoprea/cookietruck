# Standard library

import io
import sys

import pytest

import cookietruck.entrypoint.ct_to_curl


def test_ct_to_curl_stdin(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["ct_to_curl"])
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"cookie_header": "a=b; c=d"}'))
    assert cookietruck.entrypoint.ct_to_curl.main() == 0
    assert "-b" in capsys.readouterr().out


def test_ct_to_curl_stdin_single_cookie(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["ct_to_curl"])
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"cookie_header": "session=abc"}'))
    assert cookietruck.entrypoint.ct_to_curl.main() == 0
    out = capsys.readouterr().out
    assert "session=abc" in out


def test_ct_to_curl_invalid_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["ct_to_curl"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert cookietruck.entrypoint.ct_to_curl.main() == 1
    assert "error" in capsys.readouterr().err.lower()


def test_ct_to_curl_invalid_json_explicit(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["ct_to_curl"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert cookietruck.entrypoint.ct_to_curl.main() == 1
    assert "error" in capsys.readouterr().err.lower()


def test_ct_to_curl_not_object(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["ct_to_curl"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("[1, 2]"))
    assert cookietruck.entrypoint.ct_to_curl.main() == 1
    assert "object" in capsys.readouterr().err.lower()


def test_ct_to_curl_missing_cookie_header(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["ct_to_curl"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    assert cookietruck.entrypoint.ct_to_curl.main() == 1
    assert "cookie_header" in capsys.readouterr().err.lower()


def test_ct_to_curl_cookie_header_wrong_type(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["ct_to_curl"])
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"cookie_header": 42}'))
    assert cookietruck.entrypoint.ct_to_curl.main() == 1
    assert "string" in capsys.readouterr().err.lower()
