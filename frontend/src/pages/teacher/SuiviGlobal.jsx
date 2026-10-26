import { useEffect, useState } from 'react';
import api from '../../services/api';
import { chargerTout } from '../../services/pagination';
import { messageErreur } from '../../services/erreurs';
import { useAuth } from '../../context/AuthContext';
import CaseArchives from '../../components/CaseArchives';
import Barre from '../../components/stats/Barre';
import { pourcentage } from '../../components/stats/format';

const REGROUPEMENTS = [
  ['classe', 'Classe'], ['filiere', 'Filière'], ['ue', 'UE'], ['ec', 'Matière'], ['cohorte', 'Cohorte'],
];

const FILTRES_VIDES = { annee: '', periode: '', filiere: '', classe: '', ec: '' };

function Indicateurs({ ligne }) {
  return (
    <>
      <td>{ligne.nb_evaluations}</td>
      <td>{ligne.concernes}</td>
      <td><Barre valeur={ligne.taux_participation} libelle={`Participation ${pourcentage(ligne.taux_participation)}`} /></td>
      <td>{ligne.absents}</td>
      <td>{ligne.retards}</td>
      <td>{ligne.en_attente}</td>
      <td>{pourcentage(ligne.moyenne_pourcentage)}</td>
    </>
  );
}

const ENTETES = ['Évaluations', 'Concernés', 'Participation', 'Absents', 'Retards', 'En attente', 'Moyenne'];

export default function SuiviGlobal() {
  const { user } = useAuth();
  const [references, setReferences] = useState({ annees: [], periodes: [], filieres: [], classes: [], ecs: [] });
  const [filtres, setFiltres] = useState(FILTRES_VIDES);
  const [regroupement, setRegroupement] = useState('classe');
  const [synthese, setSynthese] = useState(null);
  const [groupe, setGroupe] = useState(null);
  const [evaluations, setEvaluations] = useState([]);
  const [detail, setDetail] = useState(null);
  const [etablissement, setEtablissement] = useState(null);
  const [delai, setDelai] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [archives, setArchives] = useState(false);
  const paramsArchives = archives ? { archives: '1' } : undefined;

  useEffect(() => {
    Promise.all([
      chargerTout('/referentiel/annees-academiques/'), chargerTout('/referentiel/periodes-evaluation/', paramsArchives),
      chargerTout('/referentiel/filieres/'), chargerTout('/referentiel/classes/', paramsArchives), chargerTout('/referentiel/ecs/'),
    ]).then(([annees, periodes, filieres, classes, ecs]) => setReferences({ annees, periodes, filieres, classes, ecs }))
      .catch((err) => setError(messageErreur(err, 'Erreur lors du chargement des filtres.')));
    if (user?.role === 'admin') {
      api.get('/referentiel/etablissements/')
        .then((res) => {
          const e = (res.data.results || res.data)[0] || null;
          setEtablissement(e);
          setDelai(e ? String(e.delai_retard_minutes) : '');
        })
        .catch((err) => setError(messageErreur(err, "Erreur lors du chargement de l'établissement.")));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, archives]);

  const params = () => {
    const p = { regroupement };
    if (archives) p.archives = '1';
    Object.entries(filtres).forEach(([cle, valeur]) => { if (valeur) p[cle] = valeur; });
    return p;
  };

  useEffect(() => {
    setLoading(true);
    setGroupe(null);
    setDetail(null);
    api.get('/quiz/suivi/', { params: params() })
      .then((res) => { setSynthese(res.data); setError(''); })
      .catch((err) => setError(messageErreur(err, 'Erreur lors du chargement du suivi.')))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtres, regroupement, archives]);

  const ouvrirGroupe = async (g) => {
    try {
      const res = await api.get('/quiz/suivi/evaluations/', { params: { ...params(), groupe: g.cle } });
      setGroupe(g);
      setEvaluations(res.data);
      setDetail(null);
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors du chargement des évaluations.'));
    }
  };

  const ouvrirEvaluation = async (e) => {
    try {
      const p = { quiz: e.quiz };
      if (archives) p.archives = '1';
      if (filtres.classe) p.classe = filtres.classe;
      if (groupe) {
        p.regroupement = regroupement;
        p.groupe = groupe.cle;
      }
      const res = await api.get('/quiz/suivi/absences/', { params: p });
      setDetail(res.data);
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors du chargement des absences.'));
    }
  };

  const enregistrerDelai = async () => {
    try {
      const res = await api.patch(`/referentiel/etablissements/${etablissement.id}/parametres/`,
        { delai_retard_minutes: parseInt(delai, 10) });
      setEtablissement(res.data);
      setMessage('Délai de retard enregistré.');
      setError('');
      setFiltres((f) => ({ ...f }));
    } catch (err) {
      setError(messageErreur(err, "Erreur lors de l'enregistrement du délai."));
    }
  };

  const champ = (cle, libelle, options) => (
    <div className="form-group" style={{ margin: 0 }}>
      <label>{libelle}</label>
      <select value={filtres[cle]} onChange={(e) => setFiltres({ ...filtres, [cle]: e.target.value })}>
        <option value="">Toutes</option>
        {options.map(([id, texte]) => <option key={id} value={id}>{texte}</option>)}
      </select>
    </div>
  );

  return (
    <div>
      <div className="page-header"><h1>Suivi global</h1></div>
      <CaseArchives archives={archives} onChange={(v) => { setArchives(v); setFiltres(FILTRES_VIDES); }} />
      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-success">{message}</div>}

      {etablissement && (
        <div style={{ marginBottom: "16px", padding: "12px", border: "1px solid var(--gray-200)", borderRadius: "8px", display: 'flex', gap: '12px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ margin: 0 }}>
            <label>Délai avant retard (minutes après l'ouverture)</label>
            <input type="number" min="0" max="240" value={delai} onChange={(e) => setDelai(e.target.value)} />
          </div>
          <button type="button" className="btn btn-primary" onClick={enregistrerDelai}
            disabled={delai === '' || String(etablissement.delai_retard_minutes) === delai}>Enregistrer</button>
        </div>
      )}

      <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: '12px' }}>
        <div className="form-group" style={{ margin: 0 }}>
          <label>Regrouper par</label>
          <select value={regroupement} onChange={(e) => setRegroupement(e.target.value)}>
            {REGROUPEMENTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        {champ('annee', 'Année', references.annees.map((a) => [a.id, a.libelle]))}
        {champ('periode', 'Période', references.periodes.map((p) => [p.id, `${p.semestre_libelle} : ${p.libelle}`]))}
        {champ('filiere', 'Filière', references.filieres.map((f) => [f.id, f.libelle]))}
        {champ('classe', 'Classe', references.classes.map((c) => [c.id, c.libelle]))}
        {champ('ec', 'Matière', references.ecs.map((m) => [m.id, m.libelle]))}
      </div>

      <p style={{ fontSize: '0.9rem' }}>
        <button type="button" className="btn btn-sm" onClick={() => { setGroupe(null); setDetail(null); }}>Synthèse</button>
        {groupe && <> / <button type="button" className="btn btn-sm" onClick={() => setDetail(null)}>{groupe.libelle}</button></>}
        {detail && <> / {detail.titre}</>}
      </p>

      <div className="table-container">
        {loading ? <div className="loading">Chargement...</div> : detail ? (
          <div>
            <h3>Absents ({detail.absents.length})</h3>
            {detail.absents.length === 0 ? <p>Aucun absent.</p> : (
              <table className="data-table">
                <thead><tr><th>Étudiant</th><th>Classes</th></tr></thead>
                <tbody>{detail.absents.map((p) => <tr key={p.id}><td>{p.nom}</td><td>{p.classes.join(', ') || '-'}</td></tr>)}</tbody>
              </table>
            )}
            <h3>Retards ({detail.retards.length}, au-delà de {detail.delai_retard_minutes} min)</h3>
            {detail.retards.length === 0 ? <p>Aucun retard.</p> : (
              <table className="data-table">
                <thead><tr><th>Étudiant</th><th>Classes</th><th>Retard</th></tr></thead>
                <tbody>{detail.retards.map((p) => <tr key={p.id}><td>{p.nom}</td><td>{p.classes.join(', ') || '-'}</td><td>{p.minutes} min</td></tr>)}</tbody>
              </table>
            )}
          </div>
        ) : groupe ? (
          evaluations.length === 0 ? <div className="empty-state"><p>Aucune évaluation.</p></div> : (
            <table className="data-table">
              <thead><tr><th>Évaluation</th><th>Période</th><th>Matière</th>{ENTETES.map((t) => <th key={t}>{t}</th>)}</tr></thead>
              <tbody>
                {evaluations.map((e) => (
                  <tr key={e.quiz} style={{ cursor: 'pointer' }} onClick={() => ouvrirEvaluation(e)}>
                    <td>{e.titre}</td><td>{e.periode_libelle || '-'}</td><td>{e.ec_libelle || '-'}</td><Indicateurs ligne={e} />
                  </tr>
                ))}
              </tbody>
            </table>
          )
        ) : !synthese || synthese.groupes.length === 0 ? (
          <div className="empty-state"><p>Aucune évaluation à suivre.</p></div>
        ) : (
          <table className="data-table">
            <thead><tr><th>{REGROUPEMENTS.find(([v]) => v === regroupement)[1]}</th>{ENTETES.map((t) => <th key={t}>{t}</th>)}</tr></thead>
            <tbody>
              {synthese.groupes.map((g) => (
                <tr key={g.cle} style={{ cursor: 'pointer' }} onClick={() => ouvrirGroupe(g)}>
                  <td>{g.libelle}</td><Indicateurs ligne={g} />
                </tr>
              ))}
              <tr style={{ fontWeight: 600 }}><td>Total</td><Indicateurs ligne={synthese.total} /></tr>
            </tbody>
          </table>
        )}
      </div>
      <p style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>
        Participation : copies rendues parmi les étudiants dont la fenêtre est close. En attente : quiz encore ouvert ou à venir pour l'étudiant.
      </p>
    </div>
  );
}
