import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../../services/api';

// Auto-sauvegarde des brouillons d'un devoir : un envoi à la fois par exercice, la dernière valeur partant à la fin
// de l'envoi en cours. La copie de l'onglet (sessionStorage, par utilisateur, avec la date de la frappe) n'est effacée
// que lorsque le serveur a confirmé exactement la valeur envoyée, ou à la déconnexion explicite.

export const DELAI_SAISIE_MS = 3000;
export const DELAI_REPRISE_MS = 10000;

const PREFIXE_LOCAL = 'pel-brouillon-';
const cleLocale = (utilisateurId, devoirId, exerciceId) => `${PREFIXE_LOCAL}u${utilisateurId}-devoir-${devoirId}-${exerciceId}`;

// DEBUT-ENREGISTREUR (logique pure, sans React : vérifiable hors navigateur)
// Copie locale stockée : { fichiers, date } (ms). Un tableau nu (ancien format) n'a pas de date.
export function analyserCopie(brut) {
  let valeur;
  try { valeur = brut ? JSON.parse(brut) : null; } catch { return null; }
  const ancien = Array.isArray(valeur);
  const fichiers = ancien ? valeur : valeur?.fichiers;
  if (!Array.isArray(fichiers) || fichiers.length === 0) return null;
  return { fichiers, date: ancien ? null : Number(valeur.date) || null };
}

// Le plus récent l'emporte : une copie datée d'une frappe (ms) contre un brouillon du serveur { modifie_le }.
// Sans brouillon, la copie gagne ; sans date, elle perd contre un brouillon ; à égalité, le serveur gagne.
export const copieGagne = (date, brouillon) => {
  if (!brouillon) return true;
  return date !== null && date !== undefined && date > new Date(brouillon.modifie_le).getTime();
};

// Soumission automatique : [[exerciceId, fichiers]], ou null si l'étudiant n'a ni frappe ni brouillon (rien à soumettre).
// Un exercice sans frappe ni brouillon n'a ses fichiers de départ que si l'étudiant n'a aucun brouillon (comme la clôture).
export function copiesAuto(exerciceIds, { frappe, copie, brouillon, depart }) {
  const aFrappe = (id) => frappe(id) !== null && frappe(id) !== undefined && Boolean(copie(id));
  const unBrouillon = exerciceIds.some((id) => brouillon(id));
  if (!unBrouillon && !exerciceIds.some(aFrappe)) return null;
  const copies = [];
  exerciceIds.forEach((id) => {
    if (aFrappe(id) && copieGagne(frappe(id), brouillon(id))) copies.push([id, copie(id)]);
    else if (brouillon(id)) copies.push([id, brouillon(id).fichiers]);
    else if (!unBrouillon) copies.push([id, depart(id)]);
  });
  return copies;
}

export function creerEnregistreur({
  envoyer, ecrire, effacer, surEtat, surConflit, delaiSaisie = DELAI_SAISIE_MS, delaiReprise = DELAI_REPRISE_MS,
}) {
  const suivis = new Map();
  let demonte = false;
  let generation = 0;

  const suivi = (exercice) => {
    if (!suivis.has(exercice)) suivis.set(exercice, { valeur: null, sale: false, enVol: false, minuteur: null, arret: false });
    return suivis.get(exercice);
  };
  const signaler = (exercice, etat) => { if (!demonte) surEtat(exercice, etat); };
  const arreterMinuteur = (s) => { clearTimeout(s.minuteur); s.minuteur = null; };
  const planifier = (exercice, s, delai) => {
    arreterMinuteur(s);
    s.minuteur = setTimeout(() => { s.minuteur = null; partir(exercice); }, delai);
  };

  function partir(exercice) {
    const s = suivi(exercice);
    arreterMinuteur(s);
    if (!s.sale || s.enVol || s.arret) return;
    const valeur = s.valeur;
    const miseEnRoute = generation;
    s.sale = false;
    s.enVol = true;
    signaler(exercice, { statut: 'en_cours' });
    Promise.resolve().then(() => envoyer(exercice, valeur)).then((heure) => {
      s.enVol = false;
      // Seule la valeur exacte confirmée efface la copie locale.
      if (s.valeur === valeur) effacer(exercice);
      // Une valeur plus récente attendait : elle part tout de suite.
      if (s.sale) { partir(exercice); return; }
      if (miseEnRoute === generation) signaler(exercice, { statut: 'enregistre', heure });
    }, (erreur) => {
      s.enVol = false;
      if (miseEnRoute !== generation) {
        // Envoi antérieur à une soumission : son échec n'est pas signalé, une saisie plus récente part.
        if (s.sale && !s.minuteur) partir(exercice);
        return;
      }
      if (erreur?.response?.status === 409) {
        s.arret = true;
        signaler(exercice, { statut: 'erreur', conflit: true });
        if (!demonte) surConflit?.();
        return;
      }
      // Refus définitif de cette valeur : pas de reprise, seule une saisie plus récente repart.
      if (erreur?.response?.status === 400) {
        signaler(exercice, { statut: 'erreur', refus: erreur });
        if (s.sale && !s.minuteur) partir(exercice);
        return;
      }
      s.sale = true;
      signaler(exercice, { statut: 'erreur' });
      if (!demonte && !s.minuteur) planifier(exercice, s, s.valeur === valeur ? delaiReprise : 0);
    });
  }

  return {
    enregistrer(exercice, fichiers) {
      if (demonte) return;
      const s = suivi(exercice);
      s.valeur = fichiers;
      s.sale = true;
      ecrire(exercice, fichiers);
      if (s.arret) return;
      signaler(exercice, { statut: 'en_cours' });
      planifier(exercice, s, delaiSaisie);
    },
    // Envoi immédiat de ce qui attend (onglet passé en arrière-plan).
    tout() { suivis.forEach((s, exercice) => partir(exercice)); },
    // Après une relecture de l'état du devoir : un exercice arrêté par une 409 peut repartir.
    reprendre() {
      suivis.forEach((s, exercice) => {
        if (!s.arret) return;
        s.arret = false;
        if (s.sale) planifier(exercice, s, delaiSaisie);
      });
    },
    // Après une soumission : plus rien n'attend, une réponse tardive n'est plus signalée.
    annuler() {
      generation += 1;
      suivis.forEach((s) => { arreterMinuteur(s); s.sale = false; s.valeur = null; s.arret = false; });
    },
    // Démontage : ce qui attendait part une fois, sans mise à jour d'état ensuite.
    arreter() {
      demonte = true;
      suivis.forEach((s, exercice) => { arreterMinuteur(s); if (s.sale && !s.arret) partir(exercice); });
    },
  };
}
// FIN-ENREGISTREUR

// Enregistreurs des pages ouvertes : la déconnexion leur fait envoyer ce qui attend avant le retrait des jetons.
const actifs = new Set();

// À appeler avant de retirer les jetons (déconnexion explicite) : l'envoi final part avec le jeton encore valable, et
// aucune copie non confirmée ne reste pour le prochain compte. Une session expirée (401) ne passe pas ici : la copie
// reste sous la clé de l'étudiant, qui la retrouve en se reconnectant.
export function avantDeconnexion() {
  const jeton = window.localStorage.getItem('access_token');
  actifs.forEach((figer) => figer(jeton));
  try {
    Object.keys(window.sessionStorage).filter((cle) => cle.startsWith(PREFIXE_LOCAL))
      .forEach((cle) => window.sessionStorage.removeItem(cle));
  } catch { /* stockage indisponible */ }
}

// Brouillons du devoir `devoirId` pour l'étudiant `utilisateurId`.
// `enregistrer(exerciceId, fichiers, date?)` ; `etats[exerciceId]` = { statut: 'enregistre' | 'en_cours' | 'erreur', heure } ;
// `charger()` relit les brouillons du serveur ({ exerciceId: { fichiers, modifie_le } }, null en cas d'échec) ;
// `confirmer(exerciceIds)` : à appeler après une soumission réussie (annule les envois, efface les copies locales) ;
// `lireCopie`, `oublierCopie` : copie locale d'un exercice ; `frappeDe` : date de la dernière frappe de cet onglet.
export default function useBrouillons(devoirId, utilisateurId, { surConflit } = {}) {
  const [etats, setEtats] = useState({});
  const enregistreur = useRef(null);
  const frappes = useRef({});
  const conflitRef = useRef(surConflit);
  useEffect(() => { conflitRef.current = surConflit; });

  const lireCopie = useCallback((exerciceId) => {
    try { return analyserCopie(window.sessionStorage.getItem(cleLocale(utilisateurId, devoirId, exerciceId))); } catch { return null; }
  }, [utilisateurId, devoirId]);
  const oublierCopie = useCallback((exerciceId) => {
    try { window.sessionStorage.removeItem(cleLocale(utilisateurId, devoirId, exerciceId)); } catch { /* stockage indisponible */ }
  }, [utilisateurId, devoirId]);

  useEffect(() => {
    let jetonFige = null;
    const instance = creerEnregistreur({
      envoyer: async (exercice, fichiers) => {
        // Après une déconnexion : jamais sous le compte qui s'est connecté entre-temps.
        const courant = window.localStorage.getItem('access_token');
        if (jetonFige && courant && courant !== jetonFige) throw new Error('Session remplacée');
        const config = jetonFige ? { headers: { Authorization: `Bearer ${jetonFige}` } } : undefined;
        const res = await api.put(`/programming/devoirs/${devoirId}/brouillons/`, { exercice, fichiers }, config);
        return res.data.modifie_le ? new Date(res.data.modifie_le) : new Date();
      },
      ecrire: (exercice, fichiers) => {
        const copie = JSON.stringify({ fichiers, date: frappes.current[exercice] });
        try { window.sessionStorage.setItem(cleLocale(utilisateurId, devoirId, exercice), copie); } catch { /* stockage indisponible */ }
      },
      effacer: oublierCopie,
      surEtat: (exercice, etat) => setEtats((avant) => ({ ...avant, [exercice]: etat })),
      surConflit: () => conflitRef.current?.(),
    });
    enregistreur.current = instance;
    const figer = (jeton) => { jetonFige = jeton; instance.arreter(); };
    actifs.add(figer);
    const arrierePlan = () => { if (document.visibilityState === 'hidden') instance.tout(); };
    document.addEventListener('visibilitychange', arrierePlan);
    return () => {
      document.removeEventListener('visibilitychange', arrierePlan);
      actifs.delete(figer);
      instance.arreter();
      enregistreur.current = null;
    };
  }, [devoirId, utilisateurId, oublierCopie]);

  const enregistrer = useCallback((exerciceId, fichiers, date = Date.now()) => {
    frappes.current[exerciceId] = date;
    enregistreur.current?.enregistrer(exerciceId, fichiers);
  }, []);
  const frappeDe = useCallback((exerciceId) => frappes.current[exerciceId] ?? null, []);

  const charger = useCallback(async () => {
    try {
      const res = await api.get(`/programming/devoirs/${devoirId}/brouillons/`);
      enregistreur.current?.reprendre();
      return Object.fromEntries(res.data.map((b) => [b.exercice, { fichiers: b.fichiers, modifie_le: b.modifie_le }]));
    } catch {
      return null;
    }
  }, [devoirId]);

  const confirmer = useCallback((exerciceIds) => {
    enregistreur.current?.annuler();
    frappes.current = {};
    exerciceIds.forEach((id) => oublierCopie(id));
    setEtats({});
  }, [oublierCopie]);

  return { enregistrer, etats, charger, confirmer, lireCopie, oublierCopie, frappeDe };
}
