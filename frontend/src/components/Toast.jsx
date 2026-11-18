import React from "react";
import Icon from "./Icon.jsx";

const Ctx = React.createContext(null);
const TONE = { success: "text-success", error: "text-error", info: "text-primary" };
const ICON = { success: "check", error: "alert", info: "info" };

export function ToastProvider({ children }) {
  const [items, setItems] = React.useState([]);
  const idRef = React.useRef(0);

  const dismiss = React.useCallback((id) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const push = React.useCallback(
    (kind, message) => {
      const id = ++idRef.current;
      setItems((xs) => [...xs.slice(-2), { id, kind, message }]);
      setTimeout(() => dismiss(id), kind === "error" ? 6000 : 4000);
    },
    [dismiss]
  );
  const api = React.useMemo(
    () => ({
      success: (m) => push("success", m),
      error: (m) => push("error", m),
      info: (m) => push("info", m),
    }),
    [push]
  );

  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(92vw,360px)] flex-col gap-2" role="status" aria-live="polite">
        {items.map((t) => (
          <div
            key={t.id}
            className="pointer-events-auto flex items-start gap-3 rounded-lg bg-surface-dark px-4 py-3 text-body-sm text-on-dark shadow-pop animate-toast-in"
          >
            <Icon name={ICON[t.kind]} size={18} className={`mt-0.5 ${TONE[t.kind]}`} />
            <span className="flex-1 whitespace-pre-wrap">{t.message}</span>
            <button className="text-on-dark-soft hover:text-on-dark" onClick={() => dismiss(t.id)} aria-label="Dismiss">
              <Icon name="close" size={14} />
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast() {
  const ctx = React.useContext(Ctx);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
