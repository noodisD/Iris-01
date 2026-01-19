import { useState } from 'react';
import AuthForm from './AuthForm';

const Landing = () => {
  const [showAuth, setShowAuth] = useState(false);
  const [authMode, setAuthMode] = useState('signup');

  const handleAuthClick = (mode) => {
    setAuthMode(mode);
    setShowAuth(true);
  };

  if (showAuth) {
    return (
      <AuthForm
        mode={authMode}
        onBack={() => setShowAuth(false)}
        onToggle={() => setAuthMode(authMode === 'signup' ? 'login' : 'signup')}
      />
    );
  }

  return (
    <div className="flex flex-col justify-center items-center min-h-screen text-center px-8">
      <h1 className="text-6xl md:text-7xl gradient-text mb-6 tracking-wider">
        IRIS
      </h1>

      <p className="text-xl text-text-secondary mb-8 max-w-2xl leading-relaxed">
        Your personal AI companion that learns from your patterns, understands
        your conflicts, and guides you with narrative insight. A system that
        grows with you, adapts to you, and helps you understand yourself.
      </p>

      <div className="flex gap-4 flex-wrap justify-center">
        <button
          className="btn-primary"
          onClick={() => handleAuthClick('signup')}
        >
          Sign Up
        </button>
        <button
          className="btn-secondary"
          onClick={() => handleAuthClick('login')}
        >
          Log In
        </button>
      </div>
    </div>
  );
};

export default Landing;
