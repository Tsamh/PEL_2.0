import { useState, useEffect, useCallback } from 'react';

export default function CountdownTimer({ dateFin, onTimeUp }) {
  const [remaining, setRemaining] = useState(0);

  const calcRemaining = useCallback(() => {
    const end = new Date(dateFin).getTime();
    const now = Date.now();
    return Math.max(0, Math.floor((end - now) / 1000));
  }, [dateFin]);

  useEffect(() => {
    setRemaining(calcRemaining());
    const interval = setInterval(() => {
      const r = calcRemaining();
      setRemaining(r);
      if (r <= 0) {
        clearInterval(interval);
        onTimeUp?.();
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [calcRemaining, onTimeUp]);

  if (remaining <= 0) {
    return (
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: '8px',
        padding: '8px 16px', borderRadius: '8px',
        background: 'var(--danger, #ef4444)', color: '#fff', fontWeight: 700, fontSize: '1.1rem'
      }}>
        ⏰ Temps écoulé
      </div>
    );
  }

  const hours = Math.floor(remaining / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  const seconds = remaining % 60;
  const pad = (n) => String(n).padStart(2, '0');

  let color = 'var(--success, #22c55e)';
  let bg = 'rgba(34, 197, 94, 0.1)';
  if (remaining < 300) {
    color = 'var(--danger, #ef4444)';
    bg = 'rgba(239, 68, 68, 0.1)';
  } else if (remaining < 1800) {
    color = 'var(--warning, #f59e0b)';
    bg = 'rgba(245, 158, 11, 0.1)';
  }

  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: '8px',
      padding: '8px 16px', borderRadius: '8px',
      background: bg, color, fontWeight: 700, fontSize: '1.1rem',
      fontVariantNumeric: 'tabular-nums'
    }}>
      ⏱ {pad(hours)}:{pad(minutes)}:{pad(seconds)}
    </div>
  );
}
