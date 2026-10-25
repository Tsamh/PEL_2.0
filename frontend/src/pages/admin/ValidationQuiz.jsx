import { Fragment, useCallback, useEffect, useState } from 'react';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import { useAuth } from '../../context/AuthContext';
import { resumeCibles } from '../../components/quiz/cibles';

const TYPES = { qcm: 'QCM', vf: 'Vrai / Faux', courte: 'Réponse courte' };
const formatDate = (iso) => (iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }) : '-');

function Apercu({ quiz }) {
  return (
    <ol style={{ margin: '8px 0', paddingLeft: '20px' }}>
      {quiz.questions.map((q) => (
        <li key={q.id} style={{ marginBottom: '8px' }}>
          <strong>{q.texte}</strong> <span style={{ color: 'var(--gray-500)', fontSize: '0.85rem' }}>({TYPES[q.type_question]}, {Number(q.points)} pt{Number(q.penalite) > 0 ? `, pénalité ${Number(q.penalite)}` : ''})</span>
          <ul style={{ margin: '4px 0', paddingLeft: '18px' }}>
            {q.choix.map((c) => (
              <li key={c.id} style={{ color: c.est_correct ? 'var(--success, #16a34a)' : 'inherit' }}>
                {c.texte}{c.est_correct && (q.type_question === 'courte' ? ' (réponse acceptée)' : ' (bonne réponse)')}
              </li>
            ))}
          </ul>
          {q.explication && <div style={{ fontSize: '0.85rem' }}>Explication : {q.explication}</div>}
        </li>
      ))}
    </ol>
  );
}

export default function ValidationQuiz() {
  const { user } = useAuth();
  const peutRegler = user?.role === 'admin';
  const [etablissement, setEtablissement] = useState(null);
  const [quiz, setQuiz] = useState([]);
  const [suivant, setSuivant] = useState(null);
  const [ouvert, setOuvert] = useState(null);
  const [refus, setRefus] = useState({ id: null, motif: '' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const chargerFile = useCallback(async () => {
    try {
      const res = await api.get('/quiz/quizzes/', { params: { statut_validation: 'en_attente' } });
      setQuiz(res.data.results);
      setSuivant(res.data.next);
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors du chargement des quiz en attente.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    chargerFile();
    if (user?.role !== 'superadmin') {
      api.get('/referentiel/etablissements/')
        .then((res) => setEtablissement((res.data.results || res.data)[0] || null))
        .catch((err) => setError(messageErreur(err, "Erreur lors du chargement de l'établissement.")));
    }
  }, [chargerFile, user?.role]);

  const executer = async (action, succes, defaut) => {
    setError('');
    setMessage('');
    try {
      await action();
      setMessage(succes);
      await chargerFile();
    } catch (err) {
      setError(messageErreur(err, defaut));
    }
  };

  const basculerReglage = () => executer(async () => {
    const res = await api.patch(`/referentiel/etablissements/${etablissement.id}/parametres/`, { validation_quiz_requise: !etablissement.validation_quiz_requise });
    setEtablissement(res.data);
  }, 'Réglage enregistré.', "Erreur lors de l'enregistrement du réglage.");

  const valider = (q) => executer(() => api.post(`/quiz/quizzes/${q.id}/valider/`), `« ${q.titre} » est validé et publié.`, 'Erreur lors de la validation.');

  const refuser = (q) => executer(async () => {
    await api.post(`/quiz/quizzes/${q.id}/refuser/`, { motif: refus.motif });
    setRefus({ id: null, motif: '' });
  }, `« ${q.titre} » est renvoyé à son auteur.`, 'Erreur lors du refus.');

  const plus = async () => {
    try {
      const res = await api.get(suivant);
      setQuiz((l) => [...l, ...res.data.results]);
      setSuivant(res.data.next);
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors du chargement des quiz en attente.'));
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Validation des quiz</h1>
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-success">{message}</div>}

      {etablissement && (
        <div className="table-container" style={{ padding: '16px', marginBottom: '16px' }}>
          <strong>Réglage de l'établissement :</strong>{' '}
          {etablissement.validation_quiz_requise
            ? 'les quiz des enseignants doivent être validés avant publication.'
            : 'les enseignants publient leurs quiz directement.'}
          {peutRegler && (
            <div style={{ marginTop: '8px' }}>
              <button type="button" className="btn btn-sm btn-secondary" onClick={basculerReglage}>
                {etablissement.validation_quiz_requise ? 'Ne plus exiger de validation' : 'Exiger une validation avant publication'}
              </button>
            </div>
          )}
        </div>
      )}

      <h2>En attente de validation</h2>
      <div className="table-container">
        {loading ? <div className="loading">Chargement...</div> : quiz.length === 0 ? (
          <div className="empty-state"><p>Aucun quiz en attente.</p></div>
        ) : (
          <>
            <table className="data-table">
              <thead><tr><th>Quiz</th><th>Auteur</th><th>Soumis le</th><th>Questions</th><th>Cible</th><th>Actions</th></tr></thead>
              <tbody>
                {quiz.map((q) => (
                  <Fragment key={q.id}>
                    <tr>
                      <td><strong>{q.titre}</strong>{q.description && <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>{q.description}</div>}</td>
                      <td>{q.cree_par_nom || '-'}</td>
                      <td>{formatDate(q.soumis_le)}</td>
                      <td>{q.questions.length}</td>
                      <td>{q.nb_cibles > 0 ? resumeCibles(q.classes_detail.length, q.groupes_detail.length, q.etudiants_detail.length) : 'Non affecté'}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <button type="button" className="btn btn-sm btn-outline" style={{ marginRight: '6px' }} onClick={() => setOuvert(ouvert === q.id ? null : q.id)}>{ouvert === q.id ? 'Masquer' : 'Aperçu'}</button>
                        <button type="button" className="btn btn-sm btn-primary" style={{ marginRight: '6px' }} onClick={() => valider(q)}>Valider</button>
                        <button type="button" className="btn btn-sm btn-danger" onClick={() => setRefus({ id: q.id, motif: '' })}>Refuser</button>
                      </td>
                    </tr>
                    {ouvert === q.id && <tr><td colSpan={6}><Apercu quiz={q} /></td></tr>}
                    {refus.id === q.id && (
                      <tr>
                        <td colSpan={6}>
                          <div className="form-group" style={{ margin: '4px 0' }}>
                            <label>Motif du refus (envoyé à l'auteur)</label>
                            <textarea rows={2} maxLength={2000} value={refus.motif} onChange={(e) => setRefus({ id: q.id, motif: e.target.value })} />
                          </div>
                          <div style={{ display: 'flex', gap: '6px' }}>
                            <button type="button" className="btn btn-sm btn-danger" disabled={!refus.motif.trim()} onClick={() => refuser(q)}>Confirmer le refus</button>
                            <button type="button" className="btn btn-sm btn-secondary" onClick={() => setRefus({ id: null, motif: '' })}>Annuler</button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
            {suivant && <div style={{ padding: '12px', textAlign: 'right' }}><button className="btn btn-sm btn-secondary" onClick={plus}>Afficher plus</button></div>}
          </>
        )}
      </div>
    </div>
  );
}
