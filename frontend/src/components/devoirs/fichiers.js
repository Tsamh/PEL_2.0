// Liste de fichiers d'un exercice [{nom, contenu}] : ajout, renommage, suppression et contrôle des noms.
// Les règles de nom reprennent `nom_refuse` et `valider_fichiers` du serveur (backend/programming).

export const FICHIERS_MAX = 20;
export const NOM_MAX = 100;

const INTERDITS = /[/\\:*?"<>|\x00-\x1f\x7f]/u; // eslint-disable-line no-control-regex
const NON_ENCODABLE = /\p{Cs}/u;
const RESERVES = new Set(['CON', 'PRN', 'AUX', 'NUL',
  ...Array.from({ length: 9 }, (_, i) => `COM${i + 1}`), ...Array.from({ length: 9 }, (_, i) => `LPT${i + 1}`)]);

// Le serveur retire les espaces autour du nom : l'éditeur fait de même pour afficher ce qui sera enregistré.
export const nettoyerNom = (nom) => (typeof nom === 'string' ? nom.trim() : '');

const MESSAGE_NOM = `Un nom de fichier compte de 1 à ${NOM_MAX} caractères, sans chemin, caractère spécial ni point final, et n'est pas un nom réservé (CON, NUL, COM1...).`;

function nomRefuse(nom) {
  if (!nom || [...nom].length > NOM_MAX) return true;
  if (/^\.+$/.test(nom) || nom.endsWith('.') || nom.endsWith(' ')) return true;
  if (INTERDITS.test(nom) || NON_ENCODABLE.test(nom)) return true;
  return RESERVES.has(nom.split('.')[0].replace(/ +$/, '').toUpperCase());
}

const memeNom = (a, b) => a.toLowerCase() === b.toLowerCase();

// Message d'erreur si `nom` ne peut pas être ajouté à `fichiers` (ou donné à `nomActuel`), sinon null.
export function erreurNom(nom, fichiers, nomActuel = null) {
  const propre = nettoyerNom(nom);
  if (nomRefuse(propre)) return MESSAGE_NOM;
  if (fichiers.some((f) => f.nom !== nomActuel && memeNom(f.nom, propre))) return `Deux fichiers ne peuvent pas porter le nom ${propre} (la casse ne compte pas).`;
  if (nomActuel === null && fichiers.length >= FICHIERS_MAX) return `Un exercice compte ${FICHIERS_MAX} fichiers au plus.`;
  return null;
}

export const ajouter = (fichiers, nom) => [...fichiers, { nom: nettoyerNom(nom), contenu: '' }];

export const renommer = (fichiers, ancien, nouveau) => fichiers.map((f) => (f.nom === ancien ? { ...f, nom: nettoyerNom(nouveau) } : f));

export const supprimer = (fichiers, nom) => fichiers.filter((f) => f.nom !== nom);
