import { useState } from 'react';
import FiltresBanque from './FiltresBanque';
import useListeBanque from './useListeBanque';
import useReferencesBanque from './useReferencesBanque';
import { filtresVides, LIBELLES_DIFFICULTE, LIBELLES_TYPE } from './banqueFiltres';

export default function SelecteurBanque({ onAjouter, onFermer }) {
  const [filtres, setFiltres] = useState(filtresVides);
  const { items, total, suivant, loading, erreur, plus } = useListeBanque(filtres);
  const { ecs, tags, erreur: erreurReferences } = useReferencesBanque();
  const [choisies, setChoisies] = useState({});

  const basculer = (fiche) => setChoisies((c) => {
    const suite = { ...c };
    if (suite[fiche.id]) delete suite[fiche.id];
    else suite[fiche.id] = fiche;
    return suite;
  });
  const nb = Object.keys(choisies).length;

  return (
    <div className="modal-overlay" style={{ zIndex: 1100 }} onClick={onFermer}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '900px', maxHeight: '90vh', overflowY: 'auto' }}>
        <div className="modal-header">
          <h3>Ajouter depuis la banque</h3>
          <button type="button" className="close-btn" onClick={onFermer}>×</button>
        </div>
        <div className="modal-body">
          {(erreur || erreurReferences) && <div className="alert alert-error">{erreur || erreurReferences}</div>}
          <FiltresBanque valeur={filtres} onChange={setFiltres} ecs={ecs} tags={tags} avecArchivees={false} />
          {loading ? (
            <div className="loading">Chargement...</div>
          ) : items.length === 0 ? (
            <p style={{ color: 'var(--gray-500)' }}>Aucune question ne correspond à ces filtres.</p>
          ) : (
            <>
              <table className="data-table">
                <thead><tr><th></th><th>Question</th><th>Type</th><th>Difficulté</th><th>Points</th><th>Version</th></tr></thead>
                <tbody>
                  {items.map((fiche) => (
                    <tr key={fiche.id} onClick={() => basculer(fiche)} style={{ cursor: 'pointer' }}>
                      <td><input type="checkbox" style={{ width: 'auto' }} checked={Boolean(choisies[fiche.id])} onChange={() => basculer(fiche)} onClick={(e) => e.stopPropagation()} /></td>
                      <td>{fiche.version.texte}</td>
                      <td>{LIBELLES_TYPE[fiche.version.type_question]}</td>
                      <td>{LIBELLES_DIFFICULTE[fiche.difficulte]}</td>
                      <td>{Number(fiche.version.points)}</td>
                      <td>v{fiche.version.numero}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px' }}>
                <span style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>{items.length} sur {total}</span>
                {suivant && <button type="button" className="btn btn-sm btn-secondary" onClick={plus}>Afficher plus</button>}
              </div>
            </>
          )}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onFermer}>Annuler</button>
          <button type="button" className="btn btn-primary" disabled={nb === 0} onClick={() => onAjouter(Object.values(choisies))}>Ajouter ({nb})</button>
        </div>
      </div>
    </div>
  );
}
