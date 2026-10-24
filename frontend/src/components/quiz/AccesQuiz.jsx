import { useState } from 'react';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';

export default function AccesQuiz({ quiz, onCodeChange }) {
  const [code, setCode] = useState(quiz.code_acces || '');
  const [message, setMessage] = useState('');
  const [erreur, setErreur] = useState('');
  const [enCours, setEnCours] = useState(false);
  const lien = `${window.location.origin}/quiz-disponibles/quiz/${quiz.id}`;

  const executer = async (action) => {
    setEnCours(true);
    setErreur('');
    setMessage('');
    try {
      await action();
      if (onCodeChange) onCodeChange();
    } catch (err) {
      setErreur(messageErreur(err, "Erreur lors de la mise à jour du code d'accès."));
    } finally {
      setEnCours(false);
    }
  };
  const generer = () => executer(async () => {
    const res = await api.post(`/quiz/quizzes/${quiz.id}/code_acces/`);
    setCode(res.data.code_acces);
  });
  const retirer = () => executer(async () => {
    await api.delete(`/quiz/quizzes/${quiz.id}/code_acces/`);
    setCode('');
  });
  const copier = async () => {
    setErreur('');
    try {
      await navigator.clipboard.writeText(lien);
      setMessage('Lien copié.');
    } catch {
      setMessage(`Copiez ce lien : ${lien}`);
    }
  };

  return (
    <div>
      <h3 style={{ margin: '0 0 8px' }}>Accès</h3>
      <p style={{ fontSize: '0.85rem', color: 'var(--gray-500)', margin: '0 0 12px' }}>
        La connexion est toujours obligatoire. Le code et le lien ne donnent accès qu'aux étudiants affectés.
      </p>
      {erreur && <div className="alert alert-error">{erreur}</div>}
      {message && <div className="alert alert-success">{message}</div>}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '8px' }}>
        {code ? (
          <>
            <span style={{ fontFamily: 'monospace', fontSize: '1.4rem', letterSpacing: '0.2em', fontWeight: 700 }}>{code}</span>
            <button type="button" className="btn btn-sm btn-secondary" disabled={enCours} onClick={generer}>Régénérer</button>
            <button type="button" className="btn btn-sm btn-danger" disabled={enCours} onClick={retirer}>Retirer le code</button>
          </>
        ) : (
          <button type="button" className="btn btn-sm btn-primary" disabled={enCours} onClick={generer}>Générer un code</button>
        )}
        <button type="button" className="btn btn-sm btn-outline" onClick={copier}>Copier le lien</button>
      </div>
    </div>
  );
}
