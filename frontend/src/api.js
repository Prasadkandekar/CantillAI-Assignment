// Fetch wrapper: base URL from VITE_API_BASE (Render) or "/api" (dev proxy / nginx), stub identity headers.
const BASE = (import.meta.env.VITE_API_BASE || "/api").replace(/\/$/, "");
const USER_KEY = "corvo_user";
const DEFAULT_USER = { name: "A. Buyer", role: "buyer", department: "Maintenance" };

export function getUser() {
  try {
    return { ...DEFAULT_USER, ...JSON.parse(localStorage.getItem(USER_KEY) || "{}") };
  } catch {
    return DEFAULT_USER;
  }
}

export function setUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event("corvo-user"));
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(formatDetail(detail));
    this.status = status;
    this.detail = detail;
  }
}

export function formatDetail(detail) {
  if (!detail) return "Request failed";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  if (detail.message) {
    const errs = (detail.errors || []).map((e) => `${e.path}: ${e.message}`);
    return [detail.message, ...errs].join("\n");
  }
  return JSON.stringify(detail);
}

function headers(extra = {}) {
  const u = getUser();
  return { "X-User": u.name, "X-Role": u.role, "X-Department": u.department || "", ...extra };
}

async function request(path, { method = "GET", json, form, raw = false } = {}) {
  const opts = { method, headers: headers(json ? { "Content-Type": "application/json" } : {}) };
  if (json !== undefined) opts.body = JSON.stringify(json);
  if (form) opts.body = form;
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return raw ? res : res.json();
}

export const api = {
  get: (path) => request(path),
  post: (path, json) => request(path, { method: "POST", json: json ?? {} }),
  put: (path, json) => request(path, { method: "PUT", json }),
  upload: (path, form) => request(path, { method: "POST", form }),
  async download(path, filename) {
    const res = await request(path, { raw: true });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
};

export function qs(params) {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, v);
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}
