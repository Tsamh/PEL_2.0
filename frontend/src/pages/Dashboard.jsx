import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await api.get('/accounts/users/dashboard_stats/');
        setStats(res.data);
      } catch {}
      setLoading(false);
    };
    fetchStats();
  }, []);

  if (loading) return <div className="loading">Chargement du tableau de bord...</div>;

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Bienvenue, {user?.first_name}</h1>
          <p style={{ color: 'var(--gray-500)', marginTop: '4px' }}>
            {user?.role === 'superadmin' && 'Vue globale de la plateforme PEL'}
            {user?.role === 'admin' && `Administration — ${user?.etablissement_nom || 'Votre établissement'}`}
            {user?.role === 'enseignant' && 'Gestion de vos cours et évaluations'}
            {user?.role === 'etudiant' && 'Suivez vos évaluations et résultats'}
          </p>
        </div>
      </div>

      {user?.role === 'superadmin' && stats && (
        <div className="dashboard-cards">
          {stats.demandes_attente > 0 && (
            <div className="stat-card" onClick={() => navigate('/validations')} style={{ cursor: 'pointer' }}>
              <div className="stat-icon orange">⏳</div>
              <h3>{stats.demandes_attente}</h3>
              <p>Demandes en attente</p>
            </div>
          )}
          <div className="stat-card" onClick={() => navigate('/etablissements')} style={{ cursor: 'pointer' }}>
            <div className="stat-icon blue">🏫</div>
            <h3>{stats.total_users || 0}</h3>
            <p>Utilisateurs total</p>
          </div>
          <div className="stat-card">
            <div className="stat-icon green">👨‍🎓</div>
            <h3>{stats.total_etudiants || 0}</h3>
            <p>Étudiants</p>
          </div>
          <div className="stat-card">
            <div className="stat-icon purple">👨‍🏫</div>
            <h3>{stats.total_enseignants || 0}</h3>
            <p>Enseignants</p>
          </div>
        </div>
      )}

      {(user?.role === 'admin' || user?.role === 'responsable_formation') && stats && (
        <div className="dashboard-cards">
          <div className="stat-card" onClick={() => navigate('/filieres')} style={{ cursor: 'pointer' }}>
            <div className="stat-icon blue">📚</div>
            <h3>{stats.filieres || 0}</h3>
            <p>Filières</p>
          </div>
          <div className="stat-card" onClick={() => navigate('/classes')} style={{ cursor: 'pointer' }}>
            <div className="stat-icon green">🎓</div>
            <h3>{stats.classes || 0}</h3>
            <p>Classes</p>
          </div>
          <div className="stat-card" onClick={() => navigate('/etudiants')} style={{ cursor: 'pointer' }}>
            <div className="stat-icon orange">👨‍🎓</div>
            <h3>{stats.etudiants || 0}</h3>
            <p>Étudiants</p>
          </div>
          <div className="stat-card" onClick={() => navigate('/enseignants')} style={{ cursor: 'pointer' }}>
            <div className="stat-icon purple">👨‍🏫</div>
            <h3>{stats.enseignants || 0}</h3>
            <p>Enseignants</p>
          </div>
          <div className="stat-card" onClick={() => navigate('/quiz')} style={{ cursor: 'pointer' }}>
            <div className="stat-icon red">📝</div>
            <h3>{stats.quiz || 0}</h3>
            <p>Quiz</p>
          </div>
          <div className="stat-card" onClick={() => navigate('/devoirs')} style={{ cursor: 'pointer' }}>
            <div className="stat-icon blue">💻</div>
            <h3>{stats.devoirs || 0}</h3>
            <p>Devoirs</p>
          </div>
          <div className="stat-card">
            <div className="stat-icon green">📋</div>
            <h3>{stats.soumissions || 0}</h3>
            <p>Soumissions reçues</p>
          </div>
        </div>
      )}

      {user?.role === 'enseignant' && stats && (
        <div className="dashboard-cards">
          <div className="stat-card" onClick={() => navigate('/mes-quiz')} style={{ cursor: 'pointer' }}>
            <div className="stat-icon blue">📝</div>
            <h3>{stats.mes_quiz || 0}</h3>
            <p>Mes Quiz</p>
          </div>
          <div className="stat-card" onClick={() => navigate('/mes-devoirs')} style={{ cursor: 'pointer' }}>
            <div className="stat-icon green">💻</div>
            <h3>{stats.mes_devoirs || 0}</h3>
            <p>Mes Devoirs</p>
          </div>
          <div className="stat-card">
            <div className="stat-icon orange">📋</div>
            <h3>{stats.soumissions_recues || 0}</h3>
            <p>Soumissions reçues</p>
          </div>
          {stats.soumissions_a_corriger > 0 && (
            <div className="stat-card" onClick={() => navigate('/mes-devoirs')} style={{ cursor: 'pointer' }}>
              <div className="stat-icon red">✏️</div>
              <h3>{stats.soumissions_a_corriger}</h3>
              <p>À corriger</p>
            </div>
          )}
        </div>
      )}

      {user?.role === 'etudiant' && stats && (
        <div className="dashboard-cards">
          <div className="stat-card" onClick={() => navigate('/quiz-disponibles')} style={{ cursor: 'pointer' }}>
            <div className="stat-icon blue">📝</div>
            <h3>{stats.quiz_disponibles || 0}</h3>
            <p>Quiz disponibles</p>
          </div>
          <div className="stat-card" onClick={() => navigate('/mes-devoirs')} style={{ cursor: 'pointer' }}>
            <div className="stat-icon green">💻</div>
            <h3>{stats.mes_soumissions || 0}</h3>
            <p>Mes soumissions</p>
          </div>
          <div className="stat-card" onClick={() => navigate('/mes-resultats')} style={{ cursor: 'pointer' }}>
            <div className="stat-icon orange">📊</div>
            <h3>{stats.soumissions_corrigees || 0}</h3>
            <p>Corrigées</p>
          </div>
          {stats.moyenne !== undefined && (
            <div className="stat-card">
              <div className="stat-icon purple">⭐</div>
              <h3>{stats.moyenne}</h3>
              <p>Moyenne générale</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
