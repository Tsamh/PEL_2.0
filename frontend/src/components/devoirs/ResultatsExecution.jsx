import { STATUTS_EXECUTION, executionActive, libelleTest, resumeResultats } from './statuts';

// Affichage d'une exécution `{type, statut, message, compilation, resultats}` : console d'un essai libre,
// ou tableau des tests. Les champs absents (tests cachés vus par l'étudiant) ne sont pas affichés.

const styleNote = { fontSize: '0.85rem', color: 'var(--gray-500)' };
const stylePre = { background: 'var(--gray-900, #1a1a1a)', color: '#e2e8f0', padding: '12px', borderRadius: '8px', overflow: 'auto', fontFamily: 'monospace', fontSize: '0.85rem', maxHeight: '240px', whiteSpace: 'pre-wrap', margin: '4px 0 8px' };
const stylePreCellule = { margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: '0.8rem', maxHeight: '120px', overflow: 'auto' };

export function BadgeTest({ statut }) {
  return <span className={`badge ${statut === 'OK' ? 'badge-active' : 'badge-inactive'}`}>{libelleTest(statut)}</span>;
}

function Console({ titre, texte }) {
  if (!texte) return null;
  return <div><div style={styleNote}>{titre}</div><pre style={stylePre}>{texte}</pre></div>;
}

const a = (r, champ) => Object.prototype.hasOwnProperty.call(r, champ);

function TableResultats({ resultats }) {
  const avecEntree = resultats.some((r) => a(r, 'entree'));
  const avecSortie = resultats.some((r) => a(r, 'sortie'));
  const avecErreurs = resultats.some((r) => r.erreurs);
  return (
    <table className="data-table" style={{ fontSize: '0.85rem', marginTop: '6px' }}>
      <thead>
        <tr>
          <th>#</th><th>Statut</th><th>Temps</th>
          {avecEntree && <><th>Entrée</th><th>Sortie attendue</th></>}
          {avecSortie && <th>Sortie obtenue</th>}
          {avecErreurs && <th>Erreurs</th>}
        </tr>
      </thead>
      <tbody>
        {resultats.map((r, i) => {
          const cache = r.public === false || (!a(r, 'entree') && !a(r, 'public'));
          return (
            <tr key={i}>
              <td>{i + 1}{cache && <div style={styleNote}>caché</div>}</td>
              <td><BadgeTest statut={r.statut} /></td>
              <td style={{ whiteSpace: 'nowrap' }}>{r.temps_ms !== null && r.temps_ms !== undefined ? `${r.temps_ms} ms` : '-'}</td>
              {avecEntree && (
                <>
                  <td><pre style={stylePreCellule}>{r.entree ?? ''}</pre></td>
                  <td><pre style={stylePreCellule}>{r.sortie_attendue ?? ''}</pre></td>
                </>
              )}
              {avecSortie && <td><pre style={stylePreCellule}>{r.sortie ?? ''}</pre></td>}
              {avecErreurs && <td><pre style={stylePreCellule}>{r.erreurs || ''}</pre></td>}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function ResultatsExecution({ execution }) {
  if (!execution) return null;
  if (executionActive(execution.statut)) {
    return <div className="loading">{execution.statut === 'en_attente' ? "En attente d'exécution..." : 'Exécution en cours...'}</div>;
  }
  if (execution.statut === 'erreur') {
    return <div className="alert alert-error">{execution.message || STATUTS_EXECUTION.erreur}</div>;
  }
  const resultats = execution.resultats || [];
  if (execution.type === 'essai_run') {
    const r = resultats[0];
    return (
      <div>
        {r && (
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '6px' }}>
            <BadgeTest statut={r.statut} />
            {r.temps_ms !== null && r.temps_ms !== undefined && <span style={styleNote}>Durée : {r.temps_ms} ms</span>}
          </div>
        )}
        <Console titre="Compilation" texte={execution.compilation} />
        <Console titre="Sortie" texte={r?.sortie} />
        <Console titre="Erreurs" texte={r?.erreurs} />
        {r && !r.sortie && !r.erreurs && !execution.compilation && <p style={styleNote}>Aucune sortie.</p>}
      </div>
    );
  }
  return (
    <div>
      <Console titre="Compilation" texte={execution.compilation} />
      {resultats.length === 0 ? (
        <p style={styleNote}>Aucun test pour cet exercice.</p>
      ) : (
        <>
          <strong>{resumeResultats(resultats)}</strong>
          <TableResultats resultats={resultats} />
        </>
      )}
    </div>
  );
}
