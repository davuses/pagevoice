// `api`, `DEFAULT_SPEED`, and `getServerUrl` come from shared.js, which build.js
// prepends to this file (see its comment for why concatenation, not imports).
const actionApi = api.action ?? api.browserAction;

function createMenus() {
  api.contextMenus.create({
    id: "ttsReadElement",
    title: "Read an element aloud…",
    contexts: ["page"],
  });
  api.contextMenus.create({
    id: "ttsReadSelection",
    title: "Read selection aloud",
    contexts: ["selection"],
  });
  api.contextMenus.create({
    id: "ttsReadFromHere",
    title: "Read from here to the end",
    contexts: ["page", "selection"],
  });
  api.contextMenus.create({
    id: "ttsReadArticle",
    title: "Read main article aloud",
    contexts: ["page"],
  });
}

api.runtime.onInstalled.addListener(createMenus);
api.runtime.onStartup.addListener(createMenus);

api.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "ttsReadElement") {
    // Ask the page to enter element-picker mode; it sends back "tts_text".
    api.tabs.sendMessage(tab.id, { action: "enterPickMode" });
  } else if (info.menuItemId === "ttsReadSelection") {
    // Read the highlighted text. The page clears the selection first so the
    // karaoke highlight isn't painted over by ::selection.
    api.tabs.sendMessage(tab.id, { action: "readSelection" });
  } else if (info.menuItemId === "ttsReadFromHere") {
    // Read the right-clicked element and everything after it.
    api.tabs.sendMessage(tab.id, { action: "readFromHere" });
  } else if (info.menuItemId === "ttsReadArticle") {
    // Detect and read the page's main article content.
    api.tabs.sendMessage(tab.id, { action: "readArticle" });
  }
});

// Alt+S reads the current selection — the same path as the context-menu entry.
// The tab argument isn't passed on every browser/manifest version, so resolve
// the active tab ourselves rather than relying on it.
api.commands?.onCommand.addListener(async (command) => {
  if (command !== "read-selection") return;
  const [tab] = await api.tabs.query({ active: true, currentWindow: true });
  if (tab?.id == null) return;
  // No content script on chrome://, the Web Store, PDFs, etc. — sendMessage
  // rejects there, so swallow it rather than log an unhandled rejection.
  api.tabs
    .sendMessage(tab.id, { action: "readSelection" })
    .catch(() => {});
});

// Text extracted by the content-script readers (element picker, "read from
// here", "read main article") comes back here to be synthesized.
api.runtime.onMessage.addListener((message, sender) => {
  if (message.action === "tts_text" && message.text && sender.tab) {
    const segments = message.segments?.length ? message.segments : [message.text];
    handleTTS(message.text, segments, sender.tab.id);
  }
});

async function handleTTS(selectedText, segments, tabId) {
  const data = await getTTSSettings();
  const ttsEngine = data.ttsEngine || "google-translate";

  if (ttsEngine === "kokoro" || ttsEngine === "pocket") {
    // Local engines stream for low latency, and the
    // streaming player can still export the full audio as a WAV download.
    const voice = data.ttsVoice;
    const speed = ttsEngine === "kokoro" ? Number(data.ttsSpeed) || DEFAULT_SPEED : 1;
    const lookAhead = Number(data.ttsLookAhead) || DEFAULT_LOOKAHEAD;
    const autoScroll = data.ttsAutoScroll ?? DEFAULT_AUTO_SCROLL;
    streamLocal(segments, voice, tabId, speed, lookAhead, autoScroll, ttsEngine);
  } else if (ttsEngine === "google-translate") {
    const gtUrl = `https://www.google.com/speech-api/v1/synthesize?text=${encodeURIComponent(selectedText)}&enc=mpeg&lang=en-us&speed=0.45&client=lr-language-tts&use_google_only_voices=1`;

    actionApi?.setBadgeText({ text: "…", tabId });
    actionApi?.setBadgeBackgroundColor({ color: "#3b82f6", tabId });

    try {
      const response = await fetch(gtUrl);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const audioBlob = await response.blob();
      const reader = new FileReader();
      reader.onloadend = () => {
        actionApi?.setBadgeText({ text: "", tabId });
        api.tabs.sendMessage(tabId, {
          action: "tts_google_translate",
          audioBase64: reader.result.split(",")[1],
        });
      };
      reader.readAsDataURL(audioBlob);
    } catch (error) {
      actionApi?.setBadgeText({ text: "!", tabId });
      actionApi?.setBadgeBackgroundColor({ color: "#ef4444", tabId });
      setTimeout(() => actionApi?.setBadgeText({ text: "", tabId }), 2500);
      api.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "TTS Error",
        message: `Google Translate TTS failed: ${error.message}`,
      });
    }
  }
}

// Streaming playback: open a port to the page and feed it PCM chunks, one text
// segment at a time. Closing the player disconnects the port, which aborts the
// in-flight fetch so the server stops generating.
//
// Segments exist for two reasons. The server holds a single global inference
// lock for the whole of a /tts/stream request, so one long request would block
// every other read on the server; short ones interleave. And with a bounded
// look-ahead we simply stop asking for the next segment once we are far enough
// ahead of the playhead, so abandoning a long article wastes at most one
// segment instead of the whole thing. lookAhead === 0 means unlimited: fetch
// every segment back to back, which is the original behaviour.
async function streamLocal(
  segments,
  voice,
  tabId,
  speed = DEFAULT_SPEED,
  lookAhead = DEFAULT_LOOKAHEAD,
  autoScroll = DEFAULT_AUTO_SCROLL,
  engine = "kokoro"
) {
  let port;
  try {
    port = api.tabs.connect(tabId, { name: "tts-stream" });
  } catch (e) {
    console.error("Could not connect to page for streaming:", e);
    return;
  }

  const controller = new AbortController();
  let aborted = false;
  port.onDisconnect.addListener(() => {
    aborted = true;
    controller.abort();
  });

  let generateAll = !lookAhead;
  let next = 0; // index of the next segment to generate
  let fetching = false;

  port.onMessage.addListener((msg) => {
    if (!msg || aborted) return;
    if (msg.type === "need_more") {
      // The player is running low on buffered audio.
      pumpSegments();
    } else if (msg.type === "generate_all") {
      // Download was requested: generate the remainder now.
      generateAll = true;
      pumpSegments();
    }
    // "ping" needs no handling — port traffic alone keeps the MV3 service
    // worker from being torn down mid-read while a segment is playing out.
  });

  // The player needs to know whether to ask for more audio, or just wait.
  try {
    port.postMessage({ type: "meta", lookAhead, autoScroll });
  } catch (e) {
    return;
  }

  actionApi?.setBadgeText({ text: "…", tabId });
  actionApi?.setBadgeBackgroundColor({ color: "#3b82f6", tabId });

  async function pumpSegments() {
    if (fetching || aborted || next >= segments.length) return;
    fetching = true;
    try {
      // In unlimited mode keep going; otherwise generate one segment per
      // request from the player.
      do {
        await streamSegment(segments[next]);
        if (aborted) return;
        next += 1;
      } while (generateAll && next < segments.length);
    } catch (error) {
      if (aborted || error.name === "AbortError") return; // user closed the player
      actionApi?.setBadgeText({ text: "!", tabId });
      actionApi?.setBadgeBackgroundColor({ color: "#ef4444", tabId });
      setTimeout(() => actionApi?.setBadgeText({ text: "", tabId }), 2500);
      console.error("TTS stream error:", error);
      try { port.postMessage({ type: "error", message: error.message }); } catch (e) { /* page gone */ }
      api.notifications.create({
        type: "basic",
        iconUrl: "icons/icon128.png",
        title: "TTS Server Error",
        message: `${error.message}. Check that PageVoice Server is running and the server URL is correct.`,
      });
      try { port.disconnect(); } catch (e) { /* page gone */ }
      return;
    } finally {
      fetching = false;
    }

    if (next >= segments.length) {
      actionApi?.setBadgeText({ text: "", tabId });
      try { port.postMessage({ type: "end" }); } catch (e) { /* page gone */ }
      try { port.disconnect(); } catch (e) { /* page gone */ }
    }
  }

  // Generate one segment, forwarding each PCM chunk to the player as it lands.
  async function streamSegment(text) {
    const serverUrl = await getServerUrl();
    const response = await fetch(`${serverUrl}/tts/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice, speed, engine }),
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = "Unknown error";
      try {
        const j = await response.json();
        if (j.detail) detail = j.detail;
      } catch (e) {
        console.error("Failed to parse error response:", e);
      }
      throw new Error(`${response.status} - ${detail}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let completed = false;
    function forward(line) {
      if (!line.trim()) return;
      const obj = JSON.parse(line);
      if (obj.error) throw new Error(obj.error);
      if (obj.done) completed = true;
      else if (obj.pcm_b64) port.postMessage({ ...obj, type: "chunk" });
      else if (obj.type === "sentence_start" || obj.type === "sentence_end") port.postMessage(obj);
    }
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 1);
        forward(line);
        // A per-segment {"done":true} is not the end of the read; the outer
        // loop decides that once every segment has been generated.
      }
    }
    buf += decoder.decode();
    forward(buf);
    if (!completed) throw new Error("Speech stream ended before completion");
  }

  pumpSegments();
}
