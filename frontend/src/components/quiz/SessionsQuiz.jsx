import { useCallback, useEffect, useState } from 'react';
import api from '../../services/api';
import { chargerTout } from '../../services/pagination';
import { messageErreur } from '../../services/erreurs';

const formatDate = (iso) => new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
const versIso = (local) => (local ? new Date(local).toISOString() : null);
const formulaireVide = { libelle: '', ouverture: '', fermeture: '', periode: '', classes: [], groupes: [], etudiants: [], tentatives_supplementaires: 1 };
const styleLigne = { display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'normal', margin: '2px 0' };

// Routes et textes propres au type d'évaluation ('quiz' ou 'devoir'). Les devoirs n'ont pas de tentatives :
// le rattrapage rouvre la fenêtre et les candidats sont les étudiants sans soumission.
const TYPES = {
  quiz: {
    nom: 'quiz', champ: 'quiz', sessions: '/quiz/sessions-quiz/', tentatives: true,
    candidats: (id) => `/quiz/quizzes/${id}/candidats_rattrapage/`,
  },
  devoir: {
    nom: 'devoir', champ: 'devoir', sessions: '/programming/sessions-devoir/', tentatives: false,
    candidats: (id) => `/programming/devoirs/${id}/candidats_rattrapage/`,
  },
};

function cibles(s, avecTentatives) {
  if (s.type === 'rattrapage') {
    const etudiants = `${s.nb_etudiants} étudiant${s.nb_etudiants > 1 ? 's' : ''}`;
    if (!avecTentatives) return etudiants;
    return `${etudiants}, +${s.tentatives_supplementaires} tentative${s.tentatives_supplementaires > 1 ? 's' : ''}`;
  }
  return [...s.classes_detail.map((c) => c.code), ...s.groupes_detail.map((g) => g.libelle)].join(', ');
}

export default function SessionsQuiz({ evaluation, type = 'quiz' }) {
  const t = TYPES[type] || TYPES.quiz;
  const [sessions, setSessions] = useState([]);
  const [groupes, setGroupes] = useState([]);
  const [periodes, setPeriodes] = useState([]);
  const [mode, setMode] = useState(null);
  const [form, setForm] = useState(formulaireVide);
  const [seuil, setSeuil] = useState(50);
  const [candidats, setCandidats] = useState([]);
  const [candidatsCharges, setCandidatsCharges] = useState(false);
  const [erreur, setErreur] = useState('');
  const [message, setMessage] = useState('');

  const charger = useCallback(async () => {
    try {
      setSessions(await chargerTout(t.sessions, { [t.champ]: evaluation.id }));
    } catch (err) {
      setErreur(messageErreur(err, 'Erreur lors du chargement des sessions.'));
    }
  }, [evaluation.id, t.sessions, t.champ]);

  useEffect(() => {
    charger();
    const classes = new Set((evaluation.classes_detail || []).map((c) => c.id));
    const affectes = new Set((evaluation.groupes_detail || []).map((g) => g.id));
    Promise.all([chargerTout('/referentiel/groupes/'), chargerTout('/referentiel/periodes-evaluation/')])
      .then(([g, p]) => { setGroupes(g.filter((x) => classes.has(x.classe) || affectes.has(x.id))); setPeriodes(p); })
      .catch((err) => setErreur(messageErreur(err, 'Erreur lors du chargement des groupes et des périodes.')));
  }, [charger, evaluation.classes_detail, evaluation.groupes_detail]);

  const ouvrir = (nouveauMode) => { setMode(nouveauMode); setForm(formulaireVide); setCandidats([]); setCandidatsCharges(false); setErreur(''); setMessage(''); };
  const basculer = (cle, id) => setForm((f) => ({ ...f, [cle]: f[cle].includes(id) ? f[cle].filter((x) => x !== id) : [...f[cle], id] }));

  const proposer = async () => {
    setErreur('');
    try {
      const res = await api.get(t.candidats(evaluation.id), t.tentatives ? { params: { seuil } } : undefined);
      setCandidats(res.data);
      setCandidatsCharges(true);
      setForm((f) => ({ ...f, etudiants: res.data.map((c) => c.id) }));
    } catch (err) {
      setErreur(messageErreur(err, 'Erreur lors du calcul des candidats.'));
    }
  };

  const enregistrer = async () => {
    setErreur('');
    const corps = {
      [t.champ]: evaluation.id, type: mode, libelle: form.libelle, ouverture: versIso(form.ouverture), fermeture: versIso(form.fermeture),
      periode: form.periode || null,
      ...(mode === 'rattrapage'
        ? { etudiants: form.etudiants, ...(t.tentatives ? { tentatives_supplementaires: Number(form.tentatives_supplementaires) } : {}) }
        : { classes: form.classes, groupes: form.groupes }),
    };
    try {
      await api.post(t.sessions, corps);
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
      await api.delete(`${t.sessions}${s.id}/`);
      charger();
    } catch (err) {
      setErreur(messageErreur(err, 'Erreur lors de la suppression.'));
    }
  };

  return (
    // Rendu dans le formulaire de l'évaluation : Entrée ne doit pas l'enregistrer depuis un champ de session.
    <div onKeyDown={(e) => { if (e.key === 'Enter') e.preventDefault(); }}>
      <h3 style={{ margin: '0 0 8px' }}>Sessions</h3>
      <p style={{ fontSize: '0.85rem', color: 'var(--gray-500)', margin: '0 0 12px' }}>
        Sans session, les dates générales du {t.nom} s'appliquent. Une session donne des dates propres à des classes ou groupes affectés ; un rattrapage rouvre le {t.nom} pour des étudiants choisis.
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
                <td>{cibles(s, t.tentatives)}</td>
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
                {(evaluation.classes_detail || []).length === 0 ? <p style={{ color: 'var(--gray-500)' }}>Aucune classe affectée.</p> : evaluation.classes_detail.map((c) => (
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
              {t.tentatives ? (
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
              ) : (
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                  <button type="button" className="btn btn-sm btn-secondary" onClick={proposer}>Proposer les étudiants sans soumission</button>
                  {candidatsCharges && candidats.length === 0 && <span style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>Tous les étudiants concernés ont soumis ce devoir.</span>}
                </div>
              )}
              {candidats.length > 0 && (
                <div style={{ maxHeight: '200px', overflowY: 'auto', border: '1px solid var(--gray-200)', borderRadius: '6px', padding: '8px', marginTop: '8px' }}>
                  {candidats.map((c) => (
                    <label key={c.id} style={styleLigne}>
                      <input type="checkbox" style={{ width: 'auto' }} checked={form.etudiants.includes(c.id)} onChange={() => basculer('etudiants', c.id)} />
                      {t.tentatives ? `${c.nom} (${c.meilleure_pourcentage == null ? 'rien soumis' : `${Number(c.meilleure_pourcentage)} %`})` : c.nom}
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
