import { useEffect, useState } from "react";
import { api } from "./api.js";
import Workspace from "./views/Workspace.jsx";
import Evaluation from "./views/Evaluation.jsx";
import History from "./views/History.jsx";

const initial = () => ({
  files: [{ name: "submission_1.py", code: "" }], active: 0,
  options: { run_ai: true, run_plagiarism: true, run_vulnerability: true, compare_corpus: false, persist: false, explain: true },
  job: { status: "idle", report: null, error: null }, ranCode: {},
});

export default function App() {
  const [view, setView] = useState("workspace");
  const [ws, setWs] = useState(initial);
  const [health, setHealth] = useState(null);
  useEffect(() => { api.health().then(setHealth).catch(() => setHealth(false)); }, [view]);
  const m = health?.models;
  const open = (job) => {
    // Re-open a stored report: the code is not retained unless it was saved, so only the report is shown.
    setWs((s) => ({ ...s, job: { status: "done", report: job.result, error: null, id: job.id }, ranCode: {} }));
    setView("workspace");
  };
  return (
    <div className="app">
      <header className="top">
        <span className="brand">Code<i>Guard</i></span>
        <nav className="nav" aria-label="Main">
          {[["workspace", "Workspace"], ["history", "History"], ["evaluation", "Evaluation"]].map(([k, l]) => (
            <button key={k} aria-current={view === k ? "page" : undefined} onClick={() => setView(k)}>{l}</button>
          ))}
        </nav>
        <div className="status" aria-label="Model status">
          {health === false && <span><span className="dot" />API offline</span>}
          {m && <>
            <span><span className={`dot ${m.xgboost.available ? "on" : ""}`} />XGBoost</span>
            <span><span className={`dot ${m.codebert.available ? "on" : ""}`} />CodeBERT</span>
          </>}
        </div>
      </header>
      <main style={{ minHeight: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        <div style={{ display: view === "workspace" ? "flex" : "none", flex: 1, minHeight: 0 }}><Workspace ws={ws} setWs={setWs} /></div>
        {view === "history" && <div style={{ overflow: "auto" }}><History onOpen={open} /></div>}
        {view === "evaluation" && <div style={{ overflow: "auto" }}><Evaluation /></div>}
      </main>
    </div>
  );
}
