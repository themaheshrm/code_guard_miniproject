import { Suspense, lazy, useEffect, useState } from "react";
import { BookOpenCheck, BrainCircuit, Code2, FileClock, LayoutDashboard, Menu, Moon, ShieldHalf, Sun, X } from "lucide-react";
import { api } from "./api.js";
import { ThemeCtx } from "./charts.jsx";
import { useLocal, useRoute, useTheme } from "./hooks.js";
import { cx } from "./ui.jsx";
import Dashboard from "./views/Dashboard.jsx";
import History from "./views/History.jsx";
import Models from "./views/Models.jsx";
import Rules from "./views/Rules.jsx";

const Workspace = lazy(() => import("./views/Workspace.jsx"));
const ReportPage = lazy(() => import("./views/ReportPage.jsx"));

const NAV = [
  ["dashboard", "Dashboard", LayoutDashboard, "Overview of every analysis"],
  ["analyze", "Analyze", Code2, "Paste or upload code"],
  ["history", "Reports", FileClock, "History & saved corpus"],
  ["models", "Models", BrainCircuit, "Engines, training & evaluation"],
  ["rules", "Rules", BookOpenCheck, "Vulnerability rule catalogue"],
];

export const DEFAULT_OPTIONS = { run_ai: true, run_plagiarism: true, run_vulnerability: true, compare_corpus: false, persist: false, explain: true };
const initialWs = () => ({ files: [{ name: "submission_1.py", code: "" }], active: 0, options: DEFAULT_OPTIONS, title: "" });

function Loading() {
  return <div className="page-loading"><span className="spin lg" /> Loading…</div>;
}

export default function App() {
  const [route, go] = useRoute("dashboard");
  const [theme, toggleTheme] = useTheme();
  const [saved, setSaved] = useLocal("cg.workspace.v2", initialWs);
  const [job, setJob] = useState({ status: "idle", report: null, error: null, ranCode: {} });
  const [health, setHealth] = useState(null);
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = () => api.health().then((h) => alive && setHealth(h)).catch(() => alive && setHealth(false));
    tick();
    const t = setInterval(tick, 20000);
    return () => { alive = false; clearInterval(t); };
  }, [route.page]);
  useEffect(() => { setNavOpen(false); window.scrollTo(0, 0); }, [route.page, route.arg]);

  const loadIntoWorkspace = (files, title = "") => {
    setSaved((s) => ({ ...s, files, active: 0, title }));
    setJob({ status: "idle", report: null, error: null, ranCode: {} });
    go("analyze");
  };
  const m = health?.models;
  const page = NAV.find((n) => n[0] === route.page) || (route.page === "report" ? ["report", "Report", FileClock, "Analysis report"] : NAV[0]);

  return (
    <ThemeCtx.Provider value={theme}>
      <div className={cx("shell", navOpen && "nav-open")}>
        <aside className="side" aria-label="Main navigation">
          <div className="brand" onClick={() => go("dashboard")} role="link" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && go("dashboard")}>
            <span className="logo"><ShieldHalf size={20} aria-hidden /></span>
            <span><b>CodeGuard</b><small>Code integrity AI</small></span>
          </div>
          <nav>
            {NAV.map(([k, label, Icon, hint]) => (
              <a key={k} href={`#/${k}`} className="nav-i" aria-current={route.page === k || (k === "history" && route.page === "report") ? "page" : undefined} title={hint}>
                <Icon size={18} aria-hidden /><span>{label}</span>
                {k === "analyze" && (job.status === "queued" || job.status === "running") && <span className="pulse" aria-label="analysis running" />}
              </a>
            ))}
          </nav>
          <div className="side-foot">
            <div className="eng-title">Detection engines</div>
            {health === false && <div className="eng off"><span className="dot" />API offline</div>}
            {health == null && <div className="eng"><span className="dot" />Connecting…</div>}
            {m && <>
              <div className={cx("eng", m.heuristic.available && "on")}><span className="dot" />Heuristic stylometry</div>
              <div className={cx("eng", m.xgboost.available && "on")}><span className="dot" />XGBoost {m.xgboost.available ? "" : "· untrained"}</div>
              <div className={cx("eng", m.codebert.available && "on")}><span className="dot" />CodeBERT {m.codebert.available ? "" : "· optional"}</div>
              <div className="eng on"><span className="dot" />{health.rules} security rules</div>
            </>}
          </div>
        </aside>
        <div className="side-scrim" onClick={() => setNavOpen(false)} />
        <div className="main">
          <header className="top">
            <button className="iconbtn menu" onClick={() => setNavOpen((v) => !v)} aria-label="Toggle navigation">{navOpen ? <X size={20} /> : <Menu size={20} />}</button>
            <div className="top-t"><h1>{page[1]}</h1><span className="muted">{page[3]}</span></div>
            <div className="top-r">
              <span className={cx("api-pill", health ? "ok" : health === false ? "bad" : "")} title={health ? `API v${health.version}` : "API status"}>
                <span className="dot" />{health ? "API online" : health === false ? "API offline" : "Connecting"}
              </span>
              <button className="iconbtn" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} title="Toggle theme">
                {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
              </button>
            </div>
          </header>
          <main className={cx("content", route.page === "analyze" && "content-ws")} key={route.page === "analyze" ? "ws" : route.page + (route.arg || "")}>
            <Suspense fallback={<Loading />}>
              {route.page === "dashboard" && <Dashboard go={go} health={health} onExample={loadIntoWorkspace} />}
              {route.page === "analyze" && <Workspace ws={saved} setWs={setSaved} job={job} setJob={setJob} theme={theme} go={go} health={health} />}
              {route.page === "history" && <History go={go} onLoad={loadIntoWorkspace} />}
              {route.page === "report" && <ReportPage id={route.arg} go={go} theme={theme} />}
              {route.page === "models" && <Models onHealth={setHealth} />}
              {route.page === "rules" && <Rules />}
            </Suspense>
          </main>
        </div>
      </div>
    </ThemeCtx.Provider>
  );
}
