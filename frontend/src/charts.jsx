import { createContext, useContext } from "react";
import { pct } from "./lib.js";

// Validated reference palette (dataviz skill): categorical slots stepped per theme, status colors reserved.
const PALETTE = {
  dark: { ai: "#9887ef", sim: "#d28e05", sec: "#eb6263", s1: "#338ced", s2: "#e76624", s3: "#00a888",
    good: "#0aac23", warn: "#d28e05", bad: "#eb6263", crit: "#ff8a8a", grid: "rgba(255,255,255,.06)", axis: "#7d869b", surface: "#12151c",
    heatLo: [24, 28, 37], heatHi: [210, 142, 5] },
  light: { ai: "#6a4ce2", sim: "#f2a600", sec: "#ec4647", s1: "#257de0", s2: "#f47230", s3: "#00b894",
    good: "#008a17", warn: "#c98600", bad: "#d93536", crit: "#a31d1e", grid: "rgba(16,24,40,.07)", axis: "#6b7385", surface: "#ffffff",
    heatLo: [240, 242, 247], heatHi: [214, 132, 0] },
};

export const ThemeCtx = createContext("dark");
export const useColors = () => PALETTE[useContext(ThemeCtx)] || PALETTE.dark;

export const axisProps = (c) => ({ stroke: c.axis, tick: { fill: c.axis, fontSize: 11 }, tickLine: false, axisLine: false });

export function ChartTip({ active, payload, label, fmt = (v) => v, labelFmt = (l) => l }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="ctip">
      {label != null && <div className="ctip-l">{labelFmt(label)}</div>}
      {payload.map((p) => (
        <div key={p.dataKey ?? p.name} className="ctip-r">
          <span className="sw" style={{ background: p.color || p.payload?.fill }} />
          <span className="grow">{p.name}</span><b>{fmt(p.value, p)}</b>
        </div>
      ))}
    </div>
  );
}

function heatColor(v, c) {
  const t = Math.max(0, Math.min(1, v)) ** 0.8;
  const mix = c.heatLo.map((lo, i) => Math.round(lo + (c.heatHi[i] - lo) * t));
  return `rgb(${mix.join(",")})`;
}

/** Pairwise similarity matrix; sequential single hue, value printed in each cell, click selects the pair. */
export function Heatmap({ names, matrix, languages, onSelect, selected, threshold = 0.5 }) {
  const c = useColors();
  const n = names.length;
  return (
    <div className="heat-wrap">
      <div className="heat" style={{ gridTemplateColumns: `minmax(90px, 160px) repeat(${n}, minmax(34px, 1fr))` }} role="grid" aria-label="Pairwise similarity heatmap">
        <span />
        {names.map((nm, j) => <span key={j} className="heat-col" title={nm}>{j + 1}</span>)}
        {names.map((a, i) => [
          <span key={`l${i}`} className="heat-row" title={a}><em>{i + 1}</em>{a}</span>,
          ...names.map((b, j) => {
            const v = matrix[i][j];
            const cross = languages && languages[i] !== languages[j];
            const active = selected && ((selected[0] === a && selected[1] === b) || (selected[0] === b && selected[1] === a));
            const strong = v >= 0.55;
            return (
              <button key={`${i}-${j}`} className={`cell${active ? " on" : ""}${v >= threshold && i !== j ? " flag" : ""}`} disabled={i === j || cross}
                title={i === j ? a : cross ? "Different languages — not compared" : `${a} ↔ ${b}: ${pct(v)}`}
                style={{ background: i === j || cross ? undefined : heatColor(v, c), color: strong ? "#fff" : undefined }}
                onClick={() => onSelect?.(i < j ? [a, b] : [b, a])}>
                {i === j ? "" : cross ? "·" : Math.round(v * 100)}
              </button>
            );
          }),
        ])}
      </div>
      <div className="heat-legend" aria-hidden><span>0%</span><i style={{ background: `linear-gradient(90deg, ${heatColor(0, c)}, ${heatColor(1, c)})` }} /><span>100%</span>
        <span className="muted">· outlined cells ≥ threshold {pct(threshold)}</span></div>
    </div>
  );
}

export function ConfusionMatrix({ cm, labels = ["human", "AI"] }) {
  const total = Math.max(1, cm.tn + cm.fp + cm.fn + cm.tp);
  const cell = (v, good) => <div className={`cm-c ${good ? "good" : "bad"}`} style={{ "--a": 0.12 + Math.min(0.6, (v / total) * 1.6) }}><b>{v}</b><small>{pct(v / total)}</small></div>;
  return (
    <div className="cm" aria-label="Confusion matrix">
      <div /><div className="cm-h">pred. {labels[0]}</div><div className="cm-h">pred. {labels[1]}</div>
      <div className="cm-h">actual {labels[0]}</div>{cell(cm.tn, true)}{cell(cm.fp, false)}
      <div className="cm-h">actual {labels[1]}</div>{cell(cm.fn, false)}{cell(cm.tp, true)}
    </div>
  );
}

export function LegendRow({ items }) {
  return <div className="legend">{items.map(([label, color, value]) => (
    <span key={label}><i style={{ background: color }} />{label}{value != null && <b>{value}</b>}</span>))}</div>;
}
