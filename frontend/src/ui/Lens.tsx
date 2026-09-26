import styles from './Lens.module.css';

/**
 * The iris lens: IRIS's one bold element. Fibres around a pupil, coloured by
 * the page's mood (applyOrbVibe sets --orb-hue-*). The pupil breathes slowly;
 * with reduced motion it rests.
 */
export function Lens({ size = 24, label }: { size?: number; label?: string }) {
  const fibres = Array.from({ length: 24 }, (_, i) => (i * 360) / 24);
  return (
    <svg className={styles.lens} width={size} height={size} viewBox="0 0 40 40"
      role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <defs>
        <radialGradient id="lens-iris" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--orb-hue-a)" />
          <stop offset="55%" stopColor="var(--orb-hue-b)" />
          <stop offset="100%" stopColor="var(--orb-hue-c)" />
        </radialGradient>
      </defs>
      <circle cx="20" cy="20" r="19" fill="url(#lens-iris)" />
      <g className={styles.fibres}>
        {fibres.map(angle => (
          <line key={angle} x1="20" y1="9" x2="20" y2="3" transform={`rotate(${angle} 20 20)`} />
        ))}
      </g>
      <circle className={styles.pupil} cx="20" cy="20" r="7" />
      <circle cx="17" cy="16.5" r="1.6" className={styles.glint} />
    </svg>
  );
}
