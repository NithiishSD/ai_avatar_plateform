import { useEffect, useState, useCallback } from "react";
import "./App.css";

const API_BASE = "http://localhost:8000";

/* ------------------------------------------------------------------ */
/* Model routing hints shown in the UI                                 */
/* ------------------------------------------------------------------ */
const MODE_INFO = {
  fast:         { label: "⚡ Fast (Kokoro 82M)",        hint: "Sub-second English synthesis. Best for real-time use." },
  clone:        { label: "🎤 Voice Clone (XTTS-v2)",    hint: "Zero-shot cloning from a reference recording. Multilingual." },
  high_quality: { label: "🏆 High Quality (Higgs 3B)",  hint: "Ultra-high MOS, multilingual. Slower, GPU-intensive." },
  dialogue:     { label: "💬 Dialogue (Dia 1.6B)",       hint: "Multi-speaker with [S1] / [S2] tags. Great for conversations." },
};

const LANGUAGE_OPTIONS = [
  { value: "en",    label: "English (en)" },
  { value: "en-US", label: "English US (en-US)" },
  { value: "en-GB", label: "English UK (en-GB)" },
  { value: "es",    label: "Spanish (es) → Higgs" },
  { value: "fr",    label: "French (fr) → Higgs" },
  { value: "de",    label: "German (de) → Higgs" },
  { value: "ja",    label: "Japanese (ja) → Higgs" },
  { value: "zh",    label: "Chinese (zh) → Higgs" },
];

const buildSampleRenderJob = () => ({
  jobId: `JOB-${Date.now()}`,
  avatarId: "AVATAR_TEST_01",
  audioUrl: "https://example.com/audio/test.wav",
  sampleRate: 24000,
  durationSeconds: 2.5,
  phonemeTimestamps: [
    { phoneme: "SIL", viseme: "viseme_sil", startMs: 0,    endMs: 250  },
    { phoneme: "EH",  viseme: "viseme_E",   startMs: 250,  endMs: 650  },
    { phoneme: "L",   viseme: "viseme_L",   startMs: 650,  endMs: 950  },
    { phoneme: "OW",  viseme: "viseme_O",   startMs: 950,  endMs: 1400 },
    { phoneme: "SIL", viseme: "viseme_sil", startMs: 1400, endMs: 1800 },
  ],
  emotionVector: { happy: 0.7, neutral: 0.3, eyeblinkRate: 4.5 },
  renderQuality: "1080P_HQ",
  targetFps: 30,
});

function ModelBadge({ modelUsed }) {
  if (!modelUsed) return null;
  const colors = {
    "kokoro":     "#6ee7b7",
    "xtts-v2":    "#93c5fd",
    "higgs-tts-2":"#fbbf24",
    "dia-1.6b":   "#c4b5fd",
  };
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 10px",
      borderRadius: "999px",
      fontSize: "0.75rem",
      fontWeight: 700,
      background: colors[modelUsed] ?? "#4b5563",
      color: "#0f172a",
      marginTop: "0.4rem",
    }}>
      {modelUsed}
    </span>
  );
}

function App() {
  const [text, setText]           = useState("Hello! I am your AI avatar running from the connected backend.");
  const [mode, setMode]           = useState("fast");
  const [language, setLanguage]   = useState("en");
  const [quality, setQuality]     = useState("balanced");
  const [style, setStyle]         = useState("");
  const [speed, setSpeed]         = useState(1.0);
  const [pitch, setPitch]         = useState(1.0);
  const [returnAlignment, setReturnAlignment] = useState(true);
  const [selectedSample, setSelectedSample]   = useState("");

  const [backendStatus, setBackendStatus] = useState("Checking...");
  const [taskId, setTaskId]       = useState("");
  const [taskStatus, setTaskStatus] = useState("idle");
  const [modelUsed, setModelUsed] = useState(null);
  const [jobId, setJobId]         = useState("");
  const [jobStatus, setJobStatus] = useState("idle");
  const [error, setError]         = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [audioUrl, setAudioUrl]   = useState("");
  const [phonemeTimestamps, setPhonemeTimestamps] = useState([]);
  const [activeViseme, setActiveViseme] = useState("viseme_sil");
  const [showTimeline, setShowTimeline] = useState(false);

  // Voice samples from inputs/ folder (for clone mode)
  const [voiceSamples, setVoiceSamples]       = useState([]);
  const [samplesLoading, setSamplesLoading]   = useState(false);
  const [samplesError, setSamplesError]       = useState("");
  const [inputsDir, setInputsDir]             = useState("");
  const [supportedFormats, setSupportedFormats] = useState([]);

  /* ---------- computed predicted model (client-side hint) ----------- */
  const predictedModel = (() => {
    if (mode === "dialogue" || style === "dialogue" || text.includes("[S1]") || text.includes("[S2]")) return "dia-1.6b";
    if (mode === "clone") return "xtts-v2";
    if (mode === "high_quality" || quality === "high") return "higgs-tts-2";
    const lang = language.toLowerCase().replace("_", "-");
    if (!["en", "en-us", "en-gb", "en-au", "en-ca"].includes(lang)) return "higgs-tts-2";
    return "kokoro";
  })();

  /* ---------- backend health check ---------------------------------- */
  const checkBackend = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      if (!res.ok) throw new Error("Backend unavailable");
      const data = await res.json();
      setBackendStatus(`${data.status} (${data.queueBackend})`);
    } catch (err) {
      setBackendStatus("Offline");
      setError(err.message || "Unable to reach backend");
    }
  };

  /* ---------- voice sample scanning --------------------------------- */
  const fetchSamples = useCallback(async () => {
    setSamplesLoading(true);
    setSamplesError("");
    try {
      const res = await fetch(`${API_BASE}/api/v1/audio/samples`);
      if (!res.ok) throw new Error(`Samples request failed: ${res.status}`);
      const data = await res.json();
      setVoiceSamples(data.samples ?? []);
      setInputsDir(data.inputs_dir ?? "");
      setSupportedFormats(data.supported_formats ?? []);
      // Auto-select first sample if none selected
      if (!selectedSample && data.samples?.length > 0) {
        setSelectedSample(data.samples[0].path);
      }
    } catch (err) {
      setSamplesError(err.message || "Could not load voice samples");
    } finally {
      setSamplesLoading(false);
    }
  }, [selectedSample]);

  useEffect(() => { checkBackend(); }, []);

  // Fetch samples when mode switches to clone
  useEffect(() => {
    if (mode === "clone") fetchSamples();
  }, [mode]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ---------- audio playback time synchronization ------------------- */
  const handleAudioTimeUpdate = (e) => {
    const currentMs = e.target.currentTime * 1000;
    if (!phonemeTimestamps || phonemeTimestamps.length === 0) return;
    const current = phonemeTimestamps.find(
      (t) => currentMs >= t.startMs && currentMs < t.endMs
    );
    if (current) {
      setActiveViseme(current.viseme);
    } else {
      setActiveViseme("viseme_sil");
    }
  };

  const handleAudioEnded = () => {
    setActiveViseme("viseme_sil");
  };

  /* ---------- task status polling ----------------------------------- */
  useEffect(() => {
    if (!taskId) return;
    const terminal = ["SUCCESS", "FAILED", "CANCELLED", "UNKNOWN"];
    if (terminal.includes(taskStatus)) return;

    const timer = window.setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/audio/synthesize/${taskId}`);
        if (!res.ok) throw new Error("Task status check failed");
        const payload = await res.json();
        setTaskStatus(payload.status);
        if (payload.modelUsed) setModelUsed(payload.modelUsed);
        if (payload.phonemeTimestamps) setPhonemeTimestamps(payload.phonemeTimestamps);
        if (payload.status === "SUCCESS") {
          setAudioUrl(`${API_BASE}/outputs/speech.wav?t=${Date.now()}`);
        }
      } catch (err) {
        setError(err.message || "Could not poll task status");
      }
    }, 1500);

    return () => window.clearTimeout(timer);
  }, [taskId, taskStatus]);

  /* ---------- synthesis submit -------------------------------------- */
  const handleSynthesize = async (event) => {
    event.preventDefault();
    setError("");
    setAudioUrl("");
    setModelUsed(null);
    setPhonemeTimestamps([]);
    setIsSubmitting(true);

    try {
      const body = {
        text,
        mode,
        language,
        quality,
        speed: parseFloat(speed),
        pitch: parseFloat(pitch),
        returnAlignment,
      };
      if (style) body.style = style;
      // For clone mode, pass the selected input file path
      if (mode === "clone") {
        if (!selectedSample) {
          throw new Error(
            "No voice sample selected. Place a WAV/MP3/FLAC file in inputs/ and refresh the sample list."
          );
        }
        body.speakerWav = selectedSample;
      }

      const res = await fetch(`${API_BASE}/api/v1/audio/synthesize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || `Request failed ${res.status}`);
      if (!payload.taskId) throw new Error("Missing taskId in response");

      setTaskId(payload.taskId);
      const newStatus = payload.status || "QUEUED";
      setTaskStatus(newStatus);
      if (payload.modelUsed) setModelUsed(payload.modelUsed);
      if (payload.phonemeTimestamps) setPhonemeTimestamps(payload.phonemeTimestamps);
      if (newStatus === "SUCCESS") {
        setAudioUrl(`${API_BASE}/outputs/speech.wav?t=${Date.now()}`);
      }
    } catch (err) {
      setError(err.message || "Could not start synthesis");
    } finally {
      setIsSubmitting(false);
    }
  };

  /* ---------- render job with aligned audio ------------------------- */
  const handleCreateRenderJob = async () => {
    setError("");
    try {
      // Use synthesized audio and aligned timestamps if available, otherwise sample
      const timestamps = phonemeTimestamps.length > 0
        ? phonemeTimestamps
        : buildSampleRenderJob().phonemeTimestamps;

      const duration = timestamps.length > 0
        ? timestamps[timestamps.length - 1].endMs / 1000.0
        : 2.5;

      const jobPayload = {
        jobId: `JOB-${Date.now()}`,
        avatarId: "AVATAR_FEMALE_01",
        audioUrl: `${API_BASE}/outputs/speech.wav`,
        sampleRate: 24000,
        durationSeconds: Math.max(duration, 0.5),
        phonemeTimestamps: timestamps,
        emotionVector: { happy: 0.8, neutral: 0.2, eyeblinkRate: 1.2 },
        renderQuality: "1080P_HQ",
        targetFps: 30,
      };

      const res = await fetch(`${API_BASE}/api/v1/avatar/render-job`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(jobPayload),
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || "Render job creation failed");
      setJobId(payload.jobId);
      setJobStatus(payload.status);
    } catch (err) {
      setError(err.message || "Could not create render job");
    }
  };

  /* ---------- render ------------------------------------------------ */
  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>AI Avatar Creator Studio</h1>
          <p>Phase 2 Voice Engine & Forced Alignment Pipeline</p>
        </div>
        <div className="status">
          <span className="status-dot" />
          {backendStatus}
        </div>
      </header>

      <main className="workspace">
        {/* -------- LEFT: Controls -------- */}
        <section className="canvas-panel">
          <div className="panel-header">
            <h2>Voice Synthesis & Prosody Controls</h2>
            <span>Phase 2 Neural Stack</span>
          </div>

          <form className="studio-form" onSubmit={handleSynthesize}>
            <label>
              Text
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={3}
                placeholder="Enter text • Use [S1] / [S2] tags for dialogue mode"
              />
            </label>

            {/* Mode row */}
            <label>
              Synthesis Mode
              <select id="mode-select" value={mode} onChange={(e) => setMode(e.target.value)}>
                {Object.entries(MODE_INFO).map(([val, { label }]) => (
                  <option key={val} value={val}>{label}</option>
                ))}
              </select>
              <span style={{ fontSize: "0.75rem", color: "#9ca3af", marginTop: "4px", display: "block" }}>
                {MODE_INFO[mode]?.hint}
              </span>
            </label>

            {/* Clone mode — voice sample picker from inputs/ */}
            {mode === "clone" && (
              <div style={{
                background: "#1e293b",
                border: "1px solid #334155",
                borderRadius: "10px",
                padding: "14px",
              }}>
                <div style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "10px",
                }}>
                  <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>🎤 Voice Reference Sample</span>
                  <button
                    type="button"
                    id="refresh-samples-btn"
                    onClick={fetchSamples}
                    disabled={samplesLoading}
                    style={{
                      background: "transparent",
                      border: "1px solid #475569",
                      color: "#94a3b8",
                      borderRadius: "6px",
                      padding: "3px 10px",
                      fontSize: "0.75rem",
                      cursor: "pointer",
                    }}
                  >
                    {samplesLoading ? "Scanning…" : "↻ Refresh"}
                  </button>
                </div>

                {samplesError && (
                  <div style={{ color: "#f87171", fontSize: "0.8rem", marginBottom: "8px" }}>
                    {samplesError}
                  </div>
                )}

                {voiceSamples.length === 0 && !samplesLoading ? (
                  <div style={{ fontSize: "0.8rem", color: "#64748b", lineHeight: 1.6 }}>
                    <strong style={{ color: "#f59e0b" }}>No audio files found in inputs/</strong><br />
                    Place a recording in:<br />
                    <code style={{ fontSize: "0.75rem", color: "#94a3b8" }}>{inputsDir || "…/inputs/"}</code><br />
                    <span style={{ marginTop: "6px", display: "block" }}>
                      Supported: {supportedFormats.join(", ") || "WAV, MP3, FLAC, OGG, M4A…"}
                    </span>
                    <span style={{ marginTop: "4px", display: "block", color: "#475569" }}>
                      Ideal: 30–60 s of clean speech. Auto-converted to WAV 24 kHz.
                    </span>
                  </div>
                ) : (
                  <>
                    <select
                      id="sample-select"
                      value={selectedSample}
                      onChange={(e) => setSelectedSample(e.target.value)}
                      style={{ marginBottom: "8px" }}
                    >
                      {voiceSamples.map((s) => (
                        <option key={s.path} value={s.path}>
                          {s.filename} ({s.duration_label}, {s.format.toUpperCase()})
                        </option>
                      ))}
                    </select>

                    {/* Selected sample details */}
                    {(() => {
                      const selected = voiceSamples.find((s) => s.path === selectedSample);
                      if (!selected) return null;
                      return (
                        <div style={{
                          display: "grid",
                          gridTemplateColumns: "1fr 1fr 1fr",
                          gap: "6px",
                          fontSize: "0.72rem",
                          color: "#94a3b8",
                          marginTop: "6px",
                        }}>
                          <div>📏 {selected.duration_label}</div>
                          <div>🎵 {selected.sample_rate > 0 ? `${(selected.sample_rate / 1000).toFixed(1)} kHz` : "—"}</div>
                          <div>📁 {(selected.size_bytes / 1024).toFixed(0)} KB</div>
                          <div style={{ gridColumn: "1/-1", marginTop: "2px" }}>
                            {selected.ready_for_cloning
                              ? <span style={{ color: "#4ade80" }}>✅ Ready (WAV 24 kHz mono)</span>
                              : <span style={{ color: "#fbbf24" }}>⚡ Will auto-convert on synthesis</span>}
                          </div>
                        </div>
                      );
                    })()}
                  </>
                )}
              </div>
            )}

            <div className="grid-two">
              <label>
                Language
                <select id="language-select" value={language} onChange={(e) => setLanguage(e.target.value)}>
                  {LANGUAGE_OPTIONS.map(({ value, label }) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>

              <label>
                Quality
                <select id="quality-select" value={quality} onChange={(e) => setQuality(e.target.value)}>
                  <option value="fast">fast</option>
                  <option value="balanced">balanced</option>
                  <option value="high">high → Higgs</option>
                </select>
              </label>
            </div>

            {/* Prosody controls: Speed & Pitch */}
            <div className="grid-two" style={{ marginTop: "4px" }}>
              <label>
                Speed / Rhythm: <span style={{ color: "#38bdf8", fontWeight: "bold" }}>{speed}x</span>
                <input
                  type="range"
                  min="0.6"
                  max="1.6"
                  step="0.05"
                  value={speed}
                  onChange={(e) => setSpeed(e.target.value)}
                  style={{ width: "100%", accentColor: "#38bdf8" }}
                />
              </label>

              <label>
                Pitch Shift: <span style={{ color: "#38bdf8", fontWeight: "bold" }}>{pitch}x</span>
                <input
                  type="range"
                  min="0.7"
                  max="1.4"
                  step="0.05"
                  value={pitch}
                  onChange={(e) => setPitch(e.target.value)}
                  style={{ width: "100%", accentColor: "#38bdf8" }}
                />
              </label>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "8px", margin: "6px 0" }}>
              <input
                type="checkbox"
                id="alignment-checkbox"
                checked={returnAlignment}
                onChange={(e) => setReturnAlignment(e.target.checked)}
                style={{ width: "auto", cursor: "pointer" }}
              />
              <label htmlFor="alignment-checkbox" style={{ fontSize: "0.82rem", color: "#e2e8f0", cursor: "pointer", margin: 0 }}>
                ⚡ Extract Millisecond Phoneme & Viseme Timestamps
              </label>
            </div>

            <label>
              Style <span style={{ fontSize: "0.75rem", color: "#6b7280" }}>(optional)</span>
              <select id="style-select" value={style} onChange={(e) => setStyle(e.target.value)}>
                <option value="">— none —</option>
                <option value="dialogue">dialogue (multi-speaker)</option>
                <option value="expressive">expressive</option>
                <option value="narration">narration</option>
              </select>
            </label>

            {/* Predicted model hint */}
            <div style={{
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: "8px",
              padding: "10px 14px",
              fontSize: "0.8rem",
              color: "#94a3b8",
              marginBottom: "4px",
            }}>
              🤖 Router will select: <ModelBadge modelUsed={predictedModel} />
            </div>

            <div className="controls">
              <button type="submit" id="generate-btn" disabled={isSubmitting}>
                {isSubmitting ? "Synthesizing..." : "Generate Speech"}
              </button>
              <button
                type="button"
                id="render-job-btn"
                className="secondary"
                onClick={handleCreateRenderJob}
                title="Create avatar video rendering job using synthesized audio and phoneme timestamps"
              >
                Create Render Job
              </button>
            </div>
          </form>

          {error ? <div className="alert error">{error}</div> : null}
        </section>

        {/* -------- RIGHT: Status & Viseme Visualizer panel -------- */}
        <section className="info-panel">
          <h2>Synthesis & Lip-Sync Status</h2>

          <div className="info-card">
            <label>Task ID</label>
            <strong>{taskId || "Not started"}</strong>
          </div>

          <div className="info-card">
            <label>Task Status</label>
            <strong>{taskStatus}</strong>
          </div>

          <div className="info-card">
            <label>Model Used</label>
            {modelUsed
              ? <ModelBadge modelUsed={modelUsed} />
              : <strong style={{ color: "#4b5563" }}>—</strong>
            }
          </div>

          {/* Viseme / Facial Shape Indicator */}
          <div className="info-card" style={{
            background: "linear-gradient(135deg, #1e293b, #0f172a)",
            border: "1px solid #3b82f6",
          }}>
            <label style={{ color: "#60a5fa" }}>👄 Live Viseme Sync</label>
            <div style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginTop: "6px",
            }}>
              <span style={{
                fontSize: "1.1rem",
                fontWeight: "bold",
                color: activeViseme === "viseme_sil" ? "#64748b" : "#38bdf8",
              }}>
                {activeViseme}
              </span>
              <span style={{
                padding: "2px 8px",
                borderRadius: "4px",
                fontSize: "0.72rem",
                background: activeViseme === "viseme_sil" ? "#334155" : "#1d4ed8",
                color: "#f8fafc",
              }}>
                {activeViseme === "viseme_sil" ? "Rest / Silence" : "Active Speaking"}
              </span>
            </div>
          </div>

          {/* Phoneme timestamps timeline */}
          {phonemeTimestamps && phonemeTimestamps.length > 0 && (
            <div className="info-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <label>Aligned Phonemes ({phonemeTimestamps.length})</label>
                <button
                  type="button"
                  onClick={() => setShowTimeline(!showTimeline)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "#38bdf8",
                    fontSize: "0.75rem",
                    cursor: "pointer",
                    textDecoration: "underline",
                  }}
                >
                  {showTimeline ? "Hide Details" : "Show Details"}
                </button>
              </div>

              {showTimeline && (
                <div style={{
                  maxHeight: "130px",
                  overflowY: "auto",
                  marginTop: "8px",
                  fontSize: "0.72rem",
                  background: "#0f172a",
                  padding: "6px",
                  borderRadius: "6px",
                  border: "1px solid #334155",
                }}>
                  {phonemeTimestamps.map((t, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        padding: "2px 4px",
                        borderBottom: "1px solid #1e293b",
                        color: activeViseme === t.viseme ? "#38bdf8" : "#94a3b8",
                      }}
                    >
                      <span><strong>{t.phoneme}</strong> → {t.viseme}</span>
                      <span>{t.startMs}ms - {t.endMs}ms</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="info-card">
            <label>Render Job ID</label>
            <strong>{jobId || "Not created"}</strong>
          </div>

          <div className="info-card">
            <label>Render Job Status</label>
            <strong>{jobStatus}</strong>
          </div>

          <div className="info-card">
            <label>Output Audio</label>
            <strong>
              {taskStatus === "SUCCESS"
                ? "Audio & Lip-Sync Ready"
                : taskStatus === "FAILED"
                ? "Generation failed"
                : taskStatus === "QUEUED" || taskStatus === "PROCESSING"
                ? "Generating speech & alignment…"
                : "Waiting for generation"}
            </strong>
            {audioUrl ? (
              <div style={{ marginTop: "0.75rem" }}>
                <audio
                  controls
                  src={audioUrl}
                  style={{ width: "100%" }}
                  onTimeUpdate={handleAudioTimeUpdate}
                  onEnded={handleAudioEnded}
                  onPause={handleAudioEnded}
                >
                  Your browser does not support audio playback.
                </audio>
                <div style={{ marginTop: "0.35rem", fontSize: "0.8rem", color: "#9ca3af" }}>
                  outputs/speech.wav
                </div>
              </div>
            ) : null}
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;

