import React from "react";

const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// Counts up from 0 to `value` when it scrolls into view. Reduced motion shows the final value.
export default function AnimatedNumber({ value, duration = 900, format = (n) => Math.round(n).toLocaleString("en-IN"), className = "" }) {
  const target = Number(value) || 0;
  const ref = React.useRef(null);
  const [shown, setShown] = React.useState(reduced() ? target : 0);

  React.useEffect(() => {
    if (reduced() || typeof IntersectionObserver === "undefined") {
      setShown(target);
      return undefined;
    }
    let raf = 0;
    const start = (from) => {
      const t0 = performance.now();
      const tick = (now) => {
        const p = Math.min(1, (now - t0) / duration);
        setShown(from + (target - from) * (1 - Math.pow(1 - p, 3)));
        if (p < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    };
    const el = ref.current;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          io.disconnect();
          start(0);
        }
      },
      { threshold: 0.2 }
    );
    if (el) io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [target, duration]);

  return (
    <span ref={ref} className={`tabular-nums ${className}`}>
      {format(shown)}
    </span>
  );
}
