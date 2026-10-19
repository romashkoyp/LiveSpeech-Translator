<p align="center">
  <img src="art/app_icon.svg" width="96" height="96" alt="LiveSpeech Translator Logo" />
</p>

# LiveSpeech Translator

Real-time voice-to-voice translation and live subtitles desktop application powered by **Google Gemini Live API (`gemini-3.5-live-translate-preview`)**.

Translate meetings, voice calls, presentations, and streams in real time with zero subscription fees.

---

## 🌟 Key Features

- **3 Translation Modes**:
- `🎧 Incoming Only` — Translates incoming audio only (for foreign meetings, YouTube, lectures, podcasts).
- `🎙️ Outgoing Only` — Translates your voice only (for presentations, webinars, or outgoing voice calls).
- `⇄ Bidirectional (Meeting Mode)` — Full two-way live translation for meetings (Zoom, Teams, Meet, Discord).

- 🔊 **Direct Low-Latency Speech Playback**: Real-time 24 kHz translated audio stream played directly into headphones or virtual audio cables.
- 🔍 **Searchable Languages (80+)**: Instant search and selection across 80+ supported languages.
- 🤖 **Automatic Language Detection**: Dynamically recognizes the speaker's language in real time.
- 💬 **Live Subtitles & Transcripts**: Color-coded speaker tags with live keyword search and highlighting.
- 📄 **1-Click TXT Export**: Save full transcripts with clean timestamps (`HH:MM:SS`) and speaker tags.
- 📦 **Standalone Windows App**: Ready-to-use portable `.exe` with no complex setup needed.

---

## 🚀 Quick Start

### Step 1: Install Free Virtual Audio Drivers (One-Time Setup)

To route audio between LiveSpeech Translator and meeting apps (like Zoom or Teams), install these two free drivers:

1. **VB-CABLE Driver**: [Download VB-CABLE](https://vb-audio.com/Cable/index.htm) *(used for Outgoing audio)*
2. **Hi-Fi CABLE Driver**: [Download Hi-Fi CABLE](https://vb-audio.com/Cable/index.htm#DownloadASIOBridge) *(used for Incoming audio)*

> **How to install**:
>
> 1. Extract the downloaded ZIP folders.
> 2. Right-click `VBCABLE_Setup_x64.exe` (or `HiFiCable_Setup_x64.exe`) and choose **"Run as administrator"**.
> 3. Restart your computer after installation.

---

### Step 2: Add Your Free Gemini API Key

1. Get a free API key from [Google AI Studio](https://aistudio.google.com/).
2. Open **LiveSpeech Translator**.
3. Click **`⚙️ Settings / API Key`** in the top-right corner.
4. Paste your key and click **`🔄 Test Connection`** ➔ **`💾 Save & Apply`**.

---

### Step 3: Choose Your Mode & Start Translating

1. Select your desired mode on the top bar (`🎧 Incoming`, `🎙️ Outgoing` or `⇄ Bidirectional`).
2. Select your input/output audio devices according to the mode diagrams below.
3. Click **`▶ START STREAMING`**.

---

## 🎛️ Audio Setup Guide

### Mode 1: Incoming Only (Meeting / YouTube / Stream ➔ You)

Use this mode when you **only need to listen to foreign speech translated into your headphones** (e.g. listening to a lecture, watching a live stream, watching a YouTube video, or listening to a meeting).

#### Audio Routing Diagram (incoming audio only)

<p align="center">
  <img src="docs/diagrams/mode1_incoming.svg" alt="mode1_incoming" width="100%">
</p>

#### ⚙️ Settings Configuration

**1. For meeting apps like Zoom, Teams, Google Meet, Discord, Telegram, Whatsapp and etc.:**

- Open **Meeting app** and go to **audio settings**
- Set **Speaker / Audio Output** to `HiFi Cable Input (VB-Audio Hi-Fi Cable)`

**2. For browsers like Chrome, Edge, Firefox, Opera, Brave and etc.:**

- Open **Windows** settings -> **System** -> **Sound** -> **Volume Mixer**
- In **Apps** section find your **Browser**
- Set `HiFi Cable Input (VB-Audio Hi-Fi Cable)` as output device instead of **Default**

<p align="center">
  <img src="docs/images/windows-settings.png" alt="windows-settings" width="100%">
</p>

**3. Inside LiveSpeech Translator:**

| Setting | What to Select |
| :--- | :--- |
| **Mode** | `Incoming Only` |
| **Input** | `HiFi Cable Output (VB-Audio Hi-Fi Cable)` |
| **Output** | Your physical Headphones / Speakers |
| **Target Language** | Your native language |

---

### Mode 2: Outgoing Only (You ➔ Others / Presentation)

Use this mode when you **only need your voice translated** to remote listeners (e.g. giving a presentation, hosting a webinar, streaming, or in-person speaking).

#### Audio Routing Diagram (outgoing audio only)

<p align="center">
  <img src="docs/diagrams/mode2_outgoing.svg" alt="mode2_outgoing" width="100%">
</p>

#### ⚙️ Settings Configuration

**1. Inside Your Meeting / Streaming App:**

- **Microphone**: Select `CABLE Output (VB-Audio Virtual Cable)`.

**2. Inside LiveSpeech Translator:**

| Setting | What to Select |
| :--- | :--- |
| **Input** | Your physical Microphone |
| **Output** | `CABLE Input (VB-Audio Virtual Cable)` |
| **Target Language** | The audience's language |

### Mode 3: ⇄ Bidirectional (Live Meeting Mode)

Use this mode for **full two-way translation** in video meetings (Zoom, Microsoft Teams, Google Meet, Discord). You speak in your language and attendees hear translated speech; when they speak, you hear translated speech in your headphones.

#### Audio Routing Diagram (bidirectional mode)

<p align="center">
  <img src="docs/diagrams/mode3_bidirectional.svg" alt="mode3_bidirectional" width="100%">
</p>

#### ⚙️ Settings Configuration

**1. Inside LiveSpeech Translator:**

| Section | Setting | What to Select |
| :--- | :--- | :--- |
| | **Mode** | `⇄ Bidirectional` |
| **🎙️ Outgoing Translation** | **Input** | Your physical Microphone |
| | **Output (Virtual Cable)** | `CABLE Input (VB-Audio Virtual Cable)` |
| | **Target Language** | Meeting attendees' language |
| **🎧 Incoming Translation** | **Input** | `HiFi Cable Output (VB-Audio Hi-Fi Cable)` |
| | **Output** | Your physical Headphones / Speakers |
| | **Target Language** | Your native language |

**2. Inside Meeting Apps (Zoom / Teams / Meet / Discord):**

- **Microphone**: Select `CABLE Output (VB-Audio Virtual Cable)`.
- **Speaker**: Select `HiFi Cable Input (VB-Audio Hi-Fi Cable)`.

---

## 📄 Transcript Export Format Examples

### Bidirectional Mode Export

```text
LiveSpeech Translator Transcript
══════════════════════════════════════════════════
Mode:        bidirectional
Export Date: 01.09.2026 14:00:00
══════════════════════════════════════════════════

[14:00:05]
[YOU SPEAK → EN]: Hello everyone, thanks for joining the call today.
[THEY HEAR → FI]: Hei kaikki, kiitos että liityitte puheluun tänään.

[14:00:15]
[THEY SPEAK → FI]: Tervetuloa! Käydään läpi projektin nykytilanne.
[YOU HEAR   → EN]: Welcome! Let's go over the current status of the project.
```

### Incoming Mode Export

```text
LiveSpeech Translator Transcript
══════════════════════════════════════════════════
Mode:        incoming
Export Date: 01.09.2026 14:00:00
══════════════════════════════════════════════════

[14:00:15]
[THEY SPEAK → EN]: Welcome to the annual technology keynote.
[YOU HEAR   → FI]: Tervetuloa vuotuiseen teknologiakatsaukseen.
```

### Outgoing Mode Export

```text
LiveSpeech Translator Transcript
══════════════════════════════════════════════════
Mode:        outgoing
Export Date: 01.09.2026 14:00:00
══════════════════════════════════════════════════

[14:00:05]
[YOU SPEAK → FI]: Tervetuloa esitykseen, aloitamme heti.
[THEY HEAR → EN]: Welcome to the presentation, we will start right away.
```

---

## 💻 Developer & Build Guide

### Option 1: Run from Standalone Binary (.exe)

Directly run the compiled executable:

```bash
dist\LiveSpeech-Translator.exe
```

### Option 2: Run from Python Source

```bash
# 1. Install dependencies
pip install fastapi uvicorn pywebview google-genai pyaudio numpy pydantic pyinstaller

# 2. Run application
python main.py
```

### Option 3: Build Standalone Executable (.exe)

Run the build script or use PyInstaller:

```bash
# Using batch file
build_exe.bat

# Or using PyInstaller directly
python -m PyInstaller --clean livespeech-translator.spec
```

The resulting executable will be in `dist\LiveSpeech-Translator.exe`.

---

## 🛠️ Technical Specifications

- **AI Translation Model**: `gemini-3.5-live-translate-preview` via Google GenAI Live WebSocket API
- **Input Audio Capture**: 16,000 Hz, 16-bit Mono Linear PCM
- **Output Audio Playback**: 24,000 Hz, 16-bit Linear PCM direct hardware stream
- **Desktop Runtime**: Microsoft Edge WebView2 via PyWebView
- **Backend Server**: FastAPI + Uvicorn asyncio server on `127.0.0.1:8765`
- **Configuration**: Local JSON storage in `config.json`
- **Temporary storage**: Local JSON storage for transcripts in `transcripts.json`
