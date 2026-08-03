import { useState, useEffect } from 'react';
import api from '../../services/api';

export default function Statistiques() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => { fetchStats(); }, []);

  const fetchStats = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/accounts/users/dashboard_stats/');
      setStats(res.data);
    } catch (err) {
      setError('Erreur lors du chargement des statistiques.');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="loading">Chargement...</div>;

  return (
    <div>
      <div className="page-header">
        <h1>Statistiques</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {stats && (
        <div className="dashboard-grid">
          <div className="stat-card">
            <div className="stat-number">{stats.mes_quiz || 0}</div>
            <div className="stat-label">Quiz créés</div>
          </div>
          <div className="stat-card">
            <div className="stat-number">{stats.mes_devoirs || 0}</div>
            <div className="stat-label">Devoirs créés</div>
          </div>
          <div className="stat-card">
            <div className="stat-number">{stats.soumissions_recues || 0}</div>
            <div className="stat-label">Soumissions reçues</div>
          </div>
          <div className="stat-card">
            <div className="stat-number">{stats.soumissions_a_corriger || 0}</div>
            <div className="stat-label">À corriger</div>
          </div>
        </div>
      )}
    </div>
  );
}
