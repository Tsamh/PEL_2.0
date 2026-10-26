import { Fragment, useCallback, useEffect, useState } from 'react';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import { useAuth } from '../../context/AuthContext';
import { resumeCibles } from '../../components/quiz/cibles';
import ApercuDevoir from '../../components/devoirs/ApercuDevoir';

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

// File d'attente d'un type d'évaluation : chargement paginé, aperçu, validation et refus avec motif.
const SOURCES = {
  quiz: {
    url: '/quiz/quizzes/', titre: 'Quiz', colonneTitre: 'Quiz', vide: 'Aucun quiz en attente.', colonne: 'Questions',
    erreur: 'Erreur lors du chargement des quiz en attente.',
    sousTitre: (q) => q.description,
    contenu: (q) => q.questions.length,
    nbCibles: (q) => q.nb_cibles,
    apercu: (q) => <Apercu quiz={q} />,
  },
  devoir: {
    url: '/programming/devoirs/', titre: 'Devoirs', colonneTitre: 'Devoir', vide: 'Aucun devoir en attente.', colonne: 'Exercices',
    erreur: 'Erreur lors du chargement des devoirs en attente.',
    sousTitre: (d) => d.langage_display,
    contenu: (d) => `${d.nb_exercices ?? (d.exercices || []).length} (${Number(d.bareme)} pts)`,
    nbCibles: (d) => d.classes_detail.length + d.groupes_detail.length + d.etudiants_detail.length,
    apercu: (d) => <ApercuDevoir devoir={d} />,
  },
};

function FileAttente({ type, onMessage, onErreur }) {
  const source = SOURCES[type];
  const [items, setItems] = useState([]);
  const [suivant, setSuivant] = useState(null);
  const [ouvert, setOuvert] = useState(null);
  const [refus, setRefus] = useState({ id: null, motif: '' });
  const [loading, setLoading] = useState(true);
  const [enCours, setEnCours] = useState(false);

  const charger = useCallback(async () => {
    try {
      const res = await api.get(source.url, { params: { statut_validation: 'en_attente' } });
      setItems(res.data.results || res.data);
      setSuivant(res.data.next || null);
    } catch (err) {
      onErreur(messageErreur(err, source.erreur));
    } finally {
      setLoading(false);
    }
  }, [source, onErreur]);

  useEffect(() => { charger(); }, [charger]);

  const executer = async (action, succes, defaut) => {
    onErreur('');
    onMessage('');
    setEnCours(true);
    try {
      await action();
      onMessage(succes);
      await charger();
    } catch (err) {
      onErreur(messageErreur(err, defaut));
    } finally {
      setEnCours(false);
    }
  };

  const valider = (e) => executer(() => api.post(`${source.url}${e.id}/valider/`), `« ${e.titre} » est validé et publié.`, 'Erreur lors de la validation.');

  const refuser = (e) => executer(async () => {
    await api.post(`${source.url}${e.id}/refuser/`, { motif: refus.motif });
    setRefus({ id: null, motif: '' });
  }, `« ${e.titre} » est renvoyé à son auteur.`, 'Erreur lors du refus.');

  const plus = async () => {
    try {
      const res = await api.get(suivant);
      setItems((l) => [...l, ...res.data.results]);
      setSuivant(res.data.next);
    } catch (err) {
      onErreur(messageErreur(err, source.erreur));
    }
  };

  return (
    <>
      <h2>{source.titre} en attente de validation</h2>
      <div className="table-container" style={{ marginBottom: '24px' }}>
        {loading ? <div className="loading">Chargement...</div> : items.length === 0 ? (
          <div className="empty-state"><p>{source.vide}</p></div>
        ) : (
          <>
            <table className="data-table">
              <thead><tr><th>{source.colonneTitre}</th><th>Auteur</th><th>Soumis le</th><th>{source.colonne}</th><th>Cible</th><th>Actions</th></tr></thead>
              <tbody>
                {items.map((e) => (
                  <Fragment key={e.id}>
                    <tr>
                      <td><strong>{e.titre}</strong>{source.sousTitre(e) && <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>{source.sousTitre(e)}</div>}</td>
                      <td>{e.cree_par_nom || '-'}</td>
                      <td>{formatDate(e.soumis_le)}</td>
                      <td>{source.contenu(e)}</td>
                      <td>{source.nbCibles(e) > 0 ? resumeCibles(e.classes_detail.length, e.groupes_detail.length, e.etudiants_detail.length) : 'Non affecté'}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <button type="button" className="btn btn-sm btn-outline" style={{ marginRight: '6px' }} onClick={() => setOuvert(ouvert === e.id ? null : e.id)}>{ouvert === e.id ? 'Masquer' : 'Aperçu'}</button>
                        <button type="button" className="btn btn-sm btn-primary" style={{ marginRight: '6px' }} disabled={enCours} onClick={() => valider(e)}>Valider</button>
                        <button type="button" className="btn btn-sm btn-danger" onClick={() => setRefus({ id: e.id, motif: '' })}>Refuser</button>
                      </td>
                    </tr>
                    {ouvert === e.id && <tr><td colSpan={6}>{source.apercu(e)}</td></tr>}
                    {refus.id === e.id && (
                      <tr>
                        <td colSpan={6}>
                          <div className="form-group" style={{ margin: '4px 0' }}>
                            <label>Motif du refus (envoyé à l'auteur)</label>
                            <textarea rows={2} maxLength={2000} value={refus.motif} onChange={(ev) => setRefus({ id: e.id, motif: ev.target.value })} />
                          </div>
                          <div style={{ display: 'flex', gap: '6px' }}>
                            <button type="button" className="btn btn-sm btn-danger" disabled={enCours || !refus.motif.trim()} onClick={() => refuser(e)}>Confirmer le refus</button>
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
    </>
  );
}

const ONGLETS = [['quiz', 'Quiz'], ['devoir', 'Devoirs']];

export default function ValidationQuiz() {
  const { user } = useAuth();
  const peutRegler = user?.role === 'admin';
  const [etablissement, setEtablissement] = useState(null);
  const [onglet, setOnglet] = useState('quiz');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (user?.role !== 'superadmin') {
      api.get('/referentiel/etablissements/')
        .then((res) => setEtablissement((res.data.results || res.data)[0] || null))
        .catch((err) => setError(messageErreur(err, "Erreur lors du chargement de l'établissement.")));
    }
  }, [user?.role]);

  const basculerReglage = async () => {
    setError('');
    setMessage('');
    try {
      const res = await api.patch(`/referentiel/etablissements/${etablissement.id}/parametres/`, { validation_quiz_requise: !etablissement.validation_quiz_requise });
      setEtablissement(res.data);
      setMessage('Réglage enregistré.');
    } catch (err) {
      setError(messageErreur(err, "Erreur lors de l'enregistrement du réglage."));
    }
  };

  const changerOnglet = (cle) => { setOnglet(cle); setError(''); setMessage(''); };

  return (
    <div>
      <div className="page-header">
        <h1>Validation des évaluations</h1>
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-success">{message}</div>}

      {etablissement && (
        <div className="table-container" style={{ padding: '16px', marginBottom: '16px' }}>
          <strong>Réglage de l'établissement :</strong>{' '}
          {etablissement.validation_quiz_requise
            ? 'les quiz et les devoirs des enseignants doivent être validés avant publication.'
            : 'les enseignants publient leurs quiz et leurs devoirs directement.'}
          {peutRegler && (
            <div style={{ marginTop: '8px' }}>
              <button type="button" className="btn btn-sm btn-secondary" onClick={basculerReglage}>
                {etablissement.validation_quiz_requise ? 'Ne plus exiger de validation' : 'Exiger une validation avant publication'}
              </button>
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        {ONGLETS.map(([cle, libelle]) => (
          <button key={cle} type="button" className={`btn btn-sm ${onglet === cle ? 'btn-primary' : 'btn-secondary'}`} onClick={() => changerOnglet(cle)}>{libelle}</button>
        ))}
      </div>
      <FileAttente key={onglet} type={onglet} onMessage={setMessage} onErreur={setError} />
    </div>
  );
}
