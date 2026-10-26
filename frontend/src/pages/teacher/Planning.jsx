import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../../services/api';
import { chargerTout } from '../../services/pagination';
import { messageErreur } from '../../services/erreurs';

const formatDate = (iso) => new Date(iso).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' });

function etat(s, maintenant) {
  if (new Date(s.ouverture) > maintenant) return ['badge-inactive', 'À venir'];
  if (new Date(s.fermeture) > maintenant) return ['badge-active', 'En cours'];
  return ['badge-pending', 'Terminée'];
}

function cibles(s) {
  if (s.type === 'rattrapage') return `${s.nb_etudiants} étudiant${s.nb_etudiants > 1 ? 's' : ''}`;
  return [...s.classes_detail.map((c) => c.code), ...s.groupes_detail.map((g) => g.libelle)].join(', ');
}

// Deux sources paginées, chacune triée par ouverture : quiz et devoirs.
const SOURCES = [
  { type: 'quiz', url: '/quiz/sessions-quiz/' },
  { type: 'devoir', url: '/programming/sessions-devoir/' },
];

const marquer = (type, liste) => liste.map((s) => ({ ...s, evaluation: type }));
const cle = (s) => `${s.evaluation}-${s.id}`;
const parOuverture = (a, b) => new Date(a.ouverture) - new Date(b.ouverture) || a.evaluation.localeCompare(b.evaluation) || a.id - b.id;

// Fusion des sources : seules les sessions qui ouvrent avant la dernière chargée de chaque source
// incomplète sont montrées, pour que l'ordre reste exact quand une page suivante arrive.
function fusion(etat) {
  const limites = SOURCES.filter((src) => etat[src.type].suivant && etat[src.type].sessions.length > 0)
    .map((src) => new Date(etat[src.type].sessions[etat[src.type].sessions.length - 1].ouverture).getTime());
  const limite = limites.length > 0 ? Math.min(...limites) : Infinity;
  return SOURCES.flatMap((src) => etat[src.type].sessions)
    .filter((s) => new Date(s.ouverture).getTime() <= limite)
    .sort(parOuverture);
}

const etatVide = { quiz: { sessions: [], suivant: null }, devoir: { sessions: [], suivant: null } };

function lienEvaluation(s) {
  if (s.evaluation === 'devoir') return <Link to={`/devoirs/${s.devoir}/corrections`}>{s.devoir_titre}</Link>;
  return <Link to={`/quiz/${s.quiz}/statistiques`}>{s.quiz_titre}</Link>;
}

export default function Planning() {
  const [sources, setSources] = useState(etatVide);
  const [periodes, setPeriodes] = useState([]);
  const [periode, setPeriode] = useState('');
  const [passees, setPassees] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    chargerTout('/referentiel/periodes-evaluation/').then(setPeriodes)
      .catch((err) => setError(messageErreur(err, 'Erreur lors du chargement des périodes.')));
  }, []);

  useEffect(() => {
    setLoading(true);
    const params = { a_venir: passees ? undefined : '1', periode: periode || undefined };
    Promise.all(SOURCES.map((src) => api.get(src.url, { params })))
      .then((reponses) => {
        setSources(Object.fromEntries(SOURCES.map((src, i) => [src.type, {
          sessions: marquer(src.type, reponses[i].data.results || reponses[i].data), suivant: reponses[i].data.next || null,
        }])));
        setError('');
      })
      .catch((err) => setError(messageErreur(err, 'Erreur lors du chargement du planning.')))
      .finally(() => setLoading(false));
  }, [periode, passees]);

  const sessions = fusion(sources);
  const incompletes = SOURCES.filter((src) => sources[src.type].suivant);

  // Charge la page suivante de la source qui limite l'affichage (celle dont la dernière session ouvre le plus tôt).
  const plus = async () => {
    const derniere = (src) => {
      const l = sources[src.type].sessions;
      return l.length > 0 ? new Date(l[l.length - 1].ouverture).getTime() : -Infinity;
    };
    const src = incompletes.reduce((a, b) => (derniere(b) < derniere(a) ? b : a));
    try {
      const res = await api.get(sources[src.type].suivant);
      setSources((etat) => ({
        ...etat,
        [src.type]: { sessions: [...etat[src.type].sessions, ...marquer(src.type, res.data.results)], suivant: res.data.next },
      }));
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors du chargement du planning.'));
    }
  };

  const maintenant = new Date();

  return (
    <div>
      <div className="page-header">
        <h1>Planning des évaluations</h1>
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: '12px' }}>
        <div className="form-group" style={{ margin: 0 }}>
          <label>Période</label>
          <select value={periode} onChange={(e) => setPeriode(e.target.value)}>
            <option value="">Toutes</option>
            {periodes.map((p) => <option key={p.id} value={p.id}>{p.semestre_libelle} : {p.libelle}</option>)}
          </select>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 'normal' }}>
          <input type="checkbox" style={{ width: 'auto' }} checked={passees} onChange={(e) => setPassees(e.target.checked)} />
          Inclure les sessions terminées
        </label>
      </div>
      <div className="table-container">
        {loading ? <div className="loading">Chargement...</div> : sessions.length === 0 ? (
          <div className="empty-state"><p>Aucune session planifiée.</p></div>
        ) : (
          <>
            <table className="data-table">
              <thead><tr><th>Ouverture</th><th>Fermeture</th><th>Type d'évaluation</th><th>Évaluation</th><th>Session</th><th>Cibles</th><th>État</th></tr></thead>
              <tbody>
                {sessions.map((s) => {
                  const [classe, libelle] = etat(s, maintenant);
                  return (
                    <tr key={cle(s)}>
                      <td>{formatDate(s.ouverture)}</td>
                      <td>{formatDate(s.fermeture)}</td>
                      <td><span className="badge badge-active">{s.evaluation === 'devoir' ? 'Devoir' : 'Quiz'}</span></td>
                      <td>{lienEvaluation(s)}{s.libelle && <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>{s.libelle}</div>}</td>
                      <td>{s.type === 'rattrapage' ? 'Rattrapage' : 'Session'}</td>
                      <td>{cibles(s)}</td>
                      <td><span className={`badge ${classe}`}>{libelle}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {incompletes.length > 0 && <div style={{ padding: '12px', textAlign: 'right' }}><button className="btn btn-sm btn-secondary" onClick={plus}>Afficher plus</button></div>}
          </>
        )}
      </div>
    </div>
  );
}
