import React from "react";
import Badge from "./Badge.jsx";
import Icon from "./Icon.jsx";
import { useToast } from "./Toast.jsx";

const ALERT = {
  error: { cls: "border-error/40 bg-error/10 text-error", icon: "alert" },
  info: { cls: "border-hairline bg-surface-soft text-body", icon: "info" },
  success: { cls: "border-success/40 bg-success/10 text-body-strong", icon: "check" },
  warning: { cls: "border-warning/40 bg-warning/10 text-body-strong", icon: "alert" },
};

export function Alert({ kind = "error", children, onClose }) {
  if (!children) return null;
  const a = ALERT[kind] || ALERT.error;
  return (
    <div className={`my-2 flex items-start gap-2 whitespace-pre-wrap rounded-md border px-3 py-2 text-body-sm animate-fade-in ${a.cls}`} role="alert">
      <Icon name={a.icon} size={16} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">{children}</div>
      {onClose && (
        <button className="text-caption underline" onClick={onClose}>
          dismiss
        </button>
      )}
    </div>
  );
}

const ROUTE_TONE = {
  SPOT_PO: "success",
  CONTRACT_PO: "teal",
  EMERGENCY_PO: "amber",
  RFQ: "neutral",
  RFP: "warning",
  CAPEX_SOURCING: "dark",
  NEW_ITEM_SOURCING: "coral",
  NOT_PROCESSED: "error",
};

export function RouteChip({ route, count }) {
  if (!route) return null;
  return (
    <Badge tone={ROUTE_TONE[route] || "neutral"} className="font-mono !text-[12px]">
      {route}
      {count !== undefined && <span className="ml-1 font-semibold">{count}</span>}
    </Badge>
  );
}

const STATUS_TONE = {
  PROPOSED: "amber",
  APPROVED: "success",
  OVERRIDDEN: "neutral",
  ACTIVE: "success",
  SUPERSEDED: "neutral",
  DRAFT: "warning",
  DISCARDED: "neutral",
};

export function StatusChip({ status }) {
  if (!status) return null;
  return (
    <Badge tone={STATUS_TONE[status] || "neutral"} dot className={status === "DISCARDED" ? "line-through opacity-70" : ""}>
      {status}
    </Badge>
  );
}

export function inr(value) {
  if (value === null || value === undefined || value === "") return "";
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return "₹" + n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function Modal({ title, children, onClose }) {
  React.useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-ink/40 p-4 animate-fade-in" onClick={onClose}>
      <div className="card max-h-[90vh] w-full max-w-lg overflow-auto shadow-pop animate-scale-in" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="mb-md flex items-center justify-between gap-md">
          <h2 className="h2">{title}</h2>
          <button className="btn-icon-ghost" onClick={onClose} aria-label="Close">
            <Icon name="close" size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// Label + control + helper text or validation message. Pass `error` (string) to show the error state.
export function Field({ label, children, hint, error, className = "mb-3" }) {
  return (
    <label className={`block ${className}`}>
      <span className="label">{label}</span>
      {children}
      {error ? <span className="field-error">{error}</span> : hint ? <span className="mt-1 block text-caption font-normal text-muted">{hint}</span> : null}
    </label>
  );
}

export function NextAction({ children }) {
  return <p className="mb-md text-body-sm text-muted">{children}</p>;
}

// Shows an action error as a toast whenever it changes to a non-empty message.
export function useErrorToast(error) {
  const toast = useToast();
  React.useEffect(() => {
    if (error) toast.error(error);
  }, [error, toast]);
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

