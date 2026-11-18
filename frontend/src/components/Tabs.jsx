import React from "react";

// tabs: [{id,label,count?}]. Arrow keys / Home / End move between tabs.
export default function Tabs({ tabs, value, onChange, className = "" }) {
  const refs = React.useRef({});
  const onKeyDown = (e) => {
    const i = tabs.findIndex((t) => t.id === value);
    let next = -1;
    if (e.key === "ArrowRight") next = (i + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    if (next < 0) return;
    e.preventDefault();
    onChange(tabs[next].id);
    refs.current[tabs[next].id]?.focus();
  };
  return (
    <div className={`tabs ${className}`} role="tablist" onKeyDown={onKeyDown}>
      {tabs.map((t) => {
        const active = t.id === value;
        return (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            className={`tab ${active ? "tab-active" : ""}`}
            onClick={() => onChange(t.id)}
          >
            {t.label}
            {t.count !== undefined && <span className="ml-2 text-caption text-muted-soft">{t.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
