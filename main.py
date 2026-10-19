"""
LiveSpeech Translator Application Entrypoint.
Starts the FastAPI server in a background thread, waits deterministically for
the TCP socket to bind, and launches the PyWebView native desktop window.
"""

import socket
import sys
import threading
import time
import webbrowser
import uvicorn

from app.server import app
from app.window_manager import WindowManager

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765


def run_server():
    """Run the FastAPI server in a background daemon thread."""
    config = uvicorn.Config(
        app,
        host=SERVER_HOST,
        port=SERVER_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()


def wait_for_server_ready(host: str, port: int, timeout: float = 5.0) -> bool:
    """Poll loopback socket at 15ms intervals until Uvicorn is accepting connections."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.05)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.015)
    return False


def main():
    print("=" * 55)
    print("  LiveSpeech Translator")
    print(f"  Starting local server at http://{SERVER_HOST}:{SERVER_PORT}")
    print("=" * 55)

    # Start FastAPI in background daemon thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    wait_for_server_ready(SERVER_HOST, SERVER_PORT)

    app_url = f"http://{SERVER_HOST}:{SERVER_PORT}"

    try:
        wm = WindowManager(server_url=app_url)
        wm.create_main_window()
        print("  Launching native desktop window (Edge WebView2)...")
        wm.start()
    except Exception as e:
        print(f"  [Notice] Native window closed or not available: {e}")
        print(f"  Opening browser fallback at {app_url}...")
        webbrowser.open(app_url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n  Session ended.")


if __name__ == "__main__":
    main()
