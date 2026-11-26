import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { ToastProvider } from "./ui.jsx";
import "./styles.css";

// Apply the saved theme before first paint (no inline script: the CSP forbids it).
try { document.documentElement.dataset.theme = JSON.parse(localStorage.getItem("cg.theme")) || "dark"; } catch { document.documentElement.dataset.theme = "dark"; }

class Boundary extends React.Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error, info) { console.error("CodeGuard UI error", error, info); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="crash">
        <h1>Something went wrong</h1>
        <p>{String(this.state.error.message || this.state.error)}</p>
        <button className="btn primary" onClick={() => { this.setState({ error: null }); window.location.hash = "/dashboard"; }}>Back to dashboard</button>
        <button className="btn ghost" onClick={() => { try { localStorage.removeItem("cg.workspace.v2"); } catch { /* ignore */ } window.location.reload(); }}>Reset workspace & reload</button>
      </div>
    );
  }
}

createRoot(document.getElementById("root")).render(<React.StrictMode><Boundary><ToastProvider><App /></ToastProvider></Boundary></React.StrictMode>);
