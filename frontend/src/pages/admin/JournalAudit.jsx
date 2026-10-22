import { useState, useEffect, useCallback } from 'react';
import api from '../../services/api';

const ACTIONS = [
  ['', 'Toutes les actions'],
  ['login_succes', 'Connexion réussie'],
  ['login_echec', 'Échec de connexion'],
  ['invitation', 'Invitation'],
  ['validation_admin', 'Validation administrateur'],
  ['rejet_admin', 'Rejet administrateur'],
  ['desactivation', 'Désactivation'],
  ['reactivation', 'Réactivation'],
  ['suppression_compte', 'Suppression de compte'],
  ['inscription', 'Inscription'],
  ['affectation', 'Affectation'],
  ['retrait_affectation', "Retrait d'affectation"],
  ['publication_evaluation', 'Publication'],
  ['suppression_evaluation', "Suppression d'évaluation"],
  ['saisie_note', 'Saisie de note'],
  ['modification_note', 'Modification de note'],
  ['export', 'Export'],
];

const TAILLE_PAGE = 50;

export default function JournalAudit() {
  const [entrees, setEntrees] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filtres, setFiltres] = useState({ action: '', date_debut: '', date_fin: '' });
  const [error, setError] = useState('');

  const charger = useCallback(async () => {
    setError('');
    const params = { page };
    Object.entries(filtres).forEach(([cle, valeur]) => {
      if (valeur) params[cle] = valeur;
    });
    try {
      const res = await api.get('/audit/', { params });
      setEntrees(res.data.results);
      setTotal(res.data.count);
    } catch {
      setError('Impossible de charger le journal.');
    }
  }, [page, filtres]);

  useEffect(() => {
    charger();
  }, [charger]);

  const changerFiltre = (cle, valeur) => {
    setPage(1);
    setFiltres({ ...filtres, [cle]: valeur });
  };

  const pages = Math.max(1, Math.ceil(total / TAILLE_PAGE));

  return (
    <div>
      <div className="page-header">
        <h1>Journal d'audit</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="form-row" style={{ marginBottom: '16px' }}>
        <div className="form-group">
          <label>Action</label>
          <select value={filtres.action} onChange={(e) => changerFiltre('action', e.target.value)}>
            {ACTIONS.map(([valeur, libelle]) => (
              <option key={valeur} value={valeur}>{libelle}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label>Du</label>
          <input type="date" value={filtres.date_debut} onChange={(e) => changerFiltre('date_debut', e.target.value)} />
        </div>
        <div className="form-group">
          <label>Au</label>
          <input type="date" value={filtres.date_fin} onChange={(e) => changerFiltre('date_fin', e.target.value)} />
        </div>
      </div>

      <div className="table-container">
        {entrees.length === 0 ? (
          <div className="empty-state">
            <h3>Aucune entrée</h3>
            <p>Aucune action ne correspond à ces filtres.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Date</th><th>Action</th><th>Acteur</th><th>Cible</th><th>Établissement</th><th>IP</th></tr>
            </thead>
            <tbody>
              {entrees.map((e) => (
                <tr key={e.id}>
                  <td>{new Date(e.date).toLocaleString('fr-FR')}</td>
                  <td>{e.action_libelle}</td>
                  <td>{e.acteur_nom || 'Anonyme'}</td>
                  <td>{e.cible_repr || '-'}</td>
                  <td>{e.etablissement_nom || '-'}</td>
                  <td>{e.ip || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '16px' }}>
        <button className="btn btn-sm btn-secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Précédent</button>
        <span>Page {page} sur {pages}</span>
        <button className="btn btn-sm btn-secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Suivant</button>
      </div>
    </div>
  );
}
