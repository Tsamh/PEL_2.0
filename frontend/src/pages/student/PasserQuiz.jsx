import { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useParams } from 'react-router-dom';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import CountdownTimer from '../../components/CountdownTimer';
import ResultatTentative from '../../components/quiz/ResultatTentative';

const LIBELLES_SAUVEGARDE = { enregistrement: 'Enregistrement...', enregistre: 'Réponses enregistrées', erreur: 'Échec de l\'enregistrement' };
const estRepondue = (v) => Boolean(v && ((v.choix && v.choix.length) || (v.texte && v.texte.trim())));

export default function PasserQuiz() {
  const { id } = useParams();
  const [tentative, setTentative] = useState(null);
  const [reponses, setReponses] = useState({});
  const [index, setIndex] = useState(0);
  const [decalage, setDecalage] = useState(0);
  const [etatSauvegarde, setEtatSauvegarde] = useState('');
  const [error, setError] = useState('');
  const [confirmation, setConfirmation] = useState(false);
  const [soumission, setSoumission] = useState(false);
  const minuteurs = useRef({});
  const enAttente = useRef({});
  const dernieres = useRef({});
  const chaines = useRef({});
  const nbEnvois = useRef(0);
  const enSoumission = useRef(false);

  const appliquer = useCallback((data) => {
    setTentative(data);
    // Écart entre l'horloge du serveur et celle du poste : le chrono reste juste même si le poste est déréglé.
    setDecalage(new Date(data.heure_serveur).getTime() - Date.now());
    const initiales = {};
    (data.reponses || []).forEach((r) => { initiales[r.question] = { choix: r.choix, texte: r.texte }; });
    setReponses(initiales);
  }, []);

  const charger = useCallback(async () => {
    try {
      const res = await api.get(`/quiz/tentatives/${id}/`);
      appliquer(res.data);
      setError('');
    } catch (err) {
      setError(messageErreur(err, 'Tentative introuvable.'));
    }
  }, [id, appliquer]);

  // Enregistre une réponse. Les envois d'une même question sont chaînés (le dernier envoie toujours la valeur la plus récente).
  // Renvoie une promesse qui vaut true si la réponse est enregistrée, false sinon.
  const sauvegarder = useCallback((questionId, valeur) => {
    dernieres.current[questionId] = valeur;
    nbEnvois.current += 1;
    setEtatSauvegarde('enregistrement');
    const precedent = chaines.current[questionId] || Promise.resolve();
    const envoi = precedent.then(async () => {
      const courante = dernieres.current[questionId];
      let ok = true;
      try {
        await api.put(`/quiz/tentatives/${id}/repondre/`, { question: questionId, choix: courante.choix, texte: courante.texte });
        setError('');
      } catch (err) {
        if (err.response?.status === 409) {
          charger();
        } else {
          ok = false;
          // Conservée pour être renvoyée à la prochaine soumission ou au prochain changement de page.
          if (!(questionId in enAttente.current) && dernieres.current[questionId] === courante) enAttente.current[questionId] = courante;
          setError(messageErreur(err, "La réponse n'a pas pu être enregistrée."));
        }
      }
      nbEnvois.current -= 1;
      if (!ok) setEtatSauvegarde('erreur');
      else if (nbEnvois.current === 0) setEtatSauvegarde('enregistre');
      return ok;
    });
    chaines.current[questionId] = envoi;
    return envoi;
  }, [id, charger]);

  // Envoie sans attendre les réponses saisies dont l'envoi différé n'est pas encore parti.
  const envoyerEnAttente = useCallback(() => {
    const restantes = Object.entries(enAttente.current);
    enAttente.current = {};
    Object.values(minuteurs.current).forEach(clearTimeout);
    return Promise.all(restantes.map(([questionId, valeur]) => sauvegarder(Number(questionId), valeur)));
  }, [sauvegarder]);

  useEffect(() => {
    charger();
    window.addEventListener('beforeunload', envoyerEnAttente);
    return () => {
      window.removeEventListener('beforeunload', envoyerEnAttente);
      envoyerEnAttente();
    };
  }, [charger, envoyerEnAttente]);

  const modifier = (question, valeur, differe = false) => {
    setReponses((r) => ({ ...r, [question.id]: valeur }));
    clearTimeout(minuteurs.current[question.id]);
    if (differe) {
      enAttente.current[question.id] = valeur;
      minuteurs.current[question.id] = setTimeout(() => {
        delete enAttente.current[question.id];
        sauvegarder(question.id, valeur);
      }, 800);
    } else {
      delete enAttente.current[question.id];
      sauvegarder(question.id, valeur);
    }
  };

  const soumettre = useCallback(async (tempsEcoule = false) => {
    if (enSoumission.current) return;
    enSoumission.current = true;
    setSoumission(true);
    setConfirmation(false);
    try {
      await envoyerEnAttente();
      const resultats = await Promise.all(Object.values(chaines.current));
      if (!resultats.every(Boolean)) {
        setError("Certaines réponses n'ont pas pu être enregistrées. Vérifiez votre connexion puis réessayez.");
        // Une fois le temps écoulé, le serveur clôture la tentative : on tente quand même la soumission.
        if (!tempsEcoule) return;
      }
      const res = await api.post(`/quiz/tentatives/${id}/soumettre/`);
      appliquer(res.data);
      setError('');
    } catch (err) {
      if (err.response?.status === 409) charger();
      else setError(messageErreur(err, 'La soumission a échoué. Réessayez.'));
    } finally {
      enSoumission.current = false;
      setSoumission(false);
    }
  }, [id, envoyerEnAttente, appliquer, charger]);

  if (error && !tentative) return <div className="alert alert-error">{error}</div>;
  if (!tentative) return <div className="loading">Chargement...</div>;

  if (tentative.statut === 'soumise') {
    return (
      <div>
        <div className="page-header">
          <h1>Résultat</h1>
          <Link className="btn btn-secondary" to="/quiz-disponibles">Retour aux quiz</Link>
        </div>
        <ResultatTentative tentative={tentative} />
      </div>
    );
  }

  const questions = tentative.questions;
  const question = questions[index];
  const valeur = reponses[question?.id] || { choix: [], texte: '' };
  const finLocale = new Date(new Date(tentative.fin_prevue).getTime() - decalage).toISOString();
  const nbRepondues = questions.filter((q) => estRepondue(reponses[q.id])).length;

  const basculerChoix = (choixId) => {
    if (question.est_multiple) {
      const choix = valeur.choix.includes(choixId) ? valeur.choix.filter((c) => c !== choixId) : [...valeur.choix, choixId];
      modifier(question, { choix, texte: '' });
    } else {
      modifier(question, { choix: [choixId], texte: '' });
    }
  };

  return (
    <div>
      <div className="page-header" style={{ flexWrap: 'wrap', gap: '12px' }}>
        <h1 style={{ margin: 0 }}>{tentative.quiz_titre}</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ fontSize: '0.9rem', color: etatSauvegarde === 'erreur' ? 'var(--danger, #dc2626)' : 'var(--gray-500)' }}>
            {LIBELLES_SAUVEGARDE[etatSauvegarde] || ''}
          </span>
          <CountdownTimer dateFin={finLocale} onTimeUp={() => soumettre(true)} />
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <nav style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '16px' }} aria-label="Questions">
        {questions.map((q, i) => (
          <button key={q.id} type="button" onClick={() => setIndex(i)}
            className={`btn btn-sm ${i === index ? 'btn-primary' : 'btn-secondary'}`}
            style={estRepondue(reponses[q.id]) && i !== index ? { outline: '2px solid var(--success, #16a34a)' } : undefined}
            aria-current={i === index ? 'step' : undefined}>
            {i + 1}
          </button>
        ))}
      </nav>

      {question && (
        <div className="form-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', marginBottom: '12px' }}>
            <strong>Question {index + 1} sur {questions.length}</strong>
            <span>{Number(question.points)} pt</span>
          </div>
          <p style={{ whiteSpace: 'pre-wrap', fontSize: '1.05rem' }}>{question.texte}</p>
          {question.type_question === 'courte' ? (
            <textarea rows={3} value={valeur.texte} placeholder="Votre réponse"
              onChange={(e) => modifier(question, { choix: [], texte: e.target.value }, true)} style={{ width: '100%' }} />
          ) : (
            <div>
              {question.est_multiple && <p style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>Plusieurs réponses possibles.</p>}
              {question.choix.map((c) => (
                <label key={c.id} style={{ display: 'flex', gap: '10px', alignItems: 'center', padding: '8px 0', cursor: 'pointer' }}>
                  <input type={question.est_multiple ? 'checkbox' : 'radio'} name={`q_${question.id}`}
                    checked={valeur.choix.includes(c.id)} onChange={() => basculerChoix(c.id)} style={{ width: 'auto' }} />
                  {c.texte}
                </label>
              ))}
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '20px' }}>
            <button type="button" className="btn btn-secondary" disabled={index === 0} onClick={() => setIndex(index - 1)}>Précédente</button>
            {index < questions.length - 1 && (
              <button type="button" className="btn btn-primary" onClick={() => setIndex(index + 1)}>Suivante</button>
            )}
          </div>
        </div>
      )}

      <div className="form-card" style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
        <span>{nbRepondues} question(s) répondue(s) sur {questions.length}</span>
        {confirmation ? (
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <span>Soumettre définitivement ?</span>
            <button type="button" className="btn btn-success" disabled={soumission} onClick={() => soumettre()}>{soumission ? 'Envoi...' : 'Oui, soumettre'}</button>
            <button type="button" className="btn btn-secondary" onClick={() => setConfirmation(false)}>Annuler</button>
          </div>
        ) : (
          <button type="button" className="btn btn-primary" onClick={() => setConfirmation(true)}>Terminer et soumettre</button>
        )}
      </div>
    </div>
  );
}
