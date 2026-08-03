import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

export default function Niveaux() {
  const { user } = useAuth();
  const isSuperAdmin = user?.role === 'superadmin';
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [form, setForm] = useState({ code: '', libelle: '' });
  const [saving, setSaving] = useState(false);

  useEffect(() => { fetchItems(); }, []);

  const fetchItems = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/referentiel/niveaux/');
      setItems(res.data.results || res.data);
    } catch (err) {
      setError('Erreur lors du chargement des données.');
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditingItem(null);
    setForm({ code: '', libelle: '' });
    setShowForm(true);
  };

  const openEdit = (item) => {
    setEditingItem(item);
    setForm({ code: item.code, libelle: item.libelle });
    setShowForm(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editingItem) {
        await api.put(`/referentiel/niveaux/${editingItem.id}/`, form);
      } else {
        await api.post('/referentiel/niveaux/', form);
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
    if (window.confirm('Supprimer ce niveau ?')) {
      try {
        await api.delete(`/referentiel/niveaux/${id}/`);
        fetchItems();
      } catch (err) {
        setError('Erreur lors de la suppression.');
      }
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Niveaux</h1>
        {isSuperAdmin && <button className="btn btn-primary" onClick={openCreate}>+ Ajouter</button>}
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{editingItem ? 'Modifier' : 'Nouveau'} niveau</h3>
              <button className="close-btn" onClick={() => setShowForm(false)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                <div className="form-group">
                  <label>Code</label>
                  <input value={form.code} onChange={(e) => setForm({...form, code: e.target.value})} placeholder="ex: L1, L2, M1" required />
                </div>
                <div className="form-group">
                  <label>Libellé</label>
                  <input value={form.libelle} onChange={(e) => setForm({...form, libelle: e.target.value})} placeholder="ex: Licence 1" required />
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
              <tr><th>Code</th><th>Libellé</th>{isSuperAdmin && <th>Actions</th>}</tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr><td colSpan={isSuperAdmin ? 3 : 2}><div className="empty-state"><div className="empty-icon">📊</div><h3>Aucun niveau</h3></div></td></tr>
              ) : items.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.code}</strong></td>
                  <td>{item.libelle}</td>
                  {isSuperAdmin && (
                    <td>
                      <button className="btn btn-sm btn-secondary" onClick={() => openEdit(item)} style={{marginRight: '8px'}}>Modifier</button>
                      <button className="btn btn-sm btn-danger" onClick={() => handleDelete(item.id)}>Supprimer</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
