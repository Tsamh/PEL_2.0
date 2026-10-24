import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import { fenetre, formatNote } from './quizAffichage';

function libelleAction(quiz) {
  if (quiz.etat.tentative_en_cours) return quiz.reprise_autorisee ? 'Reprendre' : 'Ouvrir';
  if (quiz.etat.ouvert && quiz.etat.tentatives_restantes > 0) return 'Ouvrir';
  return 'Voir';
}

export default function QuizDisponibles() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/quiz/quizzes/')
      .then((res) => setItems(res.data.results || res.data))
      .catch((err) => setError(messageErreur(err, 'Erreur lors du chargement des quiz.')))
      .finally(() => setLoading(false));
  }, []);

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
            <p>Aucun quiz ne vous est affecté pour le moment.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Titre</th><th>Disponibilité</th><th>Durée</th><th>Questions</th><th>Tentatives</th><th>Meilleure note</th><th>Action</th></tr>
            </thead>
            <tbody>
              {items.map((quiz) => (
                <tr key={quiz.id}>
                  <td>
                    <strong>{quiz.titre}</strong>
                    {quiz.code_requis && <span className="badge badge-pending" style={{ marginLeft: '6px' }}>Code requis</span>}
                    {quiz.description && <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>{quiz.description}</div>}
                  </td>
                  <td>{fenetre(quiz)}</td>
                  <td>{quiz.duree_minutes} min</td>
                  <td>{quiz.nb_questions}</td>
                  <td>{quiz.etat.tentatives_utilisees} / {quiz.tentatives_autorisees}</td>
                  <td>{formatNote(quiz.etat.meilleure_note)}</td>
                  <td><Link className="btn btn-sm btn-primary" to={`/quiz-disponibles/quiz/${quiz.id}`}>{libelleAction(quiz)}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
