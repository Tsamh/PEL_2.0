export const filtresVides = {
  recherche: '', ec: '', type_question: '', difficulte: '', chapitre: '', competence: '', mes_questions: false, archivee: false,
};

export const LIBELLES_TYPE = { qcm: 'QCM', vf: 'Vrai / Faux', courte: 'Réponse courte' };
export const LIBELLES_DIFFICULTE = { facile: 'Facile', moyen: 'Moyen', difficile: 'Difficile' };

// Paramètres de requête de la liste de la banque (les tags sont répétés : tag=1&tag=2).
export function requeteBanque(f) {
  const p = new URLSearchParams();
  if (f.recherche.trim()) p.set('recherche', f.recherche.trim());
  ['ec', 'type_question', 'difficulte'].forEach((cle) => { if (f[cle]) p.set(cle, f[cle]); });
  [f.chapitre, f.competence].filter(Boolean).forEach((tag) => p.append('tag', tag));
  if (f.mes_questions) p.set('mes_questions', '1');
  if (f.archivee) p.set('archivee', '1');
  return p.toString();
}
