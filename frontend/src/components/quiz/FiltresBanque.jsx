import { useState } from 'react';
import { LIBELLES_DIFFICULTE, LIBELLES_TYPE } from './banqueFiltres';

export default function FiltresBanque({ valeur, onChange, ecs, tags, avecArchivees = true }) {
  const [recherche, setRecherche] = useState(valeur.recherche);
  const maj = (patch) => onChange({ ...valeur, ...patch });
  const appliquerRecherche = () => { if (recherche !== valeur.recherche) maj({ recherche }); };

  return (
    <form onSubmit={(e) => { e.preventDefault(); appliquerRecherche(); }} style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'flex-end', marginBottom: '12px' }}>
      <div className="form-group" style={{ margin: 0, flex: '1 1 220px' }}>
        <label>Recherche</label>
        <input value={recherche} onChange={(e) => setRecherche(e.target.value)} onBlur={appliquerRecherche} placeholder="Texte de la question" />
      </div>
      <div className="form-group" style={{ margin: 0 }}>
        <label>Matière</label>
        <select value={valeur.ec} onChange={(e) => maj({ ec: e.target.value })}>
          <option value="">Toutes</option>
          {ecs.map((ec) => <option key={ec.id} value={ec.id}>{ec.code} - {ec.libelle}</option>)}
        </select>
      </div>
      <div className="form-group" style={{ margin: 0 }}>
        <label>Type</label>
        <select value={valeur.type_question} onChange={(e) => maj({ type_question: e.target.value })}>
          <option value="">Tous</option>
          {Object.entries(LIBELLES_TYPE).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      <div className="form-group" style={{ margin: 0 }}>
        <label>Difficulté</label>
        <select value={valeur.difficulte} onChange={(e) => maj({ difficulte: e.target.value })}>
          <option value="">Toutes</option>
          {Object.entries(LIBELLES_DIFFICULTE).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      <div className="form-group" style={{ margin: 0 }}>
        <label>Chapitre</label>
        <select value={valeur.chapitre} onChange={(e) => maj({ chapitre: e.target.value })}>
          <option value="">Tous</option>
          {tags.chapitre.map((t) => <option key={t.id} value={t.id}>{t.libelle}</option>)}
        </select>
      </div>
      <div className="form-group" style={{ margin: 0 }}>
        <label>Compétence</label>
        <select value={valeur.competence} onChange={(e) => maj({ competence: e.target.value })}>
          <option value="">Toutes</option>
          {tags.competence.map((t) => <option key={t.id} value={t.id}>{t.libelle}</option>)}
        </select>
      </div>
      <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 'normal' }}>
        <input type="checkbox" style={{ width: 'auto' }} checked={valeur.mes_questions} onChange={(e) => maj({ mes_questions: e.target.checked })} />
        Mes questions
      </label>
      {avecArchivees && (
        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 'normal' }}>
          <input type="checkbox" style={{ width: 'auto' }} checked={valeur.archivee} onChange={(e) => maj({ archivee: e.target.checked })} />
          Archivées
        </label>
      )}
      <button type="submit" className="btn btn-secondary">Filtrer</button>
    </form>
  );
}
