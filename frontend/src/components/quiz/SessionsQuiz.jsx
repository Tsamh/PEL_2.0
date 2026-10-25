import { useCallback, useEffect, useState } from 'react';
import api from '../../services/api';
import { chargerTout } from '../../services/pagination';
import { messageErreur } from '../../services/erreurs';

const formatDate = (iso) => new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
const versIso = (local) => (local ? new Date(local).toISOString() : null);
const formulaireVide = { libelle: '', ouverture: '', fermeture: '', periode: '', classes: [], groupes: [], etudiants: [], tentatives_supplementaires: 1 };
const styleLigne = { display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'normal', margin: '2px 0' };

function cibles(s) {
  if (s.type === 'rattrapage') return `${s.nb_etudiants} étudiant${s.nb_etudiants > 1 ? 's' : ''}, +${s.tentatives_supplementaires} tentative${s.tentatives_supplementaires > 1 ? 's' : ''}`;
  return [...s.classes_detail.map((c) => c.code), ...s.groupes_detail.map((g) => g.libelle)].join(', ');
}

export default function SessionsQuiz({ quiz }) {
  const [sessions, setSessions] = useState([]);
  const [groupes, setGroupes] = useState([]);
  const [periodes, setPeriodes] = useState([]);
  const [mode, setMode] = useState(null);
  const [form, setForm] = useState(formulaireVide);
  const [seuil, setSeuil] = useState(50);
  const [candidats, setCandidats] = useState([]);
  const [erreur, setErreur] = useState('');
  const [message, setMessage] = useState('');

  const charger = useCallback(async () => {
    try {
      setSessions(await chargerTout('/quiz/sessions-quiz/', { quiz: quiz.id }));
    } catch (err) {
      setErreur(messageErreur(err, 'Erreur lors du chargement des sessions.'));
    }
  }, [quiz.id]);

  useEffect(() => {
    charger();
    const classes = new Set((quiz.classes_detail || []).map((c) => c.id));
    const affectes = new Set((quiz.groupes_detail || []).map((g) => g.id));
    Promise.all([chargerTout('/referentiel/groupes/'), chargerTout('/referentiel/periodes-evaluation/')])
      .then(([g, p]) => { setGroupes(g.filter((x) => classes.has(x.classe) || affectes.has(x.id))); setPeriodes(p); })
      .catch((err) => setErreur(messageErreur(err, 'Erreur lors du chargement des groupes et des périodes.')));
  }, [charger, quiz.classes_detail, quiz.groupes_detail]);

  const ouvrir = (nouveauMode) => { setMode(nouveauMode); setForm(formulaireVide); setCandidats([]); setErreur(''); setMessage(''); };
  const basculer = (cle, id) => setForm((f) => ({ ...f, [cle]: f[cle].includes(id) ? f[cle].filter((x) => x !== id) : [...f[cle], id] }));

  const proposer = async () => {
    setErreur('');
    try {
      const res = await api.get(`/quiz/quizzes/${quiz.id}/candidats_rattrapage/`, { params: { seuil } });
      setCandidats(res.data);
      setForm((f) => ({ ...f, etudiants: res.data.map((c) => c.id) }));
    } catch (err) {
      setErreur(messageErreur(err, 'Erreur lors du calcul des candidats.'));
    }
  };

  const enregistrer = async () => {
    setErreur('');
    const corps = {
      quiz: quiz.id, type: mode, libelle: form.libelle, ouverture: versIso(form.ouverture), fermeture: versIso(form.fermeture),
      periode: form.periode || null,
      ...(mode === 'rattrapage'
        ? { etudiants: form.etudiants, tentatives_supplementaires: Number(form.tentatives_supplementaires) }
        : { classes: form.classes, groupes: form.groupes }),
    };
    try {
      await api.post('/quiz/sessions-quiz/', corps);
      setMode(null);
      setMessage(mode === 'rattrapage' ? 'Rattrapage planifié.' : 'Session planifiée.');
      charger();
    } catch (err) {
      setErreur(messageErreur(err, "Erreur lors de l'enregistrement de la session."));
    }
  };

  const supprimer = async (s) => {
    if (!window.confirm('Supprimer cette session ?')) return;
    try {
      await api.delete(`/quiz/sessions-quiz/${s.id}/`);
      charger();
    } catch (err) {
      setErreur(messageErreur(err, 'Erreur lors de la suppression.'));
    }
  };

  return (
    // Rendu dans le formulaire du quiz : Entrée ne doit pas enregistrer le quiz depuis un champ de session.
    <div onKeyDown={(e) => { if (e.key === 'Enter') e.preventDefault(); }}>
      <h3 style={{ margin: '0 0 8px' }}>Sessions</h3>
      <p style={{ fontSize: '0.85rem', color: 'var(--gray-500)', margin: '0 0 12px' }}>
        Sans session, les dates générales du quiz s'appliquent. Une session donne des dates propres à des classes ou groupes affectés ; un rattrapage rouvre le quiz pour des étudiants choisis.
      </p>
      {erreur && <div className="alert alert-error">{erreur}</div>}
      {message && <div className="alert alert-success">{message}</div>}
      {sessions.length > 0 && (
        <table className="data-table" style={{ marginBottom: '8px' }}>
          <thead><tr><th>Type</th><th>Libellé</th><th>Ouverture</th><th>Fermeture</th><th>Cibles</th><th></th></tr></thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id}>
                <td>{s.type === 'rattrapage' ? <span className="badge badge-pending">Rattrapage</span> : <span className="badge badge-active">Session</span>}</td>
                <td>{s.libelle || '-'}</td>
                <td>{formatDate(s.ouverture)}</td>
                <td>{formatDate(s.fermeture)}</td>
                <td>{cibles(s)}</td>
                <td><button type="button" className="btn btn-sm btn-danger" onClick={() => supprimer(s)}>Supprimer</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {!mode && (
        <div style={{ display: 'flex', gap: '8px' }}>
          <button type="button" className="btn btn-sm btn-secondary" onClick={() => ouvrir('normale')}>+ Session</button>
          <button type="button" className="btn btn-sm btn-secondary" onClick={() => ouvrir('rattrapage')}>+ Rattrapage</button>
        </div>
      )}
      {mode && (
        <div style={{ border: '1px solid var(--gray-200)', borderRadius: '8px', padding: '12px' }}>
          <div className="form-row">
            <div className="form-group">
              <label>Libellé</label>
              <input value={form.libelle} onChange={(e) => setForm({ ...form, libelle: e.target.value })} placeholder={mode === 'rattrapage' ? 'Rattrapage' : 'Par exemple : TD1, lundi'} />
            </div>
            <div className="form-group">
              <label>Période</label>
              <select value={form.periode} onChange={(e) => setForm({ ...form, periode: e.target.value })}>
                <option value="">-- Aucune --</option>
                {periodes.map((p) => <option key={p.id} value={p.id}>{p.semestre_libelle} : {p.libelle}</option>)}
              </select>
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Ouverture</label>
              <input type="datetime-local" value={form.ouverture} onChange={(e) => setForm({ ...form, ouverture: e.target.value })} />
            </div>
            <div className="form-group">
              <label>Fermeture</label>
              <input type="datetime-local" value={form.fermeture} onChange={(e) => setForm({ ...form, fermeture: e.target.value })} />
            </div>
          </div>
          {mode === 'normale' ? (
            <div className="form-row">
              <div className="form-group">
                <label>Classes</label>
                {(quiz.classes_detail || []).length === 0 ? <p style={{ color: 'var(--gray-500)' }}>Aucune classe affectée.</p> : quiz.classes_detail.map((c) => (
                  <label key={c.id} style={styleLigne}><input type="checkbox" style={{ width: 'auto' }} checked={form.classes.includes(c.id)} onChange={() => basculer('classes', c.id)} />{c.code} - {c.libelle}</label>
                ))}
              </div>
              <div className="form-group">
                <label>Groupes</label>
                {groupes.length === 0 ? <p style={{ color: 'var(--gray-500)' }}>Aucun groupe.</p> : groupes.map((g) => (
                  <label key={g.id} style={styleLigne}><input type="checkbox" style={{ width: 'auto' }} checked={form.groupes.includes(g.id)} onChange={() => basculer('groupes', g.id)} />{g.libelle}</label>
                ))}
              </div>
            </div>
          ) : (
            <div>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
                <div className="form-group" style={{ margin: 0 }}>
                  <label>Seuil (note en %)</label>
                  <input type="number" min="0" max="100" value={seuil} onChange={(e) => setSeuil(e.target.value)} style={{ width: '100px' }} />
                </div>
                <button type="button" className="btn btn-sm btn-secondary" onClick={proposer}>Proposer les absents et les notes sous le seuil</button>
                <div className="form-group" style={{ margin: 0 }}>
                  <label>Tentatives en plus</label>
                  <input type="number" min="0" max="10" value={form.tentatives_supplementaires} onChange={(e) => setForm({ ...form, tentatives_supplementaires: e.target.value })} style={{ width: '100px' }} />
                </div>
              </div>
              {candidats.length > 0 && (
                <div style={{ maxHeight: '200px', overflowY: 'auto', border: '1px solid var(--gray-200)', borderRadius: '6px', padding: '8px', marginTop: '8px' }}>
                  {candidats.map((c) => (
                    <label key={c.id} style={styleLigne}>
                      <input type="checkbox" style={{ width: 'auto' }} checked={form.etudiants.includes(c.id)} onChange={() => basculer('etudiants', c.id)} />
                      {c.nom} ({c.meilleure_pourcentage == null ? 'rien soumis' : `${Number(c.meilleure_pourcentage)} %`})
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}
          <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
            <button type="button" className="btn btn-sm btn-primary" onClick={enregistrer}>Enregistrer</button>
            <button type="button" className="btn btn-sm btn-secondary" onClick={() => setMode(null)}>Annuler</button>
          </div>
        </div>
      )}
    </div>
  );
}
