import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Orb } from '@/components/primitives';
import { useUser } from '@/hooks/useData';
import { useIrisStore, applyOrbVibe, type OrbVibe } from '@/hooks/useIrisState';

const NAV = [
  { to: '/chat',      label: 'Chat' },
  { to: '/today',     label: 'Today' },
  { to: '/journal',   label: 'Journal' },
  { to: '/habits',    label: 'Habits' },
  { to: '/decisions', label: 'Decisions' },
  { to: '/insights',  label: 'Insights' },
  { to: '/patterns',  label: 'Patterns' },
  { to: '/constructs', label: 'Noticed' },
  { to: '/ideas', label: 'Ideas' },
  { to: '/review',    label: 'Review' },
  { to: '/import',    label: 'Import' },
  { to: '/sensors',   label: 'Sensors' },
  { to: '/settings',  label: 'Settings' },
];

// Per-route default orb vibe
const ROUTE_VIBE: Record<string, Exclude<OrbVibe, 'auto'>> = {
  '/chat': 'calm', '/today': 'calm', '/journal': 'high',
  '/habits': 'high', '/insights': 'low', '/patterns': 'low', '/constructs': 'low', '/ideas': 'cool', '/review': 'cool', '/import': 'cool', '/sensors': 'dim', '/settings': 'dim',
};

const COLLAPSED_KEY = 'iris.sidebar.collapsed';

/** Whether the owner left the menu folded. A convenience, so storage may fail. */
function readCollapsed(): boolean {
  try { return window.localStorage.getItem(COLLAPSED_KEY) === '1'; } catch { return false; }
}

function writeCollapsed(value: boolean) {
  try { window.localStorage.setItem(COLLAPSED_KEY, value ? '1' : '0'); } catch { /* not remembered */ }
}

const toggleStyle: React.CSSProperties = {
  background: 'none', border: '1px solid var(--line-soft)', borderRadius: 6, cursor: 'pointer',
  color: 'var(--ink-3)', fontSize: 14, lineHeight: 1, width: 26, height: 26, padding: 0,
  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
};

export function Sidebar() {
  const { data: user } = useUser();
  const { vibe } = useIrisStore();
  const loc = useLocation();
  const [collapsed, setCollapsed] = React.useState(readCollapsed);
  const toggle = () => setCollapsed(c => { writeCollapsed(!c); return !c; });

  // Drive the orb hue from current route + user vibe choice
  React.useEffect(() => {
    const key = '/' + (loc.pathname.split('/')[1] || 'chat');
    applyOrbVibe(vibe, ROUTE_VIBE[key] ?? 'calm');
  }, [loc.pathname, vibe]);

  const aside: React.CSSProperties = {
    width: collapsed ? 56 : 220, height: '100%', background: 'var(--bg-1)',
    borderRight: '1px solid var(--line-soft)', padding: '22px 0 18px',
    display: 'flex', flexDirection: 'column', flexShrink: 0,
    transition: 'width 160ms ease', overflow: 'hidden',
  };

  if (collapsed) {
    return (
      <aside aria-label="Menu, folded" style={{ ...aside, alignItems: 'center', gap: 14 }}>
        <Orb />
        <button type="button" onClick={toggle} aria-label="Open the menu" aria-expanded={false}
          title="Open the menu" style={toggleStyle}>›</button>
      </aside>
    );
  }

  return (
    <aside style={aside}>
      <div className="row" style={{ alignItems: 'center', gap: 10, padding: '0 14px 22px 22px' }}>
        <Orb />
        <div className="col" style={{ gap: 1, lineHeight: 1, flex: 1, minWidth: 0 }}>
          <span className="serif" style={{ fontSize: 22, color: 'var(--ink)' }}>Iris</span>
          <span style={{ fontSize: 10, color: 'var(--ink-3)', fontFamily: 'var(--mono)', letterSpacing: '0.14em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>v.0{user ? ` · day ${user.dayInJourney}` : ''}</span>
        </div>
        <button type="button" onClick={toggle} aria-label="Fold the menu" aria-expanded={true}
          title="Fold the menu" style={toggleStyle}>‹</button>
      </div>

      <hr className="hairline" style={{ margin: '0 22px' }} />

      <nav className="col" style={{ padding: '14px 12px', gap: 1, flex: 1 }}>
        {NAV.map(item => (
          <NavLink key={item.to} to={item.to}
            style={({ isActive }) => ({
              background: isActive ? 'var(--bg-2)' : 'transparent',
              color: isActive ? 'var(--ink)' : 'var(--ink-2)',
              textDecoration: 'none', padding: '9px 12px', borderRadius: 6,
              fontFamily: 'var(--sans)', fontSize: 13, letterSpacing: '0.01em',
              display: 'flex', alignItems: 'center', gap: 10, position: 'relative',
            })}>
            {({ isActive }: { isActive: boolean }) => (
              <>
                {isActive && <span style={{ position: 'absolute', left: -1, top: 8, bottom: 8, width: 2, background: 'var(--sage)', borderRadius: 2 }} />}
                <span style={{ flex: 1 }}>{item.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div style={{ padding: '12px 22px 4px' }}>
        <NavLink to="/onboarding" style={{ background: 'none', border: 'none', color: 'var(--ink-3)', fontSize: 11, fontFamily: 'var(--mono)', letterSpacing: '0.08em', textTransform: 'uppercase', textDecoration: 'none' }}>
          ↺ Re-meet Iris
        </NavLink>
      </div>
      {user?.name && (
        <div style={{ padding: '10px 22px 0', borderTop: '1px solid var(--line-soft)', marginTop: 6 }}>
          <span style={{ fontSize: 12, color: 'var(--ink)' }}>{user.name}</span>
        </div>
      )}
    </aside>
  );
}
