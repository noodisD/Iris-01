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
  { to: '/insights',  label: 'Insights', dot: true },
  { to: '/review',    label: 'Review' },
  { to: '/mobile',    label: 'On the go' },
  { to: '/settings',  label: 'Settings' },
];

// Per-route default orb vibe
const ROUTE_VIBE: Record<string, Exclude<OrbVibe, 'auto'>> = {
  '/chat': 'calm', '/today': 'calm', '/journal': 'high',
  '/habits': 'high', '/insights': 'low', '/review': 'cool', '/mobile': 'calm', '/settings': 'dim',
};

export function Sidebar() {
  const { data: user } = useUser();
  const { vibe } = useIrisStore();
  const loc = useLocation();

  // Drive the orb hue from current route + user vibe choice
  React.useEffect(() => {
    const key = '/' + (loc.pathname.split('/')[1] || 'chat');
    applyOrbVibe(vibe, ROUTE_VIBE[key] ?? 'calm');
  }, [loc.pathname, vibe]);

  const day = user?.dayInJourney ?? 47;

  return (
    <aside style={{
      width: 220, height: '100%', background: 'var(--bg-1)',
      borderRight: '1px solid var(--line-soft)', padding: '22px 0 18px',
      display: 'flex', flexDirection: 'column', flexShrink: 0,
    }}>
      <div className="row" style={{ alignItems: 'center', gap: 10, padding: '0 22px 22px' }}>
        <Orb />
        <div className="col" style={{ gap: 1, lineHeight: 1 }}>
          <span className="serif" style={{ fontSize: 22, color: 'var(--ink)' }}>Iris</span>
          <span style={{ fontSize: 10, color: 'var(--ink-3)', fontFamily: 'var(--mono)', letterSpacing: '0.14em', textTransform: 'uppercase' }}>v.0 · day {day}</span>
        </div>
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
                {item.dot && <span className="dot sage" />}
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
      <div style={{ padding: '10px 22px 0', borderTop: '1px solid var(--line-soft)', marginTop: 6 }}>
        <div className="row" style={{ alignItems: 'center', gap: 10, marginTop: 12 }}>
          <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'linear-gradient(135deg, #d4a374, #c47d4a)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--serif)', fontSize: 14, color: '#1a1a14' }}>
            {(user?.name ?? 'S')[0]}
          </div>
          <div className="col" style={{ gap: 1 }}>
            <span style={{ fontSize: 12, color: 'var(--ink)' }}>{user?.name ?? 'Sam Reeves'}</span>
            <span style={{ fontSize: 10, color: 'var(--ink-3)' }}>Pacific · 7:42 PM</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
