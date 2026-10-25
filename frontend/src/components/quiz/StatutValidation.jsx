import { useState } from 'react';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';

const LIBELLES = { brouillon: 'Brouillon', en_attente: 'En attente de validation', validee: 'Validé', refusee: 'Refusé' };
const BADGES = { brouillon: 'badge-inactive', en_attente: 'badge-pending', validee: 'badge-active', refusee: 'badge-inactive' };
const styleNote = { margin: '8px 0 0', fontSize: '0.85rem', color: 'var(--gray-500)' };

export default function StatutValidation({ quiz, onChange }) {
  const [erreur, setErreur] = useState('');
  const [enCours, setEnCours] = useState(false);

  if (!quiz) {
    return (
      <p style={styleNote}>
        Votre établissement demande une validation avant publication : enregistrez le quiz, puis soumettez-le au responsable de formation.
      </p>
    );
  }

  const soumettre = async () => {
    setEnCours(true);
    setErreur('');
    try {
      const res = await api.post(`/quiz/quizzes/${quiz.id}/soumettre_validation/`);
      onChange(res.data);
    } catch (err) {
      setErreur(messageErreur(err, 'Erreur lors de la soumission.'));
    } finally {
      setEnCours(false);
    }
  };

  const statut = quiz.statut_validation;
  return (
    <div style={{ border: '1px solid var(--gray-200)', borderRadius: '8px', padding: '12px', margin: '8px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        <strong>Validation :</strong>
        <span className={`badge ${BADGES[statut]}`}>{LIBELLES[statut]}</span>
        {['brouillon', 'refusee'].includes(statut) && (
          <button type="button" className="btn btn-sm btn-primary" disabled={enCours} onClick={soumettre}>Soumettre pour validation</button>
        )}
      </div>
      {statut === 'refusee' && quiz.motif_refus && <p style={{ margin: '8px 0 0' }}><strong>Motif du refus :</strong> {quiz.motif_refus}</p>}
      {['brouillon', 'refusee'].includes(statut) && <p style={styleNote}>Enregistrez vos modifications avant de soumettre : c'est la version enregistrée qui est examinée.</p>}
      {statut === 'en_attente' && <p style={styleNote}>Le responsable de formation a été prévenu. Modifier le contenu du quiz retire la demande.</p>}
      {statut === 'validee' && <p style={styleNote}>Modifier le contenu (titre, description, réglages de passage, questions) dépubliera le quiz : il faudra le soumettre de nouveau.</p>}
      {erreur && <div className="alert alert-error" style={{ marginTop: '8px' }}>{erreur}</div>}
    </div>
  );
}
