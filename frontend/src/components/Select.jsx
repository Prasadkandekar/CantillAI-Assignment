import React from "react";
import { createPortal } from "react-dom";
import Icon from "./Icon.jsx";
import usePopover from "../hooks/usePopover.js";

// Accessible custom listbox. onChange receives the option value (not an event).
// options: [{value,label,hint?}]
export default function Select({
  value,
  onChange,
  options,
  placeholder = "Select…",
  label,
  disabled = false,
  error = false,
  size = "md",
  align = "left",
  className = "",
  id,
  "aria-label": ariaLabel,
}) {
  const uid = React.useId();
  const listId = `${uid}-list`;
  const { open, setOpen, style, up, triggerRef, popRef } = usePopover({ align, estHeight: Math.min(options.length * 38 + 8, 280) });
  const [active, setActive] = React.useState(-1);
  const typed = React.useRef({ text: "", t: 0 });
  const selectedIndex = options.findIndex((o) => String(o.value) === String(value));
  const selected = selectedIndex >= 0 ? options[selectedIndex] : null;

  const openList = () => {
    if (disabled) return;
    setActive(selectedIndex >= 0 ? selectedIndex : 0);
    setOpen(true);
  };
  const choose = (i) => {
    const o = options[i];
    if (!o) return;
    onChange(o.value);
    setOpen(false);
    triggerRef.current?.focus();
  };

  React.useEffect(() => {
    if (!open || active < 0) return;
    document.getElementById(`${uid}-opt-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [open, active, uid]);

  const typeahead = (ch) => {
    const now = Date.now();
    const t = typed.current;
    t.text = now - t.t > 700 ? ch : t.text + ch;
    t.t = now;
    const q = t.text.toLowerCase();
    const start = t.text.length === 1 ? active + 1 : active;
    for (let k = 0; k < options.length; k++) {
      const i = (start + k + options.length) % options.length;
      if (String(options[i].label).toLowerCase().startsWith(q)) {
        setActive(i);
        return;
      }
    }
  };

  const onKeyDown = (e) => {
    if (disabled) return;
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
        e.preventDefault();
        openList();
      } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        openList();
        typeahead(e.key);
      }
      return;
    }
    const n = options.length;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % n);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a - 1 + n) % n);
    } else if (e.key === "Home") {
      e.preventDefault();
      setActive(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActive(n - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      choose(active);
    } else if (e.key === "Tab") {
      setOpen(false);
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      typeahead(e.key);
    }
  };

  const h = size === "sm" ? "h-9" : "h-10";
  return (
    <div className={`relative ${className}`}>
      {label && (
        <label className="label" htmlFor={id || `${uid}-btn`}>
          {label}
        </label>
      )}
      <button
        type="button"
        id={id || `${uid}-btn`}
        ref={triggerRef}
        disabled={disabled}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open && active >= 0 ? `${uid}-opt-${active}` : undefined}
        aria-label={ariaLabel}
        aria-invalid={error || undefined}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onKeyDown}
        className={`input flex ${h} items-center justify-between gap-2 text-left ${error ? "input-error" : ""} ${open ? "border-primary ring-[3px] ring-primary/15" : ""}`}
      >
        <span className={`truncate ${selected ? "text-ink" : "text-muted-soft"}`}>{selected ? selected.label : placeholder}</span>
        <Icon name="chevron-down" size={16} className={`text-muted transition-transform duration-150 ${open ? "rotate-180" : ""}`} />
      </button>
      {open &&
        style &&
        createPortal(
          <ul
            ref={popRef}
            id={listId}
            role="listbox"
            aria-label={ariaLabel || label}
            style={style}
            className={`popover max-h-72 overflow-auto ${up ? "origin-bottom" : "origin-top"}`}
          >
            {options.map((o, i) => {
              const isSel = i === selectedIndex;
              return (
                <li
                  key={String(o.value)}
                  id={`${uid}-opt-${i}`}
                  role="option"
                  aria-selected={isSel}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => choose(i)}
                  className={`popover-item justify-between ${i === active ? "popover-item-active" : ""}`}
                >
                  <span className="min-w-0">
                    <span className={`block truncate ${isSel ? "font-medium" : ""}`}>{o.label}</span>
                    {o.hint && <span className="block truncate text-caption text-muted">{o.hint}</span>}
                  </span>
                  {isSel && <Icon name="check" size={16} className="text-primary" />}
                </li>
              );
            })}
            {options.length === 0 && <li className="px-3 py-2 text-body-sm text-muted">No options</li>}
          </ul>,
          document.body
        )}
    </div>
  );
}
