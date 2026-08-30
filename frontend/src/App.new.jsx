import { useEffect, useState } from "react";
import "./App.css";

const API_BASE = "http://localhost:8000";

const buildSampleRenderJob = () => ({
  jobId: `JOB-${Date.now()}`,
  avatarId: "AVATAR_TEST_01",
  audioUrl: "https://example.com/audio/test.wav",
  sampleRate: 24000,
  durationSeconds: 2.5,
  phonemeTimestamps: [
    { phoneme: "SIL", viseme: "viseme_sil", startMs: 0, endMs: 250 },
    { phoneme: "EH", viseme: "viseme_E", startMs: 250, endMs: 650 },
    { phoneme: "L", viseme: "viseme_L", startMs: 650, endMs: 950 },
    { phoneme: "OW", viseme: "viseme_O", startMs: 950, endMs: 1400 },
    { phoneme: "SIL", viseme: "viseme_sil", startMs: 1400, endMs: 1800 },
  ],
  emotionVector: {
    happy: 0.7,
    neutral: 0.3,
    eyeblinkRate: 4.5,
  },
  renderQuality: "1080P_HQ",
  targetFps: 30,
});

function App() {
  const [text, setText] = useState("Hello! I am your AI avatar running from the connected backend.");
  const [mode, setMode] = useState("fast");
  const [language, setLanguage] = useState("en");
  const [quality, setQuality] = useState("balanced");
  const [backendStatus, setBackendStatus] = useState("Checking...");
  const [taskId, setTaskId] = useState("");
  const [taskStatus, setTaskStatus] = useState("idle");
  const [jobId, setJobId] = useState("");
  const [jobStatus, setJobStatus] = useState("idle");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const checkBackend = async () => {
    try {
      const response = await fetch(`${API_BASE}/health`);
      if (!response.ok) throw new Error("Backend unavailable");
      const data = await response.json();
      setBackendStatus(`${data.status} (${data.queueBackend})`);
    } catch (err) {
      setBackendStatus("Offline");
      setError(err.message || "Unable to reach backend");
    }
  };

  useEffect(() => {
    checkBackend();
  }, []);

  useEffect(() => {
    if (!taskId) return;
    if (!["PENDING", "STARTED", "RETRY", "QUEUED"].includes(taskStatus)) return;

    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/audio/synthesize/${taskId}`);
        if (!response.ok) throw new Error("Task status check failed");
        const payload = await response.json();
        setTaskStatus(payload.status);
      } catch (err) {
        setError(err.message || "Could not poll task status");
      }
    }, 1500);

    return () => window.clearTimeout(timer);
  }, [taskId, taskStatus]);

  const handleSynthesize = async (event) => {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      const response = await fetch(`${API_BASE}/api/v1/audio/synthesize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, mode, language, quality }),
      });

      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Synthesis request failed");

      setTaskId(payload.taskId);
      setTaskStatus(payload.status);
    } catch (err) {
      setError(err.message || "Could not start synthesis");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateRenderJob = async () => {
    setError("");
    try {
      const job = buildSampleRenderJob();
      const response = await fetch(`${API_BASE}/api/v1/avatar/render-job`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(job),
      });

      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Render job creation failed");

      setJobId(payload.jobId);
      setJobStatus(payload.status);
    } catch (err) {
      setError(err.message || "Could not create render job");
    }
  };

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
        <section className="canvas-panel">
          <div className="panel-header">
            <h2>Avatar Controls</h2>
            <span>Backend sync enabled</span>
          </div>

          <form className="studio-form" onSubmit={handleSynthesize}>
            <label>
              Text
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value)}
                rows={4}
                placeholder="Enter text for the avatar to say"
              />
            </label>

            <div className="grid-two">
              <label>
                Mode
                <select value={mode} onChange={(event) => setMode(event.target.value)}>
                  <option value="fast">fast</option>
                  <option value="clone">clone</option>
                </select>
              </label>

              <label>
                Language
                <select value={language} onChange={(event) => setLanguage(event.target.value)}>
                  <option value="en">en</option>
                  <option value="en-US">en-US</option>
                  <option value="en-GB">en-GB</option>
                </select>
              </label>
            </div>

            <label>
              Quality
              <select value={quality} onChange={(event) => setQuality(event.target.value)}>
                <option value="fast">fast</option>
                <option value="balanced">balanced</option>
                <option value="high">high</option>
              </select>
            </label>

            <div className="controls">
              <button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Submitting..." : "Generate Speech"}
              </button>

              <button type="button" className="secondary" onClick={handleCreateRenderJob}>
                Create Render Job
              </button>
            </div>
          </form>

          {error ? <div className="alert error">{error}</div> : null}
        </section>

        <section className="info-panel">
          <h2>Backend Status</h2>

          <div className="info-card">
            <label>Task ID</label>
            <strong>{taskId || "Not started"}</strong>
          </div>

          <div className="info-card">
            <label>Task Status</label>
            <strong>{taskStatus}</strong>
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
            <label>Mode</label>
            <strong>{mode}</strong>
          </div>

          <div className="info-card">
            <label>Output</label>
            <strong>{taskStatus === "SUCCESS" ? "Audio file created" : "Waiting for generation"}</strong>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
