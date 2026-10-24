export const nouveauChoix = (texte = '', est_correct = false) => ({ texte, est_correct, points: 0 });

export const nouvelleQuestion = () => ({
  texte: '', type_question: 'qcm', points: 1, mode_notation: 'tout_ou_rien', penalite: 0, explication: '',
  choix: [nouveauChoix('', true), nouveauChoix()],
});

export const sommePositive = (choix) => choix.reduce((s, c) => s + (Number(c.points) > 0 ? Number(c.points) : 0), 0);

export const penaliteApplicable = (q) => q.type_question === 'vf' || (q.type_question === 'qcm' && q.mode_notation === 'tout_ou_rien');

// Question reçue de l'API (question de quiz ou version de la banque) vers l'état de l'éditeur.
export function depuisApi(q) {
  return {
    texte: q.texte, type_question: q.type_question, points: Number(q.points), mode_notation: q.mode_notation,
    penalite: Number(q.penalite || 0), explication: q.explication || '',
    choix: (q.choix || []).map((c) => ({ texte: c.texte, est_correct: c.est_correct, points: Number(c.points) })),
  };
}

// État de l'éditeur vers le contenu envoyé à l'API.
export function versContenu(q) {
  const parChoix = q.type_question === 'qcm' && q.mode_notation === 'par_choix';
  return {
    texte: q.texte, type_question: q.type_question, points: q.points, mode_notation: q.mode_notation,
    penalite: penaliteApplicable(q) ? q.penalite || 0 : 0, explication: q.explication || '',
    choix: q.choix.map((c) => ({
      texte: c.texte, est_correct: parChoix ? Number(c.points) > 0 : c.est_correct, points: parChoix ? c.points || 0 : 0,
    })),
  };
}
