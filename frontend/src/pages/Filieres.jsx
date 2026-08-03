import { useState, useEffect } from 'react';
import api from '../services/api';

export default function Filieres() {
  const [items, setItems] = useState([]);
  const [etablissements, setEtablissements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [form, setForm] = useState({ code: '', libelle: '', etablissement: '', description: '' });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchItems();
    api.get('/referentiel/etablissements/').then((res) => setEtablissements(res.data.results || res.data));
  }, []);

  const fetchItems = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/referentiel/filieres/');
      setItems(res.data.results || res.data);
    } catch (err) {
      setError('Erreur lors du chargement des données.');
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditingItem(null);
    setForm({ code: '', libelle: '', etablissement: '', description: '' });
    setShowForm(true);
  };

  const openEdit = (item) => {
    setEditingItem(item);
    setForm({ code: item.code, libelle: item.libelle, etablissement: item.etablissement || '', description: item.description || '' });
    setShowForm(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editingItem) {
        await api.put(`/referentiel/filieres/${editingItem.id}/`, form);
      } else {
        await api.post('/referentiel/filieres/', form);
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
    if (window.confirm('Supprimer cette filière ?')) {
      try {
        await api.delete(`/referentiel/filieres/${id}/`);
        fetchItems();
      } catch (err) {
        setError('Erreur lors de la suppression.');
      }
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Filières</h1>
        <button className="btn btn-primary" onClick={openCreate}>+ Ajouter</button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{editingItem ? 'Modifier' : 'Nouvelle'} filière</h3>
              <button className="close-btn" onClick={() => setShowForm(false)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                <div className="form-row">
                  <div className="form-group">
                    <label>Code</label>
                    <input value={form.code} onChange={(e) => setForm({...form, code: e.target.value})} required />
                  </div>
                  <div className="form-group">
                    <label>Établissement</label>
                    <select value={form.etablissement} onChange={(e) => setForm({...form, etablissement: e.target.value})}>
                      <option value="">-- Sélectionner --</option>
                      {etablissements.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
                    </select>
                  </div>
                </div>
                <div className="form-group">
                  <label>Libellé</label>
                  <input value={form.libelle} onChange={(e) => setForm({...form, libelle: e.target.value})} required />
                </div>
                <div className="form-group">
                  <label>Description</label>
                  <textarea value={form.description} onChange={(e) => setForm({...form, description: e.target.value})} rows={3} />
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
              <tr><th>Code</th><th>Libellé</th><th>Établissement</th><th>Description</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr><td colSpan="5"><div className="empty-state"><div className="empty-icon">📚</div><h3>Aucune filière</h3></div></td></tr>
              ) : items.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.code}</strong></td>
                  <td>{item.libelle}</td>
                  <td>{item.etablissement_nom || '-'}</td>
                  <td>{item.description || '-'}</td>
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
