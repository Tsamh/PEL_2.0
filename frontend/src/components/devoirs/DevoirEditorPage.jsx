import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import { chargerTout } from '../../services/pagination';
import AffectationQuiz from '../quiz/AffectationQuiz';
import SessionsQuiz from '../quiz/SessionsQuiz';
import StatutValidation from '../quiz/StatutValidation';
import CaseArchives from '../CaseArchives';
import ExerciceEditeur from './ExerciceEditeur';
import { POLITIQUES_RESULTATS } from './statuts';
import { DIFFICULTES, LANGAGES, depuisApi, nouvelExercice, renommerFichiers, versPayload } from './exercices';
import { versChampLocal, badgeStatut } from '../evaluations/communs';
import { useAuth } from '../../context/AuthContext';

const MESSAGE_VERROU = 'Ce devoir a déjà des soumissions : ses exercices et ses tests ne peuvent plus être modifiés.';

const formulaireVide = {
  titre: '', objectifs: '', consignes: '', ressources: [], langage: 'python', politique_resultats: 'apres_validation',
  filiere: '', niveau: '', annee_academique: '', periode: '', ec: '',
  date_debut: '', date_fin: '', est_publie: false, resoumission_autorisee: false,
  classes: [], groupes: [], etudiants: [],
};

const separateur = <hr style={{ margin: '20px 0', border: 'none', borderTop: '1px solid var(--gray-200)' }} />;
const styleNote = { fontSize: '0.85rem', color: 'var(--gray-500)' };

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }) : '');

function periodeAffichee(item) {
  if (item.date_debut && item.date_fin) return `Du ${formatDate(item.date_debut)} au ${formatDate(item.date_fin)}`;
  if (item.date_fin) return `Jusqu'au ${formatDate(item.date_fin)}`;
  if (item.date_debut) return `À partir du ${formatDate(item.date_debut)}`;
  return '-';
}

export default function DevoirEditorPage({ titre, texteVide, sousTexteVide }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [alerte, setAlerte] = useState('');
  const [formError, setFormError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [form, setForm] = useState(formulaireVide);
  const [exercices, setExercices] = useState([]);
  const [filieres, setFilieres] = useState([]);
  const [niveaux, setNiveaux] = useState([]);
  const [annees, setAnnees] = useState([]);
  const [periodes, setPeriodes] = useState([]);
  const [ecs, setEcs] = useState([]);
  const [competences, setCompetences] = useState([]);
  const [saving, setSaving] = useState(false);
  const [archives, setArchives] = useState(false);
  const { user } = useAuth();
  const [validationRequise, setValidationRequise] = useState(false);

  const verrouille = Boolean(editingItem?.a_des_soumissions);
  const soumisAValidation = user?.role === 'enseignant' && (editingItem ? editingItem.validation_requise : validationRequise);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchItems(); }, [archives]);

  useEffect(() => {
    // Le réglage de validation est celui de l'établissement, commun aux quiz et aux devoirs.
    api.get('/quiz/quizzes/validation/').then((res) => setValidationRequise(res.data.validation_requise)).catch(() => setValidationRequise(false));
    const liste = (res) => res.data.results || res.data;
    Promise.all([
      api.get('/referentiel/filieres/'), api.get('/referentiel/niveaux/'), api.get('/referentiel/annees-academiques/'),
    ]).then(([f, n, a]) => { setFilieres(liste(f)); setNiveaux(liste(n)); setAnnees(liste(a).filter((x) => !x.archivee)); })
      .catch(() => setError('Erreur lors du chargement des listes de référence.'));
    chargerTout('/referentiel/periodes-evaluation/').then(setPeriodes).catch(() => setError('Erreur lors du chargement des périodes.'));
    chargerTout('/referentiel/ecs/').then(setEcs).catch(() => setError('Erreur lors du chargement des matières.'));
    api.get('/quiz/banque/tags/', { params: { type: 'competence' } }).then((res) => setCompetences(liste(res)))
      .catch(() => setError('Erreur lors du chargement des compétences.'));
  }, []);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const res = await api.get('/programming/devoirs/', { params: archives ? { archives: '1' } : {} });
      setItems(res.data.results || res.data);
      setError('');
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors du chargement des devoirs.'));
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditingItem(null);
    setForm(formulaireVide);
    setExercices([nouvelExercice(formulaireVide.langage)]);
    setFormError('');
    setShowForm(true);
  };

  const openEdit = (item) => {
    setEditingItem(item);
    setForm({
      titre: item.titre, objectifs: item.objectifs || '', consignes: item.consignes || '',
      ressources: (item.ressources || []).map((r) => ({ libelle: r.libelle, url: r.url })),
      langage: item.langage, politique_resultats: item.politique_resultats || 'apres_validation',
      filiere: item.filiere || '', niveau: item.niveau || '', annee_academique: item.annee_academique || '', periode: item.periode || '', ec: item.ec || '',
      date_debut: versChampLocal(item.date_debut), date_fin: versChampLocal(item.date_fin), est_publie: item.est_publie,
      resoumission_autorisee: Boolean(item.resoumission_autorisee),
      classes: item.classes || [], groupes: item.groupes || [], etudiants: item.etudiants || [],
    });
    const charges = (item.exercices || []).map(depuisApi);
    setExercices(charges.length > 0 || item.a_des_soumissions ? charges : [nouvelExercice(item.langage)]);
    setFormError('');
    setShowForm(true);
  };

  const changerLangage = (langage) => {
    setForm((f) => ({ ...f, langage }));
    if (!verrouille) {
      setExercices((es) => es.map((e) => ({
        ...e, fichiers_initiaux: renommerFichiers(e.fichiers_initiaux, langage), solution: renommerFichiers(e.solution, langage),
      })));
    }
  };

  const majExercice = (idx, patch) => setExercices((es) => es.map((e, i) => (i === idx ? { ...e, ...patch } : e)));
  const deplacerExercice = (idx, sens) => setExercices((es) => {
    const copie = [...es];
    [copie[idx], copie[idx + sens]] = [copie[idx + sens], copie[idx]];
    return copie;
  });

  const majRessource = (idx, patch) => setForm((f) => ({ ...f, ressources: f.ressources.map((r, i) => (i === idx ? { ...r, ...patch } : r)) }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setFormError('');
    const payload = {
      ...form,
      filiere: form.filiere || null,
      niveau: form.niveau || null,
      annee_academique: form.annee_academique || null,
      periode: form.periode || null,
      ec: form.ec || null,
      date_debut: form.date_debut ? new Date(form.date_debut).toISOString() : null,
      date_fin: form.date_fin ? new Date(form.date_fin).toISOString() : null,
    };
    if (!verrouille) payload.exercices = versPayload(exercices);
    try {
      setAlerte('');
      if (editingItem) {
        const res = await api.patch(`/programming/devoirs/${editingItem.id}/`, payload);
        const avant = editingItem.est_publie || editingItem.statut_validation === 'validee';
        if (avant && !res.data.est_publie && res.data.statut_validation === 'brouillon') {
          setAlerte(`Le contenu de « ${res.data.titre} » a changé : le devoir est dépublié et doit être soumis de nouveau à la validation.`);
        }
      } else {
        await api.post('/programming/devoirs/', payload);
      }
      setShowForm(false);
      fetchItems();
    } catch (err) {
      setFormError(messageErreur(err, "Erreur lors de l'enregistrement."));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Supprimer ce devoir et toutes ses soumissions ?')) return;
    try {
      await api.delete(`/programming/devoirs/${id}/`);
      fetchItems();
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors de la suppression.'));
    }
  };

  const bareme = Math.round(exercices.reduce((somme, ex) => somme + (Number(ex.points) || 0), 0) * 100) / 100;

  return (
    <div>
      <div className="page-header">
        <h1>{titre}</h1>
        {!archives && <button className="btn btn-primary" onClick={openCreate}>+ Créer un devoir</button>}
      </div>

      <CaseArchives archives={archives} onChange={setArchives} />

      {error && <div className="alert alert-error">{error}</div>}
      {alerte && <div className="alert alert-error">{alerte}</div>}

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '900px', maxHeight: '90vh', overflowY: 'auto' }}>
            <div className="modal-header">
              <h3>{editingItem ? 'Modifier le' : 'Nouveau'} devoir</h3>
              <button className="close-btn" onClick={() => setShowForm(false)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                {formError && <div className="alert alert-error">{formError}</div>}
                <h3 style={{ margin: '0 0 12px' }}>Informations</h3>
                <div className="form-group">
                  <label>Titre</label>
                  <input value={form.titre} onChange={(e) => setForm({ ...form, titre: e.target.value })} required />
                </div>
                <div className="form-group">
                  <label>Objectifs</label>
                  <textarea value={form.objectifs} onChange={(e) => setForm({ ...form, objectifs: e.target.value })} rows={2} />
                </div>
                <div className="form-group">
                  <label>Consignes</label>
                  <textarea value={form.consignes} onChange={(e) => setForm({ ...form, consignes: e.target.value })} rows={3} />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Langage</label>
                    <select value={form.langage} disabled={verrouille} onChange={(e) => changerLangage(e.target.value)}>
                      {Object.entries(LANGAGES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Filière</label>
                    <select value={form.filiere} onChange={(e) => setForm({ ...form, filiere: e.target.value })}>
                      <option value="">-- Toutes --</option>
                      {filieres.map((f) => <option key={f.id} value={f.id}>{f.libelle}</option>)}
                    </select>
                  </div>
                </div>
                <div className="form-group">
                  <label>Résultats montrés aux étudiants</label>
                  <select value={form.politique_resultats} onChange={(e) => setForm({ ...form, politique_resultats: e.target.value })}>
                    {Object.entries(POLITIQUES_RESULTATS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                  <small style={styleNote}>
                    {form.politique_resultats === 'immediate'
                      ? "L'étudiant voit la note proposée et le statut de chaque test dès la fin de la correction automatique."
                      : "L'étudiant voit sa note et le statut de chaque test une fois la note validée par l'enseignant."}
                  </small>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Niveau</label>
                    <select value={form.niveau} onChange={(e) => setForm({ ...form, niveau: e.target.value })}>
                      <option value="">-- Tous --</option>
                      {niveaux.map((n) => <option key={n.id} value={n.id}>{n.libelle}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Année académique</label>
                    <select value={form.annee_academique} onChange={(e) => setForm({ ...form, annee_academique: e.target.value })}>
                      <option value="">-- Toutes --</option>
                      {annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
                    </select>
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Période d'évaluation</label>
                    <select value={form.periode} onChange={(e) => setForm({ ...form, periode: e.target.value })}>
                      <option value="">-- Aucune --</option>
                      {periodes.map((p) => <option key={p.id} value={p.id}>{p.semestre_libelle} : {p.libelle}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Matière</label>
                    <select value={form.ec} onChange={(e) => setForm({ ...form, ec: e.target.value })}>
                      <option value="">-- Aucune --</option>
                      {ecs.map((m) => <option key={m.id} value={m.id}>{m.ue_libelle} : {m.libelle}</option>)}
                    </select>
                    {!form.ec && <small style={{ color: 'var(--gray-500)' }}>Recommandé : la matière sert aux synthèses par UE et par matière du suivi global.</small>}
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Ouverture</label>
                    <input type="datetime-local" value={form.date_debut} onChange={(e) => setForm({ ...form, date_debut: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label>Fermeture</label>
                    <input type="datetime-local" value={form.date_fin} onChange={(e) => setForm({ ...form, date_fin: e.target.value })} />
                  </div>
                </div>
                <div className="form-group">
                  <label><input type="checkbox" checked={form.resoumission_autorisee} onChange={(e) => setForm({ ...form, resoumission_autorisee: e.target.checked })} style={{ width: 'auto', marginRight: '8px' }} />Autoriser les resoumissions</label>
                  <small style={styleNote}>L'étudiant peut soumettre de nouvelles versions tant que le devoir est ouvert ; la dernière version compte.</small>
                </div>
                {(!soumisAValidation || editingItem?.statut_validation === 'validee') && (
                  <div className="form-group">
                    <label><input type="checkbox" checked={form.est_publie} onChange={(e) => setForm({ ...form, est_publie: e.target.checked })} style={{ width: 'auto', marginRight: '8px' }} />Publier</label>
                  </div>
                )}
                {soumisAValidation && (
                  <StatutValidation type="devoir" evaluation={editingItem} onChange={(devoir) => { setEditingItem(devoir); fetchItems(); }} />
                )}

                {separateur}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <h3 style={{ margin: 0 }}>Ressources ({form.ressources.length})</h3>
                  <button type="button" className="btn btn-sm btn-secondary" onClick={() => setForm((f) => ({ ...f, ressources: [...f.ressources, { libelle: '', url: '' }] }))}>+ Lien</button>
                </div>
                {form.ressources.length === 0 && <p style={styleNote}>Aucun lien. Ajoutez des liens utiles (documentation, cours) avec leur libellé.</p>}
                {form.ressources.map((r, i) => (
                  <div key={i} style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'center' }}>
                    <input placeholder="Libellé" value={r.libelle} onChange={(e) => majRessource(i, { libelle: e.target.value })} style={{ flex: 1 }} required />
                    <input type="url" placeholder="https://..." value={r.url} onChange={(e) => majRessource(i, { url: e.target.value })} style={{ flex: 2 }} required />
                    <button type="button" className="btn btn-sm btn-danger" onClick={() => setForm((f) => ({ ...f, ressources: f.ressources.filter((_, j) => j !== i) }))}>×</button>
                  </div>
                ))}

                {separateur}
                <AffectationQuiz
                  type="devoir"
                  key={editingItem?.id || 'nouveau'}
                  valeur={{ classes: form.classes, groupes: form.groupes, etudiants: form.etudiants }}
                  onChange={(cibles) => setForm((f) => ({ ...f, ...cibles }))}
                  etudiantsConnus={editingItem?.etudiants_detail || []} />
                {separateur}
                {editingItem ? <SessionsQuiz type="devoir" evaluation={editingItem} /> : <p style={styleNote}>Enregistrez le devoir pour planifier des sessions.</p>}

                {separateur}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 style={{ margin: 0 }}>Exercices ({exercices.length}), barème : {bareme} pt{bareme > 1 ? 's' : ''}</h3>
                  {!verrouille && (
                    <button type="button" className="btn btn-sm btn-primary" onClick={() => setExercices([...exercices, nouvelExercice(form.langage)])}>+ Ajouter</button>
                  )}
                </div>

                {verrouille ? (
                  <div>
                    <div className="alert alert-error">{MESSAGE_VERROU} Les autres informations restent modifiables.</div>
                    <ol>
                      {exercices.map((ex, i) => {
                        const publics = ex.tests.filter((t) => t.public).length;
                        return (
                          <li key={i}>
                            {ex.titre} ({Number(ex.points)} pt, {DIFFICULTES[ex.difficulte] || ex.difficulte}, {publics} test{publics > 1 ? 's' : ''} public{publics > 1 ? 's' : ''}, {ex.tests.length - publics} caché{ex.tests.length - publics > 1 ? 's' : ''})
                          </li>
                        );
                      })}
                    </ol>
                  </div>
                ) : exercices.length === 0 ? (
                  <p style={styleNote}>Aucun exercice. Un devoir publié doit contenir au moins un exercice.</p>
                ) : exercices.map((ex, i) => (
                  <ExerciceEditeur key={ex.cle} exercice={ex} index={i} langage={form.langage} competences={competences}
                    onChange={(patch) => majExercice(i, patch)}
                    onMonter={i > 0 ? () => deplacerExercice(i, -1) : null}
                    onDescendre={i < exercices.length - 1 ? () => deplacerExercice(i, 1) : null}
                    onRemove={() => setExercices(exercices.filter((_, j) => j !== i))} />
                ))}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>Annuler</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Enregistrement...' : 'Enregistrer'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="table-container">
        {loading ? (
          <div className="loading">Chargement...</div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">💻</div>
            <h3>{texteVide}</h3>
            <p>{sousTexteVide}</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Titre</th><th>Langage</th><th>Barème</th><th>Exercices</th><th>Statut</th><th>Période</th><th>Dates</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.titre}</strong></td>
                  <td><span className="badge badge-active">{item.langage_display || LANGAGES[item.langage] || item.langage}</span></td>
                  <td>{Number(item.bareme)} pts</td>
                  <td>{item.nb_exercices}</td>
                  <td>{badgeStatut(item)}</td>
                  <td>{item.periode_libelle || '-'}</td>
                  <td>{periodeAffichee(item)}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {!archives && <button className="btn btn-sm btn-secondary" onClick={() => openEdit(item)} style={{ marginRight: '8px' }}>Modifier</button>}
                    <Link to={`/devoirs/${item.id}`} className="btn btn-sm btn-outline" style={{ marginRight: '8px' }}>Aperçu</Link>
                    <Link to={`/devoirs/${item.id}/corrections`} className="btn btn-sm btn-primary" style={{ marginRight: '8px' }}>Corrections</Link>
                    {!archives && <button className="btn btn-sm btn-danger" onClick={() => handleDelete(item.id)}>Supprimer</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
