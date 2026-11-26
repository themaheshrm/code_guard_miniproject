import { useMemo, useState } from "react";
import { BookOpenCheck, Search, Wrench } from "lucide-react";
import { api } from "../api.js";
import { useAsync } from "../hooks.js";
import { LANG_LABEL, SEV_ORDER, cap } from "../lib.js";
import { Badge, Card, Empty, ErrorBox, Skeleton } from "../ui.jsx";

const SEV_TONE = { critical: "bad", high: "bad", medium: "warn", low: "neutral" };

export default function Rules() {
  const { data, error, reload } = useAsync(() => api.rules(), []);
  const [lang, setLang] = useState("all");
  const [sev, setSev] = useState("all");
  const [q, setQ] = useState("");
  const rows = useMemo(() => (data?.rules || [])
    .filter((r) => (lang === "all" || r.languages.includes(lang)) && (sev === "all" || r.severity === sev)
      && (!q || `${r.id} ${r.cwe} ${r.message} ${r.owasp}`.toLowerCase().includes(q.toLowerCase())))
    .sort((a, b) => SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity) || a.id.localeCompare(b.id)), [data, lang, sev, q]);

  if (error) return <div className="page"><ErrorBox onRetry={reload}>{error}</ErrorBox></div>;
  return (
    <div className="page stack">
      <div className="toolbar">
        <div className="chips" role="group" aria-label="Language">
          {["all", "python", "java", "c", "cpp", "javascript"].map((l) => (
            <button key={l} className="chip" aria-pressed={lang === l} onClick={() => setLang(l)}>{l === "all" ? "All languages" : LANG_LABEL[l]}</button>))}
        </div>
        <select className="input sel" value={sev} onChange={(e) => setSev(e.target.value)} aria-label="Severity">
          <option value="all">All severities</option>{SEV_ORDER.map((s) => <option key={s} value={s}>{cap(s)}</option>)}
        </select>
        <div className="search"><Search size={15} aria-hidden /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search CWE, rule or keyword" aria-label="Search rules" /></div>
      </div>
      <p className="muted small">{data ? `${rows.length} of ${data.count} rules.` : ""} Rules run on comment-stripped code, line by line and per multi-line statement. Each finding links to its CWE entry and carries a concrete fix.</p>
      {!data ? <div className="grid-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} h={140} />)}</div>
        : rows.length === 0 ? <Card><Empty icon={BookOpenCheck} title="No rules match" /></Card>
        : <div className="rules-grid">
          {rows.map((r) => (
            <article key={r.id} className={`rule sev-${r.severity}`}>
              <div className="row-wrap"><Badge tone={SEV_TONE[r.severity]}>{cap(r.severity)}</Badge><span className="mono small grow">{r.id}</span>
                <a className="tag" href={`https://cwe.mitre.org/data/definitions/${r.cwe.replace("CWE-", "")}.html`} target="_blank" rel="noreferrer noopener">{r.cwe}</a></div>
              <p>{r.message}</p>
              {r.fix && <div className="fix small"><Wrench size={13} aria-hidden /><span>{r.fix}</span></div>}
              <div className="row-wrap small muted">{r.owasp && <span>OWASP {r.owasp}</span>}<span className="grow" />{r.languages.map((l) => <span key={l} className="tag">{LANG_LABEL[l]}</span>)}</div>
            </article>
          ))}
        </div>}
    </div>
  );
}
