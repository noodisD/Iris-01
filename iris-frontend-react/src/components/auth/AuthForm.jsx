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

  const title = mode === 'signup' ? 'Sign Up' : 'Log In';
  const submitText = mode === 'signup' ? 'Sign Up' : 'Log In';
  const toggleText =
    mode === 'signup' ? 'Already have an account?' : 'Need an account?';

  return (
    <div className="flex flex-col justify-center items-center min-h-screen px-8">
      <div className="glass-container p-8 w-full max-w-md">
        <h2 className="text-3xl gradient-text mb-6 text-center">{title}</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block mb-2 text-sm text-text-secondary">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              className="input-field"
              disabled={loading}
            />
          </div>

          <div>
            <label className="block mb-2 text-sm text-text-secondary">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="input-field"
              disabled={loading}
            />
          </div>

          {error && (
            <div className="text-red-500 text-sm bg-red-500/10 border border-red-500/30 rounded p-3">
              {error}
            </div>
          )}

          <div className="flex gap-4 pt-4">
            <button
              type="submit"
              className="btn-primary flex-1"
              disabled={loading}
            >
              {loading ? 'Processing...' : submitText}
            </button>
            <button
              type="button"
              onClick={onBack}
              className="btn-secondary flex-1"
              disabled={loading}
            >
              Back
            </button>
          </div>
        </form>

        <div className="text-center mt-6 text-sm text-text-secondary">
          <p>
            {toggleText}{' '}
            <button
              onClick={onToggle}
              className="text-primary-gold underline font-bold hover:text-primary-goldLight"
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
