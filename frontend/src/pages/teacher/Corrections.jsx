import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import { chargerTout } from '../../services/pagination';
import CodeEditor from '../../components/CodeEditor';
import ResultatsExecution from '../../components/devoirs/ResultatsExecution';
import { LANGAGES } from '../../components/devoirs/exercices';
import { STATUTS_SOUMISSION, executionActive } from '../../components/devoirs/statuts';

// Relecture d'une soumission ouverte tant que sa correction automatique est en cours.
const INTERVALLE_CORRECTION_MS = 3000;
const styleNote = { fontSize: '0.85rem', color: 'var(--gray-500)' };

// Résumé de la liste : tests acceptés sur l'ensemble des exercices, à partir des compteurs par statut.
function resumeTests(sub) {
  const corrections = (sub.reponses || []).map((r) => r.correction).filter(Boolean);
  if (corrections.length === 0) return '-';
  if (corrections.some((c) => c.statut === 'erreur')) return 'Erreur du service';
  if (corrections.some((c) => executionActive(c.statut))) return 'En cours';
  const total = corrections.reduce((somme, c) => somme + (c.nombre_tests || 0), 0);
  const acceptes = corrections.reduce((somme, c) => somme + (c.compteurs?.OK || 0), 0);
  return `${acceptes} / ${total}`;
}

function badgeSoumission(statut) {
  const classe = statut === 'corrige' ? 'badge-active' : 'badge-inactive';
  return <span className={`badge ${classe}`}>{STATUTS_SOUMISSION[statut] || statut}</span>;
}

const aUneValeur = (v) => v !== null && v !== undefined;
// Une réponse arrivée après la fermeture de la modale (ou l'ouverture d'une autre) est ignorée.
const siToujoursOuverte = (donnees) => (prev) => (prev && prev.id === donnees.id ? donnees : prev);

export default function Corrections() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [devoir, setDevoir] = useState(null);
  const [soumissions, setSoumissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [chargementDetail, setChargementDetail] = useState(false);
  const [score, setScore] = useState('');
  const [commentaire, setCommentaire] = useState('');
  const [saving, setSaving] = useState(false);
  const [relance, setRelance] = useState(false);
  const [message, setMessage] = useState('');
  const [erreurModale, setErreurModale] = useState('');
  const minuteur = useRef(null);

  const rechargerListe = useCallback(async () => {
    setSoumissions(await chargerTout('/programming/soumissions/', { devoir: id }));
  }, [id]);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const devoirRes = await api.get(`/programming/devoirs/${id}/`);
        setDevoir(devoirRes.data);
        await rechargerListe();
      } catch (err) {
        setError(messageErreur(err, 'Erreur lors du chargement.'));
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id, rechargerListe]);

  // Soumission ouverte en cours de correction : relue jusqu'à la fin, arrêt à la fermeture ou au démontage.
  const selectedId = selected?.id;
  const enCorrection = selected?.statut === 'en_correction';
  useEffect(() => {
    if (!selectedId || !enCorrection) return undefined;
    const relire = async () => {
      try {
        const res = await api.get(`/programming/soumissions/${selectedId}/`);
        setSelected(siToujoursOuverte(res.data));
        if (res.data.statut === 'en_correction') minuteur.current = setTimeout(relire, INTERVALLE_CORRECTION_MS);
        else rechargerListe().catch(() => {});
      } catch {
        minuteur.current = setTimeout(relire, INTERVALLE_CORRECTION_MS * 3);
      }
    };
    minuteur.current = setTimeout(relire, INTERVALLE_CORRECTION_MS);
    return () => clearTimeout(minuteur.current);
  }, [selectedId, enCorrection, rechargerListe]);

  const openCorrection = async (sub) => {
    setMessage('');
    setErreurModale('');
    setScore(aUneValeur(sub.score) ? sub.score.toString() : '');
    setCommentaire(sub.commentaire || '');
    // La liste ne porte qu'un résumé : le détail des tests est lu sur la soumission.
    setSelected(sub);
    setChargementDetail(true);
    try {
      const res = await api.get(`/programming/soumissions/${sub.id}/`);
      setSelected(siToujoursOuverte(res.data));
    } catch (err) {
      setErreurModale(messageErreur(err, 'Erreur lors du chargement de la soumission.'));
    } finally {
      setChargementDetail(false);
    }
  };

  const fermer = () => setSelected(null);

  const handleSave = async () => {
    setSaving(true);
    setMessage('');
    setErreurModale('');
    try {
      // Note vide : le serveur valide la note proposée, arrondie.
      await api.post(`/programming/soumissions/${selected.id}/corriger/`, {
        score: score.trim() !== '' ? score.trim() : null,
        commentaire,
      });
      setMessage('Note validée.');
      setSelected(null);
      rechargerListe().catch((err) => setError(messageErreur(err, 'Erreur lors du chargement.')));
    } catch (err) {
      setErreurModale(messageErreur(err, 'Erreur lors de la sauvegarde.'));
    } finally {
      setSaving(false);
    }
  };

  const relancer = async (tout) => {
    setRelance(true);
    setErreurModale('');
    try {
      const res = await api.post(`/programming/soumissions/${selected.id}/recorriger/`, tout ? { tout: true } : {});
      setSelected(siToujoursOuverte(res.data));
      rechargerListe().catch(() => {});
    } catch (err) {
      setErreurModale(messageErreur(err, 'Erreur lors de la relance de la correction.'));
    } finally {
      setRelance(false);
    }
  };

  const compter = (statut) => soumissions.filter((s) => s.statut === statut).length;
  const stats = {
    total: soumissions.length,
    validees: compter('corrige'),
    aValider: compter('corrigee_auto') + compter('soumis'),
    enCorrection: compter('en_correction'),
  };

  // La note est un entier compris entre 0 et la partie entière du barème.
  const noteMax = Math.floor(Number(devoir?.bareme) || 0);
  const exercices = devoir?.exercices || [];
  const executable = devoir?.langage !== 'autre';
  const reponsesDe = (sub) => Object.fromEntries((sub.reponses || []).map((r) => [r.exercice, r]));
  const noteProposee = aUneValeur(selected?.note_proposee) ? Number(selected.note_proposee) : null;
  const erreursService = (selected?.reponses || []).some((r) => r.correction?.statut === 'erreur');

  if (loading) return <div className="loading">Chargement...</div>;

  return (
    <div>
      <div className="page-header">
        <div>
          <button className="btn btn-secondary" onClick={() => navigate(-1)} style={{ marginBottom: '8px' }}>← Retour</button>
          <h1>Corrections : {devoir?.titre}</h1>
        </div>
        <div>
          <span className="badge badge-active">{devoir?.langage_display || LANGAGES[devoir?.langage] || devoir?.langage}</span>
          <span style={{ marginLeft: '12px', color: 'var(--gray-500)' }}>Barème : {Number(devoir?.bareme)} pts, {exercices.length} exercice{exercices.length > 1 ? 's' : ''}</span>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-success">{message}</div>}

      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
        <div className="form-card" style={{ flex: 1, textAlign: 'center' }}>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--primary)' }}>{stats.total}</div>
          <div style={{ color: 'var(--gray-500)' }}>Soumissions</div>
        </div>
        <div className="form-card" style={{ flex: 1, textAlign: 'center' }}>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--success)' }}>{stats.validees}</div>
          <div style={{ color: 'var(--gray-500)' }}>Validées</div>
        </div>
        <div className="form-card" style={{ flex: 1, textAlign: 'center' }}>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--warning, #f59e0b)' }}>{stats.aValider}</div>
          <div style={{ color: 'var(--gray-500)' }}>À valider</div>
        </div>
        {executable && (
          <div className="form-card" style={{ flex: 1, textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--gray-500)' }}>{stats.enCorrection}</div>
            <div style={{ color: 'var(--gray-500)' }}>Correction en cours</div>
          </div>
        )}
      </div>

      <div className="table-container">
        {soumissions.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📋</div>
            <h3>Aucune soumission</h3>
            <p>Les étudiants n'ont pas encore soumis ce devoir.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr><th>Étudiant</th><th>Date</th>{executable && <><th>Tests acceptés</th><th>Note proposée</th></>}<th>Note</th><th>Statut</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {soumissions.map((sub) => (
                <tr key={sub.id}>
                  <td><strong>{sub.etudiant_nom}</strong></td>
                  <td>{new Date(sub.date_soumission).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
                  {executable && (
                    <>
                      <td>{resumeTests(sub)}</td>
                      <td>{aUneValeur(sub.note_proposee) ? `${Number(sub.note_proposee)} / ${Number(devoir?.bareme)}` : '-'}</td>
                    </>
                  )}
                  <td>{aUneValeur(sub.score) ? <strong>{sub.score} / {noteMax}</strong> : '-'}</td>
                  <td>{badgeSoumission(sub.statut)}</td>
                  <td>
                    <button className="btn btn-sm btn-primary" onClick={() => openCorrection(sub)}>
                      {sub.statut === 'corrige' ? 'Revoir' : 'Valider'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <div className="modal-overlay" onClick={fermer}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '1000px', maxHeight: '90vh', overflowY: 'auto' }}>
            <div className="modal-header">
              <h3>Correction : {selected.etudiant_nom}</h3>
              <button className="close-btn" onClick={fermer}>×</button>
            </div>
            <div className="modal-body">
              {erreurModale && <div className="alert alert-error">{erreurModale}</div>}
              <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '16px' }}>
                {badgeSoumission(selected.statut)}
                {executable && (
                  <span style={{ fontWeight: 600 }}>
                    Note proposée : {noteProposee !== null ? `${noteProposee} / ${Number(devoir?.bareme)}` : '-'}
                  </span>
                )}
                {executable && selected.statut !== 'corrige' && (
                  <span style={{ marginLeft: 'auto', display: 'flex', gap: '8px' }}>
                    <button type="button" className="btn btn-sm btn-secondary" onClick={() => relancer(false)}
                      disabled={relance || chargementDetail || enCorrection || !erreursService}
                      title="Relance les exercices dont la correction est en erreur">Relancer les erreurs</button>
                    <button type="button" className="btn btn-sm btn-outline" onClick={() => relancer(true)}
                      disabled={relance || chargementDetail || enCorrection}>Tout recorriger</button>
                  </span>
                )}
              </div>
              {enCorrection && <p style={styleNote}>Correction automatique en cours : les résultats s'afficheront à la fin.</p>}
              {chargementDetail && <div className="loading">Chargement des résultats...</div>}

              {exercices.map((ex, i) => {
                const reponse = reponsesDe(selected)[ex.id];
                const correction = reponse?.correction;
                return (
                  <div key={ex.id} style={{ marginBottom: '20px', borderBottom: '1px solid var(--gray-200)', paddingBottom: '12px' }}>
                    <label style={{ fontWeight: 600, display: 'block', marginBottom: '8px' }}>
                      Exercice {i + 1} : {ex.titre} <span style={{ fontWeight: 'normal', color: 'var(--gray-500)' }}>({Number(ex.points)} pt{Number(ex.points) > 1 ? 's' : ''})</span>
                    </label>
                    {!reponse || reponse.fichiers.length === 0 ? (
                      <p style={{ color: 'var(--gray-500)', fontSize: '0.9rem' }}>Aucune réponse rendue pour cet exercice.</p>
                    ) : reponse.fichiers.map((f, j) => (
                      <div key={j} style={{ marginBottom: '8px' }}>
                        <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)', marginBottom: '4px' }}>{f.nom}</div>
                        <CodeEditor language={devoir?.langage} value={f.contenu} readOnly height="250px" />
                      </div>
                    ))}
                    {/* Le détail complet porte `resultats` ; le résumé de la liste (compteurs) attend le chargement. */}
                    {correction?.resultats && <ResultatsExecution execution={correction} />}
                    {executable && reponse && !correction && !chargementDetail && <p style={styleNote}>Aucune correction automatique.</p>}
                  </div>
                );
              })}
              <div className="form-row">
                <div className="form-group" style={{ flex: '0 0 180px' }}>
                  <label>Note / {noteMax}</label>
                  <input
                    type="number"
                    min="0"
                    max={noteMax}
                    step="1"
                    value={score}
                    onChange={(e) => setScore(e.target.value)}
                    placeholder={noteProposee !== null ? String(Math.min(Math.max(Math.round(noteProposee), 0), noteMax)) : '0'}
                  />
                  {noteProposee !== null && <small style={styleNote}>Vide : la note proposée arrondie est validée.</small>}
                </div>
                <div className="form-group" style={{ flex: 1 }}>
                  <label>Remarques</label>
                  <textarea
                    value={commentaire}
                    onChange={(e) => setCommentaire(e.target.value)}
                    rows={3}
                    placeholder="Remarques pour l'étudiant (style, logique, optimisation...)..."
                  />
                </div>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={fermer}>Annuler</button>
              <button className="btn btn-primary" onClick={handleSave} disabled={saving || chargementDetail}>
                {saving ? 'Enregistrement...' : 'Valider la note'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
