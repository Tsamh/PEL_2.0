import { useCallback, useEffect, useState } from 'react';
import api from '../services/api';
import { chargerTout } from '../services/pagination';
import { messageErreur } from '../services/erreurs';

const groupeVide = { code: '', libelle: '', type_groupe: 'td' };
const nomUtilisateur = (u) => [u.first_name, u.last_name].filter(Boolean).join(' ') || u.username;
const TYPES = { td: 'TD', tp: 'TP' };

export default function Groupes() {
  const [classes, setClasses] = useState([]);
  const [classeId, setClasseId] = useState('');
  const [groupes, setGroupes] = useState([]);
  const [inscrits, setInscrits] = useState([]);
  const [ouvertId, setOuvertId] = useState(null);
  const [aAjouter, setAAjouter] = useState([]);
  const [form, setForm] = useState(groupeVide);
  const [enEdition, setEnEdition] = useState(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    chargerTout('/referentiel/classes/')
      .then((c) => {
        setClasses(c);
        if (c.length) setClasseId(String(c[0].id));
      })
      .catch((err) => setError(messageErreur(err, 'Erreur lors du chargement des classes.')))
      .finally(() => setLoading(false));
  }, []);

  const chargerGroupes = useCallback(async () => {
    if (!classeId) return;
    try {
      const [g, u] = await Promise.all([
        chargerTout('/referentiel/groupes/'),
        chargerTout('/accounts/users/', { role: 'etudiant', classe: classeId }),
      ]);
      setGroupes(g.filter((x) => String(x.classe) === classeId));
      setInscrits(u);
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors du chargement des groupes.'));
    }
  }, [classeId]);

  useEffect(() => { chargerGroupes(); }, [chargerGroupes]);

  const changerClasse = (id) => {
    setClasseId(id);
    setOuvertId(null);
    setAAjouter([]);
    setEnEdition(null);
    setForm(groupeVide);
  };

  const executer = async (action, succes, defaut) => {
    setError('');
    setMessage('');
    try {
      await action();
      if (succes) setMessage(succes);
      await chargerGroupes();
    } catch (err) {
      setError(messageErreur(err, defaut));
    }
  };

  const enregistrer = (e) => {
    e.preventDefault();
    executer(async () => {
      if (enEdition) await api.patch(`/referentiel/groupes/${enEdition}/`, form);
      else await api.post('/referentiel/groupes/', { ...form, classe: Number(classeId) });
      setForm(groupeVide);
      setEnEdition(null);
    }, 'Groupe enregistré.', "Erreur lors de l'enregistrement du groupe.");
  };

  const supprimer = (g) => {
    if (!window.confirm(`Supprimer le groupe ${g.libelle} ?`)) return;
    executer(async () => {
      await api.delete(`/referentiel/groupes/${g.id}/`);
      if (ouvertId === g.id) setOuvertId(null);
    }, 'Groupe supprimé.', 'Erreur lors de la suppression du groupe.');
  };

  const ajouterMembres = (g) => executer(async () => {
    await api.post(`/referentiel/groupes/${g.id}/membres/`, { etudiants: aAjouter });
    setAAjouter([]);
  }, 'Membres ajoutés.', "Erreur lors de l'ajout des membres.");

  const retirerMembre = (g, etudiantId) => executer(
    () => api.delete(`/referentiel/groupes/${g.id}/membres/${etudiantId}/`),
    'Membre retiré.', 'Erreur lors du retrait du membre.',
  );

  const basculerAjout = (id) => setAAjouter((liste) => (liste.includes(id) ? liste.filter((x) => x !== id) : [...liste, id]));

  const ouvert = groupes.find((g) => g.id === ouvertId);
  const membresIds = new Set((ouvert?.membres_detail || []).map((m) => m.id));
  const candidats = inscrits.filter((u) => !membresIds.has(u.id));

  if (loading) return <div className="loading">Chargement...</div>;

  return (
    <div>
      <div className="page-header">
        <h1>Groupes TD/TP</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-success">{message}</div>}

      <div className="table-container" style={{ padding: '16px', marginBottom: '16px' }}>
        <div className="form-row">
          <div className="form-group">
            <label>Classe</label>
            <select value={classeId} onChange={(e) => changerClasse(e.target.value)}>
              {classes.length === 0 && <option value="">Aucune classe</option>}
              {classes.map((c) => <option key={c.id} value={c.id}>{c.code} - {c.libelle}</option>)}
            </select>
          </div>
        </div>
        {classeId && (
          <form onSubmit={enregistrer} className="form-row" style={{ alignItems: 'flex-end' }}>
            <div className="form-group">
              <label>Code</label>
              <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} required maxLength={20} />
            </div>
            <div className="form-group">
              <label>Libellé</label>
              <input value={form.libelle} onChange={(e) => setForm({ ...form, libelle: e.target.value })} required />
            </div>
            <div className="form-group">
              <label>Type</label>
              <select value={form.type_groupe} onChange={(e) => setForm({ ...form, type_groupe: e.target.value })}>
                <option value="td">Travaux dirigés</option>
                <option value="tp">Travaux pratiques</option>
              </select>
            </div>
            <div className="form-group" style={{ display: 'flex', gap: '8px' }}>
              <button type="submit" className="btn btn-primary">{enEdition ? 'Enregistrer' : 'Ajouter le groupe'}</button>
              {enEdition && <button type="button" className="btn btn-secondary" onClick={() => { setEnEdition(null); setForm(groupeVide); }}>Annuler</button>}
            </div>
          </form>
        )}
      </div>

      <div className="table-container">
        {groupes.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">👥</div>
            <h3>Aucun groupe</h3>
            <p>Créez un premier groupe TD ou TP pour cette classe.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Code</th><th>Libellé</th><th>Type</th><th>Membres</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {groupes.map((g) => (
                <tr key={g.id}>
                  <td><strong>{g.code}</strong></td>
                  <td>{g.libelle}</td>
                  <td>{TYPES[g.type_groupe] || g.type_groupe}</td>
                  <td>{g.membres_detail.length}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button className="btn btn-sm btn-primary" style={{ marginRight: '8px' }} onClick={() => { setOuvertId(ouvertId === g.id ? null : g.id); setAAjouter([]); }}>Membres</button>
                    <button className="btn btn-sm btn-secondary" style={{ marginRight: '8px' }} onClick={() => { setEnEdition(g.id); setForm({ code: g.code, libelle: g.libelle, type_groupe: g.type_groupe }); }}>Modifier</button>
                    <button className="btn btn-sm btn-danger" onClick={() => supprimer(g)}>Supprimer</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {ouvert && (
        <div className="table-container" style={{ padding: '16px', marginTop: '16px' }}>
          <h3 style={{ marginTop: 0 }}>Membres de {ouvert.libelle}</h3>
          {ouvert.membres_detail.length === 0 ? (
            <p style={{ color: 'var(--gray-500)' }}>Ce groupe n'a pas encore de membre.</p>
          ) : (
            <ul style={{ paddingLeft: '18px' }}>
              {ouvert.membres_detail.map((m) => (
                <li key={m.id} style={{ marginBottom: '4px' }}>
                  {m.nom}
                  <button className="btn btn-sm btn-secondary" style={{ marginLeft: '8px' }} onClick={() => retirerMembre(ouvert, m.id)}>Retirer</button>
                </li>
              ))}
            </ul>
          )}
          <h4>Ajouter des inscrits de la classe</h4>
          {candidats.length === 0 ? (
            <p style={{ color: 'var(--gray-500)' }}>Tous les inscrits de la classe sont déjà membres.</p>
          ) : (
            <>
              <div style={{ maxHeight: '220px', overflowY: 'auto', border: '1px solid var(--gray-200)', borderRadius: '6px', padding: '8px', marginBottom: '8px' }}>
                {candidats.map((u) => (
                  <label key={u.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'normal' }}>
                    <input type="checkbox" style={{ width: 'auto' }} checked={aAjouter.includes(u.id)} onChange={() => basculerAjout(u.id)} />
                    {nomUtilisateur(u)}
                  </label>
                ))}
              </div>
              <button className="btn btn-primary" disabled={aAjouter.length === 0} onClick={() => ajouterMembres(ouvert)}>Ajouter la sélection ({aAjouter.length})</button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
