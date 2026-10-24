import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import { useAuth } from '../../context/AuthContext';
import Barre from '../../components/stats/Barre';
import { nombre, pourcentage } from '../../components/stats/format';

export default function Statistiques() {
  const { user } = useAuth();
  const enseignant = user?.role === 'enseignant';
  const [compteurs, setCompteurs] = useState(null);
  const [quiz, setQuiz] = useState([]);
  const [suivant, setSuivant] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const requetes = [api.get('/quiz/quizzes/statistiques/')];
    if (enseignant) requetes.push(api.get('/accounts/users/dashboard_stats/'));
    Promise.all(requetes)
      .then(([q, c]) => {
        setQuiz(q.data.results);
        setSuivant(q.data.next);
        if (c) setCompteurs(c.data);
      })
      .catch((err) => setError(messageErreur(err, 'Erreur lors du chargement des statistiques.')))
      .finally(() => setLoading(false));
  }, [enseignant]);

  const plus = async () => {
    try {
      const res = await api.get(suivant);
      setQuiz((liste) => [...liste, ...res.data.results]);
      setSuivant(res.data.next);
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors du chargement des statistiques.'));
    }
  };

  if (loading) return <div className="loading">Chargement...</div>;

  return (
    <div>
      <div className="page-header">
        <h1>Statistiques</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {compteurs && (
        <div className="dashboard-grid" style={{ marginBottom: '24px' }}>
          <div className="stat-card"><div className="stat-number">{compteurs.mes_quiz || 0}</div><div className="stat-label">Quiz créés</div></div>
          <div className="stat-card"><div className="stat-number">{compteurs.mes_devoirs || 0}</div><div className="stat-label">Devoirs créés</div></div>
          <div className="stat-card"><div className="stat-number">{compteurs.soumissions_recues || 0}</div><div className="stat-label">Soumissions reçues</div></div>
          <div className="stat-card"><div className="stat-number">{compteurs.soumissions_a_corriger || 0}</div><div className="stat-label">À corriger</div></div>
        </div>
      )}

      <h2>Quiz</h2>
      <div className="table-container">
        {quiz.length === 0 ? (
          <div className="empty-state"><p>Aucun quiz pour le moment.</p></div>
        ) : (
          <>
            <table className="data-table">
              <thead>
                <tr><th>Quiz</th><th>Participation</th><th>Moyenne</th><th>Médiane</th><th>À valider</th><th></th></tr>
              </thead>
              <tbody>
                {quiz.map((q) => (
                  <tr key={q.id}>
                    <td>
                      <strong>{q.titre}</strong>{' '}
                      {q.est_publie ? <span className="badge badge-active">Publié</span> : <span className="badge badge-inactive">Brouillon</span>}
                    </td>
                    <td>
                      <Barre valeur={q.population.taux_participation} libelle={`${q.population.soumis} sur ${q.population.concernes} étudiants ont soumis`} />
                      <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>{q.population.soumis} sur {q.population.concernes}</div>
                    </td>
                    <td>{q.notes.moyenne == null ? '-' : `${pourcentage(q.notes.moyenne_pourcentage)} (${nombre(q.notes.moyenne)} / ${nombre(q.notes.score_max)})`}</td>
                    <td>{nombre(q.notes.mediane)}</td>
                    <td>{q.nb_a_valider > 0 ? <span className="badge badge-pending">{q.nb_a_valider}</span> : '0'}</td>
                    <td><Link className="btn btn-sm btn-outline" to={`/quiz/${q.id}/statistiques`}>Tableau de bord</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {suivant && <div style={{ padding: '12px', textAlign: 'right' }}><button className="btn btn-sm btn-secondary" onClick={plus}>Afficher plus</button></div>}
          </>
        )}
      </div>
    </div>
  );
}
