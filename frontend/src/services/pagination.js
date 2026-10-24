import api from './api';

// Charge toutes les pages d'une liste paginée par DRF ({ count, next, results }) ; renvoie la liste complète.
export async function chargerTout(url, params) {
  let res = await api.get(url, { params });
  if (!res.data || !Array.isArray(res.data.results)) return res.data;
  const tout = [...res.data.results];
  while (res.data.next) {
    res = await api.get(res.data.next);
    tout.push(...res.data.results);
  }
  return tout;
}
