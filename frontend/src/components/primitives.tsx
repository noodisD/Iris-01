/**
 * Shared visual primitives — typed React versions of the prototype's charts.
 * Pure presentational: they take data, draw SVG. No data fetching here.
 */
import React from 'react';

export function Sparkline({
  data, w = 200, h = 40, stroke = 'var(--sage)', fill = false, dots = false, baseline = false,
}: {
  data: number[]; w?: number; h?: number; stroke?: string; fill?: boolean; dots?: boolean; baseline?: boolean;
}) {
  if (!data?.length) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const step = w / (data.length - 1 || 1);
  const pts = data.map((d, i) => [i * step, h - ((d - min) / span) * h * 0.85 - h * 0.075] as const);
  const path = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  const area = path + ` L${w} ${h} L0 ${h} Z`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      {baseline && <line x1="0" y1={h - 1} x2={w} y2={h - 1} stroke="var(--line)" strokeWidth="1" />}
      {fill && <path d={area} fill={stroke} opacity="0.12" />}
      <path d={path} stroke={stroke} strokeWidth="1.4" fill="none" strokeLinejoin="round" strokeLinecap="round" />
      {dots && pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="1.6" fill={stroke} />)}
    </svg>
  );
}

export function BarSeries({
  data, w = 240, h = 60, color = 'var(--ink-2)', gap = 2, rounded = 1,
}: {
  data: number[]; w?: number; h?: number; color?: string | ((d: number, i: number) => string); gap?: number; rounded?: number;
}) {
  if (!data?.length) return null;
  const max = Math.max(...data);
  const bw = (w - gap * (data.length - 1)) / data.length;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      {data.map((d, i) => {
        const bh = (d / max) * h * 0.92;
        return <rect key={i} x={i * (bw + gap)} y={h - bh} width={bw} height={bh} rx={rounded}
          fill={typeof color === 'function' ? color(d, i) : color} />;
      })}
    </svg>
  );
}

export function Ring({
  value, size = 64, stroke = 5, color = 'var(--sage)', track = 'var(--line)', label,
}: {
  value: number; size?: number; stroke?: number; color?: string; track?: string; label?: React.ReactNode;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div style={{ position: 'relative', width: size, height: size, display: 'inline-block' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={r} stroke={track} strokeWidth={stroke} fill="none" />
        <circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={stroke} fill="none"
          strokeDasharray={c} strokeDashoffset={c * (1 - value)} strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      </svg>
      {label != null && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-2)' }}>{label}</div>
      )}
    </div>
  );
}

export function Orb({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  return <div className={`iris-orb ${size === 'lg' ? 'lg' : size === 'sm' ? 'sm' : ''}`} />;
}

export function Tag({ children, accent }: { children: React.ReactNode; accent?: string }) {
  return (
    <span className="tag" style={accent ? { color: accent, borderColor: accent } : undefined}>{children}</span>
  );
}

/** Color token resolver: maps 'sage'|'rose'|… to a CSS var, passes through hex. */
export function color(token: string): string {
  const map: Record<string, string> = {
    sage: 'var(--sage)', amber: 'var(--amber)', indigo: 'var(--indigo)', rose: 'var(--rose)',
    ink: 'var(--ink)', 'ink-2': 'var(--ink-2)', 'ink-3': 'var(--ink-3)',
  };
  return map[token] ?? token;
}
