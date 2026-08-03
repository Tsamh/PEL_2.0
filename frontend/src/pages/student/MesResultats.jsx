import { useState, useEffect } from 'react';
import api from '../../services/api';

export default function MesResultats() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => { fetchItems(); }, []);

  const fetchItems = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/referentiel/resultats/');
      setItems(res.data.results || res.data);
    } catch (err) {
      setError('Erreur lors du chargement des résultats.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Mes résultats</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="table-container">
        {loading ? (
          <div className="loading">Chargement...</div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📊</div>
            <h3>Aucun résultat</h3>
            <p>Vos résultats apparaîtront ici après les évaluations.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Évaluation</th><th>Cours</th><th>Note</th><th>Date</th></tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={index}>
                  <td><strong>{item.evaluation_titre || '-'}</strong></td>
                  <td>{item.cours_libelle || '-'}</td>
                  <td><span className="badge badge-active">{item.note}/20</span></td>
                  <td>{item.date || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
