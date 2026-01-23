import { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react';
import api from '../services/api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);

  // Check for existing session on mount
  useEffect(() => {
    const savedToken = localStorage.getItem('access_token');
    const savedUsername = localStorage.getItem('username');

    if (savedToken && savedUsername) {
      setToken(savedToken);
      setUser(savedUsername);
    }
    setLoading(false);
  }, []);

  const login = useCallback(async (username, password) => {
    try {
      const data = await api.login(username, password);

      setToken(data.access_token);
      setUser(data.username);

      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('username', data.username);

      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }, []);

  const signup = useCallback(async (username, password) => {
    try {
      const data = await api.signup(username, password);

      setToken(data.access_token);
      setUser(data.username);

      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('username', data.username);

      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('access_token');
    localStorage.removeItem('username');
  }, []);

  const value = useMemo(() => ({
    user,
    token,
    loading,
    login,
    signup,
    logout,
    isAuthenticated: !!token,
  }), [user, token, loading, login, signup, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
