import { createContext, useContext, useState, useCallback } from 'react';
import * as api from '../api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('apex_token'));
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('apex_user');
      return stored && stored !== 'undefined' ? JSON.parse(stored) : null;
    } catch { return null; }
  });

  const handleLogin = useCallback(async (email, password) => {
    const data = await api.login(email, password);
    if (!data?.access_token) throw new Error('Invalid login response');
    const user = data.user ?? { email };
    localStorage.setItem('apex_token', data.access_token);
    localStorage.setItem('apex_user', JSON.stringify(user));
    setToken(data.access_token);
    setUser(user);
    return data;
  }, []);

  const handleLogout = useCallback(() => {
    localStorage.removeItem('apex_token');
    localStorage.removeItem('apex_user');
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, login: handleLogin, logout: handleLogout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
