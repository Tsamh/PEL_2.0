import { useState, useEffect } from 'react';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';

export default function Enseignants() {
  const { user } = useAuth();
  const estAdmin = ['superadmin', 'admin'].includes(user?.role);
  const [enseignants, setEnseignants] = useState([]);
  const [classes, setClasses] = useState([]);
  const [showInvite, setShowInvite] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [editEnseignant, setEditEnseignant] = useState(null);
  const [editForm, setEditForm] = useState({ first_name: '', last_name: '', email: '', telephone: '', classes: [] });
  const [form, setForm] = useState({ email: '', first_name: '', last_name: '', telephone: '', mot_de_passe: '', classes: [] });
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchEnseignants();
    api.get('/referentiel/classes/').then((res) => setClasses(res.data.results || res.data));
  }, []);

  const fetchEnseignants = async () => {
    const res = await api.get('/accounts/users/by_role/?role=enseignant');
    setEnseignants(res.data);
  };

  const handleInvite = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);
    try {
      const res = await api.post('/accounts/users/invite_enseignant/', form);
      setMessage(res.data.message);
      setForm({ email: '', first_name: '', last_name: '', telephone: '', mot_de_passe: '', classes: [] });
      setShowInvite(false);
      fetchEnseignants();
    } catch (err) {
      setError(err.response?.data?.error || "Erreur lors de l'invitation");
    } finally {
      setLoading(false);
    }
  };

  const openEdit = async (enseignant) => {
    setEditEnseignant(enseignant);
    setEditForm({
      first_name: enseignant.first_name || '',
      last_name: enseignant.last_name || '',
      email: enseignant.email || '',
      telephone: enseignant.telephone || '',
      classes: enseignant.classes_assignees?.map((c) => c.id) || [],
    });
    setShowEdit(true);
  };

  const handleEdit = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);
    try {
      const { classes: classesIds, ...userFields } = editForm;
      if (estAdmin) {
        await api.patch(`/accounts/users/${editEnseignant.id}/`, userFields);
      }
      await api.post(`/accounts/users/${editEnseignant.id}/update_classes/`, { classes: classesIds });
      setMessage('Enseignant modifié avec succès');
      setShowEdit(false);
      setEditEnseignant(null);
      fetchEnseignants();
    } catch (err) {
      setError(err.response?.data?.error || 'Erreur lors de la modification');
    } finally {
      setLoading(false);
    }
  };

  const toggleActif = async (enseignant) => {
    setError('');
    setMessage('');
    const verbe = enseignant.is_active ? 'deactivate' : 'reactivate';
    try {
      const res = await api.post(`/accounts/users/${enseignant.id}/${verbe}/`);
      setMessage(res.data.message);
      fetchEnseignants();
    } catch (err) {
      setError(err.response?.data?.error || 'Action impossible');
    }
  };

  const toggleEditClasse = (classeId) => {
    const current = editForm.classes;
    if (current.includes(classeId)) {
      setEditForm({ ...editForm, classes: current.filter((id) => id !== classeId) });
    } else {
      setEditForm({ ...editForm, classes: [...current, classeId] });
    }
  };

  const toggleClasse = (classeId) => {
    const current = form.classes;
    if (current.includes(classeId)) {
      setForm({ ...form, classes: current.filter((id) => id !== classeId) });
    } else {
      setForm({ ...form, classes: [...current, classeId] });
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Enseignants</h1>
        {estAdmin && <button className="btn btn-primary" onClick={() => setShowInvite(true)}>+ Inviter un enseignant</button>}
      </div>

      {message && <div className="alert alert-success">{message}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      <div className="table-container">
        {enseignants.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">👨‍🏫</div>
            <h3>Aucun enseignant</h3>
            <p>Invitez des enseignants à rejoindre votre établissement.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Nom complet</th><th>Email</th><th>Téléphone</th><th>Classes</th><th>Statut</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {enseignants.map((e) => (
                <tr key={e.id}>
                  <td><strong>{e.last_name} {e.first_name}</strong></td>
                  <td>{e.email}</td>
                  <td>{e.telephone || '-'}</td>
                  <td>
                    {e.classes_assignees?.length > 0 ? (
                      <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                        {e.classes_assignees.map((c) => (
                          <span key={c.id} className="badge badge-active" style={{ fontSize: '0.75rem' }}>{c.libelle}</span>
                        ))}
                      </div>
                    ) : (
                      <span style={{ color: 'var(--gray-400)' }}>-</span>
                    )}
                  </td>
                  <td>
                    {e.must_change_password ? (
                      <span className="badge badge-inactive">En attente</span>
                    ) : e.is_active ? (
                      <span className="badge badge-active">Actif</span>
                    ) : (
                      <span className="badge badge-inactive">Inactif</span>
                    )}
                  </td>
                  <td>
                    <button className="btn btn-sm btn-primary" style={{ marginRight: '6px' }} onClick={() => openEdit(e)}>Modifier</button>
                    {estAdmin && (
                      <button className={`btn btn-sm ${e.is_active ? 'btn-danger' : 'btn-primary'}`} onClick={() => toggleActif(e)}>
                        {e.is_active ? 'Désactiver' : 'Réactiver'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showEdit && editEnseignant && (
        <div className="modal-overlay" onClick={() => setShowEdit(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Modifier l'enseignant</h3>
              <button className="close-btn" onClick={() => setShowEdit(false)}>×</button>
            </div>
            <form onSubmit={handleEdit}>
              <div className="modal-body">
                <div className="form-row">
                  <div className="form-group">
                    <label>Prénom</label>
                    <input value={editForm.first_name} onChange={(e) => setEditForm({...editForm, first_name: e.target.value})} required />
                  </div>
                  <div className="form-group">
                    <label>Nom</label>
                    <input value={editForm.last_name} onChange={(e) => setEditForm({...editForm, last_name: e.target.value})} required />
                  </div>
                </div>
                <div className="form-group">
                  <label>Email</label>
                  <input type="email" value={editForm.email} onChange={(e) => setEditForm({...editForm, email: e.target.value})} required />
                </div>
                <div className="form-group">
                  <label>Téléphone</label>
                  <input value={editForm.telephone} onChange={(e) => setEditForm({...editForm, telephone: e.target.value})} />
                </div>
                <div className="form-group">
                  <label>Classes assignées</label>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '4px' }}>
                    {classes.map((c) => (
                      <label key={c.id} style={{
                        display: 'flex', alignItems: 'center', gap: '6px',
                        padding: '6px 12px', borderRadius: '6px', cursor: 'pointer',
                        border: editForm.classes.includes(c.id) ? '2px solid var(--primary)' : '1px solid var(--gray-200)',
                        background: editForm.classes.includes(c.id) ? 'var(--primary-light, rgba(59,130,246,0.1))' : 'white',
                        fontSize: '0.85rem'
                      }}>
                        <input
                          type="checkbox"
                          checked={editForm.classes.includes(c.id)}
                          onChange={() => toggleEditClasse(c.id)}
                          style={{ width: 'auto' }}
                        />
                        {c.libelle} ({c.code})
                      </label>
                    ))}
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowEdit(false)}>Annuler</button>
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? 'Enregistrement...' : 'Enregistrer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showInvite && (
        <div className="modal-overlay" onClick={() => setShowInvite(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Inviter un enseignant</h3>
              <button className="close-btn" onClick={() => setShowInvite(false)}>×</button>
            </div>
            <form onSubmit={handleInvite}>
              <div className="modal-body">
                <div className="form-row">
                  <div className="form-group">
                    <label>Prénom</label>
                    <input value={form.first_name} onChange={(e) => setForm({...form, first_name: e.target.value})} required />
                  </div>
                  <div className="form-group">
                    <label>Nom</label>
                    <input value={form.last_name} onChange={(e) => setForm({...form, last_name: e.target.value})} required />
                  </div>
                </div>
                <div className="form-group">
                  <label>Email</label>
                  <input type="email" value={form.email} onChange={(e) => setForm({...form, email: e.target.value})} required />
                </div>
                <div className="form-group">
                  <label>Téléphone (optionnel)</label>
                  <input value={form.telephone} onChange={(e) => setForm({...form, telephone: e.target.value})} />
                </div>
                <div className="form-group">
                  <label>Classes assignées</label>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '4px' }}>
                    {classes.map((c) => (
                      <label key={c.id} style={{
                        display: 'flex', alignItems: 'center', gap: '6px',
                        padding: '6px 12px', borderRadius: '6px', cursor: 'pointer',
                        border: form.classes.includes(c.id) ? '2px solid var(--primary)' : '1px solid var(--gray-200)',
                        background: form.classes.includes(c.id) ? 'var(--primary-light, rgba(59,130,246,0.1))' : 'white',
                        fontSize: '0.85rem'
                      }}>
                        <input
                          type="checkbox"
                          checked={form.classes.includes(c.id)}
                          onChange={() => toggleClasse(c.id)}
                          style={{ width: 'auto' }}
                        />
                        {c.libelle} ({c.code})
                      </label>
                    ))}
                    {classes.length === 0 && <span style={{ color: 'var(--gray-400)', fontSize: '0.85rem' }}>Aucune classe disponible</span>}
                  </div>
                </div>
                <div className="form-group">
                  <label>Mot de passe (optionnel)</label>
                  <input type="password" value={form.mot_de_passe} onChange={(e) => setForm({...form, mot_de_passe: e.target.value})} placeholder="Si vide, l'enseignant devra réinitialiser son mot de passe" />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowInvite(false)}>Annuler</button>
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? 'Création...' : 'Créer l\'enseignant'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
