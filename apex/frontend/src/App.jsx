import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import ProjectDetailPage from './pages/ProjectDetailPage';
import ProductivityPage from './pages/ProductivityPage';
import AdminPage from './pages/AdminPage';
import MaterialsPage from './pages/MaterialsPage';
import ComparePage from './pages/ComparePage';
import FieldActualsPage from './pages/FieldActualsPage';
import BenchmarkingPage from './pages/BenchmarkingPage';
import ErrorBoundary from './components/ErrorBoundary';

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
    </ErrorBoundary>
  );
}
