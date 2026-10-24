import { useState } from 'react';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import { telecharger } from '../../services/telechargement';
import QuestionEditeur from '../../components/quiz/QuestionEditeur';
import FiltresBanque from '../../components/quiz/FiltresBanque';
import useListeBanque from '../../components/quiz/useListeBanque';
import useReferencesBanque from '../../components/quiz/useReferencesBanque';
import { filtresVides, requeteBanque, LIBELLES_DIFFICULTE, LIBELLES_TYPE } from '../../components/quiz/banqueFiltres';
import { depuisApi, nouvelleQuestion, versContenu } from '../../components/quiz/questions';

const ficheVide = { ec: '', partagee: false, difficulte: 'moyen', chapitres: [], competences: [] };
const formatDate = (iso) => new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });

function ChampTags({ id, libelles, onChange, suggestions, placeholder }) {
  const [saisie, setSaisie] = useState('');
  const ajouter = () => {
    const libelle = saisie.trim();
    if (libelle && !libelles.some((l) => l.toLowerCase() === libelle.toLowerCase())) onChange([...libelles, libelle]);
    setSaisie('');
  };
  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '6px' }}>
        {libelles.map((l) => (
          <span key={l} className="badge badge-active" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            {l}
            <button type="button" aria-label={`Retirer ${l}`} onClick={() => onChange(libelles.filter((x) => x !== l))} style={{ border: 'none', background: 'none', cursor: 'pointer', padding: 0 }}>×</button>
          </span>
        ))}
      </div>
      <input list={id} value={saisie} placeholder={placeholder}
        onChange={(e) => setSaisie(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); ajouter(); } }}
        onBlur={ajouter} />
      <datalist id={id}>{suggestions.map((t) => <option key={t.id} value={t.libelle} />)}</datalist>
    </div>
  );
}

function ImportBanque({ ecs, onTermine, onFermer, onModele }) {
  const [fichier, setFichier] = useState(null);
  const [ec, setEc] = useState('');
  const [rapport, setRapport] = useState(null);
  const [erreur, setErreur] = useState('');
  const [enCours, setEnCours] = useState(false);

  const envoyer = async (apercu) => {
    const donnees = new FormData();
    donnees.append('fichier', fichier);
    if (ec) donnees.append('ec', ec);
    if (apercu) donnees.append('apercu', '1');
    setEnCours(true);
    setErreur('');
    try {
      const res = await api.post('/quiz/banque/import/', donnees, { headers: { 'Content-Type': 'multipart/form-data' } });
      if (apercu) setRapport(res.data);
      else onTermine(res.data.crees);
    } catch (err) {
      if (err.response?.data?.lignes) {
        setRapport(err.response.data);
        setErreur('Le fichier contient des erreurs : corrigez-les puis vérifiez à nouveau.');
      } else {
        setErreur(messageErreur(err, "Erreur lors de l'import."));
      }
    } finally {
      setEnCours(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onFermer}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '760px', maxHeight: '90vh', overflowY: 'auto' }}>
        <div className="modal-header">
          <h3>Importer des questions (CSV)</h3>
          <button className="close-btn" onClick={onFermer}>×</button>
        </div>
        <div className="modal-body">
          {erreur && <div className="alert alert-error">{erreur}</div>}
          <p style={{ fontSize: '0.9rem' }}>
            Fichier CSV en UTF-8, séparateur point-virgule.{' '}
            <button type="button" className="btn btn-sm btn-outline" onClick={onModele}>Télécharger le modèle</button>
          </p>
          <div className="form-row">
            <div className="form-group">
              <label>Fichier</label>
              <input type="file" accept=".csv,text/csv" onChange={(e) => { setFichier(e.target.files[0] || null); setRapport(null); }} />
            </div>
            <div className="form-group">
              <label>Matière des questions importées</label>
              <select value={ec} onChange={(e) => { setEc(e.target.value); setRapport(null); }}>
                <option value="">Aucune</option>
                {ecs.map((m) => <option key={m.id} value={m.id}>{m.code} - {m.libelle}</option>)}
              </select>
            </div>
          </div>
          {rapport && (
            <div>
              <p><strong>{rapport.valides}</strong> ligne(s) valide(s), <strong>{rapport.invalides}</strong> en erreur.</p>
              <table className="data-table">
                <thead><tr><th>Ligne</th><th>Question</th><th>Statut</th></tr></thead>
                <tbody>
                  {rapport.lignes.map((l) => (
                    <tr key={l.ligne}>
                      <td>{l.ligne}</td>
                      <td>{l.resume}</td>
                      <td>{l.ok ? <span className="badge badge-active">OK</span> : <span style={{ color: 'var(--danger, #dc2626)' }}>{l.erreurs.join(' ; ')}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" onClick={onFermer}>Annuler</button>
          <button type="button" className="btn btn-secondary" disabled={!fichier || enCours} onClick={() => envoyer(true)}>Vérifier</button>
          <button type="button" className="btn btn-primary" disabled={!rapport || rapport.invalides > 0 || rapport.valides === 0 || enCours} onClick={() => envoyer(false)}>Importer</button>
        </div>
      </div>
    </div>
  );
}

export default function BanqueQuestions() {
  const [filtres, setFiltres] = useState(filtresVides);
  const { items, total, suivant, loading, erreur: erreurListe, recharger, plus } = useListeBanque(filtres);
  const { ecs, tags, erreur: erreurReferences, rechargerTags } = useReferencesBanque();
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [edition, setEdition] = useState(null);
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);
  const [historique, setHistorique] = useState(null);
  const [importOuvert, setImportOuvert] = useState(false);

  const signaler = (texte) => { setError(''); setMessage(texte); };
  const echec = (err, defaut) => { setMessage(''); setError(messageErreur(err, defaut)); };

  const ouvrirCreation = () => { setFormError(''); setEdition({ id: null, fiche: ficheVide, question: nouvelleQuestion() }); };
  const ouvrirEdition = (item) => {
    setFormError('');
    setEdition({
      id: item.id,
      fiche: {
        ec: item.ec || '', partagee: item.partagee, difficulte: item.difficulte,
        chapitres: item.tags.filter((t) => t.type === 'chapitre').map((t) => t.libelle),
        competences: item.tags.filter((t) => t.type === 'competence').map((t) => t.libelle),
      },
      question: depuisApi(item.version),
    });
  };
  const majFiche = (patch) => setEdition((e) => ({ ...e, fiche: { ...e.fiche, ...patch } }));
  const majQuestion = (patch) => setEdition((e) => ({ ...e, question: { ...e.question, ...patch } }));

  const enregistrer = async (e) => {
    e.preventDefault();
    setSaving(true);
    setFormError('');
    const corps = { ...edition.fiche, ec: edition.fiche.ec || null, contenu: versContenu(edition.question) };
    try {
      if (edition.id) await api.patch(`/quiz/banque/${edition.id}/`, corps);
      else await api.post('/quiz/banque/', corps);
      setEdition(null);
      signaler('Question enregistrée.');
      recharger();
      rechargerTags();
    } catch (err) {
      setFormError(messageErreur(err, "Erreur lors de l'enregistrement."));
    } finally {
      setSaving(false);
    }
  };

  const archiver = async (item) => {
    if (!window.confirm("Archiver cette question ? Les quiz qui l'utilisent gardent leur copie.")) return;
    try {
      await api.delete(`/quiz/banque/${item.id}/`);
      signaler('Question archivée.');
      recharger();
    } catch (err) {
      echec(err, "Erreur lors de l'archivage.");
    }
  };
  const desarchiver = async (item) => {
    try {
      await api.patch(`/quiz/banque/${item.id}/`, { archivee: false });
      signaler('Question rétablie.');
      recharger();
    } catch (err) {
      echec(err, 'Erreur lors du rétablissement.');
    }
  };
  const ouvrirHistorique = async (item) => {
    try {
      const res = await api.get(`/quiz/banque/${item.id}/versions/`);
      setHistorique({ fiche: item, versions: res.data });
    } catch (err) {
      echec(err, "Erreur lors du chargement de l'historique.");
    }
  };
  const restaurer = async (numero) => {
    try {
      await api.post(`/quiz/banque/${historique.fiche.id}/restaurer/`, { numero });
      setHistorique(null);
      signaler(`La version ${numero} est redevenue la version courante.`);
      recharger();
    } catch (err) {
      echec(err, 'Erreur lors de la restauration.');
    }
  };
  const exporter = () => telecharger(`/quiz/banque/export/?${requeteBanque(filtres)}`, 'banque_questions.csv')
    .catch((err) => echec(err, "Erreur lors de l'export."));
  const modele = () => telecharger('/quiz/banque/modele/', 'modele_banque_questions.csv')
    .catch((err) => echec(err, 'Erreur lors du téléchargement du modèle.'));

  const erreurAffichee = error || erreurListe || erreurReferences;

  return (
    <div>
      <div className="page-header">
        <h1>Banque de questions</h1>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button className="btn btn-secondary" onClick={() => setImportOuvert(true)}>Importer</button>
          <button className="btn btn-secondary" onClick={exporter}>Exporter</button>
          <button className="btn btn-primary" onClick={ouvrirCreation}>+ Nouvelle question</button>
        </div>
      </div>

      {erreurAffichee && <div className="alert alert-error">{erreurAffichee}</div>}
      {message && <div className="alert alert-success">{message}</div>}

      <FiltresBanque valeur={filtres} onChange={setFiltres} ecs={ecs} tags={tags} />

      <div className="table-container">
        {loading ? (
          <div className="loading">Chargement...</div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🗂️</div>
            <h3>Aucune question</h3>
            <p>Créez une question, importez un fichier CSV ou enregistrez une question depuis un quiz.</p>
          </div>
        ) : (
          <>
            <table className="data-table">
              <thead>
                <tr><th>Question</th><th>Type</th><th>Difficulté</th><th>Tags</th><th>Version</th><th>Auteur</th><th>Partage</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td style={{ maxWidth: '320px' }}>
                      <strong>{item.version.texte.length > 120 ? `${item.version.texte.slice(0, 120)}...` : item.version.texte}</strong>
                      {item.ec_libelle && <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>{item.ec_libelle}</div>}
                    </td>
                    <td>{LIBELLES_TYPE[item.version.type_question]}</td>
                    <td>{LIBELLES_DIFFICULTE[item.difficulte]}</td>
                    <td>{item.tags.map((t) => <span key={t.id} className="badge badge-inactive" style={{ marginRight: '4px' }}>{t.libelle}</span>)}</td>
                    <td>v{item.version.numero}</td>
                    <td>{item.auteur_nom}</td>
                    <td>{item.partagee ? 'Partagée' : 'Privée'}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      {item.modifiable && !item.archivee && <button className="btn btn-sm btn-secondary" style={{ marginRight: '6px' }} onClick={() => ouvrirEdition(item)}>Modifier</button>}
                      <button className="btn btn-sm btn-outline" style={{ marginRight: '6px' }} onClick={() => ouvrirHistorique(item)}>Historique</button>
                      {item.modifiable && (item.archivee
                        ? <button className="btn btn-sm btn-secondary" onClick={() => desarchiver(item)}>Rétablir</button>
                        : <button className="btn btn-sm btn-danger" onClick={() => archiver(item)}>Archiver</button>)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>{items.length} sur {total}</span>
              {suivant && <button className="btn btn-sm btn-secondary" onClick={plus}>Afficher plus</button>}
            </div>
          </>
        )}
      </div>

      {edition && (
        <div className="modal-overlay" onClick={() => setEdition(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '820px', maxHeight: '90vh', overflowY: 'auto' }}>
            <div className="modal-header">
              <h3>{edition.id ? 'Modifier la' : 'Nouvelle'} question</h3>
              <button className="close-btn" onClick={() => setEdition(null)}>×</button>
            </div>
            <form onSubmit={enregistrer}>
              <div className="modal-body">
                {formError && <div className="alert alert-error">{formError}</div>}
                <div className="form-row">
                  <div className="form-group">
                    <label>Matière</label>
                    <select value={edition.fiche.ec} onChange={(e) => majFiche({ ec: e.target.value })}>
                      <option value="">Aucune</option>
                      {ecs.map((m) => <option key={m.id} value={m.id}>{m.code} - {m.libelle}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Difficulté</label>
                    <select value={edition.fiche.difficulte} onChange={(e) => majFiche({ difficulte: e.target.value })}>
                      {Object.entries(LIBELLES_DIFFICULTE).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Chapitres</label>
                    <ChampTags id="chapitres-connus" libelles={edition.fiche.chapitres} onChange={(chapitres) => majFiche({ chapitres })} suggestions={tags.chapitre} placeholder="Ajouter un chapitre puis Entrée" />
                  </div>
                  <div className="form-group">
                    <label>Compétences</label>
                    <ChampTags id="competences-connues" libelles={edition.fiche.competences} onChange={(competences) => majFiche({ competences })} suggestions={tags.competence} placeholder="Ajouter une compétence puis Entrée" />
                  </div>
                </div>
                <div className="form-group">
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 'normal' }}>
                    <input type="checkbox" style={{ width: 'auto' }} checked={edition.fiche.partagee} onChange={(e) => majFiche({ partagee: e.target.checked })} />
                    Partager avec les enseignants de cette matière (lecture et copie dans leurs quiz)
                  </label>
                </div>
                <QuestionEditeur question={edition.question} index={0} titre="Contenu" onChange={majQuestion} />
                {edition.id && <p style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>Modifier le contenu crée une nouvelle version ; les quiz qui utilisent cette question ne changent pas.</p>}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setEdition(null)}>Annuler</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Enregistrement...' : 'Enregistrer'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {historique && (
        <div className="modal-overlay" onClick={() => setHistorique(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '720px', maxHeight: '90vh', overflowY: 'auto' }}>
            <div className="modal-header">
              <h3>Historique des versions</h3>
              <button className="close-btn" onClick={() => setHistorique(null)}>×</button>
            </div>
            <div className="modal-body">
              <table className="data-table">
                <thead><tr><th>Version</th><th>Date</th><th>Par</th><th>Texte</th><th></th></tr></thead>
                <tbody>
                  {historique.versions.map((v, i) => (
                    <tr key={v.id}>
                      <td>v{v.numero}{i === 0 && ' (courante)'}</td>
                      <td>{formatDate(v.date)}</td>
                      <td>{v.creee_par_nom}</td>
                      <td>{v.texte}</td>
                      <td>{i > 0 && historique.fiche.modifiable && <button className="btn btn-sm btn-secondary" onClick={() => restaurer(v.numero)}>Restaurer</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {importOuvert && (
        <ImportBanque ecs={ecs} onModele={modele} onFermer={() => setImportOuvert(false)}
          onTermine={(crees) => { setImportOuvert(false); signaler(`${crees} question(s) importée(s).`); recharger(); rechargerTags(); }} />
      )}
    </div>
  );
}
