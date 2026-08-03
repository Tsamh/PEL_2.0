import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../../services/api';

export default function MesDevoirsEtudiant() {
  const [items, setItems] = useState([]);
  const [soumissions, setSoumissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError('');
      try {
        const [devoirsRes, soumissionsRes] = await Promise.all([
          api.get('/programming/devoirs/'),
          api.get('/programming/soumissions/'),
        ]);
        setItems(devoirsRes.data.results || devoirsRes.data);
        setSoumissions(soumissionsRes.data.results || soumissionsRes.data);
      } catch (err) {
        setError('Erreur lors du chargement des devoirs.');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const getSoumission = (devoirId) => soumissions.find((s) => s.devoir === devoirId);

  const langageLabel = { python: 'Python', java: 'Java', c: 'C', cpp: 'C++', javascript: 'JavaScript', autre: 'Autre' };

  return (
    <div>
      <div className="page-header">
        <h1>Mes devoirs</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="table-container">
        {loading ? (
          <div className="loading">Chargement...</div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">💻</div>
            <h3>Aucun devoir</h3>
            <p>Il n'y a pas de devoir en cours pour le moment.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Titre</th><th>Langage</th><th>Points</th><th>Échéance</th><th>Statut</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const sub = getSoumission(item.id);
                return (
                  <tr key={item.id}>
                    <td><strong>{item.titre}</strong></td>
                    <td><span className="badge badge-active">{langageLabel[item.langage] || item.langage}</span></td>
                    <td>{item.points_max} pts</td>
                    <td>{item.date_fin ? new Date(item.date_fin).toLocaleDateString('fr-FR') : '-'}</td>
                    <td>
                      {sub ? (
                        sub.statut === 'corrige' ? (
                          <span className="badge badge-active">Corrigé ({sub.score}/{item.points_max})</span>
                        ) : (
                          <span className="badge badge-active">Soumis</span>
                        )
                      ) : (
                        <span className="badge badge-inactive">À rendre</span>
                      )}
                    </td>
                    <td>
                      <Link to={`/devoirs/${item.id}`} className={`btn btn-sm ${sub ? 'btn-secondary' : 'btn-primary'}`}>
                        {sub ? 'Voir' : 'Soumettre'}
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
