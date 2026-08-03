import { useState, useEffect } from 'react';
import api from '../../services/api';
import CodeEditor from '../../components/CodeEditor';

export default function MesQuiz() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    titre: '', description: '', filiere: '', niveau: '', annee_academique: '',
    duree_minutes: 30, date_debut: '', date_fin: '', est_publie: false,
  });
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
      setError('Erreur lors du chargement des quiz.');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post('/quiz/quizzes/', {
        ...form,
        filiere: form.filiere || null,
        niveau: form.niveau || null,
        annee_academique: form.annee_academique || null,
        date_debut: form.date_debut || null,
        date_fin: form.date_fin || null,
      });
      setShowForm(false);
      setForm({ titre: '', description: '', filiere: '', niveau: '', annee_academique: '', duree_minutes: 30, date_debut: '', date_fin: '', est_publie: false });
      fetchItems();
    } catch (err) {
      setError("Erreur lors de l'enregistrement.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    if (window.confirm('Supprimer ce quiz ?')) {
      await api.delete(`/quiz/quizzes/${id}/`);
      fetchItems();
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Mes quiz</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ Créer un quiz</button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '700px' }}>
            <div className="modal-header">
              <h3>Nouveau quiz</h3>
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
                  <textarea value={form.description} onChange={(e) => setForm({...form, description: e.target.value})} rows={3} />
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
                    <input type="number" value={form.duree_minutes} onChange={(e) => setForm({...form, duree_minutes: parseInt(e.target.value)})} min="1" />
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
            <h3>Aucun quiz créé</h3>
            <p>Commencez par créer des quiz pour vos cours.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Titre</th><th>Filière</th><th>Niveau</th><th>Durée</th><th>Statut</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.titre}</strong></td>
                  <td>{item.filiere_libelle || 'Toutes'}</td>
                  <td>{item.niveau_libelle || 'Tous'}</td>
                  <td>{item.duree_minutes} min</td>
                  <td>{item.est_publie ? <span className="badge badge-active">Publié</span> : <span className="badge badge-inactive">Brouillon</span>}</td>
                  <td>
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
