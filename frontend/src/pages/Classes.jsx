import { useState, useEffect } from 'react';
import api from '../services/api';
import CaseArchives from '../components/CaseArchives';

export default function Classes() {
  const [items, setItems] = useState([]);
  const [filieres, setFilieres] = useState([]);
  const [niveaux, setNiveaux] = useState([]);
  const [annees, setAnnees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [form, setForm] = useState({ code: '', libelle: '', filiere: '', niveau: '', annee_academique: '', effectif_max: 60 });
  const [saving, setSaving] = useState(false);
  const [archives, setArchives] = useState(false);

  useEffect(() => {
    api.get('/referentiel/filieres/').then((res) => setFilieres(res.data.results || res.data));
    api.get('/referentiel/niveaux/').then((res) => setNiveaux(res.data.results || res.data));
    api.get('/referentiel/annees-academiques/').then((res) => setAnnees((res.data.results || res.data).filter((a) => !a.archivee)));
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchItems(); }, [archives]);

  const fetchItems = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/referentiel/classes/', { params: archives ? { archives: '1' } : {} });
      setItems(res.data.results || res.data);
    } catch (err) {
      setError('Erreur lors du chargement des données.');
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditingItem(null);
    setForm({ code: '', libelle: '', filiere: '', niveau: '', annee_academique: '', effectif_max: 60 });
    setShowForm(true);
  };

  const openEdit = (item) => {
    setEditingItem(item);
    setForm({ code: item.code, libelle: item.libelle, filiere: item.filiere || '', niveau: item.niveau || '', annee_academique: item.annee_academique || '', effectif_max: item.effectif_max });
    setShowForm(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editingItem) {
        await api.put(`/referentiel/classes/${editingItem.id}/`, form);
      } else {
        await api.post('/referentiel/classes/', form);
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
    if (window.confirm('Supprimer cette classe ?')) {
      try {
        await api.delete(`/referentiel/classes/${id}/`);
        fetchItems();
      } catch (err) {
        setError('Erreur lors de la suppression.');
      }
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Classes</h1>
        {!archives && <button className="btn btn-primary" onClick={openCreate}>+ Ajouter</button>}
      </div>

      <CaseArchives archives={archives} onChange={setArchives} />

      {error && <div className="alert alert-error">{error}</div>}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{editingItem ? 'Modifier' : 'Nouvelle'} classe</h3>
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
                    <label>Effectif max</label>
                    <input type="number" value={form.effectif_max} onChange={(e) => setForm({...form, effectif_max: parseInt(e.target.value)})} />
                  </div>
                </div>
                <div className="form-group">
                  <label>Libellé</label>
                  <input value={form.libelle} onChange={(e) => setForm({...form, libelle: e.target.value})} required />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Filière</label>
                    <select value={form.filiere} onChange={(e) => setForm({...form, filiere: e.target.value})} required>
                      <option value="">-- Sélectionner --</option>
                      {filieres.map((f) => <option key={f.id} value={f.id}>{f.libelle}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Niveau</label>
                    <select value={form.niveau} onChange={(e) => setForm({...form, niveau: e.target.value})} required>
                      <option value="">-- Sélectionner --</option>
                      {niveaux.map((n) => <option key={n.id} value={n.id}>{n.libelle}</option>)}
                    </select>
                  </div>
                </div>
                <div className="form-group">
                  <label>Année académique</label>
                  <select value={form.annee_academique} onChange={(e) => setForm({...form, annee_academique: e.target.value})} required>
                    <option value="">-- Sélectionner --</option>
                    {annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
                  </select>
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
              <tr><th>Code</th><th>Libellé</th><th>Filière</th><th>Niveau</th><th>Année</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr><td colSpan="6"><div className="empty-state"><div className="empty-icon">🏫</div><h3>Aucune classe</h3></div></td></tr>
              ) : items.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.code}</strong></td>
                  <td>{item.libelle}</td>
                  <td>{item.filiere_libelle}</td>
                  <td>{item.niveau_libelle}</td>
                  <td>{item.annee_libelle}</td>
                  <td>
                    {!archives && (
                      <>
                        <button className="btn btn-sm btn-secondary" onClick={() => openEdit(item)} style={{marginRight: '8px'}}>Modifier</button>
                        <button className="btn btn-sm btn-danger" onClick={() => handleDelete(item.id)}>Supprimer</button>
                      </>
                    )}
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
