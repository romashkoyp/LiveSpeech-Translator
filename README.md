# ⚡ LiveSpeech Translator

Real-time voice-to-voice translation and live subtitles desktop application powered by **Google Gemini Live API (`gemini-3.5-live-translate-preview`)**.

Translate meetings, voice calls, presentations, and streams in real time with zero subscription fees.

---

## 🌟 Key Features

- ⚡ **3 Translation Modes**:
  - `⚡ Bidirectional (Meeting Mode)` — Full two-way live translation for meetings (Zoom, Teams, Meet, Discord).
  - `🎙️ Outgoing Only` — Translates your voice only (for presentations, webinars, or outgoing voice calls).
  - `🎧 Incoming Only` — Translates incoming audio only (for foreign meetings, YouTube, lectures, podcasts).
- 🔊 **Direct Low-Latency Speech Playback**: Real-time 24 kHz translated audio stream played directly into headphones or virtual audio cables.
- 🔍 **Searchable Languages (80+)**: Instant search and selection across 80+ supported languages.
- 🤖 **Automatic Language Detection**: Dynamically recognizes the speaker's language in real time.
- 💬 **Live Subtitles & Transcripts**: Color-coded speaker tags (`🎙️ YOU`, `🎧 MEETING`) with live keyword search and highlighting.
- 📄 **1-Click TXT Export**: Save full transcripts with clean timestamps (`HH:MM:SS`) and speaker tags.
- 📦 **Standalone Windows App**: Ready-to-use portable `.exe` with no complex setup needed.

---

## 🚀 3-Step Quick Start (For Beginners)

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

1. Select your desired mode on the top bar (`⚡ Bidirectional`, `🎙️ Outgoing`, or `🎧 Incoming`).
2. Select your input/output audio devices according to the mode diagrams below.
3. Click **`▶ START STREAMING`** (or press the **`Space`** bar).

---

## 🎛️ Audio Setup Guide for All 3 Modes

---

### Mode 1: Incoming Only (Meeting / YouTube / Stream ➔ You)

Use this mode when you **only need to listen to foreign speech translated into your headphones** (e.g. listening to a lecture, watching a live stream, watching a YouTube video, or listening to a meeting).

#### Audio Routing Diagram (incoming audio only)

```plantuml
@startuml
!$ICONURL = "https://raw.githubusercontent.com/tupadr3/plantuml-icon-font-sprites/v3.0.0/icons"
!include $ICONURL/common.puml
!include $ICONURL/font-awesome-6/volume_high.puml
!include $ICONURL/material/record_voice_over.puml
skinparam {
  ComponentStyle rectangle
  DefaultTextAlignment center
  backgroundColor White
}
left to right direction
component "Meeting App/\nBrowser/\nMedia Player" as M #LightBlue{
  interface out as MOut #Black
  interface in as MIn #Black
}
component "LiveSpeech" as App #LightGreen {
  interface in as AppIn #Black
  interface out as AppOut #Black
}
FA6_VOLUME_HIGH(d1, "Your speaker")
MATERIAL_RECORD_VOICE_OVER(d2, "Incoming audio")
d2 --> MIn : original audio
MOut --> AppIn : VB-Audio\nHi-Fi Cable
AppOut --> d1 : translated audio
@enduml
```

#### ⚙️ Settings Configuration

**1. Inside Source App settings (Meeting App / Browser / Media Player):**

- **Speaker / Audio Output**: Select `HiFi Cable Input (VB-Audio Hi-Fi Cable)`.

**2. Inside LiveSpeech Translator:**

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

```plantuml
@startuml
!$ICONURL = "https://raw.githubusercontent.com/tupadr3/plantuml-icon-font-sprites/v3.0.0/icons"
!include $ICONURL/common.puml
!include $ICONURL/font-awesome-6/microphone.puml
!include $ICONURL/font-awesome-6/volume_high.puml
skinparam {
  ComponentStyle rectangle
  DefaultTextAlignment center
  backgroundColor White
}
left to right direction
component "LiveSpeech" as App #LightGreen {
  interface in as AppIn #Black
  interface out as AppOut #Black
}
component "Meeting App/\nBrowser" as M #LightBlue {
  interface out as MOut #Black
  interface in as MIn #Black
}
FA6_MICROPHONE(d1, "Your mic")
FA6_VOLUME_HIGH(d2, "Audience's\nSpeakers")
d1 --> AppIn : original audio
AppOut --> MIn : VB-Audio\nVirtual Cable
MOut --> d2 : translated audio  
@enduml
```

#### ⚙️ Settings Configuration

**1. Inside Your Meeting / Streaming App:**

- **Microphone**: Select `CABLE Output (VB-Audio Virtual Cable)`.

**2. Inside LiveSpeech Translator:**

| Setting | What to Select |
| :--- | :--- |
| **Input** | Your physical Microphone |
| **Output** | `CABLE Input (VB-Audio Virtual Cable)` |
| **Target Language** | The audience's language |

### Mode 3: Bidirectional (Live Meeting Mode)

Use this mode for **full two-way translation** in video meetings (Zoom, Microsoft Teams, Google Meet, Discord). You speak in your language and attendees hear translated speech; when they speak, you hear translated speech in your headphones.

#### Audio Routing Diagram (bidirectional mode)

```plantuml
@startuml
!$ICONURL = "https://raw.githubusercontent.com/tupadr3/plantuml-icon-font-sprites/v3.0.0/icons"
!include $ICONURL/common.puml
!include $ICONURL/font-awesome-6/microphone.puml
!include $ICONURL/font-awesome-6/volume_high.puml
!include $ICONURL/material/record_voice_over.puml
skinparam {
  ComponentStyle rectangle
  DefaultTextAlignment center
  backgroundColor White
}
left to right direction

rectangle "Incoming Flow (Audience Speaks -> You Hear)" as InSection #EFF6FF {
  MATERIAL_RECORD_VOICE_OVER(inc, "Incoming\naudio")
  component "Meeting App/\nBrowser" as M2 #LightBlue {
    interface in as MIn2 #Black
    interface out as MOut2 #Black
  }
  component "LiveSpeech" as App2 #LightGreen {
    interface out as AppOut2 #Black
    interface in as AppIn2 #Black
  }
  FA6_VOLUME_HIGH(spk, "Your speaker")
  inc --> MIn2 : original\nincoming audio
  MOut2 --> AppIn2 : VB-Audio\nHi-Fi Cable
  AppOut2 --> spk : translated\nincoming audio
}

rectangle "Outgoing Flow (You Speak -> Audience Hears)" as OutSection #F0FDF4 {
  FA6_MICROPHONE(mic, "Your mic")
  component "LiveSpeech" as App1 #LightGreen {
    interface in as AppIn1 #Black
    interface out as AppOut1 #Black
  }
  component "Meeting App/\nBrowser" as M1 #LightBlue {
    interface out as MOut1 #Black
    interface in as MIn1 #Black
  }
  FA6_VOLUME_HIGH(aud, "Audience's\nSpeakers")
  mic --> AppIn1 : original\noutgoing audio
  AppOut1 --> MIn1 : VB-Audio\nVirtual Cable
  MOut1 --> aud : translated\noutgoing audio
}

@enduml
```

#### ⚙️ Settings Configuration

**1. Inside LiveSpeech Translator:**

| Section | Setting | What to Select |
| :--- | :--- | :--- |
| **🎙️ Outgoing Translation** | **Input (Microphone)** | Your physical Microphone |
| | **Target Language** | Meeting attendees' language (e.g. `English`) |
| | **Output (Virtual Cable)** | `CABLE Input (VB-Audio Virtual Cable)` |
| **🎧 Incoming Translation** | **Input (Hi-Fi Cable)** | `HiFi Cable Output (VB-Audio Hi-Fi Cable)` |
| | **Target Language** | Your native language (e.g. `Finnish`, `Spanish`) |
| | **Output (Headphones)** | Your physical Headphones / Speakers |

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
pip install fastapi uvicorn pywebview google-genai pyaudio numpy pydantic langdetect pyinstaller

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
