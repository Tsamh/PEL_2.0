// Libellés des statuts d'exécution, de test et de correction (communs à l'étudiant et à l'enseignant).

export const STATUTS_TEST = {
  OK: 'Accepté',
  CE: 'Erreur de compilation',
  RE: "Erreur d'exécution",
  WA: 'Mauvaise réponse',
  TLE: 'Temps dépassé',
  MLE: 'Mémoire dépassée',
  SE: 'Erreur du service',
};

export const STATUTS_EXECUTION = {
  en_attente: 'En attente',
  en_cours: 'En cours',
  terminee: 'Terminée',
  erreur: 'Erreur du service',
};

export const STATUTS_SOUMISSION = {
  soumis: 'Soumis',
  en_correction: 'Correction en cours',
  corrigee_auto: 'Corrigé automatiquement',
  corrige: 'Validé',
};

export const POLITIQUES_RESULTATS = {
  apres_validation: "Après validation par l'enseignant",
  immediate: 'Immédiate (dès la correction automatique)',
};

export const executionActive = (statut) => statut === 'en_attente' || statut === 'en_cours';

export const libelleTest = (statut) => STATUTS_TEST[statut] || statut;

// Résumé « n / total acceptés » d'une liste de résultats.
export const resumeResultats = (resultats) => {
  const total = resultats.length;
  const acceptes = resultats.filter((r) => r.statut === 'OK').length;
  return `${acceptes} / ${total} test${total > 1 ? 's' : ''} accepté${acceptes > 1 ? 's' : ''}`;
};
