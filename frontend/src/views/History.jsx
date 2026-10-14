import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function History({ onOpen }) {
  const [rows, setRows] = useState(null), [corpus, setCorpus] = useState([]), [err, setErr] = useState(null);
  const load = () => Promise.all([api.analyses(), api.corpus()]).then(([a, c]) => { setRows(a); setCorpus(c); }).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const del = async (fn, id) => { try { await fn(id); await load(); } catch (e) { setErr(e.message); } };
  if (err) return <div className="page"><div className="err">{err}</div></div>;
  if (!rows) return <div className="page"><p className="muted">Loading…</p></div>;
  return (
    <div className="page"><div className="eval">
      <section>
        <h2>Past analyses</h2>
        {rows.length === 0 && <p className="muted">Nothing yet. Run an analysis from the Workspace.</p>}
        {rows.map((a) => (
          <div className="row" key={a.id}>
            <span className="grow">{new Date(a.created_at).toLocaleString()} · {a.n_files} file{a.n_files > 1 ? "s" : ""} · {a.status}</span>
            <button className="btn" disabled={a.status !== "done"} onClick={async () => onOpen(await api.job(a.id))}>Open report</button>
            <button className="btn danger" onClick={() => confirm("Delete this analysis and any code saved with it?") && del(api.remove, a.id)}>Delete</button>
          </div>
        ))}
      </section>
      <section>
        <h2>Saved corpus</h2>
        <p className="muted">Code is stored only when you tick “Save submissions to corpus”. Saved files are used for “Compare with saved corpus”.</p>
        {corpus.length === 0 && <p className="muted">No saved submissions.</p>}
        {corpus.map((c) => (
          <div className="row" key={c.id}><span className="grow">{c.name} <span className="muted">({c.language})</span></span>
            <button className="btn danger" onClick={() => del(api.removeSubmission, c.id)}>Remove</button></div>
        ))}
      </section>
    </div></div>
  );
}
