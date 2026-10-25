export const nombre = (v) => (v == null ? '-' : Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 2 }));

export const pourcentage = (v) => (v == null ? '-' : `${Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`);

export function duree(secondes) {
  if (secondes == null) return '-';
  const minutes = Math.floor(secondes / 60);
  const reste = secondes % 60;
  return minutes ? `${minutes} min ${String(reste).padStart(2, '0')} s` : `${reste} s`;
}
