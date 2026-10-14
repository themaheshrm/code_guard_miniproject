import { pct } from "./lib.js";

export function Meter({ label, value, color, threshold, text }) {
  return (
    <div className="sig">
      <span>{label}</span>
      <div className="meter" role="img" aria-label={`${label} ${text ?? pct(value)}`}>
        <span style={{ width: `${Math.min(100, (value || 0) * 100)}%`, background: color }} />
        {threshold != null && <i style={{ left: `${threshold * 100}%` }} title={`decision threshold ${pct(threshold)}`} />}
      </div>
      <b>{text ?? pct(value)}</b>
    </div>
  );
}

const shade = (v) => `hsl(${35 - v * 35} ${40 + v * 45}% ${88 - v * 50}%)`;

export function Heatmap({ names, matrix, onSelect, selected }) {
  const n = names.length;
  return (
    <div className="heat" style={{ gridTemplateColumns: `110px repeat(${n}, minmax(28px, 1fr))` }} role="table" aria-label="Pairwise similarity heatmap">
      <span />
      {names.map((nm, j) => <span key={j} className="lab" style={{ textAlign: "center" }} title={nm}>{j + 1}</span>)}
      {names.map((a, i) => (
        <HeatRow key={i} i={i} a={a} names={names} matrix={matrix} onSelect={onSelect} selected={selected} />
      ))}
    </div>
  );
}

function HeatRow({ i, a, names, matrix, onSelect, selected }) {
  return (
    <>
      <span className="lab" title={a}>{i + 1}. {a}</span>
      {names.map((b, j) => {
        const v = matrix[i][j];
        const active = selected && ((selected[0] === a && selected[1] === b) || (selected[0] === b && selected[1] === a));
        return (
          <button key={j} className="cell" disabled={i === j} title={`${a} ↔ ${b}: ${pct(v)}`}
            style={{ background: i === j ? "#cfd6e4" : shade(v), color: v > 0.55 ? "#fff" : "#172033", outline: active ? "2px solid #172033" : "none" }}
            onClick={() => onSelect(i < j ? [a, b] : [b, a])}>
            {i === j ? "" : Math.round(v * 100)}
          </button>
        );
      })}
    </>
  );
}

export function ConfusionMatrix({ cm }) {
  const total = Math.max(1, cm.tn + cm.fp + cm.fn + cm.tp);
  const tint = (v, good) => ({ background: `${good ? "rgba(14,138,123," : "rgba(196,48,63,"}${0.08 + Math.min(0.55, (v / total) * 1.5)})` });
  return (
    <div className="cm" aria-label="Confusion matrix">
      <div className="h" /><div className="h">pred. human</div><div className="h">pred. AI</div>
      <div className="h">actual human</div><div style={tint(cm.tn, true)}>{cm.tn}</div><div style={tint(cm.fp, false)}>{cm.fp}</div>
      <div className="h">actual AI</div><div style={tint(cm.fn, false)}>{cm.fn}</div><div style={tint(cm.tp, true)}>{cm.tp}</div>
    </div>
  );
}
