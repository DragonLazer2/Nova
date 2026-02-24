/* Nova Web Dashboard — app.js
   WebSocket client, AudioPipeline, SoundEffects, AutoListen (server-side STT), Chat UI
   Voice flow: Nova speaks → audio finishes → mic records → server transcribes → repeat */

// Block browser from ever opening dropped files — must be top-level, outside IIFE
document.addEventListener("dragover", function (e) { e.preventDefault(); }, false);
document.addEventListener("dragenter", function (e) { e.preventDefault(); }, false);
// Document-level drop: prevent browser open AND forward image files to handler
document.addEventListener("drop", function (e) {
  e.preventDefault();
  if (window._novaAddImageFile) {
    for (var i = 0; i < e.dataTransfer.files.length; i++) {
      var file = e.dataTransfer.files[i];
      if (file.type.indexOf("image/") === 0) window._novaAddImageFile(file);
    }
  }
}, false);

(function () {
  "use strict";

  // ── State ──────────────────────────────────────────────────────────────────
  let ws = null;
  let audioCtx = null;
  let reconnectTimer = null;
  let responseInProgress = false;
  let responseInterrupted = false;  // ignore remaining audio/text from cancelled response
  let voiceEnabled = true;
  let hasConnectedBefore = false;
  const WS_URL = `ws://${location.host}/ws`;

  // ── DOM refs ───────────────────────────────────────────────────────────────
  const overlay = document.getElementById("overlay");
  const appEl = document.getElementById("app");
  const chatMessages = document.getElementById("chat-messages");
  const chatPanel = document.getElementById("chat-panel");
  const textInput = document.getElementById("text-input");
  const sendBtn = document.getElementById("send-btn");
  const pttBtn = document.getElementById("ptt-btn");
  const clearBtn = document.getElementById("clear-btn");
  const toneLabel = document.getElementById("tone-label");
  const connStatus = document.getElementById("connection-status");
  const attachBtn = document.getElementById("attach-btn");
  const fileInput = document.getElementById("file-input");
  const previewBar = document.getElementById("image-preview-bar");
  const visualPanel = document.getElementById("visual-panel");
  const visualLog = document.getElementById("visual-log");
  const visualToggle = document.getElementById("visual-toggle");
  const visualHeader = document.getElementById("visual-panel-header");

  // ── Visual state panel ──────────────────────────────────────────────────────
  if (visualHeader) {
    visualHeader.addEventListener("click", () => {
      visualPanel.classList.toggle("collapsed");
    });
  }

  function logVisualState(params) {
    if (!visualLog) return;
    // Build formatted entry
    const pairs = Object.entries(params)
      .map(([k, v]) => '<span class="v-key">' + k + '</span>=<span class="v-val">' + v + '</span>')
      .join("  ");
    // Remove "latest" from previous entries
    const prev = visualLog.querySelector(".latest");
    if (prev) prev.classList.remove("latest");
    // Add new entry
    const el = document.createElement("div");
    el.className = "visual-entry latest";
    el.innerHTML = pairs;
    visualLog.appendChild(el);
    // Keep max 20 entries
    while (visualLog.children.length > 20) visualLog.removeChild(visualLog.firstChild);
    visualLog.scrollTop = visualLog.scrollHeight;
  }

  // ── Pending images (base64 + media type) ────────────────────────────────────
  let pendingImages = [];

  // ── Screen sharing state ────────────────────────────────────────────────────
  let screenStream = null;
  let screenVideo = null;

  // ── Overlay click-to-start ─────────────────────────────────────────────────
  overlay.addEventListener("click", async () => {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    AudioPipeline.init(audioCtx);
    SoundEffects.init(audioCtx);
    await AutoListen.init();
    overlay.classList.add("fade-out");
    setTimeout(() => {
      overlay.style.display = "none";
      appEl.classList.remove("hidden");
      NovaAvatar.init(document.getElementById("avatar-canvas"));
      connect();
    }, 600);
  });

  // ── WebSocket ──────────────────────────────────────────────────────────────
  function connect() {
    if (ws && ws.readyState <= 1) return;
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      connStatus.textContent = "Connected";
      connStatus.className = "connected";
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    };

    ws.onclose = () => {
      connStatus.textContent = "Disconnected — reconnecting...";
      connStatus.className = "disconnected";
      AutoListen.abort();
      scheduleReconnect();
    };

    ws.onerror = () => {
      connStatus.textContent = "Connection error";
      connStatus.className = "disconnected";
    };

    ws.onmessage = (evt) => handleMessage(JSON.parse(evt.data));
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(); }, 3000);
  }

  function send(obj) {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
  }

  setInterval(() => { send({ type: "ping" }); }, 25000);

  // ── Message handler ────────────────────────────────────────────────────────
  let streamingEl = null;

  function handleMessage(msg) {
    switch (msg.type) {
      case "chat_history":
        // Render previous conversation on connect
        chatMessages.innerHTML = "";
        if (msg.messages) {
          for (const m of msg.messages) appendMsg(m.role, m.text);
        }
        break;

      case "greeting":
        if (!hasConnectedBefore) {
          // First connect: play sunrise chime, then greeting
          playSunriseChime(audioCtx);
          appendMsg("nova", msg.text);
          if (msg.audio) AudioPipeline.enqueue(msg.audio, 1.0);
          responseInProgress = true;
          AudioPipeline.onAllFinished = () => {
            responseInProgress = false;
            startListeningAfterDelay();
          };
        } else {
          // Reconnect: silently resume, no greeting spam
          startListeningAfterDelay();
        }
        hasConnectedBefore = true;
        break;

      case "response_start":
        responseInProgress = true;
        responseInterrupted = false;
        streamingEl = appendMsg("nova", "", true);
        // Keep mic active for voice interrupts (silent mode — no "Listening..." indicator)
        if (voiceEnabled && !AutoListen.active) {
          setTimeout(() => { if (responseInProgress && !responseInterrupted) AutoListen.start(true); }, 500);
        }
        break;

      case "text_delta":
        if (!responseInterrupted && streamingEl) { streamingEl.textContent += msg.text; scrollChat(); }
        break;

      case "tone_update":
        if (!responseInterrupted) {
          toneLabel.textContent = msg.tone || "neutral";
          if (typeof NovaAvatar !== "undefined") NovaAvatar.setTone(msg.tone);
        }
        break;

      case "sentence_audio":
        if (!responseInterrupted) {
          AudioPipeline.enqueue(msg.audio, msg.playback_vol || 1.0, msg.seq);
        }
        break;

      case "sound_effect":
        if (!responseInterrupted) SoundEffects.play(msg.name);
        break;

      case "visual_update":
        if (!responseInterrupted && typeof NovaAvatar !== "undefined") NovaAvatar.setVisual(msg.params);
        logVisualState(msg.params);
        break;

      case "response_end":
        if (streamingEl) { streamingEl.classList.remove("streaming"); streamingEl = null; }
        if (responseInterrupted) {
          // Interrupted — just clean up, don't restart listening (already listening)
          responseInProgress = false;
          responseInterrupted = false;
          break;
        }
        AudioPipeline.onAllFinished = () => {
          responseInProgress = false;
          startListeningAfterDelay();
        };
        if (!AudioPipeline.playing && AudioPipeline.queue.length === 0) {
          responseInProgress = false;
          startListeningAfterDelay();
        }
        break;

      case "transcript":
        // Server transcribed our audio — show it and send as message
        AutoListen.clearStatus();
        if (msg.text) {
          sendUserMessage(msg.text);
        } else {
          // No speech detected — listen again
          if (voiceEnabled) {
            setTimeout(() => AutoListen.start(responseInProgress), 300);
          }
        }
        break;

      case "history_cleared":
        chatMessages.innerHTML = "";
        appendMsg("system", "History cleared.");
        break;

      case "pong":
        break;
    }
  }

  function startListeningAfterDelay() {
    if (!voiceEnabled) return;
    setTimeout(() => {
      if (!responseInProgress) AutoListen.start();
    }, 400);
  }

  // ── Chat UI ────────────────────────────────────────────────────────────────
  function appendMsg(role, text, streaming) {
    const el = document.createElement("div");
    el.className = "msg " + role;
    if (streaming) el.classList.add("streaming");
    el.textContent = text;
    chatMessages.appendChild(el);
    scrollChat();
    return el;
  }

  function scrollChat() {
    chatPanel.scrollTop = chatPanel.scrollHeight;
  }

  function sendUserMessage(text) {
    text = text.trim();
    if (!text && pendingImages.length === 0) return;
    // If Nova is mid-response, mark interrupted so remaining audio/text is ignored
    if (responseInProgress) responseInterrupted = true;
    // Show user message with thumbnails in chat
    const el = appendMsg("user", text || "");
    for (const img of pendingImages) {
      const imgEl = document.createElement("img");
      imgEl.className = "chat-image";
      imgEl.src = "data:" + img.mediaType + ";base64," + img.b64;
      el.appendChild(imgEl);
    }
    scrollChat();
    AutoListen.abort();
    AudioPipeline.stop();
    const payload = { type: "user_message", text: text || "" };
    // Auto-attach screen capture frame if sharing
    var screenFrame = captureScreenFrame();
    if (pendingImages.length > 0 || screenFrame) {
      payload.images = pendingImages.map((img) => ({ data: img.b64, media_type: img.mediaType }));
      if (screenFrame) payload.images.push(screenFrame);
      pendingImages = [];
      renderPreviews();
    }
    send(payload);
  }

  function sendFromInput() {
    const text = textInput.value.trim();
    if (!text && pendingImages.length === 0) return;
    textInput.value = "";
    sendUserMessage(text);
  }

  sendBtn.addEventListener("click", sendFromInput);
  textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendFromInput(); }
  });
  textInput.addEventListener("focus", () => { AutoListen.abort(); });

  clearBtn.addEventListener("click", () => { send({ type: "clear_history" }); });

  // ── Screen share ────────────────────────────────────────────────────────────
  const screenBtn = document.getElementById("screen-btn");

  async function toggleScreenShare() {
    if (screenStream) {
      screenStream.getTracks().forEach(t => t.stop());
      screenStream = null;
      if (screenVideo) { screenVideo.remove(); screenVideo = null; }
      screenBtn.classList.remove("active");
    } else {
      try {
        screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
        screenVideo = document.createElement("video");
        screenVideo.style.display = "none";
        screenVideo.srcObject = screenStream;
        screenVideo.play();
        document.body.appendChild(screenVideo);
        screenBtn.classList.add("active");
        screenStream.getVideoTracks()[0].onended = () => {
          screenStream = null;
          if (screenVideo) { screenVideo.remove(); screenVideo = null; }
          screenBtn.classList.remove("active");
        };
      } catch (e) {
        console.warn("Screen share cancelled or failed:", e);
      }
    }
  }

  function captureScreenFrame() {
    if (!screenStream || !screenVideo || screenVideo.videoWidth === 0) return null;
    var canvas = document.createElement("canvas");
    canvas.width = screenVideo.videoWidth;
    canvas.height = screenVideo.videoHeight;
    var ctx = canvas.getContext("2d");
    ctx.drawImage(screenVideo, 0, 0);
    var dataUrl = canvas.toDataURL("image/jpeg", 0.7);
    var commaIdx = dataUrl.indexOf(",");
    return { data: dataUrl.substring(commaIdx + 1), media_type: "image/jpeg" };
  }

  screenBtn.addEventListener("click", toggleScreenShare);

  // ── Image attach ──────────────────────────────────────────────────────────

  function addImageFile(file) {
    if (!file || !file.type.startsWith("image/")) return;
    console.log("[Nova] addImageFile:", file.name, file.type);
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result;
      const commaIdx = dataUrl.indexOf(",");
      const b64 = dataUrl.substring(commaIdx + 1);
      const mediaType = file.type;
      pendingImages.push({ b64, mediaType, name: file.name });
      renderPreviews();
    };
    reader.readAsDataURL(file);
  }

  // Expose globally so document-level drop handler can call it
  window._novaAddImageFile = addImageFile;

  // Attach button → open file picker
  attachBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    console.log("[Nova] attach button clicked");
    fileInput.value = "";
    fileInput.click();
  });

  fileInput.addEventListener("change", () => {
    console.log("[Nova] file input changed, files:", fileInput.files.length);
    for (const file of fileInput.files) addImageFile(file);
    fileInput.value = "";
  });

  // Paste images from clipboard
  document.addEventListener("paste", (e) => {
    if (!e.clipboardData || !e.clipboardData.items) return;
    for (const item of e.clipboardData.items) {
      if (item.type.startsWith("image/")) {
        e.preventDefault();
        addImageFile(item.getAsFile());
      }
    }
  });

  function renderPreviews() {
    previewBar.innerHTML = "";
    if (pendingImages.length === 0) {
      previewBar.classList.add("hidden");
      attachBtn.classList.remove("has-images");
      return;
    }
    previewBar.classList.remove("hidden");
    attachBtn.classList.add("has-images");
    pendingImages.forEach((img, idx) => {
      const wrap = document.createElement("div");
      wrap.className = "img-preview";
      const imgEl = document.createElement("img");
      imgEl.src = "data:" + img.mediaType + ";base64," + img.b64;
      wrap.appendChild(imgEl);
      const removeBtn = document.createElement("button");
      removeBtn.className = "remove-img";
      removeBtn.textContent = "\u00d7";
      removeBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        pendingImages.splice(idx, 1);
        renderPreviews();
      });
      wrap.appendChild(removeBtn);
      previewBar.appendChild(wrap);
    });
    console.log("[Nova] preview bar updated, images:", pendingImages.length);
  }

  // Mic button: toggle voice on/off — OR interrupt Nova if she's speaking
  pttBtn.addEventListener("click", () => {
    if (responseInProgress) {
      // Interrupt: stop Nova's audio, tell server to cancel, start listening
      AudioPipeline.stop();
      if (streamingEl) { streamingEl.classList.remove("streaming"); streamingEl = null; }
      responseInterrupted = true;     // ignore remaining audio/text from this response
      send({ type: "interrupt" });    // tell server to cancel the stream
      voiceEnabled = true;
      pttBtn.classList.add("active");
      AutoListen.abort();
      setTimeout(() => AutoListen.start(), 150);
      return;
    }
    voiceEnabled = !voiceEnabled;
    if (voiceEnabled) {
      pttBtn.classList.add("active");
      AutoListen.start();
    } else {
      pttBtn.classList.remove("active");
      AutoListen.abort();
    }
  });
  pttBtn.classList.add("active");

  // ── AudioPipeline ──────────────────────────────────────────────────────────
  const AudioPipeline = {
    ctx: null, gainNode: null, analyser: null,
    queue: [], playing: false, stopped: false, _currentSource: null,
    onAllFinished: null,

    init(ctx) {
      this.ctx = ctx;
      this.gainNode = ctx.createGain();
      this.analyser = ctx.createAnalyser();
      this.analyser.fftSize = 256;
      this.gainNode.connect(this.analyser);
      this.analyser.connect(ctx.destination);
    },

    enqueue(b64, vol, seq) {
      this.queue.push({ b64, vol, seq: seq || 0 });
      this.queue.sort((a, b) => a.seq - b.seq);
      if (!this.playing) this._playNext();
    },

    stop() {
      this.stopped = true;
      this.queue = [];
      this.onAllFinished = null;
      if (this._currentSource) { try { this._currentSource.stop(); } catch (e) {} }
      this.playing = false;
      this.stopped = false;
    },

    async _playNext() {
      if (this.queue.length === 0 || this.stopped) {
        this.playing = false;
        if (this.onAllFinished) { const cb = this.onAllFinished; this.onAllFinished = null; cb(); }
        return;
      }
      this.playing = true;
      const { b64, vol } = this.queue.shift();
      try {
        const binary = atob(b64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        const audioBuffer = await this.ctx.decodeAudioData(bytes.buffer);
        if (this.stopped) { this.playing = false; return; }
        this.gainNode.gain.setValueAtTime(Math.max(0.15, Math.min(1.0, vol * 0.55)), this.ctx.currentTime);
        const source = this.ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(this.gainNode);
        this._currentSource = source;
        source.onended = () => { this._currentSource = null; this._playNext(); };
        source.start();
      } catch (e) { console.warn("AudioPipeline decode error:", e); this._playNext(); }
    },

    getRMS() {
      if (!this.analyser) return 0;
      const data = new Uint8Array(this.analyser.frequencyBinCount);
      this.analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) { const v = (data[i] - 128) / 128; sum += v * v; }
      return Math.sqrt(sum / data.length);
    },
  };

  window.AudioPipeline = AudioPipeline;

  // ── SoundEffects ───────────────────────────────────────────────────────────
  const SoundEffects = {
    ctx: null, cache: {},
    init(ctx) { this.ctx = ctx; },
    async play(name) {
      if (!this.ctx) return;
      try {
        let buffer = this.cache[name];
        if (!buffer) {
          const resp = await fetch(`/sounds/${name}.wav`);
          if (!resp.ok) return;
          buffer = await this.ctx.decodeAudioData(await resp.arrayBuffer());
          this.cache[name] = buffer;
        }
        const source = this.ctx.createBufferSource();
        source.buffer = buffer;
        const gain = this.ctx.createGain();
        gain.gain.value = 0.5;
        source.connect(gain);
        gain.connect(this.ctx.destination);
        source.start();
      } catch (e) { console.warn("SoundEffect error:", name, e); }
    },
  };

  // ── Sunrise welcome chime (synthesized) ───────────────────────────────────
  function playSunriseChime(ctx) {
    if (!ctx) return;
    // Ensure audio context is running (Chrome autoplay policy)
    if (ctx.state === "suspended") ctx.resume();

    const now = ctx.currentTime + 0.05;  // tiny offset to avoid scheduling at t=0
    // Bright ascending arpeggio: C5 → E5 → G5 → C6
    const notes = [523.25, 659.25, 783.99, 1046.50];
    const noteDur = 0.35;
    const master = ctx.createGain();
    master.gain.value = 0.55;
    master.connect(ctx.destination);

    notes.forEach((freq, i) => {
      const t = now + i * 0.18;

      // Primary tone (sine — warm body)
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.value = freq;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.001, t);
      g.gain.linearRampToValueAtTime(0.7, t + 0.04);
      g.gain.exponentialRampToValueAtTime(0.001, t + noteDur);
      osc.connect(g);
      g.connect(master);
      osc.start(t);
      osc.stop(t + noteDur + 0.1);

      // Bright shimmer (triangle an octave up)
      const osc2 = ctx.createOscillator();
      osc2.type = "triangle";
      osc2.frequency.value = freq * 2;
      const g2 = ctx.createGain();
      g2.gain.setValueAtTime(0.001, t);
      g2.gain.linearRampToValueAtTime(0.25, t + 0.03);
      g2.gain.exponentialRampToValueAtTime(0.001, t + noteDur * 0.6);
      osc2.connect(g2);
      g2.connect(master);
      osc2.start(t);
      osc2.stop(t + noteDur + 0.1);
    });

    // Final sparkle — high ping on the last note
    const sparkle = ctx.createOscillator();
    sparkle.type = "sine";
    sparkle.frequency.value = 2093;  // C7
    const sg = ctx.createGain();
    const sTime = now + 3 * 0.18 + 0.06;
    sg.gain.setValueAtTime(0.001, sTime);
    sg.gain.linearRampToValueAtTime(0.2, sTime + 0.03);
    sg.gain.exponentialRampToValueAtTime(0.001, sTime + 0.45);
    sparkle.connect(sg);
    sg.connect(master);
    sparkle.start(sTime);
    sparkle.stop(sTime + 0.55);
  }

  // ── AutoListen (server-side speech recognition) ────────────────────────────
  // Captures mic audio as raw PCM, encodes as WAV, sends to server for
  // transcription via speech_recognition + Google. Works in any browser.
  const AutoListen = {
    micStream: null,
    micCtx: null,
    processor: null,
    chunks: [],
    active: false,
    hasVoice: false,
    silenceStart: 0,
    startTime: 0,
    statusEl: null,

    async init() {
      try {
        this.micStream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 16000 }
        });
      } catch (e) {
        console.warn("Mic access denied:", e);
        appendMsg("system", "Microphone access denied. Check browser permissions.");
        voiceEnabled = false;
        pttBtn.classList.remove("active");
      }
    },

    start(silent) {
      if (!this.micStream || this.active || !voiceEnabled) return;
      this.active = true;
      this.silent = !!silent;
      this.chunks = [];
      this.hasVoice = false;
      this.silenceStart = 0;
      this.startTime = Date.now();
      pttBtn.classList.add("active");

      if (!silent) {
        this.statusEl = appendMsg("system", "Listening...");
        this.statusEl.classList.add("listening");
        scrollChat();
      }

      // Create a dedicated AudioContext for mic capture at 16kHz
      // (some browsers ignore sampleRate constraint, so we resample later)
      try {
        this.micCtx = new AudioContext({ sampleRate: 16000 });
      } catch (e) {
        this.micCtx = new AudioContext();
      }

      const source = this.micCtx.createMediaStreamSource(this.micStream);
      // ScriptProcessorNode: 4096 samples per buffer, mono in, mono out
      this.processor = this.micCtx.createScriptProcessor(4096, 1, 1);

      this.processor.onaudioprocess = (e) => {
        if (!this.active) return;
        const data = e.inputBuffer.getChannelData(0);
        this.chunks.push(new Float32Array(data));

        // Simple energy-based voice activity detection
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
        const rms = Math.sqrt(sum / data.length);

        if (rms > 0.015) {
          // Voice detected
          this.hasVoice = true;
          this.silenceStart = 0;
          if (this.statusEl) {
            this.statusEl.textContent = "Hearing you...";
          }
        } else if (this.hasVoice && !this.silenceStart) {
          this.silenceStart = Date.now();
        }

        // Stop conditions
        const elapsed = Date.now() - this.startTime;

        // 1.5s of silence after voice → done speaking
        if (this.hasVoice && this.silenceStart && (Date.now() - this.silenceStart > 1500)) {
          this._finish();
          return;
        }

        // 10s with no voice at all → retry
        if (!this.hasVoice && elapsed > 10000) {
          this._cancel();
          return;
        }

        // 60s max recording
        if (elapsed > 60000) {
          this._finish();
        }
      };

      source.connect(this.processor);
      this.processor.connect(this.micCtx.destination);
    },

    _finish() {
      if (!this.active) return;
      this.active = false;
      this._disconnectAudio();

      if (this.statusEl) this.statusEl.textContent = "Processing...";

      if (this.hasVoice && this.chunks.length > 0) {
        const sampleRate = this.micCtx ? this.micCtx.sampleRate : 16000;
        const wav = encodeWAV(this.chunks, sampleRate);
        // Base64 encode — send in chunks to avoid call stack issues
        const b64 = arrayBufferToBase64(wav);
        send({ type: "audio_input", audio: b64 });
      } else {
        this.clearStatus();
        if (voiceEnabled) {
          // Restart listening — in silent mode if response is active
          setTimeout(() => this.start(responseInProgress), 300);
        }
      }
    },

    _cancel() {
      this.active = false;
      this._disconnectAudio();
      this.clearStatus();
      // No voice detected, try again — silent mode during response
      if (voiceEnabled) {
        setTimeout(() => this.start(responseInProgress), 300);
      }
    },

    abort() {
      this.active = false;
      this._disconnectAudio();
      this.clearStatus();
    },

    _disconnectAudio() {
      if (this.processor) { try { this.processor.disconnect(); } catch (e) {} this.processor = null; }
      if (this.micCtx) { try { this.micCtx.close(); } catch (e) {} this.micCtx = null; }
    },

    clearStatus() {
      if (this.statusEl) { this.statusEl.remove(); this.statusEl = null; }
    },
  };

  // ── WAV encoder ────────────────────────────────────────────────────────────
  function encodeWAV(chunks, sampleRate) {
    // Merge Float32 chunks
    let totalLen = 0;
    for (const c of chunks) totalLen += c.length;
    const merged = new Float32Array(totalLen);
    let off = 0;
    for (const c of chunks) { merged.set(c, off); off += c.length; }

    // If sample rate > 16kHz, downsample to 16kHz
    let samples = merged;
    let outRate = sampleRate;
    if (sampleRate > 16000) {
      const ratio = sampleRate / 16000;
      const newLen = Math.floor(merged.length / ratio);
      samples = new Float32Array(newLen);
      for (let i = 0; i < newLen; i++) {
        samples[i] = merged[Math.floor(i * ratio)];
      }
      outRate = 16000;
    }

    // Float32 → Int16
    const pcm = new Int16Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }

    // WAV header + data
    const buffer = new ArrayBuffer(44 + pcm.length * 2);
    const v = new DataView(buffer);

    writeStr(v, 0, "RIFF");
    v.setUint32(4, 36 + pcm.length * 2, true);
    writeStr(v, 8, "WAVE");
    writeStr(v, 12, "fmt ");
    v.setUint32(16, 16, true);
    v.setUint16(20, 1, true);              // PCM
    v.setUint16(22, 1, true);              // mono
    v.setUint32(24, outRate, true);
    v.setUint32(28, outRate * 2, true);    // byte rate
    v.setUint16(32, 2, true);              // block align
    v.setUint16(34, 16, true);             // bits per sample
    writeStr(v, 36, "data");
    v.setUint32(40, pcm.length * 2, true);

    // Copy PCM
    const target = new Int16Array(buffer, 44);
    target.set(pcm);

    return buffer;
  }

  function writeStr(view, offset, str) {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  }

  // Base64 encode an ArrayBuffer without hitting call stack limits
  function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    const chunkSize = 32768;
    let binary = "";
    for (let i = 0; i < bytes.length; i += chunkSize) {
      const slice = bytes.subarray(i, Math.min(i + chunkSize, bytes.length));
      binary += String.fromCharCode.apply(null, slice);
    }
    return btoa(binary);
  }

})();
