import { useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);
    try {
      const res = await api.post('/accounts/users/forgot_password/', { email });
      setMessage(res.data.message);
    } catch (err) {
      setError('Une erreur est survenue');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-left">
        <h1>PEL</h1>
        <p>Réinitialisez votre mot de passe en quelques clics.</p>
      </div>
      <div className="auth-right">
        <div className="auth-card">
          <h2>Mot de passe oublié</h2>
          <p className="subtitle">Entrez votre email pour recevoir un lien de réinitialisation</p>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>Email</label>
              <input
                type="email"
                placeholder="votre@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            {message && <div className="success-msg">{message}</div>}
            {error && <div className="error-msg">{error}</div>}
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? 'Envoi en cours...' : 'Envoyer le lien'}
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
