"""Capture cookietruck GUI screenshots for documentation (run under xvfb on headless hosts)."""

# Standard library

import os
import sys

# Qt (PySide6)

import PySide6.QtCore
import PySide6.QtWebEngineCore
import PySide6.QtWebEngineWidgets
import PySide6.QtWidgets

_WINDOW_TITLE_TEMPLATE = "cookietruck — {url}"
_DEMO_URL = "https://example.com/sign-in"


def _build_demo_page_url(repository_root: str) -> str:
    """Return a file URL for the bundled sign-in demo HTML page."""

    demo_html_path = os.path.join(repository_root, "asset", "documentation", "sign-in-demo.html")
    demo_url = PySide6.QtCore.QUrl.fromLocalFile(demo_html_path)

    return demo_url.toString()


def _save_widget_screenshot(widget: PySide6.QtWidgets.QWidget, output_path: str) -> None:
    """Grab the widget pixmap and write it to ``output_path`` as PNG."""

    pixmap = widget.grab()
    saved = pixmap.save(output_path, "PNG")

    if not saved:
        message = "failed to write screenshot: {path}".format(path=output_path)
        raise RuntimeError(message)


def main() -> int:
    """Build the authenticate UI, capture main and copy-overlay shots, return exit code."""

    repository_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    image_directory = os.path.join(repository_root, "asset", "documentation", "image")
    os.makedirs(image_directory, exist_ok=True)

    main_screenshot_path = os.path.join(image_directory, "ct-authenticate-main.png")
    copy_overlay_screenshot_path = os.path.join(image_directory, "ct-authenticate-copy-url.png")
    demo_page_url = _build_demo_page_url(repository_root)

    # Qt application + shared GL context (WebEngine requirement)

    PySide6.QtWidgets.QApplication.setAttribute(
        PySide6.QtCore.Qt.ApplicationAttribute.AA_ShareOpenGLContexts
    )
    app = PySide6.QtWidgets.QApplication([sys.argv[0]])

    profile = PySide6.QtWebEngineCore.QWebEngineProfile()
    profile.setHttpCacheType(PySide6.QtWebEngineCore.QWebEngineProfile.HttpCacheType.NoCache)

    view = PySide6.QtWebEngineWidgets.QWebEngineView()
    page = PySide6.QtWebEngineCore.QWebEnginePage(profile, view)
    view.setPage(page)

    container = PySide6.QtWidgets.QWidget()
    container.resize(1100, 720)
    container.setWindowTitle(_WINDOW_TITLE_TEMPLATE.format(url=_DEMO_URL))

    layout = PySide6.QtWidgets.QVBoxLayout(container)
    layout.addWidget(view, stretch=1)

    copy_url_button = PySide6.QtWidgets.QPushButton("Copy URL")
    capture_button = PySide6.QtWidgets.QPushButton("Quit and Dump Cookies")
    capture_button.setDefault(True)

    button_row = PySide6.QtWidgets.QHBoxLayout()
    button_row.setContentsMargins(0, 20, 0, 20)
    button_row.addStretch(1)
    button_row.addWidget(copy_url_button)
    button_row.addWidget(capture_button)
    button_row.addStretch(1)
    layout.addLayout(button_row)

    copy_overlay = PySide6.QtWidgets.QLabel(container)
    copy_overlay.setText("Copied to clipboard")
    copy_overlay.setAlignment(PySide6.QtCore.Qt.AlignmentFlag.AlignCenter)
    copy_overlay.setStyleSheet(
        "QLabel {"
        "  background-color: rgba(0, 0, 0, 180);"
        "  color: white;"
        "  padding: 12px 24px;"
        "  border-radius: 8px;"
        "  font-size: 14px;"
        "}"
    )
    copy_overlay.setAttribute(PySide6.QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    copy_overlay.hide()

    load_state = {"ready": False}

    def capture_copy_overlay_screenshot() -> None:
        """Show the clipboard toast and write the second documentation screenshot."""

        copy_overlay.adjustSize()
        horizontal = (container.width() - copy_overlay.width()) // 2
        vertical = (container.height() - copy_overlay.height()) // 2

        if horizontal < 0:
            horizontal = 0

        if vertical < 0:
            vertical = 0

        copy_overlay.move(horizontal, vertical)
        copy_overlay.show()
        copy_overlay.raise_()
        container.repaint()
        PySide6.QtCore.QCoreApplication.processEvents()
        _save_widget_screenshot(container, copy_overlay_screenshot_path)

        view.setPage(None)
        page.deleteLater()
        view.deleteLater()
        container.close()
        PySide6.QtCore.QCoreApplication.processEvents()
        app.quit()

    def capture_main_screenshot() -> None:
        """Write the primary window screenshot, then schedule the overlay shot."""

        container.repaint()
        PySide6.QtCore.QCoreApplication.processEvents()
        _save_widget_screenshot(container, main_screenshot_path)
        PySide6.QtCore.QTimer.singleShot(200, capture_copy_overlay_screenshot)

    def on_load_finished(ok: bool) -> None:
        """Defer capture until WebEngine has painted the loaded document."""

        if load_state["ready"]:
            return

        if not ok:
            return

        load_state["ready"] = True
        PySide6.QtCore.QTimer.singleShot(600, capture_main_screenshot)

    page.loadFinished.connect(on_load_finished)

    container.show()
    view.setUrl(PySide6.QtCore.QUrl(demo_page_url))

    exit_code = app.exec()

    if exit_code is None:
        return 0

    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
