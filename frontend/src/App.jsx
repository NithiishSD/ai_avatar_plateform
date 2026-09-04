import { useEffect, useState } from "react";
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

  const [backendStatus, setBackendStatus] = useState("Checking...");
  const [taskId, setTaskId]       = useState("");
  const [taskStatus, setTaskStatus] = useState("idle");
  const [modelUsed, setModelUsed] = useState(null);
  const [jobId, setJobId]         = useState("");
  const [jobStatus, setJobStatus] = useState("idle");
  const [error, setError]         = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [audioUrl, setAudioUrl]   = useState("");

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

  useEffect(() => { checkBackend(); }, []);

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
    setIsSubmitting(true);

    try {
      const body = { text, mode, language, quality };
      if (style) body.style = style;

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
      if (newStatus === "SUCCESS") {
        setAudioUrl(`${API_BASE}/outputs/speech.wav?t=${Date.now()}`);
      }
    } catch (err) {
      setError(err.message || "Could not start synthesis");
    } finally {
      setIsSubmitting(false);
    }
  };

  /* ---------- render job -------------------------------------------- */
  const handleCreateRenderJob = async () => {
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/v1/avatar/render-job`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildSampleRenderJob()),
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
          <p>Live frontend connected to the Python backend</p>
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
            <h2>Voice Synthesis Controls</h2>
            <span>Backend sync enabled</span>
          </div>

          <form className="studio-form" onSubmit={handleSynthesize}>
            <label>
              Text
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={4}
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
                {isSubmitting ? "Submitting..." : "Generate Speech"}
              </button>
              <button type="button" id="render-job-btn" className="secondary" onClick={handleCreateRenderJob}>
                Create Render Job
              </button>
            </div>
          </form>

          {error ? <div className="alert error">{error}</div> : null}
        </section>

        {/* -------- RIGHT: Status panel -------- */}
        <section className="info-panel">
          <h2>Synthesis Status</h2>

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

          <div className="info-card">
            <label>Render Job ID</label>
            <strong>{jobId || "Not created"}</strong>
          </div>

          <div className="info-card">
            <label>Render Job Status</label>
            <strong>{jobStatus}</strong>
          </div>

          <div className="info-card">
            <label>Output</label>
            <strong>
              {taskStatus === "SUCCESS"
                ? "Audio generated successfully"
                : taskStatus === "FAILED"
                ? "Generation failed"
                : taskStatus === "QUEUED" || taskStatus === "PROCESSING"
                ? "Generating speech…"
                : "Waiting for generation"}
            </strong>
            {audioUrl ? (
              <div style={{ marginTop: "0.75rem" }}>
                <audio controls src={audioUrl} style={{ width: "100%" }}>
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
