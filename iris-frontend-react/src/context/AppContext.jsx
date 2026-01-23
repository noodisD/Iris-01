import { createContext, useContext, useState, useMemo, useCallback } from 'react';

const AppContext = createContext(null);

export const AppProvider = ({ children }) => {
  const [currentTab, setCurrentTab] = useState('chat');
  const [toasts, setToasts] = useState([]);

  // Toast management
  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback((message, type = 'success') => {
    const id = Date.now();
    const newToast = { id, message, type };

    setToasts((prev) => [...prev, newToast]);

    // Auto-remove after 4 seconds
    setTimeout(() => {
      removeToast(id);
    }, 4000);
  }, [removeToast]);

  const value = useMemo(() => ({
    currentTab,
    setCurrentTab,
    toasts,
    showToast,
    removeToast,
  }), [currentTab, toasts, showToast, removeToast]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};

export const useApp = () => {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
};
