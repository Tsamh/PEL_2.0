import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../services/api';

export default function RegisterAdmin() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    email: '',
    password: '',
    password_confirm: '',
    first_name: '',
    last_name: '',
    telephone: '',
    etablissement_nom: '',
    etablissement_code: '',
    etablissement_sigle: '',
    etablissement_adresse: '',
    etablissement_telephone: '',
    etablissement_email: '',
  });

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (form.password !== form.password_confirm) {
      setError('Les mots de passe ne correspondent pas');
      return;
    }

    if (form.password.length < 8) {
      setError('Le mot de passe doit contenir au moins 8 caractères');
      return;
    }

    setSaving(true);
    try {
      await api.post('/accounts/users/register_admin/', form);
      navigate('/register-success');
    } catch (err) {
      setError(err.response?.data?.error || "Erreur lors de l'inscription");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-left">
        <div className="auth-left-content">
          <h1>PEL</h1>
          <h2>Plateforme d'Évaluation en Ligne</h2>
          <div className="features">
            <div className="feature-item">
              <span className="feature-icon">🏫</span>
              <div>
                <strong>Inscription Admin</strong>
                <p>Créez votre compte et votre établissement</p>
              </div>
            </div>
            <div className="feature-item">
              <span className="feature-icon">✅</span>
              <div>
                <strong>Validation</strong>
                <p>Le superadmin valide votre demande</p>
              </div>
            </div>
            <div className="feature-item">
              <span className="feature-icon">🚀</span>
              <div>
                <strong>Activation</strong>
                <p>Commencez à gérer votre établissement</p>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="auth-right">
        <div className="auth-card">
          <h2>Créer un compte admin</h2>
          <p className="subtitle">Inscrivez-vous pour administrer votre établissement</p>

          {error && <div className="alert alert-error">{error}</div>}

          {step === 1 && (
            <form onSubmit={(e) => { e.preventDefault(); setStep(2); }}>
              <div className="form-group">
                <label>Prénom</label>
                <input type="text" name="first_name" value={form.first_name} onChange={handleChange} placeholder="Votre prénom" required />
              </div>
              <div className="form-group">
                <label>Nom</label>
                <input type="text" name="last_name" value={form.last_name} onChange={handleChange} placeholder="Votre nom" required />
              </div>
              <div className="form-group">
                <label>Email</label>
                <input type="email" name="email" value={form.email} onChange={handleChange} placeholder="admin@ecole.com" required />
              </div>
              <div className="form-group">
                <label>Téléphone</label>
                <input type="tel" name="telephone" value={form.telephone} onChange={handleChange} placeholder="+221 77 123 45 67" />
              </div>
              <div className="form-group">
                <label>Mot de passe</label>
                <input type="password" name="password" value={form.password} onChange={handleChange} placeholder="Min. 8 caractères" required />
              </div>
              <div className="form-group">
                <label>Confirmer le mot de passe</label>
                <input type="password" name="password_confirm" value={form.password_confirm} onChange={handleChange} placeholder="Confirmez votre mot de passe" required />
              </div>
              <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
                Suivant →
              </button>
            </form>
          )}

          {step === 2 && (
            <form onSubmit={handleSubmit}>
              <h3 style={{ margin: '0 0 16px', fontSize: '1rem', color: 'var(--gray-500)' }}>Informations de l'établissement</h3>
              <div className="form-group">
                <label>Nom de l'établissement</label>
                <input type="text" name="etablissement_nom" value={form.etablissement_nom} onChange={handleChange} placeholder="ex: Université de Dakar" required />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Code</label>
                  <input type="text" name="etablissement_code" value={form.etablissement_code} onChange={handleChange} placeholder="ex: UD" required />
                </div>
                <div className="form-group">
                  <label>Sigle</label>
                  <input type="text" name="etablissement_sigle" value={form.etablissement_sigle} onChange={handleChange} placeholder="ex: UD" />
                </div>
              </div>
              <div className="form-group">
                <label>Adresse</label>
                <input type="text" name="etablissement_adresse" value={form.etablissement_adresse} onChange={handleChange} placeholder="Adresse complète" />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Téléphone</label>
                  <input type="tel" name="etablissement_telephone" value={form.etablissement_telephone} onChange={handleChange} placeholder="+221 33 123 45 67" />
                </div>
                <div className="form-group">
                  <label>Email</label>
                  <input type="email" name="etablissement_email" value={form.etablissement_email} onChange={handleChange} placeholder="contact@ecole.com" />
                </div>
              </div>
              <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setStep(1)} style={{ flex: 1 }}>
                  ← Retour
                </button>
                <button type="submit" className="btn btn-primary" disabled={saving} style={{ flex: 1 }}>
                  {saving ? 'Inscription...' : "S'inscrire"}
                </button>
              </div>
            </form>
          )}

          <div className="auth-footer">
            Déjà un compte ? <Link to="/login">Se connecter</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
