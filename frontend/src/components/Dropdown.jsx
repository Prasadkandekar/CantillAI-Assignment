import React from "react";
import { createPortal } from "react-dom";
import usePopover from "../hooks/usePopover.js";
import Icon from "./Icon.jsx";

const Ctx = React.createContext(() => {});

// Generic menu. trigger: ({open, props}) => node; spread `props` onto the trigger button.
export default function Dropdown({ trigger, children, align = "left", direction = "auto", minWidth = 220 }) {
  const { open, setOpen, style, up, triggerRef, popRef } = usePopover({ align, direction, minWidth });
  const uid = React.useId();

  const onTriggerKey = (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
    }
  };
  const onMenuKey = (e) => {
    const items = [...popRef.current.querySelectorAll('[role="menuitem"]:not([disabled])')];
    const i = items.indexOf(document.activeElement);
    let next = -1;
    if (e.key === "ArrowDown") next = (i + 1) % items.length;
    else if (e.key === "ArrowUp") next = (i - 1 + items.length) % items.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = items.length - 1;
    if (next >= 0) {
      e.preventDefault();
      items[next]?.focus();
    }
  };

  React.useEffect(() => {
    if (open && style) popRef.current?.querySelector('[role="menuitem"]')?.focus();
  }, [open, style, popRef]);

  const props = {
    ref: triggerRef,
    type: "button",
    "aria-haspopup": "menu",
    "aria-expanded": open,
    "aria-controls": open ? `${uid}-menu` : undefined,
    onClick: () => setOpen((o) => !o),
    onKeyDown: onTriggerKey,
  };
  return (
    <Ctx.Provider value={() => setOpen(false)}>
      {trigger({ open, props })}
      {open &&
        style &&
        createPortal(
          <div
            ref={popRef}
            id={`${uid}-menu`}
            role="menu"
            style={style}
            onKeyDown={onMenuKey}
            className={`popover ${up ? "origin-bottom" : "origin-top"}`}
          >
            {children}
          </div>,
          document.body
        )}
    </Ctx.Provider>
  );
}

export function DropdownItem({ icon, onClick, danger = false, children, disabled }) {
  const close = React.useContext(Ctx);
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={() => {
        close();
        onClick?.();
      }}
      className={`popover-item hover:bg-surface-card focus-visible:bg-surface-card focus-visible:outline-none ${danger ? "!text-error" : ""}`}
    >
      {icon && <Icon name={icon} size={16} />}
      {children}
    </button>
  );
}

export function DropdownLabel({ children }) {
  return <div className="px-3 py-2 text-caption text-muted">{children}</div>;
}

export function DropdownDivider() {
  return <div className="my-1 border-t border-hairline-soft" role="separator" />;
}
