import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }) : null);
const formatNote = (n) => (n ? `${Number(n.score)} / ${Number(n.score_max)}${n.provisoire ? ' (provisoire)' : ''}` : '-');

function fenetre(quiz) {
  const debut = formatDate(quiz.date_debut);
  const fin = formatDate(quiz.date_fin);
  if (debut && fin) return `${debut} au ${fin}`;
  if (debut) return `À partir du ${debut}`;
  if (fin) return `Jusqu'au ${fin}`;
  return 'Toujours ouvert';
}

export default function QuizDisponibles() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [demarrage, setDemarrage] = useState(null);

  useEffect(() => { fetchItems(); }, []);

  const fetchItems = async (silencieux = false) => {
    if (!silencieux) setLoading(true);
    try {
      const res = await api.get('/quiz/quizzes/');
      setItems(res.data.results || res.data);
      if (!silencieux) setError('');
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors du chargement des quiz.'));
    } finally {
      setLoading(false);
    }
  };

  const commencer = async (quiz) => {
    setDemarrage(quiz.id);
    setError('');
    try {
      const res = await api.post(`/quiz/quizzes/${quiz.id}/demarrer/`);
      navigate(`/quiz-disponibles/tentatives/${res.data.id}`);
    } catch (err) {
      setError(messageErreur(err, 'Impossible de démarrer ce quiz.'));
      fetchItems(true);
    } finally {
      setDemarrage(null);
    }
  };

  const action = (quiz) => {
    const { etat } = quiz;
    if (etat.tentative_en_cours) {
      return <button className="btn btn-sm btn-primary" disabled={demarrage === quiz.id} onClick={() => commencer(quiz)}>Reprendre</button>;
    }
    if (etat.ouvert && etat.tentatives_restantes > 0) {
      return <button className="btn btn-sm btn-primary" disabled={demarrage === quiz.id} onClick={() => commencer(quiz)}>Commencer</button>;
    }
    if (etat.derniere_tentative) {
      return <button className="btn btn-sm btn-secondary" onClick={() => navigate(`/quiz-disponibles/tentatives/${etat.derniere_tentative}`)}>Voir le résultat</button>;
    }
    return <span className="badge badge-inactive">Fermé</span>;
  };

  return (
    <div>
      <div className="page-header">
        <h1>Quiz disponibles</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="table-container">
        {loading ? (
          <div className="loading">Chargement...</div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📝</div>
            <h3>Aucun quiz disponible</h3>
            <p>Il n'y a pas de quiz pour vous en ce moment.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Titre</th><th>Disponibilité</th><th>Durée</th><th>Questions</th><th>Tentatives</th><th>Meilleure note</th><th>Action</th></tr>
            </thead>
            <tbody>
              {items.map((quiz) => (
                <tr key={quiz.id}>
                  <td><strong>{quiz.titre}</strong>{quiz.description && <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>{quiz.description}</div>}</td>
                  <td>{fenetre(quiz)}</td>
                  <td>{quiz.duree_minutes} min</td>
                  <td>{quiz.nb_questions}</td>
                  <td>{quiz.etat.tentatives_utilisees} / {quiz.tentatives_autorisees}</td>
                  <td>{formatNote(quiz.etat.meilleure_note)}</td>
                  <td>{action(quiz)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
