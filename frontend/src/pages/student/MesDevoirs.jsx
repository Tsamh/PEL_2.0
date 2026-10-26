import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { chargerTout } from '../../services/pagination';
import { messageErreur } from '../../services/erreurs';
import { LANGAGES } from '../../components/devoirs/exercices';

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }) : '-');

// État d'un devoir pour l'étudiant : soumis (ou corrigé), ouvert, à venir avec sa date, fermé.
function etatDevoir(devoir, soumission) {
  const etat = devoir.etat || {};
  if (etat.soumis || soumission) {
    if (soumission?.statut === 'corrige' && soumission.score !== null && soumission.score !== undefined) {
      return ['badge-active', `Corrigé (${soumission.score} / ${Number(devoir.bareme)})`];
    }
    return ['badge-active', 'Soumis'];
  }
  if (etat.ouvert) return ['badge-active', 'Ouvert'];
  if (etat.fenetre?.prochaine_ouverture) return ['badge-pending', `À venir, le ${formatDate(etat.fenetre.prochaine_ouverture)}`];
  return ['badge-inactive', 'Fermé'];
}

export default function MesDevoirsEtudiant() {
  const [items, setItems] = useState([]);
  const [soumissions, setSoumissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([chargerTout('/programming/devoirs/'), chargerTout('/programming/soumissions/')])
      .then(([devoirs, subs]) => { setItems(devoirs); setSoumissions(subs); setError(''); })
      .catch((err) => setError(messageErreur(err, 'Erreur lors du chargement des devoirs.')))
      .finally(() => setLoading(false));
  }, []);

  const getSoumission = (devoirId) => soumissions.find((s) => s.devoir === devoirId);

  return (
    <div>
      <div className="page-header">
        <h1>Mes devoirs</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="table-container">
        {loading ? (
          <div className="loading">Chargement...</div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">💻</div>
            <h3>Aucun devoir</h3>
            <p>Aucun devoir ne vous est affecté pour le moment.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Titre</th><th>Langage</th><th>Exercices</th><th>Barème</th><th>Échéance</th><th>État</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const sub = getSoumission(item.id);
                const [classe, libelle] = etatDevoir(item, sub);
                const aRendre = item.etat?.ouvert && !item.etat?.soumis && !sub;
                return (
                  <tr key={item.id}>
                    <td><strong>{item.titre}</strong>{item.ec_libelle && <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>{item.ec_libelle}</div>}</td>
                    <td><span className="badge badge-active">{item.langage_display || LANGAGES[item.langage] || item.langage}</span></td>
                    <td>{(item.exercices || []).length}</td>
                    <td>{Number(item.bareme)} pts</td>
                    <td>{formatDate(item.etat?.fenetre?.fermeture)}</td>
                    <td><span className={`badge ${classe}`}>{libelle}</span></td>
                    <td>
                      <Link to={`/devoirs/${item.id}`} className={`btn btn-sm ${aRendre ? 'btn-primary' : 'btn-secondary'}`}>
                        {aRendre ? 'Composer' : 'Voir'}
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
