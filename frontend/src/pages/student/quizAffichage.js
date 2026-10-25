export const formatDate = (iso) => (iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }) : null);

export const formatNote = (n) => (n ? `${Number(n.score)} / ${Number(n.score_max)}${n.provisoire ? ' (provisoire)' : ''}` : '-');

export function fenetre(quiz) {
  const effective = quiz.etat?.fenetre;
  const debut = formatDate(effective ? effective.ouverture : quiz.date_debut);
  const fin = formatDate(effective ? effective.fermeture : quiz.date_fin);
  if (debut && fin) return `${debut} au ${fin}`;
  if (debut) return `À partir du ${debut}`;
  if (fin) return `Jusqu'au ${fin}`;
  return 'Toujours ouvert';
}

export function prochaineOuverture(quiz) {
  const prochaine = quiz.etat?.fenetre?.prochaine_ouverture;
  return prochaine && !quiz.etat.ouvert ? `Prochaine ouverture le ${formatDate(prochaine)}` : null;
}
