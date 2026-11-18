import React from "react";

export default function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-lg flex flex-wrap items-end justify-between gap-md">
      <div className="min-w-0">
        <h1 className="display-sm">{title}</h1>
        {subtitle && <p className="mt-1 text-body-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-xs">{actions}</div>}
    </div>
  );
}
