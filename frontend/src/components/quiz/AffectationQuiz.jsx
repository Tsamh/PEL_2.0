import { useEffect, useState } from 'react';
import { chargerTout } from '../../services/pagination';
import { messageErreur } from '../../services/erreurs';
import { resumeCibles } from './cibles';

const nomUtilisateur = (u) => [u.first_name, u.last_name].filter(Boolean).join(' ') || u.username;
const correspond = (filtre, ...textes) => !filtre || textes.some((t) => (t || '').toLowerCase().includes(filtre));
const styleListe = { maxHeight: '180px', overflowY: 'auto', border: '1px solid var(--gray-200)', borderRadius: '6px', padding: '8px' };
const styleLigne = { display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'normal', margin: '2px 0' };
const styleVide = { fontSize: '0.85rem', color: 'var(--gray-500)' };

export default function AffectationQuiz({ valeur, onChange, etudiantsConnus = [], type = 'quiz' }) {
  const [classes, setClasses] = useState([]);
  const [groupes, setGroupes] = useState([]);
  const [recherche, setRecherche] = useState('');
  const [classeEtudiants, setClasseEtudiants] = useState('');
  const [etudiantsClasse, setEtudiantsClasse] = useState([]);
  const [noms, setNoms] = useState(() => Object.fromEntries(etudiantsConnus.map((e) => [e.id, e.nom])));
  const [erreur, setErreur] = useState('');

  useEffect(() => {
    Promise.all([chargerTout('/referentiel/classes/'), chargerTout('/referentiel/groupes/')])
      .then(([c, g]) => { setClasses(c); setGroupes(g); })
      .catch((err) => setErreur(messageErreur(err, 'Erreur lors du chargement des classes et des groupes.')));
  }, []);

  useEffect(() => {
    if (!classeEtudiants) return;
    chargerTout('/accounts/users/', { role: 'etudiant', classe: classeEtudiants })
      .then((us) => {
        setEtudiantsClasse(us);
        setNoms((n) => ({ ...n, ...Object.fromEntries(us.map((u) => [u.id, nomUtilisateur(u)])) }));
      })
      .catch((err) => setErreur(messageErreur(err, 'Erreur lors du chargement des étudiants.')));
  }, [classeEtudiants]);

  const basculer = (cle, id) => {
    const ensemble = new Set(valeur[cle]);
    if (ensemble.has(id)) ensemble.delete(id);
    else ensemble.add(id);
    onChange({ ...valeur, [cle]: [...ensemble] });
  };

  const filtre = recherche.trim().toLowerCase();
  const codeClasse = Object.fromEntries(classes.map((c) => [c.id, c.code]));
  const classesVisibles = classes.filter((c) => correspond(filtre, c.code, c.libelle));
  const groupesVisibles = groupes.filter((g) => correspond(filtre, g.code, g.libelle, codeClasse[g.classe]));

  return (
    <div>
      <h3 style={{ margin: '0 0 8px' }}>Affectation</h3>
      <p style={{ ...styleVide, margin: '0 0 12px' }}>
        Seuls les étudiants ciblés voient {type === 'devoir' ? 'ce devoir' : 'ce quiz'}. Cible actuelle : {resumeCibles(valeur.classes.length, valeur.groupes.length, valeur.etudiants.length)}.
      </p>
      {erreur && <div className="alert alert-error">{erreur}</div>}
      <div className="form-group">
        <input placeholder="Rechercher une classe ou un groupe (code ou libellé)" value={recherche} onChange={(e) => setRecherche(e.target.value)} />
      </div>
      <div className="form-row">
        <div className="form-group">
          <label>Classes</label>
          <div style={styleListe}>
            {classesVisibles.length === 0 ? <span style={styleVide}>Aucune classe.</span> : classesVisibles.map((c) => (
              <label key={c.id} style={styleLigne}>
                <input type="checkbox" style={{ width: 'auto' }} checked={valeur.classes.includes(c.id)} onChange={() => basculer('classes', c.id)} />
                {c.code} - {c.libelle}
              </label>
            ))}
          </div>
        </div>
        <div className="form-group">
          <label>Groupes TD/TP</label>
          <div style={styleListe}>
            {groupesVisibles.length === 0 ? <span style={styleVide}>Aucun groupe.</span> : groupesVisibles.map((g) => (
              <label key={g.id} style={styleLigne}>
                <input type="checkbox" style={{ width: 'auto' }} checked={valeur.groupes.includes(g.id)} onChange={() => basculer('groupes', g.id)} />
                {g.libelle} ({codeClasse[g.classe] || g.classe_libelle})
              </label>
            ))}
          </div>
        </div>
      </div>
      <div className="form-group">
        <label>Étudiants choisis un par un</label>
        <select value={classeEtudiants} onChange={(e) => { setEtudiantsClasse([]); setClasseEtudiants(e.target.value); }}>
          <option value="">-- Choisir une classe pour lister ses étudiants --</option>
          {classes.map((c) => <option key={c.id} value={c.id}>{c.code} - {c.libelle}</option>)}
        </select>
        {classeEtudiants && (
          <div style={{ ...styleListe, marginTop: '8px' }}>
            {etudiantsClasse.length === 0 ? <span style={styleVide}>Aucun étudiant inscrit.</span> : etudiantsClasse.map((u) => (
              <label key={u.id} style={styleLigne}>
                <input type="checkbox" style={{ width: 'auto' }} checked={valeur.etudiants.includes(u.id)} onChange={() => basculer('etudiants', u.id)} />
                {nomUtilisateur(u)}
              </label>
            ))}
          </div>
        )}
        {valeur.etudiants.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
            {valeur.etudiants.map((id) => (
              <span key={id} className="badge badge-active" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                {noms[id] || `Étudiant ${id}`}
                <button type="button" aria-label="Retirer" onClick={() => basculer('etudiants', id)} style={{ border: 'none', background: 'none', cursor: 'pointer', padding: 0 }}>×</button>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
