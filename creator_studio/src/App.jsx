import { useEffect, useState } from "react";
import "./App.css";

const mockVisemes = [
  {
    phoneme: "SIL",
    viseme: "viseme_sil",
    startMs: 0,
    endMs: 300,
    mouthState: "closed",
  },
  {
    phoneme: "EH",
    viseme: "viseme_E",
    startMs: 300,
    endMs: 700,
    mouthState: "E_shape",
  },
  {
    phoneme: "L",
    viseme: "viseme_L",
    startMs: 700,
    endMs: 1000,
    mouthState: "L_shape",
  },
  {
    phoneme: "OW",
    viseme: "viseme_O",
    startMs: 1000,
    endMs: 1500,
    mouthState: "O_shape",
  },
  {
    phoneme: "SIL",
    viseme: "viseme_sil",
    startMs: 1500,
    endMs: 2000,
    mouthState: "closed",
  },
];

function App() {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  const currentViseme = mockVisemes[currentIndex];

  useEffect(() => {
    if (!isPlaying) {
      return;
    }

    const timer = setTimeout(() => {
      if (currentIndex < mockVisemes.length - 1) {
        setCurrentIndex(currentIndex + 1);
      } else {
        setIsPlaying(false);
      }
    }, currentViseme.endMs - currentViseme.startMs);

    return () => clearTimeout(timer);
  }, [isPlaying, currentIndex, currentViseme]);

  const playMockRender = () => {
    setCurrentIndex(0);
    setIsPlaying(true);
  };

  const resetRender = () => {
    setIsPlaying(false);
    setCurrentIndex(0);
  };

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>AI Avatar Creator Studio</h1>
          <p>Phase 0 • Mock Avatar Renderer</p>
        </div>

        <div className="status">
          <span className="status-dot"></span>
          Vision Pipeline Ready
        </div>
      </header>

      <main className="workspace">
        <section className="canvas-panel">
          <div className="panel-header">
            <h2>Live Canvas</h2>
            <span>30 FPS</span>
          </div>

          <div className="avatar-canvas">
            <div className="avatar-bounding-box">
              <div className="avatar-face">
                <div className="eyes">
                  <span></span>
                  <span></span>
                </div>

                <div className={`mouth ${currentViseme.mouthState}`}>
                  {currentViseme.mouthState === "closed" && <span></span>}
                  {currentViseme.mouthState === "E_shape" && <span>e</span>}
                  {currentViseme.mouthState === "L_shape" && <span>l</span>}
                  {currentViseme.mouthState === "O_shape" && <span>o</span>}
                </div>
              </div>

              <div className="box-label">Avatar Bounding Box</div>
            </div>
          </div>

          <div className="controls">
            <button onClick={playMockRender}>
              ▶ Play Mock Render
            </button>

            <button className="secondary" onClick={resetRender}>
              ↻ Reset
            </button>
          </div>
        </section>

        <section className="info-panel">
          <h2>Render Information</h2>

          <div className="info-card">
            <label>Job ID</label>
            <strong>MOCK-001</strong>
          </div>

          <div className="info-card">
            <label>Avatar ID</label>
            <strong>AVATAR_TEST_01</strong>
          </div>

          <div className="info-card">
            <label>Current Phoneme</label>
            <strong>{currentViseme.phoneme}</strong>
          </div>

          <div className="info-card">
            <label>Current Viseme</label>
            <strong>{currentViseme.viseme}</strong>
          </div>

          <div className="info-card">
            <label>Mouth State</label>
            <strong>{currentViseme.mouthState}</strong>
          </div>

          <div className="info-card">
            <label>Timestamp</label>
            <strong>
              {currentViseme.startMs} - {currentViseme.endMs} ms
            </strong>
          </div>

          <div className="info-card">
            <label>Render Quality</label>
            <strong>1080P_HQ</strong>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;