import { Link } from 'react-router-dom';

export default function RegisterSuccess() {
  return (
    <div className="auth-page">
      <div className="auth-left">
        <div className="auth-left-content">
          <h1>PEL</h1>
          <h2>Plateforme d'Évaluation en Ligne</h2>
        </div>
      </div>
      <div className="auth-right">
        <div className="auth-card" style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '4rem', marginBottom: '16px' }}>✅</div>
          <h2>Demande envoyée !</h2>
          <p style={{ color: 'var(--gray-400)', margin: '16px 0 24px' }}>
            Votre demande de compte administrateur a été envoyée avec succès.
            Le superadministrateur va examiner votre demande.
          </p>
          <div style={{ background: 'var(--gray-100)', borderRadius: '8px', padding: '16px', marginBottom: '24px', textAlign: 'left' }}>
            <p style={{ margin: 0, fontSize: '0.9rem', color: 'var(--gray-500)' }}>
              <strong>Prochaines étapes :</strong>
            </p>
            <ol style={{ margin: '8px 0 0', paddingLeft: '20px', fontSize: '0.85rem', color: 'var(--gray-500)' }}>
              <li>Le superadministrateur valide votre demande</li>
              <li>Vous recevrez un email de confirmation</li>
              <li>Cliquez sur le lien pour créer votre mot de passe</li>
              <li>Connectez-vous et gérez votre établissement</li>
            </ol>
          </div>
          <Link to="/login" className="btn btn-primary" style={{ width: '100%' }}>
            Retour à la connexion
          </Link>
        </div>
      </div>
    </div>
  );
}
