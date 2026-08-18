/**
 * LiveSpeech Translator — Main UI Controller & WebSocket Client
 * Handles dual-channel device selection, session control, live transcription,
 * audio meters, mode switching, searchable language comboboxes, search with keyword highlighting, and TXT export.
 *
 * Supports bidirectional meeting translation with independent
 * outgoing (You → Meeting) and incoming (Meeting → You) channels.
 */

(() => {
  'use strict';

  // ── Constants ───────────────────────────────────────────────────

  const WS_URL = `ws://${location.host}/ws/live`;
  const API = `http://${location.host}/api`;

  // ── DOM References ──────────────────────────────────────────────

  const $ = (sel) => document.querySelector(sel);
  const statusBadge = $('#statusBadge');
  const statusText = statusBadge.querySelector('.status-text');
  const metricModel = $('#metricModel');
  const modelSeparator = $('#modelSeparator');
  const metricSession = $('#metricSession');
  const btnStartStop = $('#btnStartStop');
  const btnSettings = $('#btnSettings');
  const transcriptFeed = $('#transcriptFeed');
  const searchInput = $('#searchTranscripts');
  const autoScroll = $('#autoScroll');
  const btnClear = $('#btnClear');
  const btnExportTxt = $('#btnExportTxt');
  const settingsModal = $('#settingsModal');
  const btnCloseSettings = $('#btnCloseSettings');
  const apiKeyInput = $('#apiKeyInput');
  const btnToggleKey = $('#btnToggleKey');
  const btnResetKey = $('#btnResetKey');
  const apiKeyStatus = $('#apiKeyStatus');
  const btnTestConnection = $('#btnTestConnection');
  const btnDiscardSettings = $('#btnDiscardSettings');
  const btnSaveSettings = $('#btnSaveSettings');

  // Mode buttons
  const modeBtns = document.querySelectorAll('.mode-btn');

  // Channel cards
  const cardOutgoing = $('#cardOutgoing');
  const cardIncoming = $('#cardIncoming');

  // Outgoing channel controls
  const outgoingInputDevice = $('#outgoingInputDevice');
  const outgoingOutputDevice = $('#outgoingOutputDevice');
  const outgoingLangContainer = $('#outgoingLangContainer');
  const outgoingTargetLanguage = $('#outgoingTargetLanguage');
  const outgoingLangDropdown = $('#outgoingLangDropdown');
  const btnTestOutgoing = $('#btnTestOutgoing');
  const outgoingInputMeter = $('#outgoingInputMeter');
  const outgoingInputMeterVal = $('#outgoingInputMeterVal');
  const outgoingOutputMeter = $('#outgoingOutputMeter');
  const outgoingOutputMeterVal = $('#outgoingOutputMeterVal');

  // Incoming channel controls
  const incomingInputDevice = $('#incomingInputDevice');
  const incomingOutputDevice = $('#incomingOutputDevice');
  const incomingLangContainer = $('#incomingLangContainer');
  const incomingTargetLanguage = $('#incomingTargetLanguage');
  const incomingLangDropdown = $('#incomingLangDropdown');
  const btnTestIncoming = $('#btnTestIncoming');
  const incomingInputMeter = $('#incomingInputMeter');
  const incomingInputMeterVal = $('#incomingInputMeterVal');
  const incomingOutputMeter = $('#incomingOutputMeter');
  const incomingOutputMeterVal = $('#incomingOutputMeterVal');

  // ── State ───────────────────────────────────────────────────────

  let ws = null;
  let isStreaming = false;
  let sessionStartTime = null;
  let timerInterval = null;
  let languagesList = [];
  let currentMode = 'bidirectional';

  // Searchable language combobox instances
  let outgoingLangSelect = null;
  let incomingLangSelect = null;

  // Per-channel transcript accumulators
  const channelState = {
    outgoing: { currentText: '', currentOutputText: '', currentEntryEl: null },
    incoming: { currentText: '', currentOutputText: '', currentEntryEl: null },
  };
  let entryCount = 0;

  // ── Searchable Language Combobox Component ───────────────────────

  class SearchableLanguageSelect {
    constructor(containerEl, inputEl, dropdownEl, onChange) {
      this.container = containerEl;
      this.input = inputEl;
      this.dropdown = dropdownEl;
      this.onChange = onChange;
      this.languages = [];
      this.filteredLanguages = [];
      this.selectedCode = '';
      this.selectedName = '';
      this.isOpen = false;
      this.highlightedIndex = -1;

      this._bindEvents();
    }

    setLanguages(languages) {
      this.languages = languages || [];
      this.filteredLanguages = [...this.languages];
    }

    setValue(code) {
      const found = this.languages.find(l => l.code.toLowerCase() === (code || '').toLowerCase());
      if (found) {
        this.selectedCode = found.code;
        this.selectedName = found.name;
        this.input.value = found.name;
      } else if (code) {
        this.selectedCode = code;
        this.selectedName = code;
        this.input.value = code;
      } else {
        this.selectedCode = '';
        this.selectedName = '';
        this.input.value = '';
      }
    }

    getValue() {
      return this.selectedCode;
    }

    getName() {
      return this.selectedName;
    }

    setDisabled(disabled, title = '') {
      this.input.disabled = disabled;
      this.input.title = title;
      this.container.classList.toggle('disabled', disabled);
      if (disabled) {
        this.close();
      }
    }

    open() {
      if (this.input.disabled || this.isOpen) return;
      this.isOpen = true;
      this.container.classList.add('open');
      const card = this.container.closest('.channel-card');
      if (card) card.classList.add('active-select');

      // Show FULL list of languages when opening so user can choose freely
      this.filter('');

      // Highlight and scroll currently selected language into view
      if (this.selectedCode) {
        const selIdx = this.filteredLanguages.findIndex(l => l.code.toLowerCase() === this.selectedCode.toLowerCase());
        if (selIdx >= 0) {
          this.highlightedIndex = selIdx;
          this._updateHighlight();
        }
      }
    }

    close() {
      if (!this.isOpen) return;
      this.isOpen = false;
      this.container.classList.remove('open');
      const card = this.container.closest('.channel-card');
      if (card) card.classList.remove('active-select');
      this.highlightedIndex = -1;

      // Revert input text to valid selected name if user typed something unselected
      if (this.selectedName && this.input.value.trim() !== this.selectedName) {
        const exact = this.languages.find(l => l.name.toLowerCase() === this.input.value.trim().toLowerCase());
        if (exact) {
          this.select(exact.code);
        } else {
          this.input.value = this.selectedName;
        }
      }
    }

    filter(query) {
      const q = (query || '').trim().toLowerCase();
      if (!q) {
        this.filteredLanguages = [...this.languages];
      } else {
        this.filteredLanguages = this.languages.filter(l =>
          l.name.toLowerCase().includes(q) || l.code.toLowerCase().includes(q)
        );
      }
      this.highlightedIndex = this.filteredLanguages.length > 0 ? 0 : -1;
      this.render();
    }

    render() {
      this.dropdown.innerHTML = '';
      if (this.filteredLanguages.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'select-no-results';
        empty.textContent = 'No languages found';
        this.dropdown.appendChild(empty);
        return;
      }

      this.filteredLanguages.forEach((lang, idx) => {
        const opt = document.createElement('div');
        opt.className = 'select-option';
        if (lang.code.toLowerCase() === this.selectedCode.toLowerCase()) {
          opt.classList.add('selected');
        }
        if (idx === this.highlightedIndex) {
          opt.classList.add('highlighted');
        }
        opt.textContent = lang.name;
        opt.addEventListener('mousedown', (e) => {
          e.preventDefault(); // Prevent input blur before click fires
          this.select(lang.code);
        });
        this.dropdown.appendChild(opt);
      });
    }

    select(code) {
      this.setValue(code);
      this.close();
      if (this.onChange) {
        this.onChange(this.selectedCode);
      }
    }

    _bindEvents() {
      // Focus & Click: open full list and select text for fast replacement
      this.input.addEventListener('focus', () => {
        this.open();
        setTimeout(() => this.input.select(), 10);
      });

      this.input.addEventListener('click', () => {
        if (!this.isOpen) {
          this.open();
          this.input.select();
        }
      });

      // Arrow button toggle
      const arrow = this.container.querySelector('.select-arrow');
      if (arrow) {
        arrow.addEventListener('click', (e) => {
          e.stopPropagation();
          if (this.input.disabled) return;
          if (this.isOpen) {
            this.close();
          } else {
            this.input.focus();
          }
        });
      }

      // Live typing filters search
      this.input.addEventListener('input', () => {
        if (!this.isOpen) {
          this.isOpen = true;
          this.container.classList.add('open');
          const card = this.container.closest('.channel-card');
          if (card) card.classList.add('active-select');
        }
        this.filter(this.input.value);
      });

      // Keyboard navigation
      this.input.addEventListener('keydown', (e) => {
        if (!this.isOpen) {
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter') {
            this.open();
            e.preventDefault();
          }
          return;
        }

        if (e.key === 'ArrowDown') {
          e.preventDefault();
          if (this.filteredLanguages.length > 0) {
            this.highlightedIndex = (this.highlightedIndex + 1) % this.filteredLanguages.length;
            this._updateHighlight();
          }
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          if (this.filteredLanguages.length > 0) {
            this.highlightedIndex = (this.highlightedIndex - 1 + this.filteredLanguages.length) % this.filteredLanguages.length;
            this._updateHighlight();
          }
        } else if (e.key === 'Enter') {
          e.preventDefault();
          if (this.highlightedIndex >= 0 && this.highlightedIndex < this.filteredLanguages.length) {
            this.select(this.filteredLanguages[this.highlightedIndex].code);
          } else if (this.filteredLanguages.length > 0) {
            this.select(this.filteredLanguages[0].code);
          } else {
            this.close();
          }
        } else if (e.key === 'Escape' || e.key === 'Tab') {
          this.close();
        }
      });

      this.input.addEventListener('blur', () => {
        setTimeout(() => this.close(), 150);
      });
    }

    _updateHighlight() {
      const opts = this.dropdown.querySelectorAll('.select-option');
      opts.forEach((opt, idx) => {
        opt.classList.toggle('highlighted', idx === this.highlightedIndex);
        if (idx === this.highlightedIndex) {
          opt.scrollIntoView({ block: 'nearest' });
        }
      });
    }
  }

  // ── Language & Tag Helpers ──────────────────────────────────────

  function getLanguageDisplayName(code) {
    const found = languagesList.find(l => l.code.toLowerCase() === (code || '').toLowerCase());
    return found ? found.name : (code ? code.toUpperCase() : '');
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function highlightText(plainText, query) {
    if (!plainText) return '';
    const safeText = escapeHtml(plainText);
    if (!query || !query.trim()) {
      return safeText;
    }
    const escapedQuery = escapeHtml(query.trim()).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escapedQuery})`, 'gi');
    return safeText.replace(regex, '<mark class="search-highlight">$1</mark>');
  }

  function renderEntryText(entry) {
    if (!entry) return;
    const query = searchInput ? searchInput.value : '';
    const rawSrc = entry.dataset.rawSource || '';
    const rawTrans = entry.dataset.rawTranslation || '';
    const srcEl = entry.querySelector('.source-text');
    const transEl = entry.querySelector('.translation-text');
    if (srcEl) srcEl.innerHTML = highlightText(rawSrc, query);
    if (transEl) transEl.innerHTML = highlightText(rawTrans, query);
  }

  function detectTextLanguage(text) {
    if (!text || !text.trim()) return null;
    const clean = text.trim();
    if (/[\u0400-\u04FF]/.test(clean)) {
      if (/[ієїґ]/.test(clean)) return 'uk';
      return 'ru';
    }
    if (/[\u4e00-\u9fff]/.test(clean)) return 'zh-Hans';
    if (/[\u3040-\u30ff]/.test(clean)) return 'ja';
    if (/[\uac00-\ud7af]/.test(clean)) return 'ko';
    if (/[\u0600-\u06FF]/.test(clean)) return 'ar';
    if (/[\u0590-\u05FF]/.test(clean)) return 'he';
    if (/[\u0900-\u097F]/.test(clean)) return 'hi';
    if (/[\u0E00-\u0E7F]/.test(clean)) return 'th';
    if (/[\u0370-\u03FF]/.test(clean)) return 'el';

    const lower = clean.toLowerCase();
    if (/\b(the|is|are|and|you|this|that|with|have|for|what|how|why|where|when|from|today)\b/i.test(lower)) return 'en';
    if (/\b(le|la|les|est|sont|et|vous|avec|pour|dans|que|qui|bonjour|merci|oui|non)\b/i.test(lower)) return 'fr';
    if (/\b(el|la|los|las|es|son|y|usted|con|para|por|que|hola|gracias|buenos|dias)\b/i.test(lower)) return 'es';
    if (/\b(der|die|das|ist|sind|und|sie|mit|für|nicht|wie|guten|morgen|tag|danke|bitte)\b/i.test(lower)) return 'de';
    if (/\b(il|la|lo|sono|è|ed|con|per|non|che|come|ciao|grazie|buongiorno)\b/i.test(lower)) return 'it';
    if (/\b(o|a|os|as|é|são|com|para|por|que|obrigado|bom|dia|ola)\b/i.test(lower)) return 'pt-BR';
    return null;
  }

  // ── Initialize ──────────────────────────────────────────────────

  async function init() {
    initComboboxes();
    await loadDevices();
    await loadLanguages();
    await loadConfig();
    connectWebSocket();
    bindEvents();
  }

  function initComboboxes() {
    outgoingLangSelect = new SearchableLanguageSelect(
      outgoingLangContainer,
      outgoingTargetLanguage,
      outgoingLangDropdown,
      async (code) => {
        if (isStreaming) return;
        await fetch(`${API}/config`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ outgoing: { target_language: code } }),
        });
      }
    );

    incomingLangSelect = new SearchableLanguageSelect(
      incomingLangContainer,
      incomingTargetLanguage,
      incomingLangDropdown,
      async (code) => {
        if (isStreaming) return;
        await fetch(`${API}/config`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ incoming: { target_language: code } }),
        });
      }
    );
  }

  // ── Data Loaders ────────────────────────────────────────────────

  async function loadDevices() {
    try {
      const res = await fetch(`${API}/devices`);
      const data = await res.json();

      // Populate all input selectors
      [outgoingInputDevice, incomingInputDevice].forEach(sel => {
        sel.innerHTML = '';
        data.inputs.forEach(d => {
          const opt = document.createElement('option');
          opt.value = d.index;
          opt.textContent = d.name;
          if (d.index === data.default_input) opt.selected = true;
          sel.appendChild(opt);
        });
      });

      // Populate all output selectors
      [outgoingOutputDevice, incomingOutputDevice].forEach(sel => {
        sel.innerHTML = '';
        data.outputs.forEach(d => {
          const opt = document.createElement('option');
          opt.value = d.index;
          opt.textContent = d.name;
          if (d.index === data.default_output) opt.selected = true;
          sel.appendChild(opt);
        });
      });
    } catch (e) {
      console.error('Failed to load devices:', e);
    }
  }

  async function loadLanguages() {
    try {
      const res = await fetch(`${API}/languages`);
      const data = await res.json();
      languagesList = data.languages || [];

      if (outgoingLangSelect) outgoingLangSelect.setLanguages(languagesList);
      if (incomingLangSelect) incomingLangSelect.setLanguages(languagesList);

      // Defaults
      outgoingLangSelect.setValue('en');
      incomingLangSelect.setValue('ru');
    } catch (e) {
      console.error('Failed to load languages:', e);
    }
  }

  async function loadConfig() {
    try {
      const res = await fetch(`${API}/config`);
      const config = await res.json();

      // Mode
      if (config.mode) {
        setMode(config.mode, false);
      } else {
        setMode('bidirectional', false);
      }

      // Outgoing channel
      const out = config.outgoing || {};
      if (out.input_device_index != null) outgoingInputDevice.value = out.input_device_index;
      if (out.output_device_index != null) outgoingOutputDevice.value = out.output_device_index;
      if (out.target_language && outgoingLangSelect) outgoingLangSelect.setValue(out.target_language);

      // Incoming channel
      const inc = config.incoming || {};
      if (inc.input_device_index != null) incomingInputDevice.value = inc.input_device_index;
      if (inc.output_device_index != null) incomingOutputDevice.value = inc.output_device_index;
      if (inc.target_language && incomingLangSelect) incomingLangSelect.setValue(inc.target_language);

      // API key status
      if (config.has_api_key) {
        apiKeyInput.value = '';
        apiKeyInput.placeholder = config.api_key_masked || '••••••••';
        apiKeyStatus.textContent = 'API Key configured';
        apiKeyStatus.className = 'setting-hint valid';
      } else {
        apiKeyInput.value = '';
        apiKeyInput.placeholder = 'Enter your Gemini API Key';
        apiKeyStatus.textContent = '⚠️ No API Key set';
        apiKeyStatus.className = 'setting-hint invalid';
      }
    } catch (e) {
      console.error('Failed to load config:', e);
    }
  }

  function showModelBadge(visible) {
    if (metricModel) metricModel.style.display = visible ? 'inline' : 'none';
    if (modelSeparator) modelSeparator.style.display = visible ? 'inline' : 'none';
  }

  // ── Mode Management ────────────────────────────────────────────

  function setMode(mode, persist = true) {
    currentMode = mode;

    modeBtns.forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });

    // Show/hide channel cards based on mode
    cardOutgoing.classList.toggle('hidden', mode === 'incoming');
    cardIncoming.classList.toggle('hidden', mode === 'outgoing');

    // In bidirectional mode, hide Test button on Outgoing (Virtual Cable); in outgoing-only, show it
    if (btnTestOutgoing) {
      btnTestOutgoing.style.display = (mode === 'outgoing' ? '' : 'none');
    }

    if (persist) {
      fetch(`${API}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
    }
  }

  // ── WebSocket Connection ────────────────────────────────────────

  function connectWebSocket() {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      handleWsEvent(msg.event, msg.data);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected, reconnecting in 2s...');
      setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
    };
  }

  function handleWsEvent(event, data) {
    switch (event) {
      case 'status':
        handleStatusChange(data.state, data.detail, data.channel);
        break;

      case 'input_transcript':
        appendInputTranscript(data.text, data.time, data.lang, data.channel || 'outgoing');
        break;

      case 'output_transcript':
        appendOutputTranscript(data.text, data.time, data.channel || 'outgoing');
        break;

      case 'audio_level':
        handleAudioLevel(data.channel || 'outgoing', data.source, data.level);
        break;

      case 'transcript_cleared':
        clearTranscriptUI();
        break;

      case 'pong':
        break;
    }
  }

  // ── Audio Level Routing ────────────────────────────────────────

  function handleAudioLevel(channel, source, level) {
    if (channel === 'outgoing') {
      if (source === 'input') {
        setMeter(outgoingInputMeter, outgoingInputMeterVal, level);
      } else {
        setMeter(outgoingOutputMeter, outgoingOutputMeterVal, level);
      }
    } else if (channel === 'incoming') {
      if (source === 'input') {
        setMeter(incomingInputMeter, incomingInputMeterVal, level);
      } else {
        setMeter(incomingOutputMeter, incomingOutputMeterVal, level);
      }
    }
  }

  // ── Status Handling ─────────────────────────────────────

  function handleStatusChange(state, detail, channel) {
    // For per-channel status updates, log errors if significant
    if (channel && channel !== 'all') {
      if (state === 'error') {
        renderErrorMessage(`[${channel.toUpperCase()}] ${detail}`);
      }
      return;
    }

    statusBadge.className = 'status-badge';
    switch (state) {
      case 'connecting':
        statusBadge.classList.add('connecting');
        statusText.textContent = 'Connecting...';
        showModelBadge(false);
        setLanguageSelectorsDisabled(true);
        break;
      case 'connected':
        statusBadge.classList.add('live');
        statusText.textContent = 'LIVE';
        isStreaming = true;
        setLanguageSelectorsDisabled(true);
        updateStartStopBtn();
        startTimer();
        showModelBadge(true);
        break;
      case 'disconnected':
      case 'stopped':
        statusText.textContent = 'Ready';
        isStreaming = false;
        setLanguageSelectorsDisabled(false);
        updateStartStopBtn();
        stopTimer();
        resetMeters();
        finalizeAllEntries();
        showModelBadge(false);
        break;
      case 'error':
        statusBadge.classList.add('error');
        statusText.textContent = detail && detail.includes('exhausted') ? 'Quota Exceeded' : 'Error';
        statusBadge.title = detail || 'An error occurred';
        isStreaming = false;
        setLanguageSelectorsDisabled(false);
        updateStartStopBtn();
        stopTimer();
        resetMeters();
        showModelBadge(false);
        renderErrorMessage(detail || 'Connection error');
        break;
    }
  }

  function setLanguageSelectorsDisabled(disabled) {
    const title = disabled ? 'Cannot change language while streaming' : '';
    if (outgoingLangSelect) outgoingLangSelect.setDisabled(disabled, title);
    if (incomingLangSelect) incomingLangSelect.setDisabled(disabled, title);
  }

  function updateStartStopBtn() {
    const icon = btnStartStop.querySelector('.btn-icon-inner');
    const label = btnStartStop.querySelector('.btn-label');

    if (isStreaming) {
      icon.textContent = '■';
      label.textContent = 'Stop Streaming';
      btnStartStop.classList.add('streaming');
    } else {
      icon.textContent = '▶';
      label.textContent = 'Start Streaming';
      btnStartStop.classList.remove('streaming');
    }
  }

  // ── Session Timer ───────────────────────────────────────────────

  function startTimer() {
    sessionStartTime = Date.now();
    timerInterval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - sessionStartTime) / 1000);
      const h = String(Math.floor(elapsed / 3600)).padStart(2, '0');
      const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0');
      const s = String(elapsed % 60).padStart(2, '0');
      metricSession.textContent = `Session: ${h}:${m}:${s}`;
    }, 1000);
  }

  function stopTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
    metricSession.textContent = 'Session: 00:00:00';
  }

  // ── Audio Meters ────────────────────────────────────────────────

  function setMeter(meterEl, valEl, level) {
    const pct = Math.min(100, Math.max(0, Math.round(level * 100)));
    meterEl.style.width = `${pct}%`;
    valEl.textContent = `${pct}%`;
  }

  function resetMeters() {
    [outgoingInputMeter, outgoingOutputMeter, incomingInputMeter, incomingOutputMeter].forEach(m => {
      m.style.width = '0%';
    });
    [outgoingInputMeterVal, outgoingOutputMeterVal, incomingInputMeterVal, incomingOutputMeterVal].forEach(v => {
      v.textContent = '0%';
    });
  }

  // ── Transcript Feed ─────────────────────────────────────────────

  function removePlaceholder() {
    const ph = transcriptFeed.querySelector('.transcript-placeholder');
    if (ph) ph.remove();
  }

  function ensureCurrentEntry(channel, timestamp) {
    removePlaceholder();
    const state = channelState[channel];
    if (!state) return null;

    if (!state.currentEntryEl) {
      entryCount++;
      const time = timestamp
        ? new Date(timestamp * 1000).toLocaleTimeString('en-US', { hour12: false })
        : new Date().toLocaleTimeString('en-US', { hour12: false });

      const isOutgoing = channel === 'outgoing';
      const channelLabel = isOutgoing ? 'YOU' : 'MEETING';
      const channelIcon = isOutgoing ? '🎙️' : '🎧';
      const targetLang = isOutgoing
        ? (outgoingLangSelect ? outgoingLangSelect.getValue() || 'en' : 'en').toUpperCase()
        : (incomingLangSelect ? incomingLangSelect.getValue() || 'ru' : 'ru').toUpperCase();

      state.currentEntryEl = document.createElement('div');
      state.currentEntryEl.className = `transcript-entry channel-${channel}`;
      state.currentEntryEl.dataset.id = entryCount;
      state.currentEntryEl.dataset.channel = channel;
      state.currentEntryEl.dataset.srcTag = '[AUTO]:';
      state.currentEntryEl.dataset.tgtTag = `[${targetLang}]:`;
      state.currentEntryEl.dataset.rawSource = '';
      state.currentEntryEl.dataset.rawTranslation = '';
      state.currentEntryEl.innerHTML = `
        <div class="transcript-time">[${time}]</div>
        <div class="transcript-channel-badge channel-badge-${channel}">
          ${channelIcon} ${channelLabel}
        </div>
        <div class="transcript-source">
          <span class="label">[AUTO]:</span>
          <span class="source-text"></span>
        </div>
        <div class="transcript-translation">
          <span class="label"><span class="speaker-icon">🔊</span> [${targetLang}]:</span>
          <span class="translation-text"></span><span class="typing-cursor"></span>
        </div>
      `;
      transcriptFeed.appendChild(state.currentEntryEl);
      state.currentText = '';
      state.currentOutputText = '';

      // Check search match for newly created entry
      const q = (searchInput.value || '').trim().toLowerCase();
      if (q) {
        state.currentEntryEl.style.display = time.toLowerCase().includes(q) ? '' : 'none';
      }
    }
    return state.currentEntryEl;
  }

  function appendInputTranscript(text, timestamp, serverLang, channel) {
    const entry = ensureCurrentEntry(channel, timestamp);
    if (!entry) return;
    const state = channelState[channel];
    state.currentText += text;
    entry.dataset.rawSource = state.currentText;

    const detectedCode = serverLang || detectTextLanguage(state.currentText);
    if (detectedCode) {
      const srcTag = `[${detectedCode.toUpperCase()}]:`;
      entry.dataset.srcTag = srcTag;
      const labelEl = entry.querySelector('.transcript-source .label');
      if (labelEl) labelEl.textContent = srcTag;
    }

    renderEntryText(entry);

    // Apply search filter if active
    const q = (searchInput.value || '').trim().toLowerCase();
    if (q) {
      const rawSrc = (entry.dataset.rawSource || '').toLowerCase();
      const rawTrans = (entry.dataset.rawTranslation || '').toLowerCase();
      entry.style.display = (rawSrc.includes(q) || rawTrans.includes(q)) ? '' : 'none';
    }

    maybeAutoScroll();
  }

  function appendOutputTranscript(text, timestamp, channel) {
    const entry = ensureCurrentEntry(channel, timestamp);
    if (!entry) return;
    const state = channelState[channel];
    state.currentOutputText += text;
    entry.dataset.rawTranslation = state.currentOutputText;

    renderEntryText(entry);

    // Apply search filter if active
    const q = (searchInput.value || '').trim().toLowerCase();
    if (q) {
      const rawSrc = (entry.dataset.rawSource || '').toLowerCase();
      const rawTrans = (entry.dataset.rawTranslation || '').toLowerCase();
      entry.style.display = (rawSrc.includes(q) || rawTrans.includes(q)) ? '' : 'none';
    }

    maybeAutoScroll();

    if (text.trimEnd().match(/[.?!]$/)) {
      finalizeEntry(channel);
    }
  }

  function finalizeEntry(channel) {
    const state = channelState[channel];
    if (state && state.currentEntryEl) {
      const cursor = state.currentEntryEl.querySelector('.typing-cursor');
      if (cursor) cursor.remove();
      state.currentEntryEl = null;
      state.currentText = '';
      state.currentOutputText = '';
    }
  }

  function finalizeAllEntries() {
    finalizeEntry('outgoing');
    finalizeEntry('incoming');
  }

  function clearTranscriptUI() {
    transcriptFeed.innerHTML = `
      <div class="transcript-placeholder">
        <span class="placeholder-icon">🎧</span>
        <p>Press <strong>Start Streaming</strong> to begin live translation.</p>
        <p class="placeholder-sub">Audio will play through your selected output devices.</p>
      </div>
    `;
    channelState.outgoing = { currentText: '', currentOutputText: '', currentEntryEl: null };
    channelState.incoming = { currentText: '', currentOutputText: '', currentEntryEl: null };
    entryCount = 0;
  }

  function maybeAutoScroll() {
    if (autoScroll.checked) {
      transcriptFeed.scrollTop = transcriptFeed.scrollHeight;
    }
  }

  function renderErrorMessage(msg) {
    const errDiv = document.createElement('div');
    errDiv.className = 'transcript-entry';
    errDiv.dataset.channel = 'system';
    errDiv.innerHTML = `
      <div class="transcript-time" style="color: #ef4444; font-weight: 600;">⚠️ SYSTEM NOTICE</div>
      <div class="transcript-translation" style="color: #fca5a5; font-size: 13px;">${msg}</div>
    `;
    transcriptFeed.appendChild(errDiv);
    maybeAutoScroll();
  }

  // ── Search & Highlight Engine ─────────────────────────────────

  function filterTranscripts(query) {
    const entries = transcriptFeed.querySelectorAll('.transcript-entry');
    const q = (query || '').trim().toLowerCase();

    entries.forEach(entry => {
      const isSystem = entry.dataset.channel === 'system';
      if (isSystem) {
        entry.style.display = '';
        return;
      }

      const rawSrc = (entry.dataset.rawSource || '').toLowerCase();
      const rawTrans = (entry.dataset.rawTranslation || '').toLowerCase();
      const time = (entry.querySelector('.transcript-time')?.textContent || '').toLowerCase();

      const matches = !q || rawSrc.includes(q) || rawTrans.includes(q) || time.includes(q);
      entry.style.display = matches ? '' : 'none';

      // Update highlight mark tags
      renderEntryText(entry);
    });
  }

  // ── Export ─────────────────────────────────────────────────────

  async function exportTxt() {
    try {
      const entryEls = transcriptFeed.querySelectorAll('.transcript-entry');
      if (!entryEls || entryEls.length === 0) {
        alert('No transcripts to export.');
        return;
      }

      const now = new Date();
      const pad = (n) => String(n).padStart(2, '0');
      const formattedDate = `${pad(now.getDate())}.${pad(now.getMonth() + 1)}.${now.getFullYear()}`;
      const formattedTime = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;

      let content = 'LiveSpeech Translator Transcript\n' + '═'.repeat(50) + '\n';
      content += `Mode: ${currentMode}\n`;
      content += `Outgoing Language: ${getLanguageDisplayName(outgoingLangSelect ? outgoingLangSelect.getValue() : 'en')}\n`;
      content += `Incoming Language: ${getLanguageDisplayName(incomingLangSelect ? incomingLangSelect.getValue() : 'ru')}\n`;
      content += `Export Date: ${formattedDate} ${formattedTime}\n`;
      content += '═'.repeat(50) + '\n\n';

      let count = 0;

      entryEls.forEach(entry => {
        const timeEl = entry.querySelector('.transcript-time');
        if (timeEl && timeEl.textContent.includes('SYSTEM NOTICE')) return;

        const rawSrc = (entry.dataset.rawSource || '').trim();
        const rawTrans = (entry.dataset.rawTranslation || '').trim();
        const channel = entry.dataset.channel || 'outgoing';

        if (!rawSrc && !rawTrans) return;

        const time = timeEl ? timeEl.textContent.trim() : '';
        const speakerTag = channel === 'incoming' ? '[MEETING' : '[YOU';
        const srcTag = entry.dataset.srcTag || '[AUTO]:';
        const tgtTag = entry.dataset.tgtTag || '[EN]:';

        count++;
        if (time) content += `${time}\n`;
        if (rawSrc) content += `${speakerTag} → ${tgtTag.replace(':', '').replace('[', '').replace(']', '')}] ${srcTag} ${rawSrc}\n`;
        if (rawTrans) content += `${speakerTag} → ${tgtTag.replace(':', '').replace('[', '').replace(']', '')}] ${tgtTag} ${rawTrans}\n`;
        content += '\n';
      });

      if (count === 0) {
        alert('No transcript entries found to export.');
        return;
      }

      const timestamp = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}_${pad(now.getHours())}-${pad(now.getMinutes())}-${pad(now.getSeconds())}`;
      const suggestedName = `livespeech-transcript-${timestamp}.txt`;

      if (window.showSaveFilePicker) {
        try {
          const handle = await window.showSaveFilePicker({
            suggestedName: suggestedName,
            types: [{ description: 'Text Document (*.txt)', accept: { 'text/plain': ['.txt'] } }]
          });
          const writable = await handle.createWritable();
          await writable.write(content);
          await writable.close();
          return;
        } catch (err) {
          if (err.name === 'AbortError') return;
          console.warn('Native picker failed, using download fallback:', err);
        }
      }

      const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = suggestedName;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Export failed:', e);
    }
  }

  // ── Session Control ───────────────────────────────────────────

  async function startSession() {
    setLanguageSelectorsDisabled(true);
    try {
      // Persist current device + language config before starting
      await fetch(`${API}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: currentMode,
          outgoing: {
            input_device_index: parseInt(outgoingInputDevice.value),
            output_device_index: parseInt(outgoingOutputDevice.value),
            target_language: outgoingLangSelect ? outgoingLangSelect.getValue() || 'en' : 'en',
          },
          incoming: {
            input_device_index: parseInt(incomingInputDevice.value),
            output_device_index: parseInt(incomingOutputDevice.value),
            target_language: incomingLangSelect ? incomingLangSelect.getValue() || 'ru' : 'ru',
          },
        }),
      });

      const res = await fetch(`${API}/session/start`, { method: 'POST' });
      const data = await res.json();
      if (data.status === 'error') {
        alert(`Error: ${data.detail}`);
        if (!isStreaming) {
          setLanguageSelectorsDisabled(false);
        }
      } else if (data.status === 'started') {
        handleStatusChange('connected', `Channels: ${(data.channels || []).join(', ')}`, 'all');
      }
    } catch (e) {
      console.error('Failed to start session:', e);
      if (!isStreaming) {
        setLanguageSelectorsDisabled(false);
      }
    }
  }

  async function stopSession() {
    await fetch(`${API}/session/stop`, { method: 'POST' });
  }

  // ── Settings Modal ────────────────────────────────────────────

  async function openSettings() {
    await loadConfig();
    settingsModal.classList.add('open');
  }

  function closeSettings() {
    settingsModal.classList.remove('open');
  }

  async function saveSettings() {
    const body = {};
    if (apiKeyInput.value.trim()) {
      body.api_key = apiKeyInput.value.trim();
    }

    await fetch(`${API}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    await loadConfig();
    closeSettings();
  }

  async function resetApiKey() {
    try {
      await fetch(`${API}/config/reset-key`, { method: 'POST' });
      await loadConfig();
      showModelBadge(false);
    } catch (e) {
      console.error('Failed to reset API key:', e);
    }
  }

  async function testConnection() {
    btnTestConnection.textContent = '⏳ Testing...';
    try {
      if (apiKeyInput.value.trim()) {
        await fetch(`${API}/config`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ api_key: apiKeyInput.value.trim() }),
        });
      }
      const res = await fetch(`${API}/status`);
      const configRes = await fetch(`${API}/config`);
      const configData = await configRes.json();
      if (res.ok && configData.has_api_key) {
        btnTestConnection.textContent = '✅ Connected';
        showModelBadge(true);
        apiKeyStatus.textContent = 'API Key configured';
        apiKeyStatus.className = 'setting-hint valid';
        if (configData.api_key_masked) {
          apiKeyInput.value = '';
          apiKeyInput.placeholder = configData.api_key_masked;
        }
      } else {
        btnTestConnection.textContent = '❌ Key Missing';
        apiKeyStatus.textContent = '⚠️ No API Key set';
        apiKeyStatus.className = 'setting-hint invalid';
      }
    } catch (e) {
      btnTestConnection.textContent = '❌ Failed';
      apiKeyStatus.textContent = '❌ Connection failed';
      apiKeyStatus.className = 'setting-hint invalid';
    }
    setTimeout(() => {
      btnTestConnection.textContent = '🔄 Test Connection';
    }, 2500);
  }

  // ── Event Bindings ────────────────────────────────────

  function bindEvents() {
    // Start/Stop
    btnStartStop.addEventListener('click', () => {
      if (isStreaming) stopSession();
      else startSession();
    });

    // Mode switching
    modeBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        if (isStreaming) return; // Don't switch mode while streaming
        setMode(btn.dataset.mode);
      });
    });

    // Outgoing device changes
    outgoingInputDevice.addEventListener('change', async () => {
      await fetch(`${API}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ outgoing: { input_device_index: parseInt(outgoingInputDevice.value) } }),
      });
    });
    outgoingOutputDevice.addEventListener('change', async () => {
      await fetch(`${API}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ outgoing: { output_device_index: parseInt(outgoingOutputDevice.value) } }),
      });
    });

    // Incoming device changes
    incomingInputDevice.addEventListener('change', async () => {
      await fetch(`${API}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ incoming: { input_device_index: parseInt(incomingInputDevice.value) } }),
      });
    });
    incomingOutputDevice.addEventListener('change', async () => {
      await fetch(`${API}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ incoming: { output_device_index: parseInt(incomingOutputDevice.value) } }),
      });
    });

    // Test sound buttons
    btnTestOutgoing.addEventListener('click', async () => {
      const original = btnTestOutgoing.textContent;
      btnTestOutgoing.textContent = '⏳ Playing...';
      btnTestOutgoing.disabled = true;
      try {
        await fetch(`${API}/audio/test-output`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ device_index: parseInt(outgoingOutputDevice.value) }),
        });
      } catch (e) { console.error('Test sound failed:', e); }
      finally {
        setTimeout(() => { btnTestOutgoing.textContent = original; btnTestOutgoing.disabled = false; }, 500);
      }
    });

    btnTestIncoming.addEventListener('click', async () => {
      const original = btnTestIncoming.textContent;
      btnTestIncoming.textContent = '⏳ Playing...';
      btnTestIncoming.disabled = true;
      try {
        await fetch(`${API}/audio/test-output`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ device_index: parseInt(incomingOutputDevice.value) }),
        });
      } catch (e) { console.error('Test sound failed:', e); }
      finally {
        setTimeout(() => { btnTestIncoming.textContent = original; btnTestIncoming.disabled = false; }, 500);
      }
    });

    // Settings
    btnSettings.addEventListener('click', openSettings);
    btnCloseSettings.addEventListener('click', closeSettings);
    btnDiscardSettings.addEventListener('click', closeSettings);
    btnSaveSettings.addEventListener('click', saveSettings);
    btnTestConnection.addEventListener('click', testConnection);

    btnToggleKey.addEventListener('click', () => {
      apiKeyInput.type = apiKeyInput.type === 'password' ? 'text' : 'password';
    });

    btnResetKey.addEventListener('click', resetApiKey);

    btnClear.addEventListener('click', async () => {
      await fetch(`${API}/transcript/clear`, { method: 'POST' });
    });

    btnExportTxt.addEventListener('click', exportTxt);

    searchInput.addEventListener('input', () => {
      filterTranscripts(searchInput.value);
    });

    // Close modal on backdrop click
    settingsModal.addEventListener('click', (e) => {
      if (e.target === settingsModal) closeSettings();
    });

    // Keyboard shortcut: Space to toggle streaming (when not in input)
    document.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
      if (e.code === 'Space') {
        e.preventDefault();
        if (isStreaming) stopSession();
        else startSession();
      }
    });
  }

  // ── Boot ──────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', init);
})();
