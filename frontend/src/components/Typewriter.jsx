import React from "react";

const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// Types `lines` ([{ text, className }]) one character at a time. A hidden full copy reserves the height.
export default function Typewriter({ lines, speed = 22, startDelay = 400, className = "" }) {
  const total = React.useMemo(() => lines.reduce((n, l) => n + l.text.length, 0), [lines]);
  const [count, setCount] = React.useState(() => (reduced() ? total : 0));

  React.useEffect(() => {
    if (reduced()) {
      setCount(total);
      return undefined;
    }
    let timer;
    const start = setTimeout(() => {
      timer = setInterval(() => {
        setCount((c) => {
          if (c >= total) {
            clearInterval(timer);
            return c;
          }
          return c + 1;
        });
      }, speed);
    }, startDelay);
    return () => {
      clearTimeout(start);
      clearInterval(timer);
    };
  }, [total, speed, startDelay]);

  const render = (limit) => {
    let left = limit;
    return lines.map((l, i) => {
      const shown = l.text.slice(0, Math.max(0, left));
      left -= l.text.length;
      return (
        <div key={i} className={`whitespace-pre-wrap break-words ${l.className || ""}`}>
          {shown || "\u00A0"}
        </div>
      );
    });
  };

  const typing = count < total;
  return (
    <div className={`relative ${className}`} aria-label={lines.map((l) => l.text).join(" ")}>
      <div className="invisible" aria-hidden="true">
        {render(total)}
      </div>
      <div className="absolute inset-0" aria-hidden="true">
        {render(count)}
        {typing && <span className="inline-block h-4 w-2 translate-y-0.5 animate-blink bg-primary" />}
      </div>
    </div>
  );
}
