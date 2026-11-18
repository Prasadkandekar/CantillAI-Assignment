import React from "react";
import Icon from "./Icon.jsx";
import SpikeMark from "./SpikeMark.jsx";

const VARIANT = {
  primary: "btn-primary",
  secondary: "btn-secondary",
  ghost: "btn-ghost",
  danger: "btn-danger",
  "secondary-dark": "btn-secondary-dark",
};

export default function Button({ variant = "primary", loading = false, icon, className = "", children, disabled, ...rest }) {
  return (
    <button className={`${VARIANT[variant] || VARIANT.primary} ${className}`} disabled={disabled || loading} {...rest}>
      {loading ? <SpikeMark size={16} spinning /> : icon ? <Icon name={icon} size={16} /> : null}
      {children}
    </button>
  );
}
