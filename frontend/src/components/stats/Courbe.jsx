// Petite courbe de progression (valeurs de 0 à max), une info-bulle par point.
export default function Courbe({ valeurs, max, largeur = 90, hauteur = 28, libelles = [] }) {
  if (!valeurs.length) return <span style={{ color: 'var(--gray-500)' }}>-</span>;
  const nombres = valeurs.map(Number);
  const haut = Math.max(Number(max) || 0, ...nombres, 1);
  const pas = nombres.length > 1 ? (largeur - 8) / (nombres.length - 1) : 0;
  const points = nombres.map((v, i) => [4 + i * pas, hauteur - 4 - (Math.max(0, v) / haut) * (hauteur - 8)]);
  return (
    <svg width={largeur} height={hauteur} viewBox={`0 0 ${largeur} ${hauteur}`} role="img" aria-label={`Progression : ${nombres.join(', ')}`}>
      {points.length > 1 && (
        <polyline points={points.map((p) => p.join(',')).join(' ')} fill="none" stroke="var(--primary)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      )}
      {points.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="3" fill="var(--primary)" stroke="var(--white, #fff)" strokeWidth="1.5">
          <title>{libelles[i] || String(nombres[i])}</title>
        </circle>
      ))}
    </svg>
  );
}
