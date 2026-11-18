import React from "react";

export function Alert({ kind = "error", children, onClose }) {
  if (!children) return null;
  const color = {
    error: "border-rose-300 bg-rose-50 text-rose-800",
    info: "border-sky-300 bg-sky-50 text-sky-800",
    success: "border-emerald-300 bg-emerald-50 text-emerald-800",
    warning: "border-amber-300 bg-amber-50 text-amber-800",
  }[kind];
  return (
    <div className={`my-2 whitespace-pre-wrap rounded-md border px-3 py-2 text-sm ${color}`} role="alert">
      {children}
      {onClose && (
        <button className="float-right text-xs underline" onClick={onClose}>
          dismiss
        </button>
      )}
    </div>
  );
}

const ROUTE_COLORS = {
  SPOT_PO: "bg-emerald-100 text-emerald-800",
  CONTRACT_PO: "bg-teal-100 text-teal-800",
  EMERGENCY_PO: "bg-orange-100 text-orange-800",
  RFQ: "bg-sky-100 text-sky-800",
  RFP: "bg-indigo-100 text-indigo-800",
  CAPEX_SOURCING: "bg-purple-100 text-purple-800",
  NEW_ITEM_SOURCING: "bg-fuchsia-100 text-fuchsia-800",
  NOT_PROCESSED: "bg-rose-100 text-rose-800",
};

export function RouteChip({ route, count }) {
  if (!route) return null;
  const color = ROUTE_COLORS[route] || "bg-slate-100 text-slate-700";
  return (
    <span className={`inline-block whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-medium ${color}`}>
      {route}
      {count !== undefined && <span className="ml-1 font-bold">{count}</span>}
    </span>
  );
}

export function StatusChip({ status }) {
  const color = {
    PROPOSED: "bg-amber-100 text-amber-800",
    APPROVED: "bg-emerald-100 text-emerald-800",
    OVERRIDDEN: "bg-slate-200 text-slate-600",
    ACTIVE: "bg-emerald-100 text-emerald-800",
    SUPERSEDED: "bg-slate-200 text-slate-600",
    DRAFT: "bg-amber-100 text-amber-800",
    DISCARDED: "bg-slate-100 text-slate-400 line-through",
  }[status] || "bg-slate-100 text-slate-700";
  return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${color}`}>{status}</span>;
}

export function inr(value) {
  if (value === null || value === undefined || value === "") return "";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return "₹" + n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function Modal({ title, children, onClose }) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div className="card max-h-[90vh] w-full max-w-lg overflow-auto" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="h2">{title}</h2>
          <button className="text-slate-500 hover:text-slate-800" onClick={onClose} aria-label="close">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Field({ label, children, hint }) {
  return (
    <label className="mb-2 block text-sm">
      <span className="mb-0.5 block font-medium text-slate-600">{label}</span>
      {children}
      {hint && <span className="block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export function NextAction({ children }) {
  return <p className="mb-3 text-sm text-slate-600">{children}</p>;
}

export function useAsync() {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const run = React.useCallback(async (fn) => {
    setBusy(true);
    setError("");
    try {
      return await fn();
    } catch (e) {
      setError(e.message || String(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, setError, run };
}
