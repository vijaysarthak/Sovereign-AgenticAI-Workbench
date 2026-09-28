import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';
import AppLayout from './components/Layout/AppLayout';
import LoginPage from './pages/LoginPage';
import WorkbenchPage from './pages/WorkbenchPage';
import DocumentsPage from './pages/DocumentsPage';
import KnowledgeBasePage from './pages/KnowledgeBasePage';
import ModelsPage from './pages/ModelsPage';
import SovereigntyPage from './pages/SovereigntyPage';
import GeneratedOutputsPage from './pages/GeneratedOutputsPage';
import AdminPage from './pages/AdminPage';
import ProfilePage from './pages/ProfilePage';

function ProtectedRoute({ children }) {
  const { principal, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-sov-bg flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-2 border-sov-orange border-t-transparent rounded-full animate-spin" />
          <span className="text-sov-text-secondary text-sm">Loading SovereignAI...</span>
        </div>
      </div>
    );
  }

  if (!principal) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <AppLayout>
              <Routes>
                <Route path="/" element={<Navigate to="/workbench" replace />} />
                <Route path="/workbench" element={<WorkbenchPage />} />
                <Route path="/documents" element={<DocumentsPage />} />
                <Route path="/knowledge-base" element={<KnowledgeBasePage />} />
                <Route path="/models" element={<ModelsPage />} />
                <Route path="/sovereignty" element={<SovereigntyPage />} />
                <Route path="/generated-outputs" element={<GeneratedOutputsPage />} />
                <Route path="/admin" element={<AdminPage />} />
                <Route path="/profile" element={<ProfilePage />} />
                <Route path="*" element={<Navigate to="/workbench" replace />} />
              </Routes>
            </AppLayout>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}
