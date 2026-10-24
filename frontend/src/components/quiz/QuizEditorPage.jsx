import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import AffectationQuiz from './AffectationQuiz';
import AccesQuiz from './AccesQuiz';
import { resumeCibles } from './cibles';

const nouveauChoix = (texte = '', est_correct = false) => ({ texte, est_correct, points: 0 });
const nouvelleQuestion = () => ({
  texte: '', type_question: 'qcm', points: 1, mode_notation: 'tout_ou_rien',
  choix: [nouveauChoix('', true), nouveauChoix()],
});
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

const sommePositive = (choix) => choix.reduce((s, c) => s + (Number(c.points) > 0 ? Number(c.points) : 0), 0);

function QuestionEditeur({ question: q, index, onChange, onRemove }) {
  const setChoix = (cIdx, patch) => onChange({ choix: q.choix.map((c, j) => (j === cIdx ? { ...c, ...patch } : c)) });
  const bonneReponseUnique = (cIdx) => onChange({ choix: q.choix.map((c, j) => ({ ...c, est_correct: j === cIdx })) });
  const ajouterChoix = (est_correct = false) => onChange({ choix: [...q.choix, nouveauChoix('', est_correct)] });
  const retirerChoix = (cIdx) => onChange({ choix: q.choix.filter((_, j) => j !== cIdx) });
  const changerType = (type) => {
    let choix = [nouveauChoix('', true), nouveauChoix()];
    if (type === 'vf') choix = [nouveauChoix('Vrai', true), nouveauChoix('Faux')];
    if (type === 'courte') choix = [nouveauChoix('', true)];
    onChange({ type_question: type, mode_notation: 'tout_ou_rien', choix });
  };
  const parChoix = q.type_question === 'qcm' && q.mode_notation === 'par_choix';
  const somme = sommePositive(q.choix);

  return (
    <div style={{ border: '1px solid var(--gray-200)', borderRadius: '8px', padding: '16px', marginBottom: '12px', background: 'var(--gray-50, #f9fafb)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <strong style={{ color: 'var(--primary)' }}>Question {index + 1}</strong>
        <button type="button" className="btn btn-sm btn-danger" onClick={onRemove}>Supprimer</button>
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
            <select value={q.mode_notation} onChange={(e) => onChange({ mode_notation: e.target.value })}>
              <option value="tout_ou_rien">Tout ou rien</option>
              <option value="par_choix">Points par choix</option>
            </select>
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
    </div>
  );
}

export default function QuizEditorPage({ titre, texteVide, sousTexteVide }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
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
      texte: q.texte, type_question: q.type_question, points: Number(q.points), mode_notation: q.mode_notation,
      choix: (q.choix || []).map((c) => ({ texte: c.texte, est_correct: c.est_correct, points: Number(c.points) })),
    }));
    setQuestions(chargees.length > 0 ? chargees : [nouvelleQuestion()]);
    setFormError('');
    setShowForm(true);
  };

  const majQuestion = (idx, patch) => setQuestions((qs) => qs.map((q, i) => (i === idx ? { ...q, ...patch } : q)));

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
      payload.questions = questions.map((q, i) => ({
        texte: q.texte, type_question: q.type_question, points: q.points, mode_notation: q.mode_notation, ordre: i + 1,
        choix: q.choix.map((c, j) => {
          const parChoix = q.type_question === 'qcm' && q.mode_notation === 'par_choix';
          return {
            texte: c.texte, est_correct: parChoix ? Number(c.points) > 0 : c.est_correct, ordre: j + 1,
            points: parChoix ? c.points || 0 : 0,
          };
        }),
      }));
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
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '820px', maxHeight: '90vh', overflowY: 'auto' }}>
            <div className="modal-header">
              <h3>{editingItem ? 'Modifier le' : 'Nouveau'} quiz</h3>
              <button className="close-btn" onClick={() => setShowForm(false)}>×</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                {formError && <div className="alert alert-error">{formError}</div>}
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
                  {!verrouille && <button type="button" className="btn btn-sm btn-primary" onClick={() => setQuestions([...questions, nouvelleQuestion()])}>+ Ajouter</button>}
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
