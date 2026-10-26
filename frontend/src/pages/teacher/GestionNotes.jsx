import { useState, useEffect } from 'react';
import api from '../../services/api';

export default function GestionNotes() {
  const [classes, setClasses] = useState([]);
  const [ecs, setEcs] = useState([]);
  const [annees, setAnnees] = useState([]);
  const [selectedClasse, setSelectedClasse] = useState('');
  const [selectedEC, setSelectedEC] = useState('');
  const [selectedAnnee, setSelectedAnnee] = useState('');
  const [etudiants, setEtudiants] = useState([]);
  const [notes, setNotes] = useState({});
  const [notesProg, setNotesProg] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/referentiel/classes/').then((res) => setClasses(res.data.results || res.data));
    api.get('/referentiel/annees-academiques/').then((res) => setAnnees((res.data.results || res.data).filter((a) => !a.archivee)));
  }, []);

  useEffect(() => {
    if (selectedClasse) {
      setSelectedEC('');
      api.get(`/referentiel/ecs/?classe=${selectedClasse}`).then((res) => setEcs(res.data.results || res.data));
    } else {
      setEcs([]);
      setSelectedEC('');
    }
  }, [selectedClasse]);

  const fetchStudents = async () => {
    if (!selectedClasse || !selectedEC || !selectedAnnee) return;
    setLoading(true);
    setError('');
    try {
      const res = await api.get(`/accounts/users/?role=etudiant&classe=${selectedClasse}`);
      const students = res.data.results || res.data;
      setEtudiants(students);

      const notesRes = await api.get(`/programming/notes/?ec=${selectedEC}&classe=${selectedClasse}&annee_academique=${selectedAnnee}`);
      const existingNotes = notesRes.data.results || notesRes.data;
      const notesMap = {};
      existingNotes.forEach((n) => {
        notesMap[n.etudiant] = {
          id: n.id,
          note_devoir: n.note_devoir !== null ? n.note_devoir.toString() : '',
          note_examen: n.note_examen !== null ? n.note_examen.toString() : '',
        };
      });
      setNotes(notesMap);

      const progRes = await api.get(`/programming/devoirs/?ec=${selectedEC}&classe=${selectedClasse}&annee_academique=${selectedAnnee}`);
      const devoirs = progRes.data.results || progRes.data;

      const soumRes = await api.get(`/programming/soumissions/?devoir_ec=${selectedEC}`);
      const soumissions = soumRes.data.results || soumRes.data;

      const progMap = {};
      for (const etudiant of students) {
        const etudSoums = soumissions.filter((s) =>
          s.etudiant === etudiant.id && s.statut === 'corrige' && s.score !== null
        );
        if (etudSoums.length > 0) {
          let totalNote = 0;
          let count = 0;
          for (const s of etudSoums) {
            const devoir = devoirs.find((d) => d.id === s.devoir);
            if (devoir && devoir.points_max > 0) {
              totalNote += (s.score / devoir.points_max) * 20;
              count++;
            }
          }
          if (count > 0) {
            progMap[etudiant.id] = (totalNote / count).toFixed(1);
          }
        }
      }
      setNotesProg(progMap);
    } catch (err) {
      setError('Erreur lors du chargement.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStudents();
  }, [selectedClasse, selectedEC, selectedAnnee]);

  const updateNote = (etudiantId, field, value) => {
    setNotes((prev) => ({
      ...prev,
      [etudiantId]: {
        ...prev[etudiantId],
        [field]: value,
      },
    }));
  };

  const handleSave = async () => {
    if (!selectedEC || !selectedClasse || !selectedAnnee) {
      setError('Veuillez sélectionner une matière, une classe et une année.');
      return;
    }
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const notesList = etudiants.map((e) => ({
        etudiant: e.id,
        note_devoir: notes[e.id]?.note_devoir ? parseFloat(notes[e.id].note_devoir) : null,
        note_examen: notes[e.id]?.note_examen ? parseFloat(notes[e.id].note_examen) : null,
      }));
      await api.post('/programming/notes/bulk_update/', {
        ec: parseInt(selectedEC),
        classe: parseInt(selectedClasse),
        annee_academique: parseInt(selectedAnnee),
        notes: notesList,
      });
      setMessage('Notes enregistrées avec succès !');
    } catch (err) {
      setError(err.response?.data?.error || 'Erreur lors de la sauvegarde.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Gestion des notes</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-success">{message}</div>}

      <div className="form-card" style={{ marginBottom: '24px' }}>
        <div className="form-row">
          <div className="form-group">
            <label>Classe</label>
            <select value={selectedClasse} onChange={(e) => setSelectedClasse(e.target.value)}>
              <option value="">-- Sélectionner une classe --</option>
              {classes.map((c) => <option key={c.id} value={c.id}>{c.libelle}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label>Matière (EC)</label>
            <select value={selectedEC} onChange={(e) => setSelectedEC(e.target.value)} disabled={!selectedClasse}>
              <option value="">{selectedClasse ? '-- Sélectionner une matière --' : '-- Choisissez d\'abord une classe --'}</option>
              {ecs.map((ec) => <option key={ec.id} value={ec.id}>{ec.libelle}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label>Année académique</label>
            <select value={selectedAnnee} onChange={(e) => setSelectedAnnee(e.target.value)}>
              <option value="">-- Sélectionner --</option>
              {annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
            </select>
          </div>
        </div>
      </div>

      {etudiants.length > 0 && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h2 style={{ margin: 0 }}>Notes des étudiants ({etudiants.length})</h2>
            <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
              {saving ? 'Enregistrement...' : 'Enregistrer les notes'}
            </button>
          </div>

          <div style={{ marginBottom: '12px', padding: '12px', background: 'var(--primary-50, #eff6ff)', borderRadius: '8px', fontSize: '0.9rem', color: 'var(--primary)' }}>
            <strong>Pondération :</strong> Devoir = 40% | Examen = 60% | Moyenne = max(Manuelle, Prog) × 0.4 + Examen × 0.6
          </div>

          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Étudiant</th>
                  <th>Devoir (manuelle)</th>
                  <th>Devoir (prog auto)</th>
                  <th>Examen (/20)</th>
                  <th>Moyenne</th>
                </tr>
              </thead>
              <tbody>
                {etudiants.map((e) => {
                  const n = notes[e.id] || {};
                  const devoir = n.note_devoir ? parseFloat(n.note_devoir) : null;
                  const devoirProg = notesProg[e.id] ? parseFloat(notesProg[e.id]) : null;
                  const examen = n.note_examen ? parseFloat(n.note_examen) : null;

                  let bestDevoir = null;
                  if (devoir !== null && devoirProg !== null) bestDevoir = Math.max(devoir, devoirProg);
                  else if (devoir !== null) bestDevoir = devoir;
                  else if (devoirProg !== null) bestDevoir = devoirProg;

                  let moyenne = null;
                  if (bestDevoir !== null && examen !== null) moyenne = (bestDevoir * 0.4 + examen * 0.6).toFixed(1);
                  else if (bestDevoir !== null) moyenne = (bestDevoir * 0.4).toFixed(1);
                  else if (examen !== null) moyenne = (examen * 0.6).toFixed(1);

                  return (
                    <tr key={e.id}>
                      <td><strong>{e.first_name} {e.last_name}</strong></td>
                      <td>
                        <input
                          type="number"
                          min="0"
                          max="20"
                          step="0.5"
                          value={n.note_devoir || ''}
                          onChange={(ev) => updateNote(e.id, 'note_devoir', ev.target.value)}
                          placeholder="—"
                          style={{ width: '80px' }}
                        />
                      </td>
                      <td>
                        {devoirProg !== null ? (
                          <span className="badge badge-active">{devoirProg}/20</span>
                        ) : (
                          <span style={{ color: 'var(--gray-400)' }}>—</span>
                        )}
                      </td>
                      <td>
                        <input
                          type="number"
                          min="0"
                          max="20"
                          step="0.5"
                          value={n.note_examen || ''}
                          onChange={(ev) => updateNote(e.id, 'note_examen', ev.target.value)}
                          placeholder="—"
                          style={{ width: '80px' }}
                        />
                      </td>
                      <td>
                        {moyenne !== null ? (
                          <strong style={{
                            color: parseFloat(moyenne) >= 10 ? 'var(--success, #22c55e)' : 'var(--danger, #ef4444)',
                            fontSize: '1.05rem'
                          }}>
                            {moyenne}/20
                          </strong>
                        ) : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {etudiants.length === 0 && !loading && selectedClasse && selectedEC && selectedAnnee && (
        <div className="empty-state">
          <div className="empty-icon">👤</div>
          <h3>Aucun étudiant trouvé</h3>
          <p>Aucun étudiant n'est inscrit dans cette classe.</p>
        </div>
      )}
    </div>
  );
}
