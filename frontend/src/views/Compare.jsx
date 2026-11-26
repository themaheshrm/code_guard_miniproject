import { useEffect, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import "../monaco.js";
import { MONACO_LANG, langOf, pct } from "../lib.js";
import { Badge, Modal } from "../ui.jsx";

const OPTS = { readOnly: true, minimap: { enabled: false }, fontSize: 12.5, scrollBeyondLastLine: false, automaticLayout: true,
  lineDecorationsWidth: 8, folding: false, renderLineHighlight: "none", fontFamily: "'JetBrains Mono', ui-monospace, Consolas, monospace" };

function Side({ name, code, ranges, theme, edRef, onReady }) {
  return (
    <div className="cmp-side">
      <div className="cmp-h mono">{name}</div>
      <div className="cmp-ed">
        <Editor height="100%" path={`cmp://${name}`} language={MONACO_LANG[langOf(name)]} value={code} theme={theme === "dark" ? "cg-dark" : "cg-light"} options={OPTS}
          onMount={(ed, monaco) => {
            edRef.current = ed;
            ed.createDecorationsCollection(ranges.map(([s, e]) => ({ range: new monaco.Range(s, 1, e, 1),
              options: { isWholeLine: true, className: "cg-bar-sim-bg", linesDecorationsClassName: "cg-bar-sim" } })));
            onReady();
          }} />
      </div>
    </div>
  );
}

/** Side-by-side view of a pair with matched token runs highlighted and AST block matches listed. */
export default function Compare({ pair, codeOf, onClose, theme }) {
  const a = useRef(null), b = useRef(null);
  const [ready, setReady] = useState(0);
  const go = (m) => { a.current?.revealLineInCenter(m.a[0]); b.current?.revealLineInCenter(m.b[0]); };
  useEffect(() => { if (ready === 2 && pair.block_matches?.[0]) go(pair.block_matches[0]); }, [ready]); // eslint-disable-line
  return (
    <Modal open onClose={onClose} wide title={`Compare · ${pct(pair.score)} similar`}>
      <div className="cmp-meta">
        <Badge tone={pair.flagged ? "warn" : "neutral"}>{pair.flagged ? "Above threshold" : "Below threshold"}</Badge>
        <span className="muted">Token overlap {pct(pair.token_similarity)} · Structural (AST) overlap {pair.ast_used ? pct(pair.ast_similarity) : "n/a"}</span>
      </div>
      <div className="cmp">
        <Side name={pair.a} code={codeOf(pair.a)} ranges={pair.lines_a} theme={theme} edRef={a} onReady={() => setReady((r) => r + 1)} />
        <Side name={pair.b} code={codeOf(pair.b)} ranges={pair.lines_b} theme={theme} edRef={b} onReady={() => setReady((r) => r + 1)} />
      </div>
      {pair.block_matches?.length > 0 && (
        <div className="cmp-blocks">
          <span className="muted small">Matched structures (survive renaming & reordering):</span>
          {pair.block_matches.slice(0, 12).map((m, i) => (
            <button key={i} className="chip" onClick={() => go(m)}>L{m.a[0]}–{m.a[1]} ↔ L{m.b[0]}–{m.b[1]} <b>{m.size} nodes</b></button>
          ))}
        </div>
      )}
    </Modal>
  );
}
