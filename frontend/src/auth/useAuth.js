import React from "react";
import { AuthContext } from "./AuthContext.jsx";

export function useAuth() {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export default useAuth;
