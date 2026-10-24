const compte = (n, singulier, pluriel) => `${n} ${n > 1 ? pluriel : singulier}`;

// Résumé lisible des cibles d'un quiz, par exemple « 2 classes, 1 groupe, 3 étudiants ».
export function resumeCibles(nbClasses, nbGroupes, nbEtudiants) {
  const parties = [];
  if (nbClasses) parties.push(compte(nbClasses, 'classe', 'classes'));
  if (nbGroupes) parties.push(compte(nbGroupes, 'groupe', 'groupes'));
  if (nbEtudiants) parties.push(compte(nbEtudiants, 'étudiant', 'étudiants'));
  return parties.length ? parties.join(', ') : 'aucune cible';
}
