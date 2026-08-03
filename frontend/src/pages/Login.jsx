import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Link, useNavigate } from 'react-router-dom';

export default function Login() {
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login: authLogin } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const userData = await authLogin(login, password);
      if (userData.must_change_password) {
        navigate('/changer-mot-de-passe');
      } else {
        window.location.href = '/';
      }
    } catch (err) {
      const msg = err.response?.data?.non_field_errors?.[0] || 'Identifiants incorrects';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-left">
        <h1>PEL</h1>
        <p>Plateforme d'Évaluation en Ligne — gérez vos quiz, devoirs de programmation et suivez les résultats en temps réel.</p>
        <ul className="features">
          <li>Quiz interactifs (QCM, vrai/faux, réponses courtes)</li>
          <li>Devoirs de programmation avec IDE intégré</li>
          <li>Auto-correction et statistiques avancées</li>
          <li>Exports Excel et rapports détaillés</li>
        </ul>
      </div>
      <div className="auth-right">
        <div className="auth-card">
          <h2>Connexion</h2>
          <p className="subtitle">Connectez-vous à votre compte</p>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>Email ou nom d'utilisateur</label>
              <input
                type="text"
                placeholder="Entrez votre email ou identifiant"
                value={login}
                onChange={(e) => setLogin(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label>Mot de passe</label>
              <input
                type="password"
                placeholder="Entrez votre mot de passe"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && <div className="error-msg">{error}</div>}
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? 'Connexion...' : 'Se connecter'}
            </button>
          </form>
          <div className="auth-link">
            <Link to="/forgot-password">Mot de passe oublié ?</Link>
          </div>
          <div className="auth-link" style={{ marginTop: '12px' }}>
            <Link to="/register">Créer un compte admin</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
