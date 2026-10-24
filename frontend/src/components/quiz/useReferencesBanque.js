import { useCallback, useEffect, useState } from 'react';
import api from '../../services/api';
import { chargerTout } from '../../services/pagination';
import { messageErreur } from '../../services/erreurs';

// Matières et tags de la banque, pour les filtres et l'autocomplétion.
export default function useReferencesBanque() {
  const [ecs, setEcs] = useState([]);
  const [tags, setTags] = useState({ chapitre: [], competence: [] });
  const [erreur, setErreur] = useState('');

  const rechargerTags = useCallback(() => Promise.all([
    api.get('/quiz/banque/tags/', { params: { type: 'chapitre' } }),
    api.get('/quiz/banque/tags/', { params: { type: 'competence' } }),
  ]).then(([c, k]) => setTags({ chapitre: c.data, competence: k.data }))
    .catch((err) => setErreur(messageErreur(err, 'Erreur lors du chargement des tags.'))), []);

  useEffect(() => {
    chargerTout('/referentiel/ecs/').then(setEcs)
      .catch((err) => setErreur(messageErreur(err, 'Erreur lors du chargement des matières.')));
    rechargerTags();
  }, [rechargerTags]);

  return { ecs, tags, erreur, rechargerTags };
}
