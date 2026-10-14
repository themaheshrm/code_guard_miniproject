import { useEffect, useState } from "react";
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend, ResponsiveContainer } from "recharts";
import { api } from "../api.js";
import { ConfusionMatrix } from "../components.jsx";

const f = (x) => (x == null ? "–" : typeof x === "number" ? x.toFixed(3) : x);

function ModelBlock({ title, m, cmd }) {
  if (!m) return (
    <section><h2>{title}</h2><p className="muted">Not trained yet. Run:</p><pre>{cmd}</pre></section>
  );
  const t = m.test;
  return (
    <section>
      <h2>{title}</h2>
      <p className="muted">Split sizes (by problem, 70/15/15): {Object.entries(m.split_sizes || {}).map(([k, v]) => `${k} ${v}`).join(", ")}. {m.threshold_policy}</p>
      {t && <div className="grid2">
        <div>
          <h3>Test metrics @ threshold {f(t.threshold)}</h3>
          <table><tbody>
            {[["Accuracy", t.accuracy], ["Precision", t.precision], ["Recall", t.recall], ["F1", t.f1], ["ROC-AUC", t.roc_auc], ["PR-AUC", t.pr_auc], ["False-positive rate", t.false_positive_rate]].map(([k, v]) => <tr key={k}><th>{k}</th><td>{f(v)}</td></tr>)}
          </tbody></table>
        </div>
        <div><h3>Confusion matrix</h3><ConfusionMatrix cm={t.confusion_matrix} /></div>
        {t.roc_curve && <div><h3>ROC curve</h3>
          <ResponsiveContainer width="100%" height={240}><LineChart data={t.roc_curve}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="fpr" type="number" domain={[0, 1]} /><YAxis domain={[0, 1]} /><Tooltip /><Line dataKey="tpr" dot={false} stroke="#6b46f0" strokeWidth={2} /></LineChart></ResponsiveContainer></div>}
        {m.feature_importance && <div><h3>Feature importance (gain)</h3>
          <ResponsiveContainer width="100%" height={Math.min(420, m.feature_importance.slice(0, 12).length * 26)}><BarChart data={m.feature_importance.slice(0, 12)} layout="vertical"><XAxis type="number" hide /><YAxis type="category" dataKey="feature" width={140} tick={{ fontSize: 12 }} /><Tooltip /><Bar dataKey="gain" fill="#6b46f0" /></BarChart></ResponsiveContainer></div>}
      </div>}
      {m.by_length?.length > 0 && <><h3>By code length</h3><table><thead><tr><th>Bucket</th><th>n</th><th>Accuracy</th><th>Recall</th><th>FPR</th></tr></thead><tbody>
        {m.by_length.map((r) => <tr key={r.bucket}><td>{r.bucket}</td><td>{r.n}</td><td>{f(r.accuracy)}</td><td>{f(r.recall)}</td><td>{f(r.false_positive_rate)}</td></tr>)}</tbody></table></>}
      {m.by_generator?.length > 0 && <><h3>Recall by generating model</h3><table><thead><tr><th>Generator</th><th>n</th><th>Recall</th></tr></thead><tbody>
        {m.by_generator.map((r) => <tr key={r.generator}><td>{r.generator}</td><td>{r.n}</td><td>{f(r.recall)}</td></tr>)}</tbody></table></>}
    </section>
  );
}

function PlagBlock({ m }) {
  if (!m) return <section><h2>Plagiarism engine</h2><p className="muted">Not evaluated yet. Run:</p><pre>python -m ml.eval_plagiarism --data data/datasets/ai_dataset.jsonl</pre></section>;
  const rows = Object.entries(m.recall_at_threshold);
  return (
    <section>
      <h2>Plagiarism engine</h2>
      <p className="muted">{m.n_programs} programs from {m.corpus}; {m.n_negative_pairs} unrelated pairs. Threshold {m.config.threshold}, k={m.config.k}, w={m.config.w}.</p>
      <div className="grid2">
        <div><h3>Recall on obfuscated copies</h3><table><tbody>{rows.map(([k, v]) => <tr key={k}><th>{k.replace("_", " ")}</th><td>{f(v)}</td></tr>)}
          <tr><th>False positives (unrelated)</th><td>{f(m.negative_fpr_at_threshold)}</td></tr></tbody></table></div>
        <div><h3>Threshold sweep</h3>
          <ResponsiveContainer width="100%" height={240}><LineChart data={m.sweep}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="threshold" /><YAxis domain={[0, 1]} /><Tooltip /><Legend />
            <Line dataKey="precision" dot={false} stroke="#c97a00" strokeWidth={2} /><Line dataKey="recall" dot={false} stroke="#6b46f0" strokeWidth={2} /><Line dataKey="f1" dot={false} stroke="#0e8a7b" strokeWidth={2} /></LineChart></ResponsiveContainer></div>
      </div>
    </section>
  );
}

export default function Evaluation() {
  const [m, setM] = useState(null), [err, setErr] = useState(null);
  useEffect(() => { api.metrics().then(setM).catch((e) => setErr(e.message)); }, []);
  if (err) return <div className="page"><div className="err">{err}</div></div>;
  if (!m) return <div className="page"><p className="muted">Loading evaluation…</p></div>;
  return (
    <div className="page"><div className="eval">
      <p className="muted">Results come from the training and evaluation scripts. They describe the dataset they were run on; always report false-positive rates alongside accuracy.</p>
      <ModelBlock title="AI-code detector: XGBoost baseline" m={m.xgboost} cmd="python -m ml.train_xgboost --data data/datasets/ai_dataset.jsonl" />
      <ModelBlock title="AI-code detector: CodeBERT" m={m.codebert} cmd="python -m ml.train_codebert --task ai --data data/datasets/ai_dataset.jsonl" />
      <PlagBlock m={m.plagiarism} />
      <ModelBlock title="Vulnerability classifier (stretch)" m={m.vulnerability} cmd="python -m ml.prepare_vuln --dataset devign --out data/datasets/vuln_dataset.jsonl && python -m ml.train_codebert --task vuln --data data/datasets/vuln_dataset.jsonl" />
    </div></div>
  );
}
