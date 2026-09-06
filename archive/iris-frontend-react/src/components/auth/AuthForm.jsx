import { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useApp } from '../../context/AppContext';

const AuthForm = ({ mode, onBack, onToggle }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const { login, signup } = useAuth();
  const { showToast } = useApp();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    const result =
      mode === 'signup'
        ? await signup(username, password)
        : await login(username, password);

    setLoading(false);

    if (!result.success) {
      setError(result.error);
    } else {
      showToast(
        mode === 'signup'
          ? 'Welcome to IRIS! Your journey begins now.'
          : 'Welcome back! Ready to continue your journey?',
        'success'
      );
    }
  };

  const title = mode === 'signup' ? 'Create Account' : 'Welcome Back';
  const submitText = mode === 'signup' ? 'Get Started' : 'Sign In';
  const toggleText =
    mode === 'signup' ? 'Already have an account?' : 'Need an account?';

  return (
    <div className="flex flex-col justify-center items-center min-h-screen px-6 animate-fade-in bg-bg-deep">
      <div className="glass-surface p-10 w-full max-w-md shadow-2xl border-primary-amber/10">
        <h2 className="text-4xl font-black text-gradient-gold mb-2 text-center">IRIS</h2>
        <p className="text-text-secondary text-sm mb-8 text-center font-medium uppercase tracking-widest">{title}</p>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block mb-2 text-xs font-bold text-text-muted uppercase tracking-wider">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              placeholder="Your unique handle"
              className="input-field py-3 bg-bg-deep/50"
              disabled={loading}
            />
          </div>

          <div>
            <label className="block mb-2 text-xs font-bold text-text-muted uppercase tracking-wider">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="••••••••"
              className="input-field py-3 bg-bg-deep/50"
              disabled={loading}
            />
          </div>

          {error && (
            <div className="text-red-400 text-xs font-medium bg-red-500/5 border border-red-500/20 rounded-lg p-4 animate-shake">
              <span className="flex items-center gap-2">
                <span className="text-sm">⚠️</span> {error}
              </span>
            </div>
          )}

          <div className="flex flex-col gap-3 pt-4">
            <button
              type="submit"
              className="btn-primary interactive-tactile w-full py-3.5 shadow-amber-500/20"
              disabled={loading}
            >
              {loading ? 'Validating credentials...' : submitText}
            </button>
            <button
              type="button"
              onClick={onBack}
              className="btn-secondary interactive-tactile w-full py-3.5"
              disabled={loading}
            >
              Back
            </button>
          </div>
        </form>

        <div className="text-center mt-10 text-sm text-text-muted">
          <p>
            {toggleText}{' '}
            <button
              onClick={onToggle}
              className="text-primary-amber font-bold hover:underline"
              disabled={loading}
            >
              Click here
            </button>
          </p>
        </div>
      </div>
    </div>
  );
};

export default AuthForm;
