export const formatDate = (iso) => (iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }) : null);

export const formatNote = (n) => (n ? `${Number(n.score)} / ${Number(n.score_max)}${n.provisoire ? ' (provisoire)' : ''}` : '-');

export function fenetre(quiz) {
  const debut = formatDate(quiz.date_debut);
  const fin = formatDate(quiz.date_fin);
  if (debut && fin) return `${debut} au ${fin}`;
  if (debut) return `À partir du ${debut}`;
  if (fin) return `Jusqu'au ${fin}`;
  return 'Toujours ouvert';
}
