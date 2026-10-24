import { pourcentage } from './format';

// Barre horizontale d'une part (0 à 100), la valeur écrite à côté.
export default function Barre({ valeur, libelle }) {
  const v = Math.max(0, Math.min(100, Number(valeur) || 0));
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '140px' }} title={libelle}>
      <div role="img" aria-label={libelle} style={{ flex: 1, height: '8px', borderRadius: '4px', background: 'var(--gray-200)', overflow: 'hidden' }}>
        <div style={{ width: `${v}%`, height: '100%', borderRadius: '4px', background: 'var(--primary)' }} />
      </div>
      <span style={{ fontSize: '0.85rem', minWidth: '52px', textAlign: 'right' }}>{pourcentage(v)}</span>
    </div>
  );
}
