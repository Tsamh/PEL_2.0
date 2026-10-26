// Exercices d'un devoir : état du formulaire et format d'écriture attendu par l'API.

export const LANGAGES = { python: 'Python', java: 'Java', c: 'C', cpp: 'C++', javascript: 'JavaScript', autre: 'Autre' };
export const DIFFICULTES = { facile: 'Facile', moyen: 'Moyen', difficile: 'Difficile' };

const EXTENSIONS = { python: 'py', javascript: 'js', c: 'c', cpp: 'cpp', java: 'java', autre: 'txt' };
const EXTENSIONS_CONNUES = new Set(Object.values(EXTENSIONS));

// Nom du fichier unique d'un exercice selon le langage du devoir.
export const nomFichier = (langage) => `main.${EXTENSIONS[langage] || 'txt'}`;

export const nouveauTest = () => ({ entree: '', sortie_attendue: '', public: false, poids: 1 });
export const nouvelExemple = () => ({ entree: '', sortie: '', explication: '' });

let compteurCle = 0;
// Clé locale stable (jamais envoyée à l'API) pour que l'éditeur suive l'exercice lors des déplacements.
const nouvelleCle = () => { compteurCle += 1; return `ex-${compteurCle}`; };

export const nouvelExercice = (langage) => ({
  cle: nouvelleCle(),
  titre: '', enonce: '', contraintes: '', exemples: [],
  fichiers_initiaux: [{ nom: nomFichier(langage), contenu: '' }],
  solution: [{ nom: nomFichier(langage), contenu: '' }],
  points: 1, difficulte: 'moyen', competences: [], tests: [nouveauTest()],
});

const copieFichiers = (fichiers) => (fichiers || []).map((f) => ({ nom: f.nom, contenu: f.contenu }));

// Exercice lu dans l'API vers l'état du formulaire (le texte est gardé tel quel).
export const depuisApi = (e) => ({
  cle: nouvelleCle(),
  titre: e.titre, enonce: e.enonce || '', contraintes: e.contraintes || '',
  exemples: (e.exemples || []).map((x) => ({ entree: x.entree || '', sortie: x.sortie || '', explication: x.explication || '' })),
  fichiers_initiaux: copieFichiers(e.fichiers_initiaux),
  solution: copieFichiers(e.solution),
  points: e.points, difficulte: e.difficulte || 'moyen', competences: e.competences || [],
  competences_detail: e.competences_detail || [],
  tests: (e.tests || []).map((t) => ({ entree: t.entree, sortie_attendue: t.sortie_attendue, public: t.public, poids: t.poids })),
});

// Contenu du fichier principal (le premier de la liste) et mise à jour de ce seul fichier.
export const contenuPrincipal = (fichiers) => (fichiers.length > 0 ? fichiers[0].contenu : '');
export const avecContenuPrincipal = (fichiers, contenu, langage) => (fichiers.length > 0
  ? fichiers.map((f, i) => (i === 0 ? { ...f, contenu } : f))
  : [{ nom: nomFichier(langage), contenu }]);

// Changement de langage : les fichiers main.<ext> d'un langage connu prennent l'extension du nouveau langage.
export const renommerFichiers = (fichiers, langage) => fichiers.map((f) => {
  const [base, ext, ...reste] = f.nom.split('.');
  return base === 'main' && reste.length === 0 && EXTENSIONS_CONNUES.has(ext) ? { ...f, nom: nomFichier(langage) } : f;
});

// Format d'écriture de l'API : liste complète des exercices avec leurs tests ; l'ordre suit la liste.
export const versPayload = (exercices) => exercices.map((e, i) => ({
  ordre: i + 1, titre: e.titre, enonce: e.enonce, contraintes: e.contraintes,
  exemples: e.exemples.map((x) => ({ entree: x.entree, sortie: x.sortie, explication: x.explication })),
  fichiers_initiaux: copieFichiers(e.fichiers_initiaux),
  solution: copieFichiers(e.solution),
  points: e.points, difficulte: e.difficulte, competences: e.competences,
  tests: e.tests.map((t, j) => ({
    ordre: j + 1, entree: t.entree, sortie_attendue: t.sortie_attendue, public: Boolean(t.public), poids: Number(t.poids) || 1,
  })),
}));
