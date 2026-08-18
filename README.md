# LiveSpeech Translator: Real-Time Audio Translation & Meeting Subtitles Desktop App

A lightweight, high-performance desktop application for real-time voice-to-voice translation and live subtitles powered by the **Google Gemini Live API (`gemini-3.5-live-translate-preview`)** and **PyWebView (Microsoft Edge WebView2)** totally FREE OF CHARGE for everyone.

Supports **Bidirectional (Two-Way) Live Meeting Translation** using a 100% free virtual audio cable topology for apps like Zoom, Google Meet, Microsoft Teams, and Discord.

---

## 🌟 Key Features

- ⚡ **Bidirectional Live Meeting Mode**: Translate two separate audio streams simultaneously:
  - **Outgoing (You ➔ Meeting)**: Translates your microphone into the meeting app (e.g. Finnish ➔ English).
  - **Incoming (Meeting ➔ You)**: Translates meeting attendees into your headphones (e.g. English ➔ Finnish).
- 🎛️ **3 Operating Modes**:
  - `⚡ Bidirectional (Meeting Mode)` — Full two-way live translation.
  - `🎙️ Outgoing Only` — Only translates your voice to the target audience.
  - `🎧 Incoming Only` — Only translates incoming audio from calls, videos, or streams to your headphones.
- 🔊 **Direct Hardware Playback**: 24 kHz translated speech audio streams directly to your selected Windows playback devices with dedicated background audio workers.
- 🔍 **Searchable Language Combobox**: Instant typing-based search and filtering across 80+ supported languages. Displays clean, natural language names (e.g. `Finnish`, `English`, `Swedish`).
- 🤖 **Auto-Detected Source Language**: Speech language is automatically detected in real-time with dynamic language tags (e.g. `[FI]:`, `[EN]:`, `[FR]:`, `[ES]:`, `[DE]:`).
- 💬 **Live Color-Coded Transcripts**: Real-time transcription with blue/purple speaker tags (`🎙️ YOU`, `🎧 MEETING`) and live typing animations.
- 🔎 **Search with Keyword Highlighting**: Real-time transcript search with bright keyword highlighting across source and translated text.
- 🎙️ **Dual VU Meters & Device Testing**: Live dBFS perceptual volume meters on all active inputs and outputs with an integrated **`🔊 Test Sound`** button.
- ⚙️ **Secure Key & Config Persistence**: Live Gemini API key verification (`🟢 API Key configured` / `✅ Connected`), one-click key reset (`🗑️`), and persistence in `config.json`.
- 📄 **Standardized TXT Export**: Verbatim export with 24-hour timestamps (`HH:MM:SS`), date headers, and speaker routing tags.
- 📦 **Standalone Single-File Executable**: Compile to a portable Windows `.exe` with no external Python runtime required.

---

## 🗺️ Dual Virtual Cable Meeting Topology

For bidirectional meeting translation, LiveSpeech Translator uses two free Windows audio drivers from VB-Audio:
1. **VB-CABLE** ➔ `CABLE Input` / `CABLE Output` (Outgoing feed)
2. **Hi-Fi CABLE** ➔ `HiFi Cable Input` / `HiFi Cable Output` (Incoming feed)

```text
+----------------------------------------------------------------------------------------+
|                      CHANNEL 1: OUTGOING (You ➔ Meeting Attendees)                     |
+----------------------------------------------------------------------------------------+
  [🎙️ Physical Microphone]
          │ (Your speech, e.g. Finnish)
          ▼
  [⚡ Gemini Live Session #1] (Target: English)
          │ (Translated English audio stream)
          ▼
  [🔊 CABLE Input (VB-Audio Virtual Cable)]
          │ (Virtual audio routing)
          ▼
  [💻 Zoom / Meet / Teams Mic (Set to CABLE Output)]
          │ (Remote attendees hear translated speech)
          ▼
  [👥 Meeting Attendees]

+----------------------------------------------------------------------------------------+
|                      CHANNEL 2: INCOMING (Meeting Attendees ➔ You)                     |
+----------------------------------------------------------------------------------------+
  [👥 Meeting Attendees]
          │ (Remote attendees speak, e.g. English)
          ▼
  [💻 Zoom / Meet / Teams Speaker (Set to HiFi Cable Input)]
          │ (Meeting audio feed)
          ▼
  [🔊 HiFi Cable Output (VB-Audio Hi-Fi Cable)]
          │ (Incoming audio stream)
          ▼
  [⚡ Gemini Live Session #2] (Target: Finnish)
          │ (Translated Finnish audio stream)
          ▼
  [🎧 Physical Headphones / Speakers]
```

### Audio Device Mapping Summary

| Direction | LiveSpeech Translator Input | LiveSpeech Translator Output | Meeting App (Zoom / Teams / Meet) |
| :--- | :--- | :--- | :--- |
| **🎙️ Outgoing (Me ➔ Meeting)** | **Physical Microphone** | **`CABLE Input (VB-Audio)`** | **Microphone**: `CABLE Output (VB-Audio)` |
| **🎧 Incoming (Meeting ➔ Me)** | **`HiFi Cable Output`** | **Physical Headphones** | **Speaker**: `HiFi Cable Input` |

---

## 🚀 Quick Start (Windows 10 / 11)

### Option 1: Run the Standalone Executable (.exe)
Double-click [`dist\LiveSpeech-Translator.exe`](dist/LiveSpeech-Translator.exe) to start the app immediately.

### Option 2: Run from Python Source
```bash
# Install dependencies
pip install fastapi uvicorn pywebview google-genai pyaudio numpy pydantic langdetect pyinstaller

# Launch application
python main.py
```

### Option 3: Build Executable from Source
Double-click [`build_exe.bat`](build_exe.bat) or run:
```bash
python -m PyInstaller --clean livespeech-translator.spec
```
The compiled binary will be placed in `dist\LiveSpeech-Translator.exe`.

---

## ⚙️ Initial Configuration (Gemini API Key)

1. Open **LiveSpeech Translator**.
2. Click **`⚙️ Settings / API Key`** in the top-right header.
3. Enter your **Google Gemini API Key** ([Get a key from Google AI Studio](https://aistudio.google.com/)).
4. Click **`🔄 Test Connection`** to verify (status changes to `🟢 API Key configured`).
5. Click **`💾 Save & Apply`**.

---

## 🎧 Audio Routing Setup Guide

### 1. Free Virtual Audio Drivers Installation
- **VB-CABLE Driver** (Standard): [vb-audio.com/Cable](https://vb-audio.com/Cable/index.htm)
- **Hi-Fi CABLE Driver**: [vb-audio.com/Cable/index.htm#DownloadHiFiCable](https://vb-audio.com/Cable/index.htm#DownloadHiFiCable)

*(Restart your PC after installing the audio drivers).*

### 2. Configure LiveSpeech Translator
1. Select **`⚡ Bidirectional (Meeting Mode)`** on the mode bar.
2. In **Outgoing Translation (You ➔ Meeting)**:
   - **Input**: Your physical Microphone.
   - **Target Language**: Type or select the language remote attendees speak (e.g. `English`).
   - **Output**: `CABLE Input (VB-Audio Virtual Cable)`.
3. In **Incoming Translation (Meeting ➔ You)**:
   - **Input**: `HiFi Cable Output (VB-Audio Hi-Fi Cable)`.
   - **Target Language**: Type or select your native language (e.g. `Finnish`).
   - **Output**: Your physical Headphones / Speakers.
   - Click **`🔊 Test`** to confirm test audio plays in your headphones.

### 3. Configure Zoom / Teams / Google Meet
- **Microphone**: Select `CABLE Output (VB-Audio Virtual Cable)`.
- **Speaker**: Select `HiFi Cable Input (VB-Audio Hi-Fi Cable)`.

### 4. Start Live Translation
- Click **`▶ START STREAMING`** (or press `Space`).
- Speak into your mic: your speech will be translated and streamed to the meeting app.
- Remote attendees speak: their audio will be translated and played through your headphones.

---

## ⌨️ Controls & Shortcuts

| Action | Shortcut / Control | Description |
| :--- | :--- | :--- |
| **Start / Stop Session** | `Space` / `▶ START STREAMING` | Toggles live audio capture and streaming across active channels. |
| **Mode Selection** | `⚡ Bidirectional` / `🎙️ Outgoing` / `🎧 Incoming` | Switches between two-way meeting mode and single-channel modes. |
| **Language Search** | Type in **Target Language** field | Instantly filters 80+ supported languages by name or code. |
| **Settings & API Key** | `⚙️ Settings / API Key` | Configure, verify, or reset your Gemini API key. |
| **Test Output Sound** | `🔊 Test` | Plays a 2-tone chime through headphones to verify routing. |
| **Search Transcripts** | Search box in bottom toolbar | Live keyword search with bright yellow/amber text highlighting. |
| **Auto-scroll Toggle** | `Auto-Scroll` checkbox | Automatically follows newest transcript entries. |
| **Clear Transcripts** | `🧹 Clear` | Clears transcript feed and session memory. |
| **Export Transcripts** | `📄 Export TXT` | Exports complete meeting transcript with timestamps and speaker tags. |

---

## 📄 Export Format Example

```text
LiveSpeech Translator Transcript
══════════════════════════════════════════════════
Mode: bidirectional
Outgoing Language: English
Incoming Language: Finnish
Export Date: 18.08.2026 12:30:00
══════════════════════════════════════════════════

[12:30:05]
[YOU → EN] [FI]: Hei kaikki, mukava liittyä kokoukseen!
[YOU → EN] [EN]: Hello everyone, glad to join the meeting!

[12:30:14]
[MEETING → FI] [EN]: Welcome! We were just discussing the project timeline.
[MEETING → FI] [FI]: Tervetuloa! Keskustelimme juuri projektin aikataulusta.
```

---

## 📁 Project Architecture

```
livespeech-translator/
├── main.py                  # Entrypoint (FastAPI server daemon + PyWebView desktop window)
├── build_exe.bat            # One-click PyInstaller executable build script
├── livespeech-translator.spec # PyInstaller packaging configuration
├── config.json              # Local persistent configuration (API Key, Device indices, Mode)
├── dist/
│   └── LiveSpeech-Translator.exe # Standalone portable Windows binary
└── app/
    ├── config.py            # Nested channel config manager & 80+ language definitions
    ├── audio_manager.py     # Multi-track audio engine (independent capture/playback tracks)
    ├── gemini_live.py       # Gemini Live WebSocket client (voice-to-voice + token streams)
    ├── server.py            # FastAPI backend, multi-track audio router & WebSocket hub
    ├── window_manager.py    # Native Edge WebView2 desktop window controller
    └── static/
        ├── index.html       # Clean glassmorphic layout with 2/3 & 1/3 proportional grid
        ├── css/styles.css   # Dark glassmorphic design system, typography & animations
        └── js/app.js        # Searchable comboboxes, audio level meters & live search highlighting
```

---

## 🛠️ Technical Specifications

- **AI Translation Model**: `gemini-3.5-live-translate-preview` via Google GenAI Live WebSocket API
- **Input Audio Capture**: 16,000 Hz, 16-bit Mono Linear PCM (100ms / 1600 frame chunks per channel)
- **Output Audio Playback**: 24,000 Hz, 16-bit Linear PCM (background worker threads with auto stereo expansion)
- **Language Detection**: Real-time multi-tier detector (Gemini metadata + script heuristics + `langdetect`)
- **Desktop Runtime**: Microsoft Edge WebView2 via PyWebView
- **Backend Server**: FastAPI + Uvicorn asyncio server on `127.0.0.1:8765`
