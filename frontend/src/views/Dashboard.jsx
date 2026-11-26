import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, ArrowRight, Bot, BrainCircuit, Bug, Copy, FileCode2, FlaskConical, Gauge, Languages, ListChecks, RefreshCw, ShieldAlert, Sparkles } from "lucide-react";
import { api } from "../api.js";
import { ChartTip, LegendRow, axisProps, useColors } from "../charts.jsx";
import { useAsync } from "../hooks.js";
import { EXAMPLES, LANG_LABEL, LEVEL, pct, timeAgo } from "../lib.js";
import { Badge, Button, Card, Empty, ErrorBox, Skeleton, Stat } from "../ui.jsx";

const dayLabel = (d) => new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export default function Dashboard({ go, health, onExample }) {
  const c = useColors();
  const { data: st, error, loading, reload } = useAsync(() => api.stats(14), []);

  if (error) return <div className="page"><ErrorBox onRetry={reload}>{error}</ErrorBox></div>;
  const t = st?.totals;
  const empty = st && t.analyses === 0;

  return (
    <div className="page stack">
      <section className="hero">
        <div className="hero-txt">
          <Badge tone="ai" icon={Sparkles}>AI · Plagiarism · Security</Badge>
          <h2>Know where your code came from — and where it’s weak.</h2>
          <p>One pass flags AI-generated code, finds copying that survives renaming and reordering, and pinpoints insecure lines with CWE-tagged fixes.</p>
          <div className="row-wrap">
            <Button variant="primary" icon={ArrowRight} onClick={() => go("analyze")}>Start an analysis</Button>
            <Button icon={FlaskConical} onClick={() => onExample(EXAMPLES[0].files, EXAMPLES[0].title)}>Try the demo</Button>
          </div>
        </div>
        <div className="hero-art" aria-hidden>
          <div className="orb o1" /><div className="orb o2" /><div className="orb o3" />
          <div className="hero-card"><Bot size={18} /><span>AI likelihood</span><b>87%</b></div>
          <div className="hero-card c2"><Copy size={18} /><span>Similarity</span><b>94%</b></div>
          <div className="hero-card c3"><ShieldAlert size={18} /><span>CWE-78</span><b>High</b></div>
        </div>
      </section>

      <div className="stats-grid">
        {loading && !st ? [0, 1, 2, 3].map((i) => <Skeleton key={i} h={108} />) : <>
          <Stat icon={ListChecks} label="Analyses" value={t.analyses} sub={`${t.files} files scanned${t.failed ? ` · ${t.failed} failed` : ""}`} />
          <Stat icon={Bot} tone="ai" label="Likely AI-generated" value={t.ai_flagged} sub={st.ai_mean != null ? `mean likelihood ${pct(st.ai_mean)}` : "no AI scores yet"} />
          <Stat icon={Copy} tone="sim" label="Similar pairs" value={t.similar_pairs} sub={`${st.corpus_size} files in saved corpus`} />
          <Stat icon={ShieldAlert} tone="sec" label="Security findings" value={t.findings} sub={`${t.high_risk_files} high-risk file(s)`} />
        </>}
      </div>

      {empty && (
        <Card>
          <Empty icon={Activity} title="No analyses yet" action={
            <div className="row-wrap center">{EXAMPLES.map((ex) => <Button key={ex.id} icon={FlaskConical} onClick={() => onExample(ex.files, ex.title)}>{ex.title}</Button>)}</div>}>
            Charts appear here after your first analysis. Load a demo set to see CodeGuard in action.
          </Empty>
        </Card>
      )}

      {st && !empty && <>
        <div className="grid-2-1">
          <Card title="Activity — last 14 days" icon={Activity} actions={<Button size="sm" icon={RefreshCw} onClick={reload} aria-label="Refresh" />}>
            <LegendRow items={[["Files analyzed", c.s1], ["Files flagged", c.sim]]} />
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={st.timeline} margin={{ top: 8, right: 8, left: -18, bottom: 0 }} barGap={2} barCategoryGap="22%">
                <CartesianGrid vertical={false} stroke={c.grid} />
                <XAxis dataKey="date" tickFormatter={dayLabel} {...axisProps(c)} minTickGap={24} />
                <YAxis allowDecimals={false} {...axisProps(c)} />
                <Tooltip content={<ChartTip labelFmt={dayLabel} />} cursor={{ fill: c.grid }} />
                <Bar dataKey="files" name="Files analyzed" fill={c.s1} radius={[4, 4, 0, 0]} maxBarSize={14} />
                <Bar dataKey="flagged" name="Files flagged" fill={c.sim} radius={[4, 4, 0, 0]} maxBarSize={14} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
          <Card title="Verdicts" icon={Gauge}>
            <Donut data={[["Clear", st.verdicts.clear, c.good], ["Attention", st.verdicts.attention, c.warn], ["Review", st.verdicts.review, c.bad]]} />
          </Card>
        </div>

        <div className="grid-3">
          <Card title="Findings by severity" icon={Bug}>
            <HBars data={[["Critical", st.severity.critical, c.crit], ["High", st.severity.high, c.bad], ["Medium", st.severity.medium, c.warn], ["Low", st.severity.low, c.axis]]} />
          </Card>
          <Card title="Top weaknesses (CWE)" icon={ShieldAlert}>
            {st.top_cwes.length ? <HBars data={st.top_cwes.slice(0, 6).map((x) => [x.cwe, x.count, c.sec])} link /> : <p className="muted small">No findings yet.</p>}
          </Card>
          <Card title="Languages" icon={Languages}>
            {Object.keys(st.languages).length ? <HBars data={Object.entries(st.languages).map(([k, v]) => [LANG_LABEL[k] || k, v, c.s1])} /> : <p className="muted small">No files yet.</p>}
          </Card>
        </div>
      </>}

      <div className="grid-2-1">
        <Card title="Recent reports" icon={FileCode2} actions={<Button size="sm" onClick={() => go("history")}>View all</Button>} pad={false}>
          {!st ? <div className="card-b"><Skeleton h={160} /></div> : st.recent.length === 0 ? <div className="card-b"><p className="muted small">Your latest analyses will be listed here.</p></div> : (
            <ul className="recent">
              {st.recent.map((r) => {
                const L = LEVEL[r.summary.level];
                return (
                  <li key={r.id}><button onClick={() => go("report", r.id)}>
                    <span className={`lv lv-${r.summary.level}`} aria-hidden />
                    <span className="grow"><b>{r.title || "Untitled"}</b><small className="muted">{r.n_files} file{r.n_files > 1 ? "s" : ""} · {timeAgo(r.created_at)}</small></span>
                    <span className="recent-m">
                      {r.summary.ai_max != null && <span title="max AI likelihood" className="t-ai"><Bot size={13} aria-hidden />{pct(r.summary.ai_max)}</span>}
                      <span title="max similarity" className="t-sim"><Copy size={13} aria-hidden />{pct(r.summary.max_similarity)}</span>
                      <span title="security findings" className="t-sec"><ShieldAlert size={13} aria-hidden />{r.summary.findings}</span>
                    </span>
                    <Badge tone={L.tone}>{L.label}</Badge>
                  </button></li>
                );
              })}
            </ul>
          )}
        </Card>
        <Card title="Engine status" icon={BrainCircuit} actions={<Button size="sm" onClick={() => go("models")}>Manage</Button>}>
          {!health ? <p className="muted small">{health === false ? "API offline." : "Checking…"}</p> : (
            <ul className="engine-list">
              <EngineRow name="Heuristic stylometry" on={health.models.heuristic.available} note="always on · explainable" />
              <EngineRow name="XGBoost (45 features)" on={health.models.xgboost.available} note={health.models.xgboost.available ? "trained" : "train from Models page"} />
              <EngineRow name="CodeBERT" on={health.models.codebert.available} note={health.models.codebert.available ? "fine-tuned" : "optional · GPU"} />
              <EngineRow name="Winnowing + AST plagiarism" on note="5 languages" />
              <EngineRow name="Static security rules" on note={`${health.rules} CWE-tagged rules`} />
              <EngineRow name="Tree-sitter parsers" on={Object.values(health.parsers).every((p) => p.available)}
                note={`${Object.values(health.parsers).filter((p) => p.available).length}/5 grammars`} />
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function EngineRow({ name, on, note }) {
  return <li><span className={`dot ${on ? "on" : ""}`} aria-hidden /><span className="grow">{name}</span><Badge tone={on ? "good" : "neutral"} icon={false}>{on ? "active" : "off"}</Badge><small className="muted">{note}</small></li>;
}

function Donut({ data }) {
  const c = useColors();
  const total = data.reduce((s, d) => s + d[1], 0);
  const rows = data.map(([name, value, color]) => ({ name, value, color }));
  return (
    <div className="donut">
      <div className="donut-chart">
        <ResponsiveContainer width="100%" height={180}>
          <PieChart>
            <Pie data={total ? rows : [{ name: "none", value: 1, color: c.grid }]} dataKey="value" innerRadius={58} outerRadius={80} paddingAngle={total ? 2 : 0}
              stroke={c.surface} strokeWidth={2} startAngle={90} endAngle={-270} isAnimationActive>
              {(total ? rows : [{ color: c.grid }]).map((d, i) => <Cell key={i} fill={d.color} />)}
            </Pie>
            {total > 0 && <Tooltip content={<ChartTip fmt={(v) => `${v} file${v === 1 ? "" : "s"} (${pct(v / total)})`} />} />}
          </PieChart>
        </ResponsiveContainer>
        <div className="donut-c"><b>{total}</b><small>files</small></div>
      </div>
      <LegendRow items={data.map(([n, v, col]) => [n, col, v])} />
    </div>
  );
}

function HBars({ data, link }) {
  const c = useColors();
  const rows = data.map(([name, value, color]) => ({ name, value, color }));
  return (
    <ResponsiveContainer width="100%" height={Math.max(120, rows.length * 34)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 0, right: 28, top: 0, bottom: 0 }} barCategoryGap={8}>
        <XAxis type="number" hide allowDecimals={false} />
        <YAxis type="category" dataKey="name" width={84} {...axisProps(c)}
          tick={link ? (p) => <a href={`https://cwe.mitre.org/data/definitions/${String(p.payload.value).replace("CWE-", "")}.html`} target="_blank" rel="noreferrer noopener">
            <text x={p.x} y={p.y} dy={4} textAnchor="end" fill={c.axis} fontSize={11}>{p.payload.value}</text></a> : { fill: c.axis, fontSize: 11 }} />
        <Tooltip cursor={{ fill: c.grid }} content={<ChartTip />} />
        <Bar dataKey="value" name="Count" radius={[0, 4, 4, 0]} maxBarSize={18} label={{ position: "right", fill: c.axis, fontSize: 11 }}>
          {rows.map((r, i) => <Cell key={i} fill={r.color} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
