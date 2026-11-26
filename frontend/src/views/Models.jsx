import { useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BrainCircuit, Cpu, Download, FlaskConical, Gauge, Play, RefreshCw, Upload } from "lucide-react";
import { api } from "../api.js";
import { ChartTip, ConfusionMatrix, LegendRow, axisProps, useColors } from "../charts.jsx";
import { useAsync } from "../hooks.js";
import { download, fmtDate, pct } from "../lib.js";
import { Badge, Button, Card, ErrorBox, Skeleton, useToast } from "../ui.jsx";

const f3 = (x) => (x == null ? "–" : typeof x === "number" ? x.toFixed(3) : x);
const TEMPLATE = [
  { id: "p1-h", group_id: "p1", label: 0, language: "python", code: "n=int(input())\nprint(sum(range(n)))\n", generator: "human" },
  { id: "p1-a", group_id: "p1", label: 1, language: "python", code: "def total(n: int) -> int:\n    \"\"\"Sum 0..n-1.\"\"\"\n    return sum(range(n))\n", generator: "gpt-4o" },
].map((r) => JSON.stringify(r)).join("\n") + "\n";

export default function Models({ onHealth }) {
  const toast = useToast();
  const health = useAsync(() => api.health(), []);
  const metrics = useAsync(() => api.metrics(), []);
  const [file, setFile] = useState(null);
  const [fpr, setFpr] = useState(0.05);
  const [train, setTrain] = useState({ status: "idle" });
  const [bench, setBench] = useState({ status: "idle" });
  const [n, setN] = useState(100);
  const input = useRef(null);
  const refresh = async () => { await Promise.all([health.reload(), metrics.reload()]); api.health().then(onHealth).catch(() => {}); };

  const runTrain = async () => {
    if (!file) return;
    setTrain({ status: "queued" });
    try {
      const t = await api.train(file, fpr, (status) => setTrain({ status }));
      setTrain({ status: "done", result: t.result });
      toast.success("XGBoost trained and loaded — new analyses use it immediately.");
      refresh();
    } catch (e) { setTrain({ status: "failed", error: e.message }); toast.error(e.message); }
  };
  const runBench = async () => {
    setBench({ status: "queued" });
    try {
      const t = await api.benchmark(n, (status) => setBench({ status }));
      setBench({ status: "done", result: t.result });
      toast.success("Plagiarism benchmark finished.");
      metrics.reload();
    } catch (e) { setBench({ status: "failed", error: e.message }); toast.error(e.message); }
  };
  const reload = async () => {
    try { await api.reloadModels(); toast.success("Model artefacts re-read from disk."); refresh(); } catch (e) { toast.error(e.message); }
  };

  const h = health.data, m = metrics.data;
  const busyT = train.status === "queued" || train.status === "running";
  const busyB = bench.status === "queued" || bench.status === "running";

  return (
    <div className="page stack">
      <div className="grid-3">
        {!h ? [0, 1, 2].map((i) => <Skeleton key={i} h={150} />) : <>
          <EngineCard name="Heuristic stylometry" on={h.models.heuristic.available} icon={Gauge}
            desc="15 interpretable style signals (comments, docstrings, type hints, naming, formatting). Always on; small weight when trained models exist." meta={`threshold ${pct(h.models.heuristic.threshold)}`} />
          <EngineCard name="XGBoost" on={h.models.xgboost.available} icon={BrainCircuit}
            desc="Gradient-boosted trees over 45 stylometric + AST features. Train it below from your own labelled dataset."
            meta={h.models.xgboost.available ? `trained ${h.models.xgboost.trained_at ? fmtDate(h.models.xgboost.trained_at) : ""} · threshold ${pct(h.models.xgboost.threshold)}` : h.models.xgboost.error} />
          <EngineCard name="CodeBERT" on={h.models.codebert.available} icon={Cpu}
            desc="Fine-tuned transformer over 512-token windows. Optional: train on a GPU with ml/train_codebert.py, then reload."
            meta={h.models.codebert.available ? `threshold ${pct(h.models.codebert.threshold)}` : h.models.codebert.error} />
        </>}
      </div>

      <div className="grid-2">
        <Card title="Train the XGBoost detector" icon={BrainCircuit} actions={<Button size="sm" icon={RefreshCw} onClick={reload}>Reload models</Button>}>
          <p className="muted small">Upload a JSONL file: one object per line with <code>code</code>, <code>label</code> (0 = human, 1 = AI), and optionally <code>language</code>, <code>group_id</code> (problem ID — keeps a problem in one split) and <code>generator</code>. Build one with <code>python -m ml.build_dataset</code>.</p>
          <div className="train-form">
            <button className="dropzone" onClick={() => input.current?.click()} type="button">
              <Upload size={18} aria-hidden /><span>{file ? <><b>{file.name}</b> · {(file.size / 1024).toFixed(1)} KB</> : "Choose dataset (.jsonl)"}</span>
            </button>
            <input ref={input} type="file" accept=".jsonl,.json,.txt" hidden onChange={(e) => { setFile(e.target.files[0] || null); e.target.value = ""; }} />
            <label className="field inline"><span>Max false-positive rate</span>
              <select className="input sel" value={fpr} onChange={(e) => setFpr(Number(e.target.value))}>
                {[0.01, 0.02, 0.05, 0.1, 0.2].map((v) => <option key={v} value={v}>{pct(v)}</option>)}
              </select></label>
            <div className="row-wrap">
              <Button variant="primary" icon={Play} disabled={!file} loading={busyT} onClick={runTrain}>{busyT ? "Training…" : "Train & load"}</Button>
              <Button size="sm" icon={Download} onClick={() => download("dataset_template.jsonl", TEMPLATE, "application/x-ndjson")}>Template</Button>
            </div>
          </div>
          {busyT && <div className="progress"><div className="progress-bar" /><span>Extracting features and boosting…</span></div>}
          {train.status === "failed" && <ErrorBox>{train.error}</ErrorBox>}
          {train.status === "done" && train.result?.test && (
            <div className="note good small">Trained on {train.result.rows} rows — test accuracy {f3(train.result.test.accuracy)}, ROC-AUC {f3(train.result.test.roc_auc)}, FPR {f3(train.result.test.false_positive_rate)}.</div>
          )}
          <p className="muted small">The decision threshold is chosen on the validation split to keep false positives at or below the selected rate — flagging an honest author is the costly error.</p>
        </Card>

        <Card title="Plagiarism benchmark" icon={FlaskConical}>
          <p className="muted small">Takes real Python standard-library functions, creates obfuscated copies (identifier renaming, statement reordering, comment edits, dead-code insertion, all combined), and measures recall against unrelated pairs.</p>
          <div className="row-wrap">
            <label className="field inline"><span>Programs</span>
              <select className="input sel" value={n} onChange={(e) => setN(Number(e.target.value))}>{[50, 100, 200].map((v) => <option key={v}>{v}</option>)}</select></label>
            <Button variant="primary" icon={Play} loading={busyB} onClick={runBench}>{busyB ? "Running…" : "Run benchmark"}</Button>
          </div>
          {busyB && <div className="progress"><div className="progress-bar" /><span>Fingerprinting {n} programs × 5 variants…</span></div>}
          {bench.status === "failed" && <ErrorBox>{bench.error}</ErrorBox>}
          {m?.plagiarism && <PlagSummary m={m.plagiarism} />}
        </Card>
      </div>

      {metrics.error && <ErrorBox onRetry={metrics.reload}>{metrics.error}</ErrorBox>}
      {m && <>
        <ModelBlock title="XGBoost — evaluation on held-out problems" m={m.xgboost} cmd="Train from the card above, or: python -m ml.train_xgboost --data data/datasets/ai_dataset.jsonl" />
        <ModelBlock title="CodeBERT — evaluation" m={m.codebert} cmd="python -m ml.train_codebert --task ai --data data/datasets/ai_dataset.jsonl" />
        {m.plagiarism && <PlagBlock m={m.plagiarism} />}
        <ModelBlock title="Vulnerability classifier (optional)" m={m.vulnerability} labels={["safe", "vuln"]}
          cmd="python -m ml.prepare_vuln --dataset devign --out data/datasets/vuln_dataset.jsonl && python -m ml.train_codebert --task vuln --data data/datasets/vuln_dataset.jsonl" />
      </>}
      <p className="muted small">Metrics describe the dataset they were computed on. Report false-positive rates alongside accuracy; AI-code detection is probabilistic and weaker on short or edited code.</p>
    </div>
  );
}

function EngineCard({ name, on, icon: Icon, desc, meta }) {
  return (
    <div className={`engine-card ${on ? "on" : ""}`}>
      <div className="row-wrap"><span className="engine-ic"><Icon size={18} aria-hidden /></span><b className="grow">{name}</b><Badge tone={on ? "good" : "neutral"}>{on ? "Active" : "Not loaded"}</Badge></div>
      <p className="muted small">{desc}</p>
      {meta && <div className="mono small muted ellipsis" title={meta}>{meta}</div>}
    </div>
  );
}

function PlagSummary({ m }) {
  const c = useColors();
  return (
    <div className="mini-bars">
      {Object.entries(m.recall_at_threshold).map(([k, v]) => (
        <div key={k} className="mini-bar"><span>{k.replace("_", " ")}</span><div className="meter"><span style={{ width: `${(v || 0) * 100}%`, background: c.sim }} /></div><b>{pct(v)}</b></div>
      ))}
      <div className="mini-bar"><span>false positives</span><div className="meter"><span style={{ width: `${(m.negative_fpr_at_threshold || 0) * 100}%`, background: c.bad }} /></div><b>{pct(m.negative_fpr_at_threshold, 1)}</b></div>
    </div>
  );
}

function ModelBlock({ title, m, cmd, labels }) {
  const c = useColors();
  if (!m) return (
    <Card title={title} icon={BrainCircuit}><p className="muted small">Not trained yet.</p><pre className="cmd">{cmd}</pre></Card>
  );
  const t = m.test;
  return (
    <Card title={title} icon={BrainCircuit}>
      <p className="muted small">Split sizes (by problem): {Object.entries(m.split_sizes || {}).map(([k, v]) => `${k} ${v}`).join(" · ")}. {m.threshold_policy}</p>
      {t ? (
        <div className="grid-3 tight">
          <div>
            <h4 className="sub-h">Test metrics @ threshold {f3(t.threshold)}</h4>
            <table className="tbl compact"><tbody>
              {[["Accuracy", t.accuracy], ["Precision", t.precision], ["Recall", t.recall], ["F1", t.f1], ["ROC-AUC", t.roc_auc], ["PR-AUC", t.pr_auc], ["False-positive rate", t.false_positive_rate]]
                .map(([k, v]) => <tr key={k}><th>{k}</th><td className="num">{f3(v)}</td></tr>)}
            </tbody></table>
          </div>
          <div><h4 className="sub-h">Confusion matrix</h4><ConfusionMatrix cm={t.confusion_matrix} labels={labels} /></div>
          {t.roc_curve && <div><h4 className="sub-h">ROC curve</h4>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={t.roc_curve} margin={{ left: -18, right: 8, top: 8 }}>
                <CartesianGrid stroke={c.grid} />
                <XAxis dataKey="fpr" type="number" domain={[0, 1]} {...axisProps(c)} tickFormatter={(v) => v.toFixed(1)} />
                <YAxis domain={[0, 1]} {...axisProps(c)} tickFormatter={(v) => v.toFixed(1)} />
                <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke={c.axis} strokeDasharray="4 4" />
                <Tooltip content={<ChartTip labelFmt={(l) => `FPR ${f3(l)}`} fmt={f3} />} />
                <Line dataKey="tpr" name="True-positive rate" dot={false} stroke={c.ai} strokeWidth={2} type="stepAfter" />
              </LineChart>
            </ResponsiveContainer></div>}
        </div>
      ) : <p className="muted small">No test split metrics.</p>}
      {m.feature_importance?.length > 0 && <div>
        <h4 className="sub-h">Feature importance (gain)</h4>
        <ResponsiveContainer width="100%" height={Math.min(380, m.feature_importance.slice(0, 12).length * 28 + 10)}>
          <BarChart data={m.feature_importance.slice(0, 12)} layout="vertical" margin={{ left: 0, right: 16 }}>
            <XAxis type="number" hide /><YAxis type="category" dataKey="feature" width={160} {...axisProps(c)} />
            <Tooltip cursor={{ fill: c.grid }} content={<ChartTip fmt={(v) => v.toFixed(2)} />} />
            <Bar dataKey="gain" name="Gain" fill={c.ai} radius={[0, 4, 4, 0]} maxBarSize={16} />
          </BarChart>
        </ResponsiveContainer></div>}
      <div className="grid-2">
        {m.by_length?.length > 0 && <div><h4 className="sub-h">By code length</h4><table className="tbl compact"><thead><tr><th>Bucket</th><th>n</th><th>Acc.</th><th>Recall</th><th>FPR</th></tr></thead><tbody>
          {m.by_length.map((r) => <tr key={r.bucket}><td>{r.bucket}</td><td className="num">{r.n}</td><td className="num">{f3(r.accuracy)}</td><td className="num">{f3(r.recall)}</td><td className="num">{f3(r.false_positive_rate)}</td></tr>)}</tbody></table></div>}
        {m.by_generator?.length > 0 && <div><h4 className="sub-h">Recall by generating model</h4><table className="tbl compact"><thead><tr><th>Generator</th><th>n</th><th>Recall</th></tr></thead><tbody>
          {m.by_generator.map((r) => <tr key={r.generator}><td>{r.generator}</td><td className="num">{r.n}</td><td className="num">{f3(r.recall)}</td></tr>)}</tbody></table></div>}
      </div>
    </Card>
  );
}

function PlagBlock({ m }) {
  const c = useColors();
  return (
    <Card title="Plagiarism engine — threshold sweep" icon={FlaskConical}>
      <p className="muted small">{m.n_programs} programs from {m.corpus}; {m.n_negative_pairs} unrelated pairs. Threshold {m.config.threshold}, k={m.config.k}, w={m.config.w}. Mean score of unrelated pairs {pct(m.negative_mean_score)}.</p>
      <LegendRow items={[["Precision", c.s1], ["Recall", c.sim], ["F1", c.s3]]} />
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={m.sweep} margin={{ left: -18, right: 8, top: 8 }}>
          <CartesianGrid stroke={c.grid} vertical={false} />
          <XAxis dataKey="threshold" {...axisProps(c)} tickFormatter={(v) => v.toFixed(2)} />
          <YAxis domain={[0, 1]} {...axisProps(c)} />
          <ReferenceLine x={m.config.threshold} stroke={c.axis} strokeDasharray="4 4" label={{ value: "current", fill: c.axis, fontSize: 11, position: "insideTopRight" }} />
          <Tooltip content={<ChartTip labelFmt={(l) => `threshold ${l}`} fmt={f3} />} cursor={{ stroke: c.axis, strokeDasharray: "3 3" }} />
          <Line dataKey="precision" name="Precision" dot={false} stroke={c.s1} strokeWidth={2} />
          <Line dataKey="recall" name="Recall" dot={false} stroke={c.sim} strokeWidth={2} />
          <Line dataKey="f1" name="F1" dot={false} stroke={c.s3} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </Card>
  );
}
