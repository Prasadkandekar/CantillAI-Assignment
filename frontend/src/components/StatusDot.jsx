import React from "react";

const TONES = {
  success: "bg-success",
  teal: "bg-teal",
  error: "bg-error",
  warning: "bg-warning",
  amber: "bg-amber",
  neutral: "bg-muted-soft",
};

export default function StatusDot({ tone = "success", pulse = false, className = "" }) {
  return (
    <span
      className={`inline-block h-2 w-2 shrink-0 rounded-pill ${TONES[tone] || TONES.neutral} ${pulse ? "animate-pulse-dot" : ""} ${className}`}
      aria-hidden="true"
    />
  );
}
