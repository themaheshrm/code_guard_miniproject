import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, OctagonAlert, X, XCircle } from "lucide-react";
import { clamp } from "./lib.js";

export const cx = (...a) => a.filter(Boolean).join(" ");

export function Card({ title, icon: Icon, actions, children, className, pad = true, ...rest }) {
  return (
    <section className={cx("card", className)} {...rest}>
      {(title || actions) && (
        <header className="card-h">
          {title && <h3>{Icon && <Icon size={16} aria-hidden />}{title}</h3>}
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      <div className={pad ? "card-b" : undefined}>{children}</div>
    </section>
  );
}

export function Button({ icon: Icon, children, variant = "ghost", size, loading, className, ...rest }) {
  return (
    <button className={cx("btn", variant, size, className)} disabled={loading || rest.disabled} {...rest}>
      {loading ? <span className="spin" aria-hidden /> : Icon && <Icon size={size === "sm" ? 14 : 16} aria-hidden />}
      {children && <span>{children}</span>}
    </button>
  );
}

const TONE_ICON = { good: CheckCircle2, warn: AlertTriangle, bad: OctagonAlert, info: Info, neutral: null, ai: null, sim: null, sec: null };

/** Status always ships with an icon + text, never color alone. */
export function Badge({ tone = "neutral", children, icon, title }) {
  const Icon = icon === false ? null : icon || TONE_ICON[tone];
  return <span className={cx("badge", tone)} title={title}>{Icon && <Icon size={12} aria-hidden />}{children}</span>;
}

export function Stat({ label, value, sub, icon: Icon, tone }) {
  return (
    <div className={cx("stat", tone)}>
      <div className="stat-top">{Icon && <span className="stat-ic"><Icon size={16} aria-hidden /></span>}<span className="stat-l">{label}</span></div>
      <div className="stat-v">{value}</div>
      {sub && <div className="stat-s">{sub}</div>}
    </div>
  );
}

/** Animated radial gauge. value in [0,1]; threshold draws a tick on the ring. */
export function ScoreRing({ value, label, color, threshold, display, sub, size = 112 }) {
  const r = 44, c = 2 * Math.PI * r;
  const [shown, setShown] = useState(0);
  useEffect(() => { const t = requestAnimationFrame(() => setShown(value == null ? 0 : clamp(value))); return () => cancelAnimationFrame(t); }, [value]);
  const tick = threshold != null ? clamp(threshold) * 360 - 90 : null;
  return (
    <figure className="ring" style={{ width: size }} aria-label={`${label}: ${display}`}>
      <svg viewBox="0 0 100 100" width={size} height={size} role="img" aria-hidden>
        <circle cx="50" cy="50" r={r} className="ring-track" />
        <circle cx="50" cy="50" r={r} className="ring-val" stroke={color} strokeDasharray={c}
          strokeDashoffset={c * (1 - shown)} transform="rotate(-90 50 50)" />
        {tick != null && <line x1="50" y1="2" x2="50" y2="12" className="ring-tick" transform={`rotate(${tick + 90} 50 50)`} />}
      </svg>
      <div className="ring-c"><b>{value == null ? "–" : display}</b>{sub && <small>{sub}</small>}</div>
      <figcaption>{label}</figcaption>
    </figure>
  );
}

export function Meter({ value, color, threshold, label }) {
  return (
    <div className="meter" role="meter" aria-valuenow={Math.round((value || 0) * 100)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <span style={{ width: `${clamp(value || 0) * 100}%`, background: color }} />
      {threshold != null && <i style={{ left: `${clamp(threshold) * 100}%` }} title={`threshold ${Math.round(threshold * 100)}%`} />}
    </div>
  );
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs-row" role="tablist">
      {tabs.map(([k, label, count, Icon]) => (
        <button key={k} role="tab" aria-selected={value === k} className="tabbtn" onClick={() => onChange(k)}>
          {Icon && <Icon size={14} aria-hidden />}{label}{count != null && <span className="count">{count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Empty({ icon: Icon, title, children, action }) {
  return (
    <div className="empty">
      {Icon && <div className="empty-ic"><Icon size={26} aria-hidden /></div>}
      {title && <h3>{title}</h3>}
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Skeleton({ h = 16, w = "100%", style }) {
  return <span className="skel" style={{ height: h, width: w, ...style }} />;
}

export function ErrorBox({ children, onRetry }) {
  return (
    <div className="errbox" role="alert"><XCircle size={18} aria-hidden /><div className="grow">{children}</div>
      {onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}</div>
  );
}

export function Modal({ open, onClose, title, children, wide, footer }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => { window.removeEventListener("keydown", onKey); prev?.focus?.(); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={cx("modal", wide && "wide")} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <header className="modal-h"><h3>{title}</h3><button className="iconbtn" onClick={onClose} aria-label="Close"><X size={18} /></button></header>
        <div className="modal-b">{children}</div>
        {footer && <footer className="modal-f">{footer}</footer>}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------------------- toasts / confirm
const ToastCtx = createContext(null);

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const [ask, setAsk] = useState(null);
  const dismiss = useCallback((id) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const push = useCallback((tone, msg) => {
    const id = Math.random().toString(36).slice(2);
    setItems((xs) => [...xs.slice(-3), { id, tone, msg }]);
    setTimeout(() => dismiss(id), tone === "bad" ? 7000 : 3800);
  }, [dismiss]);
  const confirm = useCallback((opts) => new Promise((resolve) => setAsk({ ...opts, resolve })), []);
  const close = (v) => { ask?.resolve(v); setAsk(null); };
  const api = useRef({});
  Object.assign(api.current, { success: (m) => push("good", m), error: (m) => push("bad", m), info: (m) => push("info", m), confirm });
  return (
    <ToastCtx.Provider value={api.current}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((t) => {
          const Icon = TONE_ICON[t.tone] || Info;
          return <div key={t.id} className={cx("toast", t.tone)}><Icon size={16} aria-hidden /><span>{t.msg}</span>
            <button className="iconbtn" onClick={() => dismiss(t.id)} aria-label="Dismiss"><X size={14} /></button></div>;
        })}
      </div>
      <Modal open={!!ask} onClose={() => close(false)} title={ask?.title || "Are you sure?"}
        footer={<><Button onClick={() => close(false)}>Cancel</Button><Button variant={ask?.danger ? "danger" : "primary"} onClick={() => close(true)}>{ask?.confirmLabel || "Confirm"}</Button></>}>
        <p className="muted">{ask?.message}</p>
      </Modal>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);
