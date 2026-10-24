import { nouveauChoix, penaliteApplicable, sommePositive } from './questions';

export default function QuestionEditeur({ question: q, index, onChange, onRemove, titre, actions }) {
  const setChoix = (cIdx, patch) => onChange({ choix: q.choix.map((c, j) => (j === cIdx ? { ...c, ...patch } : c)) });
  const bonneReponseUnique = (cIdx) => onChange({ choix: q.choix.map((c, j) => ({ ...c, est_correct: j === cIdx })) });
  const ajouterChoix = (est_correct = false) => onChange({ choix: [...q.choix, nouveauChoix('', est_correct)] });
  const retirerChoix = (cIdx) => onChange({ choix: q.choix.filter((_, j) => j !== cIdx) });
  const changerType = (type) => {
    let choix = [nouveauChoix('', true), nouveauChoix()];
    if (type === 'vf') choix = [nouveauChoix('Vrai', true), nouveauChoix('Faux')];
    if (type === 'courte') choix = [nouveauChoix('', true)];
    onChange({ type_question: type, mode_notation: 'tout_ou_rien', penalite: 0, choix });
  };
  const parChoix = q.type_question === 'qcm' && q.mode_notation === 'par_choix';
  const somme = sommePositive(q.choix);

  return (
    <div style={{ border: '1px solid var(--gray-200)', borderRadius: '8px', padding: '16px', marginBottom: '12px', background: 'var(--gray-50, #f9fafb)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
        <strong style={{ color: 'var(--primary)' }}>{titre || `Question ${index + 1}`}</strong>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
          {actions}
          {onRemove && <button type="button" className="btn btn-sm btn-danger" onClick={onRemove}>Supprimer</button>}
        </div>
      </div>
      <div className="form-group">
        <label>Texte</label>
        <textarea value={q.texte} onChange={(e) => onChange({ texte: e.target.value })} rows={2} required />
      </div>
      <div className="form-row">
        <div className="form-group">
          <label>Type</label>
          <select value={q.type_question} onChange={(e) => changerType(e.target.value)}>
            <option value="qcm">QCM</option>
            <option value="vf">Vrai / Faux</option>
            <option value="courte">Réponse courte</option>
          </select>
        </div>
        <div className="form-group">
          <label>Points</label>
          <input type="number" step="0.25" min="0.25" value={q.points} onChange={(e) => onChange({ points: e.target.value })} required />
        </div>
        {q.type_question === 'qcm' && (
          <div className="form-group">
            <label>Notation</label>
            <select value={q.mode_notation} onChange={(e) => onChange({ mode_notation: e.target.value, penalite: e.target.value === 'par_choix' ? 0 : q.penalite })}>
              <option value="tout_ou_rien">Tout ou rien</option>
              <option value="par_choix">Points par choix</option>
            </select>
          </div>
        )}
        {penaliteApplicable(q) && (
          <div className="form-group">
            <label>Pénalité si faux</label>
            <input type="number" step="0.25" min="0" max={q.points} value={q.penalite} onChange={(e) => onChange({ penalite: e.target.value })} title="Points retirés pour une réponse fausse (pas pour une absence de réponse)" />
          </div>
        )}
      </div>

      {q.type_question === 'qcm' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <label style={{ fontWeight: 600 }}>Choix (cochez la ou les bonnes réponses)</label>
            <button type="button" className="btn btn-sm btn-secondary" onClick={() => ajouterChoix()}>+ Choix</button>
          </div>
          {q.choix.map((c, cIdx) => (
            <div key={cIdx} style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '6px' }}>
              <input type="checkbox" checked={parChoix ? Number(c.points) > 0 : c.est_correct} disabled={parChoix} onChange={(e) => setChoix(cIdx, { est_correct: e.target.checked })} style={{ width: 'auto' }} title={parChoix ? 'Bonne réponse : déduite des points (points supérieurs à 0)' : 'Bonne réponse'} />
              <input value={c.texte} onChange={(e) => setChoix(cIdx, { texte: e.target.value })} placeholder={`Choix ${cIdx + 1}`} style={{ flex: 1 }} required />
              {parChoix && (
                <input type="number" step="0.25" value={c.points} onChange={(e) => setChoix(cIdx, { points: e.target.value, est_correct: Number(e.target.value) > 0 })} style={{ width: '90px' }} title="Points de ce choix (négatif pour pénaliser)" />
              )}
              {q.choix.length > 2 && (
                <button type="button" className="btn btn-sm btn-danger" onClick={() => retirerChoix(cIdx)}>×</button>
              )}
            </div>
          ))}
          {parChoix && (
            <div style={{ fontSize: '0.85rem', color: somme === Number(q.points) ? 'var(--success, #16a34a)' : 'var(--danger, #dc2626)' }}>
              Somme des points positifs : {somme} sur {Number(q.points) || 0}. Un choix qui rapporte des points est une bonne réponse ; un choix faux peut avoir des points négatifs.
            </div>
          )}
        </div>
      )}

      {q.type_question === 'vf' && (
        <div style={{ display: 'flex', gap: '16px' }}>
          {q.choix.map((c, cIdx) => (
            <label key={cIdx} style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
              <input type="radio" name={`vf_${index}`} checked={c.est_correct} onChange={() => bonneReponseUnique(cIdx)} style={{ width: 'auto' }} />
              {c.texte} est la bonne réponse
            </label>
          ))}
        </div>
      )}

      {q.type_question === 'courte' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <label style={{ fontWeight: 600 }}>Réponses acceptées</label>
            <button type="button" className="btn btn-sm btn-secondary" onClick={() => ajouterChoix(true)}>+ Réponse</button>
          </div>
          {q.choix.map((c, cIdx) => (
            <div key={cIdx} style={{ display: 'flex', gap: '8px', marginBottom: '6px' }}>
              <input value={c.texte} onChange={(e) => setChoix(cIdx, { texte: e.target.value })} placeholder="Réponse acceptée" style={{ flex: 1 }} />
              {q.choix.length > 1 && (
                <button type="button" className="btn btn-sm btn-danger" onClick={() => retirerChoix(cIdx)}>×</button>
              )}
            </div>
          ))}
          <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>
            Une note est proposée automatiquement ; vous la validez ensuite dans la page Tentatives.
          </div>
        </div>
      )}

      <div className="form-group" style={{ marginTop: '12px', marginBottom: 0 }}>
        <label>Explication (affichée dans le corrigé)</label>
        <textarea value={q.explication} onChange={(e) => onChange({ explication: e.target.value })} rows={2} />
      </div>
    </div>
  );
}
