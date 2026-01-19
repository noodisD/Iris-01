import { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

const AuthContext = createContext(null);

// Demo mode flag - Set to true to bypass authentication
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);

  // Check for existing session on mount
  useEffect(() => {
    // Enable demo mode if environment variable is set or "demo" is in localStorage
    const demoEnabled = DEMO_MODE || localStorage.getItem('demo_mode') === 'true';

    if (demoEnabled) {
      // Auto-login with demo credentials
      setToken('demo-token-12345');
      setUser('Demo User');
      setLoading(false);
      return;
    }

    const savedToken = localStorage.getItem('access_token');
    const savedUsername = localStorage.getItem('username');

    if (savedToken && savedUsername) {
      setToken(savedToken);
      setUser(savedUsername);
    }
    setLoading(false);
  }, []);

  const login = async (username, password) => {
    // Enable demo mode with special username
    if (username.toLowerCase() === 'demo' || username.toLowerCase() === 'demo user') {
      setToken('demo-token-12345');
      setUser('Demo User');
      localStorage.setItem('demo_mode', 'true');
      return { success: true };
    }

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
  };

  const signup = async (username, password) => {
    // Enable demo mode with special username
    if (username.toLowerCase() === 'demo' || username.toLowerCase() === 'demo user') {
      setToken('demo-token-12345');
      setUser('Demo User');
      localStorage.setItem('demo_mode', 'true');
      return { success: true };
    }

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
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('access_token');
    localStorage.removeItem('username');
  };

  const value = {
    user,
    token,
    loading,
    login,
    signup,
    logout,
    isAuthenticated: !!token,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
