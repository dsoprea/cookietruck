"""CLI: Qt WebEngine cookie capture (GUI authenticate-then-export flow)."""

# Standard library

import argparse
import json
import logging
import sys
import typing

# Qt (PySide6)

import PySide6.QtCore
import PySide6.QtNetwork
import PySide6.QtWebEngineCore
import PySide6.QtWebEngineWidgets
import PySide6.QtWidgets

# Package

import cookiebaker.utility

_LOGGER = logging.getLogger(__name__)

# Run inside the loaded document: focus first usable text entry; return whether focus moved.

_FOCUS_FIRST_TEXT_INPUT_JS = (
    "(function(){"
    "function visible(el){if(!el||el.disabled)return false;var st=window.getComputedStyle(el);"
    "if(st.display==='none'||st.visibility==='hidden')return false;var r=el.getBoundingClientRect();"
    "return r.width>0&&r.height>0;}"
    "var sel="
    "'input[type=\"text\"],input[type=\"email\"],input[type=\"password\"],input[type=\"search\"],"
    "input[type=\"tel\"],input[type=\"url\"],input[type=\"number\"],input:not([type]),textarea,"
    "[contenteditable=\"true\"]';"
    "var nodes=document.querySelectorAll(sel);"
    "for(var i=0;i<nodes.length;i++){var el=nodes[i];"
    "if(el.readOnly||!visible(el))continue;"
    "try{el.focus();return true;}catch(e){}}"
    "return false;})();"
)


def _configure_logging(verbose: bool) -> None:
    """Attach stderr logging: WARNING by default, DEBUG when ``verbose`` is True."""

    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )


def _http_url_argument(value: str) -> str:
    """``argparse`` ``type=`` hook: accept only normalized http(s) URLs."""

    qurl = cookiebaker.utility.normalize_url(value)

    if not qurl.isValid() or qurl.scheme() not in ("http", "https"):
        raise argparse.ArgumentTypeError(f"not a valid http(s) URL: {value!r}")

    return qurl.toString()


def main() -> int:
    """Parse CLI flags, run Qt WebEngine, print JSON session payload; return process exit code."""

    # Argument definitions

    p = argparse.ArgumentParser(
        prog="cb_authenticate",
        description="Load a URL in Qt WebEngine and print captured cookies as JSON.",
    )
    p.add_argument(
        "url",
        type=_http_url_argument,
        help="http(s) URL to open",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging on stderr.",
    )
    p.add_argument(
        "--settle-ms",
        type=int,
        default=800,
        metavar="MS",
        help="Milliseconds to wait after loadAllCookies (default: 800).",
    )
    p.add_argument(
        "--profile",
        default=cookiebaker.utility.PROFILE_STORAGE_NAME,
        metavar="NAME",
        help=(
            "QWebEngineProfile storage name "
            f"(default: {cookiebaker.utility.PROFILE_STORAGE_NAME!r})."
        ),
    )

    # Parse and configure logging before any Qt noise

    args = p.parse_args()
    _configure_logging(args.verbose)

    base_url = args.url
    qurl = PySide6.QtCore.QUrl(base_url)
    _LOGGER.debug("normalized URL: %s", base_url)

    # Qt application + shared GL context (WebEngine requirement)

    PySide6.QtWidgets.QApplication.setAttribute(
        PySide6.QtCore.Qt.ApplicationAttribute.AA_ShareOpenGLContexts
    )
    app = PySide6.QtWidgets.QApplication([sys.argv[0]])

    # Profile: named storage + no HTTP cache (typical for cookie-only capture).

    cookie_map: typing.Dict[
        typing.Tuple[bytes, bytes, bytes],
        PySide6.QtNetwork.QNetworkCookie,
    ] = {}
    profile = PySide6.QtWebEngineCore.QWebEngineProfile(args.profile)
    profile.setHttpCacheType(PySide6.QtWebEngineCore.QWebEngineProfile.HttpCacheType.NoCache)

    def on_cookie_added(c: PySide6.QtNetwork.QNetworkCookie) -> None:
        """Merge each emitted cookie into ``cookie_map`` (latest wins per key)."""

        key = cookiebaker.utility.cookie_key(c)
        cookie_map[key] = PySide6.QtNetwork.QNetworkCookie(c)
        _LOGGER.debug("cookie added: name=%r domain=%r path=%r", key[0], key[1], key[2])

    profile.cookieStore().cookieAdded.connect(on_cookie_added)

    # Browser chrome

    view = PySide6.QtWebEngineWidgets.QWebEngineView()
    page = PySide6.QtWebEngineCore.QWebEnginePage(profile, view)
    view.setPage(page)

    # Mutable closure state: ensure ``dump_and_quit`` runs at most once.

    done = {"printed": False}

    # Embedded browser plus bottom button (explicit capture, then exit).

    _LOGGER.debug("main UI: 1100x720, capture button")

    container = PySide6.QtWidgets.QWidget()
    container.resize(1100, 720)
    container.setWindowTitle("cookiebaker")

    layout = PySide6.QtWidgets.QVBoxLayout(container)
    layout.addWidget(view, stretch=1)

    capture_btn = PySide6.QtWidgets.QPushButton("Done")
    capture_btn.setDefault(True)

    btn_row = PySide6.QtWidgets.QHBoxLayout()
    btn_row.setContentsMargins(0, 20, 0, 20)

    btn_row.addStretch(1)
    btn_row.addWidget(capture_btn)
    btn_row.addStretch(1)
    layout.addLayout(btn_row)

    def dump_and_quit() -> None:
        """Collect cookies, print JSON to stdout, close the UI, stop the Qt event loop."""

        if done["printed"]:
            return
        done["printed"] = True
        cookies = cookiebaker.utility.settle_then_collect(profile, cookie_map, args.settle_ms)
        payload = cookiebaker.utility.build_payload(base_url, cookies)
        _LOGGER.debug("emitting JSON payload with %d cookie records", len(payload["cookies"]))
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        container.close()
        app.quit()

    def on_capture_clicked() -> None:
        """Disable the button then run the shared capture-and-exit path."""

        capture_btn.setEnabled(False)
        dump_and_quit()

    capture_btn.clicked.connect(on_capture_clicked)

    # Prefer keyboard focus on the page's first text control; otherwise the Done button.

    focus_state = {"done": False, "pending": False}

    def apply_initial_focus(ok: bool) -> None:
        """Run focus JS only after a real navigation finishes (not ``about:blank`` placeholders)."""

        if focus_state["done"]:
            return

        # Failed loads leave the previous document; wait for a successful completion.

        if not ok:
            return

        loaded = page.url()

        # Initial WebEngine placeholder frames fire ``loadFinished`` before the requested URL.

        if loaded.scheme() == "about":
            path_lower = loaded.path().lower()

            if path_lower in ("blank", "srcdoc"):
                return

        if focus_state["pending"]:
            return

        focus_state["pending"] = True

        def after_js(result: object) -> None:
            if focus_state["done"]:
                return

            focus_state["done"] = True

            focused = bool(result)

            if focused:
                _LOGGER.debug("initial focus: web text control")

                return

            _LOGGER.debug("initial focus: Done button (no web text control)")

            capture_btn.setFocus(PySide6.QtCore.Qt.FocusReason.ActiveWindowReason)

        def run_focus_script() -> None:
            """Defer to the next event-loop tick so the loaded document is ready for script."""

            page.runJavaScript(_FOCUS_FIRST_TEXT_INPUT_JS, after_js)

        PySide6.QtCore.QTimer.singleShot(0, run_focus_script)

    page.loadFinished.connect(apply_initial_focus)

    container.show()
    view.setUrl(qurl)

    # Run until ``dump_and_quit`` calls ``app.quit()``

    code = app.exec()
    return int(code) if code is not None else 0
