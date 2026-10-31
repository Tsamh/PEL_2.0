import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../../services/api';
import { chargerTout } from '../../services/pagination';
import { messageErreur } from '../../services/erreurs';
import { useAuth } from '../../context/AuthContext';
import CountdownTimer from '../../components/CountdownTimer';
import ApercuDevoir, { Exemples, ListeRessources, TableTests } from '../../components/devoirs/ApercuDevoir';
import EditeurFichiers from '../../components/devoirs/EditeurFichiers';
import { DIFFICULTES, LANGAGES, nomFichier } from '../../components/devoirs/exercices';
import HistoriqueVersions from '../../components/devoirs/HistoriqueVersions';
import ResultatsExecution from '../../components/devoirs/ResultatsExecution';
import { STATUTS_SOUMISSION, executionActive } from '../../components/devoirs/statuts';
import useBrouillons, { lireLocal } from './useBrouillons';

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString('fr-FR', { dateStyle: 'medium', timeStyle: 'short' }) : '');
const styleTexte = { whiteSpace: 'pre-wrap', color: 'var(--gray-700)', margin: '4px 0' };
const styleNote = { fontSize: '0.85rem', color: 'var(--gray-500)' };
const styleCode = { fontFamily: 'monospace', width: '100%' };

// Fichiers de départ d'un exercice : le fichier principal est ajouté s'il manque (un fichier au moins).
const fichiersDeDepart = (exercice, devoir) => {
  const fichiers = (exercice.fichiers_initiaux || []).map((f) => ({ nom: f.nom, contenu: f.contenu }));
  const principal = devoir.fichier_principal || null;
  if (principal && !fichiers.some((f) => f.nom === principal)) fichiers.unshift({ nom: principal, contenu: '' });
  return fichiers.length > 0 ? fichiers : [{ nom: nomFichier(devoir.langage), contenu: '' }];
};

const plein = (fichiers) => (Array.isArray(fichiers) && fichiers.length > 0 ? fichiers : null);
// Contenu du fichier principal (par son nom) ; à défaut de nom connu, celui du premier fichier.
const contenuPrincipalDe = (fichiers, principal) => (principal ? fichiers.find((f) => f.nom === principal) : fichiers[0])?.contenu ?? '';

const libelleEnregistrement = (etat) => {
  if (!etat) return '';
  if (etat.statut === 'enregistre') {
    const h = etat.heure;
    return `Enregistré à ${h.getHours()} h ${String(h.getMinutes()).padStart(2, '0')}`;
  }
  if (etat.statut === 'en_cours') return 'Enregistrement en cours...';
  return etat.conflit ? 'Non enregistré : ce devoir ne peut plus être modifié.' : 'Non enregistré : nouvelle tentative...';
};

// Avance de la soumission automatique sur l'heure de fermeture effective.
const AVANCE_AUTO_MS = 30000;
// Interrogation d'un essai en cours, et d'une soumission en cours de correction.
const INTERVALLE_ESSAI_MS = 1000;
const INTERVALLE_CORRECTION_MS = 3000;
const MESSAGE_EN_COURS = 'Une exécution est déjà en cours.';

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
  // `fichiers` : copie de travail par exercice (absente tant que l'étudiant n'a rien modifié) ;
  // `brouillons` : brouillons lus sur le serveur au chargement.
  const [fichiers, setFichiers] = useState({});
  const [brouillons, setBrouillons] = useState({});
  const [brouillonsIndisponibles, setBrouillonsIndisponibles] = useState(false);
  const [essais, setEssais] = useState({});
  const [entrees, setEntrees] = useState({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const autoLance = useRef(false);
  const envoiRef = useRef(null);
  const minuteurs = useRef({});
  const fichiersRef = useRef({});
  const chargerRef = useRef(null);
  const { enregistrer, etats, charger: lireBrouillons, confirmer } = useBrouillons(id, { surConflit: () => chargerRef.current?.() });

  useEffect(() => { fichiersRef.current = fichiers; });

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
      const [res, subs, serveur] = await Promise.all([
        api.get(`/programming/devoirs/${id}/`),
        chargerTout('/programming/soumissions/', { devoir: id }),
        lireBrouillons(),
      ]);
      const sub = subs.find((s) => s.devoir === res.data.id) || null;
      setDevoir(res.data);
      setSoumission(sub);
      // Les brouillons du serveur ne touchent jamais une copie de travail déjà en cours.
      if (serveur) setBrouillons(serveur);
      setBrouillonsIndisponibles(!serveur);
      // Une copie de l'onglet non confirmée par le serveur reprend la place de la copie de travail et repart au serveur.
      const modifiable = (Boolean(res.data.etat?.ouvert) && !res.data.etat?.soumis && !sub) || Boolean(sub?.resoumission_possible);
      if (modifiable) {
        res.data.exercices.forEach((ex) => {
          const locale = fichiersRef.current[ex.id] ? null : lireLocal(id, ex.id);
          if (!locale) return;
          setFichiers((avant) => (avant[ex.id] ? avant : { ...avant, [ex.id]: locale }));
          enregistrer(ex.id, locale);
        });
      }
      setError('');
    } catch (err) {
      setError(messageErreur(err, 'Devoir introuvable.'));
    } finally {
      setLoading(false);
    }
  }, [id, lireBrouillons, enregistrer]);

  useEffect(() => { chargerRef.current = charger; charger(); }, [charger]);

  const rendusDe = (ex) => plein(soumission?.reponses?.find((r) => r.exercice === ex.id)?.fichiers);
  // Copie de travail : celle en cours, sinon copie de l'onglet, brouillon du serveur, version rendue, fichiers de départ.
  const travail = (ex) => fichiers[ex.id]
    ?? plein(lireLocal(id, ex.id)) ?? plein(brouillons[ex.id]) ?? rendusDe(ex) ?? fichiersDeDepart(ex, devoir);
  const modifier = (ex, maj) => {
    setFichiers((f) => ({ ...f, [ex.id]: maj }));
    enregistrer(ex.id, maj);
  };
  // « Reprendre ce code » : la version remplace la copie de travail des exercices qu'elle contient (rien n'est soumis).
  const reprendre = (version) => {
    version.reponses.forEach((r) => {
      const ex = devoir.exercices.find((e) => e.id === r.exercice);
      if (ex && plein(r.fichiers)) modifier(ex, r.fichiers.map((f) => ({ nom: f.nom, contenu: f.contenu })));
    });
    setMessage(`Le code de la version ${version.numero} est repris dans l'éditeur : soumettez une nouvelle version pour le rendre.`);
  };

  // Envoi du devoir ; en mode automatique, ni confirmation ni blocage par le chargement.
  const envoyer = async (auto) => {
    if (!devoir) return;
    const nouvelleVersion = Boolean(soumission);
    const confirmation = nouvelleVersion
      ? 'Soumettre une nouvelle version ? La version précédente sera remplacée et la correction recommencera.'
      : 'Soumettre le devoir ? Le code de tous les exercices sera rendu et ne pourra plus être modifié.';
    if (!auto && !window.confirm(confirmation)) return;
    setSubmitting(true);
    setError('');
    setMessage('');
    const copies = devoir.exercices.map((ex) => [ex.id, travail(ex)]);
    try {
      const res = await api.post('/programming/soumissions/', {
        devoir: devoir.id,
        reponses: copies.map(([exercice, fichiersEnvoyes]) => ({ exercice, fichiers: fichiersEnvoyes })),
      });
      setSoumission(res.data);
      // Plus aucun envoi de brouillon en attente ; la copie de travail reste celle qui vient d'être rendue.
      confirmer(copies.map(([exercice]) => exercice));
      setFichiers(Object.fromEntries(copies));
      // Le serveur garde les brouillons quand la resoumission est permise : le dernier est remis à jour.
      if (devoir.resoumission_autorisee && !auto) copies.forEach(([exercice, fichiersEnvoyes]) => enregistrer(exercice, fichiersEnvoyes));
      let texte = 'Votre devoir a été soumis.';
      if (auto) texte = 'Le délai se termine : votre devoir a été soumis automatiquement.';
      else if (nouvelleVersion) texte = 'Votre nouvelle version a été soumise.';
      setMessage(texte);
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
  // Pendant une correction, `resoumission_possible` est faux : l'éditeur passe en lecture seule sur le code rendu,
  // puis revient à la fin avec la copie de travail intacte.
  const editable = (Boolean(etat.ouvert) && !soumis) || Boolean(soumission?.resoumission_possible);
  const principal = devoir.fichier_principal || null;

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
      const corps = { exercice: exercice.id, fichiers: travail(exercice), mode };
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
      {brouillonsIndisponibles && editable && (
        <div className="alert alert-error">Votre brouillon enregistré n'a pas pu être relu : rechargez la page avant de modifier votre code.</div>
      )}

      {soumis && (
        <div className="form-card" style={{ marginBottom: '24px' }}>
          <h3>Votre soumission</h3>
          <div>
            <span className={`badge ${soumission?.statut === 'corrige' ? 'badge-active' : 'badge-inactive'}`}>
              {STATUTS_SOUMISSION[soumission?.statut] || 'Soumis'}
            </span>
            {soumission?.date_soumission && (
              <span style={{ ...styleNote, marginLeft: '12px' }}>
                Rendu le {formatDate(soumission.date_soumission)}
                {soumission.numero_version > 1 && `, version ${soumission.numero_version}`}
                {soumission.soumission_auto && ' (soumission automatique)'}
              </span>
            )}
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
        const rendus = rendusDe(ex);
        // Copie de travail si l'éditeur est actif ou si rien n'a été rendu ; sinon le code rendu.
        const affiches = editable || !soumis ? travail(ex) : rendus;
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
              {!affiches ? (
                <p style={styleNote}>Aucune réponse rendue pour cet exercice.</p>
              ) : (
                <>
                  <strong>{soumis && !editable ? 'Code rendu' : 'Votre code'}</strong>
                  <EditeurFichiers fichiers={affiches} langage={devoir.langage} principal={principal} readOnly={!editable} height="300px"
                    espace={`${editable ? 'travail' : 'rendu'}-${ex.id}`} onChange={(maj) => modifier(ex, maj)} />
                  {editable && etats[ex.id] && (
                    <small role="status" style={{ ...styleNote, display: 'block', marginTop: '4px' }}>{libelleEnregistrement(etats[ex.id])}</small>
                  )}
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
                    disabled={essaiActif || !contenuPrincipalDe(affiches, principal).trim()}>Exécuter</button>
                  <button type="button" className="btn btn-secondary" onClick={() => executer(ex, 'test')}
                    disabled={essaiActif || !ex.tests_publics?.length || !contenuPrincipalDe(affiches, principal).trim()}>Tester</button>
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

      {soumission?.nombre_versions > 0 && (
        <div className="form-card" style={{ marginBottom: '24px' }}>
          <h3>Versions précédentes</h3>
          <HistoriqueVersions key={`${soumission.id}-${soumission.numero_version}`} soumissionId={soumission.id}
            langage={devoir.langage} principal={principal} onReprendre={editable ? reprendre : undefined} />
        </div>
      )}

      {editable && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '24px' }}>
          <button className="btn btn-primary" onClick={() => envoyer(false)} disabled={submitting || devoir.exercices.length === 0}>
            {submitting ? 'Soumission...' : (soumission ? 'Soumettre une nouvelle version' : 'Soumettre le devoir')}
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
