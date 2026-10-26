import CodeEditor from '../CodeEditor';
import { DIFFICULTES } from './exercices';

// Aperçu complet d'un devoir pour la gestion et son auteur : consignes, ressources, exercices,
// tests (publics et cachés) et solution. Jamais utilisé pour un étudiant.

const styleTexte = { whiteSpace: 'pre-wrap', margin: '4px 0' };
const styleNote = { fontSize: '0.85rem', color: 'var(--gray-500)' };
const stylePre = { whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: '0.85rem', margin: 0 };
const styleExercice = { border: '1px solid var(--gray-200)', borderRadius: '8px', padding: '12px', marginBottom: '12px' };

export function ListeRessources({ ressources }) {
  if (!ressources || ressources.length === 0) return null;
  return (
    <ul style={{ margin: '4px 0', paddingLeft: '20px' }}>
      {ressources.map((r, i) => (
        <li key={i}><a href={r.url} target="_blank" rel="noopener noreferrer">{r.libelle}</a></li>
      ))}
    </ul>
  );
}

export function Exemples({ exemples }) {
  if (!exemples || exemples.length === 0) return null;
  return (
    <div style={{ marginTop: '8px' }}>
      <strong>Exemples</strong>
      {exemples.map((x, i) => (
        <div key={i} style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', margin: '6px 0' }}>
          <div style={{ flex: 1, minWidth: '160px' }}><div style={styleNote}>Entrée</div><pre style={stylePre}>{x.entree}</pre></div>
          <div style={{ flex: 1, minWidth: '160px' }}><div style={styleNote}>Sortie</div><pre style={stylePre}>{x.sortie}</pre></div>
          {x.explication && <div style={{ flex: 2, minWidth: '200px' }}><div style={styleNote}>Explication</div><div style={styleTexte}>{x.explication}</div></div>}
        </div>
      ))}
    </div>
  );
}

export function TableTests({ tests, avecVisibilite = false }) {
  if (!tests || tests.length === 0) return null;
  return (
    <table className="data-table" style={{ fontSize: '0.85rem', marginTop: '6px' }}>
      <thead>
        <tr><th>#</th><th>Entrée</th><th>Sortie attendue</th>{avecVisibilite && <><th>Visibilité</th><th>Poids</th></>}</tr>
      </thead>
      <tbody>
        {tests.map((t, i) => (
          <tr key={t.id ?? i}>
            <td>{i + 1}</td>
            <td><pre style={stylePre}>{t.entree}</pre></td>
            <td><pre style={stylePre}>{t.sortie_attendue}</pre></td>
            {avecVisibilite && <><td>{t.public ? 'Public' : 'Caché'}</td><td>{t.poids}</td></>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Fichiers({ titre, fichiers, langage }) {
  return (fichiers || []).map((f, i) => (
    <div key={i} style={{ marginTop: '8px' }}>
      <strong>{titre} ({f.nom})</strong>
      <CodeEditor language={langage} value={f.contenu} readOnly height="150px" />
    </div>
  ));
}

export default function ApercuDevoir({ devoir }) {
  const exercices = devoir.exercices || [];
  return (
    <div>
      {devoir.objectifs && <div><strong>Objectifs</strong><p style={styleTexte}>{devoir.objectifs}</p></div>}
      {devoir.consignes && <div><strong>Consignes</strong><p style={styleTexte}>{devoir.consignes}</p></div>}
      {devoir.ressources?.length > 0 && <div><strong>Ressources</strong><ListeRessources ressources={devoir.ressources} /></div>}
      <p style={styleNote}>
        {devoir.langage_display || devoir.langage}, {exercices.length} exercice{exercices.length > 1 ? 's' : ''}, barème : {Number(devoir.bareme)} pt{Number(devoir.bareme) > 1 ? 's' : ''}
      </p>
      {exercices.map((ex, i) => (
        <div key={ex.id ?? i} style={styleExercice}>
          <strong>Exercice {i + 1} : {ex.titre}</strong>{' '}
          <span style={styleNote}>({Number(ex.points)} pt{Number(ex.points) > 1 ? 's' : ''}, {DIFFICULTES[ex.difficulte] || ex.difficulte})</span>
          {ex.competences_detail?.length > 0 && <div style={styleNote}>Compétences : {ex.competences_detail.map((c) => c.libelle).join(', ')}</div>}
          {ex.enonce && <p style={styleTexte}>{ex.enonce}</p>}
          {ex.contraintes && <div><strong>Contraintes</strong><p style={styleTexte}>{ex.contraintes}</p></div>}
          <Exemples exemples={ex.exemples} />
          <Fichiers titre="Fichier de départ" fichiers={ex.fichiers_initiaux} langage={devoir.langage} />
          <Fichiers titre="Solution de référence" fichiers={ex.solution} langage={devoir.langage} />
          {ex.tests?.length > 0 && <div style={{ marginTop: '8px' }}><strong>Tests</strong><TableTests tests={ex.tests} avecVisibilite /></div>}
        </div>
      ))}
    </div>
  );
}
