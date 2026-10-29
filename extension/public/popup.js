// Shared settings/migration helpers are prepended by build.js.
const FALLBACK_VOICES = {
  kokoro: ["af_bella", "af_heart", "af_sarah", "af_sky", "am_echo", "am_liam",
    "am_michael", "bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel",
    "bm_fable", "bm_george", "bm_lewis"],
  pocket: ["alba", "anna", "azelma", "bill_boerst", "charles", "cosette",
    "eponine", "eve", "george", "jane", "mary", "michael"],
};

document.addEventListener("DOMContentLoaded", async () => {
  const settings = await getTTSSettings();
  const engineSelect = document.getElementById("tts-select");
  const voiceSelect = document.getElementById("voice-select");
  const urlInput = document.getElementById("server-url");
  const indicator = document.getElementById("server-status");
  const savedVoices = { ...settings.ttsVoices };
  savedVoices[settings.ttsEngine] ||= settings.ttsVoice;
  engineSelect.value = settings.ttsEngine;
  urlInput.value = await getServerUrl();
  let requestVersion = 0;

  async function refresh() {
    const version = ++requestVersion;
    const engine = engineSelect.value;
    const local = engine === "kokoro" || engine === "pocket";
    for (const id of ["voice-row", "server-url-row", "lookahead-row", "auto-scroll-row", "server-status"]) {
      document.getElementById(id).style.display = local ? "block" : "none";
    }
    document.getElementById("speed-row").style.display = engine === "kokoro" ? "block" : "none";
    if (!local) return;
    voiceSelect.disabled = true;
    indicator.textContent = "● Checking server…";
    indicator.className = "server-status checking";
    let voices = FALLBACK_VOICES[engine];
    try {
      const url = urlInput.value.trim().replace(/\/+$/, "") || DEFAULT_SERVER_URL;
      const response = await fetch(`${url}/voices?engine=${engine}`, {
        signal: AbortSignal.timeout(2500),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (engine === "pocket") {
        // Older servers ignore the query parameter; check explicit support.
        const response = await fetch(`${url}/engines`, { signal: AbortSignal.timeout(2500) });
        const catalog = response.ok ? await response.json() : {};
        if (!catalog.engines?.some((e) => e.id === "pocket" && e.installed)) {
          throw new Error("Update the server for Pocket TTS");
        }
      }
      if (!Array.isArray(data.voices) || !data.voices.length) throw new Error("No voices available");
      voices = data.voices;
      if (version !== requestVersion) return;
      indicator.textContent = "● Server online — model loads on first read";
      indicator.className = "server-status online";
    } catch (error) {
      if (version !== requestVersion) return;
      indicator.textContent = `● Server unavailable: ${error.message}. Start or update PageVoice Server.`;
      indicator.className = "server-status offline";
    }
    if (version !== requestVersion) return;
    voiceSelect.replaceChildren();
    const selected = savedVoices[engine] || voices[0];
    if (!voices.includes(selected)) voices = [...voices, selected];
    for (const voice of voices) {
      const option = document.createElement("option");
      option.value = voice;
      option.textContent = voice.replace(/_/g, " ");
      voiceSelect.appendChild(option);
    }
    voiceSelect.value = selected;
    voiceSelect.disabled = false;
  }

  engineSelect.addEventListener("change", () => {
    const engine = engineSelect.value;
    const voice = savedVoices[engine] || FALLBACK_VOICES[engine]?.[0] || "";
    api.storage.sync.set({ ttsEngine: engine, ttsVoice: voice, ttsVoices: savedVoices });
    refresh();
  });
  voiceSelect.addEventListener("change", () => {
    savedVoices[engineSelect.value] = voiceSelect.value;
    api.storage.sync.set({ ttsVoice: voiceSelect.value, ttsVoices: savedVoices });
  });
  urlInput.addEventListener("change", () => {
    urlInput.value = urlInput.value.trim().replace(/\/+$/, "") || DEFAULT_SERVER_URL;
    api.storage.sync.set({ serverUrl: urlInput.value });
    refresh();
  });

  const speed = document.getElementById("speed-range");
  const speedValue = document.getElementById("speed-value");
  speed.value = Number(settings.ttsSpeed) || DEFAULT_SPEED;
  speedValue.textContent = `${Number(speed.value).toFixed(1)}×`;
  speed.addEventListener("input", () => {
    speedValue.textContent = `${Number(speed.value).toFixed(1)}×`;
    api.storage.sync.set({ ttsSpeed: Number(speed.value) });
  });
  const lookahead = document.getElementById("lookahead-select");
  lookahead.value = String(Number(settings.ttsLookAhead) || DEFAULT_LOOKAHEAD);
  lookahead.addEventListener("change", () => api.storage.sync.set({ ttsLookAhead: Number(lookahead.value) }));
  const autoScroll = document.getElementById("auto-scroll");
  autoScroll.checked = settings.ttsAutoScroll ?? DEFAULT_AUTO_SCROLL;
  autoScroll.addEventListener("change", () => api.storage.sync.set({ ttsAutoScroll: autoScroll.checked }));

  async function run(action) {
    const [tab] = await api.tabs.query({ active: true, currentWindow: true });
    if (tab?.id == null) return;
    try {
      await api.tabs.sendMessage(tab.id, { action });
      window.close();
    } catch {
      indicator.style.display = "block";
      indicator.textContent = "Refresh this page first. Browser settings and protected pages cannot be read.";
      indicator.className = "server-status offline";
    }
  }
  document.getElementById("read-article-btn").addEventListener("click", () => run("readArticle"));
  document.getElementById("pick-element-btn").addEventListener("click", () => run("enterPickMode"));
  refresh();
});
