# AGENTS.md — Python Desktop Project Context

## 1. Tech Stack & Environment
- **Python Version:** Python 3.10+ (tested and packaged on Python 3.12 64-bit on Windows 11)
- **Environment & Package Manager:** `venv` + `pip` (virtual environment in `.venv/` or system Python; dependencies specified in `README.md` and `livespeech-translator.spec`)
- **GUI Framework:** PyWebView (`pywebview` v5.x) rendering a modern SPA (HTML5 / Vanilla CSS3 / Vanilla ES6 JS) backed by Microsoft Edge WebView2 (`edgechromium` / WinForms), with automatic fallback to the default system browser (`webbrowser.open`)
- **Architecture Pattern:** Local Client-Server Hybrid Desktop Architecture — an asynchronous FastAPI (`uvicorn`) backend running locally on `http://127.0.0.1:8765` communicating with a PyWebView desktop frontend via REST endpoints and real-time WebSockets (`/ws/live`)
- **Local Storage & Config:** Local JSON files stored in the application root directory:
  - `config.json` — user configuration, Gemini API key, model selection, translation mode, device indices/names, per-channel configurations
  - `transcripts.json` — saved session transcripts and dialogue logs
- **Packaging & Distribution:** PyInstaller (`python -m PyInstaller --clean livespeech-translator.spec` / `build_exe.bat`) generating a single-file portable Windows executable at `dist/LiveSpeech-Translator.exe`

## 2. Directory Structure & Key Modules
- **Entry Point:** `main.py` — launches the Uvicorn/FastAPI server in a background daemon thread, initializes `WindowManager`, and starts the native PyWebView window with browser fallback
- `app/` — Main application package:
  - `app/server.py` — Internal FastAPI application: lifespan management, REST API endpoints (`/api/devices`, `/api/config`, `/api/session/start`, `/api/session/stop`, `/api/transcript`), WebSocket broadcast hub (`/ws/live`), automatic language detection, and background idle audio VU meter monitor
  - `app/window_manager.py` — PyWebView window lifecycle manager (window size: 960x720, minimum: 840x600, Edge Chromium runtime)
  - `app/audio_manager.py` — Low-level audio engine via PyAudio (PortAudio): hardware enumeration, CP1251 encoding fix for Windows devices, RMS/VU level calculation, test chime playback, and `AudioTrack` channel management (capture streams, preview streams, and threaded playback queues)
  - `app/gemini_live.py` — Google Gemini Live API translation client using `google-genai` SDK (`gemini-3.5-live-translate-preview`): handles bidirectional streaming sessions, PCM 16 kHz audio upstreaming, PCM 24 kHz audio downstreaming, transcript events, session resumption handles, and automatic reconnect/GoAway recovery
  - `app/config.py` — Configuration and persistence layer: loads/saves `config.json` (with backward compatibility for flat config schemas), manages `transcripts.json`, and defines supported languages (80+ languages)
- `app/static/` — Frontend assets served by FastAPI:
  - `app/static/index.html` — Single-page dashboard UI (status bar, mode selector, outgoing/incoming channel cards, VU meters, language search comboboxes, live transcript feed, settings modal)
  - `app/static/css/styles.css` — Custom pure CSS stylesheet (dark theme, glassmorphism, responsive flex/grid layouts, animations, and custom scrollbars)
  - `app/static/js/app.js` — Client application logic (WebSocket handling, audio meter rendering, live transcript updates, settings persistence, search filters, and TXT export)
- `scripts/` — Developer utilities:
  - `scripts/render_plantuml.py` — Zero-dependency PlantUML to SVG converter using cloud encoding, syncing diagrams into `docs/` and `README.md`
- `cli-version/` — Standalone command-line proof-of-concept scripts:
  - `cli-version/gemini-live-stt.py` — Terminal-based Gemini Live audio translator
  - `cli-version/audio-settings.py` — Helper script to inspect audio device indices in terminal
- `docs/` — Architecture documentation, screenshots, and PlantUML diagrams (`docs/diagrams/`, `docs/images/`)

## 3. GUI & Concurrency Conventions
- **UI Definition Style:** Single-Page Web Application written in pure HTML5, vanilla CSS3, and vanilla JavaScript (no build tools, no bundlers, no node modules) loaded into PyWebView pointing to `http://127.0.0.1:8765`
- **Main Thread Rule:** Never run blocking I/O, network requests, audio capture, or audio playback on the main GUI event loop or the FastAPI asyncio event loop
- **Concurrency & Signals:**
  - `main.py` runs Uvicorn in a dedicated daemon thread (`threading.Thread(target=run_server, daemon=True)`) while PyWebView blocks on the main thread (`webview.start()`)
  - FastAPI executes on an `asyncio` event loop; translation sessions and idle audio meters are spawned via `asyncio.create_task()`
  - Blocking PyAudio calls (`read`, `write`, `play_test_tone`) are dispatched to worker threads via `loop.run_in_executor(None, ...)` or dedicated playback worker threads fed by `queue.Queue`
  - Real-time events (VU meter audio levels, partial transcripts, session state changes) are pushed from server to UI over WebSockets (`/ws/live`) via `broadcast()` and `broadcast_sync()`
- **Styling & Theming:** Custom dark-themed CSS (`app/static/css/styles.css`) using CSS variables, Google Fonts (`Inter`), color-coded channels (green/blue accents for outgoing/incoming audio), and hardware-accelerated CSS transitions
- **Resource Paths:**
  - Static files: Handled in `app/server.py` using `sys._MEIPASS` when frozen:
    `Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "app" / "static"`
  - Persistent files (`config.json`, `transcripts.json`): Handled in `app/config.py` using `Path(sys.executable).resolve().parent` when frozen, ensuring writes go to the application directory rather than the ephemeral `_MEIPASS` extraction folder

## 4. Development, Build & Packaging Commands
*(Run commands inside the Python virtual environment)*
- **Install Dependencies:** `pip install fastapi uvicorn pywebview google-genai pyaudio numpy pydantic pyinstaller`
- **Run App (Dev):** `python main.py`
- **Compile UI / Resources:** *N/A (static web files are served directly; no compilation step required)*
- **Run Tests:** `pytest` *(when test suite is added; excluded from PyInstaller binary)*
- **Linter & Formatter:** `ruff check . && ruff format .`
- **Build Standalone Executable:** `.\build_exe.bat` or `python -m PyInstaller --clean livespeech-translator.spec`
- **Render PlantUML Diagrams:** `python scripts/render_plantuml.py --sync-readme`

## 5. Testing & Mocking Guidelines
- **Test Framework:** `pytest` and `pytest-asyncio` (for FastAPI HTTP and WebSocket testing via `httpx.AsyncClient` / `starlette.testclient.TestClient`)
- **Audio & API Mocking Rules:**
  - Mock `pyaudio.PyAudio` and stream instances (`open_input_stream`, `open_output_stream`) using `unittest.mock.MagicMock` to run headless without audio hardware or virtual cables (VB-CABLE / Hi-Fi CABLE)
  - Mock `google.genai.Client` and `live.connect` async context managers to simulate translation streams without consuming API quota or requiring network access
  - Mock `webview.create_window` and `webview.start` when testing entrypoint or window management logic

## 6. Guardrails & Do-Nots
- **Do Not Write Persistent Data to `_MEIPASS`:** When frozen by PyInstaller, never save mutable state (`config.json`, `transcripts.json`) inside `sys._MEIPASS` because it is an ephemeral temporary directory cleaned up on process exit. Always use `Path(sys.executable).resolve().parent`.
- **Do Not Remove CP1251 Encoding Fix:** Do not bypass `_fix_encoding()` in `app/audio_manager.py`; Windows audio device names on non-English locales cause encoding errors or mojibake in PortAudio.
- **Do Not Block Event Loops:** Never invoke blocking PyAudio reads or synchronous network calls directly inside FastAPI endpoint functions or WebSocket handlers; use async methods or `loop.run_in_executor()`.
- **Strict Audio Format Requirements:** Input streams must remain 16,000 Hz, 16-bit mono Linear PCM, and output playback streams must remain 24,000 Hz Linear PCM to comply with Gemini Live API requirements.
- **Cross-Platform / OS Paths:** Always use `pathlib.Path` for file path resolution instead of hardcoded strings or backslashes.

## 7. Folder Structure and Description
```text
LiveSpeech-Translator/
├── .gitignore                   # Git ignore patterns (.venv, config.json, build artifacts, etc.)
├── AGENTS.md                    # Agent context and repository guide
├── README.md                    # Project overview, audio setup diagrams, and usage guide
├── build_exe.bat                # Windows batch script to compile the PyInstaller standalone executable
├── config.json                  # Runtime user settings (API key, mode, audio device mappings)
├── livespeech-translator.spec   # PyInstaller packaging specification with hidden imports & excludes
├── main.py                      # Application entry point: starts FastAPI daemon & PyWebView window
├── transcripts.json             # Runtime persistence of session translation history
├── art/                         # Master branding artwork and vector design source files (app_icon.svg)
├── assets/                      # Application icons and packaged binary artwork (icon.ico, app_icon_512.png)
├── app/                         # Core application package
│   ├── __init__.py              # Package marker
│   ├── audio_manager.py         # PyAudio hardware capture, playback tracks, and VU meter calculations
│   ├── config.py                # Configuration loader, defaults, language lists, and file persistence
│   ├── gemini_live.py           # Gemini 3.5 Live WebSocket translation client & session manager
│   ├── server.py                # FastAPI REST endpoints, WebSocket event hub, and idle audio monitor
│   ├── window_manager.py        # PyWebView desktop window creation and event loop wrapper
│   └── static/                  # Web dashboard UI assets
│       ├── index.html           # Main dashboard markup, status bar, channel cards, and settings modal
│       ├── css/
│       │   └── styles.css       # Complete application styling (dark modern theme, VU meters, controls)
│       └── js/
│           └── app.js           # Frontend interactivity, WebSocket client, meters, and transcript management
├── cli-version/                 # CLI proof-of-concept scripts and documentation
│   ├── .env                     # Local environment file for CLI scripts (ignored in git)
│   ├── README.md                # CLI setup and usage instructions
│   ├── audio-settings.py        # Helper to inspect audio input/output device indices
│   ├── gemini-live-stt.py       # Terminal streaming translator script
│   └── transcription.txt        # Output text transcript from CLI sessions
├── docs/                        # Project documentation and graphics
│   ├── diagrams/                # PlantUML diagrams and generated SVG routing flowcharts
│   │   ├── mode1_incoming.puml  # Incoming mode audio routing diagram source
│   │   ├── mode1_incoming.svg   # Incoming mode SVG graphic
│   │   ├── mode2_outgoing.puml  # Outgoing mode audio routing diagram source
│   │   ├── mode2_outgoing.svg   # Outgoing mode SVG graphic
│   │   ├── mode3_bidirectional.puml # Bidirectional mode audio routing diagram source
│   │   └── mode3_bidirectional.svg  # Bidirectional mode SVG graphic
│   └── images/                  # Screenshots and guides (e.g., Windows Volume Mixer setup)
│       └── windows-settings.png
└── scripts/                     # Developer automation scripts
    └── render_plantuml.py       # Cloud-based PlantUML to SVG converter script
```
