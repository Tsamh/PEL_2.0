import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

export default function AnneesAcademiques() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const isSuperAdmin = user?.role === 'superadmin';
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [form, setForm] = useState({ libelle: '', date_debut: '', date_fin: '', est_active: false });
  const [saving, setSaving] = useState(false);

  useEffect(() => { fetchItems(); }, []);

  const fetchItems = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/referentiel/annees-academiques/');
      setItems(res.data.results || res.data);
    } catch (err) {
      setError('Erreur lors du chargement des données.');
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditingItem(null);
    setForm({ libelle: '', date_debut: '', date_fin: '', est_active: false });
    setShowForm(true);
  };

  const openEdit = (item) => {
    setEditingItem(item);
    setForm({ libelle: item.libelle, date_debut: item.date_debut, date_fin: item.date_fin, est_active: item.est_active });
    setShowForm(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editingItem) {
        await api.put(`/referentiel/annees-academiques/${editingItem.id}/`, form);
      } else {
        await api.post('/referentiel/annees-academiques/', form);
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
    if (window.confirm('Supprimer cette année académique ?')) {
      try {
        await api.delete(`/referentiel/annees-academiques/${id}/`);
        fetchItems();
      } catch (err) {
        setError('Erreur lors de la suppression.');
      }
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Années académiques</h1>
        <button className="btn btn-primary" onClick={openCreate}>+ Ajouter</button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{editingItem ? 'Modifier' : 'Nouvelle'} année académique</h3>
              <button className="close-btn" onClick={() => setShowForm(false)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                <div className="form-group">
                  <label>Libellé</label>
                  <input value={form.libelle} onChange={(e) => setForm({...form, libelle: e.target.value})} placeholder="ex: 2025-2026" required />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Date début</label>
                    <input type="date" value={form.date_debut} onChange={(e) => setForm({...form, date_debut: e.target.value})} required />
                  </div>
                  <div className="form-group">
                    <label>Date fin</label>
                    <input type="date" value={form.date_fin} onChange={(e) => setForm({...form, date_fin: e.target.value})} required />
                  </div>
                </div>
                <div className="form-group">
                  <label>
                    <input type="checkbox" checked={form.est_active} onChange={(e) => setForm({...form, est_active: e.target.checked})} style={{ width: 'auto', marginRight: '8px' }} />
                    Année active
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
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Libellé</th>
                <th>Date début</th>
                <th>Date fin</th>
                <th>Établissement</th>
                <th>Statut</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr><td colSpan="6"><div className="empty-state"><div className="empty-icon">📅</div><h3>Aucune année académique</h3></div></td></tr>
              ) : items.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.libelle}</strong></td>
                  <td>{item.date_debut}</td>
                  <td>{item.date_fin}</td>
                  <td>{item.etablissement_nom || 'Global'}</td>
                  <td>{item.est_active ? <span className="badge badge-active">Active</span> : <span className="badge badge-inactive">Inactive</span>}</td>
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
