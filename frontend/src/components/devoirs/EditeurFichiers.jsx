import { useRef, useState } from 'react';
import CodeEditor from '../CodeEditor';
import { FICHIERS_MAX, ajouter, erreurNom, nettoyerNom, renommer, supprimer } from './fichiers';

const LANGAGES_EXTENSION = {
  py: 'python', js: 'javascript', java: 'java', c: 'c', h: 'c', cpp: 'cpp', cc: 'cpp', cxx: 'cpp', hpp: 'cpp',
};

// Langage de coloration d'un fichier d'après son extension ; sinon celui de l'exercice pour son fichier principal.
function langageDe(nom, langage, principal) {
  if (nom === principal) return langage;
  const point = nom.lastIndexOf('.');
  return (point > 0 && LANGAGES_EXTENSION[nom.slice(point + 1).toLowerCase()]) || 'plaintext';
}

// Les modèles Monaco survivent au composant : les identifiants ne repartent jamais de 1 pendant la vie de la page.
let prochainId = 1;

// Identifiant stable par nom de fichier : le modèle Monaco (clé = path) survit aux renommages mais pas aux
// suppressions ni aux fichiers qui apparaissent de l'extérieur. Renvoie `ids` tel quel s'il est à jour.
function synchroniser(ids, fichiers) {
  const map = new Map();
  for (const f of fichiers) map.set(f.nom, ids.get(f.nom) ?? prochainId++);
  const identique = map.size === ids.size && [...map].every(([nom, id]) => ids.get(nom) === id);
  return identique ? ids : map;
}

const styleBarre = { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px', marginBottom: '6px' };
const styleOnglet = (actif) => ({
  padding: '4px 10px', border: '1px solid var(--gray-200)', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem',
  background: actif ? 'var(--primary, #2563eb)' : 'white', color: actif ? 'white' : 'inherit',
});
const styleNote = { fontSize: '0.85rem', color: 'var(--gray-500)' };

// Onglets d'une liste de fichiers [{nom, contenu}] avec un éditeur Monaco pour le fichier actif.
// `principal` : fichier ni renommé ni supprimé. `espace` : rend unique le modèle Monaco quand une page
// affiche plusieurs éditeurs (deux exercices peuvent avoir un fichier de même nom).
export default function EditeurFichiers({
  fichiers, langage, principal = null, readOnly = false, onChange, height = '200px', espace = 'editeur',
}) {
  const [actif, setActif] = useState({ nom: null, index: 0 });
  // saisie : { mode: 'ajout' | 'renommage', valeur, ancien } ou null.
  const [saisie, setSaisie] = useState(null);
  const [erreur, setErreur] = useState('');
  const [ids, setIds] = useState(() => new Map());
  const editeur = useRef(null);

  const idsAJour = synchroniser(ids, fichiers);
  if (idsAJour !== ids) setIds(idsAJour);
  // Le renommage en cours disparaît avec son fichier (changement venu de l'extérieur).
  if (saisie && saisie.mode === 'renommage' && !fichiers.some((f) => f.nom === saisie.ancien)) setSaisie(null);

  // Le fichier actif suit son nom ; s'il a disparu à cause d'un changement extérieur, on revient au premier.
  let position = fichiers.findIndex((f) => f.nom === actif.nom);
  if (position < 0) position = fichiers.length ? 0 : -1;
  const courant = position >= 0 ? fichiers[position] : null;
  const principalAbsent = principal && !fichiers.some((f) => f.nom === principal);

  const choisir = (nom, index) => { setActif({ nom, index }); setSaisie(null); setErreur(''); };
  const annuler = () => { setSaisie(null); setErreur(''); };

  const ouvrirAjout = () => {
    setErreur('');
    setSaisie({ mode: 'ajout', valeur: principalAbsent ? principal : '', ancien: null });
  };
  const ouvrirRenommage = () => {
    setErreur('');
    setSaisie({ mode: 'renommage', valeur: courant.nom, ancien: courant.nom });
  };

  const valider = () => {
    const nom = nettoyerNom(saisie.valeur);
    if (saisie.mode === 'renommage' && nom === saisie.ancien) { annuler(); return; }
    const message = erreurNom(nom, fichiers, saisie.ancien);
    if (message) { setErreur(message); return; }
    if (saisie.mode === 'ajout') {
      onChange(ajouter(fichiers, nom));
      choisir(nom, fichiers.length);
    } else {
      const map = new Map(idsAJour);
      map.set(nom, map.get(saisie.ancien));
      map.delete(saisie.ancien);
      setIds(map);
      onChange(renommer(fichiers, saisie.ancien, nom));
      choisir(nom, position);
    }
  };

  const retirer = () => {
    if (!window.confirm(`Supprimer le fichier ${courant.nom} ?`)) return;
    const reste = supprimer(fichiers, courant.nom);
    onChange(reste);
    const suivant = reste[Math.min(position, reste.length - 1)];
    choisir(suivant ? suivant.nom : null, Math.max(0, Math.min(position, reste.length - 1)));
  };

  const modifierContenu = (contenu) => {
    if (readOnly || !courant || contenu === courant.contenu) return;
    onChange(fichiers.map((f, i) => (i === position ? { ...f, contenu } : f)));
  };

  const rechercher = () => editeur.current?.getAction('actions.find')?.run();

  const protege = courant && courant.nom === principal;

  return (
    <div>
      <div style={styleBarre} role="tablist">
        {fichiers.map((f, i) => (
          <button key={f.nom} type="button" role="tab" aria-selected={i === position} style={styleOnglet(i === position)}
            title={f.nom === principal ? 'Fichier principal' : f.nom} onClick={() => choisir(f.nom, i)}>
            {f.nom}
          </button>
        ))}
        {!readOnly && fichiers.length < FICHIERS_MAX && !saisie && (
          <button type="button" className="btn btn-sm btn-secondary" onClick={ouvrirAjout}>+ Fichier</button>
        )}
        {courant && (
          <button type="button" className="btn btn-sm btn-outline" style={{ marginLeft: 'auto' }} onClick={rechercher}>Rechercher</button>
        )}
      </div>

      {!readOnly && courant && !saisie && (
        <div style={{ ...styleBarre, marginBottom: '6px' }}>
          {protege ? (
            <small style={styleNote}>Fichier principal : il ne peut être ni renommé ni supprimé.</small>
          ) : (
            <>
              <button type="button" className="btn btn-sm btn-outline" onClick={ouvrirRenommage}>Renommer</button>
              <button type="button" className="btn btn-sm btn-danger" onClick={retirer}>Supprimer</button>
            </>
          )}
        </div>
      )}

      {saisie && (
        <div style={{ marginBottom: '6px' }}>
          <div style={styleBarre}>
            <input value={saisie.valeur} autoFocus aria-label={saisie.mode === 'ajout' ? 'Nom du nouveau fichier' : 'Nouveau nom du fichier'}
              placeholder="nom.ext" maxLength={200} style={{ width: '220px' }}
              onChange={(ev) => { setSaisie({ ...saisie, valeur: ev.target.value }); setErreur(''); }}
              onKeyDown={(ev) => {
                if (ev.key === 'Enter') { ev.preventDefault(); valider(); }
                if (ev.key === 'Escape') { ev.preventDefault(); annuler(); }
              }} />
            <button type="button" className="btn btn-sm btn-primary" onClick={valider}>{saisie.mode === 'ajout' ? 'Ajouter' : 'Renommer'}</button>
            <button type="button" className="btn btn-sm btn-secondary" onClick={annuler}>Annuler</button>
          </div>
          {erreur && <div className="alert alert-error" role="alert" style={{ marginTop: '4px' }}>{erreur}</div>}
        </div>
      )}

      {principalAbsent && !readOnly && (
        <p style={{ ...styleNote, margin: '0 0 6px' }}>Le fichier principal {principal} manque : ajoutez-le avec « + Fichier ».</p>
      )}

      {courant ? (
        <CodeEditor language={langageDe(courant.nom, langage, principal)} value={courant.contenu} readOnly={readOnly}
          height={height} path={`${espace}/${idsAJour.get(courant.nom)}`} onChange={modifierContenu}
          onMount={(ed) => { editeur.current = ed; }} />
      ) : (
        <p style={styleNote}>{readOnly ? 'Aucun fichier.' : 'Aucun fichier : ajoutez-en un avec « + Fichier ».'}</p>
      )}
    </div>
  );
}
