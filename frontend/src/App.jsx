import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/useAuth.js";
import { rolesFor } from "./nav.js";
import AppLayout from "./components/AppLayout.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import BatchPage from "./pages/BatchPage.jsx";
import WorkspacePage from "./pages/WorkspacePage.jsx";
import PolicyPage from "./pages/PolicyPage.jsx";
import ContractsPage from "./pages/ContractsPage.jsx";
import PreferredSuppliersPage from "./pages/PreferredSuppliersPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import LandingPage from "./pages/LandingPage.jsx";

function Fallback() {
  const { user } = useAuth();
  return <Navigate to={user ? "/chat" : "/"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:conversationId" element={<ChatPage />} />
          <Route element={<ProtectedRoute roles={rolesFor("/batch")} />}>
            <Route path="/batch" element={<BatchPage />} />
            <Route path="/workspace" element={<WorkspacePage />} />
            <Route path="/contracts" element={<ContractsPage />} />
            <Route path="/preferred" element={<PreferredSuppliersPage />} />
          </Route>
          <Route element={<ProtectedRoute roles={rolesFor("/policy")} />}>
            <Route path="/policy" element={<PolicyPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Fallback />} />
    </Routes>
  );
}
