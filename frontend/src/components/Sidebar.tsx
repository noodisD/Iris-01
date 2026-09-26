import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { Orb } from '@/components/primitives';
import { useUser } from '@/hooks/useData';
import { useIrisStore, applyOrbVibe } from '@/hooks/useIrisState';
import { NAV_GROUPS, vibeFor } from './nav';
import styles from './Sidebar.module.css';

const COLLAPSED_KEY = 'iris.sidebar.collapsed';

/** Whether the owner left the menu folded. A convenience, so storage may fail. */
function readCollapsed(): boolean {
  try { return window.localStorage.getItem(COLLAPSED_KEY) === '1'; } catch { return false; }
}

function writeCollapsed(value: boolean) {
  try { window.localStorage.setItem(COLLAPSED_KEY, value ? '1' : '0'); } catch { /* not remembered */ }
}

/** Desktop navigation: four groups, folding to an icon rail that keeps every link. */
export function Sidebar() {
  const { data: user } = useUser();
  const { vibe } = useIrisStore();
  const loc = useLocation();
  const [collapsed, setCollapsed] = React.useState(readCollapsed);
  const toggle = () => setCollapsed(c => { writeCollapsed(!c); return !c; });

  // The lens takes the mood of the page, unless the owner chose one.
  React.useEffect(() => { applyOrbVibe(vibe, vibeFor(loc.pathname)); }, [loc.pathname, vibe]);

  return (
    <aside className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''}`} aria-label="Main">
      <div className={styles.brand}>
        <Orb />
        {!collapsed && (
          <div className={styles.name}>
            <span className={styles.wordmark}>Iris</span>
            {user && <span className={styles.day}>Day {user.dayInJourney}</span>}
          </div>
        )}
        <button type="button" onClick={toggle} className={styles.fold}
          aria-label={collapsed ? 'Open the menu' : 'Fold the menu'} aria-expanded={!collapsed}
          title={collapsed ? 'Open the menu' : 'Fold the menu'}>
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      <nav className={styles.nav} aria-label="Sections">
        {NAV_GROUPS.map(group => (
          <div key={group.label} className={styles.group}>
            {!collapsed && <h2 className={styles.groupLabel}>{group.label}</h2>}
            <ul className={styles.list}>
              {group.items.map(item => (
                <li key={item.to}>
                  <NavLink to={item.to} className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ''}`}
                    aria-label={collapsed ? item.label : undefined} title={collapsed ? item.label : undefined}>
                    <item.icon size={17} aria-hidden />
                    {!collapsed && <span>{item.label}</span>}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className={styles.foot}>
        <NavLink to="/onboarding" className={styles.footLink}>{collapsed ? '↺' : 'Meet Iris again'}</NavLink>
        {!collapsed && user?.name && <span className={styles.user}>{user.name}</span>}
      </div>
    </aside>
  );
}
