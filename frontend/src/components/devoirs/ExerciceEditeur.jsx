import EditeurFichiers from './EditeurFichiers';
import { BUDGET_TESTS_MS, DIFFICULTES, LIMITES, nomFichier, nouveauTest, nouvelExemple } from './exercices';

const styleBloc = { border: '1px solid var(--gray-200)', borderRadius: '8px', padding: '16px', marginBottom: '12px', background: 'var(--gray-50, #f9fafb)' };
const styleSousBloc = { border: '1px solid var(--gray-200)', borderRadius: '6px', padding: '8px', marginBottom: '8px', background: 'white' };
const styleEntete = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' };
const styleNote = { fontSize: '0.85rem', color: 'var(--gray-500)' };
const styleLigne = { display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 'normal', margin: 0 };
const styleCode = { fontFamily: 'monospace', width: '100%' };

function ZoneFichiers({ libelle, fichiers, langage, espace, onChange }) {
  return (
    <div className="form-group">
      <label>{libelle}</label>
      <EditeurFichiers fichiers={fichiers} langage={langage} espace={espace} height="200px"
        principal={langage === 'autre' ? null : nomFichier(langage)} onChange={onChange} />
    </div>
  );
}

export default function ExerciceEditeur({ exercice: e, index, langage, competences, onChange, onRemove, onMonter, onDescendre }) {
  const majListe = (cle, idx, patch) => onChange({ [cle]: e[cle].map((x, j) => (j === idx ? { ...x, ...patch } : x)) });
  const retirer = (cle, idx) => onChange({ [cle]: e[cle].filter((_, j) => j !== idx) });
  const basculerCompetence = (id) => onChange({
    competences: e.competences.includes(id) ? e.competences.filter((x) => x !== id) : [...e.competences, id],
  });
  // Compétences déjà liées mais absentes de la liste chargée : affichées pour pouvoir les retirer.
  const connues = new Set(competences.map((c) => c.id));
  const toutes = [...competences, ...(e.competences_detail || []).filter((c) => e.competences.includes(c.id) && !connues.has(c.id))];
  const budget = e.tests.length * (Number(e.limite_temps_ms) || 0);

  return (
    <div style={styleBloc}>
      <div style={{ ...styleEntete, gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
        <strong style={{ color: 'var(--primary)' }}>Exercice {index + 1}</strong>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button type="button" className="btn btn-sm btn-outline" disabled={!onMonter} onClick={onMonter} title="Monter">↑</button>
          <button type="button" className="btn btn-sm btn-outline" disabled={!onDescendre} onClick={onDescendre} title="Descendre">↓</button>
          <button type="button" className="btn btn-sm btn-danger" onClick={onRemove}>Supprimer</button>
        </div>
      </div>

      <div className="form-group">
        <label>Titre</label>
        <input value={e.titre} onChange={(ev) => onChange({ titre: ev.target.value })} required />
      </div>
      <div className="form-group">
        <label>Énoncé</label>
        <textarea value={e.enonce} onChange={(ev) => onChange({ enonce: ev.target.value })} rows={4} />
      </div>
      <div className="form-group">
        <label>Contraintes</label>
        <textarea value={e.contraintes} onChange={(ev) => onChange({ contraintes: ev.target.value })} rows={2} placeholder="Par exemple : 1 ≤ n ≤ 1000, temps limité" />
      </div>
      <div className="form-row">
        <div className="form-group">
          <label>Points</label>
          <input type="number" step="0.25" min="0.25" value={e.points} onChange={(ev) => onChange({ points: ev.target.value })} required />
        </div>
        <div className="form-group">
          <label>Difficulté</label>
          <select value={e.difficulte} onChange={(ev) => onChange({ difficulte: ev.target.value })}>
            {Object.entries(DIFFICULTES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label>Limite de temps par test (ms)</label>
          <input type="number" step="1" min={LIMITES.temps.min} max={LIMITES.temps.max} value={e.limite_temps_ms}
            onChange={(ev) => onChange({ limite_temps_ms: ev.target.value })} required />
          <small style={styleNote}>De {LIMITES.temps.min} à {LIMITES.temps.max} ms (défaut {LIMITES.temps.defaut}).</small>
        </div>
        <div className="form-group">
          <label>Limite de mémoire (Mo)</label>
          <input type="number" step="1" min={LIMITES.memoire.min} max={LIMITES.memoire.max} value={e.limite_memoire_mo}
            onChange={(ev) => onChange({ limite_memoire_mo: ev.target.value })} required />
          <small style={styleNote}>De {LIMITES.memoire.min} à {LIMITES.memoire.max} Mo (défaut {LIMITES.memoire.defaut}).</small>
        </div>
      </div>
      {budget > BUDGET_TESTS_MS && (
        <div className="alert alert-error">
          {e.tests.length} tests de {Number(e.limite_temps_ms)} ms dépassent le plafond de {BUDGET_TESTS_MS / 1000} s par exercice : réduisez la limite de temps ou le nombre de tests.
        </div>
      )}

      <div className="form-group">
        <label>Compétences</label>
        {toutes.length === 0 ? (
          <p style={styleNote}>Aucune compétence dans la banque de questions de l'établissement.</p>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px' }}>
            {toutes.map((c) => (
              <label key={c.id} style={styleLigne}>
                <input type="checkbox" style={{ width: 'auto' }} checked={e.competences.includes(c.id)} onChange={() => basculerCompetence(c.id)} />
                {c.libelle}
              </label>
            ))}
          </div>
        )}
      </div>

      <div className="form-group">
        <div style={styleEntete}>
          <label style={{ fontWeight: 600, margin: 0 }}>Exemples ({e.exemples.length})</label>
          <button type="button" className="btn btn-sm btn-secondary" onClick={() => onChange({ exemples: [...e.exemples, nouvelExemple()] })}>+ Exemple</button>
        </div>
        {e.exemples.map((x, j) => (
          <div key={j} style={styleSousBloc}>
            <div className="form-row">
              <div className="form-group">
                <label>Entrée</label>
                <textarea style={styleCode} rows={2} value={x.entree} onChange={(ev) => majListe('exemples', j, { entree: ev.target.value })} />
              </div>
              <div className="form-group">
                <label>Sortie</label>
                <textarea style={styleCode} rows={2} value={x.sortie} onChange={(ev) => majListe('exemples', j, { sortie: ev.target.value })} />
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
              <div className="form-group" style={{ flex: 1, margin: 0 }}>
                <label>Explication</label>
                <input value={x.explication} onChange={(ev) => majListe('exemples', j, { explication: ev.target.value })} />
              </div>
              <button type="button" className="btn btn-sm btn-danger" onClick={() => retirer('exemples', j)}>×</button>
            </div>
          </div>
        ))}
      </div>

      <ZoneFichiers libelle="Fichiers de départ (fournis aux étudiants)" fichiers={e.fichiers_initiaux} langage={langage} espace={`${e.cle}/depart`}
        onChange={(fichiers) => onChange({ fichiers_initiaux: fichiers })} />
      <ZoneFichiers libelle="Solution de référence (jamais montrée aux étudiants)" fichiers={e.solution} langage={langage} espace={`${e.cle}/solution`}
        onChange={(fichiers) => onChange({ solution: fichiers })} />

      <div className="form-group" style={{ marginBottom: 0 }}>
        <div style={styleEntete}>
          <label style={{ fontWeight: 600, margin: 0 }}>Tests ({e.tests.length})</label>
          <button type="button" className="btn btn-sm btn-secondary" onClick={() => onChange({ tests: [...e.tests, nouveauTest()] })}>+ Test</button>
        </div>
        <p style={{ ...styleNote, margin: '0 0 8px' }}>
          Les tests publics sont montrés à l'étudiant, qui peut y exécuter son code. Les tests cachés servent à la correction et ne lui sont jamais montrés.
        </p>
        {e.tests.map((t, j) => (
          <div key={j} style={styleSousBloc}>
            <div className="form-row">
              <div className="form-group">
                <label>Entrée</label>
                <textarea style={styleCode} rows={2} value={t.entree} onChange={(ev) => majListe('tests', j, { entree: ev.target.value })} />
              </div>
              <div className="form-group">
                <label>Sortie attendue</label>
                <textarea style={styleCode} rows={2} value={t.sortie_attendue} onChange={(ev) => majListe('tests', j, { sortie_attendue: ev.target.value })} />
              </div>
            </div>
            <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
              <label style={styleLigne}>
                <input type="checkbox" style={{ width: 'auto' }} checked={t.public} onChange={(ev) => majListe('tests', j, { public: ev.target.checked })} />
                Public
              </label>
              <label style={styleLigne}>
                Poids
                <input type="number" min="1" step="1" value={t.poids} onChange={(ev) => majListe('tests', j, { poids: ev.target.value })} style={{ width: '80px' }} required />
              </label>
              <span style={styleNote}>{t.public ? 'Visible par l\'étudiant' : 'Caché'}</span>
              <button type="button" className="btn btn-sm btn-danger" style={{ marginLeft: 'auto' }} onClick={() => retirer('tests', j)}>×</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
