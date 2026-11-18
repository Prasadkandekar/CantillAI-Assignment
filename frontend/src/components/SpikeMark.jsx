import React from "react";

// 12-spoke radial mark. `spinning` rotates it, `pulsing` breathes (loading states).
export default function SpikeMark({ size = 24, spinning = false, pulsing = false, className = "" }) {
  const motion = spinning ? "animate-spin-slow" : pulsing ? "animate-pulse-spike" : "";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
      className={`shrink-0 ${motion} ${className}`}
    >
      {Array.from({ length: 12 }, (_, i) => (
        <line key={i} x1="12" y1="2.5" x2="12" y2={i % 2 ? "7" : "9"} transform={`rotate(${i * 30} 12 12)`} />
      ))}
    </svg>
  );
}

export function PageLoader({ label = "Loading" }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas text-primary" role="status" aria-label={label}>
      <SpikeMark size={40} spinning />
    </div>
  );
}
