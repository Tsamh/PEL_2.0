import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import api from '../../services/api';
import CodeEditor from '../../components/CodeEditor';
import CaseArchives from '../../components/CaseArchives';

export default function DevoirManagement() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [form, setForm] = useState({
    titre: '', description: '', filiere: '', niveau: '', annee_academique: '', ec: '',
    langage: 'python', code_initial: '', solution: '', test_cases: [],
    date_debut: '', date_fin: '', points_max: 20, est_publie: false,
  });
  const [filieres, setFilieres] = useState([]);
  const [niveaux, setNiveaux] = useState([]);
  const [annees, setAnnees] = useState([]);
  const [ecs, setEcs] = useState([]);
  const [saving, setSaving] = useState(false);
  const [archives, setArchives] = useState(false);

  useEffect(() => {
    api.get('/referentiel/filieres/').then((res) => setFilieres(res.data.results || res.data));
    api.get('/referentiel/niveaux/').then((res) => setNiveaux(res.data.results || res.data));
    api.get('/referentiel/annees-academiques/').then((res) => setAnnees((res.data.results || res.data).filter((a) => !a.archivee)));
    api.get('/referentiel/ecs/').then((res) => setEcs(res.data.results || res.data));
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchItems(); }, [archives]);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const res = await api.get('/programming/devoirs/', { params: archives ? { archives: '1' } : {} });
      setItems(res.data.results || res.data);
    } catch (err) {
      setError('Erreur lors du chargement.');
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditingItem(null);
    setForm({ titre: '', description: '', filiere: '', niveau: '', annee_academique: '', ec: '', langage: 'python', code_initial: '', solution: '', test_cases: [], date_debut: '', date_fin: '', points_max: 20, est_publie: false });
    setShowForm(true);
  };

  const openEdit = (item) => {
    setEditingItem(item);
    setForm({
      titre: item.titre, description: item.description || '',
      filiere: item.filiere || '', niveau: item.niveau || '', annee_academique: item.annee_academique || '',
      ec: item.ec || '',
      langage: item.langage, code_initial: item.code_initial || '', solution: item.solution || '',
      test_cases: item.test_cases || [],
      date_debut: item.date_debut || null, date_fin: item.date_fin || null,
      points_max: item.points_max, est_publie: item.est_publie,
    });
    setShowForm(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...form,
        filiere: form.filiere || null,
        niveau: form.niveau || null,
        annee_academique: form.annee_academique || null,
        ec: form.ec || null,
        date_debut: form.date_debut || null,
        date_fin: form.date_fin || null,
      };
      if (editingItem) {
        await api.put(`/programming/devoirs/${editingItem.id}/`, payload);
      } else {
        await api.post('/programming/devoirs/', payload);
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
    if (window.confirm('Supprimer ce devoir ?')) {
      try {
        await api.delete(`/programming/devoirs/${id}/`);
        fetchItems();
      } catch (err) {
        setError('Erreur lors de la suppression.');
      }
    }
  };

  const langageLabel = { python: 'Python', java: 'Java', c: 'C', cpp: 'C++', javascript: 'JavaScript', autre: 'Autre' };

  return (
    <div>
      <div className="page-header">
        <h1>Devoirs de programmation</h1>
        {!archives && <button className="btn btn-primary" onClick={openCreate}>+ Créer un devoir</button>}
      </div>

      <CaseArchives archives={archives} onChange={setArchives} />

      {error && <div className="alert alert-error">{error}</div>}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '900px' }}>
            <div className="modal-header">
              <h3>{editingItem ? 'Modifier' : 'Nouveau'} devoir</h3>
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
                    <label>Matière (EC)</label>
                    <select value={form.ec} onChange={(e) => setForm({...form, ec: e.target.value})}>
                      <option value="">-- Toutes --</option>
                      {ecs.map((ec) => <option key={ec.id} value={ec.id}>{ec.libelle}</option>)}
                    </select>
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Langage</label>
                    <select value={form.langage} onChange={(e) => setForm({...form, langage: e.target.value})}>
                      {Object.entries(langageLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  </div>
                </div>
                <div className="form-group">
                  <label>Code initial (fourni aux étudiants)</label>
                  <CodeEditor language={form.langage} value={form.code_initial} onChange={(val) => setForm({...form, code_initial: val})} height="250px" />
                </div>
                <div className="form-group">
                  <label>Solution de référence</label>
                  <CodeEditor language={form.langage} value={form.solution} onChange={(val) => setForm({...form, solution: val})} height="250px" />
                </div>
                <div className="form-group">
                  <label>Cas de test (pour l'exécution automatique)</label>
                  <p style={{ color: 'var(--gray-500)', fontSize: '0.8rem', marginBottom: '8px' }}>
                    Définissez des tests avec entrée et sortie attendue. L'étudiant pourra tester son code.
                  </p>
                  {form.test_cases.map((tc, idx) => (
                    <div key={idx} style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'center' }}>
                      <input
                        placeholder="Entrée (ex: 5)"
                        value={tc.input}
                        onChange={(e) => {
                          const updated = [...form.test_cases];
                          updated[idx] = { ...updated[idx], input: e.target.value };
                          setForm({...form, test_cases: updated});
                        }}
                        style={{ flex: 1 }}
                      />
                      <span style={{ color: 'var(--gray-400)' }}>→</span>
                      <input
                        placeholder="Sortie attendue (ex: 10)"
                        value={tc.expected_output}
                        onChange={(e) => {
                          const updated = [...form.test_cases];
                          updated[idx] = { ...updated[idx], expected_output: e.target.value };
                          setForm({...form, test_cases: updated});
                        }}
                        style={{ flex: 1 }}
                      />
                      <button type="button" className="btn btn-sm btn-danger" onClick={() => {
                        setForm({...form, test_cases: form.test_cases.filter((_, i) => i !== idx)});
                      }}>×</button>
                    </div>
                  ))}
                  <button type="button" className="btn btn-sm btn-secondary" onClick={() => {
                    setForm({...form, test_cases: [...form.test_cases, { input: '', expected_output: '' }]});
                  }}>+ Ajouter un test</button>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Points max</label>
                    <input type="number" value={form.points_max} onChange={(e) => setForm({...form, points_max: parseInt(e.target.value)})} />
                  </div>
                  <div className="form-group">
                    <label>
                      <input type="checkbox" checked={form.est_publie} onChange={(e) => setForm({...form, est_publie: e.target.checked})} style={{ width: 'auto', marginRight: '8px' }} />
                      Publier
                    </label>
                  </div>
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
            <div className="empty-icon">💻</div>
            <h3>Aucun devoir</h3>
            <p>Créez un devoir de programmation pour vos étudiants.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Titre</th><th>Filière</th><th>Niveau</th><th>Langage</th><th>Points</th><th>Statut</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.titre}</strong></td>
                  <td>{item.filiere_libelle || 'Toutes'}</td>
                  <td>{item.niveau_libelle || 'Tous'}</td>
                  <td><span className="badge badge-active">{langageLabel[item.langage] || item.langage}</span></td>
                  <td>{item.points_max} pts</td>
                  <td>{item.est_publie ? <span className="badge badge-active">Publié</span> : <span className="badge badge-inactive">Brouillon</span>}</td>
                  <td>
                    {!archives && <button className="btn btn-sm btn-secondary" onClick={() => openEdit(item)} style={{marginRight: '8px'}}>Modifier</button>}
                    <Link to={`/devoirs/${item.id}/corrections`} className="btn btn-sm btn-primary" style={{marginRight: '8px'}}>Corrections</Link>
                    {!archives && <button className="btn btn-sm btn-danger" onClick={() => handleDelete(item.id)}>Supprimer</button>}
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
