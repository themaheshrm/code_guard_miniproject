import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import { Bot, Copy, Download, ExternalLink, FilePlus2, FileUp, FlaskConical, FolderUp, Pencil, Play, ShieldAlert, UploadCloud, X } from "lucide-react";
import "../monaco.js";
import { api } from "../api.js";
import { ACCEPT, EXAMPLES, LANG_LABEL, MONACO_LANG, download, isSupported, langOf, pairsFor, pct, uniqueName } from "../lib.js";
import { Badge, Button, Empty, ErrorBox, Modal, cx, useToast } from "../ui.jsx";
import { FileReport, FilesTable } from "./Report.jsx";

const Compare = lazy(() => import("./Compare.jsx"));

const OPTIONS = [
  ["run_ai", "AI-code detection", Bot], ["run_plagiarism", "Plagiarism", Copy], ["run_vulnerability", "Vulnerabilities", ShieldAlert],
  ["compare_corpus", "Compare with saved corpus"], ["persist", "Save to corpus"],
];
const LAYERS = [["ai", "AI blocks"], ["sim", "Similarity"], ["vuln", "Security"]];
const MAX_BYTES = 500_000, MAX_FILES = 100;

export default function Workspace({ ws, setWs, job, setJob, theme, go, health }) {
  const toast = useToast();
  const { files, active, options, title } = ws;
  const file = files[Math.min(active, files.length - 1)] || files[0];
  const [layers, setLayers] = useState({ ai: true, sim: true, vuln: true });
  const [selPair, setSelPair] = useState(null);
  const [dragging, setDragging] = useState(0);
  const [renaming, setRenaming] = useState(null);
  const [comparing, setComparing] = useState(null);
  const [tab, setTab] = useState("overview");
  const edRef = useRef(null), monRef = useRef(null), runRef = useRef(null);
  const [ready, setReady] = useState(false);
  const rep = job.report;
  const ranCode = job.ranCode || {};
  const fileRep = rep?.files.find((f) => f.name === file.name);
  const stale = !!fileRep && ranCode[file.name] !== undefined && ranCode[file.name] !== file.code;
  const busy = job.status === "queued" || job.status === "running";
  const nonEmpty = files.filter((f) => f.code.trim()).length;

  const patch = (p) => setWs((s) => ({ ...s, ...p }));
  const setFile = (i, p) => setWs((s) => ({ ...s, files: s.files.map((f, k) => (k === i ? { ...f, ...p } : f)) }));
  const selectByName = (name) => { const i = files.findIndex((f) => f.name === name); if (i >= 0) patch({ active: i }); };

  // ----------------------------------------------------------------- editor decorations
  useEffect(() => {
    const ed = edRef.current, monaco = monRef.current;
    if (!ready || !ed || !monaco || !fileRep || stale) return;
    const max = ed.getModel()?.getLineCount() || 1;
    const mk = (s, e, cls, msg) => ({ range: new monaco.Range(Math.min(s, max), 1, Math.min(e, max), 1),
      options: { isWholeLine: true, linesDecorationsClassName: cls, className: `${cls}-bg`, hoverMessage: { value: msg },
        overviewRuler: { color: cls === "cg-bar-ai" ? "#9887ef" : cls === "cg-bar-sim" ? "#d28e05" : "#eb6263", position: 4 } } });
    const d = [];
    if (layers.ai && fileRep.ai?.blocks) for (const b of fileRep.ai.blocks) if (b.contribution > 0.02) d.push(mk(b.start, b.end, "cg-bar-ai", `**AI attribution** +${b.contribution.toFixed(2)} — \`${b.name}\``));
    if (layers.sim) for (const p of pairsFor(rep, file.name, selPair)) {
      const other = p.a === file.name ? p.b : p.a;
      for (const [s, e] of p.a === file.name ? p.lines_a : p.lines_b) d.push(mk(s, e, "cg-bar-sim", `**Similar to** \`${other}\` (${pct(p.score)})`));
    }
    if (layers.vuln && fileRep.vulnerability) for (const x of fileRep.vulnerability.findings) d.push(mk(x.line, x.line, "cg-bar-vuln", `**${x.severity.toUpperCase()} · ${x.cwe}** ${x.message}${x.fix ? `\n\nFix: ${x.fix}` : ""}`));
    const coll = ed.createDecorationsCollection(d);
    return () => coll.clear();
  }, [rep, file.name, layers, selPair, ready, stale, fileRep]);

  const reveal = useCallback((line, end = line) => {
    const ed = edRef.current;
    if (!ed) return;
    ed.revealLinesInCenter(line, end);
    ed.setSelection({ startLineNumber: line, startColumn: 1, endLineNumber: end, endColumn: 1 });
    ed.focus();
  }, []);

  // ----------------------------------------------------------------- files
  const addFile = () => setWs((s) => {
    const taken = new Set(s.files.map((f) => f.name));
    return { ...s, files: [...s.files, { name: uniqueName(`submission_${s.files.length + 1}.py`, taken), code: "" }], active: s.files.length };
  });
  const removeFile = (i) => setWs((s) => {
    const f = s.files.filter((_, k) => k !== i);
    return { ...s, files: f.length ? f : [{ name: "submission_1.py", code: "" }], active: Math.max(0, Math.min(s.active >= i ? s.active - 1 : s.active, f.length - 1)) };
  });

  async function readFiles(list) {
    const picked = [...list];
    const skipped = [];
    const items = [];
    for (const f of picked) {
      if (!isSupported(f.name)) { skipped.push(`${f.name} (unsupported type)`); continue; }
      if (f.size > MAX_BYTES) { skipped.push(`${f.name} (over 500 KB)`); continue; }
      const code = await f.text();
      if (code.includes("\u0000")) { skipped.push(`${f.name} (binary)`); continue; }
      if (code.trim()) items.push({ name: f.name, code: code.replace(/\r\n/g, "\n") });
    }
    if (skipped.length) toast.info(`Skipped ${skipped.length} file(s): ${skipped.slice(0, 3).join(", ")}${skipped.length > 3 ? "…" : ""}`);
    if (!items.length) return;
    setWs((s) => {
      const keep = s.files.filter((f) => f.code.trim());
      const taken = new Set(keep.map((f) => f.name));
      const added = items.slice(0, Math.max(0, MAX_FILES - keep.length)).map((f) => { const name = uniqueName(f.name, taken); taken.add(name); return { ...f, name }; });
      if (added.length < items.length) toast.info(`Only ${MAX_FILES} files can be analyzed at once.`);
      return { ...s, files: [...keep, ...added], active: keep.length };
    });
    toast.success(`Added ${items.length} file${items.length > 1 ? "s" : ""}.`);
  }

  const loadExample = (ex) => {
    setWs((s) => ({ ...s, files: ex.files.map((f) => ({ ...f })), active: 0, title: ex.title }));
    setJob({ status: "idle", report: null, error: null, ranCode: {} });
    setSelPair(null);
  };

  // ----------------------------------------------------------------- run
  async function run() {
    const payload = files.filter((f) => f.code.trim()).map((f) => ({ name: f.name, code: f.code, language: isSupported(f.name) ? langOf(f.name) : undefined }));
    if (!payload.length || busy) return;
    if (!options.run_ai && !options.run_plagiarism && !options.run_vulnerability) { toast.error("Enable at least one analysis."); return; }
    setJob({ status: "queued", report: job.report, error: null, ranCode: job.ranCode || {} });
    setSelPair(null);
    try {
      const done = await api.run(payload, options, title, (status) => setJob((j) => ({ ...j, status })));
      setJob({ status: "done", report: done.result, error: null, id: done.id, ranCode: Object.fromEntries(payload.map((f) => [f.name, f.code])) });
      const s = done.result.summary;
      toast.success(`Analyzed ${s.n_files} file${s.n_files > 1 ? "s" : ""} in ${Math.round(done.result.duration_ms)} ms.`);
    } catch (e) {
      setJob((j) => ({ ...j, status: "failed", error: e.message }));
      toast.error(e.message);
    }
  }
  runRef.current = run;
  useEffect(() => {
    const onKey = (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); runRef.current(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const codeOf = (name) => (ranCode[name] ?? files.find((f) => f.name === name)?.code ?? "");
  const lang = langOf(file.name);

  return (
    <div className="ws">
      <section className="pane ed-pane" aria-label="Code editor"
        onDragEnter={(e) => { e.preventDefault(); setDragging((d) => d + 1); }} onDragOver={(e) => e.preventDefault()}
        onDragLeave={() => setDragging((d) => Math.max(0, d - 1))}
        onDrop={(e) => { e.preventDefault(); setDragging(0); readFiles(e.dataTransfer.files); }}>
        <div className="ed-top">
          <input className="title-in" value={title || ""} maxLength={200} placeholder="Untitled analysis (e.g. CS101 · Lab 3)" aria-label="Analysis title"
            onChange={(e) => patch({ title: e.target.value })} />
          <div className="ed-tools">
            <Button size="sm" icon={FilePlus2} onClick={addFile} title="New empty file">New</Button>
            <label className="btn ghost sm" title="Upload source files"><FileUp size={14} aria-hidden /><span>Upload</span>
              <input type="file" multiple hidden accept={ACCEPT} onChange={(e) => { readFiles(e.target.files); e.target.value = ""; }} /></label>
            <label className="btn ghost sm" title="Upload every supported file in a folder"><FolderUp size={14} aria-hidden /><span>Folder</span>
              <input type="file" multiple hidden webkitdirectory="" directory="" onChange={(e) => { readFiles(e.target.files); e.target.value = ""; }} /></label>
          </div>
        </div>
        <div className="ftabs" role="tablist" aria-label="Files">
          {files.map((f, i) => {
            const r = rep?.files.find((x) => x.name === f.name);
            return (
              <div key={f.name + i} role="tab" aria-selected={i === active} tabIndex={0} className={cx("ftab", i === active && "on")}
                onClick={() => patch({ active: i })} onKeyDown={(e) => e.key === "Enter" && patch({ active: i })} onDoubleClick={() => setRenaming({ i, name: f.name })} title="Double-click to rename">
                {r && <span className={`lv lv-${r.verdict.level}`} aria-label={r.verdict.level} />}
                <span className="mono">{f.name}</span>
                <button className="x" aria-label={`Remove ${f.name}`} onClick={(e) => { e.stopPropagation(); removeFile(i); }}><X size={12} /></button>
              </div>
            );
          })}
        </div>
        <div className="editor">
          {dragging > 0 && <div className="drop"><UploadCloud size={36} aria-hidden /><b>Drop source files</b><span>.py .java .c .cpp .js</span></div>}
          <Editor height="100%" path={file.name} language={MONACO_LANG[lang]} value={file.code} theme={theme === "dark" ? "cg-dark" : "cg-light"}
            onChange={(v) => setFile(active, { code: v ?? "" })}
            loading={<div className="page-loading"><span className="spin" /> Loading editor…</div>}
            onMount={(ed, monaco) => { edRef.current = ed; monRef.current = monaco; setReady(true); }}
            options={{ minimap: { enabled: false }, fontSize: 13.5, lineHeight: 21, scrollBeyondLastLine: false, automaticLayout: true, padding: { top: 12 },
              fontFamily: "'JetBrains Mono', ui-monospace, Consolas, monospace", fontLigatures: true, smoothScrolling: true,
              cursorSmoothCaretAnimation: "on", lineDecorationsWidth: 10, renderLineHighlight: "line", tabSize: 4 }} />
          {!file.code && <div className="ed-hint"><p>Paste code here, drop files anywhere on this panel, or</p>
            <div className="row-wrap">{EXAMPLES.map((ex) => <Button key={ex.id} size="sm" icon={FlaskConical} onClick={() => loadExample(ex)}>{ex.title}</Button>)}</div></div>}
        </div>
        <div className="ed-status">
          <Badge tone="neutral" icon={false}>{LANG_LABEL[lang]}</Badge>
          <span className="muted">{file.code ? file.code.split("\n").length : 0} lines · {(new Blob([file.code]).size / 1024).toFixed(1)} KB</span>
          <button className="linkbtn" onClick={() => setRenaming({ i: active, name: file.name })}><Pencil size={12} aria-hidden /> Rename</button>
          {stale && <Badge tone="warn">edited since analysis</Badge>}
        </div>
        <div className="opts">
          <div className="toggles">
            {OPTIONS.map(([k, l, Icon]) => (
              <label key={k} className={cx("toggle", options[k] && "on")}>
                <input type="checkbox" checked={!!options[k]} onChange={(e) => patch({ options: { ...options, [k]: e.target.checked } })} />
                <span className="sw" aria-hidden />{Icon && <Icon size={13} aria-hidden />}{l}
              </label>
            ))}
          </div>
          <Button variant="primary" icon={Play} loading={busy} disabled={!nonEmpty || health === false} onClick={run} title="Ctrl + Enter">
            {busy ? (job.status === "queued" ? "Queued…" : "Analyzing…") : `Analyze ${nonEmpty > 1 ? `${nonEmpty} files` : "code"}`}
          </Button>
        </div>
      </section>

      <section className="pane res-pane" aria-label="Results" aria-live="polite">
        <div className="res-h">
          <h2>Integrity report</h2>
          {rep && <div className="row-wrap">
            {job.id && <Button size="sm" icon={ExternalLink} onClick={() => go("report", job.id)}>Full report</Button>}
            <Button size="sm" icon={Download} onClick={() => download(`codeguard-${(rep.title || "report").replace(/\W+/g, "_")}.json`, JSON.stringify(rep, null, 2))}>JSON</Button>
          </div>}
        </div>
        <div className="res-b">
          {busy && <div className="progress" role="status"><div className="progress-bar" /><span>{job.status === "queued" ? "Waiting for a worker…" : "Parsing, fingerprinting and scoring…"}</span></div>}
          {job.error && <ErrorBox>{job.error}</ErrorBox>}
          {health === false && !rep && <ErrorBox>The API is offline. Start the backend, then reload this page.</ErrorBox>}
          {!rep && !busy && (
            <div className="welcome">
              <Empty icon={ShieldAlert} title="Analyze code for integrity risks">
                CodeGuard estimates whether code is AI-generated, finds copying that survives renaming and reordering, and flags insecure lines with fixes.
              </Empty>
              <div className="examples">
                {EXAMPLES.map((ex) => (
                  <button key={ex.id} className="example" onClick={() => loadExample(ex)}>
                    <FlaskConical size={18} aria-hidden /><b>{ex.title}</b><span>{ex.desc}</span><em>{ex.files.length} files</em>
                  </button>
                ))}
              </div>
              <p className="muted small center">Tip: press <kbd>Ctrl</kbd> + <kbd>Enter</kbd> to analyze.</p>
            </div>
          )}
          {rep && (
            <>
              {rep.files.length > 1 && <FilesTable rep={rep} selected={file.name} onSelect={selectByName} />}
              {fileRep ? (
                <>
                  {stale && <div className="note warn">This file changed after the analysis. Editor highlights are hidden until you analyze again.</div>}
                  <div className="layer-row">
                    <span className="muted small">Editor highlights</span>
                    <div className="chips">
                      {LAYERS.map(([k, l]) => <button key={k} className={`chip lay-${k}`} aria-pressed={layers[k]} onClick={() => setLayers({ ...layers, [k]: !layers[k] })}><i />{l}</button>)}
                    </div>
                  </div>
                  <FileReport rep={rep} f={fileRep} reveal={stale ? undefined : reveal} selPair={selPair} setSelPair={setSelPair} tab={tab} setTab={setTab}
                    canCompare onCompare={setComparing} />
                </>
              ) : <div className="note info">“{file.name}” was not part of the last analysis. Analyze again to include it.</div>}
            </>
          )}
        </div>
      </section>

      <RenameModal state={renaming} files={files} onClose={() => setRenaming(null)} onSave={(i, name) => { setFile(i, { name }); setRenaming(null); }} />
      {comparing && <Suspense fallback={null}><Compare pair={comparing} codeOf={codeOf} theme={theme} onClose={() => setComparing(null)} /></Suspense>}
    </div>
  );
}

function RenameModal({ state, files, onClose, onSave }) {
  const [v, setV] = useState("");
  useEffect(() => { if (state) setV(state.name); }, [state]);
  if (!state) return null;
  const clash = files.some((f, k) => k !== state.i && f.name === v.trim());
  const bad = !v.trim() || /[\\/]/.test(v) || clash;
  return (
    <Modal open onClose={onClose} title="Rename file"
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={bad} onClick={() => onSave(state.i, v.trim())}>Rename</Button></>}>
      <form onSubmit={(e) => { e.preventDefault(); if (!bad) onSave(state.i, v.trim()); }}>
        <label className="field"><span>File name — the extension sets the language</span>
          <input autoFocus value={v} onChange={(e) => setV(e.target.value)} className="input mono" /></label>
        {clash && <p className="t-sec small">Another file already has this name.</p>}
        {!clash && v && !isSupported(v) && <p className="muted small">Unknown extension: the server will auto-detect the language.</p>}
      </form>
    </Modal>
  );
}

