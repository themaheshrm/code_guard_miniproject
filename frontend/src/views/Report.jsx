import { useMemo, useState } from "react";
import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, Bot, ChevronRight, Columns2, Copy, Fingerprint, GitCompareArrows, Info, Layers, ShieldAlert, Sparkles, Wrench } from "lucide-react";
import { ChartTip, Heatmap, useColors } from "../charts.jsx";
import { LANG_LABEL, LEVEL, RISK_TONE, SEV_ORDER, cap, pct } from "../lib.js";
import { Badge, Button, Empty, Meter, ScoreRing, Tabs, cx } from "../ui.jsx";

const SEV_TONE = { critical: "bad", high: "bad", medium: "warn", low: "neutral" };

export function VerdictBanner({ f }) {
  const L = LEVEL[f.verdict.level];
  return (
    <div className={cx("verdict", L.tone)}>
      <div className="verdict-top"><Badge tone={L.tone}>{L.label}</Badge><h3>{L.title}</h3></div>
      <ul className="signals">
        {f.verdict.signals.map((s) => (
          <li key={s.signal} className={s.flagged ? "flag" : ""}>
            {s.signal === "ai" ? <Bot size={14} aria-hidden /> : s.signal === "similarity" ? <Copy size={14} aria-hidden /> : <ShieldAlert size={14} aria-hidden />}
            <span>{s.summary}</span>{s.flagged && <Badge tone="warn" icon={false}>flagged</Badge>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Rings({ f, plag }) {
  const c = useColors();
  const ai = f.ai, v = f.vulnerability;
  return (
    <div className="rings">
      <ScoreRing label="AI likelihood" color={c.ai} value={ai?.status === "ok" ? ai.probability : null} threshold={ai?.threshold}
        display={ai?.status === "ok" ? pct(ai.probability) : "off"} sub={ai?.status === "ok" ? `${ai.confidence} conf.` : "not run"} />
      <ScoreRing label="Max similarity" color={c.sim} value={f.max_similarity} threshold={plag?.threshold}
        display={f.max_similarity == null ? "off" : pct(f.max_similarity)} sub={f.max_similarity == null ? "not run" : f.max_similarity >= (plag?.threshold ?? 0.5) ? "match found" : "no match"} />
      <ScoreRing label="Security risk" color={c.sec} value={v ? v.risk_score / 100 : null}
        display={v ? Math.round(v.risk_score) : "off"} sub={v ? `${v.risk_level || ""} · ${v.findings.length} finding${v.findings.length === 1 ? "" : "s"}` : "not run"} />
    </div>
  );
}

function Overview({ f, rep, onTab }) {
  return (
    <div className="stack">
      <VerdictBanner f={f} />
      <Rings f={f} plag={rep.plagiarism} />
      {(f.warnings || []).map((w) => <div className="note warn" key={w}><AlertTriangle size={14} aria-hidden /><span>{w}</span></div>)}
      <div className="kv">
        <div><span>Language</span><b>{LANG_LABEL[f.language] || f.language}</b></div>
        <div><span>Lines</span><b>{f.lines}</b></div>
        <div><span>Parsed AST</span><b>{f.parsed == null ? "–" : f.parsed ? "yes" : "token fallback"}</b></div>
        <div><span>Analysis time</span><b>{rep.duration_ms != null ? `${Math.round(rep.duration_ms)} ms` : "–"}</b></div>
      </div>
      <div className="quick">
        {f.ai?.status === "ok" && <button onClick={() => onTab("ai")}><Bot size={16} aria-hidden /><span>Why this AI score?</span><ChevronRight size={14} aria-hidden /></button>}
        {f.max_similarity != null && <button onClick={() => onTab("sim")}><Copy size={16} aria-hidden /><span>Similarity details</span><ChevronRight size={14} aria-hidden /></button>}
        {f.vulnerability && <button onClick={() => onTab("sec")}><ShieldAlert size={16} aria-hidden /><span>{f.vulnerability.findings.length} security findings</span><ChevronRight size={14} aria-hidden /></button>}
      </div>
      <p className="disclaimer"><Info size={13} aria-hidden /> {f.verdict.disclaimer}</p>
    </div>
  );
}

function AiTab({ f, reveal }) {
  const c = useColors();
  const ai = f.ai;
  if (!ai) return <Empty icon={Bot} title="AI detection was not run">Enable “AI-code detection” and analyze again.</Empty>;
  if (ai.status !== "ok") return <Empty icon={Bot} title="No AI engine available">{ai.message}</Empty>;
  const feat = (ai.top_features || []).map((x) => ({ ...x, name: x.label || x.feature }));
  const ENGINE = { heuristic: "Heuristic stylometry", xgboost: "XGBoost", codebert: "CodeBERT" };
  return (
    <div className="stack">
      <div className="ai-head">
        <div>
          <div className="big">{pct(ai.probability)}<small> AI likelihood</small></div>
          <div className="row-wrap">
            <Badge tone={ai.label === "ai" ? "ai" : "good"} icon={ai.label === "ai" ? Bot : undefined}>{ai.label === "ai" ? "Likely AI-generated" : "Likely human-written"}</Badge>
            <Badge tone="neutral" icon={false}>{cap(ai.confidence)} confidence</Badge>
            <Badge tone="neutral" icon={Layers}>{ai.engine === "ensemble" ? "Ensemble" : ENGINE[ai.engine] || ai.engine}</Badge>
          </div>
        </div>
      </div>
      {ai.message && <div className="note info"><Info size={14} aria-hidden /><span>{ai.message}</span></div>}
      <div className="engines">
        {Object.entries(ai.models).map(([k, x]) => (
          <div key={k} className="eng-row"><span>{ENGINE[k] || k}</span><Meter value={x.probability} threshold={x.threshold} color={c.ai} label={`${k} probability`} /><b>{pct(x.probability)}</b></div>
        ))}
      </div>
      {feat.length > 0 && (
        <div>
          <h4 className="sub-h">Signals behind the score</h4>
          <p className="muted small">Bars right of the axis push toward “AI”, left toward “human”. Hover for the measured value.</p>
          <div className="legend"><span><i style={{ background: c.ai }} />toward AI</span><span><i style={{ background: c.s1 }} />toward human</span></div>
          <ResponsiveContainer width="100%" height={Math.max(140, feat.length * 30)}>
            <BarChart data={feat} layout="vertical" margin={{ left: 4, right: 16, top: 4, bottom: 4 }} barCategoryGap={6}>
              <XAxis type="number" hide domain={["dataMin", "dataMax"]} />
              <YAxis type="category" dataKey="name" width={176} interval={0} tick={{ fontSize: 11.5, fill: c.axis }} tickLine={false} axisLine={false} />
              <ReferenceLine x={0} stroke={c.axis} strokeOpacity={0.5} />
              <Tooltip cursor={{ fill: c.grid }} content={<ChartTip fmt={(v, p) => `${v > 0 ? "+" : ""}${v.toFixed(3)} (value ${p.payload.value})`} />} />
              <Bar dataKey="contribution" name="contribution" radius={4} maxBarSize={16}>
                {feat.map((x, i) => <Cell key={i} fill={x.contribution > 0 ? c.ai : c.s1} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {ai.blocks?.length > 0 && (
        <div>
          <h4 className="sub-h">Block attribution</h4>
          <p className="muted small">How much the score drops when each block is removed. {reveal && "Click to jump to it in the editor."}</p>
          <ul className="items">
            {ai.blocks.map((b) => (
              <li key={`${b.start}-${b.end}`}>
                <button disabled={!reveal} onClick={() => reveal?.(b.start, b.end)}>
                  <span className="mono">{b.name}</span><span className="muted">lines {b.start}–{b.end}</span>
                  <b className={b.contribution > 0 ? "t-ai" : "t-hum"}>{b.contribution > 0 ? "+" : ""}{b.contribution.toFixed(3)}</b>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function SimTab({ f, rep, reveal, selPair, setSelPair, onCompare, canCompare }) {
  const c = useColors();
  const plag = rep.plagiarism;
  if (!plag) return <Empty icon={Copy} title="Plagiarism check was not run">Enable “Plagiarism” and analyze again.</Empty>;
  const names = plag.names || [];
  const mine = (plag.pairs || []).filter((p) => p.a === f.name || p.b === f.name);
  const corpus = (plag.corpus_matches || []).filter((m) => m.a === f.name);
  const cluster = (plag.clusters || []).find((g) => g.includes(f.name));
  return (
    <div className="stack">
      {cluster && <div className="note warn"><Fingerprint size={14} aria-hidden /><span>Part of a similarity cluster: <b>{cluster.join(", ")}</b></span></div>}
      {names.length > 1 && (
        <div>
          <h4 className="sub-h">Pairwise similarity</h4>
          <Heatmap names={names} matrix={plag.matrix} languages={plag.languages} threshold={plag.threshold} selected={selPair}
            onSelect={(p) => setSelPair?.(selPair && selPair[0] === p[0] && selPair[1] === p[1] ? null : p)} />
        </div>
      )}
      {names.length < 2 && !corpus.length && (
        <Empty icon={Copy} title="Nothing to compare against">Add more files, or enable “Compare with saved corpus”, to check for copying.</Empty>
      )}
      {mine.length > 0 && (
        <div>
          <h4 className="sub-h">Comparisons for {f.name}</h4>
          <ul className="pairs">
            {mine.map((p) => {
              const other = p.a === f.name ? p.b : p.a;
              const on = !!selPair && selPair[0] === p.a && selPair[1] === p.b;
              return (
                <li key={other} className={cx(on && "on", p.flagged && "flag")}>
                  <button className="pair-main" onClick={() => {
                    setSelPair?.(on ? null : [p.a, p.b]);
                    const l = (p.a === f.name ? p.lines_a : p.lines_b)[0];
                    if (l && reveal) reveal(l[0], l[1]);
                  }} aria-pressed={on}>
                    <div className="pair-t"><span className="mono">{other}</span>{p.flagged && <Badge tone="warn">match</Badge>}<b>{pct(p.score)}</b></div>
                    <div className="pair-bars">
                      <span>Tokens</span><Meter value={p.token_similarity} color={c.sim} label="token similarity" /><em>{pct(p.token_similarity)}</em>
                      <span>Structure</span><Meter value={p.ast_similarity} color={c.sim} label="AST similarity" /><em>{p.ast_used ? pct(p.ast_similarity) : "n/a"}</em>
                    </div>
                  </button>
                  {canCompare && <Button size="sm" icon={Columns2} onClick={() => onCompare(p)}>Compare</Button>}
                </li>
              );
            })}
          </ul>
          {reveal && <p className="muted small">Select a comparison to highlight only its matching lines in the editor (amber gutter).</p>}
        </div>
      )}
      {plag.corpus_size != null && (
        <div>
          <h4 className="sub-h">Saved corpus <span className="muted">({plag.corpus_size} reference files)</span></h4>
          {corpus.length === 0 ? <p className="muted small">No close match in the saved corpus.</p> : (
            <ul className="items">{corpus.map((m) => (
              <li key={m.reference_id}><button disabled={!reveal} onClick={() => m.lines_a[0] && reveal?.(m.lines_a[0][0], m.lines_a[0][1])}>
                <span className="mono">{m.reference_name}</span><span className="muted">tokens {pct(m.token_similarity)} · structure {pct(m.ast_similarity)}</span>
                <b className="t-sim">{pct(m.score)}</b></button></li>))}</ul>
          )}
        </div>
      )}
    </div>
  );
}

function SecTab({ f, reveal }) {
  const v = f.vulnerability;
  const [sev, setSev] = useState("all");
  const [open, setOpen] = useState(null);
  if (!v) return <Empty icon={ShieldAlert} title="Vulnerability scan was not run">Enable “Vulnerabilities” and analyze again.</Empty>;
  const counts = v.severity_counts || {};
  const list = [...v.findings].sort((a, b) => SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity) || a.line - b.line)
    .filter((x) => sev === "all" || x.severity === sev);
  return (
    <div className="stack">
      <div className="sec-head">
        <div><div className="big">{Math.round(v.risk_score)}<small> / 100 risk</small></div>
          <Badge tone={RISK_TONE[v.risk_level] || "neutral"}>{cap(v.risk_level || "–")} risk</Badge></div>
        <div className="chips" role="group" aria-label="Filter by severity">
          <button className="chip" aria-pressed={sev === "all"} onClick={() => setSev("all")}>All <b>{v.findings.length}</b></button>
          {SEV_ORDER.filter((s) => counts[s]).map((s) => (
            <button key={s} className={`chip sev-${s}`} aria-pressed={sev === s} onClick={() => setSev(s)}>{cap(s)} <b>{counts[s]}</b></button>
          ))}
        </div>
      </div>
      {v.findings.length === 0 && <Empty icon={ShieldAlert} title="No rule matched">Static rules are not proof of safety — review authentication, input validation and data handling manually.</Empty>}
      <ul className="findings">
        {list.map((x, i) => {
          const k = `${x.rule_id}-${x.line}`;
          const isOpen = open === k;
          return (
            <li key={k + i} className={cx("finding", `sev-${x.severity}`, isOpen && "open")}>
              <button className="finding-h" onClick={() => { setOpen(isOpen ? null : k); reveal?.(x.line, x.line); }} aria-expanded={isOpen}>
                <Badge tone={SEV_TONE[x.severity]}>{cap(x.severity)}</Badge>
                <span className="grow">{x.message}</span>
                <span className="mono muted">L{x.line}</span>
                <ChevronRight size={14} className="chev" aria-hidden />
              </button>
              {isOpen && (
                <div className="finding-b">
                  <pre className="snip"><span className="ln">{x.line}</span>{x.snippet}</pre>
                  <div className="tags">
                    <a href={`https://cwe.mitre.org/data/definitions/${x.cwe.replace("CWE-", "")}.html`} target="_blank" rel="noreferrer noopener" className="tag">{x.cwe}</a>
                    {x.owasp && <span className="tag">OWASP {x.owasp}</span>}
                    <span className="tag mono">{x.rule_id}</span>
                  </div>
                  {x.fix && <div className="fix"><Wrench size={14} aria-hidden /><span><b>Fix: </b>{x.fix}</span></div>}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <div className="note info"><Sparkles size={14} aria-hidden />
        <span>{v.ml?.status === "ok"
          ? <>Function-level model flagged {v.functions.filter((x) => x.ml_flagged).length} of {v.functions.length} functions.</>
          : <>Function-level ML model: {v.ml?.message}</>}</span></div>
      {v.ml?.status === "ok" && v.functions.filter((x) => x.ml_flagged).length > 0 && (
        <ul className="items">{v.functions.filter((x) => x.ml_flagged).map((x) => (
          <li key={x.start}><button disabled={!reveal} onClick={() => reveal?.(x.start, x.end)}><span className="mono">{x.name}</span>
            <span className="muted">lines {x.start}–{x.end}</span><b className="t-sec">{pct(x.ml_probability)}</b></button></li>))}</ul>
      )}
    </div>
  );
}

/** Full report for one file of an analysis. */
export function FileReport({ rep, f, reveal, selPair, setSelPair, onCompare, canCompare, tab, setTab }) {
  const [localTab, setLocalTab] = useState("overview");
  const t = tab ?? localTab, set = setTab ?? setLocalTab;
  const mine = (rep.plagiarism?.pairs || []).filter((p) => p.flagged && (p.a === f.name || p.b === f.name)).length;
  return (
    <div className="file-report">
      <Tabs value={t} onChange={set} tabs={[
        ["overview", "Overview", null, Layers],
        ["ai", "AI detection", f.ai?.status === "ok" ? pct(f.ai.probability) : null, Bot],
        ["sim", "Similarity", mine || null, GitCompareArrows],
        ["sec", "Security", f.vulnerability ? f.vulnerability.findings.length : null, ShieldAlert],
      ]} />
      <div className="tab-body" key={t}>
        {t === "overview" && <Overview f={f} rep={rep} onTab={set} />}
        {t === "ai" && <AiTab f={f} reveal={reveal} />}
        {t === "sim" && <SimTab f={f} rep={rep} reveal={reveal} selPair={selPair} setSelPair={setSelPair} onCompare={onCompare} canCompare={canCompare} />}
        {t === "sec" && <SecTab f={f} reveal={reveal} />}
      </div>
    </div>
  );
}

/** Compact table of every file in a batch with its three scores. */
export function FilesTable({ rep, selected, onSelect }) {
  const c = useColors();
  const rows = useMemo(() => rep.files, [rep]);
  return (
    <div className="table-wrap">
      <table className="tbl">
        <thead><tr><th>File</th><th>Verdict</th><th>AI</th><th>Similarity</th><th>Risk</th></tr></thead>
        <tbody>
          {rows.map((f) => (
            <tr key={f.name} className={cx("clickable", selected === f.name && "sel")} onClick={() => onSelect(f.name)} tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && onSelect(f.name)}>
              <td><span className="mono">{f.name}</span><div className="muted small">{LANG_LABEL[f.language]} · {f.lines} lines</div></td>
              <td><Badge tone={LEVEL[f.verdict.level].tone}>{LEVEL[f.verdict.level].label}</Badge></td>
              <td className="num-cell">{f.ai?.status === "ok" ? <><Meter value={f.ai.probability} threshold={f.ai.threshold} color={c.ai} label="AI" /><span>{pct(f.ai.probability)}</span></> : "–"}</td>
              <td className="num-cell">{f.max_similarity != null ? <><Meter value={f.max_similarity} threshold={rep.plagiarism?.threshold} color={c.sim} label="similarity" /><span>{pct(f.max_similarity)}</span></> : "–"}</td>
              <td className="num-cell">{f.vulnerability ? <><Meter value={f.vulnerability.risk_score / 100} color={c.sec} label="risk" /><span>{Math.round(f.vulnerability.risk_score)}</span></> : "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
