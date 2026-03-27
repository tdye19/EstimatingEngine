import { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import ErrorBoundary from './components/ErrorBoundary';

const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage'));
const ProductivityPage = lazy(() => import('./pages/ProductivityPage'));
const AdminPage = lazy(() => import('./pages/AdminPage'));
const MaterialsPage = lazy(() => import('./pages/MaterialsPage'));
const FieldActualsPage = lazy(() => import('./pages/FieldActualsPage'));
const ComparePage = lazy(() => import('./pages/ComparePage'));
const BenchmarkingPage = lazy(() => import('./pages/BenchmarkingPage'));

export default function App() {
  const { token, user } = useAuth();

  if (!token) {
    return (
      <ErrorBoundary>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary>
      <Suspense fallback={<div className="flex items-center justify-center h-screen text-gray-400">Loading…</div>}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/projects/:id/*" element={<ProjectDetailPage />} />
            <Route path="/productivity" element={<ProductivityPage />} />
            <Route path="/materials" element={<MaterialsPage />} />
            <Route path="/compare" element={<ComparePage />} />
            <Route path="/field-entry" element={<FieldActualsPage />} />
            <Route path="/benchmarking" element={<BenchmarkingPage />} />
            {user?.role === 'admin' && (
              <Route path="/admin" element={<AdminPage />} />
            )}
          </Route>
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
