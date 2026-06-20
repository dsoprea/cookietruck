# Standard library

import datetime
import io

# Third-party / package

import pytest

import PySide6.QtCore
import PySide6.QtNetwork

import cookietruck.utility


def cookie(
    name: bytes,
    value: bytes,
    domain: str,
    path: str = "/",
    secure: bool = False,
    http_only: bool = False,
    same_site: PySide6.QtNetwork.QNetworkCookie.SameSite | None = None,
) -> PySide6.QtNetwork.QNetworkCookie:
    """Build a QNetworkCookie for tests."""

    c = PySide6.QtNetwork.QNetworkCookie()
    c.setName(name)
    c.setValue(value)
    c.setDomain(domain)
    c.setPath(path)
    c.setSecure(secure)
    c.setHttpOnly(http_only)
    if same_site is not None:
        c.setSameSitePolicy(same_site)
    return c


def test_as_bytes_str() -> None:
    assert cookietruck.utility.as_bytes("a") == b"a"
    assert cookietruck.utility.as_bytes("é") == "é".encode("utf-8")


def test_as_bytes_bytes() -> None:
    assert cookietruck.utility.as_bytes(b"x") == b"x"


def test_normalize_url_empty() -> None:
    u = cookietruck.utility.normalize_url("   ")
    assert not u.isValid()


def test_normalize_url_bare_host() -> None:
    u = cookietruck.utility.normalize_url("example.com")
    assert u.isValid()
    assert u.scheme() == "https"
    assert u.host() == "example.com"


def test_normalize_url_explicit_scheme() -> None:
    u = cookietruck.utility.normalize_url("http://example.org/path")
    assert u.isValid()
    assert u.scheme() == "http"
    assert u.host() == "example.org"


def test_cookie_key() -> None:
    c = cookie(b"n", b"v", "d", "/p")
    assert cookietruck.utility.cookie_key(c) == (b"n", b"d", b"/p")


def test_same_site_name_default_is_omitted_in_records() -> None:
    c = cookie(b"a", b"b", "x.test", same_site=PySide6.QtNetwork.QNetworkCookie.SameSite.Default)
    rows = cookietruck.utility.cookies_as_records([c])
    assert "sameSite" not in rows[0]


def test_same_site_name_lax() -> None:
    c = cookie(b"a", b"b", "x.test", same_site=PySide6.QtNetwork.QNetworkCookie.SameSite.Lax)
    rows = cookietruck.utility.cookies_as_records([c])
    assert rows[0]["sameSite"] == "Lax"


def test_cookies_as_records_sorted() -> None:
    c1 = cookie(b"z", b"1", "b.example", "/")
    c2 = cookie(b"a", b"2", "a.example", "/")
    rows = cookietruck.utility.cookies_as_records([c1, c2])
    assert [r["name"] for r in rows] == ["a", "z"]


def test_domain_matches_via_header() -> None:
    url = PySide6.QtCore.QUrl("https://www.example.com/")
    c_ok = cookie(b"s", b"1", ".example.com")
    c_bad = cookie(b"t", b"2", "other.org")
    header = cookietruck.utility.cookie_header_for_url([c_ok, c_bad], url)
    assert header == "s=1"


def test_path_matches_via_header() -> None:
    url = PySide6.QtCore.QUrl("https://example.com/api/v1")
    c_api = cookie(b"a", b"1", "example.com", "/api")
    c_root = cookie(b"b", b"2", "example.com", "/")
    header = cookietruck.utility.cookie_header_for_url([c_api, c_root], url)
    assert "a=1" in header
    assert "b=2" in header


def test_secure_cookie_omitted_on_http() -> None:
    url = PySide6.QtCore.QUrl("http://example.com/")
    c_sec = cookie(b"s", b"x", "example.com", secure=True)
    header = cookietruck.utility.cookie_header_for_url([c_sec], url)
    assert header == ""


def test_secure_cookie_included_on_https() -> None:
    url = PySide6.QtCore.QUrl("https://example.com/")
    c_sec = cookie(b"s", b"x", "example.com", secure=True)
    header = cookietruck.utility.cookie_header_for_url([c_sec], url)
    assert header == "s=x"


def test_cookie_header_with_query_in_path_matching() -> None:
    url = PySide6.QtCore.QUrl("https://example.com/foo?q=1")
    c = cookie(b"k", b"v", "example.com", "/foo")
    header = cookietruck.utility.cookie_header_for_url([c], url)
    assert header == "k=v"


def test_build_payload_shape() -> None:
    c = cookie(b"n", b"v", "example.com")
    payload = cookietruck.utility.build_payload("https://example.com/", [c])
    assert payload["schema_version"] == 1
    assert payload["base_url"] == "https://example.com/"
    captured = payload["captured_at"]
    datetime.datetime.fromisoformat(captured.replace("Z", "+00:00"))
    assert payload["cookie_header"] == "n=v"
    assert len(payload["cookies"]) == 1
    assert payload["cookies"][0]["name"] == "n"


def test_private_domain_matches() -> None:
    assert cookietruck.utility._domain_matches("www.example.com", ".example.com") is True
    assert cookietruck.utility._domain_matches("evil.com", ".example.com") is False


def test_private_path_matches() -> None:
    assert cookietruck.utility._path_matches("/api/foo", "/api") is True
    assert cookietruck.utility._path_matches("/apifoo", "/api") is False


def test_utf8_roundtrip_in_records() -> None:
    c = cookie("né".encode("utf-8"), "β".encode("utf-8"), "example.com")
    rows = cookietruck.utility.cookies_as_records([c])
    assert rows[0]["name"] == "né"
    assert rows[0]["value"] == "β"


def test_build_curl_cookiejar_basic() -> None:
    c = cookie(b"session", b"abc123", ".example.com", "/api", secure=True)
    payload = cookietruck.utility.build_curl_cookiejar([c])
    text = payload.decode("utf-8")

    assert text.startswith("# Netscape HTTP Cookie File\n")
    assert "# https://curl.se/docs/http-cookies.html\n" in text
    assert "generated by cookietruck" in text

    lines = [line for line in text.splitlines() if "\t" in line]
    assert len(lines) == 1
    fields = lines[0].split("\t")
    assert fields == [".example.com", "TRUE", "/api", "TRUE", "0", "session", "abc123"]


def test_build_curl_cookiejar_http_only() -> None:
    c = cookie(b"n", b"v", "example.com", http_only=True)
    payload = cookietruck.utility.build_curl_cookiejar([c])
    text = payload.decode("utf-8")
    lines = [line for line in text.splitlines() if "\t" in line]
    fields = lines[0].split("\t")

    assert fields[0] == "#HttpOnly_example.com"
    assert fields[1] == "FALSE"


def test_build_curl_cookiejar_expiry() -> None:
    c = cookie(b"n", b"v", "example.com")
    expiration = PySide6.QtCore.QDateTime.fromSecsSinceEpoch(1_700_000_000, PySide6.QtCore.Qt.TimeSpec.UTC)
    c.setExpirationDate(expiration)
    payload = cookietruck.utility.build_curl_cookiejar([c])
    text = payload.decode("utf-8")
    lines = [line for line in text.splitlines() if "\t" in line]
    fields = lines[0].split("\t")

    assert fields[4] == "1700000000"


def test_is_binary_cookiejar_payload_utf8_ok() -> None:
    c = cookie(b"a", b"b", "example.com")
    payload = cookietruck.utility.build_curl_cookiejar([c])

    assert cookietruck.utility.is_binary_cookiejar_payload(payload) is False
    assert cookietruck.utility.are_cookies_binary_for_cookiejar([c]) is False


def test_is_binary_cookiejar_payload_non_utf8() -> None:
    c = cookie(b"a", b"\xff\xfe", "example.com")

    assert cookietruck.utility.are_cookies_binary_for_cookiejar([c]) is True


def test_is_binary_cookiejar_payload_tab_in_value() -> None:
    c = cookie(b"a", b"x\ty", "example.com")

    assert cookietruck.utility.are_cookies_binary_for_cookiejar([c]) is True

