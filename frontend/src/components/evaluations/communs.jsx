// Utilitaires partagés par les éditeurs d'évaluations (quiz et devoirs).

// Date ISO du serveur vers le format d'un champ <input type="datetime-local">.
export function versChampLocal(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export const STATUTS_VALIDATION = { en_attente: ['badge-pending', 'En attente de validation'], refusee: ['badge-inactive', 'Refusé'] };

export function badgeStatut(item) {
  if (item.est_publie) return <span className="badge badge-active">Publié</span>;
  if (item.validation_requise && STATUTS_VALIDATION[item.statut_validation]) {
    const [classe, libelle] = STATUTS_VALIDATION[item.statut_validation];
    return <span className={`badge ${classe}`}>{libelle}</span>;
  }
  if (item.validation_requise && item.statut_validation === 'validee') return <span className="badge badge-inactive">Validé, non publié</span>;
  return <span className="badge badge-inactive">Brouillon</span>;
}
