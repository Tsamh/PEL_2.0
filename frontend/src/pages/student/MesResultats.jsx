import { useState, useEffect } from 'react';
import api from '../../services/api';
import CaseArchives from '../../components/CaseArchives';

export default function MesResultats() {
  const [soumissions, setSoumissions] = useState([]);
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('devoirs');
  const [archives, setArchives] = useState(false);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchAll(); }, [archives]);

  const fetchAll = async () => {
    setLoading(true);
    setError('');
    try {
      const config = { params: archives ? { archives: '1' } : {} };
      const [soumRes, notesRes] = await Promise.all([
        api.get('/programming/soumissions/', config),
        api.get('/programming/notes/mes_notes/', config),
      ]);
      setSoumissions(soumRes.data.results || soumRes.data);
      setNotes(notesRes.data);
    } catch (err) {
      setError('Erreur lors du chargement des résultats.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Mes résultats</h1>
      </div>

      <CaseArchives archives={archives} onChange={setArchives} />

      {error && <div className="alert alert-error">{error}</div>}

      <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
        <button
          className={`btn ${tab === 'devoirs' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setTab('devoirs')}
        >
          Devoirs de programmation
        </button>
        <button
          className={`btn ${tab === 'notes' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setTab('notes')}
        >
          Notes par matière
        </button>
      </div>

      {loading ? (
        <div className="loading">Chargement...</div>
      ) : (
        <>
          {tab === 'devoirs' && (
            <div className="table-container">
              {soumissions.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">💻</div>
                  <h3>Aucune soumission</h3>
                  <p>Vous n'avez pas encore soumis de devoir.</p>
                </div>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr><th>Devoir</th><th>Score</th><th>Remarques</th><th>Statut</th><th>Date</th></tr>
                  </thead>
                  <tbody>
                    {soumissions.map((s) => (
                      <tr key={s.id}>
                        <td><strong>{s.devoir_titre}</strong></td>
                        <td>
                          {s.score !== null && s.score !== undefined ? (
                            <strong>{s.score}</strong>
                          ) : '—'}
                        </td>
                        <td>{s.commentaire || '—'}</td>
                        <td>
                          {s.statut === 'corrige' ? (
                            <span className="badge badge-active">Corrigé</span>
                          ) : (
                            <span className="badge badge-inactive">En attente</span>
                          )}
                        </td>
                        <td>{new Date(s.date_soumission).toLocaleDateString('fr-FR')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {tab === 'notes' && (
            <div className="table-container">
              {notes.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">📊</div>
                  <h3>Aucune note</h3>
                  <p>Vos notes apparaîtront ici une fois publiées.</p>
                </div>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Matière</th>
                      <th>Classe</th>
                      <th>Devoir (manuelle)</th>
                      <th>Devoir (prog)</th>
                      <th>Examen</th>
                      <th>Moyenne</th>
                    </tr>
                  </thead>
                  <tbody>
                    {notes.map((n) => (
                      <tr key={n.id}>
                        <td><strong>{n.ec_libelle}</strong></td>
                        <td>{n.classe_libelle}</td>
                        <td>
                          {n.note_devoir_manuelle !== null ? (
                            <strong>{n.note_devoir_manuelle.toFixed(1)}/20</strong>
                          ) : '—'}
                        </td>
                        <td>
                          {n.note_devoir_prog !== null ? (
                            <span className="badge badge-active">{n.note_devoir_prog.toFixed(1)}/20</span>
                          ) : '—'}
                        </td>
                        <td>
                          {n.note_examen !== null ? (
                            <strong>{n.note_examen.toFixed(1)}/20</strong>
                          ) : '—'}
                        </td>
                        <td>
                          {n.moyenne !== null ? (
                            <strong style={{
                              color: n.moyenne >= 10 ? 'var(--success, #22c55e)' : 'var(--danger, #ef4444)',
                              fontSize: '1.05rem'
                            }}>
                              {n.moyenne.toFixed(1)}/20
                            </strong>
                          ) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
