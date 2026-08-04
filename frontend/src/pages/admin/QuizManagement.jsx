import { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';

const emptyQuestion = () => ({
  texte: '', type_question: 'qcm', points: 1, ordre: 0,
  choix: [{ texte: '', est_correct: true, ordre: 1 }, { texte: '', est_correct: false, ordre: 2 }],
});

export default function QuizManagement() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [form, setForm] = useState({
    titre: '', description: '', filiere: '', niveau: '', annee_academique: '',
    duree_minutes: 30, date_debut: '', date_fin: '', est_publie: false,
  });
  const [questions, setQuestions] = useState([]);
  const [filieres, setFilieres] = useState([]);
  const [niveaux, setNiveaux] = useState([]);
  const [annees, setAnnees] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchItems();
    api.get('/referentiel/filieres/').then((res) => setFilieres(res.data.results || res.data));
    api.get('/referentiel/niveaux/').then((res) => setNiveaux(res.data.results || res.data));
    api.get('/referentiel/annees-academiques/').then((res) => setAnnees(res.data.results || res.data));
  }, []);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const res = await api.get('/quiz/quizzes/');
      setItems(res.data.results || res.data);
    } catch (err) {
      setError('Erreur lors du chargement.');
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditingItem(null);
    setForm({ titre: '', description: '', filiere: '', niveau: '', annee_academique: '', duree_minutes: 30, date_debut: '', date_fin: '', est_publie: false });
    setQuestions([emptyQuestion()]);
    setShowForm(true);
  };

  const openEdit = (item) => {
    setEditingItem(item);
    setForm({
      titre: item.titre, description: item.description || '',
      filiere: item.filiere || '', niveau: item.niveau || '', annee_academique: item.annee_academique || '',
      duree_minutes: item.duree_minutes, date_debut: item.date_debut || '', date_fin: item.date_fin || '',
      est_publie: item.est_publie,
    });
    const loadedQuestions = (item.questions || []).map((q) => ({
      id: q.id,
      texte: q.texte,
      type_question: q.type_question,
      points: q.points,
      ordre: q.ordre,
      choix: (q.choix || []).map((c) => ({ id: c.id, texte: c.texte, est_correct: c.est_correct, ordre: c.ordre })),
    }));
    setQuestions(loadedQuestions.length > 0 ? loadedQuestions : [emptyQuestion()]);
    setShowForm(true);
  };

  const updateQuestion = (idx, field, value) => {
    const updated = [...questions];
    updated[idx] = { ...updated[idx], [field]: value };
    if (field === 'type_question') {
      if (value === 'vf') {
        updated[idx].choix = [
          { texte: 'Vrai', est_correct: true, ordre: 1 },
          { texte: 'Faux', est_correct: false, ordre: 2 },
        ];
      } else if (value === 'courte') {
        updated[idx].choix = [];
      } else if (updated[idx].choix.length < 2) {
        updated[idx].choix = [
          { texte: '', est_correct: true, ordre: 1 },
          { texte: '', est_correct: false, ordre: 2 },
        ];
      }
    }
    setQuestions(updated);
  };

  const addQuestion = () => setQuestions([...questions, emptyQuestion()]);
  const removeQuestion = (idx) => setQuestions(questions.filter((_, i) => i !== idx));

  const updateChoix = (qIdx, cIdx, field, value) => {
    const updated = [...questions];
    const choix = [...updated[qIdx].choix];
    if (field === 'est_correct') {
      choix.forEach((c, i) => { if (i !== cIdx) c.est_correct = false; });
    }
    choix[cIdx] = { ...choix[cIdx], [field]: value };
    updated[qIdx] = { ...updated[qIdx], choix };
    setQuestions(updated);
  };

  const addChoix = (qIdx) => {
    const updated = [...questions];
    updated[qIdx].choix = [...updated[qIdx].choix, { texte: '', est_correct: false, ordre: updated[qIdx].choix.length + 1 }];
    setQuestions(updated);
  };

  const removeChoix = (qIdx, cIdx) => {
    const updated = [...questions];
    updated[qIdx].choix = updated[qIdx].choix.filter((_, i) => i !== cIdx);
    setQuestions(updated);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...form,
        filiere: form.filiere || null,
        niveau: form.niveau || null,
        annee_academique: form.annee_academique || null,
        date_debut: form.date_debut || null,
        date_fin: form.date_fin || null,
        questions: questions.map((q, i) => ({
          ...q,
          ordre: i + 1,
          choix: q.choix.map((c, j) => ({ ...c, ordre: j + 1 })),
        })),
      };
      if (editingItem) {
        await api.put(`/quiz/quizzes/${editingItem.id}/`, payload);
      } else {
        await api.post('/quiz/quizzes/', payload);
      }
      setShowForm(false);
      fetchItems();
    } catch (err) {
      setError("Erreur lors de l'enregistrement.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    if (window.confirm('Supprimer ce quiz ?')) {
      try {
        await api.delete(`/quiz/quizzes/${id}/`);
        fetchItems();
      } catch (err) {
        setError('Erreur lors de la suppression.');
      }
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Quiz</h1>
        <button className="btn btn-primary" onClick={openCreate}>+ Créer un quiz</button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '800px', maxHeight: '90vh', overflowY: 'auto' }}>
            <div className="modal-header">
              <h3>{editingItem ? 'Modifier' : 'Nouveau'} quiz</h3>
              <button className="close-btn" onClick={() => setShowForm(false)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                <div className="form-group">
                  <label>Titre</label>
                  <input value={form.titre} onChange={(e) => setForm({...form, titre: e.target.value})} required />
                </div>
                <div className="form-group">
                  <label>Description</label>
                  <textarea value={form.description} onChange={(e) => setForm({...form, description: e.target.value})} rows={2} />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Filière</label>
                    <select value={form.filiere} onChange={(e) => setForm({...form, filiere: e.target.value})}>
                      <option value="">-- Toutes --</option>
                      {filieres.map((f) => <option key={f.id} value={f.id}>{f.libelle}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Niveau</label>
                    <select value={form.niveau} onChange={(e) => setForm({...form, niveau: e.target.value})}>
                      <option value="">-- Tous --</option>
                      {niveaux.map((n) => <option key={n.id} value={n.id}>{n.libelle}</option>)}
                    </select>
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Année académique</label>
                    <select value={form.annee_academique} onChange={(e) => setForm({...form, annee_academique: e.target.value})}>
                      <option value="">-- Toutes --</option>
                      {annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Durée (minutes)</label>
                    <input type="number" value={form.duree_minutes} onChange={(e) => setForm({...form, duree_minutes: parseInt(e.target.value)})} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Date début</label>
                    <input type="datetime-local" value={form.date_debut} onChange={(e) => setForm({...form, date_debut: e.target.value})} />
                  </div>
                  <div className="form-group">
                    <label>Date fin</label>
                    <input type="datetime-local" value={form.date_fin} onChange={(e) => setForm({...form, date_fin: e.target.value})} />
                  </div>
                </div>
                <div className="form-group">
                  <label>
                    <input type="checkbox" checked={form.est_publie} onChange={(e) => setForm({...form, est_publie: e.target.checked})} style={{ width: 'auto', marginRight: '8px' }} />
                    Publier
                  </label>
                </div>

                <hr style={{ margin: '20px 0', border: 'none', borderTop: '1px solid var(--gray-200)' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 style={{ margin: 0 }}>Questions ({questions.length})</h3>
                  <button type="button" className="btn btn-sm btn-primary" onClick={addQuestion}>+ Ajouter</button>
                </div>

                {questions.map((q, qIdx) => (
                  <div key={qIdx} style={{ border: '1px solid var(--gray-200)', borderRadius: '8px', padding: '16px', marginBottom: '12px', background: 'var(--gray-50, #f9fafb)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                      <strong style={{ color: 'var(--primary)' }}>Question {qIdx + 1}</strong>
                      <button type="button" className="btn btn-sm btn-danger" onClick={() => removeQuestion(qIdx)}>Supprimer</button>
                    </div>
                    <div className="form-group">
                      <label>Texte</label>
                      <textarea value={q.texte} onChange={(e) => updateQuestion(qIdx, 'texte', e.target.value)} rows={2} required />
                    </div>
                    <div className="form-row">
                      <div className="form-group">
                        <label>Type</label>
                        <select value={q.type_question} onChange={(e) => updateQuestion(qIdx, 'type_question', e.target.value)}>
                          <option value="qcm">QCM</option>
                          <option value="vf">Vrai / Faux</option>
                          <option value="courte">Réponse courte</option>
                        </select>
                      </div>
                      <div className="form-group">
                        <label>Points</label>
                        <input type="number" value={q.points} onChange={(e) => updateQuestion(qIdx, 'points', parseInt(e.target.value))} min="1" />
                      </div>
                    </div>

                    {q.type_question === 'qcm' && (
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                          <label style={{ fontWeight: 600 }}>Choix</label>
                          <button type="button" className="btn btn-sm btn-secondary" onClick={() => addChoix(qIdx)}>+ Choix</button>
                        </div>
                        {q.choix.map((c, cIdx) => (
                          <div key={cIdx} style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '6px' }}>
                            <input
                              type="radio"
                              name={`correct_${qIdx}`}
                              checked={c.est_correct}
                              onChange={() => updateChoix(qIdx, cIdx, 'est_correct', true)}
                              style={{ width: 'auto' }}
                              title="Bonne réponse"
                            />
                            <input
                              value={c.texte}
                              onChange={(e) => updateChoix(qIdx, cIdx, 'texte', e.target.value)}
                              placeholder={`Choix ${cIdx + 1}`}
                              style={{ flex: 1 }}
                              required
                            />
                            {q.choix.length > 2 && (
                              <button type="button" className="btn btn-sm btn-danger" onClick={() => removeChoix(qIdx, cIdx)}>×</button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {q.type_question === 'vf' && (
                      <div style={{ color: 'var(--gray-500)', fontSize: '0.9rem' }}>
                        Le premier choix (Vrai) est la bonne réponse. Modifiez si nécessaire.
                      </div>
                    )}

                    {q.type_question === 'courte' && (
                      <div className="form-group">
                        <label>Réponse attendue</label>
                        <input
                          value={q.choix[0]?.texte || ''}
                          onChange={(e) => {
                            const updated = [...questions];
                            updated[qIdx].choix = [{ texte: e.target.value, est_correct: true, ordre: 1 }];
                            setQuestions(updated);
                          }}
                          placeholder="Réponse exacte attendue"
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>Annuler</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Enregistrement...' : 'Enregistrer'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="table-container">
        {loading ? (
          <div className="loading">Chargement...</div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📝</div>
            <h3>Aucun quiz</h3>
            <p>Créez votre premier quiz pour commencer.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Titre</th><th>Filière</th><th>Niveau</th><th>Questions</th><th>Durée</th><th>Statut</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.titre}</strong></td>
                  <td>{item.filiere_libelle || 'Toutes'}</td>
                  <td>{item.niveau_libelle || 'Tous'}</td>
                  <td>{item.questions?.length || 0}</td>
                  <td>{item.duree_minutes} min</td>
                  <td>{item.est_publie ? <span className="badge badge-active">Publié</span> : <span className="badge badge-inactive">Brouillon</span>}</td>
                  <td>
                    <button className="btn btn-sm btn-secondary" onClick={() => openEdit(item)} style={{marginRight: '8px'}}>Modifier</button>
                    <button className="btn btn-sm btn-danger" onClick={() => handleDelete(item.id)}>Supprimer</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
