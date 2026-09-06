// components.jsx — shared chart + visual primitives

const { useState, useEffect, useRef, useMemo } = React;

/* ---------- Sparkline ---------- */
function Sparkline({ data, w = 200, h = 40, stroke = 'var(--sage)', fill = false, dots = false, baseline = false }) {
  if (!data || !data.length) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const step = w / (data.length - 1 || 1);
  const pts = data.map((d, i) => [i * step, h - ((d - min) / span) * h * 0.85 - h * 0.075]);
  const path = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  const area = path + ` L${w} ${h} L0 ${h} Z`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      {baseline && (
        <line x1="0" y1={h - 1} x2={w} y2={h - 1} stroke="var(--line)" strokeWidth="1" />
      )}
      {fill && <path d={area} fill={stroke} opacity="0.12" />}
      <path d={path} stroke={stroke} strokeWidth="1.4" fill="none" strokeLinejoin="round" strokeLinecap="round" />
      {dots && pts.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r="1.6" fill={stroke} />
      ))}
    </svg>
  );
}

/* ---------- Bars (vertical, indexed by series) ---------- */
function BarSeries({ data, w = 240, h = 60, color = 'var(--ink-2)', gap = 2, rounded = 1 }) {
  if (!data || !data.length) return null;
  const max = Math.max(...data);
  const bw = (w - gap * (data.length - 1)) / data.length;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      {data.map((d, i) => {
        const bh = (d / max) * h * 0.92;
        const x = i * (bw + gap);
        const y = h - bh;
        return <rect key={i} x={x} y={y} width={bw} height={bh} rx={rounded} fill={typeof color === 'function' ? color(d, i) : color} />;
      })}
    </svg>
  );
}

/* ---------- Dot matrix heatmap (e.g. 7 x N) ---------- */
function DotMatrix({ values, cols, rows, dot = 8, gap = 4, colorFor }) {
  // values is rows*cols array
  const w = cols * dot + (cols - 1) * gap;
  const h = rows * dot + (rows - 1) * gap;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      {values.map((v, i) => {
        const r = Math.floor(i / cols), c = i % cols;
        const cx = c * (dot + gap) + dot / 2;
        const cy = r * (dot + gap) + dot / 2;
        return <circle key={i} cx={cx} cy={cy} r={dot / 2} fill={colorFor ? colorFor(v) : `rgba(169,200,163,${Math.max(0.06, v)})`} />;
      })}
    </svg>
  );
}

/* ---------- Ring (single circular progress) ---------- */
function Ring({ value, size = 64, stroke = 5, color = 'var(--sage)', track = 'var(--line)', label = null }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - value);
  return (
    <div style={{ position: 'relative', width: size, height: size, display: 'inline-block' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size/2} cy={size/2} r={r} stroke={track} strokeWidth={stroke} fill="none" />
        <circle cx={size/2} cy={size/2} r={r} stroke={color} strokeWidth={stroke} fill="none"
          strokeDasharray={c} strokeDashoffset={off} strokeLinecap="round"
          transform={`rotate(-90 ${size/2} ${size/2})`} />
      </svg>
      {label && (
        <div style={{
          position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-2)',
        }}>{label}</div>
      )}
    </div>
  );
}

/* ---------- Heat grid (hour x day) ---------- */
function HeatGrid({ matrix, cellW = 14, cellH = 11, gap = 2, max = 1, color = '169,200,163' }) {
  const rows = matrix.length;
  const cols = matrix[0].length;
  const w = cols * cellW + (cols - 1) * gap;
  const h = rows * cellH + (rows - 1) * gap;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      {matrix.map((row, ri) => row.map((v, ci) => {
        const x = ci * (cellW + gap);
        const y = ri * (cellH + gap);
        const a = Math.max(0.05, v / max);
        return <rect key={`${ri}-${ci}`} x={x} y={y} width={cellW} height={cellH} rx="1.5" fill={`rgba(${color},${a})`} />;
      }))}
    </svg>
  );
}

/* ---------- Stat block (big serif number + label) ---------- */
function Stat({ value, label, suffix, accent = 'var(--ink)', sub = null, size = 64 }) {
  return (
    <div className="col" style={{ gap: 4 }}>
      <div className="numerals" style={{ fontSize: size, color: accent }}>
        {value}{suffix && <span style={{ fontFamily: 'var(--sans)', fontSize: size * 0.18, color: 'var(--ink-3)', marginLeft: 4, letterSpacing: '0.06em' }}>{suffix}</span>}
      </div>
      {label && <div className="eyebrow">{label}</div>}
      {sub && <div style={{ fontSize: 12, color: 'var(--ink-3)' }}>{sub}</div>}
    </div>
  );
}

/* ---------- Iris orb with optional label ---------- */
function IrisOrb({ size = 'md', label = false }) {
  const cls = size === 'lg' ? 'iris-orb lg' : size === 'sm' ? 'iris-orb sm' : 'iris-orb';
  return (
    <div className="row" style={{ alignItems: 'center', gap: 10 }}>
      <div className={cls} />
      {label && <span className="serif ital" style={{ fontSize: 18, color: 'var(--ink)' }}>Iris</span>}
    </div>
  );
}

/* ---------- Numbered figure / annotation arrow (editorial) ---------- */
function Annotation({ children, side = 'right' }) {
  return (
    <div className="row" style={{ gap: 8, alignItems: 'flex-start', color: 'var(--ink-3)', fontSize: 11, fontFamily: 'var(--mono)', letterSpacing: '0.04em' }}>
      <span style={{ color: 'var(--amber)' }}>→</span>
      <span>{children}</span>
    </div>
  );
}

/* ---------- Section header ---------- */
function SectionHeader({ kicker, title, right = null, sub = null }) {
  return (
    <div className="row" style={{ alignItems: 'flex-end', justifyContent: 'space-between', marginBottom: 16, gap: 16 }}>
      <div className="col" style={{ gap: 6 }}>
        {kicker && <div className="kicker">{kicker}</div>}
        <h2 className="serif" style={{ margin: 0, fontSize: 38, lineHeight: 1, letterSpacing: '-0.02em' }}>{title}</h2>
        {sub && <div style={{ color: 'var(--ink-3)', fontSize: 13, maxWidth: 480 }}>{sub}</div>}
      </div>
      {right}
    </div>
  );
}

Object.assign(window, {
  Sparkline, BarSeries, DotMatrix, Ring, HeatGrid, Stat, IrisOrb, Annotation, SectionHeader,
});

/* ---------- Global state pub/sub for Iris ---------- */
window.__irisVibe = window.__irisVibe || 'calm';
window.__irisDay  = window.__irisDay  || 47;
window.setIrisVibe = function(v) { window.__irisVibe = v; window.dispatchEvent(new CustomEvent('iris-state')); };
window.setIrisDay  = function(d) { window.__irisDay  = d; window.dispatchEvent(new CustomEvent('iris-state')); };

function useIrisState() {
  const [_, force] = React.useState(0);
  React.useEffect(() => {
    const on = () => force(n => n + 1);
    window.addEventListener('iris-state', on);
    return () => window.removeEventListener('iris-state', on);
  }, []);
  return { vibe: window.__irisVibe || 'calm', day: window.__irisDay || 47 };
}
window.useIrisState = useIrisState;
