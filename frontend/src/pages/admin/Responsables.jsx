import { useState, useEffect } from 'react';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const FORMULAIRE_VIDE = { email: '', first_name: '', last_name: '', telephone: '', etablissement: '' };

export default function Responsables() {
  const { user } = useAuth();
  const [responsables, setResponsables] = useState([]);
  const [etablissements, setEtablissements] = useState([]);
  const [showInvite, setShowInvite] = useState(false);
  const [form, setForm] = useState(FORMULAIRE_VIDE);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const estSuperadmin = user?.role === 'superadmin';

  useEffect(() => {
    fetchResponsables();
    if (estSuperadmin) {
      api.get('/referentiel/etablissements/').then((res) => setEtablissements(res.data.results || res.data));
    }
  }, [estSuperadmin]);

  const fetchResponsables = async () => {
    const res = await api.get('/accounts/users/by_role/?role=responsable_formation');
    setResponsables(res.data);
  };

  const handleInvite = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);
    try {
      const payload = { ...form, etablissement: form.etablissement || null };
      const res = await api.post('/accounts/users/invite_responsable/', payload);
      setMessage(res.data.message);
      setForm(FORMULAIRE_VIDE);
      setShowInvite(false);
      fetchResponsables();
    } catch (err) {
      setError(err.response?.data?.error || "Erreur lors de l'invitation");
    } finally {
      setLoading(false);
    }
  };

  const toggleActif = async (responsable) => {
    setError('');
    setMessage('');
    const verbe = responsable.is_active ? 'deactivate' : 'reactivate';
    try {
      const res = await api.post(`/accounts/users/${responsable.id}/${verbe}/`);
      setMessage(res.data.message);
      fetchResponsables();
    } catch (err) {
      setError(err.response?.data?.error || 'Action impossible');
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Responsables de formation</h1>
        <button className="btn btn-primary" onClick={() => setShowInvite(true)}>+ Inviter un responsable</button>
      </div>

      {message && <div className="alert alert-success">{message}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      <div className="table-container">
        {responsables.length === 0 ? (
          <div className="empty-state">
            <h3>Aucun responsable</h3>
            <p>Invitez un responsable pour gérer la structure académique et les affectations.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Nom complet</th><th>Email</th><th>Établissement</th><th>Statut</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {responsables.map((r) => (
                <tr key={r.id}>
                  <td><strong>{r.last_name} {r.first_name}</strong></td>
                  <td>{r.email}</td>
                  <td>{r.etablissement_nom || '-'}</td>
                  <td>
                    {r.is_invited ? (
                      <span className="badge badge-inactive">Invitation envoyée</span>
                    ) : r.is_active ? (
                      <span className="badge badge-active">Actif</span>
                    ) : (
                      <span className="badge badge-inactive">Désactivé</span>
                    )}
                  </td>
                  <td>
                    <button className={`btn btn-sm ${r.is_active ? 'btn-danger' : 'btn-primary'}`} onClick={() => toggleActif(r)}>
                      {r.is_active ? 'Désactiver' : 'Réactiver'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showInvite && (
        <div className="modal-overlay" onClick={() => setShowInvite(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Inviter un responsable de formation</h3>
              <button className="close-btn" onClick={() => setShowInvite(false)}>×</button>
            </div>
            <form onSubmit={handleInvite}>
              <div className="modal-body">
                <div className="form-row">
                  <div className="form-group">
                    <label>Prénom</label>
                    <input value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} required />
                  </div>
                  <div className="form-group">
                    <label>Nom</label>
                    <input value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} required />
                  </div>
                </div>
                <div className="form-group">
                  <label>Email</label>
                  <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
                </div>
                <div className="form-group">
                  <label>Téléphone (optionnel)</label>
                  <input value={form.telephone} onChange={(e) => setForm({ ...form, telephone: e.target.value })} />
                </div>
                {estSuperadmin && (
                  <div className="form-group">
                    <label>Établissement</label>
                    <select value={form.etablissement} onChange={(e) => setForm({ ...form, etablissement: e.target.value })} required>
                      <option value="">Choisir un établissement</option>
                      {etablissements.map((et) => (
                        <option key={et.id} value={et.id}>{et.nom}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowInvite(false)}>Annuler</button>
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? 'Envoi...' : "Envoyer l'invitation"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
