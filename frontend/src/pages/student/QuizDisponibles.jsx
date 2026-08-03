import { useState, useEffect } from 'react';
import api from '../../services/api';

export default function QuizDisponibles() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => { fetchItems(); }, []);

  const fetchItems = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/referentiel/quizzes/');
      setItems(res.data.results || res.data);
    } catch (err) {
      setError('Erreur lors du chargement des quiz.');
    } finally {
      setLoading(false);
    }
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
            <p>Il n'y a pas de quiz en cours pour le moment.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Titre</th><th>Cours</th><th>Date</th><th>Durée</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.titre}</strong></td>
                  <td>{item.cours_libelle || '-'}</td>
                  <td>{item.date_prevue || '-'}</td>
                  <td>{item.durée ? `${item.durée} min` : '-'}</td>
                  <td><button className="btn btn-sm btn-primary">Commencer</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
