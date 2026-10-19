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
  const mainContent = $('.main-content');
  const transcriptSection = $('#transcriptSection');
  const btnMaximizeTranscript = $('#btnMaximizeTranscript');
  const btnScrollTop = $('#btnScrollTop');
  const btnScrollBottom = $('#btnScrollBottom');
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
  let suggestedDevices = {};

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
    const query = searchInput ? searchInput.value.trim() : '';
    const rawSrc = entry.dataset.rawSource || '';
    const rawTrans = entry.dataset.rawTranslation || '';
    const srcEl = entry.querySelector('.source-text');
    const transEl = entry.querySelector('.translation-text');

    // Fast path: when no search filter is active, mutate textContent directly
    // to bypass HTML escaping, regex allocation, and DOM parser churn.
    if (!query) {
      if (srcEl) srcEl.textContent = rawSrc;
      if (transEl) transEl.textContent = rawTrans;
      return;
    }

    if (srcEl) srcEl.innerHTML = highlightText(rawSrc, query);
    if (transEl) transEl.innerHTML = highlightText(rawTrans, query);
  }

  // ── Initialize ──────────────────────────────────────────────────

  async function init() {
    initComboboxes();
    await loadDevices();
    await loadLanguages();
    await loadConfig();
    await loadTranscriptsFromServer();
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
      suggestedDevices = data.suggested || {};

      const sortedInputs = [...(data.inputs || [])].sort((a, b) =>
        (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base', numeric: true })
      );
      const sortedOutputs = [...(data.outputs || [])].sort((a, b) =>
        (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base', numeric: true })
      );

      // Populate all input selectors
      [outgoingInputDevice, incomingInputDevice].forEach(sel => {
        sel.innerHTML = '';
        sortedInputs.forEach(d => {
          const opt = document.createElement('option');
          opt.value = d.index;
          opt.textContent = d.name;
          sel.appendChild(opt);
        });
      });

      // Populate all output selectors
      [outgoingOutputDevice, incomingOutputDevice].forEach(sel => {
        sel.innerHTML = '';
        sortedOutputs.forEach(d => {
          const opt = document.createElement('option');
          opt.value = d.index;
          opt.textContent = d.name;
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

  function selectDeviceBySavedConfig(selectEl, savedIndex, savedName, suggestedIndex, isMic = false) {
    if (!selectEl || selectEl.options.length === 0) return;

    const isStereoMix = (str) => {
      const s = (str || '').toLowerCase();
      return s.includes('стерео микшер') || s.includes('stereo mix') || s.includes('stereo mixer');
    };

    const isCable = (str) => {
      const s = (str || '').toLowerCase();
      return s.includes('cable') || s.includes('vb-audio');
    };

    // 1. Try to match by device name (resilient to USB plug/unplug index shifts)
    if (savedName && typeof savedName === 'string' && savedName.trim()) {
      const savedLower = savedName.trim().toLowerCase();
      for (let i = 0; i < selectEl.options.length; i++) {
        if (selectEl.options[i].textContent.trim().toLowerCase() === savedLower) {
          selectEl.selectedIndex = i;
          return;
        }
      }
      for (let i = 0; i < selectEl.options.length; i++) {
        const optLower = selectEl.options[i].textContent.trim().toLowerCase();
        if (optLower.includes(savedLower) || savedLower.includes(optLower)) {
          selectEl.selectedIndex = i;
          return;
        }
      }
      // If savedName was set but not found, device is currently unplugged.
      // Do NOT fall back to savedIndex, proceed directly to suggestedIndex.
    } else if (savedIndex != null) {
      // 2. Legacy fallback only if savedName was not set
      for (let i = 0; i < selectEl.options.length; i++) {
        if (parseInt(selectEl.options[i].value) === savedIndex) {
          const optText = selectEl.options[i].textContent;
          if (isMic && (isStereoMix(optText) || isCable(optText))) {
            break; // Skip to suggestedIndex for microphone
          }
          selectEl.selectedIndex = i;
          return;
        }
      }
    }

    // 3. Fallback to smart suggested index
    if (suggestedIndex != null) {
      for (let i = 0; i < selectEl.options.length; i++) {
        if (parseInt(selectEl.options[i].value) === suggestedIndex) {
          selectEl.selectedIndex = i;
          return;
        }
      }
    }

    // 4. Default to first valid option
    if (isMic) {
      for (let i = 0; i < selectEl.options.length; i++) {
        const optText = selectEl.options[i].textContent;
        if (!isStereoMix(optText) && !isCable(optText)) {
          selectEl.selectedIndex = i;
          return;
        }
      }
    }
    selectEl.selectedIndex = 0;
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
      selectDeviceBySavedConfig(outgoingInputDevice, out.input_device_index, out.input_device_name, suggestedDevices.outgoing_input, true);
      selectDeviceBySavedConfig(outgoingOutputDevice, out.output_device_index, out.output_device_name, suggestedDevices.outgoing_output, false);
      if (out.target_language && outgoingLangSelect) outgoingLangSelect.setValue(out.target_language);

      // Incoming channel
      const inc = config.incoming || {};
      selectDeviceBySavedConfig(incomingInputDevice, inc.input_device_index, inc.input_device_name, suggestedDevices.incoming_input, false);
      selectDeviceBySavedConfig(incomingOutputDevice, inc.output_device_index, inc.output_device_name, suggestedDevices.incoming_output, false);
      if (inc.target_language && incomingLangSelect) incomingLangSelect.setValue(inc.target_language);

      // Only if config was completely uninitialized (first run without any device config), save initial choices
      if (!out.input_device_name && !out.output_device_name && !inc.input_device_name && !inc.output_device_name) {
        const outInOpt = outgoingInputDevice.options[outgoingInputDevice.selectedIndex];
        const outOutOpt = outgoingOutputDevice.options[outgoingOutputDevice.selectedIndex];
        const incInOpt = incomingInputDevice.options[incomingInputDevice.selectedIndex];
        const incOutOpt = incomingOutputDevice.options[incomingOutputDevice.selectedIndex];

        const outInVal = outInOpt ? parseInt(outInOpt.value) : null;
        const outOutVal = outOutOpt ? parseInt(outOutOpt.value) : null;
        const incInVal = incInOpt ? parseInt(incInOpt.value) : null;
        const incOutVal = incOutOpt ? parseInt(incOutOpt.value) : null;

        if (!isNaN(outInVal) && !isNaN(outOutVal) && !isNaN(incInVal) && !isNaN(incOutVal)) {
          fetch(`${API}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              outgoing: {
                input_device_index: outInVal,
                input_device_name: outInOpt ? outInOpt.textContent.trim() : '',
                output_device_index: outOutVal,
                output_device_name: outOutOpt ? outOutOpt.textContent.trim() : ''
              },
              incoming: {
                input_device_index: incInVal,
                input_device_name: incInOpt ? incInOpt.textContent.trim() : '',
                output_device_index: incOutVal,
                output_device_name: incOutOpt ? incOutOpt.textContent.trim() : ''
              }
            })
          }).catch(e => console.warn('Could not sync initial device selections to config:', e));
        }
      }

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

  const pendingMeters = {
    outgoing_input: null,
    outgoing_output: null,
    incoming_input: null,
    incoming_output: null,
  };
  let meterRafId = null;
  let scrollRafId = null;
  let scrollVisibilityRafId = null;

  function formatDbLevel(level) {
    if (!level || level <= 0.001) return '-∞ dB';
    const db = Math.round(level * 60 - 60);
    return `${db} dB`;
  }

  function flushMetersRaf() {
    meterRafId = null;
    const apply = (meterEl, valEl, level) => {
      if (level === null || !meterEl || !valEl) return;
      const pct = Math.min(100, Math.max(0, Math.round(level * 100)));
      meterEl.style.width = `${pct}%`;
      valEl.textContent = formatDbLevel(level);
    };

    apply(outgoingInputMeter, outgoingInputMeterVal, pendingMeters.outgoing_input);
    apply(outgoingOutputMeter, outgoingOutputMeterVal, pendingMeters.outgoing_output);
    apply(incomingInputMeter, incomingInputMeterVal, pendingMeters.incoming_input);
    apply(incomingOutputMeter, incomingOutputMeterVal, pendingMeters.incoming_output);

    pendingMeters.outgoing_input = null;
    pendingMeters.outgoing_output = null;
    pendingMeters.incoming_input = null;
    pendingMeters.incoming_output = null;
  }

  function setMeter(meterEl, valEl, level) {
    if (meterEl === outgoingInputMeter) pendingMeters.outgoing_input = level;
    else if (meterEl === outgoingOutputMeter) pendingMeters.outgoing_output = level;
    else if (meterEl === incomingInputMeter) pendingMeters.incoming_input = level;
    else if (meterEl === incomingOutputMeter) pendingMeters.incoming_output = level;

    if (meterRafId === null) {
      meterRafId = requestAnimationFrame(flushMetersRaf);
    }
  }

  function resetMeters() {
    [outgoingInputMeter, outgoingOutputMeter, incomingInputMeter, incomingOutputMeter].forEach(m => {
      m.style.width = '0%';
    });
    [outgoingInputMeterVal, outgoingOutputMeterVal, incomingInputMeterVal, incomingOutputMeterVal].forEach(v => {
      v.textContent = '-∞ dB';
    });
  }

  // ── Transcript Persistence (transcripts.json) ───────────────────

  let saveTranscriptsTimer = null;

  function saveTranscriptsToServer() {
    if (saveTranscriptsTimer) clearTimeout(saveTranscriptsTimer);
    saveTranscriptsTimer = setTimeout(async () => {
      try {
        const entries = [];
        const entryEls = transcriptFeed.querySelectorAll('.transcript-entry');
        entryEls.forEach(el => {
          if (el.dataset.channel === 'system') return;
          const timeEl = el.querySelector('.transcript-time');
          const timeText = timeEl ? timeEl.textContent.replace(/^\[|\]$/g, '').trim() : '';
          entries.push({
            id: el.dataset.id || '',
            channel: el.dataset.channel || 'outgoing',
            time: timeText,
            srcTag: el.dataset.srcTag || '[AUTO]:',
            tgtTag: el.dataset.tgtTag || '[EN]:',
            rawSource: el.dataset.rawSource || '',
            rawTranslation: el.dataset.rawTranslation || ''
          });
        });
        await fetch(`${API}/transcript`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ entries }),
        });
      } catch (e) {
        console.warn('Failed to save transcripts to server:', e);
      }
    }, 1500);
  }

  function maybeAutoScroll() {
    if (!autoScroll.checked || scrollRafId !== null) return;
    scrollRafId = requestAnimationFrame(() => {
      scrollRafId = null;
      if (autoScroll.checked && transcriptFeed) {
        transcriptFeed.scrollTop = transcriptFeed.scrollHeight;
      }
    });
  }

  function updateScrollButtonsVisibility() {
    if (!transcriptFeed || !btnScrollTop || !btnScrollBottom || scrollVisibilityRafId !== null) return;
    scrollVisibilityRafId = requestAnimationFrame(() => {
      scrollVisibilityRafId = null;
      const canScroll = transcriptFeed.scrollHeight > (transcriptFeed.clientHeight + 8);
      btnScrollTop.classList.toggle('visible', canScroll);
      btnScrollBottom.classList.toggle('visible', canScroll);
    });
  }

  async function loadTranscriptsFromServer() {
    try {
      const res = await fetch(`${API}/transcript`);
      const data = await res.json();
      const entries = data.entries || [];
      if (!Array.isArray(entries) || entries.length === 0) {
        updateScrollButtonsVisibility();
        return;
      }

      removePlaceholder();
      entries.forEach(item => {
        entryCount++;
        const isOutgoing = item.channel === 'outgoing';
        const channelLabel = isOutgoing ? 'OUTGOING' : 'INCOMING';

        const entryEl = document.createElement('div');
        entryEl.className = `transcript-entry channel-${item.channel}`;
        entryEl.dataset.id = item.id || entryCount;
        entryEl.dataset.channel = item.channel;
        entryEl.dataset.srcTag = item.srcTag || '[AUTO]:';
        entryEl.dataset.tgtTag = item.tgtTag || '[EN]:';
        entryEl.dataset.rawSource = item.rawSource || '';
        entryEl.dataset.rawTranslation = item.rawTranslation || '';

        const timeFormatted = item.time ? (item.time.startsWith('[') ? item.time : `[${item.time}]`) : '';

        entryEl.innerHTML = `
          <div class="transcript-time">${timeFormatted}</div>
          <div class="transcript-channel-badge channel-badge-${item.channel}">
            ${channelLabel}
          </div>
          <div class="transcript-source">
            <span class="label">${item.srcTag || '[AUTO]:'}</span>
            <span class="source-text"></span>
          </div>
          <div class="transcript-translation">
            <span class="label">${item.tgtTag || '[EN]:'}</span>
            <span class="translation-text"></span>
          </div>
        `;
        transcriptFeed.appendChild(entryEl);
        renderEntryText(entryEl);
      });
      maybeAutoScroll();
      updateScrollButtonsVisibility();
    } catch (e) {
      console.warn('Failed to load transcripts from server:', e);
      updateScrollButtonsVisibility();
    }
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
      const channelLabel = isOutgoing ? 'OUTGOING' : 'INCOMING';
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
          ${channelLabel}
        </div>
        <div class="transcript-source">
          <span class="label">[AUTO]:</span>
          <span class="source-text"></span>
        </div>
        <div class="transcript-translation">
          <span class="label">[${targetLang}]:</span>
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

    if (serverLang) {
      const srcTag = `[${serverLang.toUpperCase()}]:`;
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
    saveTranscriptsToServer();
    updateScrollButtonsVisibility();
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
    saveTranscriptsToServer();
    updateScrollButtonsVisibility();

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
      saveTranscriptsToServer();
      updateScrollButtonsVisibility();
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
    updateScrollButtonsVisibility();
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
    updateScrollButtonsVisibility();
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
    updateScrollButtonsVisibility();
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
      content += `Mode:        ${currentMode}\n`;
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

        const cleanLang = (tag, fallback) => {
          if (!tag) return fallback;
          const m = tag.match(/\[([A-Za-z0-9_-]+)\]/);
          return m ? m[1].toUpperCase() : fallback;
        };

        const srcLang = cleanLang(entry.dataset.srcTag, 'AUTO');
        const fallbackTgt = channel === 'outgoing'
          ? (outgoingLangSelect ? outgoingLangSelect.getValue() || 'en' : 'en').toUpperCase()
          : (incomingLangSelect ? incomingLangSelect.getValue() || 'ru' : 'ru').toUpperCase();
        const tgtLang = cleanLang(entry.dataset.tgtTag, fallbackTgt);

        let srcPrefix = '';
        let tgtPrefix = '';

        if (channel === 'outgoing') {
          srcPrefix = `[YOU SPEAK → ${srcLang}]:`;
          tgtPrefix = `[THEY HEAR → ${tgtLang}]:`;
        } else {
          srcPrefix = `[THEY SPEAK → ${srcLang}]:`;
          tgtPrefix = `[YOU HEAR   → ${tgtLang}]:`;
        }

        count++;
        if (time) content += `${time}\n`;
        if (rawSrc) content += `${srcPrefix} ${rawSrc}\n`;
        if (rawTrans) content += `${tgtPrefix} ${rawTrans}\n`;
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
      const opt = outgoingInputDevice.options[outgoingInputDevice.selectedIndex];
      await fetch(`${API}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          outgoing: {
            input_device_index: parseInt(outgoingInputDevice.value),
            input_device_name: opt ? opt.textContent : ''
          }
        }),
      });
    });
    outgoingOutputDevice.addEventListener('change', async () => {
      const opt = outgoingOutputDevice.options[outgoingOutputDevice.selectedIndex];
      await fetch(`${API}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          outgoing: {
            output_device_index: parseInt(outgoingOutputDevice.value),
            output_device_name: opt ? opt.textContent : ''
          }
        }),
      });
    });

    // Incoming device changes
    incomingInputDevice.addEventListener('change', async () => {
      const opt = incomingInputDevice.options[incomingInputDevice.selectedIndex];
      await fetch(`${API}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          incoming: {
            input_device_index: parseInt(incomingInputDevice.value),
            input_device_name: opt ? opt.textContent : ''
          }
        }),
      });
    });
    incomingOutputDevice.addEventListener('change', async () => {
      const opt = incomingOutputDevice.options[incomingOutputDevice.selectedIndex];
      await fetch(`${API}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          incoming: {
            output_device_index: parseInt(incomingOutputDevice.value),
            output_device_name: opt ? opt.textContent : ''
          }
        }),
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
      const hasEntries = transcriptFeed.querySelector('.transcript-entry:not([data-channel="system"])');
      if (!hasEntries) return;

      if (confirm('Are you sure you want to clear all transcripts?')) {
        await fetch(`${API}/transcript/clear`, { method: 'POST' });
      }
    });

    btnExportTxt.addEventListener('click', exportTxt);

    // Transcript Maximize / Restore
    if (btnMaximizeTranscript) {
      btnMaximizeTranscript.addEventListener('click', () => {
        const isMaximized = mainContent.classList.toggle('transcript-maximized');
        transcriptSection.classList.toggle('maximized', isMaximized);
        btnMaximizeTranscript.textContent = isMaximized ? '🗗' : '🗖';
        btnMaximizeTranscript.title = isMaximized ? 'Restore normal view' : 'Maximize transcript view';
        setTimeout(updateScrollButtonsVisibility, 50);
      });
    }

    // Scroll Controls (Top / Bottom)
    if (btnScrollTop) {
      btnScrollTop.addEventListener('click', () => {
        transcriptFeed.scrollTo({ top: 0, behavior: 'smooth' });
      });
    }
    if (btnScrollBottom) {
      btnScrollBottom.addEventListener('click', () => {
        transcriptFeed.scrollTo({ top: transcriptFeed.scrollHeight, behavior: 'smooth' });
        if (autoScroll) autoScroll.checked = true;
      });
    }

    transcriptFeed.addEventListener('scroll', updateScrollButtonsVisibility);
    window.addEventListener('resize', updateScrollButtonsVisibility);

    if (window.ResizeObserver) {
      const ro = new ResizeObserver(() => {
        updateScrollButtonsVisibility();
      });
      ro.observe(transcriptFeed);
    }

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
