import { AuthProvider, useAuth } from './context/AuthContext';
import { AppProvider } from './context/AppContext';
import Landing from './components/auth/Landing';
import MainLayout from './components/layout/MainLayout';
import Toast from './components/shared/Toast';

function AppContent() {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-text-primary text-xl">Loading...</div>
      </div>
    );
  }

  return (
    <>
      {isAuthenticated ? <MainLayout /> : <Landing />}
      <Toast />
    </>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppProvider>
        <AppContent />
      </AppProvider>
    </AuthProvider>
  );
}

export default App;
