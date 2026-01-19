import { useAuth } from '../../context/AuthContext';
import TabNavigation from './TabNavigation';

const Header = () => {
  const { user, logout } = useAuth();

  return (
    <div className="text-center p-8 border-b border-primary-gold/20 relative">
      <button
        onClick={logout}
        className="btn-danger absolute top-4 right-4 text-sm"
      >
        Logout
      </button>

      <h1 className="text-4xl gradient-text mb-2">IRIS</h1>
      <p className="text-text-secondary mb-4">Welcome back, {user}</p>

      <TabNavigation />
    </div>
  );
};

export default Header;
