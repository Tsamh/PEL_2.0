// Premier message lisible d'une erreur axios renvoyée par l'API (detail, error ou erreurs de champs).
export function messageErreur(err, defaut = 'Une erreur est survenue.') {
  const data = err?.response?.data;
  if (!data || typeof data === 'string') return defaut;
  const premier = (valeur) => {
    if (typeof valeur === 'string') return valeur;
    if (Array.isArray(valeur)) {
      for (const v of valeur) {
        const m = premier(v);
        if (m) return m;
      }
      return null;
    }
    if (valeur && typeof valeur === 'object') {
      for (const v of Object.values(valeur)) {
        const m = premier(v);
        if (m) return m;
      }
    }
    return null;
  };
  return premier(data.detail ?? data.error ?? data) || defaut;
}
