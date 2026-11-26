const BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function req(path, opts = {}) {
  let r;
  try {
    r = await fetch(BASE + path, opts);
  } catch {
    throw new ApiError("Cannot reach the CodeGuard API. Start the backend (start.bat or `uvicorn app.main:app --port 8000`) and try again.", 0);
  }
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      if (typeof j.detail === "string") msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ");
      else if (j.detail) msg = JSON.stringify(j.detail);
    } catch { /* non-JSON error body */ }
    throw new ApiError(msg, r.status);
  }
  return r.status === 204 ? null : r.json();
}

const json = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function poll(fetcher, onStatus, { interval = 350, timeoutMs = 10 * 60 * 1000 } = {}) {
  const end = Date.now() + timeoutMs;
  let wait = interval;
  while (Date.now() < end) {
    const j = await fetcher();
    onStatus?.(j.status, j);
    if (j.status === "done") return j;
    if (j.status === "failed") throw new ApiError(j.error || "Task failed", 500);
    await sleep(wait);
    wait = Math.min(1500, wait * 1.25);
  }
  throw new ApiError("Timed out waiting for the server.", 408);
}

export const api = {
  base: BASE,
  health: () => req("/api/v1/health"),
  stats: (days = 14) => req(`/api/v1/stats?days=${days}`),
  rules: () => req("/api/v1/rules"),
  job: (id) => req(`/api/v1/jobs/${id}`),
  analyses: (params = {}) => req(`/api/v1/analyses?${new URLSearchParams({ limit: 200, ...params })}`),
  remove: (id) => req(`/api/v1/analyses/${id}`, { method: "DELETE" }),
  clearHistory: (includeCorpus = false) => req(`/api/v1/analyses?include_corpus=${includeCorpus}`, { method: "DELETE" }),
  exportUrl: (id) => `${BASE}/api/v1/analyses/${id}/export`,
  corpus: () => req("/api/v1/corpus"),
  corpusItem: (id) => req(`/api/v1/corpus/${id}`),
  removeSubmission: (id) => req(`/api/v1/corpus/${id}`, { method: "DELETE" }),
  metrics: () => req("/api/v1/metrics"),
  reloadModels: () => req("/api/v1/models/reload", { method: "POST" }),
  task: (id) => req(`/api/v1/tasks/${id}`),
  async run(files, options, title, onStatus) {
    const { id } = await req("/api/v1/jobs", json({ files, options, title: title || null }));
    return poll(() => api.job(id), onStatus);
  },
  async train(file, maxFpr, onStatus) {
    const fd = new FormData();
    fd.append("dataset", file);
    fd.append("max_fpr", String(maxFpr));
    const t = await req("/api/v1/train/xgboost", { method: "POST", body: fd });
    return poll(() => api.task(t.id), onStatus, { interval: 600 });
  },
  async benchmark(n, onStatus) {
    const t = await req(`/api/v1/benchmark/plagiarism?n=${n}`, { method: "POST" });
    return poll(() => api.task(t.id), onStatus, { interval: 500 });
  },
};
