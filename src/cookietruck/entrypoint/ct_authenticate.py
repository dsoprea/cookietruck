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

import cookietruck.utility

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

    qurl = cookietruck.utility.normalize_url(value)

    if not qurl.isValid() or qurl.scheme() not in ("http", "https"):
        raise argparse.ArgumentTypeError("not a valid http(s) URL: {value!r}".format(value=value))

    return qurl.toString()


def _write_cookiejar_stdout(payload: bytes) -> int:
    """Write cookiejar bytes to stdout; return 1 when binary payload would hit a TTY."""

    if cookietruck.utility.is_binary_cookiejar_payload(payload) and sys.stdout.isatty():
        message = \
            "error: cookiejar contains binary cookie data; redirect stdout (e.g. > cookies.txt)"
        print(message, file=sys.stderr)

        return 1

    sys.stdout.buffer.write(payload)

    return 0


def main() -> int:
    """Parse CLI flags, run Qt WebEngine, print session output; return process exit code."""

    # Argument definitions

    p = argparse.ArgumentParser(
        prog="ct_authenticate",
        description=(
            "Load a URL in Qt WebEngine and print captured cookies as JSON "
            "or, with --as-curl-cookiejar, as a curl Netscape cookiejar."
        ),
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
        help="Milliseconds to wait before collecting cookies (default: 800).",
    )
    p.add_argument(
        "--as-curl-cookiejar",
        dest="as_curl_cookiejar",
        action="store_true",
        help="Print captured cookies as a curl Netscape cookiejar instead of JSON.",
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

    # Profile: off-the-record session (no on-disk cookie jar) + no HTTP cache.

    cookie_map: typing.Dict[
        typing.Tuple[bytes, bytes, bytes],
        PySide6.QtNetwork.QNetworkCookie,
    ] = {}
    profile = PySide6.QtWebEngineCore.QWebEngineProfile()
    profile.setHttpCacheType(PySide6.QtWebEngineCore.QWebEngineProfile.HttpCacheType.NoCache)

    def on_cookie_added(c: PySide6.QtNetwork.QNetworkCookie) -> None:
        """Merge each emitted cookie into ``cookie_map`` (latest wins per key)."""

        key = cookietruck.utility.cookie_key(c)
        cookie_map[key] = PySide6.QtNetwork.QNetworkCookie(c)
        _LOGGER.debug("cookie added: name=%r domain=%r path=%r", key[0], key[1], key[2])

    profile.cookieStore().cookieAdded.connect(on_cookie_added)

    # Browser chrome

    view = PySide6.QtWebEngineWidgets.QWebEngineView()
    page = PySide6.QtWebEngineCore.QWebEnginePage(profile, view)
    view.setPage(page)

    # Mutable closure state: ensure ``dump_and_quit`` runs at most once.

    done = {"printed": False}
    exit_code = {"value": 0}

    # Embedded browser plus bottom buttons (copy URL, explicit capture, then exit).

    _LOGGER.debug("main UI: 1100x720, Copy URL and Quit and Dump Cookies buttons")

    container = PySide6.QtWidgets.QWidget()
    container.resize(1100, 720)
    container.setWindowTitle("cookietruck — {url}".format(url=base_url))

    def update_window_title_from_view(url: PySide6.QtCore.QUrl) -> None:
        """Keep the window title in sync with the active page URL (skip WebEngine placeholders)."""

        if url.scheme() == "about":
            path_lower = url.path().lower()

            if path_lower in ("blank", "srcdoc"):
                return

        container.setWindowTitle("cookietruck — {url}".format(url=url.toString()))

    view.urlChanged.connect(update_window_title_from_view)

    layout = PySide6.QtWidgets.QVBoxLayout(container)
    layout.addWidget(view, stretch=1)

    copy_url_btn = PySide6.QtWidgets.QPushButton("Copy URL")
    capture_btn = PySide6.QtWidgets.QPushButton("Quit and Dump Cookies")
    capture_btn.setDefault(True)

    btn_row = PySide6.QtWidgets.QHBoxLayout()
    btn_row.setContentsMargins(0, 20, 0, 20)

    btn_row.addStretch(1)
    btn_row.addWidget(copy_url_btn)
    btn_row.addWidget(capture_btn)
    btn_row.addStretch(1)
    layout.addLayout(btn_row)

    def dump_and_quit() -> None:
        """Collect cookies, print session output to stdout, close the UI, stop the Qt event loop."""

        if done["printed"]:
            return
        done["printed"] = True
        cookies = cookietruck.utility.settle_then_collect(cookie_map, args.settle_ms)

        if args.as_curl_cookiejar:
            if cookietruck.utility.are_cookies_binary_for_cookiejar(cookies) and sys.stdout.isatty():
                message = \
                    "error: cookiejar contains binary cookie data; redirect stdout (e.g. > cookies.txt)"
                print(message, file=sys.stderr)
                exit_code["value"] = 1
            else:
                payload = cookietruck.utility.build_curl_cookiejar(cookies)
                _LOGGER.debug("emitting curl cookiejar with %d cookie records", len(cookies))
                write_code = _write_cookiejar_stdout(payload)

                if write_code != 0:
                    exit_code["value"] = write_code
        else:
            payload = cookietruck.utility.build_payload(base_url, cookies)
            _LOGGER.debug("emitting JSON payload with %d cookie records", len(payload["cookies"]))
            print(json.dumps(payload, indent=2, ensure_ascii=False))

        # WebEngine requires pages to be gone before their profile is released.

        profile.cookieStore().cookieAdded.disconnect(on_cookie_added)
        page.loadFinished.disconnect(apply_initial_focus)
        view.urlChanged.disconnect(update_window_title_from_view)
        copy_url_btn.clicked.disconnect(on_copy_url_clicked)
        capture_btn.clicked.disconnect(on_capture_clicked)
        view.setPage(None)
        page.deleteLater()
        view.deleteLater()
        container.close()
        PySide6.QtCore.QCoreApplication.processEvents()
        app.quit()

    def on_copy_url_clicked() -> None:
        """Copy the live WebEngine page URL to the system clipboard."""

        current_url = page.url().toString()
        app.clipboard().setText(current_url)
        message = "copied URL to clipboard: {url}".format(url=current_url)
        _LOGGER.debug(message)

    def on_capture_clicked() -> None:
        """Disable the button then run the shared capture-and-exit path."""

        capture_btn.setEnabled(False)
        dump_and_quit()

    copy_url_btn.clicked.connect(on_copy_url_clicked)
    capture_btn.clicked.connect(on_capture_clicked)

    # Prefer keyboard focus on the page's first text control; otherwise the quit button.

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

            _LOGGER.debug("initial focus: Quit and Dump Cookies button (no web text control)")

            capture_btn.setFocus(PySide6.QtCore.Qt.FocusReason.ActiveWindowFocusReason)

        def run_focus_script() -> None:
            """Defer to the next event-loop tick so the loaded document is ready for script."""

            page.runJavaScript(_FOCUS_FIRST_TEXT_INPUT_JS, after_js)

        PySide6.QtCore.QTimer.singleShot(0, run_focus_script)

    page.loadFinished.connect(apply_initial_focus)

    container.show()
    view.setUrl(qurl)

    # Run until ``dump_and_quit`` calls ``app.quit()``

    code = app.exec()

    if exit_code["value"] != 0:
        return exit_code["value"]

    return int(code) if code is not None else 0
