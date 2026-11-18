import React from "react";

// Open state, outside-click, Esc, and fixed positioning from the trigger rect (flips up when no room below).
export default function usePopover({ align = "left", direction = "auto", minWidth = 0, estHeight = 240 } = {}) {
  const [open, setOpen] = React.useState(false);
  const [style, setStyle] = React.useState(null);
  const [up, setUp] = React.useState(false);
  const triggerRef = React.useRef(null);
  const popRef = React.useRef(null);

  const place = React.useCallback(() => {
    const t = triggerRef.current;
    if (!t) return;
    const r = t.getBoundingClientRect();
    const h = popRef.current?.offsetHeight || estHeight;
    const below = window.innerHeight - r.bottom;
    const goUp = direction === "up" || (direction === "auto" && below < h + 12 && r.top > below);
    const width = Math.max(r.width, minWidth);
    const s = { position: "fixed", minWidth: width, maxWidth: "min(92vw, 420px)" };
    if (align === "right") s.right = Math.max(8, window.innerWidth - r.right);
    else s.left = Math.max(8, Math.min(r.left, window.innerWidth - width - 8));
    if (goUp) s.bottom = window.innerHeight - r.top + 6;
    else s.top = r.bottom + 6;
    setUp(goUp);
    setStyle(s);
  }, [align, direction, minWidth, estHeight]);

  React.useLayoutEffect(() => {
    if (open) place();
    else setStyle(null);
  }, [open, place]);

  React.useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (triggerRef.current?.contains(e.target) || popRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    const onMove = () => place();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", onMove);
    window.addEventListener("scroll", onMove, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onMove);
      window.removeEventListener("scroll", onMove, true);
    };
  }, [open, place]);

  return { open, setOpen, style, up, triggerRef, popRef };
}
