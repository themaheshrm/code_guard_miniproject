import { useCallback, useEffect, useRef, useState } from "react";

const safe = (fn, fallback) => { try { return fn(); } catch { return fallback; } };

/** Hash router: "#/history" -> { page: "history", arg: undefined }; "#/report/abc" -> { page: "report", arg: "abc" }. */
export function useRoute(defaultPage = "dashboard") {
  const parse = () => {
    const [page, arg] = window.location.hash.replace(/^#\/?/, "").split("/");
    return { page: page || defaultPage, arg: arg ? decodeURIComponent(arg) : undefined };
  };
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = useCallback((page, arg) => { window.location.hash = `/${page}${arg ? `/${encodeURIComponent(arg)}` : ""}`; }, []);
  return [route, go];
}

/** useState mirrored to localStorage (per-browser convenience only; failures are ignored). */
export function useLocal(key, initial) {
  const [v, setV] = useState(() => safe(() => {
    const raw = localStorage.getItem(key);
    return raw == null ? (typeof initial === "function" ? initial() : initial) : JSON.parse(raw);
  }, typeof initial === "function" ? initial() : initial));
  const t = useRef();
  useEffect(() => {
    clearTimeout(t.current);
    t.current = setTimeout(() => safe(() => localStorage.setItem(key, JSON.stringify(v))), 250);
    return () => clearTimeout(t.current);
  }, [key, v]);
  return [v, setV];
}

export function useTheme() {
  const [theme, setTheme] = useLocal("cg.theme", "dark");
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}

/** Load async data with loading/error state and a reload function. */
export function useAsync(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const alive = useRef(true);
  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    return fn().then((data) => alive.current && setState({ data, error: null, loading: false }))
      .catch((e) => alive.current && setState((s) => ({ ...s, error: e.message, loading: false })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { alive.current = true; load(); return () => { alive.current = false; }; }, [load]);
  return { ...state, reload: load };
}
