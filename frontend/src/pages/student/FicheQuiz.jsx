import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import { fenetre, formatNote } from './quizAffichage';

export default function FicheQuiz() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [quiz, setQuiz] = useState(null);
  const [introuvable, setIntrouvable] = useState(false);
  const [error, setError] = useState('');
  const [code, setCode] = useState('');
  const [aConfirmer, setAConfirmer] = useState(false);
  const [demarrage, setDemarrage] = useState(false);

  const charger = useCallback(async () => {
    try {
      const res = await api.get(`/quiz/quizzes/${id}/`);
      setQuiz(res.data);
    } catch (err) {
      if (err.response?.status === 404) setIntrouvable(true);
      else setError(messageErreur(err, 'Erreur lors du chargement du quiz.'));
    }
  }, [id]);

  useEffect(() => { charger(); }, [charger]);

  const commencer = async () => {
    setAConfirmer(false);
    setDemarrage(true);
    setError('');
    try {
      const res = await api.post(`/quiz/quizzes/${id}/demarrer/`, quiz.code_requis ? { code } : {});
      navigate(`/quiz-disponibles/tentatives/${res.data.id}`);
    } catch (err) {
      if (err.response?.status === 404) {
        setIntrouvable(true);
        return;
      }
      setError(messageErreur(err, 'Impossible de démarrer ce quiz.'));
      charger();
    } finally {
      setDemarrage(false);
    }
  };

  if (introuvable) {
    return (
      <div>
        <div className="alert alert-error">Ce quiz n'existe pas ou ne vous est pas affecté.</div>
        <Link className="btn btn-secondary" to="/quiz-disponibles">Retour aux quiz</Link>
      </div>
    );
  }
  if (!quiz) return error ? <div className="alert alert-error">{error}</div> : <div className="loading">Chargement...</div>;

  const { etat } = quiz;
  const reprise = Boolean(etat.tentative_en_cours) && quiz.reprise_autorisee;
  const peutCommencer = !reprise && (Boolean(etat.tentative_en_cours) || (etat.ouvert && etat.tentatives_restantes > 0));
  const demandeCode = quiz.code_requis && !reprise;

  const soumettreFormulaire = (e) => {
    e.preventDefault();
    if (etat.tentative_en_cours) setAConfirmer(true);
    else commencer();
  };

  return (
    <div>
      <div className="page-header">
        <h1>{quiz.titre}</h1>
        <Link className="btn btn-secondary" to="/quiz-disponibles">Retour aux quiz</Link>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="table-container" style={{ padding: '20px' }}>
        {quiz.description && <p style={{ marginTop: 0 }}>{quiz.description}</p>}
        <table className="data-table">
          <tbody>
            <tr><th>Disponibilité</th><td>{fenetre(quiz)}</td></tr>
            <tr><th>Durée</th><td>{quiz.duree_minutes} min</td></tr>
            <tr><th>Questions</th><td>{quiz.nb_questions}</td></tr>
            <tr><th>Tentatives</th><td>{etat.tentatives_utilisees} / {quiz.tentatives_autorisees}</td></tr>
            <tr><th>Meilleure note</th><td>{formatNote(etat.meilleure_note)}</td></tr>
          </tbody>
        </table>

        <div style={{ marginTop: '20px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {reprise && (
            <div>
              <button className="btn btn-primary" disabled={demarrage} onClick={commencer}>Reprendre</button>
            </div>
          )}
          {peutCommencer && !aConfirmer && (
            <form onSubmit={soumettreFormulaire} style={{ display: 'flex', gap: '8px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
              {demandeCode && (
                <div className="form-group" style={{ margin: 0 }}>
                  <label>Code d'accès</label>
                  <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="Code donné par l'enseignant" autoComplete="off" required maxLength={12} />
                </div>
              )}
              <button type="submit" className="btn btn-primary" disabled={demarrage}>{etat.tentative_en_cours ? 'Nouvelle tentative' : 'Commencer'}</button>
            </form>
          )}
          {aConfirmer && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxWidth: '480px' }}>
              <span style={{ fontSize: '0.9rem' }}>
                La reprise n'est pas autorisée pour ce quiz : votre tentative en cours sera soumise avec les réponses déjà enregistrées, puis une nouvelle tentative commencera s'il vous en reste.
              </span>
              <div style={{ display: 'flex', gap: '6px' }}>
                <button className="btn btn-sm btn-primary" disabled={demarrage} onClick={commencer}>Confirmer</button>
                <button className="btn btn-sm btn-secondary" onClick={() => setAConfirmer(false)}>Annuler</button>
              </div>
            </div>
          )}
          {!reprise && !peutCommencer && <span className="badge badge-inactive" style={{ alignSelf: 'flex-start' }}>Fermé</span>}
          {etat.derniere_tentative && (
            <div>
              <Link className="btn btn-secondary" to={`/quiz-disponibles/tentatives/${etat.derniere_tentative}`}>Voir le dernier résultat</Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
