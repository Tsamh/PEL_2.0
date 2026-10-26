import { useCallback, useEffect, useState } from 'react';
import api from '../services/api';
import { chargerTout } from '../services/pagination';
import { messageErreur } from '../services/erreurs';

const TYPES = { controle_continu: 'Contrôle continu', examen: 'Examen', rattrapage: 'Rattrapage' };
const semestreVide = { libelle: '', date_debut: '', date_fin: '' };
const periodeVide = { libelle: '', type: 'controle_continu', date_debut: '', date_fin: '' };
const formatDate = (d) => (d ? new Date(`${d}T00:00:00`).toLocaleDateString('fr-FR') : '');

function ChampsDates({ valeur, onChange, avecType }) {
  return (
    <>
      <div className="form-group" style={{ margin: 0 }}>
        <label>Libellé</label>
        <input value={valeur.libelle} onChange={(e) => onChange({ ...valeur, libelle: e.target.value })} required />
      </div>
      {avecType && (
        <div className="form-group" style={{ margin: 0 }}>
          <label>Type</label>
          <select value={valeur.type} onChange={(e) => onChange({ ...valeur, type: e.target.value })}>
            {Object.entries(TYPES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
      )}
      <div className="form-group" style={{ margin: 0 }}>
        <label>Début</label>
        <input type="date" value={valeur.date_debut} onChange={(e) => onChange({ ...valeur, date_debut: e.target.value })} required />
      </div>
      <div className="form-group" style={{ margin: 0 }}>
        <label>Fin</label>
        <input type="date" value={valeur.date_fin} onChange={(e) => onChange({ ...valeur, date_fin: e.target.value })} required />
      </div>
    </>
  );
}

export default function Calendrier() {
  const [annees, setAnnees] = useState([]);
  const [anneeId, setAnneeId] = useState('');
  const [semestres, setSemestres] = useState([]);
  const [periodes, setPeriodes] = useState([]);
  const [nouveauSemestre, setNouveauSemestre] = useState(semestreVide);
  const [nouvellesPeriodes, setNouvellesPeriodes] = useState({});
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    chargerTout('/referentiel/annees-academiques/')
      .then((toutes) => {
        const liste = toutes.filter((a) => !a.archivee);
        setAnnees(liste);
        const active = liste.find((a) => a.est_active) || liste[0];
        if (active) setAnneeId(String(active.id));
      })
      .catch((err) => setError(messageErreur(err, 'Erreur lors du chargement des années académiques.')));
  }, []);

  const charger = useCallback(async () => {
    if (!anneeId) return;
    try {
      const [s, p] = await Promise.all([
        chargerTout('/referentiel/semestres/', { annee_academique: anneeId }),
        chargerTout('/referentiel/periodes-evaluation/', { annee_academique: anneeId }),
      ]);
      setSemestres(s);
      setPeriodes(p);
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors du chargement du calendrier.'));
    }
  }, [anneeId]);

  useEffect(() => { charger(); }, [charger]);

  const executer = async (action, succes, defaut) => {
    setError('');
    setMessage('');
    try {
      await action();
      setMessage(succes);
      await charger();
    } catch (err) {
      setError(messageErreur(err, defaut));
    }
  };

  const ajouterSemestre = (e) => {
    e.preventDefault();
    executer(async () => {
      await api.post('/referentiel/semestres/', { ...nouveauSemestre, annee_academique: Number(anneeId) });
      setNouveauSemestre(semestreVide);
    }, 'Semestre ajouté.', "Erreur lors de l'ajout du semestre.");
  };
  const ajouterPeriode = (e, semestre) => {
    e.preventDefault();
    executer(async () => {
      await api.post('/referentiel/periodes-evaluation/', { ...(nouvellesPeriodes[semestre.id] || periodeVide), semestre: semestre.id });
      setNouvellesPeriodes((n) => ({ ...n, [semestre.id]: periodeVide }));
    }, 'Période ajoutée.', "Erreur lors de l'ajout de la période.");
  };
  const supprimer = (url, texte) => {
    if (!window.confirm(texte)) return;
    executer(() => api.delete(url), 'Suppression effectuée.', 'Erreur lors de la suppression.');
  };

  const annee = annees.find((a) => String(a.id) === anneeId);

  return (
    <div>
      <div className="page-header">
        <h1>Calendrier</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-success">{message}</div>}

      <div className="table-container" style={{ padding: '16px', marginBottom: '16px' }}>
        <div className="form-group" style={{ maxWidth: '320px' }}>
          <label>Année académique</label>
          <select value={anneeId} onChange={(e) => setAnneeId(e.target.value)}>
            {annees.length === 0 && <option value="">Aucune année</option>}
            {annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
          </select>
        </div>
        {annee && <p style={{ color: 'var(--gray-500)', margin: '0 0 12px' }}>Du {formatDate(annee.date_debut)} au {formatDate(annee.date_fin)}.</p>}
        {anneeId && (
          <form onSubmit={ajouterSemestre} style={{ display: 'flex', gap: '8px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <ChampsDates valeur={nouveauSemestre} onChange={setNouveauSemestre} />
            <button type="submit" className="btn btn-primary">Ajouter le semestre</button>
          </form>
        )}
      </div>

      {semestres.length === 0 ? (
        <div className="table-container"><div className="empty-state"><p>Aucun semestre pour cette année.</p></div></div>
      ) : semestres.map((s) => (
        <div key={s.id} className="table-container" style={{ padding: '16px', marginBottom: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px' }}>
            <h3 style={{ margin: 0 }}>{s.libelle} <span style={{ fontWeight: 'normal', color: 'var(--gray-500)', fontSize: '0.9rem' }}>du {formatDate(s.date_debut)} au {formatDate(s.date_fin)}</span></h3>
            <button type="button" className="btn btn-sm btn-danger" onClick={() => supprimer(`/referentiel/semestres/${s.id}/`, `Supprimer le semestre ${s.libelle} et ses périodes ?`)}>Supprimer</button>
          </div>
          <table className="data-table" style={{ margin: '12px 0' }}>
            <thead><tr><th>Période</th><th>Type</th><th>Début</th><th>Fin</th><th></th></tr></thead>
            <tbody>
              {periodes.filter((p) => p.semestre === s.id).map((p) => (
                <tr key={p.id}>
                  <td>{p.libelle}</td>
                  <td>{TYPES[p.type]}</td>
                  <td>{formatDate(p.date_debut)}</td>
                  <td>{formatDate(p.date_fin)}</td>
                  <td><button type="button" className="btn btn-sm btn-danger" onClick={() => supprimer(`/referentiel/periodes-evaluation/${p.id}/`, `Supprimer la période ${p.libelle} ?`)}>Supprimer</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <form onSubmit={(e) => ajouterPeriode(e, s)} style={{ display: 'flex', gap: '8px', alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <ChampsDates avecType valeur={nouvellesPeriodes[s.id] || periodeVide} onChange={(v) => setNouvellesPeriodes((n) => ({ ...n, [s.id]: v }))} />
            <button type="submit" className="btn btn-secondary">Ajouter la période</button>
          </form>
        </div>
      ))}
    </div>
  );
}
