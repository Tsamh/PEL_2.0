import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../../services/api';
import { chargerTout } from '../../services/pagination';
import { messageErreur } from '../../services/erreurs';
import { useAuth } from '../../context/AuthContext';
import CodeEditor from '../../components/CodeEditor';
import CountdownTimer from '../../components/CountdownTimer';
import ApercuDevoir, { Exemples, ListeRessources, TableTests } from '../../components/devoirs/ApercuDevoir';
import { DIFFICULTES, LANGAGES, avecContenuPrincipal, contenuPrincipal, nomFichier } from '../../components/devoirs/exercices';
import ResultatsExecution from '../../components/devoirs/ResultatsExecution';
import { STATUTS_SOUMISSION, executionActive } from '../../components/devoirs/statuts';

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' }) : '');
const styleTexte = { whiteSpace: 'pre-wrap', color: 'var(--gray-700)', margin: '4px 0' };
const styleNote = { fontSize: '0.85rem', color: 'var(--gray-500)' };
const styleCode = { fontFamily: 'monospace', width: '100%' };

// Fichiers de travail d'un exercice : copie des fichiers de départ (un fichier principal au moins).
const fichiersDeDepart = (exercice, langage) => {
  const fichiers = (exercice.fichiers_initiaux || []).map((f) => ({ nom: f.nom, contenu: f.contenu }));
  return fichiers.length > 0 ? fichiers : [{ nom: nomFichier(langage), contenu: '' }];
};

// Avance de la soumission automatique sur l'heure de fermeture effective.
const AVANCE_AUTO_MS = 30000;
// Interrogation d'un essai en cours, et d'une soumission en cours de correction.
const INTERVALLE_ESSAI_MS = 1000;
const INTERVALLE_CORRECTION_MS = 3000;
const MESSAGE_EN_COURS = 'Une exécution est déjà en cours.';

// Brouillon du code d'un exercice, gardé le temps de l'onglet (le stockage peut être indisponible).
const cleBrouillon = (devoirId, exerciceId) => `pel-brouillon-devoir-${devoirId}-${exerciceId}`;
const lireBrouillon = (devoirId, exerciceId) => {
  try {
    const brut = window.sessionStorage.getItem(cleBrouillon(devoirId, exerciceId));
    const fichiers = brut ? JSON.parse(brut) : null;
    return Array.isArray(fichiers) && fichiers.length > 0 ? fichiers : null;
  } catch { return null; }
};
const ecrireBrouillon = (devoirId, exerciceId, fichiers) => {
  try { window.sessionStorage.setItem(cleBrouillon(devoirId, exerciceId), JSON.stringify(fichiers)); } catch { /* stockage indisponible */ }
};
const effacerBrouillons = (devoirId, exercices) => {
  try { exercices.forEach((ex) => window.sessionStorage.removeItem(cleBrouillon(devoirId, ex.id))); } catch { /* stockage indisponible */ }
};

function ApercuGestion({ id }) {
  const navigate = useNavigate();
  const [devoir, setDevoir] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get(`/programming/devoirs/${id}/`).then((res) => setDevoir(res.data))
      .catch((err) => setError(messageErreur(err, 'Devoir introuvable.')));
  }, [id]);

  if (error) return <div className="alert alert-error">{error}</div>;
  if (!devoir) return <div className="loading">Chargement...</div>;
  return (
    <div>
      <div className="page-header">
        <div>
          <button className="btn btn-secondary" onClick={() => navigate(-1)} style={{ marginBottom: '8px' }}>← Retour</button>
          <h1>{devoir.titre}</h1>
        </div>
      </div>
      <div className="form-card"><ApercuDevoir devoir={devoir} /></div>
    </div>
  );
}

function DevoirEtudiant({ id }) {
  const navigate = useNavigate();
  const [devoir, setDevoir] = useState(null);
  const [soumission, setSoumission] = useState(null);
  const [fichiers, setFichiers] = useState({});
  const [essais, setEssais] = useState({});
  const [entrees, setEntrees] = useState({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const autoLance = useRef(false);
  const envoiRef = useRef(null);
  const minuteurs = useRef({});

  // Toute interrogation s'arrête au démontage de la page.
  useEffect(() => {
    const actifs = minuteurs.current;
    return () => Object.values(actifs).forEach(clearTimeout);
  }, []);

  const planifier = (cle, fonction, delai) => {
    clearTimeout(minuteurs.current[cle]);
    minuteurs.current[cle] = setTimeout(fonction, delai);
  };

  const charger = useCallback(async () => {
    try {
      const [res, subs] = await Promise.all([
        api.get(`/programming/devoirs/${id}/`),
        chargerTout('/programming/soumissions/', { devoir: id }),
      ]);
      setDevoir(res.data);
      setSoumission(subs.find((s) => s.devoir === res.data.id) || null);
      // Les fichiers en cours d'édition sont gardés ; seuls les exercices nouveaux partent du fichier de départ.
      // Un brouillon de l'onglet remplace le fichier de départ tant que le devoir n'est pas soumis.
      const dejaSoumis = Boolean(res.data.etat?.soumis || subs.some((s) => s.devoir === res.data.id));
      setFichiers((avant) => Object.fromEntries(res.data.exercices.map((ex) => [
        ex.id,
        avant[ex.id] || (!dejaSoumis && lireBrouillon(res.data.id, ex.id)) || fichiersDeDepart(ex, res.data.langage),
      ])));
      setError('');
    } catch (err) {
      setError(messageErreur(err, 'Devoir introuvable.'));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { charger(); }, [charger]);

  // Envoi du devoir ; en mode automatique, ni confirmation ni blocage par le chargement.
  const envoyer = async (auto) => {
    if (!devoir) return;
    if (!auto && !window.confirm('Soumettre le devoir ? Le code de tous les exercices sera rendu et ne pourra plus être modifié.')) return;
    setSubmitting(true);
    setError('');
    setMessage('');
    try {
      const res = await api.post('/programming/soumissions/', {
        devoir: devoir.id,
        reponses: devoir.exercices.map((ex) => ({ exercice: ex.id, fichiers: fichiers[ex.id] })),
      });
      setSoumission(res.data);
      effacerBrouillons(devoir.id, devoir.exercices);
      setMessage(auto ? 'Le délai se termine : votre devoir a été soumis automatiquement.' : 'Votre devoir a été soumis.');
      charger();
    } catch (err) {
      setError(messageErreur(err, 'Erreur lors de la soumission.'));
      // Une 409 (déjà soumis, fermé) change l'état affiché : il est relu.
      if (err.response?.status === 409) charger();
    } finally {
      setSubmitting(false);
    }
  };

  useEffect(() => { envoiRef.current = envoyer; });

  // Soumission automatique peu avant la fermeture effective, une seule fois.
  const fermeture = devoir?.etat?.fenetre?.fermeture;
  const peutSoumettreAuto = Boolean(devoir?.etat?.ouvert) && !devoir?.etat?.soumis && !soumission;
  useEffect(() => {
    if (!peutSoumettreAuto || !fermeture || autoLance.current) return undefined;
    const declencher = () => {
      if (autoLance.current) return;
      autoLance.current = true;
      envoiRef.current(true);
    };
    const delai = new Date(fermeture).getTime() - AVANCE_AUTO_MS - Date.now();
    if (delai <= 0) { declencher(); return undefined; }
    const minuteur = setTimeout(declencher, Math.min(delai, 2147483647));
    return () => clearTimeout(minuteur);
  }, [peutSoumettreAuto, fermeture]);

  // Soumission en cours de correction : relue jusqu'à la fin de la correction automatique.
  const soumissionId = soumission?.id;
  const enCorrection = soumission?.statut === 'en_correction';
  useEffect(() => {
    if (!soumissionId || !enCorrection) return undefined;
    const relire = async () => {
      try {
        const res = await api.get(`/programming/soumissions/${soumissionId}/`);
        setSoumission(res.data);
        if (res.data.statut === 'en_correction') planifier('soumission', relire, INTERVALLE_CORRECTION_MS);
      } catch {
        planifier('soumission', relire, INTERVALLE_CORRECTION_MS * 3);
      }
    };
    planifier('soumission', relire, INTERVALLE_CORRECTION_MS);
    const actifs = minuteurs.current;
    return () => clearTimeout(actifs.soumission);
  }, [soumissionId, enCorrection]);

  if (loading) return <div className="loading">Chargement...</div>;
  if (!devoir) return <div className="alert alert-error">{error}</div>;

  const etat = devoir.etat || {};
  const soumis = Boolean(etat.soumis || soumission);
  const editable = Boolean(etat.ouvert) && !soumis;
  const reponses = Object.fromEntries((soumission?.reponses || []).map((r) => [r.exercice, r.fichiers]));

  const executable = devoir.langage !== 'autre';
  // Une seule exécution à la fois par utilisateur : les boutons de tous les exercices attendent la fin.
  const essaiActif = Object.values(essais).some((e) => e.envoi || (e.execution && executionActive(e.execution.statut)));
  const majEssai = (exerciceId, valeur) => setEssais((e) => ({ ...e, [exerciceId]: valeur }));

  const suivre = (exerciceId, executionId) => {
    const relire = async () => {
      try {
        const res = await api.get(`/programming/executions/${executionId}/`);
        majEssai(exerciceId, { execution: res.data });
        if (executionActive(res.data.statut)) planifier(`essai-${exerciceId}`, relire, INTERVALLE_ESSAI_MS);
      } catch (err) {
        majEssai(exerciceId, { erreur: messageErreur(err, "Erreur lors de la lecture du résultat de l'exécution.") });
      }
    };
    planifier(`essai-${exerciceId}`, relire, INTERVALLE_ESSAI_MS);
  };

  const executer = async (exercice, mode) => {
    majEssai(exercice.id, { envoi: true });
    try {
      const corps = { exercice: exercice.id, fichiers: fichiers[exercice.id], mode };
      if (mode === 'run') corps.entree = entrees[exercice.id] || '';
      const res = await api.post(`/programming/devoirs/${id}/executer/`, corps);
      majEssai(exercice.id, { execution: { ...res.data, type: mode === 'run' ? 'essai_run' : 'essai_test' } });
      suivre(exercice.id, res.data.id);
    } catch (err) {
      majEssai(exercice.id, { erreur: messageErreur(err, "Erreur lors de l'exécution.") });
      // Fenêtre fermée ou année archivée entre-temps : l'état affiché est relu.
      if (err.response?.status === 409 && err.response?.data?.detail !== MESSAGE_EN_COURS) charger();
    }
  };

  let messageFenetre = '';
  if (!soumis && !etat.ouvert) {
    const echu = etat.fenetre?.fermeture && new Date(etat.fenetre.fermeture) <= new Date();
    if (etat.fenetre?.prochaine_ouverture) messageFenetre = `Ce devoir n'est pas ouvert. Ouverture le ${formatDate(etat.fenetre.prochaine_ouverture)}.`;
    else if (echu) messageFenetre = "Le délai est écoulé : votre code n'a pas été rendu.";
    else messageFenetre = 'Ce devoir est fermé.';
  }
  const aUneNote = soumission && soumission.score !== null && soumission.score !== undefined;
  const aUneNoteProposee = !aUneNote && soumission?.note_proposee !== null && soumission?.note_proposee !== undefined;
  const corrections = Object.fromEntries((soumission?.reponses || []).map((r) => [r.exercice, r.correction]));
  let etatCorrection = '';
  if (soumission?.statut === 'en_correction') etatCorrection = 'La correction automatique de votre code est en cours.';
  else if (soumission?.statut === 'corrigee_auto' && !soumission.resultats_visibles) etatCorrection = "La correction automatique est terminée : les résultats seront visibles après validation par l'enseignant.";
  else if (soumission?.statut === 'soumis') etatCorrection = "Votre devoir sera corrigé par l'enseignant.";

  return (
    <div>
      <div className="page-header">
        <div>
          <button className="btn btn-secondary" onClick={() => navigate(-1)} style={{ marginBottom: '8px' }}>← Retour</button>
          <h1>{devoir.titre}</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <span className="badge badge-active">{devoir.langage_display || LANGAGES[devoir.langage] || devoir.langage}</span>
          <span style={{ color: 'var(--gray-500)' }}>Barème : {Number(devoir.bareme)} pts</span>
          {editable && etat.fenetre?.fermeture && new Date(etat.fenetre.fermeture) > new Date() && <CountdownTimer dateFin={etat.fenetre.fermeture} onTimeUp={charger} />}
        </div>
      </div>

      {(devoir.objectifs || devoir.consignes || devoir.ressources?.length > 0 || etat.fenetre?.fermeture) && (
        <div className="form-card" style={{ marginBottom: '24px' }}>
          {devoir.ec_libelle && <div style={styleNote}>Matière : {devoir.ec_libelle}</div>}
          {etat.fenetre?.fermeture && <div style={styleNote}>Échéance : {formatDate(etat.fenetre.fermeture)}</div>}
          {devoir.objectifs && <div style={{ marginTop: '8px' }}><strong>Objectifs</strong><p style={styleTexte}>{devoir.objectifs}</p></div>}
          {devoir.consignes && <div style={{ marginTop: '8px' }}><strong>Consignes</strong><p style={styleTexte}>{devoir.consignes}</p></div>}
          {devoir.ressources?.length > 0 && <div style={{ marginTop: '8px' }}><strong>Ressources</strong><ListeRessources ressources={devoir.ressources} /></div>}
        </div>
      )}

      {message && <div className="alert alert-success">{message}</div>}
      {error && <div className="alert alert-error">{error}</div>}
      {messageFenetre && <div className="alert alert-error">{messageFenetre}</div>}

      {soumis && (
        <div className="form-card" style={{ marginBottom: '24px' }}>
          <h3>Votre soumission</h3>
          <div>
            <span className={`badge ${soumission?.statut === 'corrige' ? 'badge-active' : 'badge-inactive'}`}>
              {STATUTS_SOUMISSION[soumission?.statut] || 'Soumis'}
            </span>
            {soumission?.date_soumission && <span style={{ ...styleNote, marginLeft: '12px' }}>Rendu le {formatDate(soumission.date_soumission)}</span>}
            {aUneNote && <span style={{ marginLeft: '12px', fontWeight: 600, fontSize: '1.1rem' }}>Note : {soumission.score} / {Number(soumission.bareme ?? devoir.bareme)}</span>}
            {aUneNoteProposee && (
              <span style={{ marginLeft: '12px', fontWeight: 600, fontSize: '1.1rem' }}>
                Note proposée : {Number(soumission.note_proposee)} / {Number(soumission.bareme ?? devoir.bareme)}
                <span style={{ ...styleNote, fontWeight: 'normal', marginLeft: '6px' }}>(en attente de validation)</span>
              </span>
            )}
          </div>
          {etatCorrection && <p style={{ ...styleNote, marginTop: '8px' }}>{etatCorrection}</p>}
          {soumission?.commentaire && (
            <div style={{ marginTop: '12px', padding: '12px', background: 'var(--primary-50, #eff6ff)', borderRadius: '8px', borderLeft: '4px solid var(--primary)' }}>
              <strong style={{ color: 'var(--primary)' }}>Remarques de l'enseignant :</strong>
              <p style={styleTexte}>{soumission.commentaire}</p>
            </div>
          )}
        </div>
      )}

      {devoir.exercices.map((ex, i) => {
        const rendus = reponses[ex.id];
        const affiches = soumis ? rendus : fichiers[ex.id];
        return (
          <div key={ex.id} className="form-card" style={{ marginBottom: '24px' }}>
            <h3 style={{ marginBottom: '4px' }}>Exercice {i + 1} : {ex.titre}</h3>
            <div style={styleNote}>
              {Number(ex.points)} pt{Number(ex.points) > 1 ? 's' : ''}, {DIFFICULTES[ex.difficulte] || ex.difficulte}
              {ex.competences?.length > 0 && `, compétences : ${ex.competences.join(', ')}`}
            </div>
            {ex.enonce && <p style={styleTexte}>{ex.enonce}</p>}
            {ex.contraintes && <div style={{ marginTop: '8px' }}><strong>Contraintes</strong><p style={styleTexte}>{ex.contraintes}</p></div>}
            <Exemples exemples={ex.exemples} />
            {ex.tests_publics?.length > 0 && <div style={{ marginTop: '8px' }}><strong>Tests publics</strong><TableTests tests={ex.tests_publics} /></div>}

            <div style={{ marginTop: '12px' }}>
              {soumis && !rendus ? (
                <p style={styleNote}>Aucune réponse rendue pour cet exercice.</p>
              ) : (
                <>
                  <strong>{soumis ? 'Code rendu' : 'Votre code'} ({affiches[0]?.nom})</strong>
                  <CodeEditor language={devoir.langage} value={contenuPrincipal(affiches)} readOnly={!editable} height="300px"
                    onChange={editable ? (contenu) => {
                      const maj = avecContenuPrincipal(fichiers[ex.id], contenu, devoir.langage);
                      ecrireBrouillon(devoir.id, ex.id, maj);
                      setFichiers((f) => ({ ...f, [ex.id]: maj }));
                    } : undefined} />
                  {affiches.length > 1 && <small style={styleNote}>Autres fichiers {soumis ? 'rendus' : 'conservés'} : {affiches.slice(1).map((f) => f.nom).join(', ')}.</small>}
                </>
              )}
            </div>

            {editable && executable && (
              <div style={{ marginTop: '12px' }}>
                <div className="form-group" style={{ marginBottom: '8px' }}>
                  <label style={styleNote}>Entrée (lue sur l'entrée standard par « Exécuter »)</label>
                  <textarea style={styleCode} rows={2} value={entrees[ex.id] || ''}
                    onChange={(ev) => setEntrees((e) => ({ ...e, [ex.id]: ev.target.value }))} />
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                  <button type="button" className="btn btn-secondary" onClick={() => executer(ex, 'run')}
                    disabled={essaiActif || !contenuPrincipal(fichiers[ex.id]).trim()}>Exécuter</button>
                  <button type="button" className="btn btn-secondary" onClick={() => executer(ex, 'test')}
                    disabled={essaiActif || !ex.tests_publics?.length || !contenuPrincipal(fichiers[ex.id]).trim()}>Tester</button>
                  <span style={styleNote}>
                    {ex.tests_publics?.length > 0 ? "« Tester » lance le code sur les tests publics de l'exercice." : "Cet exercice n'a pas de test public."}
                  </span>
                </div>
              </div>
            )}
            {editable && essais[ex.id] && (
              <div style={{ marginTop: '12px' }}>
                <strong>Console</strong>
                {essais[ex.id].envoi && <div className="loading">Envoi...</div>}
                {essais[ex.id].erreur && <div className="alert alert-error">{essais[ex.id].erreur}</div>}
                <ResultatsExecution execution={essais[ex.id].execution} />
              </div>
            )}
            {soumis && corrections[ex.id] && (
              <div style={{ marginTop: '12px' }}>
                <strong>Résultats de la correction</strong>
                <ResultatsExecution execution={corrections[ex.id]} />
              </div>
            )}
          </div>
        );
      })}

      {editable && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '24px' }}>
          <button className="btn btn-primary" onClick={() => envoyer(false)} disabled={submitting || devoir.exercices.length === 0}>
            {submitting ? 'Soumission...' : 'Soumettre le devoir'}
          </button>
        </div>
      )}
    </div>
  );
}

export default function DevoirDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  // La gestion et l'auteur voient l'aperçu complet ; l'étudiant compose son devoir.
  return user?.role === 'etudiant' ? <DevoirEtudiant id={id} /> : <ApercuGestion id={id} />;
}
