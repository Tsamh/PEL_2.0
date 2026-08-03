import { useState, useEffect } from 'react';
import api from '../../services/api';

export default function MesCours() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => { fetchItems(); }, []);

  const fetchItems = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/referentiel/cours/');
      setItems(res.data.results || res.data);
    } catch (err) {
      setError('Erreur lors du chargement des cours.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Mes cours</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="table-container">
        {loading ? (
          <div className="loading">Chargement...</div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📚</div>
            <h3>Aucun cours assigné</h3>
            <p>Contactez votre administrateur pour qu'il vous assigne des cours.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Titre</th><th>EC</th><th>UE</th><th>Filière</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.titre}</strong></td>
                  <td>{item.ec_libelle || '-'}</td>
                  <td>{item.ue_libelle || '-'}</td>
                  <td>{item.filiere_libelle || '-'}</td>
                  <td><button className="btn btn-sm btn-secondary">Voir détails</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
