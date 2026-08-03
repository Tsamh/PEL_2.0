import { useState, useEffect } from 'react';
import api from '../../services/api';

export default function StudentManagement() {
  const [students, setStudents] = useState([]);
  const [classes, setClasses] = useState([]);
  const [showInvite, setShowInvite] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: '', first_name: '', last_name: '', matricule: '', classe: '', mot_de_passe: '' });
  const [importFile, setImportFile] = useState(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchStudents();
    api.get('/referentiel/classes/').then((res) => setClasses(res.data.results || res.data));
  }, []);

  const fetchStudents = async () => {
    const res = await api.get('/accounts/users/by_role/?role=etudiant');
    setStudents(res.data);
  };

  const handleInvite = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    setLoading(true);
    try {
      const payload = { ...inviteForm, classe: inviteForm.classe || null, mot_de_passe: inviteForm.mot_de_passe || '' };
      const res = await api.post('/accounts/users/invite_student/', payload);
      setMessage(res.data.message);
      setInviteForm({ email: '', first_name: '', last_name: '', matricule: '', classe: '', mot_de_passe: '' });
      setShowInvite(false);
      fetchStudents();
    } catch (err) {
      setError(err.response?.data?.error || 'Erreur lors de l\'invitation');
    } finally {
      setLoading(false);
    }
  };

  const handleImport = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');
    if (!importFile) {
      setError('Sélectionnez un fichier');
      return;
    }
    setLoading(true);
    const formData = new FormData();
    formData.append('file', importFile);
    try {
      const res = await api.post('/accounts/users/import_students/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setMessage(res.data.message);
      if (res.data.errors?.length > 0) {
        setError(`${res.data.errors.length} erreur(s) : ${res.data.errors.slice(0, 3).join(', ')}`);
      }
      setImportFile(null);
      setShowImport(false);
      fetchStudents();
    } catch (err) {
      setError(err.response?.data?.error || 'Erreur lors de l\'import');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (window.confirm('Supprimer cet étudiant ?')) {
      await api.delete(`/accounts/users/${id}/`);
      fetchStudents();
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Gestion des étudiants</h1>
        <div className="header-actions">
          <button className="btn btn-outline" onClick={() => setShowImport(true)}>Import CSV/Excel</button>
          <button className="btn btn-primary" onClick={() => setShowInvite(true)}>+ Inviter un étudiant</button>
        </div>
      </div>

      {message && <div className="alert alert-success">{message}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Nom complet</th>
              <th>Email</th>
              <th>Matricule</th>
              <th>Classe</th>
              <th>Statut</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {students.length === 0 ? (
              <tr>
                <td colSpan="6">
                  <div className="empty-state">
                    <div className="empty-icon">📚</div>
                    <h3>Aucun étudiant</h3>
                    <p>Invitez des étudiants ou importez un fichier</p>
                  </div>
                </td>
              </tr>
            ) : students.map((s) => (
              <tr key={s.id}>
                <td><strong>{s.last_name} {s.first_name}</strong></td>
                <td>{s.email}</td>
                <td>{s.matricule || '-'}</td>
                <td>{s.classe_nom || '-'}</td>
                <td>
                  {s.must_change_password ? (
                    <span className="badge badge-inactive">En attente</span>
                  ) : s.is_active ? (
                    <span className="badge badge-active">Actif</span>
                  ) : (
                    <span className="badge badge-inactive">Inactif</span>
                  )}
                </td>
                <td>
                  <button className="btn btn-sm btn-danger" onClick={() => handleDelete(s.id)}>Supprimer</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showInvite && (
        <div className="modal-overlay" onClick={() => setShowInvite(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Inviter un étudiant</h3>
              <button className="close-btn" onClick={() => setShowInvite(false)}>×</button>
            </div>
            <form onSubmit={handleInvite}>
              <div className="modal-body">
                <div className="form-row">
                  <div className="form-group">
                    <label>Prénom</label>
                    <input value={inviteForm.first_name} onChange={(e) => setInviteForm({...inviteForm, first_name: e.target.value})} required />
                  </div>
                  <div className="form-group">
                    <label>Nom</label>
                    <input value={inviteForm.last_name} onChange={(e) => setInviteForm({...inviteForm, last_name: e.target.value})} required />
                  </div>
                </div>
                <div className="form-group">
                  <label>Email</label>
                  <input type="email" value={inviteForm.email} onChange={(e) => setInviteForm({...inviteForm, email: e.target.value})} required />
                </div>
                <div className="form-group">
                  <label>Matricule (optionnel)</label>
                  <input value={inviteForm.matricule} onChange={(e) => setInviteForm({...inviteForm, matricule: e.target.value})} />
                </div>
                <div className="form-group">
                  <label>Classe</label>
                  <select value={inviteForm.classe} onChange={(e) => setInviteForm({...inviteForm, classe: e.target.value})}>
                    <option value="">-- Sélectionner une classe --</option>
                    {classes.map((c) => <option key={c.id} value={c.id}>{c.libelle} ({c.code})</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label>Mot de passe (optionnel)</label>
                  <input type="password" value={inviteForm.mot_de_passe} onChange={(e) => setInviteForm({...inviteForm, mot_de_passe: e.target.value})} placeholder="Si vide, un email d'activation sera envoyé" />
                  <small style={{ color: 'var(--gray-500)', fontSize: '0.8rem' }}>
                    Si un mot de passe est défini, l'étudiant pourra se connecter directement avec son email.
                  </small>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowInvite(false)}>Annuler</button>
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? 'Envoi...' : 'Envoyer l\'invitation'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showImport && (
        <div className="modal-overlay" onClick={() => setShowImport(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Importer des étudiants</h3>
              <button className="close-btn" onClick={() => setShowImport(false)}>×</button>
            </div>
            <form onSubmit={handleImport}>
              <div className="modal-body">
                <p style={{ color: 'var(--gray-500)', marginBottom: '16px', fontSize: '0.9rem' }}>
                  Format attendu : CSV ou Excel avec les colonnes <strong>email</strong>, <strong>nom</strong>, <strong>prenom</strong>
                </p>
                <div
                  className="file-upload"
                  onClick={() => document.getElementById('file-input').click()}
                >
                  <input
                    id="file-input"
                    type="file"
                    accept=".csv,.xlsx,.xls"
                    onChange={(e) => setImportFile(e.target.files[0])}
                  />
                  <div className="upload-icon">📁</div>
                  <p>Cliquez pour sélectionner un fichier</p>
                  {importFile && <div className="file-name">{importFile.name}</div>}
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowImport(false)}>Annuler</button>
                <button type="submit" className="btn btn-primary" disabled={loading || !importFile}>
                  {loading ? 'Import...' : 'Importer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
