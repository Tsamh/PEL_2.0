const LARGEUR = 320;
const HAUTEUR = 150;
const MARGE_BAS = 20;
const MARGE_HAUT = 16;
const ECART = 2;

// Histogramme des notes par tranche de 10 % ; info-bulle par barre.
export default function Histogramme({ tranches }) {
  const max = Math.max(1, ...tranches.map((t) => t.nb));
  const largeurBarre = (LARGEUR - ECART * (tranches.length - 1)) / tranches.length;
  const utile = HAUTEUR - MARGE_BAS - MARGE_HAUT;
  const base = HAUTEUR - MARGE_BAS;
  return (
    <svg viewBox={`0 0 ${LARGEUR} ${HAUTEUR}`} role="img" aria-label="Distribution des notes par tranche de 10 %" style={{ width: '100%', maxWidth: '560px', height: 'auto' }}>
      <line x1="0" x2={LARGEUR} y1={base} y2={base} stroke="var(--gray-200)" />
      {tranches.map((t, i) => {
        const x = i * (largeurBarre + ECART);
        const h = (t.nb / max) * utile;
        return (
          <g key={t.de}>
            <title>{`${t.de} à ${t.a} % : ${t.nb} étudiant${t.nb > 1 ? 's' : ''}`}</title>
            <rect x={x} y={MARGE_HAUT} width={largeurBarre} height={utile} fill="transparent" />
            {t.nb > 0 && <rect x={x} y={base - h} width={largeurBarre} height={h} rx="3" fill="var(--primary)" />}
            {t.nb > 0 && <text x={x + largeurBarre / 2} y={base - h - 4} textAnchor="middle" fontSize="10" fill="var(--gray-700, #334155)">{t.nb}</text>}
          </g>
        );
      })}
      {[0, 50, 100].map((v) => (
        <text key={v} x={(v / 100) * LARGEUR} y={HAUTEUR - 6} textAnchor={v === 0 ? 'start' : v === 100 ? 'end' : 'middle'} fontSize="10" fill="var(--gray-500, #64748b)">{v} %</text>
      ))}
    </svg>
  );
}
