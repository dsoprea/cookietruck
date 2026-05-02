"""Cookie normalization, capture helpers, and session JSON payload (non-CLI)."""

# Standard library

import datetime
import logging
import typing

# Qt (PySide6)

import PySide6.QtCore
import PySide6.QtNetwork
import PySide6.QtWebEngineCore

_LOGGER = logging.getLogger(__name__)

# Persistent QWebEngineProfile storage id (on-disk cookie jar namespace).

PROFILE_STORAGE_NAME = "cookietruck"


def as_bytes(x: object) -> bytes:
    """Coerce ``x`` to ``bytes``: UTF-8 for ``str``, otherwise ``bytes(...)``."""

    if isinstance(x, str):
        return x.encode("utf-8", errors="replace")
    return bytes(x)


def normalize_url(text: str) -> PySide6.QtCore.QUrl:
    """Turn user input into an absolute ``QUrl``, defaulting scheme to ``https``."""

    text = text.strip()

    # Empty input yields an invalid URL so callers can reject early.

    if not text:
        return PySide6.QtCore.QUrl()

    # Bare hostnames become navigable URLs once a scheme is assumed.

    if "://" not in text:
        text = "https://" + text
    return PySide6.QtCore.QUrl.fromUserInput(text)


def cookie_key(c: PySide6.QtNetwork.QNetworkCookie) -> typing.Tuple[bytes, bytes, bytes]:
    """Stable dict key for deduplicating cookies: ``(name, domain, path)`` as bytes."""

    domain = c.domain()
    path = c.path() or "/"
    return (as_bytes(c.name()), as_bytes(domain), as_bytes(path))


def same_site_name(c: PySide6.QtNetwork.QNetworkCookie) -> str | None:
    """Map Qt same-site policy to JSON string values; ``None`` omits the field."""

    policy = c.sameSitePolicy()
    if policy == PySide6.QtNetwork.QNetworkCookie.SameSite.Default:
        return None
    if policy == PySide6.QtNetwork.QNetworkCookie.SameSite.None_:
        return "None"
    if policy == PySide6.QtNetwork.QNetworkCookie.SameSite.Lax:
        return "Lax"
    if policy == PySide6.QtNetwork.QNetworkCookie.SameSite.Strict:
        return "Strict"

    # Fallback for unexpected enum values—keeps export robust.

    return str(int(policy))


def cookies_as_records(cookies: typing.Iterable[PySide6.QtNetwork.QNetworkCookie]) -> typing.List[dict]:
    """Serialize cookies to sorted JSON-friendly dict rows (name, domain, flags, etc.)."""

    rows: typing.List[dict] = []
    for c in cookies:
        exp = c.expirationDate()

        # Core attributes always emitted for HTTP tooling / export consumers.

        row = {
            "name": as_bytes(c.name()).decode("utf-8", errors="replace"),
            "value": as_bytes(c.value()).decode("utf-8", errors="replace"),
            "domain": (c.domain() or "").strip(),
            "path": c.path() or "/",
            "secure": bool(c.isSecure()),
            "httpOnly": bool(c.isHttpOnly()),
        }
        ss = same_site_name(c)
        if ss is not None:
            row["sameSite"] = ss
        if exp.isValid():
            row["expires"] = exp.toString(PySide6.QtCore.Qt.DateFormat.ISODateWithMs)
        rows.append(row)

    # Deterministic ordering helps diffing and human inspection.

    rows.sort(key=lambda r: (r["domain"], r["path"], r["name"]))
    return rows


def _domain_matches(host: str, cookie_domain: str) -> bool:
    """Return True if ``host`` is covered by ``cookie_domain`` (with leading-dot rule)."""

    host = host.lower()
    cd = cookie_domain.lstrip(".").lower()
    return host == cd or host.endswith("." + cd)


def _path_matches(request_path: str, cookie_path: str) -> bool:
    """RFC-style path matching: prefix match with boundary at ``/``."""

    if not request_path.startswith("/"):
        request_path = "/" + request_path
    cp = cookie_path or "/"

    # Root-path cookies apply everywhere on the host.

    if cp == "/":
        return True
    if not request_path.startswith(cp):
        return False
    if len(request_path) == len(cp):
        return True

    # Require ``/`` after the cookie path prefix so ``/foo`` does not match ``/food``.

    return request_path[len(cp)] == "/"


def cookie_header_for_url(
    cookies: typing.Iterable[PySide6.QtNetwork.QNetworkCookie],
    url: PySide6.QtCore.QUrl,
) -> str:
    """Build a ``Cookie`` header value for ``url`` from in-memory cookies (browser-style filter)."""

    host = url.host()

    # Path-only matching: query is not part of the cookie ``Path`` attribute (RFC 6265).

    path = url.path() or "/"
    parts: typing.List[str] = []
    for c in cookies:
        dom = (c.domain() or "").strip()

        # Skip cookies that do not apply to this host/path.

        if not dom or not _domain_matches(host, dom):
            continue
        if not _path_matches(path, c.path() or "/"):
            continue

        # Secure cookies must not be sent on plain HTTP.

        if c.isSecure() and url.scheme().lower() != "https":
            continue
        name = as_bytes(c.name()).decode("utf-8", errors="replace")
        value = as_bytes(c.value()).decode("utf-8", errors="replace")
        parts.append(f"{name}={value}")
    return "; ".join(parts)


def settle_then_collect(
    profile: PySide6.QtWebEngineCore.QWebEngineProfile,
    cookie_map: typing.Dict[typing.Tuple[bytes, bytes, bytes], PySide6.QtNetwork.QNetworkCookie],
    settle_ms: int,
) -> typing.List[PySide6.QtNetwork.QNetworkCookie]:
    """Flush persistence via ``loadAllCookies``, wait ``settle_ms``, return live cookie list."""

    store = profile.cookieStore()
    _LOGGER.debug("cookie store loadAllCookies + settle %d ms", settle_ms)

    # Pull disk-backed cookies into the store; completion is asynchronous.

    store.loadAllCookies()

    # Block the GUI thread briefly so async cookie ops can finish.

    loop = PySide6.QtCore.QEventLoop()
    PySide6.QtCore.QTimer.singleShot(settle_ms, loop.quit)
    loop.exec()
    cookies = list(cookie_map.values())
    _LOGGER.debug("collected %d QNetworkCookie instances", len(cookies))
    return cookies


def build_payload(base_url: str, cookies: typing.List[PySide6.QtNetwork.QNetworkCookie]) -> dict:
    """Assemble the session JSON object (schema: base_url, cookie_header, cookies, …)."""

    qurl = PySide6.QtCore.QUrl(base_url)
    return {
        "schema_version": 1,
        "base_url": base_url,
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "cookie_header": cookie_header_for_url(cookies, qurl),
        "cookies": cookies_as_records(cookies),
    }
