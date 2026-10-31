import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../../services/api';

// Auto-sauvegarde des brouillons d'un devoir : un envoi à la fois par exercice, la dernière valeur partant à la fin
// de l'envoi en cours. La copie de l'onglet (sessionStorage) n'est effacée que lorsque le serveur a confirmé
// exactement la valeur envoyée.

export const DELAI_SAISIE_MS = 3000;
export const DELAI_REPRISE_MS = 10000;

const cleLocale = (devoirId, exerciceId) => `pel-brouillon-devoir-${devoirId}-${exerciceId}`;

export const lireLocal = (devoirId, exerciceId) => {
  try {
    const brut = window.sessionStorage.getItem(cleLocale(devoirId, exerciceId));
    const fichiers = brut ? JSON.parse(brut) : null;
    return Array.isArray(fichiers) && fichiers.length > 0 ? fichiers : null;
  } catch { return null; }
};
const ecrireLocal = (devoirId, exerciceId, fichiers) => {
  try { window.sessionStorage.setItem(cleLocale(devoirId, exerciceId), JSON.stringify(fichiers)); } catch { /* stockage indisponible */ }
};
const effacerLocal = (devoirId, exerciceId) => {
  try { window.sessionStorage.removeItem(cleLocale(devoirId, exerciceId)); } catch { /* stockage indisponible */ }
};

// DEBUT-ENREGISTREUR (logique pure, sans React : vérifiable hors navigateur)
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
      s.sale = true;
      signaler(exercice, { statut: 'erreur' });
      if (!demonte && !s.minuteur) planifier(exercice, s, s.valeur === valeur ? delaiReprise : 0);
    });
  }

  return {
    enregistrer(exercice, fichiers) {
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

// Brouillons du devoir `devoirId` pour l'étudiant connecté.
// `enregistrer(exerciceId, fichiers)` ; `etats[exerciceId]` = { statut: 'enregistre' | 'en_cours' | 'erreur', heure } ;
// `charger()` relit les brouillons du serveur ({ exerciceId: fichiers }, null en cas d'échec) ;
// `confirmer(exerciceIds)` : à appeler après une soumission réussie (annule les envois, efface les copies locales).
export default function useBrouillons(devoirId, { surConflit } = {}) {
  const [etats, setEtats] = useState({});
  const enregistreur = useRef(null);
  const conflitRef = useRef(surConflit);
  useEffect(() => { conflitRef.current = surConflit; });

  useEffect(() => {
    const instance = creerEnregistreur({
      envoyer: async (exercice, fichiers) => {
        const res = await api.put(`/programming/devoirs/${devoirId}/brouillons/`, { exercice, fichiers });
        return res.data.modifie_le ? new Date(res.data.modifie_le) : new Date();
      },
      ecrire: (exercice, fichiers) => ecrireLocal(devoirId, exercice, fichiers),
      effacer: (exercice) => effacerLocal(devoirId, exercice),
      surEtat: (exercice, etat) => setEtats((avant) => ({ ...avant, [exercice]: etat })),
      surConflit: () => conflitRef.current?.(),
    });
    enregistreur.current = instance;
    const arrierePlan = () => { if (document.visibilityState === 'hidden') instance.tout(); };
    document.addEventListener('visibilitychange', arrierePlan);
    return () => {
      document.removeEventListener('visibilitychange', arrierePlan);
      instance.arreter();
      enregistreur.current = null;
    };
  }, [devoirId]);

  const enregistrer = useCallback((exerciceId, fichiers) => enregistreur.current?.enregistrer(exerciceId, fichiers), []);

  const charger = useCallback(async () => {
    try {
      const res = await api.get(`/programming/devoirs/${devoirId}/brouillons/`);
      enregistreur.current?.reprendre();
      return Object.fromEntries(res.data.map((b) => [b.exercice, b.fichiers]));
    } catch {
      return null;
    }
  }, [devoirId]);

  const confirmer = useCallback((exerciceIds) => {
    enregistreur.current?.annuler();
    exerciceIds.forEach((id) => effacerLocal(devoirId, id));
    setEtats({});
  }, [devoirId]);

  return { enregistrer, etats, charger, confirmer };
}
