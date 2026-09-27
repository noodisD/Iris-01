import { useId } from 'react';
import styles from './Lens.module.css';

/**
 * The iris lens: IRIS's one bold element. Fibres around a pupil, coloured by
 * the page's mood (applyOrbVibe sets --orb-hue-*). The pupil breathes slowly;
 * with reduced motion it rests. `live` hands the pupil to a voice instead: it
 * narrows with the `--level` (0 to 1) set on an ancestor, as in Talk mode.
 */
export function Lens({ size = 24, label, live = false }: { size?: number; label?: string; live?: boolean }) {
  const fibres = Array.from({ length: 24 }, (_, i) => (i * 360) / 24);
  // One gradient per lens: with a shared id, a lens in a hidden sidebar took
  // the gradient with it and every other lens drew unlit.
  const gradient = `lens-iris-${useId().replace(/:/g, '')}`;
  return (
    <svg className={live ? `${styles.lens} ${styles.live}` : styles.lens} width={size} height={size} viewBox="0 0 40 40"
      role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <defs>
        <radialGradient id={gradient} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--orb-hue-a)" />
          <stop offset="55%" stopColor="var(--orb-hue-b)" />
          <stop offset="100%" stopColor="var(--orb-hue-c)" />
        </radialGradient>
      </defs>
      <circle cx="20" cy="20" r="19" fill={`url(#${gradient})`} />
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
