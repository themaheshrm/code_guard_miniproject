const BASE = import.meta.env.VITE_API_URL || "";

async function req(path, opts) {
  let r;
  try {
    r = await fetch(BASE + path, opts);
  } catch {
    throw new Error("Cannot reach the CodeGuard API. Start the backend (make backend) and try again.");
  }
  if (!r.ok) {
    let msg = r.statusText;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch { /* non-JSON error body */ }
    throw new Error(msg);
  }
  return r.status === 204 ? null : r.json();
}

const json = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  health: () => req("/api/v1/health"),
  job: (id) => req(`/api/v1/jobs/${id}`),
  analyses: () => req("/api/v1/analyses"),
  remove: (id) => req(`/api/v1/analyses/${id}`, { method: "DELETE" }),
  corpus: () => req("/api/v1/corpus"),
  removeSubmission: (id) => req(`/api/v1/corpus/${id}`, { method: "DELETE" }),
  metrics: () => req("/api/v1/metrics"),
  async run(files, options, onStatus) {
    const { id } = await req("/api/v1/jobs", json({ files, options }));
    for (let i = 0; i < 600; i++) {
      const j = await api.job(id);
      onStatus?.(j.status);
      if (j.status === "done") return j;
      if (j.status === "failed") throw new Error(j.error || "Analysis failed");
      await new Promise((r) => setTimeout(r, 400));
    }
    throw new Error("Analysis timed out");
  },
};
