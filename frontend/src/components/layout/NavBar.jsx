import { NavLink } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import styles from './NavBar.module.css';

const NAV_ITEMS = [
  { to: '/', label: 'Basilica', icon: '\uD83C\uDFDB\uFE0F' },
  { to: '/conviction', label: 'Conviction', icon: '\uD83D\uDCDC' },
  { to: '/anvil', label: 'Anvil', icon: '\u2694\uFE0F' },
  { to: '/archive', label: 'Archive', icon: '\uD83D\uDCDA' },
];

export function NavBar({ onRunScan, scanRunning }) {
  const { isAdmin } = useAuth();

  return (
    <nav className={styles.nav}>
      <div className={styles.links}>
        {NAV_ITEMS.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ''}`}
          >
            <span className={styles.icon}>{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </div>

      {isAdmin && (
        <button
          className={styles.scanBtn}
          onClick={onRunScan}
          disabled={scanRunning}
        >
          {scanRunning ? '\u27F3 Scanning...' : '\u25B6 Run Scan'}
        </button>
      )}
    </nav>
  );
}
