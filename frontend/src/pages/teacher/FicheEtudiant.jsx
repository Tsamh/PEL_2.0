import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import Barre from '../../components/stats/Barre';
import Courbe from '../../components/stats/Courbe';
import { nombre, pourcentage } from '../../components/stats/format';

const STATUTS = { soumis: 'Soumis', en_cours: 'En cours', non_commence: 'Non commencé' };
const formatDate = (iso) => new Date(iso).toLocaleDateString('fr-FR', { dateStyle: 'medium' });

export default function FicheEtudiant() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [fiche, setFiche] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get(`/quiz/etudiants/${id}/resultats/`)
      .then((res) => setFiche(res.data))
      .catch((err) => setError(err.response?.status === 404
        ? "Cet étudiant n'existe pas ou ne fait pas partie de votre périmètre."
        : messageErreur(err, 'Erreur lors du chargement des résultats.')));
  }, [id]);

  if (error) return <div className="alert alert-error">{error}</div>;
  if (!fiche) return <div className="loading">Chargement...</div>;

  const notes = fiche.resultats.filter((r) => r.pourcentage != null);

  return (
    <div>
      <div className="page-header">
        <h1>Résultats : {fiche.etudiant.nom}</h1>
        <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>Retour</button>
      </div>

      {notes.length > 1 && (
        <div className="table-container" style={{ padding: '16px', marginBottom: '16px' }}>
          <strong>Progression (meilleure note de chaque quiz, en %)</strong>
          <div style={{ marginTop: '8px' }}>
            <Courbe valeurs={notes.map((r) => r.pourcentage)} max={100} largeur={320} hauteur={80} libelles={notes.map((r) => `${r.titre} : ${pourcentage(r.pourcentage)}`)} />
          </div>
        </div>
      )}

      <div className="table-container">
        {fiche.resultats.length === 0 ? <div className="empty-state"><p>Aucun résultat sur vos quiz.</p></div> : (
          <table className="data-table">
            <thead><tr><th>Date</th><th>Quiz</th><th>Statut</th><th>Tentatives</th><th>Meilleure note</th><th>Part</th></tr></thead>
            <tbody>
              {fiche.resultats.map((r) => (
                <tr key={r.quiz}>
                  <td>{formatDate(r.date)}</td>
                  <td><Link to={`/quiz/${r.quiz}/statistiques`}>{r.titre}</Link></td>
                  <td>{STATUTS[r.statut]}{r.provisoire && <span className="badge badge-pending" style={{ marginLeft: '4px' }}>Provisoire</span>}</td>
                  <td>{r.nb_tentatives}</td>
                  <td>{r.score == null ? '-' : `${nombre(r.score)} / ${nombre(r.score_max)}`}</td>
                  <td>{r.pourcentage == null ? '-' : <Barre valeur={r.pourcentage} libelle={`${r.titre} : ${pourcentage(r.pourcentage)}`} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
