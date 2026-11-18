import React from "react";
import Icon from "./Icon.jsx";
import SpikeMark from "./SpikeMark.jsx";

// glyph: an Icon name, or omit for the spike mark.
export default function EmptyState({ glyph, title, body, action }) {
  return (
    <div className="flex flex-col items-center px-lg py-xxl text-center animate-fade-up">
      <span className="mb-md text-primary">{glyph ? <Icon name={glyph} size={32} /> : <SpikeMark size={32} />}</span>
      <h3 className="display-sm">{title}</h3>
      {body && <p className="mt-2 max-w-md text-body-sm text-muted">{body}</p>}
      {action && <div className="mt-lg">{action}</div>}
    </div>
  );
}
