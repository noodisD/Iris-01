import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Sheet } from '@/ui';
import { MenuIcon, NAV_GROUPS, PHONE_BAR } from './nav';
import styles from './PhoneNav.module.css';

const ITEMS = NAV_GROUPS.flatMap(group => group.items);

/** On a phone: Today, Journal and Chat at the thumb, and a menu with everything. */
export function PhoneNav() {
  const [open, setOpen] = React.useState(false);
  const loc = useLocation();
  React.useEffect(() => { setOpen(false); }, [loc.pathname]);
  const inMenu = !PHONE_BAR.some(path => loc.pathname.startsWith(path));
  return (
    <>
      <nav className={styles.bar} aria-label="Main">
        {PHONE_BAR.map(path => {
          const item = ITEMS.find(i => i.to === path)!;
          return (
            <NavLink key={path} to={path} className={({ isActive }) => `${styles.tab} ${isActive ? styles.active : ''}`}>
              <item.icon size={20} aria-hidden />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
        <button type="button" className={`${styles.tab} ${inMenu ? styles.active : ''}`} onClick={() => setOpen(true)}
          aria-haspopup="dialog">
          <MenuIcon size={20} aria-hidden />
          <span>Menu</span>
        </button>
      </nav>
      <Sheet open={open} onOpenChange={setOpen} title="Iris">
        <nav aria-label="All sections" className={styles.menu}>
          {NAV_GROUPS.map(group => (
            <div key={group.label} className={styles.group}>
              <h2 className={styles.groupLabel}>{group.label}</h2>
              <div className={styles.grid}>
                {group.items.map(item => (
                  <NavLink key={item.to} to={item.to} className={({ isActive }) => `${styles.item} ${isActive ? styles.active : ''}`}>
                    <item.icon size={18} aria-hidden />
                    <span>{item.label}</span>
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
      </Sheet>
    </>
  );
}
