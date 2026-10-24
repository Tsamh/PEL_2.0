import api from './api';

// Télécharge un fichier servi par l'API (l'en-tête d'authentification empêche un simple lien).
export async function telecharger(url, nomFichier) {
  const res = await api.get(url, { responseType: 'blob' });
  const lien = document.createElement('a');
  lien.href = URL.createObjectURL(res.data);
  lien.download = nomFichier;
  document.body.appendChild(lien);
  lien.click();
  lien.remove();
  URL.revokeObjectURL(lien.href);
}
