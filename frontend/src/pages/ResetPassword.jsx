import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../services/api';

export default function ResetPassword() {
  const { token } = useParams();
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    if (password !== passwordConfirm) {
      setError('Les mots de passe ne correspondent pas');
      return;
    }
    setLoading(true);
    try {
      const res = await api.post('/accounts/users/reset_password/', {
        token,
        password,
        password_confirm: passwordConfirm,
      });
      setMessage(res.data.message);
    } catch (err) {
      setError(err.response?.data?.error || 'Une erreur est survenue');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-left">
        <h1>PEL</h1>
        <p>Créez un nouveau mot de passe sécurisé.</p>
      </div>
      <div className="auth-right">
        <div className="auth-card">
          <h2>Nouveau mot de passe</h2>
          <p className="subtitle">Choisissez un mot de passe fort</p>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>Nouveau mot de passe</label>
              <input
                type="password"
                placeholder="Minimum 8 caractères"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
              />
            </div>
            <div className="form-group">
              <label>Confirmer le mot de passe</label>
              <input
                type="password"
                placeholder="Retapez le mot de passe"
                value={passwordConfirm}
                onChange={(e) => setPasswordConfirm(e.target.value)}
                required
                minLength={8}
              />
            </div>
            {message && <div className="success-msg">{message}</div>}
            {error && <div className="error-msg">{error}</div>}
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? 'Réinitialisation...' : 'Réinitialiser'}
            </button>
          </form>
          <div className="auth-link">
            <Link to="/login">← Retour à la connexion</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
