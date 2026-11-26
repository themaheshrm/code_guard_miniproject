import { useEffect, useState } from "react";
import { ArrowLeft, Bot, Copy, Download, FileText, Printer, ShieldAlert, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { LEVEL, fmtDate, pct } from "../lib.js";
import { Badge, Button, Card, Empty, ErrorBox, Skeleton, Stat, useToast } from "../ui.jsx";
import { FileReport, FilesTable } from "./Report.jsx";

export default function ReportPage({ id, go }) {
  const toast = useToast();
  const [job, setJob] = useState(null);
  const [err, setErr] = useState(null);
  const [sel, setSel] = useState(null);

  useEffect(() => {
    let alive = true, t;
    const load = () => api.job(id).then((j) => {
      if (!alive) return;
      setJob(j);
      if (j.status === "queued" || j.status === "running") t = setTimeout(load, 800);
    }).catch((e) => alive && setErr(e.message));
    if (id) load(); else setErr("No report selected.");
    return () => { alive = false; clearTimeout(t); };
  }, [id]);

  if (err) return <div className="page"><ErrorBox>{err}</ErrorBox><Button icon={ArrowLeft} onClick={() => go("history")}>Back to reports</Button></div>;
  if (!job) return <div className="page stack"><Skeleton h={90} /><Skeleton h={300} /></div>;
  const rep = job.result;
  const del = async () => {
    if (!(await toast.confirm({ title: "Delete report?", message: "This removes the report and any code saved to the corpus with it.", danger: true, confirmLabel: "Delete" }))) return;
    try { await api.remove(job.id); toast.success("Report deleted."); go("history"); } catch (e) { toast.error(e.message); }
  };

  const head = (
    <div className="rp-head">
      <Button icon={ArrowLeft} size="sm" onClick={() => go("history")} className="no-print">Reports</Button>
      <div className="grow">
        <h2>{job.title || "Untitled analysis"}</h2>
        <div className="muted small">{fmtDate(job.created_at)} · {job.n_files} file{job.n_files > 1 ? "s" : ""} · ID <span className="mono">{job.id.slice(0, 8)}</span></div>
      </div>
      <div className="row-wrap no-print">
        {rep && <a className="btn ghost sm" href={api.exportUrl(job.id)} download><Download size={14} aria-hidden /><span>JSON</span></a>}
        {rep && <Button size="sm" icon={Printer} onClick={() => window.print()}>Print / PDF</Button>}
        <Button size="sm" variant="danger-ghost" icon={Trash2} onClick={del}>Delete</Button>
      </div>
    </div>
  );

  if (job.status !== "done") return (
    <div className="page stack">{head}
      {job.status === "failed" ? <ErrorBox>Analysis failed: {job.error}</ErrorBox>
        : <div className="progress" role="status"><div className="progress-bar" /><span>Analysis {job.status}…</span></div>}
    </div>
  );

  const s = rep.summary || {};
  const f = rep.files.find((x) => x.name === sel) || rep.files[0];
  const L = LEVEL[s.level || "clear"];
  return (
    <div className="page stack report-page">
      {head}
      <div className="stats-grid">
        <Stat icon={FileText} label="Overall verdict" value={<Badge tone={L.tone}>{L.label}</Badge>} sub={`${s.levels?.review || 0} review · ${s.levels?.attention || 0} attention · ${s.levels?.clear || 0} clear`} />
        <Stat icon={Bot} tone="ai" label="Likely AI-generated" value={`${s.ai_flagged ?? 0} / ${s.n_files}`} sub={s.ai_mean != null ? `mean likelihood ${pct(s.ai_mean)}` : "AI detection off"} />
        <Stat icon={Copy} tone="sim" label="Similar pairs" value={s.similar_pairs ?? 0} sub={`max similarity ${pct(s.max_similarity)}`} />
        <Stat icon={ShieldAlert} tone="sec" label="Security findings" value={s.findings ?? 0} sub={`${s.high_risk_files ?? 0} high-risk file(s)`} />
      </div>
      {rep.files.length > 1 && <Card title="Files" pad={false}><FilesTable rep={rep} selected={f.name} onSelect={setSel} /></Card>}
      {rep.plagiarism?.clusters?.length > 0 && (
        <Card title="Similarity clusters" icon={Copy}>
          <div className="clusters">{rep.plagiarism.clusters.map((g, i) => (
            <div key={i} className="cluster"><b>Group {i + 1}</b>{g.map((n) => <button key={n} className="chip" onClick={() => setSel(n)}>{n}</button>)}</div>))}</div>
        </Card>
      )}
      <Card title={f.name} icon={FileText}>
        {rep.files.length === 0 ? <Empty title="Empty report" /> : <FileReport rep={rep} f={f} key={f.name} />}
        <p className="muted small">Saved reports keep scores and flagged-line snippets but not the full source, so in-editor highlights are only available in the Analyze view.</p>
      </Card>
    </div>
  );
}
