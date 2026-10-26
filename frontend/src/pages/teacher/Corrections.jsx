import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import { chargerTout } from '../../services/pagination';
import CodeEditor from '../../components/CodeEditor';
import { LANGAGES } from '../../components/devoirs/exercices';

export default function Corrections() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [devoir, setDevoir] = useState(null);
  const [soumissions, setSoumissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [score, setScore] = useState('');
  const [commentaire, setCommentaire] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [devoirRes, liste] = await Promise.all([
          api.get(`/programming/devoirs/${id}/`),
          chargerTout('/programming/soumissions/', { devoir: id }),
        ]);
        setDevoir(devoirRes.data);
        setSoumissions(liste);
      } catch (err) {
        setError(messageErreur(err, 'Erreur lors du chargement.'));
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  const openCorrection = (sub) => {
    setSelected(sub);
    setScore(sub.score !== null && sub.score !== undefined ? sub.score.toString() : '');
    setCommentaire(sub.commentaire || '');
    setMessage('');
    setError('');
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage('');
    setError('');
    try {
      const res = await api.post(`/programming/soumissions/${selected.id}/corriger/`, {
        score: score !== '' ? parseInt(score) : null,
        commentaire,
      });
      setSoumissions((prev) => prev.map((s) => s.id === selected.id ? { ...s, ...res.data } : s));
      setMessage('Correction enregistrée !');
      setSelected(null);
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors de la sauvegarde.'));
    } finally {
      setSaving(false);
    }
  };

  const stats = {
    total: soumissions.length,
    corrigees: soumissions.filter((s) => s.statut === 'corrige').length,
    enAttente: soumissions.filter((s) => s.statut === 'soumis').length,
  };

  // La note est un entier compris entre 0 et la partie entière du barème.
  const noteMax = Math.floor(Number(devoir?.bareme) || 0);
  const exercices = devoir?.exercices || [];
  const reponsesDe = (sub) => Object.fromEntries((sub.reponses || []).map((r) => [r.exercice, r]));

  if (loading) return <div className="loading">Chargement...</div>;

  return (
    <div>
      <div className="page-header">
        <div>
          <button className="btn btn-secondary" onClick={() => navigate(-1)} style={{ marginBottom: '8px' }}>← Retour</button>
          <h1>Corrections : {devoir?.titre}</h1>
        </div>
        <div>
          <span className="badge badge-active">{devoir?.langage_display || LANGAGES[devoir?.langage] || devoir?.langage}</span>
          <span style={{ marginLeft: '12px', color: 'var(--gray-500)' }}>Barème : {Number(devoir?.bareme)} pts, {exercices.length} exercice{exercices.length > 1 ? 's' : ''}</span>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-success">{message}</div>}

      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px' }}>
        <div className="form-card" style={{ flex: 1, textAlign: 'center' }}>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--primary)' }}>{stats.total}</div>
          <div style={{ color: 'var(--gray-500)' }}>Soumissions</div>
        </div>
        <div className="form-card" style={{ flex: 1, textAlign: 'center' }}>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--success)' }}>{stats.corrigees}</div>
          <div style={{ color: 'var(--gray-500)' }}>Corrigées</div>
        </div>
        <div className="form-card" style={{ flex: 1, textAlign: 'center' }}>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--warning, #f59e0b)' }}>{stats.enAttente}</div>
          <div style={{ color: 'var(--gray-500)' }}>En attente</div>
        </div>
      </div>

      <div className="table-container">
        {soumissions.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📋</div>
            <h3>Aucune soumission</h3>
            <p>Les étudiants n'ont pas encore soumis ce devoir.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Étudiant</th><th>Date</th><th>Score</th><th>Statut</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {soumissions.map((sub) => (
                <tr key={sub.id}>
                  <td><strong>{sub.etudiant_nom}</strong></td>
                  <td>{new Date(sub.date_soumission).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                  <td>{sub.score !== null && sub.score !== undefined ? <strong>{sub.score} / {noteMax}</strong> : '-'}</td>
                  <td>
                    {sub.statut === 'corrige' ? (
                      <span className="badge badge-active">Corrigé</span>
                    ) : (
                      <span className="badge badge-inactive">En attente</span>
                    )}
                  </td>
                  <td>
                    <button className="btn btn-sm btn-primary" onClick={() => openCorrection(sub)}>
                      {sub.statut === 'corrige' ? 'Revoir' : 'Corriger'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '900px' }}>
            <div className="modal-header">
              <h3>Correction : {selected.etudiant_nom}</h3>
              <button className="close-btn" onClick={() => setSelected(null)}>×</button>
            </div>
            <div className="modal-body">
              {error && <div className="alert alert-error">{error}</div>}
              {exercices.map((ex, i) => {
                const reponse = reponsesDe(selected)[ex.id];
                return (
                  <div key={ex.id} style={{ marginBottom: '16px' }}>
                    <label style={{ fontWeight: 600, display: 'block', marginBottom: '8px' }}>
                      Exercice {i + 1} : {ex.titre} <span style={{ fontWeight: 'normal', color: 'var(--gray-500)' }}>({Number(ex.points)} pt{Number(ex.points) > 1 ? 's' : ''})</span>
                    </label>
                    {!reponse || reponse.fichiers.length === 0 ? (
                      <p style={{ color: 'var(--gray-500)', fontSize: '0.9rem' }}>Aucune réponse rendue pour cet exercice.</p>
                    ) : reponse.fichiers.map((f, j) => (
                      <div key={j} style={{ marginBottom: '8px' }}>
                        <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)', marginBottom: '4px' }}>{f.nom}</div>
                        <CodeEditor language={devoir?.langage} value={f.contenu} readOnly height="250px" />
                      </div>
                    ))}
                  </div>
                );
              })}
              <div className="form-row">
                <div className="form-group" style={{ flex: '0 0 150px' }}>
                  <label>Note / {noteMax}</label>
                  <input
                    type="number"
                    min="0"
                    max={noteMax}
                    step="1"
                    value={score}
                    onChange={(e) => setScore(e.target.value)}
                    placeholder="0"
                  />
                </div>
                <div className="form-group" style={{ flex: 1 }}>
                  <label>Remarques</label>
                  <textarea
                    value={commentaire}
                    onChange={(e) => setCommentaire(e.target.value)}
                    rows={3}
                    placeholder="Remarques pour l'étudiant (style, logique, optimisation...)..."
                  />
                </div>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setSelected(null)}>Annuler</button>
              <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
                {saving ? 'Enregistrement...' : 'Enregistrer'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
