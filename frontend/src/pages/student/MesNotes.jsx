import { useState, useEffect } from 'react';
import api from '../../services/api';

export default function MesNotes() {
  const [notes, setNotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => { fetchNotes(); }, []);

  const fetchNotes = async () => {
    setLoading(true);
    try {
      const res = await api.get('/programming/notes/mes_notes/');
      setNotes(res.data);
    } catch (err) {
      setError('Erreur lors du chargement des notes.');
    } finally {
      setLoading(false);
    }
  };

  const grouped = notes.reduce((acc, n) => {
    const key = n.ec_libelle;
    if (!acc[key]) acc[key] = [];
    acc[key].push(n);
    return acc;
  }, {});

  return (
    <div>
      <div className="page-header">
        <h1>Mes notes</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <div className="loading">Chargement...</div>
      ) : notes.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📊</div>
          <h3>Aucune note disponible</h3>
          <p>Vos notes apparaîtront ici une fois que vos enseignants les auront publiées.</p>
        </div>
      ) : (
        <>
          <div className="dashboard-grid" style={{ marginBottom: '32px' }}>
            <div className="stat-card">
              <div className="stat-number">
                {notes.length > 0 ? (notes.reduce((s, n) => s + (n.moyenne || 0), 0) / notes.length).toFixed(1) : '-'}
              </div>
              <div className="stat-label">Moyenne générale</div>
            </div>
            <div className="stat-card">
              <div className="stat-number">
                {notes.filter(n => n.note_devoir_manuelle !== null).length > 0
                  ? (notes.filter(n => n.note_devoir_manuelle !== null).reduce((s, n) => s + n.note_devoir_manuelle, 0) / notes.filter(n => n.note_devoir_manuelle !== null).length).toFixed(1)
                  : '-'}
              </div>
              <div className="stat-label">Moy. Devoirs (manuelle)</div>
            </div>
            <div className="stat-card">
              <div className="stat-number">
                {notes.filter(n => n.note_devoir_prog !== null).length > 0
                  ? (notes.filter(n => n.note_devoir_prog !== null).reduce((s, n) => s + n.note_devoir_prog, 0) / notes.filter(n => n.note_devoir_prog !== null).length).toFixed(1)
                  : '-'}
              </div>
              <div className="stat-label">Moy. Devoirs (prog)</div>
            </div>
            <div className="stat-card">
              <div className="stat-number">
                {notes.filter(n => n.note_examen !== null).length > 0
                  ? (notes.filter(n => n.note_examen !== null).reduce((s, n) => s + n.note_examen, 0) / notes.filter(n => n.note_examen !== null).length).toFixed(1)
                  : '-'}
              </div>
              <div className="stat-label">Moy. Examens</div>
            </div>
          </div>

          {Object.entries(grouped).map(([matiere, matiereNotes]) => (
            <div key={matiere} className="form-card" style={{ marginBottom: '16px' }}>
              <h3 style={{ marginBottom: '12px' }}>{matiere}</h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Classe</th>
                    <th>Année</th>
                    <th>Devoir (manuelle)</th>
                    <th>Devoir (prog)</th>
                    <th>Examen</th>
                    <th>Moyenne</th>
                  </tr>
                </thead>
                <tbody>
                  {matiereNotes.map((n) => (
                    <tr key={n.id}>
                      <td>{n.classe_libelle}</td>
                      <td>{n.annee_libelle}</td>
                      <td>
                        {n.note_devoir_manuelle !== null ? (
                          <strong>{n.note_devoir_manuelle.toFixed(1)}/20</strong>
                        ) : (
                          <span style={{ color: 'var(--gray-400)' }}>—</span>
                        )}
                      </td>
                      <td>
                        {n.note_devoir_prog !== null ? (
                          <span className="badge badge-active">{n.note_devoir_prog.toFixed(1)}/20</span>
                        ) : (
                          <span style={{ color: 'var(--gray-400)' }}>—</span>
                        )}
                      </td>
                      <td>
                        {n.note_examen !== null ? (
                          <strong>{n.note_examen.toFixed(1)}/20</strong>
                        ) : (
                          <span style={{ color: 'var(--gray-400)' }}>—</span>
                        )}
                      </td>
                      <td>
                        {n.moyenne !== null ? (
                          <strong style={{
                            color: n.moyenne >= 10 ? 'var(--success, #22c55e)' : 'var(--danger, #ef4444)',
                            fontSize: '1.1rem'
                          }}>
                            {n.moyenne.toFixed(1)}/20
                          </strong>
                        ) : (
                          <span style={{ color: 'var(--gray-400)' }}>—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
