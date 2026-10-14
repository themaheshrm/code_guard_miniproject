import { useEffect, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ResponsiveContainer } from "recharts";
import { api } from "../api.js";
import { EXAMPLE, langOf, pairsFor, pct } from "../lib.js";
import { Heatmap, Meter } from "../components.jsx";

const OPT_LABELS = [["run_ai", "AI-code detection"], ["run_plagiarism", "Plagiarism"], ["run_vulnerability", "Vulnerabilities"],
  ["compare_corpus", "Compare with saved corpus"], ["persist", "Save submissions to corpus"]];

export default function Workspace({ ws, setWs }) {
  const { files, active, options, job, ranCode } = ws;
  const file = files[active] || files[0];
  const [layers, setLayers] = useState({ ai: true, sim: true, vuln: true });
  const [selPair, setSelPair] = useState(null);
  const [dragging, setDragging] = useState(false);
  const edRef = useRef(null), monRef = useRef(null);
  const [ready, setReady] = useState(false);
  const rep = job.report;
  const stale = !!rep && ranCode[file.name] !== undefined && ranCode[file.name] !== file.code;
  const fileRep = rep?.files.find((f) => f.name === file.name);
  const patch = (p) => setWs((s) => ({ ...s, ...p }));
  const setFile = (i, p) => setWs((s) => ({ ...s, files: s.files.map((f, k) => (k === i ? { ...f, ...p } : f)) }));

  useEffect(() => {
    const ed = edRef.current, monaco = monRef.current;
    if (!ready || !ed || !monaco || !rep || stale || !fileRep) return;
    const mk = (s, e, cls, msg) => ({ range: new monaco.Range(s, 1, e, 1), options: { isWholeLine: true, linesDecorationsClassName: cls, className: `${cls}-bg`, hoverMessage: { value: msg } } });
    const d = [];
    if (layers.ai && fileRep.ai?.blocks) for (const b of fileRep.ai.blocks) if (b.contribution > 0.02) d.push(mk(b.start, b.end, "cg-bar-ai", `**AI attribution** +${b.contribution.toFixed(2)} — ${b.name}`));
    if (layers.sim) for (const p of pairsFor(rep, file.name, selPair)) {
      const other = p.a === file.name ? p.b : p.a;
      for (const [s, e] of p.a === file.name ? p.lines_a : p.lines_b) d.push(mk(s, e, "cg-bar-sim", `**Similar to** ${other} (${pct(p.score)})`));
    }
    if (layers.vuln && fileRep.vulnerability) for (const x of fileRep.vulnerability.findings) d.push(mk(x.line, x.line, "cg-bar-vuln", `**${x.cwe}** ${x.message}`));
    const coll = ed.createDecorationsCollection(d);
    return () => coll.clear();
  }, [rep, file.name, layers, selPair, ready, stale, fileRep]);

  const reveal = (line) => edRef.current?.revealLineInCenter(line);
  const addFile = (name, code = "") => setWs((s) => ({ ...s, files: [...s.files, { name, code }], active: s.files.length }));
  const removeFile = (i) => setWs((s) => {
    const f = s.files.filter((_, k) => k !== i);
    return { ...s, files: f.length ? f : [{ name: "submission_1.py", code: "" }], active: Math.max(0, Math.min(s.active, f.length - 1)) };
  });
  const rename = (i) => { const n = prompt("File name (the extension sets the language)", files[i].name); if (n?.trim()) setFile(i, { name: n.trim() }); };

  async function readFiles(list) {
    const items = await Promise.all([...list].map((f) => f.text().then((code) => ({ name: f.name, code }))));
    setWs((s) => {
      const keep = s.files.filter((f) => f.code.trim());
      const names = new Set(keep.map((f) => f.name));
      const all = [...keep, ...items.filter((f) => f.code.trim() && !names.has(f.name))];
      return { ...s, files: all.length ? all : s.files, active: all.length > keep.length ? keep.length : 0 };
    });
  }

  async function run() {
    const payload = files.filter((f) => f.code.trim()).map((f) => ({ name: f.name, code: f.code, language: langOf(f.name) }));
    patch({ job: { status: "queued", report: null, error: null } });
    setSelPair(null);
    try {
      const done = await api.run(payload, options, (status) => setWs((s) => ({ ...s, job: { ...s.job, status } })));
      patch({ job: { status: "done", report: done.result, error: null, id: done.id }, ranCode: Object.fromEntries(payload.map((f) => [f.name, f.code])) });
    } catch (e) {
      patch({ job: { status: "failed", report: null, error: e.message } });
    }
  }
  const busy = job.status === "queued" || job.status === "running";
  const nonEmpty = files.filter((f) => f.code.trim()).length;

  return (
    <div className="ws">
      <section className="pane" aria-label="Code editor"
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); readFiles(e.dataTransfer.files); }}>
        <div className="bar">
          <div className="tabs" role="tablist">
            {files.map((f, i) => (
              <button key={i} role="tab" aria-selected={i === active} className="tab" onClick={() => patch({ active: i })} onDoubleClick={() => rename(i)} title="Double-click to rename">
                {f.name}
                {files.length > 1 && <span className="x" role="button" aria-label={`Remove ${f.name}`} onClick={(e) => { e.stopPropagation(); removeFile(i); }}>×</span>}
              </button>
            ))}
          </div>
          <button className="btn" onClick={() => addFile(`submission_${files.length + 1}.py`)}>Add file</button>
          <label className="btn">Upload<input type="file" multiple hidden accept=".py,.java,.c,.h,.cpp,.cc,.hpp,.js,.mjs,.jsx" onChange={(e) => { readFiles(e.target.files); e.target.value = ""; }} /></label>
        </div>
        <div className="editor">
          {dragging && <div className="drop">Drop files to add them</div>}
          <Editor height="100%" path={file.name} language={langOf(file.name)} value={file.code} theme="vs"
            onChange={(v) => setFile(active, { code: v ?? "" })}
            onMount={(ed, monaco) => { edRef.current = ed; monRef.current = monaco; setReady(true); }}
            options={{ minimap: { enabled: false }, fontSize: 13, scrollBeyondLastLine: false, automaticLayout: true, glyphMargin: false, folding: false, lineDecorationsWidth: 10 }} />
        </div>
        <div className="opts">
          {OPT_LABELS.map(([k, l]) => (
            <label key={k}><input type="checkbox" checked={!!options[k]} onChange={(e) => patch({ options: { ...options, [k]: e.target.checked } })} />{l}</label>
          ))}
          <span style={{ marginLeft: "auto" }}>
            <button className="btn primary" disabled={busy || !nonEmpty} onClick={run}>{busy ? "Analyzing…" : `Analyze ${nonEmpty > 1 ? `${nonEmpty} files` : "code"}`}</button>
          </span>
        </div>
      </section>

      <section className="pane" aria-label="Results" aria-live="polite">
        <div className="bar"><strong>Integrity report</strong></div>
        <div className="body">
          {job.error && <div className="err" role="alert"><b>Analysis failed.</b> {job.error}</div>}
          {!rep && !busy && !job.error && (
            <div className="empty">
              <h2>Paste, upload or drop source code</h2>
              <p>CodeGuard estimates whether code is AI-generated, how closely it matches other submissions (even after renaming and reordering), and which lines look insecure.</p>
              <button className="btn" onClick={() => setWs((s) => ({ ...s, files: EXAMPLE, active: 0 }))}>Load three example submissions</button>
            </div>
          )}
          {busy && <div className="empty">Analyzing ({job.status})…</div>}
          {rep && fileRep && <Report rep={rep} f={fileRep} stale={stale} layers={layers} setLayers={setLayers} selPair={selPair} setSelPair={setSelPair} reveal={reveal} />}
          {rep && !fileRep && <div className="warn">This tab was not part of the last analysis. Run it again to include {file.name}.</div>}
        </div>
      </section>
    </div>
  );
}

const LEGEND = { ai: "Violet bar: AI-attributed block", sim: "Amber bar: matches another file", vuln: "Red bar: risky line" };

function Report({ rep, f, stale, layers, setLayers, selPair, setSelPair, reveal }) {
  const ai = f.ai, v = f.vulnerability, plag = rep.plagiarism;
  const names = plag?.names || [];
  const myPairs = (plag?.pairs || []).filter((p) => p.a === f.name || p.b === f.name);
  const feat = (ai?.top_features || []).map((x) => ({ ...x, name: x.feature, v: x.contribution }));
  return (
    <>
      {stale && <div className="warn">The code changed after this analysis. Highlights are hidden; run it again.</div>}
      <div className={`verdict ${f.verdict.level}`}>
        <h3>{{ clear: "No flags raised", attention: "One signal needs a look", review: "Several signals: review manually" }[f.verdict.level]}</h3>
        {f.verdict.signals.map((s) => <p key={s.signal}>{s.flagged ? "⚑ " : "✓ "}{s.summary}</p>)}
        <p>{f.verdict.disclaimer}</p>
      </div>
      {(f.warnings || []).map((w) => <div className="warn" key={w}>{w}</div>)}
      {ai && (ai.status === "ok"
        ? <Meter label="AI-generated" value={ai.probability} threshold={ai.threshold} color="var(--ai)" />
        : <div className="warn"><b>AI detector not trained yet.</b> {ai.message}</div>)}
      {f.max_similarity != null && <Meter label="Max similarity" value={f.max_similarity} threshold={plag?.threshold} color="var(--sim)" />}
      {v && <Meter label="Security risk" value={v.risk_score / 100} text={`${v.risk_score}`} color="var(--sec)" />}

      <div className="chips" style={{ margin: "12px 0" }}>
        {[["ai", "AI blocks"], ["sim", "Similarity"], ["vuln", "Security"]].map(([k, l]) => (
          <button key={k} className={`chip ${k}`} aria-pressed={layers[k]} title={LEGEND[k]} onClick={() => setLayers({ ...layers, [k]: !layers[k] })}>{l}</button>
        ))}
      </div>

      {ai?.status === "ok" && (
        <details open>
          <summary>Why the AI score is what it is</summary>
          <p className="muted">{Object.entries(ai.models).map(([m, x]) => `${m} ${pct(x.probability)}`).join(" · ")}. Bars to the right push toward “AI”, to the left toward “human”.</p>
          {feat.length > 0 && (
            <ResponsiveContainer width="100%" height={Math.max(120, feat.length * 26)}>
              <BarChart data={feat} layout="vertical" margin={{ left: 10, right: 10 }}>
                <XAxis type="number" hide /><YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 12 }} />
                <Tooltip formatter={(val, _n, p) => [`${val} (feature value ${p.payload.value})`, "contribution"]} />
                <Bar dataKey="v">{feat.map((x, i) => <Cell key={i} fill={x.v > 0 ? "#6b46f0" : "#0e8a7b"} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
          {ai.blocks.length > 0 && <>
            <p className="muted">Blocks ranked by how much removing them changes the score:</p>
            <ul className="list">{ai.blocks.map((b) => (
              <li key={b.start}><button onClick={() => reveal(b.start)}>{b.name} (lines {b.start}–{b.end}) <b style={{ color: b.contribution > 0 ? "var(--ai)" : "var(--ok)" }}>{b.contribution > 0 ? "+" : ""}{b.contribution.toFixed(2)}</b></button></li>
            ))}</ul>
          </>}
        </details>
      )}

      {plag && (
        <details open={myPairs.length > 0}>
          <summary>Similarity {myPairs.length ? `(${myPairs.length} comparison${myPairs.length > 1 ? "s" : ""})` : ""}</summary>
          {names.length < 2 && !plag.corpus_matches?.length && <p className="muted">Add more files, or enable “Compare with saved corpus”, to check for copying.</p>}
          {names.length > 1 && <Heatmap names={names} matrix={plag.matrix} selected={selPair} onSelect={(p) => setSelPair(selPair && selPair[0] === p[0] && selPair[1] === p[1] ? null : p)} />}
          <ul className="list">{myPairs.map((p) => {
            const other = p.a === f.name ? p.b : p.a;
            const on = !!selPair && selPair[0] === p.a && selPair[1] === p.b;
            return <li key={other}><button aria-pressed={on} onClick={() => { setSelPair(on ? null : [p.a, p.b]); const l = (p.a === f.name ? p.lines_a : p.lines_b)[0]; if (l) reveal(l[0]); }}>
              {other}: <b>{pct(p.score)}</b> <span className="muted">(tokens {pct(p.token_similarity)}, structure {pct(p.ast_similarity)}){p.flagged ? " ⚑" : ""}</span></button></li>;
          })}</ul>
          {(plag.corpus_matches || []).filter((m) => m.a === f.name).map((m) => (
            <p key={m.reference_id} className="muted">Saved corpus: {m.reference_name}, {pct(m.score)}</p>
          ))}
        </details>
      )}

      {v && (
        <details open={v.findings.length > 0}>
          <summary>Security findings ({v.findings.length})</summary>
          {v.findings.length === 0 && <p className="muted">No rule matches. Static rules are not proof of safety.</p>}
          <ul className="list">{v.findings.map((x, i) => (
            <li key={i}><button onClick={() => reveal(x.line)}><span className={`sev ${x.severity}`}>{x.severity}</span>line {x.line} · {x.cwe}: {x.message}</button></li>
          ))}</ul>
          {v.ml.status === "ok"
            ? <ul className="list">{v.functions.filter((x) => x.ml_flagged).map((x) => <li key={x.start}><button onClick={() => reveal(x.start)}>Model flags <b>{x.name}</b> ({pct(x.ml_probability)})</button></li>)}</ul>
            : <p className="muted">Function-level model: {v.ml.message}</p>}
        </details>
      )}
    </>
  );
}
