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

export default function Planning() {
  const [sessions, setSessions] = useState([]);
  const [suivant, setSuivant] = useState(null);
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
    api.get('/quiz/sessions-quiz/', { params: { a_venir: passees ? undefined : '1', periode: periode || undefined } })
      .then((res) => { setSessions(res.data.results); setSuivant(res.data.next); setError(''); })
      .catch((err) => setError(messageErreur(err, 'Erreur lors du chargement du planning.')))
      .finally(() => setLoading(false));
  }, [periode, passees]);

  const plus = async () => {
    try {
      const res = await api.get(suivant);
      setSessions((l) => [...l, ...res.data.results]);
      setSuivant(res.data.next);
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
              <thead><tr><th>Ouverture</th><th>Fermeture</th><th>Quiz</th><th>Type</th><th>Cibles</th><th>État</th></tr></thead>
              <tbody>
                {sessions.map((s) => {
                  const [classe, libelle] = etat(s, maintenant);
                  return (
                    <tr key={s.id}>
                      <td>{formatDate(s.ouverture)}</td>
                      <td>{formatDate(s.fermeture)}</td>
                      <td><Link to={`/quiz/${s.quiz}/statistiques`}>{s.quiz_titre}</Link>{s.libelle && <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>{s.libelle}</div>}</td>
                      <td>{s.type === 'rattrapage' ? 'Rattrapage' : 'Session'}</td>
                      <td>{cibles(s)}</td>
                      <td><span className={`badge ${classe}`}>{libelle}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {suivant && <div style={{ padding: '12px', textAlign: 'right' }}><button className="btn btn-sm btn-secondary" onClick={plus}>Afficher plus</button></div>}
          </>
        )}
      </div>
    </div>
  );
}
