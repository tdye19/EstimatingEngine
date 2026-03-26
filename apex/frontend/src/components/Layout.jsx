import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  LayoutDashboard,
  Library,
  LogOut,
  Zap,
  Shield,
  DollarSign,
  ArrowLeftRight,
  ClipboardList,
  TrendingUp,
} from 'lucide-react';
import LLMStatus from './LLMStatus';

const NAV = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/productivity', icon: Library, label: 'Productivity Library' },
  { to: '/materials', icon: DollarSign, label: 'Material Prices' },
  { to: '/compare', icon: ArrowLeftRight, label: 'Compare' },
  { to: '/field-entry', icon: ClipboardList, label: 'Field Entry' },
  { to: '/benchmarking', icon: TrendingUp, label: 'Benchmarking' },
];

const ADMIN_NAV = { to: '/admin', icon: Shield, label: 'Admin' };

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-900 text-white flex flex-col">
        <div className="p-6 flex items-center gap-3 border-b border-gray-700">
          <Zap className="h-8 w-8 text-apex-400" />
          <div>
            <h1 className="text-lg font-bold tracking-tight">APEX</h1>
            <p className="text-xs text-gray-400">Estimating Platform</p>
          </div>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {[...NAV, ...(user?.role === 'admin' ? [ADMIN_NAV] : [])].map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-apex-600 text-white'
                    : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                }`
              }
            >
              <Icon className="h-5 w-5" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="p-4 space-y-3 border-t border-gray-700">
          <LLMStatus />
          <div className="flex items-center justify-between">
            <div className="text-sm">
              <p className="font-medium text-gray-200">{user?.full_name}</p>
              <p className="text-xs text-gray-400">{user?.role}</p>
            </div>
            <button onClick={handleLogout} className="text-gray-400 hover:text-white">
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
