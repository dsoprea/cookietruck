# Standard library

import io
import json
import sys

# Third-party / package

import pytest

import cookietruck.entrypoint.ct_authenticate


def test_ct_authenticate_rejects_bad_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ct_authenticate", "ftp://example.com"])
    with pytest.raises(SystemExit) as exc:
        cookietruck.entrypoint.ct_authenticate.main()
    assert exc.value.code == 2


def test_ct_authenticate_rejects_empty_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ct_authenticate", ""])
    with pytest.raises(SystemExit) as exc:
        cookietruck.entrypoint.ct_authenticate.main()
    assert exc.value.code == 2


def test_ct_authenticate_rejects_whitespace_only_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ct_authenticate", "   "])
    with pytest.raises(SystemExit) as exc:
        cookietruck.entrypoint.ct_authenticate.main()
    assert exc.value.code == 2


def test_ct_authenticate_accepts_https_url_argv_before_qt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ct_authenticate", "https://example.com"])

    class Boom(Exception):
        pass

    class FakeApp:
        """Stub without constructing a real GUI application."""

        @classmethod
        def setAttribute(cls, *_a: object, **_k: object) -> None:
            return None

        def __init__(self, argv: list[str]) -> None:
            raise Boom(argv)

    monkeypatch.setattr(
        cookietruck.entrypoint.ct_authenticate.PySide6.QtWidgets,
        "QApplication",
        FakeApp,
    )

    with pytest.raises(Boom) as excinfo:
        cookietruck.entrypoint.ct_authenticate.main()

    assert excinfo.value.args[0]


def test_ct_authenticate_as_curl_cookiejar_flag_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["ct_authenticate", "--as-curl-cookiejar", "https://example.com"],
    )

    class Boom(Exception):
        pass

    class FakeApp:
        """Stub without constructing a real GUI application."""

        @classmethod
        def setAttribute(cls, *_a: object, **_k: object) -> None:
            return None

        def __init__(self, argv: list[str]) -> None:
            raise Boom(argv)

    monkeypatch.setattr(
        cookietruck.entrypoint.ct_authenticate.PySide6.QtWidgets,
        "QApplication",
        FakeApp,
    )

    with pytest.raises(Boom) as excinfo:
        cookietruck.entrypoint.ct_authenticate.main()

    assert excinfo.value.args[0]


def test_write_cookiejar_stdout_rejects_binary_on_tty(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cookietruck.entrypoint.ct_authenticate.sys.stdout,
        "isatty",
        lambda: True,
    )
    payload = b"# Netscape HTTP Cookie File\n\xff\n"

    code = cookietruck.entrypoint.ct_authenticate._write_cookiejar_stdout(payload)

    captured = capsys.readouterr()
    assert code == 1
    assert "binary cookie data" in captured.err
    assert captured.out == ""


def test_write_cookiejar_stdout_writes_when_not_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = io.BytesIO()
    payload = b"# Netscape HTTP Cookie File\n\xff\n"

    class FakeStdout:
        """Capture binary writes without touching the real stdout fd."""

        def __init__(self, output: io.BytesIO) -> None:
            self.buffer = output

        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(
        cookietruck.entrypoint.ct_authenticate.sys,
        "stdout",
        FakeStdout(captured),
    )

    code = cookietruck.entrypoint.ct_authenticate._write_cookiejar_stdout(payload)

    assert code == 0
    assert captured.getvalue() == payload


def test_ct_authenticate_rejects_missing_json_seed_file(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["ct_authenticate", "--json-cookies-filepath", "/no/such/session.json", "https://example.com"],
    )

    code = cookietruck.entrypoint.ct_authenticate.main()

    captured = capsys.readouterr()
    assert code == 1
    assert "error:" in captured.err


def test_ct_authenticate_rejects_missing_curl_seed_file(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["ct_authenticate", "--curl-cookies-filepath", "/no/such/cookies.txt", "https://example.com"],
    )

    code = cookietruck.entrypoint.ct_authenticate.main()

    captured = capsys.readouterr()
    assert code == 1
    assert "error:" in captured.err


def test_ct_authenticate_rejects_both_seed_filepaths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ct_authenticate",
            "--json-cookies-filepath",
            "session.json",
            "--curl-cookies-filepath",
            "cookies.txt",
            "https://example.com",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        cookietruck.entrypoint.ct_authenticate.main()

    assert exc.value.code == 2


def test_ct_authenticate_accepts_curl_seed_flag_argv_before_qt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pytest.TempPathFactory,
) -> None:
    cookiejar_path = str(tmp_path) + "/cookies.txt"
    cookiejar_text = \
        "# Netscape HTTP Cookie File\n" \
        "example.com\tFALSE\t/\tFALSE\t0\tsession\tabc\n"
    with open(cookiejar_path, "w", encoding="utf-8") as handle:
        handle.write(cookiejar_text)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ct_authenticate",
            "--curl-cookies-filepath",
            cookiejar_path,
            "https://example.com",
        ],
    )

    class Boom(Exception):
        pass

    class FakeApp:
        """Stub without constructing a real GUI application."""

        @classmethod
        def setAttribute(cls, *_a: object, **_k: object) -> None:
            return None

        def __init__(self, argv: list[str]) -> None:
            raise Boom(argv)

    monkeypatch.setattr(
        cookietruck.entrypoint.ct_authenticate.PySide6.QtWidgets,
        "QApplication",
        FakeApp,
    )

    with pytest.raises(Boom) as excinfo:
        cookietruck.entrypoint.ct_authenticate.main()

    assert excinfo.value.args[0]
