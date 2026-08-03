import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function ForceChangePassword() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ ancien_mot_de_passe: '', nouveau_mot_de_passe: '', confirmer_mot_de_passe: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (form.nouveau_mot_de_passe !== form.confirmer_mot_de_passe) {
      setError('Les mots de passe ne correspondent pas');
      return;
    }
    if (form.nouveau_mot_de_passe.length < 8) {
      setError('Le mot de passe doit contenir au moins 8 caractères');
      return;
    }

    setLoading(true);
    try {
      await api.post('/accounts/users/force_change_password/', form);
      logout();
      navigate('/login');
    } catch (err) {
      setError(err.response?.data?.error || 'Erreur lors du changement de mot de passe');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-card">
          <div className="login-header">
            <div className="brand-icon-lg">PEL</div>
            <h1>Changer votre mot de passe</h1>
            <p>Pour des raisons de sécurité, vous devez changer votre mot de passe lors de votre première connexion.</p>
          </div>

          {error && <div className="alert alert-error">{error}</div>}

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>Mot de passe actuel</label>
              <input
                type="password"
                value={form.ancien_mot_de_passe}
                onChange={(e) => setForm({...form, ancien_mot_de_passe: e.target.value})}
                required
              />
            </div>
            <div className="form-group">
              <label>Nouveau mot de passe</label>
              <input
                type="password"
                value={form.nouveau_mot_de_passe}
                onChange={(e) => setForm({...form, nouveau_mot_de_passe: e.target.value})}
                required
                minLength={8}
              />
            </div>
            <div className="form-group">
              <label>Confirmer le mot de passe</label>
              <input
                type="password"
                value={form.confirmer_mot_de_passe}
                onChange={(e) => setForm({...form, confirmer_mot_de_passe: e.target.value})}
                required
                minLength={8}
              />
            </div>
            <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
              {loading ? 'Changement...' : 'Changer le mot de passe'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
