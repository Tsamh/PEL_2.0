import { useState, useEffect } from 'react';
import api from '../../services/api';

export default function Validations() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState(null);
  const [rejectModal, setRejectModal] = useState(null);
  const [rejectReason, setRejectReason] = useState('');

  useEffect(() => { fetchItems(); }, []);

  const fetchItems = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get('/accounts/users/pending_validations/');
      setItems(res.data);
    } catch (err) {
      setError('Erreur lors du chargement des demandes.');
    } finally {
      setLoading(false);
    }
  };

  const handleValidate = async (userId, action) => {
    setActionLoading(userId);
    try {
      await api.post('/accounts/users/validate_admin/', {
        user_id: userId,
        action: action,
        rejection_reason: action === 'reject' ? rejectReason : '',
      });
      setItems(items.filter((item) => item.id !== userId));
      setRejectModal(null);
      setRejectReason('');
    } catch (err) {
      setError(err.response?.data?.error || "Erreur lors de l'action.");
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Validations des admins</h1>
        <span className="badge badge-active" style={{ fontSize: '0.9rem', padding: '6px 12px' }}>
          {items.length} en attente
        </span>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {rejectModal && (
        <div className="modal-overlay" onClick={() => setRejectModal(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Rejeter la demande</h3>
              <button className="close-btn" onClick={() => setRejectModal(null)}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Motif du rejet (optionnel)</label>
                <textarea
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="Expliquez pourquoi la demande est rejetée..."
                  rows={4}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setRejectModal(null)}>Annuler</button>
              <button
                className="btn btn-danger"
                onClick={() => handleValidate(rejectModal, 'reject')}
                disabled={actionLoading === rejectModal}
              >
                {actionLoading === rejectModal ? 'Rejet...' : 'Confirmer le rejet'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="table-container">
        {loading ? (
          <div className="loading">Chargement...</div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">✅</div>
            <h3>Aucune demande en attente</h3>
            <p>Toutes les demandes d'inscription ont été traitées.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Nom</th>
                <th>Email</th>
                <th>Établissement</th>
                <th>Date demande</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.first_name} {item.last_name}</strong></td>
                  <td>{item.email}</td>
                  <td>{item.etablissement_nom || '-'}</td>
                  <td>{item.date_invitation ? new Date(item.date_invitation).toLocaleDateString('fr-FR') : '-'}</td>
                  <td>
                    <button
                      className="btn btn-sm btn-primary"
                      onClick={() => handleValidate(item.id, 'approve')}
                      disabled={actionLoading === item.id}
                      style={{ marginRight: '8px' }}
                    >
                      {actionLoading === item.id ? '...' : 'Approuver'}
                    </button>
                    <button
                      className="btn btn-sm btn-danger"
                      onClick={() => setRejectModal(item.id)}
                      disabled={actionLoading === item.id}
                    >
                      Rejeter
                    </button>
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
