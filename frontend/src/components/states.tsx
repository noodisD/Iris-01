import React from 'react';

/** Generic loading skeleton — a calm pulsing block. */
export function Skeleton({ h = 16, w = '100%', radius = 6 }: { h?: number; w?: number | string; radius?: number }) {
  return (
    <div style={{
      height: h, width: w, borderRadius: radius,
      background: 'linear-gradient(90deg, var(--bg-2) 25%, var(--bg-3) 50%, var(--bg-2) 75%)',
      backgroundSize: '200% 100%', animation: 'shimmer 1.4s ease-in-out infinite',
    }} />
  );
}

/** Full-screen-ish loading state with the orb. */
export function LoadingState({ label = 'Iris is gathering your day…' }: { label?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      gap: 18, padding: '120px 0', color: 'var(--ink-3)' }}>
      <div className="iris-orb" />
      <span className="serif" style={{ fontSize: 20, fontStyle: 'italic', color: 'var(--ink-2)' }}>{label}</span>
    </div>
  );
}

/** Error state — honest, calm, with a retry. */
export function ErrorState({ message, onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      gap: 14, padding: '100px 0', textAlign: 'center' }}>
      <div className="iris-orb" style={{ filter: 'grayscale(0.6)', opacity: 0.6 }} />
      <div className="serif" style={{ fontSize: 24, color: 'var(--ink)' }}>Something didn't load.</div>
      <div style={{ fontSize: 13, color: 'var(--ink-3)', maxWidth: 380 }}>
        {message ?? "Iris couldn't reach your data just now. Your information is safe — this is only the view."}
      </div>
      {onRetry && <button className="btn" onClick={onRetry} style={{ marginTop: 8 }}>Try again</button>}
    </div>
  );
}

/** Empty / first-run state. */
export function EmptyState({ title, body, action }: { title: string; body?: string; action?: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      gap: 12, padding: '90px 0', textAlign: 'center' }}>
      <div className="iris-orb sm" />
      <div className="serif" style={{ fontSize: 28, color: 'var(--ink)', maxWidth: 420, lineHeight: 1.1 }}>{title}</div>
      {body && <div style={{ fontSize: 13, color: 'var(--ink-3)', maxWidth: 380, lineHeight: 1.55 }}>{body}</div>}
      {action}
    </div>
  );
}
