import React from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/useAuth.js";
import { useToast } from "./Toast.jsx";
import { PageLoader } from "./SpikeMark.jsx";

function Forbidden() {
  const toast = useToast();
  React.useEffect(() => {
    toast.error("Your role can't open that page");
  }, [toast]);
  return <Navigate to="/chat" replace />;
}

// Not signed in: /login (remembering where to return). Wrong role: /chat with a toast.
export default function ProtectedRoute({ roles }) {
  const { user, status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <PageLoader />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (roles && !roles.includes(user.role)) return <Forbidden />;
  return <Outlet />;
}
