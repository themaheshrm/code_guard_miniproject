import { useMemo, useState } from "react";
import { Bot, Copy, Database, Download, Eye, FileClock, FileInput, Search, ShieldAlert, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { useAsync } from "../hooks.js";
import { LANG_LABEL, LEVEL, cap, fmtDate, pct, timeAgo } from "../lib.js";
import { Badge, Button, Card, Empty, ErrorBox, Modal, Skeleton, Tabs, useToast } from "../ui.jsx";

const STATUS_TONE = { done: "good", failed: "bad", running: "info", queued: "neutral" };

export default function History({ go, onLoad }) {
  const toast = useToast();
  const [tab, setTab] = useState("analyses");
  const [q, setQ] = useState("");
  const [level, setLevel] = useState("all");
  const [view, setView] = useState(null);
  const a = useAsync(() => api.analyses(), []);
  const c = useAsync(() => api.corpus(), []);

  const rows = useMemo(() => (a.data || []).filter((r) => {
    const okQ = !q || (r.title || "").toLowerCase().includes(q.toLowerCase()) || r.id.startsWith(q) || (r.summary?.names || []).some((n) => n.toLowerCase().includes(q.toLowerCase()));
    const okL = level === "all" || (level === "failed" ? r.status === "failed" : r.summary?.level === level);
    return okQ && okL;
  }), [a.data, q, level]);
  const corpus = useMemo(() => (c.data || []).filter((r) => !q || r.name.toLowerCase().includes(q.toLowerCase())), [c.data, q]);

  const act = async (fn, msg) => { try { await fn(); toast.success(msg); a.reload(); c.reload(); } catch (e) { toast.error(e.message); } };
  const delAnalysis = async (r) => {
    if (await toast.confirm({ title: "Delete report?", message: `“${r.title || r.id}” and any code saved to the corpus with it will be removed.`, danger: true, confirmLabel: "Delete" }))
      act(() => api.remove(r.id), "Report deleted.");
  };
  const clearAll = async () => {
    if (await toast.confirm({ title: "Clear history?", message: "Deletes every finished report. Reports whose code is in the saved corpus are kept.", danger: true, confirmLabel: "Clear history" }))
      act(() => api.clearHistory(false), "History cleared.");
  };
  const openCode = async (id) => { try { setView(await api.corpusItem(id)); } catch (e) { toast.error(e.message); } };

  return (
    <div className="page stack">
      <div className="toolbar">
        <Tabs value={tab} onChange={setTab} tabs={[["analyses", "Reports", a.data?.length, FileClock], ["corpus", "Saved corpus", c.data?.length, Database]]} />
        <div className="search"><Search size={15} aria-hidden /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder={tab === "analyses" ? "Search title, file or ID" : "Search file name"} aria-label="Search" /></div>
        {tab === "analyses" && <select className="input sel" value={level} onChange={(e) => setLevel(e.target.value)} aria-label="Filter by verdict">
          <option value="all">All verdicts</option><option value="review">Review</option><option value="attention">Attention</option><option value="clear">Clear</option><option value="failed">Failed</option>
        </select>}
        {tab === "analyses" && <Button variant="danger-ghost" icon={Trash2} onClick={clearAll} disabled={!a.data?.length}>Clear</Button>}
      </div>

      {tab === "analyses" && (
        <Card pad={false}>
          {a.error ? <div className="card-b"><ErrorBox onRetry={a.reload}>{a.error}</ErrorBox></div>
            : !a.data ? <div className="card-b stack">{[0, 1, 2].map((i) => <Skeleton key={i} h={44} />)}</div>
            : rows.length === 0 ? <Empty icon={FileClock} title={a.data.length ? "No matching reports" : "No reports yet"} action={!a.data.length && <Button variant="primary" onClick={() => go("analyze")}>Analyze code</Button>}>
                {a.data.length ? "Try a different search or filter." : "Every analysis you run is listed here."}</Empty>
            : (
              <div className="table-wrap">
                <table className="tbl">
                  <thead><tr><th>Report</th><th>Verdict</th><th className="hide-sm">AI max</th><th className="hide-sm">Similarity</th><th className="hide-sm">Findings</th><th aria-label="Actions" /></tr></thead>
                  <tbody>
                    {rows.map((r) => {
                      const s = r.summary;
                      return (
                        <tr key={r.id} className={r.status === "done" ? "clickable" : ""} onClick={() => r.status === "done" && go("report", r.id)}>
                          <td><b>{r.title || "Untitled"}</b><div className="muted small" title={fmtDate(r.created_at)}>{timeAgo(r.created_at)} · {r.n_files} file{r.n_files > 1 ? "s" : ""}</div></td>
                          <td>{r.status === "done" && s ? <Badge tone={LEVEL[s.level].tone}>{LEVEL[s.level].label}</Badge> : <Badge tone={STATUS_TONE[r.status]} title={r.error || ""}>{cap(r.status)}</Badge>}</td>
                          <td className="hide-sm"><span className="t-ai"><Bot size={13} aria-hidden /> {pct(s?.ai_max)}</span></td>
                          <td className="hide-sm"><span className="t-sim"><Copy size={13} aria-hidden /> {s ? pct(s.max_similarity) : "–"}</span></td>
                          <td className="hide-sm"><span className="t-sec"><ShieldAlert size={13} aria-hidden /> {s?.findings ?? "–"}</span></td>
                          <td className="actions" onClick={(e) => e.stopPropagation()}>
                            <Button size="sm" icon={Eye} disabled={r.status !== "done"} onClick={() => go("report", r.id)} aria-label="Open report">Open</Button>
                            {r.status === "done" && <a className="btn ghost sm" href={api.exportUrl(r.id)} download aria-label="Download JSON"><Download size={14} /></a>}
                            <Button size="sm" variant="danger-ghost" icon={Trash2} onClick={() => delAnalysis(r)} aria-label="Delete report" />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
        </Card>
      )}

      {tab === "corpus" && (
        <Card pad={false}>
          <div className="card-b note info small">Code is stored only when you enable “Save to corpus” before analyzing. Saved files are the reference set for “Compare with saved corpus”.</div>
          {c.error ? <div className="card-b"><ErrorBox onRetry={c.reload}>{c.error}</ErrorBox></div>
            : !c.data ? <div className="card-b"><Skeleton h={120} /></div>
            : corpus.length === 0 ? <Empty icon={Database} title="Corpus is empty">Turn on “Save to corpus” in the Analyze view to build a reference set of past submissions.</Empty>
            : (
              <div className="table-wrap"><table className="tbl">
                <thead><tr><th>File</th><th className="hide-sm">Language</th><th className="hide-sm">Saved</th><th aria-label="Actions" /></tr></thead>
                <tbody>{corpus.map((r) => (
                  <tr key={r.id}>
                    <td><span className="mono">{r.name}</span><div className="muted small">{r.lines} lines · sha {r.sha256.slice(0, 10)}</div></td>
                    <td className="hide-sm">{LANG_LABEL[r.language] || r.language}</td>
                    <td className="hide-sm muted">{fmtDate(r.created_at)}</td>
                    <td className="actions">
                      <Button size="sm" icon={Eye} onClick={() => openCode(r.id)}>View</Button>
                      <Button size="sm" variant="danger-ghost" icon={Trash2} aria-label="Remove from corpus" onClick={() => act(() => api.removeSubmission(r.id), "Removed from corpus.")} />
                    </td>
                  </tr>))}</tbody>
              </table></div>
            )}
        </Card>
      )}

      <Modal open={!!view} onClose={() => setView(null)} wide title={view?.name || ""}
        footer={<><Button onClick={() => setView(null)}>Close</Button><Button variant="primary" icon={FileInput} onClick={() => { onLoad([{ name: view.name, code: view.code }], view.name); setView(null); }}>Open in Analyze</Button></>}>
        {view && <pre className="code-view">{view.code.split("\n").map((l, i) => <div key={i}><span className="ln">{i + 1}</span>{l || " "}</div>)}</pre>}
      </Modal>
    </div>
  );
}
