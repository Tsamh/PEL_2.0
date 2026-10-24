import { useCallback, useEffect, useState } from 'react';
import api from '../../services/api';
import { messageErreur } from '../../services/erreurs';
import { requeteBanque } from './banqueFiltres';

// Liste paginée de la banque selon les filtres, avec « afficher plus ».
export default function useListeBanque(filtres) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [suivant, setSuivant] = useState(null);
  const [loading, setLoading] = useState(true);
  const [erreur, setErreur] = useState('');

  const recharger = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/quiz/banque/?${requeteBanque(filtres)}`);
      setItems(res.data.results);
      setTotal(res.data.count);
      setSuivant(res.data.next);
      setErreur('');
    } catch (err) {
      setErreur(messageErreur(err, 'Erreur lors du chargement de la banque.'));
    } finally {
      setLoading(false);
    }
  }, [filtres]);

  useEffect(() => { recharger(); }, [recharger]);

  const plus = useCallback(async () => {
    if (!suivant) return;
    try {
      const res = await api.get(suivant);
      setItems((liste) => [...liste, ...res.data.results]);
      setSuivant(res.data.next);
    } catch (err) {
      setErreur(messageErreur(err, 'Erreur lors du chargement de la banque.'));
    }
  }, [suivant]);

  return { items, total, suivant, loading, erreur, recharger, plus };
}
