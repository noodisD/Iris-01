import { useAuth } from '../../context/AuthContext';
import TabNavigation from './TabNavigation';

const Header = () => {
  const { user, logout } = useAuth();

  return (
    <header className="bg-bg-deep/80 backdrop-blur-xl border-b border-border-subtle sticky top-0 z-10">
      <div className="max-w-7xl mx-auto px-6 lg:px-10">
        <div className="flex justify-between items-center h-24">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-primary-amber to-primary-gold rounded-xl flex items-center justify-center text-black font-black text-2xl shadow-xl shadow-primary-amber/10">
              I
            </div>
            <div>
              <h1 className="text-2xl font-black tracking-tighter text-gradient-gold leading-none">IRIS</h1>
            </div>
          </div>

          <div className="flex items-center gap-8">
            <span className="text-xs font-semibold text-text-muted hidden md:block uppercase tracking-widest opacity-60">
              User: <span className="text-text-primary opacity-100">{user}</span>
            </span>
            <button
              onClick={logout}
              className="btn-secondary py-2 px-5 text-[10px] font-black uppercase tracking-[0.2em] transition-all duration-300"
            >
              Sign Out
            </button>
          </div>
        </div>
        
        <div className="pb-1">
          <TabNavigation />
        </div>
      </div>
    </header>
  );
};

export default Header;
