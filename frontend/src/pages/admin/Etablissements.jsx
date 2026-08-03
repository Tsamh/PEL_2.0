import { useState, useEffect } from 'react';
import api from '../../services/api';

export default function Etablissements() {
  const [items, setItems] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [showInviteAdmin, setShowInviteAdmin] = useState(null);
  const [form, setForm] = useState({
    code: '', nom: '', sigle: '', adresse: '', telephone: '', email: '', site_web: '',
    admin_email: '', admin_first_name: '', admin_last_name: ''
  });
  const [inviteForm, setInviteForm] = useState({ admin_email: '', admin_first_name: '', admin_last_name: '' });
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => { fetchItems(); }, []);

  const fetchItems = async () => {
    const res = await api.get('/referentiel/etablissements/');
    setItems(res.data.results || res.data);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);
    try {
      const res = await api.post('/referentiel/etablissements/', form);
      setMessage(res.data.message);
      setShowForm(false);
      setForm({ code: '', nom: '', sigle: '', adresse: '', telephone: '', email: '', site_web: '', admin_email: '', admin_first_name: '', admin_last_name: '' });
      fetchItems();
    } catch (err) {
      setError(err.response?.data?.error || 'Erreur lors de la création');
    } finally {
      setLoading(false);
    }
  };

  const handleInviteAdmin = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);
    try {
      const res = await api.post(`/referentiel/etablissements/${showInviteAdmin}/invite_admin/`, inviteForm);
      setMessage(res.data.message);
      setShowInviteAdmin(null);
      setInviteForm({ admin_email: '', admin_first_name: '', admin_last_name: '' });
      fetchItems();
    } catch (err) {
      setError(err.response?.data?.error || 'Erreur lors de l\'invitation');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (window.confirm('Supprimer cet établissement et tous ses données ?')) {
      await api.delete(`/referentiel/etablissements/${id}/`);
      fetchItems();
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Établissements</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(true)}>+ Nouvel établissement</button>
      </div>

      {message && <div className="success-msg">{message}</div>}
      {error && <div className="error-msg">{error}</div>}

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Nom</th>
              <th>Sigle</th>
              <th>Admin</th>
              <th>Email</th>
              <th>Téléphone</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan="7"><div className="empty-state"><div className="empty-icon">🏫</div><h3>Aucun établissement</h3><p>Créez votre premier établissement et invitez son administrateur</p></div></td></tr>
            ) : items.map((item) => (
              <tr key={item.id}>
                <td><strong>{item.code}</strong></td>
                <td>{item.nom}</td>
                <td>{item.sigle || '-'}</td>
                <td>
                  {item.admin_nom ? (
                    <span className="badge badge-active">{item.admin_nom}</span>
                  ) : (
                    <button className="btn btn-sm btn-outline" onClick={() => setShowInviteAdmin(item.id)}>+ Inviter</button>
                  )}
                </td>
                <td>{item.email || '-'}</td>
                <td>{item.telephone || '-'}</td>
                <td>
                  <button className="btn btn-sm btn-danger" onClick={() => handleDelete(item.id)}>Supprimer</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Nouvel établissement</h3>
              <button className="close-btn" onClick={() => setShowForm(false)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                <h4 style={{ fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--gray-400)', marginBottom: '16px', fontWeight: 700 }}>Informations de l'établissement</h4>
                <div className="form-row">
                  <div className="form-group">
                    <label>Code</label>
                    <input value={form.code} onChange={(e) => setForm({...form, code: e.target.value})} placeholder="ex: IST" required />
                  </div>
                  <div className="form-group">
                    <label>Sigle</label>
                    <input value={form.sigle} onChange={(e) => setForm({...form, sigle: e.target.value})} placeholder="ex: IST" />
                  </div>
                </div>
                <div className="form-group">
                  <label>Nom complet</label>
                  <input value={form.nom} onChange={(e) => setForm({...form, nom: e.target.value})} placeholder="ex: Institut Supérieur de Technologie" required />
                </div>
                <div className="form-group">
                  <label>Adresse</label>
                  <input value={form.adresse} onChange={(e) => setForm({...form, adresse: e.target.value})} placeholder="Adresse complète" />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Téléphone</label>
                    <input value={form.telephone} onChange={(e) => setForm({...form, telephone: e.target.value})} placeholder="+225 XX XX XX XX" />
                  </div>
                  <div className="form-group">
                    <label>Email</label>
                    <input type="email" value={form.email} onChange={(e) => setForm({...form, email: e.target.value})} placeholder="contact@etablissement.com" />
                  </div>
                </div>
                <div className="form-group">
                  <label>Site web</label>
                  <input value={form.site_web} onChange={(e) => setForm({...form, site_web: e.target.value})} placeholder="https://..." />
                </div>

                <div style={{ borderTop: '1px solid var(--gray-200)', margin: '24px 0', paddingTop: '20px' }}>
                  <h4 style={{ fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--gray-400)', marginBottom: '16px', fontWeight: 700 }}>Administrateur de l'établissement</h4>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Prénom de l'admin</label>
                      <input value={form.admin_first_name} onChange={(e) => setForm({...form, admin_first_name: e.target.value})} placeholder="Prénom" required />
                    </div>
                    <div className="form-group">
                      <label>Nom de l'admin</label>
                      <input value={form.admin_last_name} onChange={(e) => setForm({...form, admin_last_name: e.target.value})} placeholder="Nom" required />
                    </div>
                  </div>
                  <div className="form-group">
                    <label>Email de l'admin (pour recevoir l'invitation)</label>
                    <input type="email" value={form.admin_email} onChange={(e) => setForm({...form, admin_email: e.target.value})} placeholder="admin@etablissement.com" required />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>Annuler</button>
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? 'Création...' : 'Créer et inviter l\'admin'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showInviteAdmin && (
        <div className="modal-overlay" onClick={() => setShowInviteAdmin(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Inviter un administrateur</h3>
              <button className="close-btn" onClick={() => setShowInviteAdmin(null)}>×</button>
            </div>
            <form onSubmit={handleInviteAdmin}>
              <div className="modal-body">
                <div className="form-row">
                  <div className="form-group">
                    <label>Prénom</label>
                    <input value={inviteForm.admin_first_name} onChange={(e) => setInviteForm({...inviteForm, admin_first_name: e.target.value})} required />
                  </div>
                  <div className="form-group">
                    <label>Nom</label>
                    <input value={inviteForm.admin_last_name} onChange={(e) => setInviteForm({...inviteForm, admin_last_name: e.target.value})} required />
                  </div>
                </div>
                <div className="form-group">
                  <label>Email</label>
                  <input type="email" value={inviteForm.admin_email} onChange={(e) => setInviteForm({...inviteForm, admin_email: e.target.value})} placeholder="admin@etablissement.com" required />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowInviteAdmin(null)}>Annuler</button>
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? 'Envoi...' : 'Envoyer l\'invitation'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
