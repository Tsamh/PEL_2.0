import { useState, useEffect, useLayoutEffect, useCallback, useRef } from 'react';
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
import useBrouillons, { DELAI_REPRISE_MS, copieGagne, copiesAuto, estCompteCourant } from './useBrouillons';

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
const memesFichiers = (a, b) => Boolean(b) && a.length === b.length && a.every((f) => b.some((g) => g.nom === f.nom && g.contenu === f.contenu));
// Travail resté hors de ce qui est rendu, à signaler : { fichiers, enregistre } ou null. Après un rendu, seul un texte
// plus récent que ce rendu compte, sauf s'il vient d'être refusé (409) ou si le rendu est automatique (un brouillon plus
// ancien soumis par la clôture : ce texte n'a jamais été rendu) ; hors édition, le brouillon du serveur compte aussi.
function travailHorsRendu({ copie, brouillon, reference, dateRendu, conflit, soumis, auto, editable }) {
  if (editable && !conflit) return null;
  const differe = (liste) => !memesFichiers(liste, reference);
  const apresRendu = (date) => !dateRendu || (Boolean(date) && date > new Date(dateRendu).getTime());
  const copieRetenue = copie && differe(copie.fichiers) && (conflit || !soumis || auto || apresRendu(copie.date));
  const enregistre = soumis && !editable ? plein(brouillon?.fichiers) : null;
  const brouillonRetenu = enregistre && differe(enregistre) && apresRendu(new Date(brouillon.modifie_le).getTime());
  if (copieRetenue && (conflit || !brouillonRetenu || copieGagne(copie.date, brouillon))) return { fichiers: copie.fichiers, enregistre: false };
  return brouillonRetenu ? { fichiers: enregistre, enregistre: true } : null;
}
// Le code peut être modifié : devoir ouvert sans soumission, ou resoumission possible.
const estModifiable = (etat, soumission) => (Boolean(etat?.ouvert) && !etat?.soumis && !soumission) || Boolean(soumission?.resoumission_possible);
// Contenu du fichier principal (par son nom) ; à défaut de nom connu, celui du premier fichier.
const contenuPrincipalDe = (fichiers, principal) => (principal ? fichiers.find((f) => f.nom === principal) : fichiers[0])?.contenu ?? '';

const libelleEnregistrement = (etat) => {
  if (!etat) return '';
  if (etat.statut === 'enregistre') {
    const h = etat.heure;
    return `Enregistré à ${h.getHours()} h ${String(h.getMinutes()).padStart(2, '0')}`;
  }
  if (etat.statut === 'en_cours') return 'Enregistrement en cours...';
  if (etat.refus) return `Non enregistré : ${messageErreur(etat.refus, 'ce code a été refusé.')}`;
  return etat.conflit ? 'Non enregistré : ce devoir ne peut plus être modifié.' : 'Non enregistré : nouvelle tentative...';
};

// Avance de la soumission automatique sur l'heure de fermeture effective.
const AVANCE_AUTO_MS = 30000;
// Interrogation d'un essai en cours, et d'une soumission en cours de correction.
const INTERVALLE_ESSAI_MS = 1000;
const INTERVALLE_CORRECTION_MS = 3000;
const MESSAGE_EN_COURS = 'Une exécution est déjà en cours.';
// L'année archivée n'est pas exposée à l'étudiant, et la clôture du serveur n'y soumet rien.
const RESERVE_CLOTURE = "sauf si l'année académique est archivée";
const MESSAGE_COMPTE = "Le compte connecté dans ce navigateur a changé (autre connexion ou déconnexion) : cet onglet n'enregistre plus et ne soumet plus. Votre copie non enregistrée reste conservée dans cet onglet pour votre compte. Rechargez la page.";

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

// Copie de travail restée hors de ce qui est rendu : signalée, consultable en lecture seule.
function CopieNonRendue({ fichiers, langage, principal, espace, message }) {
  const [ouverte, setOuverte] = useState(false);
  return (
    <div style={{ marginTop: '12px' }}>
      <div className="alert alert-error" role="alert">
        {message}
      </div>
      <button type="button" className="btn btn-sm btn-outline" aria-expanded={ouverte} onClick={() => setOuverte(!ouverte)}>
        {ouverte ? 'Masquer cette copie' : 'Voir cette copie'}
      </button>
      {ouverte && <div style={{ marginTop: '8px' }}><EditeurFichiers fichiers={fichiers} langage={langage} principal={principal} readOnly height="300px" espace={espace} /></div>}
    </div>
  );
}

function DevoirEtudiant({ id, utilisateurId }) {
  const navigate = useNavigate();
  const [devoir, setDevoir] = useState(null);
  const [soumission, setSoumission] = useState(null);
  // `fichiers` : copie de travail par exercice (absente tant que l'étudiant n'a rien modifié) ;
  // `brouillons` : brouillons lus sur le serveur au chargement.
  const [fichiers, setFichiers] = useState({});
  const [brouillons, setBrouillons] = useState({});
  // Lectures de brouillons échouées d'affilée : tant qu'il y en a, ni édition ni soumission depuis le navigateur.
  const [echecsBrouillons, setEchecsBrouillons] = useState(0);
  const [essais, setEssais] = useState({});
  const [entrees, setEntrees] = useState({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  // Échec d'une soumission : gardé par les relectures de l'état, effacé seulement par une soumission réussie.
  const [erreurSoumission, setErreurSoumission] = useState('');
  // Un autre compte a pris le jeton de ce navigateur : plus aucun envoi depuis cet onglet, jusqu'au rechargement.
  const [compteRemplace, setCompteRemplace] = useState(false);
  const brouillonsIndisponibles = echecsBrouillons > 0;
  const bloque = submitting || brouillonsIndisponibles || compteRemplace;
  const autoLance = useRef(false);
  const envoiRef = useRef(null);
  const minuteurs = useRef({});
  const fichiersRef = useRef({});
  const chargerRef = useRef(null);
  const {
    enregistrer, etats, charger: lireBrouillons, confirmer, lireCopie, oublierCopie, frappeDe,
  } = useBrouillons(id, utilisateurId, { surConflit: () => chargerRef.current?.() });

  useEffect(() => { fichiersRef.current = fichiers; });

  // Seconde ligne contre un changement de texte venu du programme : à jour avant les effets passifs de l'éditeur.
  const modifiableRef = useRef(false);
  const peutModifier = estModifiable(devoir?.etat, soumission) && !bloque;
  useLayoutEffect(() => { modifiableRef.current = peutModifier; });

  // Vérifié juste avant chaque envoi : l'événement `storage` n'arrive pas dans l'onglet qui change le jeton.
  const compteIntact = useCallback(() => {
    const intact = estCompteCourant(utilisateurId);
    if (!intact) setCompteRemplace(true);
    return intact;
  }, [utilisateurId]);
  useEffect(() => {
    const surStockage = (ev) => { if (ev.key === 'access_token' || ev.key === null) compteIntact(); };
    window.addEventListener('storage', surStockage);
    return () => window.removeEventListener('storage', surStockage);
  }, [compteIntact]);

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
      if (!compteIntact()) return;
      const [res, subs, serveur] = await Promise.all([
        api.get(`/programming/devoirs/${id}/`),
        chargerTout('/programming/soumissions/', { devoir: id }),
        lireBrouillons(),
      ]);
      // Réponses lues sous un autre compte : ni affichées, ni comparées à la copie locale de l'étudiant.
      if (!compteIntact()) return;
      const sub = subs.find((s) => s.devoir === res.data.id) || null;
      setDevoir(res.data);
      setSoumission(sub);
      // Les brouillons du serveur ne touchent jamais une copie de travail déjà en cours.
      if (serveur) setBrouillons(serveur);
      setEchecsBrouillons((n) => (serveur ? 0 : n + 1));
      // Copie de l'onglet non confirmée contre brouillon du serveur (tous deux connus) : la plus récente l'emporte.
      // Gagnante, elle reprend la place de la copie de travail et repart au serveur ; perdante, elle est oubliée.
      if (serveur) {
        const modifiable = estModifiable(res.data.etat, sub);
        res.data.exercices.forEach((ex) => {
          const locale = fichiersRef.current[ex.id] ? null : lireCopie(ex.id);
          if (!locale) return;
          if (!copieGagne(locale.date, serveur[ex.id])) { oublierCopie(ex.id); return; }
          if (!modifiable) return;
          setFichiers((avant) => (avant[ex.id] ? avant : { ...avant, [ex.id]: locale.fichiers }));
          enregistrer(ex.id, locale.fichiers, locale.date ?? Date.now());
        });
      }
      setError('');
    } catch (err) {
      setError(messageErreur(err, 'Devoir introuvable.'));
      setEchecsBrouillons((n) => (n ? n + 1 : n));
    } finally {
      setLoading(false);
    }
  }, [id, lireBrouillons, enregistrer, lireCopie, oublierCopie, compteIntact]);

  useEffect(() => { chargerRef.current = charger; charger(); }, [charger]);

  // Brouillons illisibles : nouvelle lecture après un délai, jusqu'au succès ou au démontage.
  useEffect(() => {
    if (!echecsBrouillons) return undefined;
    const minuteur = setTimeout(() => chargerRef.current?.(), DELAI_REPRISE_MS);
    return () => clearTimeout(minuteur);
  }, [echecsBrouillons]);

  const rendusDe = (ex) => plein(soumission?.reponses?.find((r) => r.exercice === ex.id)?.fichiers);
  // Copie de travail : celle en cours (dont une copie locale reprise au chargement), sinon brouillon du serveur,
  // version rendue, fichiers de départ.
  const travail = (ex) => fichiers[ex.id]
    ?? plein(brouillons[ex.id]?.fichiers) ?? rendusDe(ex) ?? fichiersDeDepart(ex, devoir);
  const modifier = (ex, maj) => {
    if (!modifiableRef.current) return;
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
    if (!devoir || !compteIntact()) return;
    const nouvelleVersion = Boolean(soumission);
    const confirmation = nouvelleVersion
      ? 'Soumettre une nouvelle version ? La version précédente sera remplacée et la correction recommencera.'
      : `Soumettre le devoir ? Le code de tous les exercices sera rendu${devoir.resoumission_autorisee ? '. Vous pourrez soumettre une nouvelle version tant que le devoir reste ouvert.' : ' et ne pourra plus être modifié.'}`;
    if (!auto && !window.confirm(confirmation)) return;
    setSubmitting(true);
    setError('');
    setMessage('');
    try {
      let copies = devoir.exercices.map((ex) => [ex.id, travail(ex)]);
      if (auto) {
        // Un autre onglet a pu travailler depuis : pour chaque exercice, le plus récent de cet onglet et du serveur.
        const serveur = await lireBrouillons();
        if (!serveur) {
          setEchecsBrouillons((n) => n + 1);
          setErreurSoumission(`La soumission automatique n'a pas eu lieu : vos brouillons n'ont pas pu être relus. Si une version a déjà été enregistrée, elle sera soumise automatiquement à la fermeture, ${RESERVE_CLOTURE}.`);
          return;
        }
        copies = copiesAuto(devoir.exercices.map((ex) => ex.id), {
          frappe: frappeDe,
          copie: (exercice) => fichiersRef.current[exercice],
          brouillon: (exercice) => serveur[exercice],
          depart: (exercice) => fichiersDeDepart(devoir.exercices.find((ex) => ex.id === exercice), devoir),
        });
        // Devoir jamais touché : comme la clôture, rien n'est soumis.
        if (!copies) return;
      }
      if (!compteIntact()) return;
      const res = await api.post('/programming/soumissions/', {
        devoir: devoir.id,
        reponses: copies.map(([exercice, fichiersEnvoyes]) => ({ exercice, fichiers: fichiersEnvoyes })),
      });
      setSoumission(res.data);
      setErreurSoumission('');
      // Plus aucun envoi de brouillon en attente ; la copie de travail reste celle qui vient d'être rendue.
      confirmer(devoir.exercices.map((ex) => ex.id));
      setFichiers(Object.fromEntries(copies));
      // Le serveur garde les brouillons quand la resoumission est permise : le dernier est remis à jour.
      if (devoir.resoumission_autorisee && !auto) copies.forEach(([exercice, fichiersEnvoyes]) => enregistrer(exercice, fichiersEnvoyes));
      let texte = 'Votre devoir a été soumis.';
      if (auto) texte = 'Le délai se termine : votre devoir a été soumis automatiquement.';
      else if (nouvelleVersion) texte = 'Votre nouvelle version a été soumise.';
      setMessage(texte);
      charger();
    } catch (err) {
      setErreurSoumission(messageErreur(err, 'Erreur lors de la soumission.'));
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
      if (!compteIntact()) return;
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
  }, [soumissionId, enCorrection, compteIntact]);

  if (loading) return <div className="loading">Chargement...</div>;
  if (!devoir) return <div className="alert alert-error">{compteRemplace ? MESSAGE_COMPTE : error}</div>;

  const etat = devoir.etat || {};
  const soumis = Boolean(etat.soumis || soumission);
  // Pendant une correction, `resoumission_possible` est faux : l'éditeur passe en lecture seule sur le code rendu,
  // puis revient à la fin avec la copie de travail intacte.
  const editable = estModifiable(etat, soumission);
  const principal = devoir.fichier_principal || null;

  const executable = devoir.langage !== 'autre';
  // Une seule exécution à la fois par utilisateur : les boutons de tous les exercices attendent la fin.
  const essaiActif = Object.values(essais).some((e) => e.envoi || (e.execution && executionActive(e.execution.statut)));
  const majEssai = (exerciceId, valeur) => setEssais((e) => ({ ...e, [exerciceId]: valeur }));

  const suivre = (exerciceId, executionId) => {
    const relire = async () => {
      if (!compteIntact()) return;
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
    if (!compteIntact()) return;
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
    else if (echu && brouillonsIndisponibles) messageFenetre = 'Le délai est écoulé.';
    else if (echu && Object.keys(brouillons).length > 0) messageFenetre = `Le délai est écoulé : votre dernière version enregistrée sera soumise automatiquement, ${RESERVE_CLOTURE}.`;
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

      {compteRemplace && <div className="alert alert-error" role="alert">{MESSAGE_COMPTE}</div>}
      {message && <div className="alert alert-success">{message}</div>}
      {erreurSoumission && <div className="alert alert-error">{erreurSoumission}</div>}
      {error && <div className="alert alert-error">{error}</div>}
      {messageFenetre && <div className="alert alert-error">{messageFenetre}</div>}
      {brouillonsIndisponibles && (editable || !soumis) && (
        <div className="alert alert-error">
          Vos brouillons enregistrés n'ont pas pu être relus : le code affiché n'est peut-être pas votre dernière version.
          L'éditeur et la soumission restent bloqués, nouvelle tentative en cours.
          {!soumission && (etat.fenetre?.fermeture
            ? ` Si une version a déjà été enregistrée, elle reste conservée et sera soumise automatiquement à la fermeture, ${RESERVE_CLOTURE}.`
            : ' Les versions déjà enregistrées restent conservées.')}
        </div>
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
        // Référence hors édition : le code rendu ; sans soumission, le brouillon que la clôture soumettra.
        const reference = soumis ? rendusDe(ex) : plein(brouillons[ex.id]?.fichiers);
        const affiches = editable || (!soumis && !reference) ? travail(ex) : reference;
        const copie = fichiers[ex.id] ? { fichiers: fichiers[ex.id], date: frappeDe(ex.id) } : lireCopie(ex.id);
        const horsRendu = (soumis || !brouillonsIndisponibles) && travailHorsRendu({
          copie, brouillon: brouillons[ex.id], reference, dateRendu: soumission?.date_soumission, conflit: etats[ex.id]?.conflit, soumis, auto: soumission?.soumission_auto, editable,
        });
        // Déjà rendu et encore modifiable : « Enregistré à... » ne veut pas dire « sera soumis » (la clôture ne remplace pas une version).
        const aDuTravail = fichiers[ex.id] || plein(brouillons[ex.id]?.fichiers);
        const nonSoumis = editable && soumission && aDuTravail && !horsRendu && !compteRemplace && !memesFichiers(travail(ex), rendusDe(ex));
        let messageHorsRendu = "Votre copie de travail n'a pas été enregistrée : ces modifications ne seront pas soumises.";
        if (horsRendu && horsRendu.enregistre) {
          // Pendant une correction, l'édition peut revenir : le travail enregistré peut encore être soumis.
          const repris = enCorrection && devoir.resoumission_autorisee && etat.ouvert;
          messageHorsRendu = `Votre travail enregistré diffère du code rendu : il n'a pas été soumis${repris ? '' : ' et ne le sera pas'}.`;
        } else if (soumis) messageHorsRendu = "Votre copie de travail diffère du code rendu : ces modifications n'ont pas été rendues.";
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
                  <EditeurFichiers fichiers={affiches} langage={devoir.langage} principal={principal} readOnly={!editable || bloque} height="300px"
                    espace={`${editable ? 'travail' : 'rendu'}-${ex.id}-v${soumission?.numero_version ?? 0}`} onChange={(maj) => modifier(ex, maj)} />
                  {editable && !compteRemplace && etats[ex.id] && (
                    <small role="status" style={{ ...styleNote, display: 'block', marginTop: '4px' }}>{libelleEnregistrement(etats[ex.id])}</small>
                  )}
                  {nonSoumis && (
                    <div className="alert alert-error" style={{ marginTop: '8px' }}>
                      Vos modifications ne sont pas soumises : à la fermeture, seule la version {soumission.numero_version} compte. Cliquez sur « Soumettre une nouvelle version ».
                    </div>
                  )}
                </>
              )}
            </div>
            {horsRendu && <CopieNonRendue fichiers={horsRendu.fichiers} langage={devoir.langage} principal={principal} espace={`copie-${ex.id}`} message={messageHorsRendu} />}

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
            langage={devoir.langage} principal={principal} onReprendre={editable && !bloque ? reprendre : undefined} />
        </div>
      )}

      {editable && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '24px' }}>
          <button className="btn btn-primary" onClick={() => envoyer(false)} disabled={bloque || devoir.exercices.length === 0}>
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
  return user?.role === 'etudiant' ? <DevoirEtudiant id={id} utilisateurId={user.id} /> : <ApercuGestion id={id} />;
}
