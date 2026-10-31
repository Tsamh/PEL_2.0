import { useState } from 'react';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import EditeurFichiers from './EditeurFichiers';
import ResultatsExecution from './ResultatsExecution';

const styleNote = { fontSize: '0.85rem', color: 'var(--gray-500)' };
const formatDate = (iso) => (iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' }) : '');

// Versions remplacées d'une soumission, de la plus récente à la plus ancienne. Chargées à l'ouverture de la liste.
// `onReprendre(version)` absent : lecture seule ; présent : bouton « Reprendre ce code » (après confirmation).
export default function HistoriqueVersions({ soumissionId, langage, principal = null, onReprendre }) {
  const [ouverte, setOuverte] = useState(false);
  const [versions, setVersions] = useState(null);
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur] = useState('');
  const [depliees, setDepliees] = useState(() => new Set());

  const basculer = async () => {
    const ouvrir = !ouverte;
    setOuverte(ouvrir);
    if (!ouvrir) return;
    setChargement(true);
    setErreur('');
    try {
      const res = await api.get(`/programming/soumissions/${soumissionId}/versions/`);
      setVersions(res.data);
    } catch (err) {
      setErreur(messageErreur(err, "Erreur lors du chargement de l'historique."));
    } finally {
      setChargement(false);
    }
  };

  const deplier = (numero) => setDepliees((avant) => {
    const suite = new Set(avant);
    if (suite.has(numero)) suite.delete(numero); else suite.add(numero);
    return suite;
  });

  const reprendre = (version) => {
    if (!window.confirm(`Reprendre le code de la version ${version.numero} ? Votre copie de travail actuelle sera remplacée. Rien n'est soumis tant que vous ne soumettez pas une nouvelle version.`)) return;
    onReprendre(version);
  };

  return (
    <div style={{ marginTop: '12px' }}>
      <button type="button" className="btn btn-sm btn-outline" aria-expanded={ouverte} onClick={basculer}>
        {ouverte ? 'Masquer l\'historique des versions' : 'Afficher l\'historique des versions'}
      </button>
      {ouverte && (
        <div style={{ marginTop: '8px' }}>
          {chargement && <div className="loading">Chargement de l'historique...</div>}
          {erreur && <div className="alert alert-error">{erreur}</div>}
          {versions && versions.length === 0 && <p style={styleNote}>Aucune version précédente.</p>}
          {versions && versions.map((v) => {
            const ouvert = depliees.has(v.numero);
            return (
              <div key={v.numero} style={{ border: '1px solid var(--gray-200)', borderRadius: '8px', padding: '8px 12px', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                  <strong>Version {v.numero}</strong>
                  <span style={styleNote}>Rendue le {formatDate(v.date_soumission)}</span>
                  {v.soumission_auto && <span className="badge badge-inactive">Soumission automatique</span>}
                  {v.note_proposee !== null && v.note_proposee !== undefined && <span style={styleNote}>Note proposée : {Number(v.note_proposee)}</span>}
                  <span style={{ marginLeft: 'auto', display: 'flex', gap: '8px' }}>
                    <button type="button" className="btn btn-sm btn-secondary" aria-expanded={ouvert} onClick={() => deplier(v.numero)}>
                      {ouvert ? 'Replier' : 'Voir le code'}
                    </button>
                    {onReprendre && <button type="button" className="btn btn-sm btn-primary" onClick={() => reprendre(v)}>Reprendre ce code</button>}
                  </span>
                </div>
                {ouvert && v.reponses.map((r) => (
                  <div key={r.exercice} style={{ marginTop: '10px' }}>
                    <div style={{ fontWeight: 600, marginBottom: '4px' }}>{r.exercice_titre || `Exercice ${r.exercice}`}</div>
                    {r.fichiers.length === 0 ? (
                      <p style={styleNote}>Aucun fichier.</p>
                    ) : (
                      <EditeurFichiers fichiers={r.fichiers} langage={langage} principal={principal} readOnly height="200px"
                        espace={`version-${soumissionId}-${v.numero}-${r.exercice}`} />
                    )}
                    {r.correction && <div style={{ marginTop: '6px' }}><ResultatsExecution execution={r.correction} /></div>}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
