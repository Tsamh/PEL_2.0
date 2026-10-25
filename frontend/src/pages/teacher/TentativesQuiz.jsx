import { useState, useEffect, useCallback } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }) : '-');
const formatDuree = (s) => (s == null ? '-' : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')} s`);

function ValidationReponse({ reponse, onValidee }) {
  const [score, setScore] = useState(String(Number(reponse.score_obtenu)));
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState('');

  const valider = async () => {
    if (score === '' || Number.isNaN(Number(score))) {
      setErreur('Saisissez une note valide.');
      return;
    }
    setEnvoi(true);
    setErreur('');
    try {
      await api.post(`/quiz/reponses/${reponse.id}/valider/`, { score: Number(score) });
      onValidee();
    } catch (err) {
      setErreur(messageErreur(err, 'Validation impossible.'));
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <tr>
      <td>{reponse.etudiant_nom}</td>
      <td>{reponse.question_texte}</td>
      <td><em>{reponse.texte_reponse}</em></td>
      <td>{reponse.reponses_acceptees.join(', ')}</td>
      <td>{Number(reponse.score_obtenu)} (similarité {Math.round(reponse.similarite * 100)} %)</td>
      <td style={{ whiteSpace: 'nowrap' }}>
        <input type="number" step="0.25" min="0" max={Number(reponse.points)} value={score}
          onChange={(e) => setScore(e.target.value)} style={{ width: '80px', marginRight: '8px' }} />
        / {Number(reponse.points)}{' '}
        <button type="button" className="btn btn-sm btn-success" disabled={envoi} onClick={valider}>Valider</button>
        {erreur && <div className="error-msg">{erreur}</div>}
      </td>
    </tr>
  );
}

export default function TentativesQuiz() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [quiz, setQuiz] = useState(null);
  const [tentatives, setTentatives] = useState([]);
  const [aValider, setAValider] = useState([]);
  const [nbAValider, setNbAValider] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const charger = useCallback(async () => {
    try {
      setError('');
      const [q, t, r] = await Promise.all([
        api.get(`/quiz/quizzes/${id}/`),
        api.get(`/quiz/quizzes/${id}/tentatives/`),
        api.get('/quiz/reponses/', { params: { quiz: id, statut: 'a_valider' } }),
      ]);
      setQuiz(q.data);
      setTentatives(t.data);
      const reponses = r.data.results || r.data;
      setAValider(reponses);
      setNbAValider(r.data.count ?? reponses.length);
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors du chargement des tentatives.'));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { charger(); }, [charger]);

  const publier = async () => {
    setError('');
    setMessage('');
    try {
      await api.post(`/quiz/quizzes/${id}/publier_resultats/`);
      setMessage('Résultats publiés : les étudiants voient maintenant leur note.');
      charger();
    } catch (err) {
      setError(messageErreur(err, 'Publication impossible.'));
    }
  };

  if (loading) return <div className="loading">Chargement...</div>;

  return (
    <div>
      <div className="page-header" style={{ flexWrap: 'wrap', gap: '12px' }}>
        <h1 style={{ margin: 0 }}>Tentatives : {quiz?.titre}</h1>
        <div style={{ display: 'flex', gap: '8px' }}>
          {quiz?.publication_resultats === 'differee' && !quiz.resultats_publies && (
            <button type="button" className="btn btn-primary" onClick={publier}>Publier les résultats</button>
          )}
          <Link className="btn btn-outline" to={`/quiz/${id}/statistiques`}>Statistiques</Link>
          <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>Retour</button>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-success">{message}</div>}

      <h2>Réponses courtes à valider ({nbAValider})</h2>
      <div className="table-container" style={{ marginBottom: '24px' }}>
        {aValider.length === 0 ? (
          <div className="empty-state"><p>Aucune réponse en attente de validation.</p></div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Étudiant</th><th>Question</th><th>Réponse</th><th>Attendu</th><th>Suggestion</th><th>Note finale</th></tr>
            </thead>
            <tbody>
              {aValider.map((r) => <ValidationReponse key={r.id} reponse={r} onValidee={charger} />)}
            </tbody>
          </table>
        )}
      </div>

      <h2>Tentatives ({tentatives.length})</h2>
      <div className="table-container">
        {tentatives.length === 0 ? (
          <div className="empty-state"><p>Aucun étudiant n'a encore passé ce quiz.</p></div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Étudiant</th><th>N°</th><th>Statut</th><th>Début</th><th>Durée</th><th>Note</th></tr>
            </thead>
            <tbody>
              {tentatives.map((t) => (
                <tr key={t.id}>
                  <td>{t.etudiant_nom}{t.est_meilleure && <span className="badge badge-active" style={{ marginLeft: '8px' }}>Retenue</span>}</td>
                  <td>{t.numero}</td>
                  <td>
                    {t.statut === 'en_cours' ? <span className="badge badge-pending">En cours</span> : <span className="badge badge-active">Soumise</span>}
                    {t.soumission_auto && <span className="badge badge-inactive" style={{ marginLeft: '6px' }}>Auto</span>}
                  </td>
                  <td>{formatDate(t.debut)}</td>
                  <td>{formatDuree(t.duree_secondes)}</td>
                  <td>
                    {t.statut === 'soumise' ? `${Number(t.score)} / ${Number(t.score_max)}` : '-'}
                    {t.est_provisoire && ` (provisoire, ${t.nb_a_valider} à valider)`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
