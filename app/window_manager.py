"""
PyWebView window controller for LiveSpeech Translator.
Creates the main dashboard window and the floating subtitle overlay using
Windows 11 built-in Microsoft Edge WebView2 runtime.
"""

import webview


class WindowManager:
    """Manages PyWebView native desktop window."""

    def __init__(self, server_url: str = "http://127.0.0.1:8765"):
        self.server_url = server_url
        self.main_window = None

    def create_main_window(self):
        """Create the primary dashboard window."""
        self.main_window = webview.create_window(
            title="LiveSpeech Translator",
            url=self.server_url,
            width=960,
            height=720,
            min_size=(840, 600),
            resizable=True,
            text_select=True,
        )
        return self.main_window

    def start(self):
        """
        Start the PyWebView event loop.
        This call blocks until all windows are closed.
        """
        webview.start(debug=False)
