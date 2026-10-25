import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import AffectationQuiz from './AffectationQuiz';
import AccesQuiz from './AccesQuiz';
import { resumeCibles } from './cibles';
import QuestionEditeur from './QuestionEditeur';
import SelecteurBanque from './SelecteurBanque';
import { depuisApi, nouvelleQuestion, versContenu } from './questions';

const formulaireVide = {
  titre: '', description: '', filiere: '', niveau: '', annee_academique: '',
  duree_minutes: 30, date_debut: '', date_fin: '', est_publie: false,
  tentatives_autorisees: 1, reprise_autorisee: true, publication_resultats: 'immediate', afficher_corrige: false,
  classes: [], groupes: [], etudiants: [],
};

// Date ISO du serveur vers le format d'un champ <input type="datetime-local">.
function versChampLocal(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function QuizEditorPage({ titre, texteVide, sousTexteVide }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [formMessage, setFormMessage] = useState('');
  const [selecteurOuvert, setSelecteurOuvert] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingItem, setEditingItem] = useState(null);
  const [form, setForm] = useState(formulaireVide);
  const [questions, setQuestions] = useState([]);
  const [filieres, setFilieres] = useState([]);
  const [niveaux, setNiveaux] = useState([]);
  const [annees, setAnnees] = useState([]);
  const [saving, setSaving] = useState(false);

  const verrouille = Boolean(editingItem?.a_des_tentatives);

  useEffect(() => {
    fetchItems();
    const liste = (res) => res.data.results || res.data;
    Promise.all([
      api.get('/referentiel/filieres/'), api.get('/referentiel/niveaux/'), api.get('/referentiel/annees-academiques/'),
    ]).then(([f, n, a]) => { setFilieres(liste(f)); setNiveaux(liste(n)); setAnnees(liste(a)); })
      .catch(() => setError('Erreur lors du chargement des listes de référence.'));
  }, []);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const res = await api.get('/quiz/quizzes/');
      setItems(res.data.results || res.data);
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors du chargement des quiz.'));
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditingItem(null);
    setForm(formulaireVide);
    setQuestions([nouvelleQuestion()]);
    setFormError('');
    setFormMessage('');
    setShowForm(true);
  };

  const openEdit = (item) => {
    setEditingItem(item);
    setForm({
      titre: item.titre, description: item.description || '',
      filiere: item.filiere || '', niveau: item.niveau || '', annee_academique: item.annee_academique || '',
      duree_minutes: item.duree_minutes, date_debut: versChampLocal(item.date_debut), date_fin: versChampLocal(item.date_fin),
      est_publie: item.est_publie, tentatives_autorisees: item.tentatives_autorisees,
      reprise_autorisee: item.reprise_autorisee, publication_resultats: item.publication_resultats,
      afficher_corrige: item.afficher_corrige,
      classes: item.classes || [], groupes: item.groupes || [], etudiants: item.etudiants || [],
    });
    const chargees = (item.questions || []).map((q) => ({
      ...depuisApi(q), source: q.source, version_source: q.version_source, fiche_source: q.fiche_source,
      version_courante: q.version_courante, modifiee_localement: q.modifiee_localement,
    }));
    setQuestions(chargees.length > 0 ? chargees : [nouvelleQuestion()]);
    setFormError('');
    setFormMessage('');
    setShowForm(true);
  };

  const majQuestion = (idx, patch) => setQuestions((qs) => qs.map((q, i) => (i === idx ? { ...q, ...patch } : q)));

  // Questions de la banque copiées dans le quiz : contenu de la version courante, lien conservé dans `source`.
  const versQuestionLiee = (fiche) => ({
    ...depuisApi(fiche.version), source: fiche.version.id, version_source: fiche.version.numero,
    fiche_source: fiche.id, version_courante: fiche.version.numero, modifiee_localement: false,
  });

  const ajouterDepuisBanque = (fiches) => {
    setQuestions((qs) => [...qs, ...fiches.map(versQuestionLiee)]);
    setSelecteurOuvert(false);
    setFormMessage(`${fiches.length} question(s) ajoutée(s). Elles seront enregistrées avec le quiz.`);
  };

  const mettreAJourDepuisBanque = async (idx) => {
    setFormError('');
    try {
      const res = await api.get(`/quiz/banque/${questions[idx].fiche_source}/`);
      majQuestion(idx, versQuestionLiee(res.data));
      setFormMessage('Question mise à jour avec la dernière version de la banque. Enregistrez le quiz pour confirmer.');
    } catch (err) {
      setFormError(messageErreur(err, "La question d'origine n'est plus disponible dans la banque."));
    }
  };

  const enregistrerDansBanque = async (idx) => {
    setFormError('');
    try {
      const res = await api.post('/quiz/banque/', { contenu: versContenu(questions[idx]) });
      majQuestion(idx, versQuestionLiee(res.data));
      setFormMessage('Question enregistrée dans la banque. Enregistrez le quiz pour garder le lien.');
    } catch (err) {
      setFormError(messageErreur(err, "Erreur lors de l'enregistrement dans la banque."));
    }
  };

  const actionsQuestion = (q, idx) => (
    <>
      {q.source && <span className="badge badge-inactive">Banque v{q.version_source}</span>}
      {q.modifiee_localement && <span className="badge badge-pending">Modifiée localement</span>}
      {q.source && q.version_courante > q.version_source && (
        <button type="button" className="btn btn-sm btn-outline" onClick={() => mettreAJourDepuisBanque(idx)}>Mettre à jour (v{q.version_courante})</button>
      )}
      {!q.source && (
        <button type="button" className="btn btn-sm btn-outline" onClick={() => enregistrerDansBanque(idx)}>Enregistrer dans la banque</button>
      )}
    </>
  );

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setFormError('');
    const payload = {
      ...form,
      filiere: form.filiere || null,
      niveau: form.niveau || null,
      annee_academique: form.annee_academique || null,
      date_debut: form.date_debut ? new Date(form.date_debut).toISOString() : null,
      date_fin: form.date_fin ? new Date(form.date_fin).toISOString() : null,
    };
    if (!verrouille) {
      payload.questions = questions.map((q, i) => {
        const contenu = versContenu(q);
        return { ...contenu, ordre: i + 1, choix: contenu.choix.map((c, j) => ({ ...c, ordre: j + 1 })), source: q.source || null };
      });
    }
    try {
      if (editingItem) {
        await api.patch(`/quiz/quizzes/${editingItem.id}/`, payload);
      } else {
        await api.post('/quiz/quizzes/', payload);
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
    if (!window.confirm('Supprimer ce quiz et toutes ses tentatives ?')) return;
    try {
      await api.delete(`/quiz/quizzes/${id}/`);
      fetchItems();
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors de la suppression.'));
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1>{titre}</h1>
        <button className="btn btn-primary" onClick={openCreate}>+ Créer un quiz</button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {showForm && (
        <>
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '820px', maxHeight: '90vh', overflowY: 'auto' }}>
            <div className="modal-header">
              <h3>{editingItem ? 'Modifier le' : 'Nouveau'} quiz</h3>
              <button className="close-btn" onClick={() => setShowForm(false)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                {formError && <div className="alert alert-error">{formError}</div>}
                {formMessage && <div className="alert alert-success">{formMessage}</div>}
                <div className="form-group">
                  <label>Titre</label>
                  <input value={form.titre} onChange={(e) => setForm({ ...form, titre: e.target.value })} required />
                </div>
                <div className="form-group">
                  <label>Description</label>
                  <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2} />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Filière</label>
                    <select value={form.filiere} onChange={(e) => setForm({ ...form, filiere: e.target.value })}>
                      <option value="">-- Toutes --</option>
                      {filieres.map((f) => <option key={f.id} value={f.id}>{f.libelle}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Niveau</label>
                    <select value={form.niveau} onChange={(e) => setForm({ ...form, niveau: e.target.value })}>
                      <option value="">-- Tous --</option>
                      {niveaux.map((n) => <option key={n.id} value={n.id}>{n.libelle}</option>)}
                    </select>
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>Année académique</label>
                    <select value={form.annee_academique} onChange={(e) => setForm({ ...form, annee_academique: e.target.value })}>
                      <option value="">-- Toutes --</option>
                      {annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Durée (minutes)</label>
                    <input type="number" min="1" value={form.duree_minutes} onChange={(e) => setForm({ ...form, duree_minutes: parseInt(e.target.value, 10) || 1 })} />
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
                <div className="form-row">
                  <div className="form-group">
                    <label>Tentatives autorisées</label>
                    <input type="number" min="1" value={form.tentatives_autorisees} onChange={(e) => setForm({ ...form, tentatives_autorisees: parseInt(e.target.value, 10) || 1 })} />
                  </div>
                  <div className="form-group">
                    <label>Publication des résultats</label>
                    <select value={form.publication_resultats} onChange={(e) => setForm({ ...form, publication_resultats: e.target.value })}>
                      <option value="immediate">Immédiate, après chaque soumission</option>
                      <option value="differee">Différée, quand je publie</option>
                    </select>
                  </div>
                </div>
                <div className="form-group">
                  <label><input type="checkbox" checked={form.reprise_autorisee} onChange={(e) => setForm({ ...form, reprise_autorisee: e.target.checked })} style={{ width: 'auto', marginRight: '8px' }} />Reprise autorisée après une déconnexion</label>
                  <label><input type="checkbox" checked={form.afficher_corrige} onChange={(e) => setForm({ ...form, afficher_corrige: e.target.checked })} style={{ width: 'auto', marginRight: '8px' }} />Afficher le corrigé (quand l'étudiant n'a plus de tentative ou que le quiz est fermé)</label>
                  <label><input type="checkbox" checked={form.est_publie} onChange={(e) => setForm({ ...form, est_publie: e.target.checked })} style={{ width: 'auto', marginRight: '8px' }} />Publier</label>
                </div>

                <hr style={{ margin: '20px 0', border: 'none', borderTop: '1px solid var(--gray-200)' }} />
                <AffectationQuiz
                  key={editingItem?.id || 'nouveau'}
                  valeur={{ classes: form.classes, groupes: form.groupes, etudiants: form.etudiants }}
                  onChange={(cibles) => setForm((f) => ({ ...f, ...cibles }))}
                  etudiantsConnus={editingItem?.etudiants_detail || []} />
                <hr style={{ margin: '20px 0', border: 'none', borderTop: '1px solid var(--gray-200)' }} />
                {editingItem ? (
                  <AccesQuiz quiz={editingItem} onCodeChange={fetchItems} />
                ) : (
                  <p style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>Enregistrez le quiz pour générer un code d'accès et copier son lien.</p>
                )}

                <hr style={{ margin: '20px 0', border: 'none', borderTop: '1px solid var(--gray-200)' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h3 style={{ margin: 0 }}>Questions ({questions.length})</h3>
                  {!verrouille && (
                    <div>
                      <button type="button" className="btn btn-sm btn-primary" onClick={() => setQuestions([...questions, nouvelleQuestion()])}>+ Ajouter</button>
                      <button type="button" className="btn btn-sm btn-secondary" style={{ marginLeft: '8px' }} onClick={() => setSelecteurOuvert(true)}>Depuis la banque</button>
                    </div>
                  )}
                </div>

                {verrouille ? (
                  <div>
                    <div className="alert alert-error">Des étudiants ont déjà passé ce quiz : ses questions ne sont plus modifiables. Les réglages restent modifiables.</div>
                    <ol>
                      {questions.map((q, i) => <li key={i}>{q.texte} ({Number(q.points)} pt)</li>)}
                    </ol>
                  </div>
                ) : questions.map((q, i) => (
                  <QuestionEditeur key={i} question={q} index={i}
                    onChange={(patch) => majQuestion(i, patch)}
                    actions={actionsQuestion(q, i)}
                    onRemove={() => setQuestions(questions.filter((_, j) => j !== i))} />
                ))}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowForm(false)}>Annuler</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Enregistrement...' : 'Enregistrer'}</button>
              </div>
            </form>
          </div>
        </div>
        {selecteurOuvert && <SelecteurBanque onAjouter={ajouterDepuisBanque} onFermer={() => setSelecteurOuvert(false)} />}
        </>
      )}

      <div className="table-container">
        {loading ? (
          <div className="loading">Chargement...</div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📝</div>
            <h3>{texteVide}</h3>
            <p>{sousTexteVide}</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Titre</th><th>Filière</th><th>Cible</th><th>Questions</th><th>Durée</th><th>Tentatives</th><th>Statut</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.titre}</strong></td>
                  <td>{item.filiere_libelle || 'Toutes'}</td>
                  <td>
                    {item.nb_cibles > 0
                      ? resumeCibles(item.classes_detail.length, item.groupes_detail.length, item.etudiants_detail.length)
                      : (item.est_publie ? <span className="badge badge-pending">Non affecté</span> : '-')}
                    {item.code_acces && <span className="badge badge-inactive" style={{ marginLeft: '6px' }}>Code</span>}
                  </td>
                  <td>{item.questions?.length || 0}</td>
                  <td>{item.duree_minutes} min</td>
                  <td>{item.tentatives_autorisees}</td>
                  <td>{item.est_publie ? <span className="badge badge-active">Publié</span> : <span className="badge badge-inactive">Brouillon</span>}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button className="btn btn-sm btn-secondary" onClick={() => openEdit(item)} style={{ marginRight: '8px' }}>Modifier</button>
                    <Link className="btn btn-sm btn-outline" to={`/quiz/${item.id}/tentatives`} style={{ marginRight: '8px' }}>Tentatives</Link>
                    <Link className="btn btn-sm btn-outline" to={`/quiz/${item.id}/statistiques`} style={{ marginRight: '8px' }}>Statistiques</Link>
                    <button className="btn btn-sm btn-danger" onClick={() => handleDelete(item.id)}>Supprimer</button>
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
