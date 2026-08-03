import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';

const emptyFiliere = { code: '', libelle: '', description: '', niveau: '', ues: [] };
const emptyUE = { code: '', libelle: '', niveau: '', credits: 0, coefficient: 1 };

export default function AnneeWithFiliere() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const isSuperAdmin = user?.role === 'superadmin';

  const [annee, setAnnee] = useState({ libelle: '', date_debut: '', date_fin: '', est_active: false });
  const [filieres, setFilieres] = useState([{ ...emptyFiliere, ues: [] }]);
  const [etablissements, setEtablissements] = useState([]);
  const [selectedEtab, setSelectedEtab] = useState(user?.etablissement || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [niveaux, setNiveaux] = useState([]);

  useEffect(() => {
    if (isSuperAdmin) {
      api.get('/referentiel/etablissements/').then((res) => setEtablissements(res.data.results || res.data));
    }
    api.get('/referentiel/niveaux/').then((res) => setNiveaux(res.data.results || res.data));
  }, []);

  const addFiliere = () => {
    setFilieres([...filieres, { ...emptyFiliere, ues: [] }]);
  };

  const removeFiliere = (index) => {
    setFilieres(filieres.filter((_, i) => i !== index));
  };

  const updateFiliere = (index, field, value) => {
    const updated = [...filieres];
    updated[index] = { ...updated[index], [field]: value };
    setFilieres(updated);
  };

  const addUE = (filiereIndex) => {
    const updated = [...filieres];
    updated[filiereIndex].ues = [...updated[filiereIndex].ues, { ...emptyUE }];
    setFilieres(updated);
  };

  const removeUE = (filiereIndex, ueIndex) => {
    const updated = [...filieres];
    updated[filiereIndex].ues = updated[filiereIndex].ues.filter((_, i) => i !== ueIndex);
    setFilieres(updated);
  };

  const updateUE = (filiereIndex, ueIndex, field, value) => {
    const updated = [...filieres];
    updated[filiereIndex].ues[ueIndex] = { ...updated[filiereIndex].ues[ueIndex], [field]: value };
    setFilieres(updated);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (!annee.libelle || !annee.date_debut || !annee.date_fin) {
      setError('Veuillez remplir tous les champs de l\'année académique.');
      return;
    }

    const hasEmpty = filieres.some(f => !f.code || !f.libelle || !f.niveau);
    if (hasEmpty) {
      setError('Veuillez remplir le code, le libellé et le niveau de chaque filière.');
      return;
    }

    setSaving(true);
    try {
      const payload = {
        annee_libelle: annee.libelle,
        annee_date_debut: annee.date_debut,
        annee_date_fin: annee.date_fin,
        annee_est_active: annee.est_active,
        annee_etablissement: isSuperAdmin ? (selectedEtab || null) : user?.etablissement,
        filieres: filieres.map(f => ({
          code: f.code,
          libelle: f.libelle,
          description: f.description,
          niveau: f.niveau,
          ues: f.ues.map(ue => ({
            code: ue.code,
            libelle: ue.libelle,
            niveau: ue.niveau || f.niveau,
            credits: ue.credits,
            coefficient: ue.coefficient,
          })),
        })),
      };

      await api.post('/referentiel/annees-academiques/create_with_filieres/', payload);
      setSuccess('Année académique créée avec succès !');
      setTimeout(() => { setSuccess(''); }, 3000);
      setAnnee({ libelle: '', date_debut: '', date_fin: '', est_active: false });
      setFilieres([{ ...emptyFiliere, ues: [] }]);
    } catch (err) {
      setError(err.response?.data?.error || err.response?.data?.detail || "Erreur lors de la création.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>Créer une année avec filières</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-card">
          <h3>Année académique</h3>
          <div className="form-row">
            <div className="form-group">
              <label>Libellé</label>
              <input value={annee.libelle} onChange={(e) => setAnnee({...annee, libelle: e.target.value})} placeholder="ex: 2025-2026" required />
            </div>
            <div className="form-group">
              <label>Date début</label>
              <input type="date" value={annee.date_debut} onChange={(e) => setAnnee({...annee, date_debut: e.target.value})} required />
            </div>
            <div className="form-group">
              <label>Date fin</label>
              <input type="date" value={annee.date_fin} onChange={(e) => setAnnee({...annee, date_fin: e.target.value})} required />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>
                <input type="checkbox" checked={annee.est_active} onChange={(e) => setAnnee({...annee, est_active: e.target.checked})} style={{ width: 'auto', marginRight: '8px' }} />
                Année active
              </label>
            </div>
            {isSuperAdmin && (
              <div className="form-group" style={{ flex: 2 }}>
                <label>Établissement</label>
                <select value={selectedEtab} onChange={(e) => setSelectedEtab(e.target.value)}>
                  <option value="">-- Tous les établissements --</option>
                  {etablissements.map((e) => <option key={e.id} value={e.id}>{e.nom}</option>)}
                </select>
              </div>
            )}
            {isAdmin && (
              <div className="form-group" style={{ flex: 2 }}>
                <label>Établissement</label>
                <input value={user?.etablissement_nom || ''} disabled style={{ background: '#f3f4f6' }} />
              </div>
            )}
          </div>
        </div>

        <div className="form-card" style={{ marginTop: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ margin: 0 }}>Filières</h3>
            <button type="button" className="btn btn-secondary btn-sm" onClick={addFiliere}>+ Ajouter une filière</button>
          </div>

          {filieres.map((filiere, fi) => (
            <div key={fi} style={{ border: '1px solid #e5e7eb', borderRadius: '8px', padding: '16px', marginBottom: '16px', position: 'relative' }}>
              {filieres.length > 1 && (
                <button type="button" onClick={() => removeFiliere(fi)} style={{ position: 'absolute', top: '8px', right: '8px', background: 'none', border: 'none', color: '#dc2626', cursor: 'pointer', fontSize: '1.2rem' }}>×</button>
              )}

              <div className="form-row">
                <div className="form-group">
                  <label>Code filière</label>
                  <input value={filiere.code} onChange={(e) => updateFiliere(fi, 'code', e.target.value)} placeholder="ex: INFO" required />
                </div>
                <div className="form-group">
                  <label>Libellé filière</label>
                  <input value={filiere.libelle} onChange={(e) => updateFiliere(fi, 'libelle', e.target.value)} placeholder="ex: Informatique" required />
                </div>
                <div className="form-group">
                  <label>Niveau</label>
                  <select value={filiere.niveau} onChange={(e) => updateFiliere(fi, 'niveau', e.target.value)} required>
                    <option value="">-- Sélectionner --</option>
                    {niveaux.map((n) => <option key={n.id} value={n.code}>{n.libelle}</option>)}
                  </select>
                </div>
              </div>
              <div className="form-group">
                <label>Description</label>
                <input value={filiere.description} onChange={(e) => updateFiliere(fi, 'description', e.target.value)} placeholder="Description (optionnel)" />
              </div>

              <div style={{ marginTop: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <strong style={{ fontSize: '0.9rem', color: '#374151' }}>Unités d'enseignement</strong>
                  <button type="button" className="btn btn-sm btn-secondary" onClick={() => addUE(fi)} style={{ fontSize: '0.8rem' }}>+ Ajouter une UE</button>
                </div>

                {filiere.ues.length === 0 && (
                  <p style={{ fontSize: '0.85rem', color: '#9ca3af', fontStyle: 'italic' }}>Aucune UE ajoutée</p>
                )}

                {filiere.ues.map((ue, ui) => (
                  <div key={ui} style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr 1fr 0.5fr 0.5fr auto', gap: '8px', marginBottom: '8px', alignItems: 'end' }}>
                    <div className="form-group" style={{ margin: 0 }}>
                      <label style={{ fontSize: '0.75rem' }}>Code UE</label>
                      <input value={ue.code} onChange={(e) => updateUE(fi, ui, 'code', e.target.value)} placeholder="UE101" required />
                    </div>
                    <div className="form-group" style={{ margin: 0 }}>
                      <label style={{ fontSize: '0.75rem' }}>Libellé UE</label>
                      <input value={ue.libelle} onChange={(e) => updateUE(fi, ui, 'libelle', e.target.value)} placeholder="Mathématiques" required />
                    </div>
                    <div className="form-group" style={{ margin: 0 }}>
                      <label style={{ fontSize: '0.75rem' }}>Niveau</label>
                      <select value={ue.niveau} onChange={(e) => updateUE(fi, ui, 'niveau', e.target.value)}>
                        <option value="">-- Filière --</option>
                        {niveaux.map((n) => <option key={n.id} value={n.code}>{n.libelle}</option>)}
                      </select>
                    </div>
                    <div className="form-group" style={{ margin: 0 }}>
                      <label style={{ fontSize: '0.75rem' }}>Crédits</label>
                      <input type="number" value={ue.credits} onChange={(e) => updateUE(fi, ui, 'credits', parseInt(e.target.value) || 0)} />
                    </div>
                    <div className="form-group" style={{ margin: 0 }}>
                      <label style={{ fontSize: '0.75rem' }}>Coeff.</label>
                      <input type="number" step="0.5" value={ue.coefficient} onChange={(e) => updateUE(fi, ui, 'coefficient', parseFloat(e.target.value) || 1)} />
                    </div>
                    <button type="button" onClick={() => removeUE(fi, ui)} style={{ background: 'none', border: 'none', color: '#dc2626', cursor: 'pointer', fontSize: '1.1rem', marginBottom: '4px' }}>×</button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: '20px', display: 'flex', gap: '12px' }}>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Création...' : 'Créer l\'année et les filières'}
          </button>
        </div>
      </form>
    </div>
  );
}
