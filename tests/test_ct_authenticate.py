# Standard library

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
